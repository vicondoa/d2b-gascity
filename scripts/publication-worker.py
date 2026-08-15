#!/usr/bin/env python3
"""Deterministic trusted worker for the d2b publication stage."""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping


PUBLICATION_MARKER = (
    "gc.publication.worker_marker=d2b-gascity-publication-worker-v1"
)
PUBLISH_KEY = "gc.publication.push"
OPEN_PR_KEY = "gc.publication.open_pr"
ROOT_KEY = "gc.root_bead_id"
INPUT_CONVOY_KEY = "gc.input_convoy_id"
SYNTHETIC_KIND_KEY = "gc.synthetic_kind"
DRAIN_MEMBER_KEY = "gc.drain_member_id"
WORKTREE_KEY = "work_dir"
BASE_REF_KEY = "gc.publication.base_ref"
BASE_SHA_KEY = "gc.publication.base_sha"
EXPECTED_HEAD_KEY = "gc.publication.expected_head_sha"
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
BEAD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
PULL_URL = re.compile(
    r"^https://github\.com/vicondoa/d2b/pull/[1-9][0-9]*$"
)
HELPER_ERROR = re.compile(r"^publish-pr: ([a-z0-9][a-z0-9-]*)$")
HELPER_TIMEOUT = 300
RETRYABLE_HELPER_CODES = frozenset(
    {
        "base-refresh-failed",
        "base-remote-unavailable",
        "beads-anchor-metadata-missing",
        "beads-anchor-mismatch",
        "beads-anchor-missing",
        "beads-readback-mismatch",
        "beads-response-invalid",
        "beads-show-unavailable",
        "beads-update-failed",
        "command-unavailable",
        "github-create-unavailable",
        "github-create-unobserved",
        "github-list-unavailable",
        "github-response-invalid",
        "remote-state-invalid",
        "remote-state-unavailable",
        "remote-head-unverified",
    }
)


