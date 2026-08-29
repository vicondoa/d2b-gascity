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
from datetime import datetime, timedelta, timezone
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
REARMABLE_STATES = {"blocked", "exhausted", "merge-ready"}
CHECKPOINT_STATES = {"watching", "waiting"}
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
TIME_BUDGET_REASON = "time-budget-exhausted"
BACKSTOP_REASON = "backstop-expired"
ACTIVE_BUDGET = timedelta(hours=8)
BACKSTOP_BUDGET = timedelta(days=3)
DEFAULT_DUE_LIMIT = 32
MAX_DUE_LIMIT = 100
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SLUG_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?$")
WATCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
BEAD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
ACTION_KIND_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
SAFE_REASON_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")
SAFE_METADATA_KEYS = {
    "record_kind",
    "watch_id",
    "rig",
    "rig_prefix",
    "host",
    "github_host",
    "owner",
    "repo",
    "repository",
    "pr_number",
    "url",
    "base_ref",
    "target",
    "target_branch",
    "merge_strategy",
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
    "handoff_verified",
    "handoff_watch_id",
    "handoff_target",
    "handoff_publication_bead",
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
    if prefix != expected_rig["prefix"] or not WATCH_ID_RE.fullmatch(prefix):
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
        str(identity[key])
        for key in (
            "rig",
            "rig_prefix",
            "github_host",
            "owner",
            "repository",
            "pr_number",
        )
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
            return parse_time(iso_now(), field)
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


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


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


def configured_command(
    names: tuple[str, ...],
    default: str,
    *,
    label: str,
) -> list[str]:
    raw = next(
        (
            os.environ.get(name)
            for name in names
            if os.environ.get(name) is not None
        ),
        None,
    )
    if raw is None:
        command = [default]
    else:
        command = shlex.split(raw)
    if not command:
        fail(f"{label} executable is empty", "configuration")
    return command


def gh_command() -> list[str]:
    return configured_command(
        (
            "PR_BABYSIT_GH_COMMAND",
            "PR_BABYSIT_GH_BIN",
            "GH_BIN",
            "GH_EXECUTABLE",
        ),
        "gh",
        label="GitHub",
    )


def gc_command() -> list[str]:
    return configured_command(
        (
            "PR_BABYSIT_GC_COMMAND",
            "PR_BABYSIT_GC_BIN",
            "GC_BIN",
            "GC_EXECUTABLE",
        ),
        "gc",
        label="Gas City",
    )


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


def show_issue(
    issue_id: str,
    *,
    operation: str = "show",
) -> tuple[dict[str, Any], dict[str, str]]:
    validate_watch_id(issue_id)
    result = run_beads(["show", issue_id, "--json"])
    payload = require_beads(result, operation)
    issue = issue_from_payload(payload)
    if issue.get("id") != issue_id:
        fail("Beads returned a different issue ID", "beads-invalid-response")
    return issue, metadata_from_issue(issue)


def validate_bead_id(value: Any, field: str = "bead_id") -> str:
    result = text_value(value, field)
    if not BEAD_ID_RE.fullmatch(result):
        fail(f"{field} is not a safe Beads ID")
    return result


def show_bead(
    bead_id: str,
    *,
    operation: str = "show",
) -> tuple[dict[str, Any], dict[str, str]]:
    bead_id = validate_bead_id(bead_id)
    result = run_beads(["show", bead_id, "--json"])
    payload = require_beads(result, operation)
    issue = issue_from_payload(payload)
    if issue.get("id") != bead_id:
        fail("Beads returned a different issue ID", "beads-invalid-response")
    return issue, metadata_from_issue(issue)


def show_issue_if_present(
    issue_id: str,
    *,
    operation: str = "show",
) -> tuple[dict[str, Any], dict[str, str]] | None:
    try:
        return show_issue(issue_id, operation=operation)
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
    issue_id: str,
    updates: dict[str, str],
    *,
    status: str | None = None,
    assignee: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    if set(updates) - SAFE_METADATA_KEYS:
        fail("attempted to write an unallowlisted metadata key", "unsafe-state")
    validate_bead_id(issue_id)
    args = ["update", issue_id]
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
    active_since_time = parse_time(active_since, "active_since")
    if backstop_at:
        if parse_time(backstop_at, "backstop_at") < active_since_time:
            fail("backstop_at must not precede active_since")
    else:
        backstop_at = format_time(active_since_time + BACKSTOP_BUDGET)
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
    existing = show_issue_if_present(action_id, operation="stale action show")
    if existing is None:
        return
    _, action_metadata_value = existing
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


def publication_repository(
    payload: dict[str, Any],
    metadata: dict[str, str],
) -> tuple[str, str]:
    owner_value = metadata.get("owner") or payload_value(payload, "owner")
    repository_value = (
        metadata.get("repository")
        or metadata.get("repo")
        or payload_value(payload, "repository", "repo")
    )
    owner: str | None = None
    if owner_value is not None and owner_value != "":
        owner = safe_slug(owner_value, "owner")
    if repository_value is None or repository_value == "":
        fail("publication bead is missing repository", "identity-mismatch")
    repository_text = text_value(repository_value, "repository")
    if "/" in repository_text:
        if owner is not None:
            fail(
                "publication repository duplicates owner",
                "identity-mismatch",
            )
        parts = repository_text.split("/")
        if len(parts) != 2:
            fail("publication repository is malformed", "identity-mismatch")
        owner = safe_slug(parts[0], "owner")
        repository = safe_slug(parts[1], "repository")
    else:
        if owner is None:
            fail("publication bead is missing owner", "identity-mismatch")
        repository = safe_slug(repository_text, "repository")
    return owner.lower(), repository.lower()


def publication_context(
    payload: dict[str, Any],
    metadata: dict[str, str],
    *,
    require_reference: bool,
) -> dict[str, Any]:
    rig = text_value(payload_value(payload, "rig"), "rig")
    if rig not in RIGS:
        fail("unknown rig")
    expected_rig = RIGS[rig]
    recorded_rig = metadata.get("rig", "")
    if recorded_rig and recorded_rig != rig:
        fail("publication bead rig does not match request", "identity-mismatch")
    recorded_prefix = metadata.get("rig_prefix", "")
    if recorded_prefix and recorded_prefix != expected_rig["prefix"]:
        fail("publication bead prefix does not match rig", "identity-mismatch")

    recorded_strategy = metadata.get("merge_strategy", "")
    if recorded_strategy.lower() != "pr":
        fail(
            "publication bead must use pull-request merge strategy",
            "policy",
        )
    owner, repository = publication_repository(payload, metadata)

    host_value = (
        metadata.get("github_host")
        or metadata.get("host")
        or payload_value(payload, "github_host", "host")
    )
    supplied_url = payload_value(
        payload,
        "url",
        "pr_url",
        "pull_request_url",
    )
    supplied_number = payload_value(payload, "pr_number", "number")
    number: int | None = None
    if supplied_number is not None:
        number = integer_value(supplied_number, "pr_number")
    supplied_host = ""
    if supplied_url is not None:
        supplied_host, _, _, parsed_number = parse_url(
            supplied_url,
            owner,
            repository,
            number,
        )
        if number is None:
            number = parsed_number
    elif number is None and require_reference:
        fail("a pull-request URL or number is required")

    if host_value is None or host_value == "":
        if supplied_host:
            host_value = supplied_host
        elif number is not None:
            host_value = "github.com"
        else:
            fail("publication bead is missing GitHub host", "identity-mismatch")
    host = text_value(host_value, "github_host").lower()
    if host not in allowed_hosts():
        fail("GitHub host is not allowlisted", "identity-mismatch")
    if supplied_host and supplied_host != host:
        fail("pull-request URL host does not match publication", "identity-mismatch")

    recorded_base = (
        metadata.get("base_ref")
        or metadata.get("target")
        or metadata.get("target_branch")
    )
    if recorded_base:
        recorded_base = validate_git_ref(recorded_base, "base_ref")
        if recorded_base != expected_rig["base_ref"]:
            fail(
                f"publication base must be {expected_rig['base_ref']}",
                "identity-mismatch",
            )

    return {
        "rig": rig,
        "rig_prefix": expected_rig["prefix"],
        "github_host": host,
        "owner": owner,
        "repository": repository,
        "base_ref": expected_rig["base_ref"],
        "pr_number": number,
        "input_url": (
            f"https://{supplied_host}/{owner}/{repository}/pull/{number}"
            if supplied_host and number is not None
            else None
        ),
    }


def query_github_publication(context: dict[str, Any]) -> dict[str, Any]:
    number = context.get("pr_number")
    if number is None:
        fail("a pull-request number is required", "identity-mismatch")
    repo = f'{context["owner"]}/{context["repository"]}'
    command = gh_command() + [
        "pr",
        "view",
        str(number),
        "--repo",
        repo,
        "--json",
        (
            "number,url,state,isDraft,baseRefName,headRefName,headRefOid,"
            "repository"
        ),
    ]
    environment = os.environ.copy()
    environment["GH_HOST"] = context["github_host"]
    try:
        result = subprocess.run(
            command,
            cwd=beads_cwd(),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        fail("could not execute GitHub executable", "github-exec")
    if result.returncode:
        fail("GitHub pull-request query failed", "github-query")
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        fail("GitHub returned invalid pull-request JSON", "github-invalid-response")
    if not isinstance(raw, dict):
        fail("GitHub returned an invalid pull-request object", "github-invalid-response")

    number_value = raw.get("number")
    if number_value is None:
        fail("GitHub response is missing pull-request number", "github-invalid-response")
    response_number = integer_value(number_value, "pr_number")
    if response_number != context["pr_number"]:
        fail("GitHub pull-request number does not match request", "identity-mismatch")

    response_url = raw.get("url", raw.get("html_url"))
    if response_url is None:
        fail("GitHub response is missing pull-request URL", "github-invalid-response")
    response_host, response_owner, response_repository, response_number = parse_url(
        response_url,
        context["owner"],
        context["repository"],
        response_number,
    )
    if response_host != context["github_host"]:
        fail("GitHub pull-request host does not match publication", "identity-mismatch")
    canonical_url = (
        f"https://{response_host}/{response_owner.lower()}/"
        f"{response_repository.lower()}/pull/{response_number}"
    )
    input_url = context.get("input_url")
    if input_url is not None and input_url != canonical_url:
        fail("GitHub pull-request URL does not match request", "identity-mismatch")

    state_value = raw.get("state")
    if state_value is None:
        fail("GitHub response is missing pull-request state", "github-invalid-response")
    state = text_value(state_value, "pr_state").upper()
    if state != "OPEN":
        fail("pull request is not open", "pr-not-open")
    draft_value = raw.get("isDraft", raw.get("is_draft"))
    if draft_value is None:
        fail("GitHub response is missing draft status", "github-invalid-response")
    if bool_value(draft_value, "isDraft"):
        fail("draft pull requests cannot be handed off", "draft-pr")

    base_value = raw.get("baseRefName", raw.get("base_ref"))
    if base_value is None:
        fail("GitHub response is missing base ref", "github-invalid-response")
    base_ref = validate_git_ref(base_value, "base_ref")
    if base_ref != context["base_ref"]:
        fail(
            f"pull-request base must be {context['base_ref']}",
            "wrong-base",
        )

    head_value = raw.get("headRefName", raw.get("head_ref"))
    if head_value is None:
        fail("GitHub response is missing head ref", "github-invalid-response")
    head_ref = validate_git_ref(head_value, "head_ref")
    sha_value_raw = raw.get(
        "headRefOid",
        raw.get("head_sha", raw.get("current_sha")),
    )
    head_sha = sha_value(sha_value_raw, "head_sha")

    repository_value = raw.get("repository")
    if repository_value is not None:
        if isinstance(repository_value, dict):
            repository_value = (
                repository_value.get("nameWithOwner")
                or repository_value.get("name_with_owner")
                or repository_value.get("fullName")
                or repository_value.get("full_name")
            )
        if repository_value is None or not isinstance(repository_value, str):
            fail(
                "GitHub response repository identity is malformed",
                "github-invalid-response",
            )
        response_parts = repository_value.split("/")
        if len(response_parts) != 2:
            fail(
                "GitHub response repository identity is malformed",
                "github-invalid-response",
            )
        response_repo_owner = safe_slug(response_parts[0], "owner")
        response_repo_name = safe_slug(response_parts[1], "repository")
        if (
            response_repo_owner.lower() != context["owner"]
            or response_repo_name.lower() != context["repository"]
        ):
            fail("GitHub repository does not match publication", "wrong-repository")

    return {
        "rig": context["rig"],
        "rig_prefix": context["rig_prefix"],
        "github_host": context["github_host"],
        "owner": context["owner"],
        "repository": context["repository"],
        "pr_number": response_number,
        "url": canonical_url,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "head_sha": head_sha,
        "current_sha": head_sha,
        "pr_state": state,
    }


def handoff_target(rig: str) -> str:
    return f"{rig}/pr-babysit.pr-babysitter"


def receipt_updates(
    publication_bead_id: str,
    watch_id: str,
    target: str,
) -> dict[str, str]:
    return {
        "handoff_verified": "true",
        "handoff_watch_id": watch_id,
        "handoff_target": target,
        "handoff_publication_bead": publication_bead_id,
    }


def existing_receipt_matches(
    metadata: dict[str, str],
    receipt: dict[str, str],
) -> None:
    present = set(receipt) & set(metadata)
    if not present:
        return
    for key, value in receipt.items():
        if metadata.get(key) != value:
            fail(
                "existing handoff receipt does not match",
                "identity-mismatch",
            )


def block_route_failure(watch_id: str) -> None:
    _, metadata = show_issue(watch_id)
    state = state_from_metadata(metadata)
    if state in {"terminal", "exhausted", "merge-ready"}:
        return
    if state in {"watching", "repairing"}:
        try:
            transition(
                {
                    "watch_id": watch_id,
                    "to": "blocked",
                    "reason": "route-failed",
                }
            )
            return
        except StateError as error:
            if error.code not in {"illegal-transition", "stale-transition"}:
                raise
    metadata_updates(
        watch_id,
        {
            "state": "blocked",
            "claim_status": "blocked",
            "terminal_reason": "route-failed",
        },
        status="blocked",
        assignee="",
    )


def route_watch(target: str, watch_id: str) -> None:
    command = gc_command() + [
        "sling",
        "--nudge",
        target,
        watch_id,
        "--no-formula",
        "--json",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=beads_cwd(),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        fail("could not execute Gas City executable", "route-exec")
    if result.returncode:
        fail("Gas City babysitter route failed", "route-failed")


def publication_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    publication_bead_id = validate_bead_id(
        payload_value(
            payload,
            "publication_bead_id",
            "workflow_bead_id",
            "publication",
            "workflow",
        ),
        "publication_bead_id",
    )
    _, publication_metadata = show_bead(publication_bead_id)
    context = publication_context(
        payload,
        publication_metadata,
        require_reference=True,
    )
    identity = parse_identity(
        {
            **query_github_publication(context),
            "verified": True,
        }
    )
    watch_id = watch_id_for(identity)
    target = handoff_target(context["rig"])
    receipt = receipt_updates(publication_bead_id, watch_id, target)
    existing_receipt_matches(publication_metadata, receipt)
    existing_watch = show_issue_if_present(watch_id)
    if existing_watch is not None:
        _, existing_watch_metadata = existing_watch
        immutable_matches(existing_watch_metadata, identity)
        existing_receipt_matches(existing_watch_metadata, receipt)

    handoff_payload = {
        **identity,
        "verified": True,
        "observed_at": payload_value(payload, "observed_at") or iso_now(),
        "next_snapshot_at": payload_value(payload, "next_snapshot_at")
        or payload_value(payload, "observed_at")
        or iso_now(),
        "active_since": payload_value(payload, "active_since")
        or payload_value(payload, "observed_at")
        or iso_now(),
    }
    handoff_result = handoff(handoff_payload)
    try:
        route_watch(target, watch_id)
    except StateError as error:
        if error.code in {"route-failed", "route-exec"}:
            block_route_failure(watch_id)
        raise

    metadata_updates(watch_id, receipt)
    metadata_updates(publication_bead_id, receipt)
    return {
        "ok": True,
        "action": "publication-handoff",
        "rig": context["rig"],
        "publication_bead_id": publication_bead_id,
        "watch_id": watch_id,
        "target": target,
        "verified": True,
        "created": bool(handoff_result.get("created", False)),
        "reused": bool(handoff_result.get("reused", False)),
    }


def watch_identity_from_metadata(
    metadata: dict[str, str],
    context: dict[str, Any],
) -> dict[str, Any]:
    if metadata.get("record_kind") != "watch":
        fail("handoff target is not a watch record", "identity-mismatch")
    for key in (
        "github_host",
        "owner",
        "repository",
        "pr_number",
        "url",
        "base_ref",
        "head_ref",
        "head_sha",
    ):
        if not metadata.get(key):
            fail("watch identity is incomplete", "corrupt-state")
    number = integer_value(metadata["pr_number"], "pr_number")
    host, owner, repository, number = parse_url(
        metadata["url"],
        metadata["owner"],
        metadata["repository"],
        number,
    )
    if host != context["github_host"]:
        fail("watch host does not match publication", "identity-mismatch")
    if owner.lower() != context["owner"] or repository.lower() != context["repository"]:
        fail("watch repository does not match publication", "identity-mismatch")
    base_ref = validate_git_ref(metadata["base_ref"], "base_ref")
    if base_ref != context["base_ref"]:
        fail("watch base does not match publication", "identity-mismatch")
    head_ref = validate_git_ref(metadata["head_ref"], "head_ref")
    head_sha = sha_value(metadata["head_sha"], "head_sha")
    return {
        "rig": metadata.get("rig", ""),
        "rig_prefix": metadata.get("rig_prefix", ""),
        "github_host": host,
        "owner": owner.lower(),
        "repository": repository.lower(),
        "pr_number": number,
        "url": f"https://{host}/{owner.lower()}/{repository.lower()}/pull/{number}",
        "base_ref": base_ref,
        "head_ref": head_ref,
        "head_sha": head_sha,
    }


def verify_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    publication_bead_id = validate_bead_id(
        payload_value(
            payload,
            "publication_bead_id",
            "workflow_bead_id",
            "publication",
            "workflow",
        ),
        "publication_bead_id",
    )
    _, publication_metadata = show_bead(publication_bead_id)
    context = publication_context(
        payload,
        publication_metadata,
        require_reference=False,
    )
    watch_id = validate_watch_id(
        publication_metadata.get("handoff_watch_id"),
    )
    target = handoff_target(context["rig"])
    expected_receipt = receipt_updates(publication_bead_id, watch_id, target)
    existing_receipt_matches(publication_metadata, expected_receipt)
    _, watch_metadata = show_issue(watch_id)
    existing_receipt_matches(watch_metadata, expected_receipt)
    identity = watch_identity_from_metadata(watch_metadata, context)
    if watch_id_for(identity) != watch_id:
        fail("watch ID does not match watch identity", "identity-mismatch")
    if watch_metadata.get("rig") != context["rig"]:
        fail("watch rig does not match publication", "identity-mismatch")
    if watch_metadata.get("rig_prefix") != context["rig_prefix"]:
        fail("watch prefix does not match publication", "identity-mismatch")
    if watch_metadata.get("handoff_publication_bead") != publication_bead_id:
        fail("watch publication binding does not match", "identity-mismatch")
    supplied_url = context.get("input_url")
    if supplied_url is not None and supplied_url != identity["url"]:
        fail("watch URL does not match request", "identity-mismatch")
    if (
        context.get("pr_number") is not None
        and int(context["pr_number"]) != identity["pr_number"]
    ):
        fail("watch PR number does not match request", "identity-mismatch")
    return {
        "ok": True,
        "action": "verify-handoff",
        "rig": context["rig"],
        "publication_bead_id": publication_bead_id,
        "watch_id": watch_id,
        "target": target,
        "verified": True,
    }


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


def checkpoint(payload: dict[str, Any]) -> dict[str, Any]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    with watch_lock(watch_id):
        return _checkpoint_locked(payload, watch_id)


def _checkpoint_locked(
    payload: dict[str, Any],
    watch_id: str,
) -> dict[str, Any]:
    _, metadata = show_issue(watch_id)
    if metadata.get("record_kind") != "watch":
        fail("requested Beads record is not a watch", "identity-mismatch")
    current = state_from_metadata(metadata)
    generation = generation_from_metadata(metadata)
    current_head = sha_value(metadata.get("head_sha"), "head_sha")

    if current == "terminal":
        return metadata_response(
            "checkpoint",
            watch_id,
            metadata,
            changed=False,
            absorbed=True,
        )

    expected_generation_raw = payload_value(
        payload,
        "expected_generation",
        "generation",
    )
    expected_head_raw = payload_value(
        payload,
        "expected_head_sha",
        "expected_head",
        "expected_old_sha",
        "expected_old_head",
    )
    if expected_head_raw is None:
        expected_head_raw = payload_value(payload, "head_sha")
    if expected_generation_raw is None:
        fail("expected_generation is required", "invalid-request")
    if expected_head_raw is None:
        fail("expected_head_sha is required", "invalid-request")
    expected_generation = integer_value(
        expected_generation_raw,
        "expected_generation",
    )
    expected_head = sha_value(expected_head_raw, "expected_head_sha")
    if expected_generation != generation or expected_head != current_head:
        fail("checkpoint is stale for the current watch", "stale-checkpoint")

    observed_head_raw = payload_value(
        payload,
        "observed_head_sha",
        "snapshot_head_sha",
        "current_head_sha",
        "current_sha",
        "remote_head_sha",
        "new_head_sha",
        "head_sha",
    )
    if observed_head_raw is None:
        observed_head_raw = expected_head
    observed_head = sha_value(observed_head_raw, "observed_head_sha")

    observed_at = text_value(
        payload_value(
            payload,
            "observed_at",
            "last_snapshot_at",
            "snapshot_at",
            "now",
        )
        or iso_now(),
        "observed_at",
    )
    next_snapshot_at = text_value(
        payload_value(payload, "next_snapshot_at", "next_at")
        or metadata.get("next_snapshot_at", ""),
        "next_snapshot_at",
    )
    observed_time = parse_time(observed_at, "observed_at")
    parse_time(next_snapshot_at, "next_snapshot_at")
    active_since = text_value(
        metadata.get("active_since", ""),
        "active_since",
    )
    active_since_time = parse_time(active_since, "active_since")
    backstop_at = text_value(
        metadata.get("backstop_at", ""),
        "backstop_at",
        required=False,
    )
    if backstop_at:
        backstop_time = parse_time(backstop_at, "backstop_at")
        if backstop_time < active_since_time:
            fail("backstop_at must not precede active_since", "corrupt-state")
    else:
        backstop_time = active_since_time + BACKSTOP_BUDGET
        backstop_at = format_time(backstop_time)
    if observed_time < active_since_time:
        fail("observed_at must not precede active_since", "invalid-request")

    pr_state_raw = payload_value(
        payload,
        "pr_state",
        "observed_pr_state",
        "pull_request_state",
    )
    pr_state = "OPEN"
    if pr_state_raw is not None:
        pr_state = text_value(pr_state_raw, "pr_state").upper()
        if pr_state not in {"OPEN", "CLOSED", "MERGED"}:
            fail("pr_state must be OPEN, CLOSED, or MERGED")

    desired_raw = payload_value(
        payload,
        "to",
        "state",
        "next_state",
        "desired_state",
    )
    desired = (
        current
        if desired_raw is None
        else text_value(desired_raw, "to").lower()
    )
    if desired not in STATES:
        fail("to is not a supported watch state")

    claim_status = metadata.get("claim_status", "none")
    active_claim = claim_status in {"claimed", "result-recorded"}
    if current == "repairing" and not active_claim:
        fail("repairing watch has no active action claim", "corrupt-state")

    if current in CHECKPOINT_STATES and (
        claim_status != "none"
        or metadata.get("action_kind", "")
        or metadata.get("action_fingerprint", "")
    ):
        fail(
            "watch has an unconfirmed action claim",
            "unconfirmed-claim",
        )

    if pr_state != "OPEN":
        desired = "terminal"
        reason = "merged" if pr_state == "MERGED" else "closed"
    else:
        reason = safe_reason(payload_value(payload, "reason"))

    head_changed = observed_head != current_head
    next_generation = generation + 1 if head_changed else generation
    if current == "repairing" and pr_state == "OPEN" and not head_changed:
        return metadata_response(
            "checkpoint",
            watch_id,
            metadata,
            changed=False,
            waiting_for_action=True,
            dispatched=False,
        )
    if current == "repairing" and head_changed and desired == current:
        desired = "watching"
    budget_reason = ""
    if current in CHECKPOINT_STATES and pr_state == "OPEN":
        if observed_time >= backstop_time:
            budget_reason = BACKSTOP_REASON
        elif observed_time - active_since_time >= ACTIVE_BUDGET:
            budget_reason = TIME_BUDGET_REASON
    if budget_reason:
        desired = "exhausted"
        reason = budget_reason

    if desired == "repairing":
        fail(
            "checkpoint cannot create an action claim",
            "action-required",
        )
    if (
        desired != current
        and desired != "exhausted"
        and desired not in TRANSITIONS[current]
    ):
        fail(
            f"illegal watch transition {current} -> {desired}",
            "illegal-transition",
        )
    if desired == "exhausted" and not budget_reason:
        fail(
            f"illegal watch transition {current} -> {desired}",
            "illegal-transition",
        )
    if desired in {"blocked", "exhausted", "terminal"}:
        reason = safe_reason(
            reason or desired,
            required=desired == "terminal",
        )

    updates = {
        "state": desired,
        "generation": str(next_generation),
        "head_sha": observed_head,
        "last_snapshot_at": observed_at,
        "next_snapshot_at": next_snapshot_at,
        "active_since": active_since,
        "backstop_at": backstop_at,
    }
    if head_changed or desired in {
        "merge-ready",
        "blocked",
        "exhausted",
        "terminal",
    }:
        updates.update(
            {
                "action_kind": "",
                "action_fingerprint": "",
                "claim_status": (
                    "blocked"
                    if desired == "blocked"
                    else "exhausted"
                    if desired == "exhausted"
                    else "none"
                ),
                "expected_old_head": "",
                "expected_new_head": "",
                "expected_old_sha": "",
                "expected_new_sha": "",
                "pushed_sha": "",
                "validation_status": "",
            }
        )
    else:
        updates["claim_status"] = "none"
    updates["terminal_reason"] = (
        reason
        if desired in {"blocked", "exhausted", "terminal"}
        else ""
    )

    changed = any(metadata.get(key) != value for key, value in updates.items())
    if not changed:
        return metadata_response(
            "checkpoint",
            watch_id,
            metadata,
            changed=False,
            head_reconciled=False,
        )

    if current == "repairing" and (head_changed or desired == "terminal"):
        invalidate_action_claim(
            watch_id,
            metadata,
            "head-changed" if head_changed else "terminal",
        )
    if desired == "terminal":
        metadata_updates(watch_id, updates, status="open", assignee="")
        close_issue(watch_id, reason)
    else:
        metadata_updates(
            watch_id,
            updates,
            status=(
                "blocked"
                if desired in {"blocked", "exhausted"}
                else "open"
            ),
            assignee=(
                ""
                if desired in {"blocked", "exhausted"}
                else None
            ),
        )
    _, metadata = show_issue(watch_id)
    return metadata_response(
        "checkpoint",
        watch_id,
        metadata,
        changed=True,
        head_reconciled=head_changed,
        exhausted=desired == "exhausted",
        terminal_reason=(
            metadata.get("terminal_reason", "")
            if desired in {"blocked", "exhausted", "terminal"}
            else ""
        ),
    )


def list_due(payload: dict[str, Any]) -> dict[str, Any]:
    rig = payload_value(payload, "rig")
    if rig is not None:
        rig = text_value(rig, "rig")
        if rig not in RIGS:
            fail("unknown rig")
    now = parse_time(payload_value(payload, "now"), "now", default_now=True)
    limit_raw = payload_value(payload, "limit", "max_watches")
    limit = (
        DEFAULT_DUE_LIMIT
        if limit_raw is None
        else integer_value(limit_raw, "limit")
    )
    if limit > MAX_DUE_LIMIT:
        fail(f"limit must not exceed {MAX_DUE_LIMIT}")
    args = ["list", "--all", "--limit", str(limit), "--sort", "id", "--json"]
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
                fail("Beads list returned malformed metadata", "corrupt-state")
        if not isinstance(raw_metadata, dict):
            fail("Beads list returned malformed metadata", "corrupt-state")
        if raw_metadata.get("record_kind") != "watch":
            continue
        metadata = metadata_from_issue(record)
        state = state_from_metadata(metadata)
        generation_from_metadata(metadata)
        attempts_from_metadata(metadata)
        validate_watch_id(record["id"])
        if not SHA_RE.fullmatch(metadata.get("head_sha", "")):
            fail("watch metadata has an invalid head SHA", "corrupt-state")
        if not metadata.get("last_snapshot_at", ""):
            fail("watch metadata is missing last_snapshot_at", "corrupt-state")
        parse_time(metadata["last_snapshot_at"], "last_snapshot_at")
        if not metadata.get("active_since", ""):
            fail("watch metadata is missing active_since", "corrupt-state")
        active_since = parse_time(metadata["active_since"], "active_since")
        backstop_at = metadata.get("backstop_at", "")
        if not backstop_at:
            fail("watch metadata is missing backstop_at", "corrupt-state")
        if parse_time(backstop_at, "backstop_at") < active_since:
            fail("backstop_at must not precede active_since", "corrupt-state")
        next_at = metadata.get("next_snapshot_at", "")
        if not next_at:
            fail("watch metadata is missing next_snapshot_at", "corrupt-state")
        next_time = parse_time(next_at, "next_snapshot_at")
        if rig and metadata.get("rig") != rig:
            continue
        if state not in CHECKPOINT_STATES:
            continue
        if (
            metadata.get("claim_status", "none") != "none"
            or metadata.get("action_kind", "")
            or metadata.get("action_fingerprint", "")
        ):
            continue
        if next_time <= now:
            due.append(
                {
                    "watch_id": record["id"],
                    "metadata": dict(sorted(metadata.items())),
                    "_due_at": next_time,
                }
            )
    due.sort(
        key=lambda item: (
            item["_due_at"],
            item["watch_id"],
        )
    )
    due = due[:limit]
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
            "checkpoint": (
                "watch_id",
                "expected_generation",
                "expected_head_sha",
                "observed_head_sha",
                "observed_at",
                "next_snapshot_at",
                "to",
            ),
            "checkpoint-state": (
                "watch_id",
                "expected_generation",
                "expected_head_sha",
                "observed_head_sha",
                "observed_at",
                "next_snapshot_at",
                "to",
            ),
            "record-checkpoint": (
                "watch_id",
                "expected_generation",
                "expected_head_sha",
                "observed_head_sha",
                "observed_at",
                "next_snapshot_at",
                "to",
            ),
            "publication-handoff": (
                "rig",
                "publication_bead_id",
                "url",
                "pr_number",
            ),
            "publish-handoff": (
                "rig",
                "publication_bead_id",
                "url",
                "pr_number",
            ),
            "handoff-publication": (
                "rig",
                "publication_bead_id",
                "url",
                "pr_number",
            ),
            "verify-handoff": (
                "rig",
                "publication_bead_id",
                "url",
                "pr_number",
            ),
            "verify-publication-handoff": (
                "rig",
                "publication_bead_id",
                "url",
                "pr_number",
            ),
        }.get(request_action, ())
        for key, value in zip(positional_fields, positionals):
            data.setdefault(key, value)
    data["action"] = request_action
    return data


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action == "handoff":
        return handoff(payload)
    if action in {
        "publication-handoff",
        "publish-handoff",
        "handoff-publication",
    }:
        return publication_handoff(payload)
    if action in {"verify-handoff", "verify-publication-handoff"}:
        return verify_handoff(payload)
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
    if action in {"checkpoint", "checkpoint-state", "record-checkpoint"}:
        return checkpoint(payload)
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
