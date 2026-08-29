#!/usr/bin/env python3

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import stat
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


RIGS = {
    "d2b": {"prefix": "d2b", "base_ref": "v3"},
    "city-source": {"prefix": "city", "base_ref": "main"},
}
STATES = {
    "watching",
    "waiting",
    "repairing",
    "merge-ready",
    "blocked",
    "exhausted",
    "terminal",
}
TERMINAL_STATES = {"terminal"}
REARMABLE_STATES = {"blocked", "exhausted", "merge-ready"}
TRANSITIONS = {
    "watching": {"waiting", "repairing", "merge-ready", "blocked", "terminal"},
    "waiting": {"watching", "terminal"},
    "repairing": {"watching", "exhausted", "blocked", "terminal"},
    "merge-ready": {"terminal"},
    "blocked": {"terminal"},
    "exhausted": {"terminal"},
    "terminal": set(),
}
VALIDATION_STATUSES = {"passed", "failed", "not-run", "ambiguous"}
AMBIGUOUS_REASON = "ambiguous-outcome"
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SLUG_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?$")
LOWER_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
WATCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ACTION_KIND_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
SAFE_REASON_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")
SAFE_METADATA_KEYS = {
    "record_kind",
    "watch_id",
    "rig",
    "rig_prefix",
    "github_host",
    "owner",
    "repository",
    "pr_number",
    "url",
    "base_ref",
    "head_ref",
    "head_sha",
    "posture",
    "target_posture",
    "state",
    "generation",
    "next_snapshot_at",
    "last_snapshot_at",
    "action_kind",
    "action_fingerprint",
    "claim_status",
    "attempts",
    "expected_old_head",
    "expected_new_head",
    "expected_old_sha",
    "expected_new_sha",
    "pushed_sha",
    "last_pushed_sha",
    "validation_status",
    "terminal_reason",
    "active_since",
    "backstop_at",
}


class StateError(Exception):
    def __init__(self, message: str, code: str = "invalid-request") -> None:
        super().__init__(message)
        self.code = code


class BeadsResult:
    def __init__(
        self,
        args: list[str],
        returncode: int,
        stdout: str,
        stderr: str,
        payload: Any,
    ) -> None:
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.payload = payload

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def emit(value: Any) -> None:
    sys.stdout.write(canonical_json(value) + "\n")


def fail(message: str, code: str = "invalid-request") -> None:
    raise StateError(message, code)


def text_value(value: Any, field: str, *, required: bool = True) -> str:
    if value is None:
        if required:
            fail(f"{field} is required")
        return ""
    if isinstance(value, bool):
        fail(f"{field} must be a string")
    result = str(value)
    if required and result == "":
        fail(f"{field} is required")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in result):
        fail(f"{field} contains a control character")
    return result