class WorkerError(RuntimeError):
    """A redacted, machine-readable worker failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class MetadataCommitError(WorkerError):
    """A metadata commit failed before the claimed step could close."""


def _run(
    argv: list[str],
    *,
    cwd: pathlib.Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 60,
    timeout_code: str = "command-unavailable",
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            close_fds=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise WorkerError(timeout_code) from error
    except OSError as error:
        raise WorkerError("command-unavailable") from error


def _resolve_git() -> str:
    value = shutil.which("git")
    if value is None:
        raise WorkerError("git-unavailable")
    path = pathlib.Path(value)
    try:
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            raise WorkerError("git-unavailable")
        return str(path)
    except WorkerError:
        raise
    except OSError as error:
        raise WorkerError("git-unavailable") from error


def _git_environment(git: str) -> dict[str, str]:
    config = (
        ("core.fsmonitor", "false"),
        ("core.hooksPath", "/dev/null"),
        ("credential.helper", ""),
        ("core.sshCommand", "/bin/false"),
    )
    environment = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/false",
        "GIT_SSH": "/bin/false",
        "GIT_SSH_COMMAND": "/bin/false",
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "NO_COLOR": "1",
        "PATH": str(pathlib.Path(git).parent),
        "GIT_CONFIG_COUNT": str(len(config)),
    }
    for index, (key, value) in enumerate(config):
        environment[f"GIT_CONFIG_KEY_{index}"] = key
        environment[f"GIT_CONFIG_VALUE_{index}"] = value
    return environment


def _git_context() -> tuple[str, dict[str, str]]:
    git = _resolve_git()
    return git, _git_environment(git)


def _validate_id(value: object, code: str = "bead-id-invalid") -> str:
    if not isinstance(value, str) or not BEAD_ID.fullmatch(value):
        raise WorkerError(code)
    return value


def _validate_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or not COMMIT_SHA.fullmatch(value):
        raise WorkerError(code)
    return value


def _metadata(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise WorkerError("bead-metadata-invalid")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise WorkerError("bead-metadata-invalid")
        result[key] = item
    return result


def _unwrap_bead(raw: object) -> Mapping[str, object]:
    if isinstance(raw, list):
        if len(raw) != 1 or not isinstance(raw[0], Mapping):
            raise WorkerError("bead-response-invalid")
        return raw[0]
    if isinstance(raw, Mapping):
        value = raw.get("issue", raw)
        if not isinstance(value, Mapping):
            raise WorkerError("bead-response-invalid")
        return value
    raise WorkerError("bead-response-invalid")


def _show_bead(bead_id: str, *, cwd: pathlib.Path | None) -> dict[str, object]:
    result = _run(
        ["gc", "bd", "show", bead_id, "--json", "--long"],
        cwd=cwd,
    )
    if result.returncode != 0:
        raise WorkerError("bead-read-failed")
    try:
        bead = dict(_unwrap_bead(json.loads(result.stdout)))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkerError("bead-response-invalid") from error
    if bead.get("id") != bead_id:
        raise WorkerError("bead-id-mismatch")
    bead["metadata"] = _metadata(bead.get("metadata"))
    return bead


def _claim() -> dict[str, object]:
    # The role protocol calls this transaction `gc gc claim`; the pinned CLI
    # exposes it as the normalized hook claim command.
    result = _run(["gc", "hook", "--claim", "--drain-ack", "--json"])
    if result.returncode != 0:
        raise WorkerError("claim-failed")
    try:
        raw = json.loads(result.stdout.strip())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkerError("claim-response-invalid") from error
    if not isinstance(raw, Mapping):
        raise WorkerError("claim-response-invalid")
    allowed = {
        "schema_version",
        "ok",
        "command",
        "action",
        "reason",
        "bead_id",
        "assignee",
        "route",
        "root_bead_id",
        "continuation_group",
        "continuation_assigned",
        "drain_acknowledged",
    }
    if set(raw) - allowed:
        raise WorkerError("claim-response-invalid")
    if (
        raw.get("schema_version") != "1"
        or raw.get("ok") is not True
        or raw.get("command") != "hook"
        or raw.get("action") not in {"work", "drain"}
    ):
        raise WorkerError("claim-response-invalid")
    reasons = (
        {"claimed", "existing_assignment", "ready_assignment"}
        if raw.get("action") == "work"
        else {"no_work", "claims_errored", "stale_session"}
    )
    if raw.get("reason") not in reasons:
        raise WorkerError("claim-response-invalid")
    if raw.get("action") == "drain" and raw.get("reason") == "claims_errored":
        raise WorkerError("claims-errored")
    if raw.get("action") == "work":
        _validate_id(raw.get("bead_id"))
        if not isinstance(raw.get("assignee"), str) or not raw["assignee"]:
            raise WorkerError("claim-response-invalid")
        if "root_bead_id" in raw and raw["root_bead_id"] is not None:
            _validate_id(raw["root_bead_id"], "root-bead-id-invalid")
    return dict(raw)


def _description(bead: Mapping[str, object]) -> str:
    for key in ("description", "body", "title"):
        value = bead.get(key)
        if isinstance(value, str):
            return value
    return ""


def _rendered_publication_values(
    description: str,
) -> tuple[bool, bool]:
    lines = description.splitlines()
    if lines.count(PUBLICATION_MARKER) != 1:
        raise WorkerError("publication-marker-mismatch")
    values: dict[str, str] = {}
    for line in lines:
        for key in (PUBLISH_KEY, OPEN_PR_KEY):
            prefix = f"{key}="
            if line.startswith(prefix):
                if key in values:
                    raise WorkerError("publication-input-invalid")
                values[key] = line[len(prefix) :]
    if set(values) != {PUBLISH_KEY, OPEN_PR_KEY}:
        raise WorkerError("publication-input-missing")
    if any(value not in {"true", "false"} for value in values.values()):
        raise WorkerError("publication-input-invalid")
    return values[PUBLISH_KEY] == "true", values[OPEN_PR_KEY] == "true"


def _safe_worktree(value: object) -> pathlib.Path:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or "\x00" in value
        or any(character in value for character in "\r\n")
        or "//" in value[1:]
        or ".." in pathlib.PurePosixPath(value).parts
    ):
        raise WorkerError("source-worktree-invalid")
    path = pathlib.Path(value)
    try:
        info = path.lstat()
    except OSError as error:
        raise WorkerError("source-worktree-invalid") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise WorkerError("source-worktree-invalid")
    if not (path / ".git").exists():
        raise WorkerError("source-worktree-invalid")
    return path


def _command_cwd(root: Mapping[str, str]) -> pathlib.Path:
    value = root.get(WORKTREE_KEY)
    if isinstance(value, str) and value.startswith("/"):
        candidate = pathlib.Path(value)
        try:
            if candidate.is_dir() and not candidate.is_symlink():
                return candidate
        except OSError:
            pass
    return pathlib.Path.cwd()


def _resolve_source(
    *,
    claim: Mapping[str, object],
    step: Mapping[str, object],
    cwd: pathlib.Path,
) -> tuple[str, dict[str, object], dict[str, object], pathlib.Path]:
    step_metadata = _metadata(step["metadata"])
    claim_root = claim.get("root_bead_id")
    metadata_root = step_metadata.get(ROOT_KEY)
    if claim_root is not None and metadata_root is not None and claim_root != metadata_root:
        raise WorkerError("workflow-root-mismatch")
    root_id = _validate_id(claim_root or metadata_root, "workflow-root-missing")
    root = _show_bead(root_id, cwd=cwd)
    root_metadata = _metadata(root["metadata"])
    input_convoy_id = _validate_id(
        root_metadata.get(INPUT_CONVOY_KEY),
        "input-convoy-missing",
    )
    convoy = _show_bead(input_convoy_id, cwd=cwd)
    convoy_metadata = _metadata(convoy["metadata"])
    if convoy_metadata.get(SYNTHETIC_KIND_KEY) == "drain-unit-convoy":
        source_id = _validate_id(
            convoy_metadata.get(DRAIN_MEMBER_KEY),
            "drain-member-missing",
        )
        if source_id == input_convoy_id:
            raise WorkerError("synthetic-source-invalid")
    else:
        source_id = input_convoy_id
    root_drain_member = root_metadata.get(DRAIN_MEMBER_KEY)
    if root_drain_member is not None and root_drain_member != source_id:
        raise WorkerError("drain-member-mismatch")
    source = _show_bead(source_id, cwd=cwd)
    return root_id, root, source, _safe_worktree(
        _metadata(source["metadata"]).get(WORKTREE_KEY)
    )


def _check_clean_head(
    worktree: pathlib.Path,
    *,
    git: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> str:
    if git is None or environment is None:
        git, environment = _git_context()
    root = _run(
        [git, "-C", str(worktree), "rev-parse", "--show-toplevel"],
        cwd=worktree,
        env=environment,
    )
    if root.returncode != 0:
        raise WorkerError("source-worktree-invalid")
    try:
        if pathlib.Path(root.stdout.strip()).resolve() != worktree.resolve():
            raise WorkerError("source-worktree-invalid")
    except (OSError, RuntimeError) as error:
        raise WorkerError("source-worktree-invalid") from error
    status = _run(
        [git, "-C", str(worktree), "status", "--porcelain"],
        cwd=worktree,
        env=environment,
    )
    if status.returncode != 0:
        raise WorkerError("source-worktree-status-unavailable")
    if status.stdout.strip():
        raise WorkerError("source-worktree-dirty")
    head = _run(
        [git, "-C", str(worktree), "rev-parse", "HEAD"],
        cwd=worktree,
        env=environment,
    )
    if head.returncode != 0:
        raise WorkerError("source-head-unavailable")
    return _validate_sha(head.stdout.strip(), "source-head-invalid")


def _update(
    bead_id: str,
    metadata: Mapping[str, str],
    *,
    cwd: pathlib.Path,
) -> None:
    argv = ["gc", "bd", "update", bead_id]
    for key, value in metadata.items():
        if any(character in value for character in "\x00\r\n"):
            raise WorkerError("metadata-value-invalid")
        argv.extend(["--set-metadata", f"{key}={value}"])
    result = _run(argv, cwd=cwd)
    if result.returncode != 0:
        raise WorkerError("bead-update-failed")


def _close(bead_id: str, *, cwd: pathlib.Path, reason: str) -> None:
    result = _run(
        ["gc", "bd", "close", bead_id, "--reason", reason],
        cwd=cwd,
    )
    if result.returncode != 0:
        raise WorkerError("bead-close-failed")


def _run_checked(
    argv: list[str],
    *,
    cwd: pathlib.Path | None = None,
) -> None:
    result = _run(argv, cwd=cwd)
    if result.returncode != 0:
        raise WorkerError("command-failed")


def _timestamp() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _artifact_path(bead_id: str) -> pathlib.Path | None:
    value = os.environ.get("GC_ARTIFACT_DIR")
    if not value:
        return None
    if (
        not value.startswith("/")
        or value == "/"
        or "\x00" in value
        or any(character in value for character in "\r\n")
        or "//" in value[1:]
        or ".." in pathlib.PurePosixPath(value).parts
    ):
        raise WorkerError("artifact-directory-invalid")
    directory = pathlib.Path(value)
    try:
        info = directory.lstat()
    except OSError as error:
        raise WorkerError("artifact-directory-invalid") from error
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_mode & 0o022
    ):
        raise WorkerError("artifact-directory-invalid")
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", bead_id)
    return directory / f"publication-{safe_id}.json"


def _write_artifact(bead_id: str, payload: Mapping[str, object]) -> str:
    path = _artifact_path(bead_id)
    if path is None:
        return ""
    if path.is_symlink():
        raise WorkerError("artifact-path-invalid")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
    except OSError as error:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise WorkerError("artifact-write-failed") from error
    return str(path)


def _remote_status(
    root: Mapping[str, str],
    *,
    cwd: pathlib.Path,
    git: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> str:
    if git is None or environment is None:
        git, environment = _git_context()
    candidate = _command_cwd(root)
    result = _run(
        [
            git,
            "-C",
            str(candidate),
            "remote",
            "get-url",
            "--all",
            "origin",
        ],
        cwd=cwd,
        env=environment,
    )
    if result.returncode == 0 and any(line.strip() for line in result.stdout.splitlines()):
        return "present"
    if result.returncode == 1:
        return "absent"
    return "unknown"


def _base_failure_metadata(
    *,
    push: bool,
    open_pr: bool,
    status: str,
    action: str,
    reason: str,
    artifact_path: str,
    outcome: str,
    failure_class: str | None = None,
    remote_status: str = "unknown",
) -> dict[str, str]:
    values = {
        "gc.outcome": outcome,
        "gc.build.publish_status": status,
        "gc.build.publish_action": action,
        "gc.build.publish_recorded_at": _timestamp(),
        "gc.build.publish_artifact_path": artifact_path,
        "gc.build.publish_reason": reason,
        "gc.build.publish_remote_status": remote_status,
        "gc.build.publish_push": "true" if push else "false",
        "gc.build.publish_open_pr": "true" if open_pr else "false",
    }
    if failure_class is not None:
        values["gc.failure_class"] = failure_class
    return values


def _close_with_metadata(
    *,
    step_id: str,
    root_id: str | None,
    metadata: Mapping[str, str],
    cwd: pathlib.Path,
    reason: str,
) -> None:
    if root_id is not None:
        _update_and_verify(root_id, metadata, cwd=cwd)
    _update_and_verify(step_id, metadata, cwd=cwd)
    try:
        _close(step_id, cwd=cwd, reason=reason)
    except WorkerError as error:
        raise MetadataCommitError(error.code) from error


def _update_and_verify(
    bead_id: str,
    metadata: Mapping[str, str],
    *,
    cwd: pathlib.Path,
) -> None:
    try:
        _update(bead_id, metadata, cwd=cwd)
        readback = _metadata(_show_bead(bead_id, cwd=cwd)["metadata"])
        for key, value in metadata.items():
            if readback.get(key) != value:
                raise WorkerError("bead-readback-mismatch")
    except WorkerError as error:
        raise MetadataCommitError(error.code) from error


def _record_contract_failure(
    *,
    step_id: str,
    root_id: str | None,
    push: bool,
    open_pr: bool,
    code: str,
    cwd: pathlib.Path,
    update_root: bool,
) -> None:
    metadata = _base_failure_metadata(
        push=push,
        open_pr=open_pr,
        status="failed",
        action="failed",
        reason=code,
        artifact_path="",
        outcome="fail",
        failure_class="publication_contract",
    )
    try:
        _close_with_metadata(
            step_id=step_id,
            root_id=root_id if update_root else None,
            metadata=metadata,
            cwd=cwd,
            reason="Publication worker rejected the claimed contract.",
        )
    except WorkerError:
        raise


def _safe_helper_record(
    raw: object,
    *,
    source_id: str,
    expected_head: str,
) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise WorkerError("helper-response-invalid")
    required = {
        "status",
        "repository",
        "base",
        "branch",
        "work_id",
        "head_sha",
        "url",
    }
    if not required.issubset(raw):
        raise WorkerError("helper-response-invalid")
    if (
        raw.get("status") != "open"
        or raw.get("repository") != "vicondoa/d2b"
        or raw.get("base") != "v3"
        or raw.get("work_id") != source_id
        or raw.get("branch") != f"gascity/{source_id}"
        or raw.get("head_sha") != expected_head
        or not isinstance(raw.get("url"), str)
        or not PULL_URL.fullmatch(raw["url"])
    ):
        raise WorkerError("helper-response-invalid")
    safe: dict[str, object] = {}
    for key in (
        "version",
        "status",
        "repository",
        "base",
        "branch",
        "work_id",
        "head_sha",
        "number",
        "url",
    ):
        if key in raw and isinstance(raw[key], (str, int)):
            safe[key] = raw[key]
    return safe


def _parsed_helper_error(stderr: str) -> str | None:
    match = HELPER_ERROR.fullmatch(stderr.strip())
    return match.group(1) if match is not None else None


def _helper_failure(stderr: str) -> WorkerError:
    code = _parsed_helper_error(stderr)
    if code in RETRYABLE_HELPER_CODES:
        return WorkerError("helper-retryable")
    return WorkerError("helper-failed")


def _process_claim(claim: Mapping[str, object]) -> str:
    step_id = _validate_id(claim.get("bead_id"))
    cwd = pathlib.Path.cwd()
    try:
        step = _show_bead(step_id, cwd=cwd)
    except WorkerError as error:
        _record_contract_failure(
            step_id=step_id,
            root_id=None,
            push=False,
            open_pr=False,
            code=error.code,
            cwd=cwd,
            update_root=False,
        )
        return str(claim.get("continuation_group") or "")

    try:
        push, open_pr = _rendered_publication_values(_description(step))
    except WorkerError as error:
        _record_contract_failure(
            step_id=step_id,
            root_id=None,
            push=False,
            open_pr=False,
            code=error.code,
            cwd=cwd,
            update_root=False,
        )
        return str(claim.get("continuation_group") or "")

    step_metadata = _metadata(step["metadata"])
    root_hint = claim.get("root_bead_id") or step_metadata.get(ROOT_KEY)
    try:
        root_id = _validate_id(root_hint, "workflow-root-missing")
    except WorkerError as error:
        _record_contract_failure(
            step_id=step_id,
            root_id=None,
            push=push,
            open_pr=open_pr,
            code=error.code,
            cwd=cwd,
            update_root=False,
        )
        return str(claim.get("continuation_group") or "")
    try:
        root = _show_bead(root_id, cwd=cwd)
        root_metadata = _metadata(root["metadata"])
        command_cwd = _command_cwd(root_metadata)
    except WorkerError as error:
        _record_contract_failure(
            step_id=step_id,
            root_id=None,
            push=push,
            open_pr=open_pr,
            code=error.code,
            cwd=cwd,
            update_root=False,
        )
        return str(claim.get("continuation_group") or "")

    if not push and not open_pr:
        git, git_environment = _git_context()
        remote_status = _remote_status(
            root_metadata,
            cwd=command_cwd,
            git=git,
            environment=git_environment,
        )
        payload = {
            "schema": "gc.build.publish.v1",
            "status": "noop",
            "action": "noop",
            "reason": "push=false_open_pr=false",
            "push": False,
            "open_pr": False,
            "remote_status": remote_status,
        }
        artifact_path = _write_artifact(step_id, payload)
        metadata = _base_failure_metadata(
            push=push,
            open_pr=open_pr,
            status="noop",
            action="noop",
            reason="push=false_open_pr=false",
            artifact_path=artifact_path,
            outcome="pass",
            remote_status=remote_status,
        )
        _close_with_metadata(
            step_id=step_id,
            root_id=root_id,
            metadata=metadata,
            cwd=command_cwd,
            reason="Publishing disabled; recorded the required no-op result.",
        )
        return str(claim.get("continuation_group") or "")

    if not open_pr:
        code = "push-only-unsupported"
        _record_contract_failure(
            step_id=step_id,
            root_id=root_id,
            push=push,
            open_pr=open_pr,
            code=code,
            cwd=command_cwd,
            update_root=True,
        )
        return str(claim.get("continuation_group") or "")
    if not push:
        code = "pr-without-push-authorization"
        _record_contract_failure(
            step_id=step_id,
            root_id=root_id,
            push=push,
            open_pr=open_pr,
            code=code,
            cwd=command_cwd,
            update_root=True,
        )
        return str(claim.get("continuation_group") or "")

    try:
        _, root, source, worktree = _resolve_source(
            claim=claim,
            step=step,
            cwd=command_cwd,
        )
        source_metadata = _metadata(source["metadata"])
        if source_metadata.get(BASE_REF_KEY) != "origin/v3":
            raise WorkerError("source-base-ref-missing")
        _validate_sha(source_metadata.get(BASE_SHA_KEY), "source-base-sha-invalid")
        git, git_environment = _git_context()
        head_sha = _check_clean_head(
            worktree,
            git=git,
            environment=git_environment,
        )
        source_id = _validate_id(source["id"])
        expected_head_value = source_metadata.get(EXPECTED_HEAD_KEY)
        if expected_head_value is None:
            _update(
                source_id,
                {EXPECTED_HEAD_KEY: head_sha},
                cwd=command_cwd,
            )
            readback = _metadata(_show_bead(source_id, cwd=command_cwd)["metadata"])
            if readback.get(EXPECTED_HEAD_KEY) != head_sha:
                raise WorkerError("source-head-readback-mismatch")
        else:
            expected_head = _validate_sha(
                expected_head_value,
                "source-expected-head-invalid",
            )
            if expected_head != head_sha:
                raise WorkerError("source-head-mismatch")
        try:
            helper = _run(
                ["d2b-gascity-publish-pr", source_id],
                cwd=worktree,
                timeout=HELPER_TIMEOUT,
                timeout_code="helper-timeout",
            )
        except WorkerError as error:
            if error.code == "command-unavailable":
                raise WorkerError("helper-retryable") from error
            raise
        if helper.returncode != 0:
            raise _helper_failure(helper.stderr)
        try:
            helper_raw = json.loads(helper.stdout.strip())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkerError("helper-response-invalid") from error
        record = _safe_helper_record(
            helper_raw,
            source_id=source_id,
            expected_head=head_sha,
        )
        url = record["url"]
        sha = record["head_sha"]
        branch = record["branch"]
        payload = {
            "schema": "gc.build.publish.v1",
            "status": "published",
            "action": "push_pr",
            "source_anchor_id": source_id,
            "url": url,
            "sha": sha,
            "branch": branch,
            "record": record,
        }
        artifact_path = _write_artifact(step_id, payload)
        metadata = _base_failure_metadata(
            push=push,
            open_pr=open_pr,
            status="published",
            action="push_pr",
            reason="published",
            artifact_path=artifact_path,
            outcome="pass",
            remote_status="verified",
        )
        metadata.update(
            {
                "gc.build.publish_url": str(url),
                "gc.build.publish_sha": str(sha),
                "gc.build.publish_branch": str(branch),
                "gc.publication.url": str(url),
                "gc.publication.sha": str(sha),
                "gc.publication.branch": str(branch),
            }
        )
        _close_with_metadata(
            step_id=step_id,
            root_id=root["id"],
            metadata=metadata,
            cwd=command_cwd,
            reason="Published the verified d2b v3 pull request.",
        )
    except MetadataCommitError:
        raise
    except WorkerError as error:
        if error.code in {"helper-retryable", "helper-timeout"}:
            raise
        metadata = _base_failure_metadata(
            push=push,
            open_pr=open_pr,
            status="failed",
            action="failed",
            reason=error.code,
            artifact_path="",
            outcome="fail",
            failure_class=(
                "publication_helper"
                if error.code.startswith("helper-")
                else "publication_worker"
            ),
        )
        _close_with_metadata(
            step_id=step_id,
            root_id=root_id,
            metadata=metadata,
            cwd=command_cwd,
            reason="Publication failed with a typed machine-readable result.",
        )
    return str(claim.get("continuation_group") or "")


def main(argv: list[str] | None = None) -> int:
    try:
        if argv:
            raise WorkerError("arguments-not-allowed")
        while True:
            claim = _claim()
            if claim["action"] == "drain":
                return 0
            continuation = _process_claim(claim)
            if not continuation:
                _run_checked(
                    ["gc", "runtime", "drain-ack"],
                    cwd=pathlib.Path.cwd(),
                )
                return 0
    except WorkerError as error:
        print(f"publication-worker: {error.code}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
