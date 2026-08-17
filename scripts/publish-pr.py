#!/usr/bin/env python3
"""Publish one immutable Beads work item as a bounded d2b v3 pull request."""

from __future__ import annotations

import argparse
import base64
import contextlib
import dataclasses
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping


REPOSITORY = "vicondoa/d2b"
BASE_BRANCH = "v3"
BASE_REF = "origin/v3"
BRANCH_PREFIX = "gascity/"
CREDENTIALS_DIRECTORY_ENV = "CREDENTIALS_DIRECTORY"
GITHUB_PUBLICATION_TOKEN_CREDENTIAL = "github-publication-token"
GITHUB_PUBLICATION_POLICY_CREDENTIAL = "github-publication-policy"
GITHUB_PUBLICATION_APP_KEY_CREDENTIAL = "github-publication-app-key"
GITHUB_PUBLICATION_APP_CONFIG_CREDENTIAL = "github-publication-app-config"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_TIMEOUT = 30
INSTALLATION_TOKEN_MAX_LIFETIME = 3600
REQUESTED_PERMISSIONS = {
    "metadata": "read",
    "contents": "write",
    "pull_requests": "write",
}

EXPECTED_HEAD_KEY = "gc.publication.expected_head_sha"
BASE_SHA_KEY = "gc.publication.base_sha"
BASE_REF_KEY = "gc.publication.base_ref"
WORKTREE_KEY = "work_dir"
PUBLICATION_URL_KEY = "gc.publication.url"
PUBLICATION_SHA_KEY = "gc.publication.sha"
PUBLICATION_BRANCH_KEY = "gc.publication.branch"

WORK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
PULL_URL = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*$"
)

EXPECTED_SERVER_POLICY = {
    "version": 1,
    "identity": "d2b-gascity-publication",
    "repository": REPOSITORY,
    "base": BASE_BRANCH,
    "publication_branch_pattern": "gascity/*",
    "publication_branch_create_only": True,
    "can_create_pull_request": True,
    "allow_direct_base_update": False,
    "allow_branch_update": False,
    "allow_force_push": False,
    "allow_force_with_lease": False,
    "allow_merge": False,
    "allow_auto_merge": False,
    "allow_merge_queue": False,
    "allow_ruleset_bypass": False,
}