def bool_value(value: Any, field: str, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    fail(f"{field} must be boolean")


def sha_value(value: Any, field: str, *, required: bool = True) -> str:
    if value is not None and not isinstance(value, str):
        fail(f"{field} must be a 40-hex SHA")
    result = text_value(value, field, required=required)
    if result == "":
        return ""
    if not SHA_RE.fullmatch(result):
        fail(f"{field} must be a 40-hex SHA")
    return result.lower()


def integer_value(value: Any, field: str) -> int:
    if isinstance(value, bool):
        fail(f"{field} must be a positive integer")
    result = str(value)
    if not re.fullmatch(r"[1-9][0-9]*", result):
        fail(f"{field} must be a positive integer")
    return int(result)


def safe_slug(value: Any, field: str) -> str:
    if not isinstance(value, str):
        fail(f"{field} is not a valid slug")
    result = text_value(value, field)
    if not SLUG_RE.fullmatch(result):
        fail(f"{field} is not a valid slug")
    return result


def safe_reason(value: Any, field: str = "reason", *, required: bool = False) -> str:
    if value is None or value == "":
        if required:
            fail(f"{field} is required")
        return ""
    result = text_value(value, field).strip().lower()
    result = re.sub(r"\s+", "-", result)
    if not SAFE_REASON_RE.fullmatch(result):
        fail(f"{field} must be a safe reason token")
    return result


def normalize_fingerprint(value: Any) -> str:
    if value is None or not isinstance(value, str):
        fail("fingerprint must be a string")
    result = value
    if len(result) > 1_000_000:
        fail("fingerprint is too large")
    normalized = unicodedata.normalize("NFKC", result)
    normalized = " ".join(normalized.split()).casefold()
    if not normalized:
        fail("fingerprint is required")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def validate_git_ref(value: Any, field: str) -> str:
    if not isinstance(value, str):
        fail(f"{field} is not a valid git ref")
    result = text_value(value, field)
    try:
        check = subprocess.run(
            ["git", "check-ref-format", "--branch", result],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        fail(f"{field} cannot be validated as a git ref", "configuration")
    if check.returncode:
        fail(f"{field} is not a valid git ref")
    return result


def allowed_hosts() -> set[str]:
    raw = (
        os.environ.get("PR_BABYSIT_ALLOWED_HOSTS")
        or os.environ.get("PR_BABYSIT_GITHUB_HOST_ALLOWLIST")
        or os.environ.get("GITHUB_HOST_ALLOWLIST")
        or "github.com"
    )
    hosts = {item.strip().lower() for item in re.split(r"[\s,]+", raw) if item.strip()}
    if not hosts:
        fail("GitHub host allowlist is empty", "configuration")
    for host in hosts:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
            fail("GitHub host allowlist contains an invalid host", "configuration")
    return hosts


def parse_url(
    value: Any,
    owner: str | None,
    repository: str | None,
    number: int | None,
) -> tuple[str, str, str, int]:
    if not isinstance(value, str):
        fail("url must be an exact HTTPS pull-request URL")
    url = text_value(value, "url")
    try:
        parsed = urlsplit(url)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError:
        fail("url must be an exact HTTPS pull-request URL")
    if (
        parsed.scheme.lower() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.endswith("/")
    ):
        fail("url must be an exact HTTPS pull-request URL")
    host = (hostname or "").lower()
    if host not in allowed_hosts():
        fail("url host is not allowlisted")
    parts = parsed.path.split("/")
    if len(parts) != 5 or parts[0] or parts[3] != "pull":
        fail("url must have the form https://host/owner/repository/pull/number")
    url_owner = safe_slug(parts[1], "owner")
    url_repository = safe_slug(parts[2], "repository")
    url_number = integer_value(parts[4], "pr_number")
    if owner is not None and owner.lower() != url_owner.lower():
        fail("owner does not match url")
    if repository is not None and repository.lower() != url_repository.lower():
        fail("repository does not match url")
    if number is not None and number != url_number:
        fail("pr_number does not match url")
    return host, url_owner, url_repository, url_number


def payload_value(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in payload:
            return payload[name]
    return None


def parse_identity(payload: dict[str, Any]) -> dict[str, Any]:
    if "verified" in payload and not bool_value(payload["verified"], "verified"):
        fail("verified handoff is required")
    rig = text_value(payload_value(payload, "rig"), "rig")
    if rig not in RIGS:
        fail("unknown rig")
    expected_rig = RIGS[rig]
    prefix = text_value(
        payload_value(payload, "prefix", "rig_prefix") or expected_rig["prefix"],
        "prefix",
    )
    if prefix != expected_rig["prefix"] or not LOWER_SLUG_RE.fullmatch(prefix):
        fail("prefix does not match the owning rig")

    owner_raw = payload_value(payload, "owner")
    repository_raw = payload_value(payload, "repository", "repo")
    owner = safe_slug(owner_raw, "owner") if owner_raw is not None else None
    repository = None
    if repository_raw is not None:
        repository_text = text_value(repository_raw, "repository")
        if "/" in repository_text:
            if owner is not None:
                fail("repository must not include owner when owner is supplied")
            parts = repository_text.split("/")
            if len(parts) != 2:
                fail("repository is not a valid owner/repository slug")
            owner = safe_slug(parts[0], "owner")
            repository = safe_slug(parts[1], "repository")
        else:
            repository = safe_slug(repository_text, "repository")

    number_raw = payload_value(payload, "pr_number", "number")
    number = integer_value(number_raw, "pr_number") if number_raw is not None else None
    url = payload_value(payload, "url", "pr_url")
    if url is None:
        fail("url is required")
    host, owner, repository, number = parse_url(url, owner, repository, number)
    supplied_host = payload_value(payload, "github_host", "host")
    if supplied_host is not None:
        if text_value(supplied_host, "github_host").lower() != host:
            fail("github_host does not match url")

    base_ref = validate_git_ref(
        payload_value(payload, "base_ref", "base", "base_branch"),
        "base_ref",
    )
    if base_ref != expected_rig["base_ref"]:
        fail(f"base_ref must be {expected_rig['base_ref']} for {rig}")
    head_ref = validate_git_ref(
        payload_value(payload, "head_ref", "head", "head_branch"),
        "head_ref",
    )
    head_sha = sha_value(
        payload_value(
            payload,
            "head_sha",
            "current_sha",
            "current_head_sha",
            "observed_head_sha",
            "sha",
        ),
        "head_sha",
    )
    current_sha = sha_value(
        payload_value(
            payload,
            "current_sha",
            "current_head_sha",
            "current_head",
            "current",
            "observed_head_sha",
            "sha",
        )
        or head_sha,
        "current_sha",
    )
    if head_sha != current_sha:
        fail("head_sha and current_sha must match")

    pr_state_raw = payload_value(payload, "pr_state", "state")
    pr_state = (
        text_value(pr_state_raw, "pr_state").upper()
        if pr_state_raw is not None
        else "OPEN"
    )
    if pr_state not in {"OPEN", "CLOSED", "MERGED"}:
        fail("pr_state must be OPEN, CLOSED, or MERGED")

    identity = {
        "rig": rig,
        "rig_prefix": prefix,
        "github_host": host,
        "owner": owner.lower(),
        "repository": repository.lower(),
        "pr_number": str(number),
        "url": f"https://{host}/{owner.lower()}/{repository.lower()}/pull/{number}",
        "base_ref": base_ref,
        "head_ref": head_ref,
        "head_sha": current_sha,
    }
    identity["pr_state"] = pr_state
    return identity


def watch_id_for(identity: dict[str, Any]) -> str:
    seed = "\x00".join(
        [
            identity["rig"],
            identity["rig_prefix"],
            identity["github_host"],
            identity["owner"],
            identity["repository"],
            identity["pr_number"],
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f'{identity["rig_prefix"]}-pr-{digest[:32]}'


def action_id_for(
    watch_id: str,
    generation: int,
    action_kind: str,
    fingerprint: str,
) -> str:
    seed = "\x00".join([watch_id, str(generation), action_kind, fingerprint])
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"{watch_id}-action-{generation}-{digest[:32]}"


def iso_now() -> str:
    configured = os.environ.get("PR_BABYSIT_NOW")
    if configured:
        parse_time(configured, "PR_BABYSIT_NOW")
        return configured
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def parse_time(value: Any, field: str, *, default_now: bool = False) -> datetime:
    if value is None or value == "":
        if default_now:
            return datetime.now(timezone.utc)
        fail(f"{field} is required")
    result = text_value(value, field)
    normalized = result[:-1] + "+00:00" if result.endswith("Z") else result
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        fail(f"{field} must be an RFC3339 timestamp")
    if parsed.tzinfo is None:
        fail(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def state_from_metadata(metadata: dict[str, str]) -> str:
    state = metadata.get("state", "")
    if state not in STATES:
        fail("watch metadata has an invalid state", "corrupt-state")
    return state


def generation_from_metadata(metadata: dict[str, str]) -> int:
    generation = metadata.get("generation", "")
    if not re.fullmatch(r"[1-9][0-9]*", generation):
        fail("watch metadata has an invalid generation", "corrupt-state")
    return int(generation)


def attempts_from_metadata(metadata: dict[str, str]) -> int:
    attempts = metadata.get("attempts", "")
    if not re.fullmatch(r"[0-9]+", attempts):
        fail("watch metadata has an invalid attempts count", "corrupt-state")
    return int(attempts)


def metadata_from_issue(issue: dict[str, Any]) -> dict[str, str]:
    raw = issue.get("metadata", {})
    if raw is None:
        raw = {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            fail("Beads metadata is not valid JSON", "corrupt-state")
    if not isinstance(raw, dict):
        fail("Beads metadata must be a JSON object", "corrupt-state")
    unknown = set(raw) - SAFE_METADATA_KEYS
    if unknown:
        fail("Beads metadata contains an unallowlisted key", "unsafe-state")
    result: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, (dict, list, tuple)) or value is None:
            fail("Beads metadata values must be scalar strings", "unsafe-state")
        result[str(key)] = str(value)
    return result


def issue_from_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        if not payload:
            fail("Beads returned no issue", "beads-not-found")
        issue = payload[0]
    elif isinstance(payload, dict) and isinstance(payload.get("issues"), list):
        if not payload["issues"]:
            fail("Beads returned no issue", "beads-not-found")
        issue = payload["issues"][0]
    else:
        issue = payload
    if not isinstance(issue, dict) or not issue.get("id"):
        fail("Beads returned an invalid issue", "beads-invalid-response")
    return issue


def beads_command() -> list[str]:
    raw = (
        os.environ.get("PR_BABYSIT_BEADS_COMMAND")
        or os.environ.get("PR_BABYSIT_BEADS")
        or os.environ.get("PR_BABYSIT_BEADS_BIN")
        or os.environ.get("PR_BABYSIT_BEADS_EXECUTABLE")
        or os.environ.get("BEADS_BIN")
        or os.environ.get("BEADS_EXECUTABLE")
        or os.environ.get("GC_BD_BIN")
        or os.environ.get("PR_BABYSIT_BD_BIN")
        or os.environ.get("GC_BEADS_BIN")
        or os.environ.get("BD_BIN")
    )
    if raw:
        command = shlex.split(raw)
    else:
        gc_bin = os.environ.get("GC_BIN")
        if gc_bin:
            command = [gc_bin, "bd"]
        elif shutil.which("gc"):
            command = ["gc", "bd"]
        else:
            command = [os.environ.get("BD_BIN", "bd")]
    if not command:
        fail("Beads executable is empty", "configuration")
    return command


def beads_cwd() -> str:
    candidate = (
        os.environ.get("PR_BABYSIT_BEADS_CWD")
        or os.environ.get("GC_RIG_ROOT")
        or os.getcwd()
    )
    if not os.path.isdir(candidate):
        fail("Beads working directory does not exist", "configuration")
    return candidate


def _lock_directory_path() -> pathlib.Path:
    override = (
        os.environ.get("PR_BABYSIT_LOCK_DIR")
        or os.environ.get("PR_BABYSIT_LOCK_DIRECTORY")
    )
    if override:
        path = pathlib.Path(override)
        if not path.is_absolute():
            fail(
                "PR_BABYSIT_LOCK_DIR must be an absolute path",
                "configuration",
            )
        return path
    rig_root = (
        os.environ.get("GC_RIG_ROOT")
        or os.environ.get("PR_BABYSIT_BEADS_CWD")
        or os.getcwd()
    )
    path = pathlib.Path(rig_root)
    if not path.is_absolute():
        path = path.absolute()
    return path / ".beads" / "pr-babysit-locks"


def lock_directory() -> pathlib.Path:
    path = _lock_directory_path()
    if not path.is_absolute():
        fail("lock directory must be absolute", "configuration")
    if path == pathlib.Path(path.anchor):
        fail("lock directory must not be the filesystem root", "configuration")
    current = pathlib.Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            info = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                info = current.lstat()
            except OSError:
                fail("could not create lock directory", "configuration")
        except OSError:
            fail("could not validate lock directory", "configuration")
        else:
            if stat.S_ISLNK(info.st_mode):
                fail("lock directory path contains a symlink", "configuration")
            if not stat.S_ISDIR(info.st_mode):
                fail("lock directory path is not a directory", "configuration")
            continue
        try:
            info = current.lstat()
        except OSError:
            fail("could not validate lock directory", "configuration")
        if stat.S_ISLNK(info.st_mode):
            fail("lock directory path contains a symlink", "configuration")
        if not stat.S_ISDIR(info.st_mode):
            fail("lock directory path is not a directory", "configuration")
    return path


@contextmanager
def watch_lock(watch_id: str):
    validate_watch_id(watch_id)
    directory = lock_directory()
    lock_path = directory / f"{watch_id}.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError:
        fail("could not open watch lock", "configuration")
    locked = False
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            fail("watch lock is not a regular file", "configuration")
        if info.st_size:
            fail("watch lock contains state", "unsafe-state")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except OSError:
            fail("could not acquire watch lock", "configuration")
        locked = True
        yield
    finally:
        if locked:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(descriptor)


def run_beads(args: list[str], *, actor: str | None = None) -> BeadsResult:
    command = beads_command() + args
    environment = os.environ.copy()
    if actor:
        environment["BEADS_ACTOR"] = actor
    try:
        result = subprocess.run(
            command,
            cwd=beads_cwd(),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        fail(f"could not execute Beads executable: {exc.__class__.__name__}", "beads-exec")
    output = result.stdout.strip()
    parsed: Any = None
    if output:
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            parsed = None
    return BeadsResult(args, result.returncode, result.stdout, result.stderr, parsed)


def beads_error(
    result: BeadsResult,
    operation: str,
    *,
    atomic_conflict: bool = True,
) -> StateError:
    if re.search(
        r"not\s+found|no\s+issue",
        result.stderr + "\n" + result.stdout,
        flags=re.IGNORECASE,
    ):
        return StateError(f"Beads {operation} could not find the record", "beads-not-found")
    if atomic_conflict and re.search(
        r"already[\s_-]+claimed|already[\s_-]+exists|duplicate|conflict",
        result.stderr + "\n" + result.stdout,
        flags=re.IGNORECASE,
    ):
        return StateError(f"Beads {operation} reported an atomic conflict", "already-exists")
    return StateError(f"Beads {operation} failed", "beads-error")


def require_beads(result: BeadsResult, operation: str) -> Any:
    if not result.ok:
        raise beads_error(result, operation)
    if result.payload is None:
        fail(f"Beads {operation} returned non-JSON output", "beads-invalid-response")
    return result.payload


def show_issue(issue_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    validate_watch_id(issue_id)
    result = run_beads(["show", issue_id, "--json"])
    payload = require_beads(result, "show")
    issue = issue_from_payload(payload)
    if issue.get("id") != issue_id:
        fail("Beads returned a different issue ID", "beads-invalid-response")
    return issue, metadata_from_issue(issue)


def show_issue_if_present(
    issue_id: str,
) -> tuple[dict[str, Any], dict[str, str]] | None:
    try:
        return show_issue(issue_id)
    except StateError as error:
        if error.code == "beads-not-found":
            return None
        raise


def validate_watch_id(value: Any) -> str:
    result = text_value(value, "watch_id")
    if not WATCH_ID_RE.fullmatch(result):
        fail("watch_id is not a safe Beads ID")
    return result


def immutable_matches(
    metadata: dict[str, str],
    identity: dict[str, Any],
) -> None:
    for key in (
        "rig",
        "rig_prefix",
        "github_host",
        "owner",
        "repository",
        "pr_number",
        "url",
        "base_ref",
        "head_ref",
        "target_posture",
        "posture",
    ):
        expected = identity[key] if key not in {"target_posture", "posture"} else "target"
        if metadata.get(key) != str(expected):
            fail("existing watch identity does not match handoff", "identity-mismatch")


def metadata_response(
    action: str,
    watch_id: str,
    metadata: dict[str, str],
    **extra: Any,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "ok": True,
        "action": action,
        "watch_id": watch_id,
        "metadata": dict(sorted(metadata.items())),
    }
    if "state" in metadata:
        response["state"] = metadata["state"]
    if "generation" in metadata:
        response["generation"] = int(metadata["generation"])
    response.update(extra)
    return response


def metadata_updates(
    watch_id: str,
    updates: dict[str, str],
    *,
    status: str | None = None,
    assignee: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    if set(updates) - SAFE_METADATA_KEYS:
        fail("attempted to write an unallowlisted metadata key", "unsafe-state")
    args = ["update", watch_id]
    if status is not None:
        args.extend(["--status", status])
    if assignee is not None:
        args.extend(["--assignee", assignee])
    for key in sorted(updates):
        args.extend(["--set-metadata", f"{key}={updates[key]}"])
    args.append("--json")
    result = run_beads(args, actor=actor)
    return require_beads(result, "metadata update")


def close_issue(issue_id: str, reason: str) -> dict[str, Any]:
    result = run_beads(["close", issue_id, "--reason", reason, "--json"])
    return require_beads(result, "close")


def initial_watch_metadata(
    identity: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, str]:
    observed_at = text_value(
        payload_value(payload, "observed_at", "last_snapshot_at") or iso_now(),
        "observed_at",
    )
    parse_time(observed_at, "observed_at")
    next_snapshot_at = text_value(
        payload_value(payload, "next_snapshot_at") or observed_at,
        "next_snapshot_at",
    )
    parse_time(next_snapshot_at, "next_snapshot_at")
    active_since = text_value(
        payload_value(payload, "active_since") or observed_at,
        "active_since",
    )
    parse_time(active_since, "active_since")
    backstop_at = text_value(
        payload_value(payload, "backstop_at") or "",
        "backstop_at",
        required=False,
    )
    if backstop_at:
        parse_time(backstop_at, "backstop_at")
    result = {
        "record_kind": "watch",
        **{key: str(value) for key, value in identity.items() if key != "pr_state"},
        "posture": "target",
        "target_posture": "target",
        "state": "watching",
        "generation": "1",
        "next_snapshot_at": next_snapshot_at,
        "last_snapshot_at": observed_at,
        "action_kind": "",
        "action_fingerprint": "",
        "claim_status": "none",
        "attempts": "0",
        "expected_old_head": "",
        "expected_new_head": "",
        "expected_old_sha": "",
        "expected_new_sha": "",
        "pushed_sha": "",
        "last_pushed_sha": "",
        "validation_status": "",
        "terminal_reason": "",
        "active_since": active_since,
        "backstop_at": backstop_at,
    }
    return result


def create_watch(
    watch_id: str,
    metadata: dict[str, str],
    identity: dict[str, Any] | None = None,
) -> tuple[bool, bool, dict[str, Any], dict[str, str]]:
    existing = show_issue_if_present(watch_id)
    if existing is not None:
        issue, current_metadata = existing
        if identity is not None:
            immutable_matches(current_metadata, identity)
        return False, True, issue, current_metadata

    title = f"PR babysit watch {watch_id}"
    description = "Durable target-only pull-request watch record."
    result = run_beads(
        [
            "create",
            "--id",
            watch_id,
            "--title",
            title,
            "--description",
            description,
            "--type",
            "task",
            "--metadata",
            canonical_json(metadata),
            "--silent",
            "--json",
        ]
    )
    if not result.ok:
        raise beads_error(result, "create", atomic_conflict=False)

    issue, current_metadata = show_issue(watch_id)
    if identity is not None:
        immutable_matches(current_metadata, identity)
    return True, False, issue, current_metadata


def action_metadata(
    watch_id: str,
    identity: dict[str, Any],
    generation: int,
    action_kind: str,
    fingerprint: str,
    head_sha: str,
) -> dict[str, str]:
    return {
        "record_kind": "action",
        "watch_id": watch_id,
        "rig": identity["rig"],
        "rig_prefix": identity["rig_prefix"],
        "generation": str(generation),
        "action_kind": action_kind,
        "action_fingerprint": fingerprint,
        "claim_status": "claimed",
        "attempts": "1",
        "expected_old_head": head_sha,
        "expected_new_head": "",
        "expected_old_sha": head_sha,
        "expected_new_sha": "",
        "pushed_sha": "",
        "last_pushed_sha": "",
        "validation_status": "",
        "terminal_reason": "",
    }


def create_action(
    action_id: str,
    watch_id: str,
    metadata: dict[str, str],
    action_kind: str,
    generation: int,
    fingerprint: str,
) -> tuple[bool, dict[str, Any], dict[str, str]]:
    expected_identity = (
        "record_kind",
        "watch_id",
        "generation",
        "action_kind",
        "action_fingerprint",
        "expected_old_head",
    )

    def validate_action_identity(
        current_metadata: dict[str, str],
    ) -> None:
        for key in expected_identity:
            if current_metadata.get(key) != metadata.get(key):
                fail(
                    "existing action identity does not match claim",
                    "identity-mismatch",
                )

    existing = show_issue_if_present(action_id)
    if existing is not None:
        issue, current_metadata = existing
        validate_action_identity(current_metadata)
        return False, issue, current_metadata

    title = f"PR babysit action {action_kind}-{fingerprint[:12]}"
    description = f"Bounded target-only action for watch generation {generation}."
    result = run_beads(
        [
            "create",
            "--id",
            action_id,
            "--title",
            title,
            "--description",
            description,
            "--type",
            "task",
            "--parent",
            watch_id,
            "--metadata",
            canonical_json(metadata),
            "--silent",
            "--json",
        ]
    )
    if not result.ok:
        raise beads_error(result, "action create", atomic_conflict=False)
    require_beads(result, "action create")
    issue, current_metadata = show_issue(action_id)
    validate_action_identity(current_metadata)
    return True, issue, current_metadata


def clear_claim_updates(
    state: str,
    generation: int,
    *,
    head_sha: str,
    observed_at: str,
    next_snapshot_at: str,
    active_since: str,
    terminal_reason: str = "",
    last_pushed_sha: str = "",
    backstop_at: str | None = None,
) -> dict[str, str]:
    updates = {
        "state": state,
        "generation": str(generation),
        "head_sha": head_sha,
        "last_snapshot_at": observed_at,
        "next_snapshot_at": next_snapshot_at,
        "active_since": active_since,
        "action_kind": "",
        "action_fingerprint": "",
        "claim_status": "none",
        "attempts": "0",
        "expected_old_head": "",
        "expected_new_head": "",
        "expected_old_sha": "",
        "expected_new_sha": "",
        "pushed_sha": "",
        "last_pushed_sha": last_pushed_sha,
        "validation_status": "",
        "terminal_reason": terminal_reason,
    }
    if backstop_at is not None:
        updates["backstop_at"] = backstop_at
    return updates


def invalidate_action_claim(
    watch_id: str,
    metadata: dict[str, str],
    reason: str,
) -> None:
    action_kind = metadata.get("action_kind", "")
    fingerprint = metadata.get("action_fingerprint", "")
    claim_status = metadata.get("claim_status", "")
    if (
        not action_kind
        or not fingerprint
        or claim_status not in {"claimed", "result-recorded"}
    ):
        return
    generation = generation_from_metadata(metadata)
    action_id = action_id_for(watch_id, generation, action_kind, fingerprint)
    result = run_beads(["show", action_id, "--json"])
    if not result.ok:
        error = beads_error(result, "stale action show")
        if error.code == "beads-not-found":
            return
        raise error
    action = issue_from_payload(require_beads(result, "stale action show"))
    action_metadata_value = metadata_from_issue(action)
    if action_metadata_value.get("watch_id") != watch_id:
        fail("stale action does not belong to watch", "identity-mismatch")
    metadata_updates(
        action_id,
        {
            "claim_status": "stale",
            "terminal_reason": reason,
        },
        status="blocked",
        assignee="",
    )


def handoff(payload: dict[str, Any]) -> dict[str, Any]:
    identity = parse_identity(payload)
    rearm = bool_value(payload_value(payload, "rearm", "allow_rearm"), "rearm")
    watch_id = watch_id_for(identity)
    initial = initial_watch_metadata(identity, payload)
    with watch_lock(watch_id):
        return _handoff_locked(
            payload,
            identity,
            rearm,
            watch_id,
            initial,
        )


def _handoff_locked(
    payload: dict[str, Any],
    identity: dict[str, Any],
    rearm: bool,
    watch_id: str,
    initial: dict[str, str],
) -> dict[str, Any]:
    created, reused, _, metadata = create_watch(watch_id, initial, identity)
    immutable_matches(metadata, identity)
    current_state = state_from_metadata(metadata)
    if current_state == "terminal":
        return metadata_response(
            "handoff",
            watch_id,
            metadata,
            created=False,
            reused=True,
            absorbed=True,
        )
    if created and identity["pr_state"] != "OPEN":
        reason = "merged" if identity["pr_state"] == "MERGED" else "closed"
        metadata_updates(
            watch_id,
            {
                "state": "terminal",
                "claim_status": "none",
                "terminal_reason": reason,
            },
            status="open",
            assignee="",
        )
        close_issue(watch_id, reason)
        _, metadata = show_issue(watch_id)
        return metadata_response(
            "handoff",
            watch_id,
            metadata,
            created=True,
            reused=False,
            absorbed=False,
        )

    incoming_head = identity["head_sha"]
    current_head = metadata.get("head_sha", "")
    if not SHA_RE.fullmatch(current_head):
        fail("existing watch has an invalid head SHA", "corrupt-state")
    generation = generation_from_metadata(metadata)
    observed_at = text_value(
        payload_value(payload, "observed_at", "last_snapshot_at") or iso_now(),
        "observed_at",
    )
    next_snapshot_at = text_value(
        payload_value(payload, "next_snapshot_at") or metadata.get("next_snapshot_at", observed_at),
        "next_snapshot_at",
    )
    active_since = text_value(
        payload_value(payload, "active_since") or observed_at,
        "active_since",
    )
    backstop_at = text_value(
        payload_value(payload, "backstop_at")
        if payload_value(payload, "backstop_at") is not None
        else metadata.get("backstop_at", ""),
        "backstop_at",
        required=False,
    )
    parse_time(observed_at, "observed_at")
    parse_time(next_snapshot_at, "next_snapshot_at")
    parse_time(active_since, "active_since")
    if backstop_at:
        parse_time(backstop_at, "backstop_at")
    head_changed = current_head != incoming_head
    should_rearm = current_state in REARMABLE_STATES and rearm
    if identity["pr_state"] != "OPEN":
        invalidate_action_claim(watch_id, metadata, "terminal")
        updates = clear_claim_updates(
            "terminal",
            generation,
            head_sha=metadata["head_sha"],
            observed_at=metadata["last_snapshot_at"],
            next_snapshot_at=metadata["next_snapshot_at"],
            active_since=metadata["active_since"],
            terminal_reason=(
                "merged"
                if identity["pr_state"] == "MERGED"
                else "closed"
            ),
            last_pushed_sha=metadata.get("last_pushed_sha", ""),
            backstop_at=backstop_at,
        )
        metadata_updates(
            watch_id,
            updates,
            status="open",
            assignee="",
        )
        close_issue(
            watch_id,
            "merged" if identity["pr_state"] == "MERGED" else "closed",
        )
        _, metadata = show_issue(watch_id)
    elif head_changed or should_rearm:
        invalidate_action_claim(
            watch_id,
            metadata,
            "head-changed" if head_changed else "rearmed",
        )
        next_generation = generation + 1
        updates = clear_claim_updates(
            "watching",
            next_generation,
            head_sha=incoming_head,
            observed_at=observed_at,
            next_snapshot_at=next_snapshot_at,
            active_since=active_since,
            last_pushed_sha=metadata.get("last_pushed_sha", ""),
            backstop_at=backstop_at,
        )
        metadata_updates(
            watch_id,
            updates,
            status="open",
            assignee="",
        )
        _, metadata = show_issue(watch_id)
    return metadata_response(
        "handoff",
        watch_id,
        metadata,
        created=created,
        reused=reused or not created,
        absorbed=False,
    )


def show_state(payload: dict[str, Any]) -> dict[str, Any]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    _, metadata = show_issue(watch_id)
    if metadata.get("record_kind") != "watch":
        fail("requested Beads record is not a watch", "identity-mismatch")
    state_from_metadata(metadata)
    generation_from_metadata(metadata)
    return metadata_response("show", watch_id, metadata)


def transition(payload: dict[str, Any]) -> dict[str, Any]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    with watch_lock(watch_id):
        return _transition_locked(payload, watch_id)


def _transition_locked(
    payload: dict[str, Any],
    watch_id: str,
) -> dict[str, Any]:
    desired = text_value(payload_value(payload, "to", "state"), "to").lower()
    if desired not in STATES:
        fail("to is not a supported watch state")
    _, metadata = show_issue(watch_id)
    if metadata.get("record_kind") != "watch":
        fail("requested Beads record is not a watch", "identity-mismatch")
    current = state_from_metadata(metadata)
    generation = generation_from_metadata(metadata)
    if not SHA_RE.fullmatch(metadata.get("head_sha", "")):
        fail("watch metadata has an invalid head SHA", "corrupt-state")
    expected_state = payload_value(payload, "expected_state", "from")
    if expected_state is not None:
        expected_state = text_value(expected_state, "expected_state").lower()
        if expected_state not in STATES:
            fail("expected_state is not a supported watch state")
        if current != expected_state:
            fail("watch state changed before transition", "stale-transition")
    expected_generation = payload_value(payload, "expected_generation", "generation")
    if expected_generation is not None:
        if integer_value(expected_generation, "expected_generation") != generation_from_metadata(metadata):
            fail("watch generation changed before transition", "stale-transition")
    expected_head = payload_value(
        payload,
        "expected_head_sha",
        "expected_head",
        "head_sha",
    )
    if expected_head is not None and sha_value(expected_head, "expected_head_sha") != metadata.get("head_sha"):
        fail("watch head changed before transition", "stale-transition")
    if current == "terminal":
        return metadata_response(
            "transition",
            watch_id,
            metadata,
            absorbed=True,
        )
    if desired == current:
        return metadata_response("transition", watch_id, metadata, changed=False)
    if desired not in TRANSITIONS[current]:
        fail(f"illegal watch transition {current} -> {desired}", "illegal-transition")
    reason = safe_reason(payload_value(payload, "reason"), required=desired == "terminal")
    updates = {"state": desired}
    if desired in {"blocked", "exhausted"}:
        updates["claim_status"] = "blocked" if desired == "blocked" else "exhausted"
        updates["terminal_reason"] = reason or desired
    elif desired == "terminal":
        invalidate_action_claim(watch_id, metadata, "terminal")
        updates = clear_claim_updates(
            "terminal",
            generation,
            head_sha=metadata["head_sha"],
            observed_at=metadata["last_snapshot_at"],
            next_snapshot_at=metadata["next_snapshot_at"],
            active_since=metadata["active_since"],
            terminal_reason=reason,
            last_pushed_sha=metadata.get("last_pushed_sha", ""),
        )
    else:
        updates["terminal_reason"] = ""
    if desired == "terminal":
        metadata_updates(watch_id, updates, status="open", assignee="")
        close_issue(watch_id, reason)
    else:
        metadata_updates(
            watch_id,
            updates,
            status="blocked" if desired in {"blocked", "exhausted"} else "open",
            assignee="" if desired in {"blocked", "exhausted"} else None,
        )
    _, metadata = show_issue(watch_id)
    return metadata_response("transition", watch_id, metadata, changed=True)


def claim_action(payload: dict[str, Any]) -> dict[str, Any]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    with watch_lock(watch_id):
        return _claim_action_locked(payload, watch_id)


def _claim_action_locked(
    payload: dict[str, Any],
    watch_id: str,
) -> dict[str, Any]:
    action_kind = text_value(
        payload_value(payload, "action_kind", "kind"),
        "action_kind",
    ).lower()
    if not ACTION_KIND_RE.fullmatch(action_kind):
        fail("action_kind is not a safe token")
    fingerprint = normalize_fingerprint(payload_value(payload, "fingerprint"))
    generation_raw = payload_value(payload, "generation")
    head_raw = payload_value(
        payload,
        "head_sha",
        "current_sha",
        "expected_old_sha",
        "expected_old_head",
    )
    if (
        isinstance(generation_raw, str)
        and SHA_RE.fullmatch(generation_raw)
        and head_raw is not None
        and not SHA_RE.fullmatch(str(head_raw))
    ):
        generation_raw, head_raw = head_raw, generation_raw
    expected_generation = integer_value(generation_raw, "generation")
    head_sha = sha_value(head_raw, "head_sha")
    _, metadata = show_issue(watch_id)
    if metadata.get("record_kind") != "watch":
        fail("requested Beads record is not a watch", "identity-mismatch")
    state = state_from_metadata(metadata)
    generation = generation_from_metadata(metadata)
    attempts = attempts_from_metadata(metadata)
    if state in {"blocked", "exhausted", "merge-ready", "terminal"}:
        fail(f"cannot claim an action while watch is {state}", "not-claimable")
    if generation != expected_generation or metadata.get("head_sha") != head_sha:
        fail("action claim is stale for the current watch head", "stale-claim")
    action_id = action_id_for(watch_id, generation, action_kind, fingerprint)
    current_claim = metadata.get("claim_status", "none")
    if current_claim in {"claimed", "result-recorded"}:
        same = (
            metadata.get("action_kind") == action_kind
            and metadata.get("action_fingerprint") == fingerprint
        )
        if same:
            return {
                "ok": True,
                "action": "claim-action",
                "watch_id": watch_id,
                "action_id": action_id,
                "generation": generation,
                "reused": True,
                "state": state,
            }
        fail("watch already has an unconfirmed action claim", "already-claimed")

    actor = f"pr-babysit-{action_id}"
    claim_result = run_beads(["update", watch_id, "--claim", "--json"], actor=actor)
    if not claim_result.ok:
        error = beads_error(claim_result, "claim")
        if error.code == "already-exists":
            fail("watch is already claimed by another action", "already-claimed")
        raise error

    action_initial = action_metadata(
        watch_id,
        {
            "rig": metadata.get("rig", ""),
            "rig_prefix": metadata.get("rig_prefix", ""),
        },
        generation,
        action_kind,
        fingerprint,
        head_sha,
    )
    action_initial["record_kind"] = "action"
    created, _, _ = create_action(
        action_id,
        watch_id,
        action_initial,
        action_kind,
        generation,
        fingerprint,
    )
    updates = {
        "state": "repairing",
        "action_kind": action_kind,
        "action_fingerprint": fingerprint,
        "claim_status": "claimed",
        "attempts": str(attempts + 1),
        "expected_old_head": head_sha,
        "expected_new_head": "",
        "expected_old_sha": head_sha,
        "expected_new_sha": "",
        "pushed_sha": "",
        "validation_status": "",
        "terminal_reason": "",
    }
    metadata_updates(watch_id, updates)
    _, metadata = show_issue(watch_id)
    return {
        "ok": True,
        "action": "claim-action",
        "watch_id": watch_id,
        "action_id": action_id,
        "generation": generation,
        "created": created,
        "reused": not created,
        "state": metadata["state"],
    }


def action_context(
    payload: dict[str, Any],
) -> tuple[str, str, dict[str, str], dict[str, str], int, str]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    action_id = validate_watch_id(payload_value(payload, "action_id"))
    _, watch_metadata = show_issue(watch_id)
    if watch_metadata.get("record_kind") != "watch":
        fail("requested Beads record is not a watch", "identity-mismatch")
    _, action_metadata_value = show_issue(action_id)
    if action_metadata_value.get("record_kind") != "action":
        fail("requested Beads record is not an action", "identity-mismatch")
    generation = integer_value(payload_value(payload, "generation"), "generation")
    if generation != generation_from_metadata(watch_metadata):
        fail("action generation is stale", "stale-claim")
    if action_metadata_value.get("watch_id") != watch_id:
        fail("action does not belong to watch", "identity-mismatch")
    if watch_metadata.get("action_kind") == "":
        fail("watch has no active action claim", "not-claimable")
    if watch_metadata.get("state") != "repairing":
        fail("watch is not repairing an active action", "not-claimable")
    action_kind = watch_metadata.get("action_kind", "")
    fingerprint = watch_metadata.get("action_fingerprint", "")
    if not action_kind or not fingerprint:
        fail("watch has incomplete action identity", "corrupt-state")
    expected_action_id = action_id_for(
        watch_id,
        generation,
        action_kind,
        fingerprint,
    )
    if expected_action_id != action_id:
        fail("action ID does not match the active claim", "identity-mismatch")
    return (
        watch_id,
        action_id,
        watch_metadata,
        action_metadata_value,
        generation,
        action_kind,
    )


def record_repair_result(payload: dict[str, Any]) -> dict[str, Any]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    with watch_lock(watch_id):
        return _record_repair_result_locked(payload)


def _record_repair_result_locked(payload: dict[str, Any]) -> dict[str, Any]:
    (
        watch_id,
        action_id,
        watch_metadata,
        action_metadata_value,
        generation,
        _,
    ) = action_context(payload)
    expected_old_sha = sha_value(
        payload_value(payload, "expected_old_sha", "expected_old_head"),
        "expected_old_sha",
    )
    pushed_sha = sha_value(
        payload_value(payload, "pushed_sha", "new_head_sha", "expected_new_sha"),
        "pushed_sha",
        required=False,
    )
    validation_status = text_value(
        payload_value(payload, "validation_status", "validation"),
        "validation_status",
    ).lower()
    if validation_status not in VALIDATION_STATUSES:
        fail("validation_status is not supported")
    if validation_status == "passed" and not pushed_sha:
        fail("a passed repair result requires pushed_sha")
    if (
        expected_old_sha != watch_metadata.get("expected_old_head")
        or expected_old_sha != action_metadata_value.get("expected_old_head")
    ):
        fail("repair result expected old SHA does not match claim", "stale-claim")
    remote_head = sha_value(
        payload_value(payload, "remote_head_sha", "current_sha"),
        "remote_head_sha",
        required=False,
    )
    if remote_head and pushed_sha and remote_head != pushed_sha:
        validation_status = "ambiguous"
    action_updates = {
        "claim_status": "ambiguous"
        if validation_status == "ambiguous"
        else "result-recorded",
        "expected_old_head": expected_old_sha,
        "expected_new_head": pushed_sha,
        "expected_old_sha": expected_old_sha,
        "expected_new_sha": pushed_sha,
        "pushed_sha": pushed_sha,
        "last_pushed_sha": pushed_sha,
        "validation_status": validation_status,
    }
    metadata_updates(
        action_id,
        action_updates,
        status="blocked" if validation_status == "ambiguous" else None,
    )
    watch_updates = {
        "expected_old_head": expected_old_sha,
        "expected_new_head": pushed_sha,
        "expected_old_sha": expected_old_sha,
        "expected_new_sha": pushed_sha,
        "pushed_sha": pushed_sha,
        "last_pushed_sha": pushed_sha,
        "validation_status": validation_status,
        "claim_status": (
            "blocked"
            if validation_status == "ambiguous"
            else "result-recorded"
        ),
    }
    if validation_status == "ambiguous":
        watch_updates.update(
            {
                "state": "blocked",
                "terminal_reason": AMBIGUOUS_REASON,
            }
        )
        metadata_updates(watch_id, watch_updates, status="blocked", assignee="")
    elif validation_status == "failed":
        watch_updates.update(
            {
                "state": "blocked",
                "terminal_reason": "repair-validation-failed",
            }
        )
        metadata_updates(watch_id, watch_updates, status="blocked", assignee="")
    else:
        metadata_updates(watch_id, watch_updates)
    _, metadata = show_issue(watch_id)
    return metadata_response(
        "record-repair-result",
        watch_id,
        metadata,
        action_id=action_id,
        generation=generation,
    )


def confirm_action(payload: dict[str, Any]) -> dict[str, Any]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    with watch_lock(watch_id):
        return _confirm_action_locked(payload)


def _confirm_action_locked(payload: dict[str, Any]) -> dict[str, Any]:
    (
        watch_id,
        action_id,
        watch_metadata,
        action_metadata_value,
        generation,
        _,
    ) = action_context(payload)
    current_sha = sha_value(
        payload_value(
            payload,
            "current_sha",
            "current_head_sha",
            "remote_head_sha",
            "new_head_sha",
        ),
        "current_sha",
    )
    validation_status = action_metadata_value.get("validation_status", "")
    pushed_sha = action_metadata_value.get("pushed_sha", "")
    expected_old_sha = action_metadata_value.get("expected_old_head", "")
    if not pushed_sha or validation_status != "passed":
        reason = (
            "repair-validation-failed"
            if validation_status == "failed"
            else AMBIGUOUS_REASON
        )
        metadata_updates(
            action_id,
            {
                "claim_status": "ambiguous"
                if reason == AMBIGUOUS_REASON
                else "blocked",
                "terminal_reason": reason,
                "validation_status": validation_status or "ambiguous",
            },
            status="blocked",
        )
        metadata_updates(
            watch_id,
            {
                "state": "blocked",
                "claim_status": "blocked",
                "terminal_reason": reason,
            },
            status="blocked",
            assignee="",
        )
        _, metadata = show_issue(watch_id)
        return metadata_response(
            "confirm-action",
            watch_id,
            metadata,
            action_id=action_id,
            terminal_reason=reason,
        )
    if current_sha != pushed_sha:
        reason = AMBIGUOUS_REASON
        metadata_updates(
            action_id,
            {
                "claim_status": "ambiguous",
                "terminal_reason": reason,
                "validation_status": "ambiguous",
            },
            status="blocked",
        )
        metadata_updates(
            watch_id,
            {
                "state": "blocked",
                "claim_status": "blocked",
                "terminal_reason": reason,
            },
            status="blocked",
            assignee="",
        )
        _, metadata = show_issue(watch_id)
        return metadata_response(
            "confirm-action",
            watch_id,
            metadata,
            action_id=action_id,
            terminal_reason=reason,
        )

    observed_at = text_value(
        payload_value(payload, "observed_at", "last_snapshot_at") or iso_now(),
        "observed_at",
    )
    next_snapshot_at = text_value(
        payload_value(payload, "next_snapshot_at")
        or watch_metadata.get("next_snapshot_at", observed_at),
        "next_snapshot_at",
    )
    parse_time(observed_at, "observed_at")
    parse_time(next_snapshot_at, "next_snapshot_at")
    close_issue(action_id, "confirmed")
    next_generation = generation + 1
    metadata_updates(
        watch_id,
        clear_claim_updates(
            "watching",
            next_generation,
            head_sha=current_sha,
            observed_at=observed_at,
            next_snapshot_at=next_snapshot_at,
            active_since=observed_at,
            last_pushed_sha=pushed_sha,
        ),
        status="open",
        assignee="",
    )
    _, metadata = show_issue(watch_id)
    return metadata_response(
        "confirm-action",
        watch_id,
        metadata,
        action_id=action_id,
        confirmed=True,
        expected_old_sha=expected_old_sha,
    )


def list_due(payload: dict[str, Any]) -> dict[str, Any]:
    rig = payload_value(payload, "rig")
    if rig is not None:
        rig = text_value(rig, "rig")
        if rig not in RIGS:
            fail("unknown rig")
    now = parse_time(payload_value(payload, "now"), "now", default_now=True)
    args = ["list", "--all", "--limit", "0", "--json"]
    args.extend(["--metadata-field", "record_kind=watch"])
    if rig:
        args.extend(["--metadata-field", f"rig={rig}"])
    result = run_beads(args)
    payload_value_result = require_beads(result, "list")
    records = payload_value_result
    if isinstance(records, dict) and isinstance(records.get("issues"), list):
        records = records["issues"]
    if not isinstance(records, list):
        fail("Beads list returned an invalid result", "beads-invalid-response")
    due: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or not record.get("id"):
            continue
        raw_metadata = record.get("metadata", {})
        if isinstance(raw_metadata, str):
            try:
                raw_metadata = json.loads(raw_metadata)
            except json.JSONDecodeError:
                continue
        if (
            not isinstance(raw_metadata, dict)
            or raw_metadata.get("record_kind") != "watch"
        ):
            continue
        metadata = metadata_from_issue(record)
        state_from_metadata(metadata)
        validate_watch_id(record["id"])
        if rig and metadata.get("rig") != rig:
            continue
        if metadata.get("state") in TERMINAL_STATES:
            continue
        next_at = metadata.get("next_snapshot_at", "")
        if not next_at:
            continue
        if parse_time(next_at, "next_snapshot_at") <= now:
            due.append(
                {
                    "watch_id": record["id"],
                    "metadata": dict(sorted(metadata.items())),
                    "_due_at": parse_time(next_at, "next_snapshot_at"),
                }
            )
    due.sort(
        key=lambda item: (
            item["_due_at"],
            item["watch_id"],
        )
    )
    for item in due:
        item.pop("_due_at", None)
    return {"ok": True, "action": "list-due", "watches": due}


def parse_cli_request(argv: list[str]) -> dict[str, Any]:
    action: str | None = None
    option_values: dict[str, Any] = {}
    positionals: list[str] = []
    remaining = list(argv)
    if remaining and not remaining[0].startswith("-"):
        action = remaining.pop(0)
    index = 0
    while index < len(remaining):
        token = remaining[index]
        if token == "--":
            positionals.extend(remaining[index + 1 :])
            break
        if not token.startswith("--"):
            positionals.append(token)
            index += 1
            continue
        key_value = token[2:]
        if "=" in key_value:
            key, value = key_value.split("=", 1)
            option_values[key.replace("-", "_")] = value
            index += 1
            continue
        key = key_value.replace("-", "_")
        if index + 1 < len(remaining) and not remaining[index + 1].startswith("--"):
            option_values[key] = remaining[index + 1]
            index += 2
        else:
            option_values[key] = True
            index += 1
    input_json = option_values.pop("input_json", None) or option_values.pop(
        "input",
        None,
    )
    stdin_text = sys.stdin.read()
    data: dict[str, Any] = {}
    if input_json is not None:
        try:
            parsed = json.loads(str(input_json))
        except json.JSONDecodeError:
            fail("input-json must be valid JSON")
        if not isinstance(parsed, dict):
            fail("input-json must be a JSON object")
        data.update(parsed)
    elif stdin_text.strip():
        try:
            parsed = json.loads(stdin_text)
        except json.JSONDecodeError:
            fail("stdin must contain a JSON object")
        if not isinstance(parsed, dict):
            fail("stdin must contain a JSON object")
        data.update(parsed)
    elif positionals and positionals[0].lstrip().startswith("{"):
        try:
            parsed = json.loads(positionals.pop(0))
        except json.JSONDecodeError:
            fail("positional JSON must be valid")
        if not isinstance(parsed, dict):
            fail("positional JSON must be an object")
        data.update(parsed)
    data.update(option_values)
    if positionals:
        data.setdefault("_args", positionals)
    request_action = action or data.pop("action", None) or data.pop("operation", None)
    if request_action is None:
        fail("an action is required")
    request_action = str(request_action).strip().lower().replace("_", "-")
    if request_action == "state" and positionals and positionals[0] == "show":
        positionals = positionals[1:]
    if (
        request_action == "transition"
        and len(positionals) >= 3
        and positionals[1] in STATES
        and positionals[2] in STATES
    ):
        data.setdefault("expected_state", positionals[1])
        positionals = [positionals[0], positionals[2], *positionals[3:]]
    if positionals:
        positional_fields = {
            "show": ("watch_id",),
            "state": ("watch_id",),
            "state-show": ("watch_id",),
            "transition": ("watch_id", "to", "reason"),
            "claim-action": (
                "watch_id",
                "action_kind",
                "fingerprint",
                "generation",
                "head_sha",
            ),
            "claim": (
                "watch_id",
                "action_kind",
                "fingerprint",
                "generation",
                "head_sha",
            ),
            "record-repair-result": (
                "watch_id",
                "action_id",
                "expected_old_sha",
                "pushed_sha",
                "validation_status",
            ),
            "record": (
                "watch_id",
                "action_id",
                "expected_old_sha",
                "pushed_sha",
                "validation_status",
            ),
            "confirm-action": ("watch_id", "action_id", "current_sha",),
            "confirm": ("watch_id", "action_id", "current_sha",),
        }.get(request_action, ())
        for key, value in zip(positional_fields, positionals):
            data.setdefault(key, value)
    data["action"] = request_action
    return data


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action == "handoff":
        return handoff(payload)
    if action in {"show", "state", "state-show"}:
        return show_state(payload)
    if action == "transition":
        return transition(payload)
    if action in {"claim-action", "claim"}:
        return claim_action(payload)
    if action in {"record-repair-result", "record"}:
        return record_repair_result(payload)
    if action in {"confirm-action", "confirm"}:
        return confirm_action(payload)
    if action in {"list-due", "due"}:
        return list_due(payload)
    fail("unsupported action")


def main(argv: list[str]) -> int:
    try:
        request = parse_cli_request(argv)
        result = dispatch(request)
        emit(result)
        return 0
    except StateError as error:
        emit({"ok": False, "error": {"code": error.code, "message": str(error)}})
        return 1
    except (OSError, ValueError, TypeError) as error:
        emit(
            {
                "ok": False,
                "error": {
                    "code": "internal-error",
                    "message": error.__class__.__name__,
                },
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