class PublishError(RuntimeError):
    """Operator-safe publication failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclasses.dataclass(frozen=True)
class Anchor:
    issue_id: str
    worktree: pathlib.Path
    expected_head_sha: str
    base_sha: str
    base_ref: str
    source_metadata: Mapping[str, str]


@dataclasses.dataclass(frozen=True)
class PullRequest:
    number: int
    state: str
    branch: str
    base: str
    head_sha: str
    repository: str
    url: str


def _command_path(value: str, label: str) -> str:
    if os.path.sep in value:
        path = pathlib.Path(value)
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            raise PublishError(f"{label}-unavailable")
        return str(path)
    resolved = shutil.which(value)
    if resolved is None:
        raise PublishError(f"{label}-unavailable")
    return resolved


def _minimal_path(*commands: str) -> str:
    directories = [str(pathlib.Path(sys.executable).parent)]
    directories.extend(
        str(pathlib.Path(command).parent)
        for command in commands
        if os.path.sep in command
    )
    directories.extend(os.defpath.split(os.pathsep))
    return os.pathsep.join(dict.fromkeys(directories))


def _scrubbed_environment(*commands: str) -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "NO_COLOR": "1",
        "PATH": _minimal_path(*commands),
    }


def _git_remote_environment(token: str, git: str) -> dict[str, str]:
    environment = _scrubbed_environment(git)
    authorization = base64.b64encode(
        f"x-access-token:{token}".encode("ascii")
    ).decode("ascii")
    config = (
        ("core.hooksPath", "/dev/null"),
        ("push.followTags", "false"),
        ("credential.helper", ""),
        ("core.sshCommand", "/bin/false"),
        ("http.proxy", ""),
        ("http.sslVerify", "true"),
        ("http.sslCAInfo", ""),
        ("http.sslCert", ""),
        ("http.sslKey", ""),
        (
            "http.https://github.com/.extraHeader",
            f"Authorization: Basic {authorization}",
        ),
    )
    environment.update(
        {
            "GIT_CONFIG_COUNT": str(len(config)),
            "GIT_ASKPASS": "/bin/false",
        }
    )
    for index, (key, value) in enumerate(config):
        environment[f"GIT_CONFIG_KEY_{index}"] = key
        environment[f"GIT_CONFIG_VALUE_{index}"] = value
    return environment


def _gh_environment(token: str, gh: str) -> dict[str, str]:
    environment = _scrubbed_environment(gh)
    environment.update(
        {
            "GH_PROMPT_DISABLED": "1",
            "GH_TOKEN": token,
        }
    )
    return environment


def _run_command(
    command: list[str],
    *,
    cwd: pathlib.Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            close_fds=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PublishError("command-unavailable") from error


def _validate_work_id(value: str) -> str:
    if (
        not WORK_ID.fullmatch(value)
        or ".." in value
        or value.endswith(".")
        or "@{" in value
    ):
        raise PublishError("work-id-invalid")
    return value


def derive_branch(work_id: str) -> str:
    return BRANCH_PREFIX + _validate_work_id(work_id)


def _validate_sha(value: object, code: str) -> str:
    if not isinstance(value, str) or not COMMIT_SHA.fullmatch(value):
        raise PublishError(code)
    return value


def _validate_worktree(value: object) -> pathlib.Path:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or "\x00" in value
        or any(character in value for character in "\r\n")
        or "//" in value[1:]
        or ".." in pathlib.PurePosixPath(value).parts
    ):
        raise PublishError("worktree-invalid")
    path = pathlib.Path(value)
    try:
        info = path.lstat()
    except OSError as error:
        raise PublishError("worktree-invalid") from error
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PublishError("worktree-invalid")
    if not (path / ".git").exists():
        raise PublishError("worktree-invalid")
    return path


def _load_beads_issue(
    bd: str,
    issue_id: str,
    *,
    cwd: pathlib.Path | None,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    result = _run_command(
        [bd, "show", issue_id, "--json", "--long"],
        cwd=cwd,
    )
    if result.returncode != 0:
        raise PublishError("beads-show-unavailable")
    try:
        raw = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublishError("beads-response-invalid") from error

    if isinstance(raw, list):
        if not raw:
            raise PublishError("beads-anchor-missing")
        if len(raw) != 1 or not isinstance(raw[0], Mapping):
            raise PublishError("beads-response-invalid")
        issue = raw[0]
    elif isinstance(raw, Mapping):
        issue_value = raw.get("issue", raw)
        if not isinstance(issue_value, Mapping):
            raise PublishError("beads-response-invalid")
        issue = issue_value
    else:
        raise PublishError("beads-response-invalid")

    if issue.get("id") != issue_id:
        raise PublishError("beads-anchor-mismatch")
    metadata = issue.get("metadata")
    if not isinstance(metadata, Mapping):
        raise PublishError("beads-anchor-metadata-missing")
    return issue, metadata


def _read_anchor(
    bd: str,
    issue_id: str,
    *,
    cwd: pathlib.Path | None,
) -> Anchor:
    _, metadata = _load_beads_issue(bd, issue_id, cwd=cwd)
    required = (WORKTREE_KEY, EXPECTED_HEAD_KEY, BASE_SHA_KEY, BASE_REF_KEY)
    if any(key not in metadata for key in required):
        raise PublishError("beads-anchor-metadata-missing")
    worktree_value = metadata[WORKTREE_KEY]
    expected_head_sha = _validate_sha(metadata[EXPECTED_HEAD_KEY], "head-sha-invalid")
    base_sha = _validate_sha(metadata[BASE_SHA_KEY], "base-sha-invalid")
    base_ref = metadata[BASE_REF_KEY]
    if base_ref != BASE_REF:
        raise PublishError("base-ref-mismatch")
    if not isinstance(worktree_value, str):
        raise PublishError("worktree-invalid")
    source_metadata = {
        WORKTREE_KEY: worktree_value,
        EXPECTED_HEAD_KEY: expected_head_sha,
        BASE_SHA_KEY: base_sha,
        BASE_REF_KEY: base_ref,
    }
    return Anchor(
        issue_id=issue_id,
        worktree=_validate_worktree(worktree_value),
        expected_head_sha=expected_head_sha,
        base_sha=base_sha,
        base_ref=base_ref,
        source_metadata=source_metadata,
    )


def _validated_remote_url(value: str) -> str:
    if not value or any(character in value for character in "\r\n"):
        raise PublishError("remote-repository-mismatch")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        raise PublishError("remote-repository-mismatch")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or port is not None
        or "@" in parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise PublishError("remote-repository-mismatch")
    if parsed.path not in {f"/{REPOSITORY}", f"/{REPOSITORY}.git"}:
        raise PublishError("remote-repository-mismatch")
    return value


def _remote_url(
    git: str,
    worktree: pathlib.Path,
    *,
    push: bool,
    environment: Mapping[str, str],
) -> str:
    command = [git, "-C", str(worktree), "remote", "get-url"]
    if push:
        command.append("--push")
    command.extend(["--all", "origin"])
    result = _run_command(
        command,
        cwd=worktree,
        env=environment,
    )
    if result.returncode != 0:
        raise PublishError("remote-invalid")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise PublishError("remote-repository-mismatch")
    return _validated_remote_url(lines[0])


def _check_local_repository(
    git: str,
    worktree: pathlib.Path,
    expected_sha: str,
    *,
    environment: Mapping[str, str],
) -> str:
    root = _run_command(
        [git, "-C", str(worktree), "rev-parse", "--show-toplevel"],
        cwd=worktree,
        env=environment,
    )
    if root.returncode != 0:
        raise PublishError("worktree-invalid")
    try:
        root_path = pathlib.Path(root.stdout.strip()).resolve()
    except (OSError, RuntimeError) as error:
        raise PublishError("worktree-invalid") from error
    if root_path != worktree.resolve():
        raise PublishError("worktree-invalid")

    head = _run_command(
        [git, "-C", str(worktree), "rev-parse", "HEAD"],
        cwd=worktree,
        env=environment,
    )
    if head.returncode != 0 or head.stdout.strip() != expected_sha:
        raise PublishError("head-sha-mismatch")

    status = _run_command(
        [git, "-C", str(worktree), "status", "--porcelain"],
        cwd=worktree,
        env=environment,
    )
    if status.returncode != 0:
        raise PublishError("worktree-status-unavailable")
    if status.stdout.strip():
        raise PublishError("worktree-dirty")

    _reject_ancestry_overrides(
        git,
        worktree,
        environment=environment,
    )

    fetch_url = _remote_url(
        git,
        worktree,
        push=False,
        environment=environment,
    )
    push_url = _remote_url(
        git,
        worktree,
        push=True,
        environment=environment,
    )
    if fetch_url != push_url:
        raise PublishError("remote-repository-mismatch")
    return fetch_url


def _reject_ancestry_overrides(
    git: str,
    worktree: pathlib.Path,
    *,
    environment: Mapping[str, str],
) -> None:
    replacements = _run_command(
        [git, "-C", str(worktree), "replace", "-l"],
        cwd=worktree,
        env=environment,
    )
    if replacements.returncode != 0:
        raise PublishError("replacement-refs-unavailable")
    if any(line.strip() for line in replacements.stdout.splitlines()):
        raise PublishError("replacement-objects-present")

    graft_path_result = _run_command(
        [git, "-C", str(worktree), "rev-parse", "--git-path", "info/grafts"],
        cwd=worktree,
        env=environment,
    )
    if graft_path_result.returncode != 0:
        raise PublishError("grafts-unavailable")
    raw_path = graft_path_result.stdout.strip()
    if not raw_path:
        raise PublishError("grafts-unavailable")
    graft_path = pathlib.Path(raw_path)
    if not graft_path.is_absolute():
        graft_path = worktree / graft_path
    try:
        if graft_path.is_symlink():
            raise PublishError("grafts-present")
        if graft_path.exists() and graft_path.read_text(encoding="utf-8").strip():
            raise PublishError("grafts-present")
    except PublishError:
        raise
    except (OSError, UnicodeError) as error:
        raise PublishError("grafts-unavailable") from error


@contextlib.contextmanager
def _trusted_bare_repository(
    git: str,
    worktree: pathlib.Path,
    expected_sha: str,
    *,
    environment: Mapping[str, str],
):
    try:
        directory = pathlib.Path(
            tempfile.mkdtemp(prefix=".d2b-publication-", dir=worktree.parent)
        )
        directory.chmod(0o700)
    except OSError as error:
        raise PublishError("trusted-repository-unavailable") from error
    try:
        initialized = _run_command(
            [git, "init", "--bare", "--quiet", str(directory)],
            cwd=worktree,
            env=environment,
        )
        if initialized.returncode != 0:
            raise PublishError("trusted-repository-unavailable")
        try:
            directory.chmod(0o700)
        except OSError as error:
            raise PublishError("trusted-repository-unavailable") from error
        imported = _run_command(
            [
                git,
                "--git-dir",
                str(directory),
                "fetch",
                "--no-tags",
                "--no-write-fetch-head",
                str(worktree),
                f"{expected_sha}:refs/d2b/head",
            ],
            cwd=worktree,
            env=environment,
        )
        if imported.returncode != 0:
            raise PublishError("head-import-failed")
        imported_head = _run_command(
            [
                git,
                "--git-dir",
                str(directory),
                "rev-parse",
                "--verify",
                "refs/d2b/head^{commit}",
            ],
            cwd=worktree,
            env=environment,
        )
        if (
            imported_head.returncode != 0
            or imported_head.stdout.strip() != expected_sha
        ):
            raise PublishError("head-import-mismatch")
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _refresh_and_verify_base(
    git: str,
    git_dir: pathlib.Path,
    *,
    base_sha: str,
    head_sha: str,
    remote_url: str,
    remote_environment: Mapping[str, str],
    local_environment: Mapping[str, str],
    cwd: pathlib.Path,
) -> None:
    fetched = _run_command(
        [
            git,
            "--git-dir",
            str(git_dir),
            "fetch",
            "--prune",
            "--no-tags",
            remote_url,
            f"refs/heads/{BASE_BRANCH}:refs/d2b/base",
        ],
        cwd=cwd,
        env=remote_environment,
    )
    if fetched.returncode != 0:
        raise PublishError("base-refresh-failed")

    reference = f"refs/heads/{BASE_BRANCH}"
    remote = _run_command(
        [git, "--git-dir", str(git_dir), "ls-remote", remote_url, reference],
        cwd=cwd,
        env=remote_environment,
    )
    if remote.returncode != 0:
        raise PublishError("base-remote-unavailable")
    lines = [line.split() for line in remote.stdout.splitlines() if line.strip()]
    if (
        len(lines) != 1
        or len(lines[0]) != 2
        or not COMMIT_SHA.fullmatch(lines[0][0])
        or lines[0][1] != reference
    ):
        raise PublishError("base-remote-invalid")
    current_base_sha = lines[0][0]

    tracking = _run_command(
        [
            git,
            "--git-dir",
            str(git_dir),
            "rev-parse",
            "--verify",
            "refs/d2b/base^{commit}",
        ],
        cwd=cwd,
        env=local_environment,
    )
    if tracking.returncode != 0 or tracking.stdout.strip() != current_base_sha:
        raise PublishError("base-tracking-mismatch")

    imported_head = _run_command(
        [
            git,
            "--git-dir",
            str(git_dir),
            "rev-parse",
            "--verify",
            "refs/d2b/head^{commit}",
        ],
        cwd=cwd,
        env=local_environment,
    )
    if imported_head.returncode != 0 or imported_head.stdout.strip() != head_sha:
        raise PublishError("head-import-mismatch")

    on_v3 = _run_command(
        [
            git,
            "--git-dir",
            str(git_dir),
            "merge-base",
            "--is-ancestor",
            base_sha,
            current_base_sha,
        ],
        cwd=cwd,
        env=local_environment,
    )
    if on_v3.returncode != 0:
        raise PublishError("base-not-on-v3")

    head_ancestor = _run_command(
        [
            git,
            "--git-dir",
            str(git_dir),
            "merge-base",
            "--is-ancestor",
            base_sha,
            "refs/d2b/head",
        ],
        cwd=cwd,
        env=local_environment,
    )
    if head_ancestor.returncode != 0:
        raise PublishError("base-not-ancestor")


def _validate_server_policy(raw: object) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise PublishError("server-protection-unsupported")
    if dict(raw) != EXPECTED_SERVER_POLICY:
        raise PublishError("server-protection-unsupported")
    return dict(raw)


def _credentials_directory() -> pathlib.Path:
    value = os.environ.get(CREDENTIALS_DIRECTORY_ENV)
    if (
        not value
        or not value.startswith("/")
        or value == "/"
        or "\x00" in value
        or any(character in value for character in "\r\n")
        or "//" in value[1:]
        or ".." in pathlib.PurePosixPath(value).parts
    ):
        raise PublishError("credentials-directory-unavailable")
    path = pathlib.Path(value)
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_mode & 0o022
        ):
            raise PublishError("credentials-directory-unavailable")
    except PublishError:
        raise
    except OSError as error:
        raise PublishError("credentials-directory-unavailable") from error
    return path


def _read_credential(
    name: str,
    *,
    max_size: int,
    private: bool,
    failure_code: str,
    unavailable_code: str | None = None,
) -> str:
    try:
        try:
            directory = _credentials_directory()
        except PublishError as error:
            if unavailable_code is None:
                raise
            raise PublishError(unavailable_code) from error
        path = directory / name
        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_size <= 0
                or info.st_size > max_size
                or (
                    private
                    and stat.S_IMODE(info.st_mode) not in {0o400, 0o440}
                )
                or (not private and info.st_mode & 0o222)
            ):
                raise PublishError(failure_code)
            value = stream.read(max_size + 1)
    except PublishError:
        raise
    except FileNotFoundError as error:
        raise PublishError(unavailable_code or failure_code) from error
    except (OSError, ValueError) as error:
        raise PublishError(failure_code) from error
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PublishError(failure_code) from error


def _load_server_policy() -> dict[str, object]:
    try:
        value = _read_credential(
            GITHUB_PUBLICATION_POLICY_CREDENTIAL,
            max_size=64 * 1024,
            private=False,
            failure_code="server-protection-unverified",
            unavailable_code="server-protection-unverified",
        )
        raw = json.loads(value)
    except PublishError:
        raise
    except json.JSONDecodeError as error:
        raise PublishError("server-protection-unverified") from error
    return _validate_server_policy(raw)


def _read_github_token() -> str:
    value = _read_credential(
        GITHUB_PUBLICATION_TOKEN_CREDENTIAL,
        max_size=8192,
        private=True,
        failure_code="github-credential-unverified",
        unavailable_code="github-credential-unavailable",
    ).rstrip("\r\n")
    if not value or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value):
        raise PublishError("github-credential-invalid")
    return value


def _read_github_app_key() -> str:
    value = _read_credential(
        GITHUB_PUBLICATION_APP_KEY_CREDENTIAL,
        max_size=32 * 1024,
        private=True,
        failure_code="github-app-key-unverified",
        unavailable_code="github-app-key-unavailable",
    )
    lines = value.strip("\r\n").splitlines()
    if len(lines) < 3:
        raise PublishError("github-app-key-invalid")
    begin = lines[0]
    if not begin.startswith("-----BEGIN ") or not begin.endswith(" PRIVATE KEY-----"):
        raise PublishError("github-app-key-invalid")
    label = begin[len("-----BEGIN ") : -len("-----")]
    if label not in {"PRIVATE KEY", "RSA PRIVATE KEY"}:
        raise PublishError("github-app-key-invalid")
    if lines[-1] != f"-----END {label}-----" or not any(lines[1:-1]):
        raise PublishError("github-app-key-invalid")
    return value


def _load_github_app_config() -> dict[str, object]:
    try:
        value = _read_credential(
            GITHUB_PUBLICATION_APP_CONFIG_CREDENTIAL,
            max_size=8 * 1024,
            private=False,
            failure_code="github-app-config-unverified",
            unavailable_code="github-app-config-unavailable",
        )
        raw = json.loads(value)
    except PublishError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublishError("github-app-config-invalid") from error

    if (
        not isinstance(raw, Mapping)
        or set(raw) != {"version", "app_id", "installation_id", "repository"}
        or raw.get("version") != 1
        or isinstance(raw.get("version"), bool)
        or raw.get("repository") != REPOSITORY
    ):
        raise PublishError("github-app-config-invalid")
    for key in ("app_id", "installation_id"):
        value = raw.get(key)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
            or value > 2**63 - 1
        ):
            raise PublishError("github-app-config-invalid")
    return {
        "version": 1,
        "app_id": raw["app_id"],
        "installation_id": raw["installation_id"],
        "repository": REPOSITORY,
    }


def _urlsafe_b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _create_github_app_jwt(
    app_id: int,
    key_path: pathlib.Path,
    *,
    openssl_command: str,
) -> str:
    now = int(time.time())
    header = _urlsafe_b64(
        json.dumps(
            {"alg": "RS256", "typ": "JWT"},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    payload = _urlsafe_b64(
        json.dumps(
            {"exp": now + 540, "iat": now - 60, "iss": app_id},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    try:
        openssl = _command_path(openssl_command, "openssl")
    except PublishError as error:
        raise PublishError("github-app-jwt-unavailable") from error
    try:
        result = subprocess.run(
            [openssl, "dgst", "-sha256", "-sign", str(key_path)],
            input=signing_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_scrubbed_environment(openssl),
            check=False,
            close_fds=True,
            timeout=GITHUB_API_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PublishError("github-app-jwt-unavailable") from error
    if result.returncode != 0 or not result.stdout:
        raise PublishError("github-app-jwt-failed")
    return f"{header}.{payload}.{_urlsafe_b64(result.stdout)}"


def _valid_installation_token_expiry(value: object, *, now: int) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
        expires_at = parsed.timestamp()
    except (OSError, TypeError, ValueError, OverflowError):
        return False
    if parsed.tzinfo is None:
        return False
    return now < expires_at <= now + INSTALLATION_TOKEN_MAX_LIFETIME


def _validate_installation_token_response(raw: object, *, now: int) -> str:
    if not isinstance(raw, Mapping):
        raise PublishError("github-app-response-invalid")
    token = raw.get("token")
    if (
        not isinstance(token, str)
        or not token
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in token)
        or not _valid_installation_token_expiry(raw.get("expires_at"), now=now)
    ):
        raise PublishError("github-app-response-invalid")

    permissions = raw.get("permissions")
    if (
        not isinstance(permissions, Mapping)
        or set(permissions) - set(REQUESTED_PERMISSIONS)
        or set(permissions) != set(REQUESTED_PERMISSIONS)
        or any(
            permissions.get(name) != level
            for name, level in REQUESTED_PERMISSIONS.items()
        )
    ):
        raise PublishError("github-app-response-invalid")

    repositories = raw.get("repositories")
    if not isinstance(repositories, list) or len(repositories) != 1:
        raise PublishError("github-app-response-invalid")
    repository = repositories[0]
    if isinstance(repository, Mapping):
        repository = repository.get("full_name")
    if repository != REPOSITORY:
        raise PublishError("github-app-response-invalid")
    if raw.get("repository_selection", "selected") != "selected":
        raise PublishError("github-app-response-invalid")
    return token


def _request_github_installation_token(
    jwt: str,
    installation_id: int,
) -> str:
    body = json.dumps(
        {
            "repositories": ["d2b"],
            "permissions": REQUESTED_PERMISSIONS,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        (
            f"{GITHUB_API_BASE}/app/installations/"
            f"{installation_id}/access_tokens"
        ),
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
            "User-Agent": "d2b-gascity-publication",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=GITHUB_API_TIMEOUT) as response:
            if response.getcode() != 201:
                raise PublishError("github-app-api-unavailable")
            payload = response.read(64 * 1024 + 1)
    except PublishError:
        raise
    except urllib.error.HTTPError as error:
        raise PublishError("github-app-api-unavailable") from error
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        raise PublishError("github-app-api-unavailable") from error
    if not isinstance(payload, bytes) or len(payload) > 64 * 1024:
        raise PublishError("github-app-response-invalid")
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublishError("github-app-response-invalid") from error
    return _validate_installation_token_response(raw, now=int(time.time()))


def _mint_github_installation_token(*, openssl_command: str) -> str:
    config = _load_github_app_config()
    _read_github_app_key()
    credentials_directory = _credentials_directory()
    key_path = credentials_directory / GITHUB_PUBLICATION_APP_KEY_CREDENTIAL
    jwt = _create_github_app_jwt(
        config["app_id"],
        key_path,
        openssl_command=openssl_command,
    )
    return _request_github_installation_token(jwt, config["installation_id"])


def _parse_pull_request(raw: Mapping[str, object]) -> PullRequest:
    try:
        number = raw["number"]
        state = raw["state"]
        branch = raw["headRefName"]
        base = raw["baseRefName"]
        head_sha = raw["headRefOid"]
        url = raw["url"]
        repository_value = raw["headRepository"]
    except (KeyError, TypeError):
        raise PublishError("github-response-invalid")
    if isinstance(repository_value, Mapping):
        repository = repository_value.get("nameWithOwner")
    else:
        repository = repository_value
    if (
        not isinstance(number, int)
        or isinstance(number, bool)
        or number <= 0
        or not isinstance(state, str)
        or not isinstance(branch, str)
        or not isinstance(base, str)
        or not isinstance(head_sha, str)
        or not isinstance(url, str)
        or not isinstance(repository, str)
        or not repository
        or not COMMIT_SHA.fullmatch(head_sha)
        or not PULL_URL.fullmatch(url)
    ):
        raise PublishError("github-response-invalid")
    merged = raw.get("mergedAt") is not None or state.upper() == "MERGED"
    normalized = "merged" if merged else state.lower()
    if normalized not in {"open", "closed", "merged"}:
        raise PublishError("github-response-invalid")
    return PullRequest(number, normalized, branch, base, head_sha, repository, url)


def _list_pull_requests(
    gh: str,
    branch: str,
    *,
    worktree: pathlib.Path,
    environment: Mapping[str, str],
) -> list[PullRequest]:
    result = _run_command(
        [
            gh,
            "pr",
            "list",
            "--repo",
            REPOSITORY,
            "--state",
            "all",
            "--head",
            branch,
            "--limit",
            "1000",
            "--json",
            (
                "number,state,headRefName,baseRefName,headRefOid,"
                "headRepository,headRepositoryOwner,mergedAt,url"
            ),
        ],
        cwd=worktree,
        env=environment,
    )
    if result.returncode != 0:
        raise PublishError("github-list-unavailable")
    try:
        raw = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublishError("github-response-invalid") from error
    if not isinstance(raw, list):
        raise PublishError("github-response-invalid")
    records: list[PullRequest] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise PublishError("github-response-invalid")
        records.append(_parse_pull_request(item))
    return records


def _find_reusable_pr(
    records: list[PullRequest],
    *,
    branch: str,
    expected_sha: str,
) -> PullRequest | None:
    if not records:
        return None
    for record in records:
        if record.branch != branch:
            raise PublishError("github-response-invalid")
        if (
            record.repository != REPOSITORY
            or record.base != BASE_BRANCH
            or record.head_sha != expected_sha
            or not record.url.startswith(f"https://github.com/{REPOSITORY}/pull/")
        ):
            raise PublishError("publication-conflict")
        if record.state in {"closed", "merged"}:
            raise PublishError("publication-conflict")
    open_records = [record for record in records if record.state == "open"]
    if len(open_records) != 1:
        raise PublishError("publication-conflict")
    return open_records[0]


def _remote_branch(
    git: str,
    git_dir: pathlib.Path,
    branch: str,
    expected_sha: str,
    *,
    remote_url: str,
    environment: Mapping[str, str],
    cwd: pathlib.Path,
) -> str | None:
    reference = f"refs/heads/{branch}"
    result = _run_command(
        [git, "--git-dir", str(git_dir), "ls-remote", remote_url, reference],
        cwd=cwd,
        env=environment,
    )
    if result.returncode != 0:
        raise PublishError("remote-state-unavailable")
    lines = [line.split() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    if (
        len(lines) != 1
        or len(lines[0]) != 2
        or not COMMIT_SHA.fullmatch(lines[0][0])
        or lines[0][1] != reference
    ):
        raise PublishError("remote-state-invalid")
    if lines[0][0] != expected_sha:
        raise PublishError("remote-head-mismatch")
    return lines[0][0]


def _publication_record(
    work_id: str,
    branch: str,
    pr: PullRequest,
) -> dict[str, object]:
    return {
        "version": 1,
        "status": "open",
        "repository": REPOSITORY,
        "base": BASE_BRANCH,
        "branch": branch,
        "work_id": work_id,
        "head_sha": pr.head_sha,
        "number": pr.number,
        "url": pr.url,
        "beads_record": {
            "publication_url": pr.url,
            "publication_sha": pr.head_sha,
            "publication_branch": branch,
        },
    }


def _update_beads(
    bd: str,
    issue_id: str,
    record: Mapping[str, object],
    *,
    cwd: pathlib.Path | None,
) -> None:
    url = record.get("url")
    sha = record.get("head_sha")
    branch = record.get("branch")
    if (
        not isinstance(url, str)
        or not isinstance(sha, str)
        or not isinstance(branch, str)
    ):
        raise PublishError("publication-record-invalid")
    result = _run_command(
        [
            bd,
            "update",
            issue_id,
            "--set-metadata",
            f"{PUBLICATION_URL_KEY}={url}",
            "--set-metadata",
            f"{PUBLICATION_SHA_KEY}={sha}",
            "--set-metadata",
            f"{PUBLICATION_BRANCH_KEY}={branch}",
        ],
        cwd=cwd,
    )
    if result.returncode != 0:
        raise PublishError("beads-update-failed")


def _verify_beads_readback(
    bd: str,
    issue_id: str,
    anchor: Anchor,
    record: Mapping[str, object],
    *,
    cwd: pathlib.Path | None,
) -> None:
    _, metadata = _load_beads_issue(bd, issue_id, cwd=cwd)
    expected = {
        **anchor.source_metadata,
        PUBLICATION_URL_KEY: record["url"],
        PUBLICATION_SHA_KEY: record["head_sha"],
        PUBLICATION_BRANCH_KEY: record["branch"],
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise PublishError("beads-readback-mismatch")


def _persist_publication(
    bd: str,
    issue_id: str,
    anchor: Anchor,
    record: Mapping[str, object],
    *,
    cwd: pathlib.Path | None,
) -> dict[str, object]:
    _update_beads(bd, issue_id, record, cwd=cwd)
    _verify_beads_readback(
        bd,
        issue_id,
        anchor,
        record,
        cwd=cwd,
    )
    return dict(record)


def publish(
    issue_id: str,
    *,
    bd_command: str = "bd",
    git_command: str = "git",
    gh_command: str = "gh",
    beads_cwd: pathlib.Path | None = None,
    openssl_command: str = "openssl",
) -> dict[str, object]:
    issue_id = _validate_work_id(issue_id)
    branch = derive_branch(issue_id)
    bd = _command_path(bd_command, "bd")
    git = _command_path(git_command, "git")
    gh = _command_path(gh_command, "gh")

    anchor = _read_anchor(bd, issue_id, cwd=beads_cwd)
    local_git_environment = _scrubbed_environment(git)
    remote_url = _check_local_repository(
        git,
        anchor.worktree,
        anchor.expected_head_sha,
        environment=local_git_environment,
    )
    _load_server_policy()
    try:
        token = _read_github_token()
    except PublishError as error:
        if error.code != "github-credential-unavailable":
            raise
        token = _mint_github_installation_token(
            openssl_command=openssl_command,
        )
    git_remote_environment = _git_remote_environment(token, git)
    gh_environment = _gh_environment(token, gh)
    with _trusted_bare_repository(
        git,
        anchor.worktree,
        anchor.expected_head_sha,
        environment=local_git_environment,
    ) as trusted_git_dir:
        _refresh_and_verify_base(
            git,
            trusted_git_dir,
            base_sha=anchor.base_sha,
            head_sha=anchor.expected_head_sha,
            remote_url=remote_url,
            remote_environment=git_remote_environment,
            local_environment=local_git_environment,
            cwd=anchor.worktree,
        )

        records = _list_pull_requests(
            gh,
            branch,
            worktree=anchor.worktree,
            environment=gh_environment,
        )
        remote_head = _remote_branch(
            git,
            trusted_git_dir,
            branch,
            anchor.expected_head_sha,
            remote_url=remote_url,
            environment=git_remote_environment,
            cwd=anchor.worktree,
        )
        reusable = _find_reusable_pr(
            records,
            branch=branch,
            expected_sha=anchor.expected_head_sha,
        )
        if reusable is not None:
            if remote_head != anchor.expected_head_sha:
                raise PublishError("remote-branch-missing")
            record = _publication_record(issue_id, branch, reusable)
            return _persist_publication(
                bd,
                issue_id,
                anchor,
                record,
                cwd=beads_cwd,
            )

        if remote_head is None:
            pushed = _run_command(
                [
                    git,
                    "--git-dir",
                    str(trusted_git_dir),
                    "push",
                    "--porcelain",
                    remote_url,
                    f"{anchor.expected_head_sha}:refs/heads/{branch}",
                ],
                cwd=anchor.worktree,
                env=git_remote_environment,
            )
            if pushed.returncode != 0:
                try:
                    observed_after_push = _remote_branch(
                        git,
                        trusted_git_dir,
                        branch,
                        anchor.expected_head_sha,
                        remote_url=remote_url,
                        environment=git_remote_environment,
                        cwd=anchor.worktree,
                    )
                except PublishError as error:
                    if error.code == "remote-head-mismatch":
                        raise
                    raise PublishError("remote-state-unavailable") from error
                if observed_after_push is None:
                    raise PublishError("push-rejected")
            elif (
                _remote_branch(
                    git,
                    trusted_git_dir,
                    branch,
                    anchor.expected_head_sha,
                    remote_url=remote_url,
                    environment=git_remote_environment,
                    cwd=anchor.worktree,
                )
                != anchor.expected_head_sha
            ):
                raise PublishError("remote-head-unverified")

        records = _list_pull_requests(
            gh,
            branch,
            worktree=anchor.worktree,
            environment=gh_environment,
        )
        reusable = _find_reusable_pr(
            records,
            branch=branch,
            expected_sha=anchor.expected_head_sha,
        )
        if reusable is None:
            created = _run_command(
                [
                    gh,
                    "pr",
                    "create",
                    "--repo",
                    REPOSITORY,
                    "--base",
                    BASE_BRANCH,
                    "--head",
                    branch,
                    "--title",
                    f"d2b-gascity: {issue_id}",
                    "--body",
                    (
                        "Publication for immutable Beads work item "
                        f"{issue_id} at head {anchor.expected_head_sha}."
                    ),
                ],
                cwd=anchor.worktree,
                env=gh_environment,
            )
            records = _list_pull_requests(
                gh,
                branch,
                worktree=anchor.worktree,
                environment=gh_environment,
            )
            reusable = _find_reusable_pr(
                records,
                branch=branch,
                expected_sha=anchor.expected_head_sha,
            )
            if reusable is None:
                if created.returncode != 0:
                    raise PublishError("github-create-unavailable")
                raise PublishError("github-create-unobserved")

        record = _publication_record(issue_id, branch, reusable)
        return _persist_publication(
            bd,
            issue_id,
            anchor,
            record,
            cwd=beads_cwd,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish one immutable Beads work item as a non-merging d2b v3 PR."
    )
    parser.add_argument("issue_id", metavar="ISSUE_ID")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        record = publish(
            args.issue_id,
        )
    except PublishError as error:
        print(f"publish-pr: {error.code}", file=sys.stderr)
        return 2
    print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
