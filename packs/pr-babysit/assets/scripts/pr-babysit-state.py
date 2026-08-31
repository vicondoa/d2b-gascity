#!/usr/bin/env python3

from __future__ import annotations

from contextlib import contextmanager
import errno
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
    "waiting": {"watching", "merge-ready", "blocked", "terminal"},
    "repairing": {"watching", "exhausted", "blocked", "terminal"},
    "merge-ready": {"terminal"},
    "blocked": {"terminal"},
    "exhausted": {"terminal"},
    "terminal": set(),
}
VALIDATION_STATUSES = {"passed", "failed", "not-run", "ambiguous"}
REVIEW_VERDICTS = {"passed", "failed"}
FORMULA_ATTACHMENT_STATES = {"false", "pending", "true"}
HANDOFF_ROUTE_STATUSES = {"pending", "complete", "route-failed"}
HANDOFF_WAKE_STATUSES = {"not-started", "ready", "delivered", "failed"}
ACTION_CLEANUP_STATUSES = {
    "claimed",
    "result-recorded",
    "blocked",
    "ambiguous",
    "exhausted",
}
AMBIGUOUS_REASON = "ambiguous-outcome"
TIME_BUDGET_REASON = "time-budget-exhausted"
BACKSTOP_REASON = "backstop-expired"
ATTEMPT_LIMITS = {"ci": 3, "review": 2}
REPAIR_FORMULA = "mol-pr-babysit-repair"
ACTIVE_BUDGET = timedelta(hours=8)
BACKSTOP_BUDGET = timedelta(days=3)
ORDER_TIMEOUT_SECONDS = 30
BEADS_TIMEOUT_SECONDS = ORDER_TIMEOUT_SECONDS
ROUTE_TIMEOUT_SECONDS = 20
GAS_CITY_TIMEOUT_SECONDS = ROUTE_TIMEOUT_SECONDS
FORMULA_TIMEOUT_SECONDS = ORDER_TIMEOUT_SECONDS
GIT_VALIDATION_TIMEOUT_SECONDS = ORDER_TIMEOUT_SECONDS
GITHUB_TIMEOUT_SECONDS = 60
SWEEP_INTERVAL = timedelta(minutes=1)
WAKE_LEASE = timedelta(seconds=10)
DEFAULT_DUE_LIMIT = 4
MAX_DUE_LIMIT = 100
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SLUG_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?$")
WATCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
BEAD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
ACTION_KIND_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
SAFE_REASON_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SAFE_GIT_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
GITHUB_PUBLICATION_JSON_FIELDS = (
    "number",
    "url",
    "state",
    "isDraft",
    "baseRefName",
    "headRefName",
    "headRefOid",
    "isCrossRepository",
    "headRepository",
    "headRepositoryOwner",
)
GITHUB_PUBLICATION_FIELDS = ",".join(GITHUB_PUBLICATION_JSON_FIELDS)
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
    "head_repository",
    "head_sha",
    "observed_head_sha",
    "posture",
    "target_posture",
    "state",
    "generation",
    "next_snapshot_at",
    "wake_lease_until",
    "last_snapshot_at",
    "action_kind",
    "action_fingerprint",
    "action_id",
    "attempt_key",
    "attempt_limit",
    "attempt_history",
    "claim_status",
    "attempts",
    "expected_old_head",
    "expected_new_head",
    "expected_old_sha",
    "expected_new_sha",
    "pushed_sha",
    "last_pushed_sha",
    "validation_status",
    "make_check_result",
    "addressed_thread_ids",
    "pending_disposition_action_kind",
    "pending_disposition_ids",
    "pending_disposition_head_sha",
    "pending_disposition_generation",
    "formula_attached",
    "formula_root",
    "blocker_emitted",
    "provenance_version",
    "worktree_provenance",
    "worktree_head_sha",
    "worktree_head_ref",
    "worktree_base_ref",
    "worktree_generation",
    "worktree_action_id",
    "terminal_reason",
    "active_since",
    "backstop_at",
    "handoff_verified",
    "handoff_watch_id",
    "handoff_target",
    "handoff_publication_bead",
    "handoff_route_status",
    "handoff_wake_status",
    "gc.routed_to",
    "gc.session_name",
    "candidate_head_sha",
    "worker_signoff_sha",
    "review_verdict",
    "review_verdict_action_id",
    "review_verdict_generation",
    "review_verdict_head_sha",
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


def normalize_action_kind(value: Any) -> str:
    result = text_value(value, "action_kind").strip().lower()
    result = re.sub(r"[\s_]+", "-", result)
    if not ACTION_KIND_RE.fullmatch(result):
        fail("action_kind is not a safe token")
    return result


def action_attempt_key(
    action_kind: str,
    fingerprint: str,
    head_sha: str,
) -> str:
    seed = "\x00".join((action_kind, fingerprint, head_sha.lower()))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def action_attempt_limit(action_kind: str) -> int:
    if action_kind == "review" or action_kind.startswith("review-"):
        return ATTEMPT_LIMITS["review"]
    return ATTEMPT_LIMITS["ci"]


def parse_attempt_history(value: Any) -> dict[str, int]:
    if value is None or value == "":
        return {}
    raw = text_value(value, "attempt_history")
    history: dict[str, int] = {}
    for entry in raw.split(","):
        if not entry:
            fail("attempt_history contains an empty entry", "corrupt-state")
        key, separator, count = entry.partition(":")
        if (
            not separator
            or not re.fullmatch(r"[0-9a-f]{64}", key)
            or not re.fullmatch(r"[0-9]+", count)
        ):
            fail("attempt_history is malformed", "corrupt-state")
        history[key] = int(count)
    if len(history) > 128:
        fail("attempt_history is too large", "corrupt-state")
    return history


def format_attempt_history(history: dict[str, int]) -> str:
    if len(history) > 128:
        fail("attempt_history is too large", "unsafe-state")
    return ",".join(
        f"{key}:{history[key]}"
        for key in sorted(history)
    )


def safe_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str):
        fail(f"{field} must be a safe identifier")
    result = text_value(value, field)
    if len(result) > 128 or not SAFE_ID_RE.fullmatch(result):
        fail(f"{field} must be a safe identifier")
    return result


def safe_identifier_list(value: Any, field: str) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        values: list[Any] = [
            item.strip() for item in value.split(",") if item.strip()
        ]
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        fail(f"{field} must be a list of safe identifiers")
    if len(values) > 128:
        fail(f"{field} contains too many identifiers")
    identifiers = sorted(
        {
            safe_identifier(item, field)
            for item in values
        }
    )
    if any(len(item) > 128 for item in identifiers):
        fail(f"{field} contains an identifier that is too long")
    return ",".join(identifiers)


def require_repair_credentials() -> None:
    copilot_values = (
        os.environ.get("COPILOT_GITHUB_TOKEN", ""),
        os.environ.get("COPILOT_REQUESTS_TOKEN", ""),
        os.environ.get("COPILOT_TOKEN", ""),
    )
    for github_name in ("GH_TOKEN", "GITHUB_TOKEN"):
        github_value = os.environ.get(github_name, "")
        if github_value and github_value in copilot_values:
            fail(
                f"{github_name} must not reuse a Copilot token",
                "credential-coupling",
            )
    attestation = os.environ.get(
        "PR_BABYSIT_GITHUB_CAPABILITY_ATTESTED",
        "",
    )
    if attestation != "contents-write,pull-requests-read":
        fail(
            "repair requires operator-attested Contents write and "
            "Pull requests read capability",
            "credential-capability",
        )


def check_repair_credentials() -> dict[str, Any]:
    require_repair_credentials()
    return {
        "ok": True,
        "action": "check-credentials",
        "operator_attested": True,
    }


def validate_git_ref(value: Any, field: str) -> str:
    if not isinstance(value, str):
        fail(f"{field} is not a valid git ref")
    result = text_value(value, field)
    if not SAFE_GIT_REF_RE.fullmatch(result):
        fail(f"{field} is not a safe git ref")
    try:
        check = subprocess.run(
            ["git", "check-ref-format", "--branch", result],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_VALIDATION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        fail(
            f"{field} could not be validated as a git ref",
            "configuration",
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


def repository_name_with_owner(
    value: Any,
    field: str,
) -> str:
    if not isinstance(value, str):
        fail(f"{field} must be an owner/repository identity", "identity-mismatch")
    text = text_value(value, field)
    parts = text.split("/")
    if len(parts) != 2:
        fail(f"{field} must be an owner/repository identity", "identity-mismatch")
    owner = safe_slug(parts[0], f"{field}_owner")
    repository = safe_slug(parts[1], field)
    return f"{owner.lower()}/{repository.lower()}"


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

    head_repository_raw = payload_value(
        payload,
        "head_repository",
        "head_repository_name_with_owner",
    )
    head_repository = None
    if head_repository_raw is not None:
        head_repository = repository_name_with_owner(
            head_repository_raw,
            "head_repository",
        )
        expected_repository = f"{owner.lower()}/{repository.lower()}"
        if head_repository != expected_repository:
            fail(
                "pull-request head repository does not match base repository",
                "cross-repository-head",
            )

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
        "observed_head_sha": current_sha,
    }
    if head_repository is not None:
        identity["head_repository"] = head_repository
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
        if isinstance(value, bool):
            result[str(key)] = "true" if value else "false"
        else:
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
def watch_lock(watch_id: str, *, blocking: bool = True):
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
            lock_flags = fcntl.LOCK_EX
            if not blocking:
                lock_flags |= fcntl.LOCK_NB
            fcntl.flock(descriptor, lock_flags)
        except OSError as error:
            if (
                not blocking
                and error.errno
                in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}
            ):
                yield False
                return
            fail("could not acquire watch lock", "configuration")
        locked = True
        yield True
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
            timeout=BEADS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        fail("Beads executable timed out", "beads-exec")
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


def action_records_for_watch(watch_id: str) -> list[tuple[dict[str, Any], dict[str, str]]]:
    """Return every durable action recorded for a watch.

    The watch can clear its active action fields after a failed setup, so the
    action ID in watch metadata is not sufficient for invalidation.  Querying
    the allowlisted action records also makes cleanup cover crash and blocker
    paths without trusting an opaque payload.
    """
    validate_watch_id(watch_id)
    result = run_beads(
        [
            "list",
            "--all",
            "--metadata-field",
            "record_kind=action",
            "--metadata-field",
            f"watch_id={watch_id}",
            "--json",
        ]
    )
    payload = require_beads(result, "action list")
    if isinstance(payload, dict) and isinstance(payload.get("issues"), list):
        payload = payload["issues"]
    if not isinstance(payload, list):
        fail("Beads action list returned an invalid result", "beads-invalid-response")
    actions: list[tuple[dict[str, Any], dict[str, str]]] = []
    for record in payload:
        if not isinstance(record, dict) or not record.get("id"):
            continue
        action_id = validate_bead_id(record["id"], "action_id")
        metadata = metadata_from_issue(record)
        if metadata.get("record_kind") != "action":
            continue
        if metadata.get("watch_id") != watch_id:
            continue
        actions.append((record, metadata))
    return actions


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
    if "head_repository" in identity and metadata.get("head_repository") != str(
        identity["head_repository"]
    ):
        fail("existing watch head repository does not match handoff", "identity-mismatch")


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


def formula_attachment_state(
    value: Any,
    *,
    field: str = "formula_attached",
    default: str = "false",
) -> str:
    state = default if value in (None, "") else str(value).lower()
    if state not in FORMULA_ATTACHMENT_STATES:
        fail(f"{field} must be false, pending, or true", "corrupt-state")
    return state


def pending_disposition_details(
    metadata: dict[str, str],
) -> tuple[str, str, str, int] | None:
    kind = metadata.get("pending_disposition_action_kind", "")
    identifiers = metadata.get("pending_disposition_ids", "")
    head_sha = metadata.get("pending_disposition_head_sha", "")
    generation = metadata.get("pending_disposition_generation", "")

    if not kind and not identifiers:
        # Accept the pre-carryover shape so a restart can still finish a
        # confirmation written by an older helper.
        if (
            metadata.get("action_id", "") == ""
            and metadata.get("claim_status", "none") == "none"
            and (
                metadata.get("action_kind", "").startswith("review")
                and metadata.get("addressed_thread_ids", "")
            )
        ):
            kind = metadata.get("action_kind", "")
            identifiers = metadata.get("addressed_thread_ids", "")
            head_sha = metadata.get("head_sha", "")
            generation = metadata.get("generation", "")
        else:
            return None

    if not kind or not identifiers:
        fail(
            "pending review dispositions are incomplete",
            "corrupt-state",
        )
    kind = normalize_action_kind(kind)
    if kind != "review" and not kind.startswith("review-"):
        fail(
            "pending dispositions must belong to a review action",
            "corrupt-state",
        )
    identifiers = safe_identifier_list(identifiers, "pending_disposition_ids")
    if not identifiers:
        fail(
            "pending review dispositions have no addressed IDs",
            "corrupt-state",
        )
    if metadata.get("action_kind", "") not in {"", kind}:
        fail(
            "pending disposition action kind disagrees with the watch",
            "corrupt-state",
        )
    if metadata.get("addressed_thread_ids", "") not in {"", identifiers}:
        fail(
            "pending disposition IDs disagree with the watch",
            "corrupt-state",
        )
    head_sha = sha_value(head_sha or metadata.get("head_sha"), "pending_disposition_head_sha")
    generation = integer_value(
        generation or metadata.get("generation"),
        "pending_disposition_generation",
    )
    return kind, identifiers, head_sha, generation


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


def close_action(action_id: str, reason: str) -> dict[str, Any]:
    issue, _ = show_bead(action_id, operation="action close check")
    if issue.get("status") == "closed":
        return issue
    return close_issue(action_id, reason)


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
        "wake_lease_until": "",
        "last_snapshot_at": observed_at,
        "observed_head_sha": identity["head_sha"],
        "action_kind": "",
        "action_fingerprint": "",
        "action_id": "",
        "attempt_key": "",
        "attempt_limit": "",
        "attempt_history": "",
        "claim_status": "none",
        "attempts": "0",
        "expected_old_head": "",
        "expected_new_head": "",
        "expected_old_sha": "",
        "expected_new_sha": "",
        "pushed_sha": "",
        "last_pushed_sha": "",
        "validation_status": "",
        "make_check_result": "",
        "addressed_thread_ids": "",
        "pending_disposition_action_kind": "",
        "pending_disposition_ids": "",
        "pending_disposition_head_sha": "",
        "pending_disposition_generation": "",
        "formula_attached": "false",
        "formula_root": "",
        "blocker_emitted": "false",
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


def ensure_action_blocks_watch(action_id: str, watch_id: str) -> None:
    result = run_beads(
        [
            "dep",
            action_id,
            "--blocks",
            watch_id,
        ]
    )
    if result.ok:
        return
    if re.search(
        r"already[\s_-]+exists|duplicate|conflict",
        result.stderr + "\n" + result.stdout,
        flags=re.IGNORECASE,
    ):
        return
    raise beads_error(result, "dependency", atomic_conflict=False)


def action_metadata(
    watch_id: str,
    identity: dict[str, Any],
    generation: int,
    action_kind: str,
    fingerprint: str,
    head_sha: str,
    action_id: str,
) -> dict[str, str]:
    return {
        "record_kind": "action",
        "provenance_version": "pr-repair-v1",
        "action_id": action_id,
        "watch_id": watch_id,
        "rig": identity["rig"],
        "rig_prefix": identity["rig_prefix"],
        "github_host": identity.get("github_host", ""),
        "owner": identity.get("owner", ""),
        "repository": identity.get("repository", ""),
        "pr_number": str(identity.get("pr_number", "")),
        "url": identity.get("url", ""),
        "base_ref": identity.get("base_ref", ""),
        "head_ref": identity.get("head_ref", ""),
        "head_repository": identity.get("head_repository", ""),
        "head_sha": head_sha,
        "observed_head_sha": head_sha,
        "posture": "target",
        "target_posture": "target",
        "generation": str(generation),
        "action_kind": action_kind,
        "action_fingerprint": fingerprint,
        "attempt_key": action_attempt_key(action_kind, fingerprint, head_sha),
        "attempt_limit": str(action_attempt_limit(action_kind)),
        "claim_status": "claimed",
        "attempts": "1",
        "expected_old_head": head_sha,
        "expected_new_head": "",
        "expected_old_sha": head_sha,
        "expected_new_sha": "",
        "pushed_sha": "",
        "last_pushed_sha": "",
        "validation_status": "",
        "make_check_result": "",
        "addressed_thread_ids": "",
        "candidate_head_sha": "",
        "review_verdict": "",
        "review_verdict_action_id": "",
        "review_verdict_generation": "",
        "review_verdict_head_sha": "",
        "formula_attached": "false",
        "formula_root": "",
        "blocker_emitted": "false",
        "worktree_provenance": "",
        "worktree_head_sha": "",
        "worktree_head_ref": "",
        "worktree_base_ref": "",
        "worktree_generation": "",
        "worktree_action_id": "",
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
        "provenance_version",
        "action_id",
        "watch_id",
        "generation",
        "rig",
        "rig_prefix",
        "github_host",
        "owner",
        "repository",
        "pr_number",
        "url",
        "base_ref",
        "head_ref",
        "head_repository",
        "head_sha",
        "observed_head_sha",
        "posture",
        "target_posture",
        "action_kind",
        "action_fingerprint",
        "attempt_key",
        "attempt_limit",
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
        ensure_action_blocks_watch(action_id, watch_id)
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
            "--metadata",
            canonical_json(metadata),
            "--silent",
            "--json",
        ]
    )
    if not result.ok:
        raise beads_error(result, "action create", atomic_conflict=False)
    require_beads(result, "action create")
    parent_result = run_beads(
        [
            "update",
            action_id,
            "--parent",
            watch_id,
            "--json",
        ]
    )
    require_beads(parent_result, "action parent")
    issue, current_metadata = show_issue(action_id)
    validate_action_identity(current_metadata)
    ensure_action_blocks_watch(action_id, watch_id)
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
    attempt_key: str = "",
    attempts: int = 0,
    attempt_limit: str = "",
    attempt_history: str = "",
) -> dict[str, str]:
    updates = {
        "state": state,
        "generation": str(generation),
        "head_sha": head_sha,
        "observed_head_sha": head_sha,
        "last_snapshot_at": observed_at,
        "next_snapshot_at": next_snapshot_at,
        "wake_lease_until": "",
        "active_since": active_since,
        "action_kind": "",
        "action_fingerprint": "",
        "action_id": "",
        "attempt_key": attempt_key,
        "attempt_limit": attempt_limit,
        "attempt_history": attempt_history,
        "claim_status": "none",
        "attempts": str(attempts),
        "expected_old_head": "",
        "expected_new_head": "",
        "expected_old_sha": "",
        "expected_new_sha": "",
        "pushed_sha": "",
        "last_pushed_sha": last_pushed_sha,
        "validation_status": "",
        "make_check_result": "",
        "addressed_thread_ids": "",
        "pending_disposition_action_kind": "",
        "pending_disposition_ids": "",
        "pending_disposition_head_sha": "",
        "pending_disposition_generation": "",
        "formula_attached": "false",
        "formula_root": "",
        "blocker_emitted": "false",
        "terminal_reason": terminal_reason,
    }
    if backstop_at is not None:
        updates["backstop_at"] = backstop_at
    return updates


def remove_dependency(blocked_id: str, blocker_id: str) -> None:
    validate_bead_id(blocked_id, "blocked_id")
    validate_bead_id(blocker_id, "blocker_id")
    result = run_beads(
        [
            "dep",
            "remove",
            blocked_id,
            blocker_id,
            "--json",
        ]
    )
    if result.ok:
        return
    if re.search(
        r"not\s+found|no\s+dependency|does\s+not\s+exist|already\s+removed",
        result.stderr + "\n" + result.stdout,
        flags=re.IGNORECASE,
    ):
        return
    raise beads_error(result, "dependency removal", atomic_conflict=False)


def remove_action_blocks_watch(action_id: str, watch_id: str) -> None:
    remove_dependency(watch_id, action_id)


def formula_root_issue(root_id: str) -> dict[str, Any] | None:
    root_id = validate_bead_id(root_id, "formula_root")
    try:
        result = run_beads(["show", root_id, "--json"])
        payload = require_beads(result, "formula root show")
    except StateError as error:
        if error.code == "beads-not-found":
            return None
        raise
    issue = issue_from_payload(payload)
    if issue.get("id") != root_id:
        fail("Beads returned a different formula root ID", "beads-invalid-response")
    return issue


def ensure_rearm_formula_roots_clear(
    watch_id: str,
    watch_metadata: dict[str, str] | None = None,
) -> None:
    roots = set()
    if watch_metadata is not None and watch_metadata.get("formula_root"):
        roots.add(watch_metadata["formula_root"])
    for issue, action_metadata_value in action_records_for_watch(watch_id):
        root_id = action_metadata_value.get("formula_root", "")
        if not root_id:
            continue
        roots.add(root_id)
    for root_id in roots:
        root_id = validate_bead_id(root_id, "formula_root")
        root_issue = formula_root_issue(root_id)
        if root_issue is not None and root_issue.get("status") != "closed":
            try:
                metadata_updates(
                    watch_id,
                    {
                        "state": "blocked",
                        "claim_status": "blocked",
                        "terminal_reason": "formula-root-active",
                        "blocker_emitted": "true",
                    },
                    status="blocked",
                    assignee="",
                )
            except StateError:
                pass
            fail(
                "cannot rearm while the repair formula root is open",
                "formula-root-active",
            )


def clean_rearm_dependencies(watch_id: str) -> None:
    for issue, action_metadata_value in action_records_for_watch(watch_id):
        action_id = validate_bead_id(issue["id"], "action_id")
        root_id = action_metadata_value.get("formula_root", "")
        if root_id:
            root_id = validate_bead_id(root_id, "formula_root")
            root_issue = formula_root_issue(root_id)
            if root_issue is None or root_issue.get("status") == "closed":
                remove_dependency(action_id, root_id)
        remove_action_blocks_watch(action_id, watch_id)


def _merge_ready_evidence(
    payload: dict[str, Any],
    *,
    expected_head: str,
    observed_head: str | None = None,
) -> dict[str, Any]:
    raw = payload_value(
        payload,
        "merge_ready_evidence",
        "readiness_evidence",
        "snapshot_readiness",
        "readiness",
        "current_snapshot_evidence",
        "merge_ready_snapshot",
        "merge_ready",
        "current_snapshot",
        "snapshot",
    )
    if raw is None:
        evidence_keys = {
            "current_head_sha",
            "current_head",
            "head_sha",
            "observed_head_sha",
            "snapshot_head_sha",
            "mergeability_certain",
            "mergeable_certain",
            "mergeability",
            "mergeable",
            "mergeability_status",
            "branch_clean",
            "clean_branch",
            "branch",
            "branch_state",
            "merge_state_status",
            "required_checks_terminal",
            "checks_terminal",
            "required_checks_successful",
            "checks_successful",
            "all_checks_ok",
            "required_checks",
            "no_actionable_feedback",
            "actionable_feedback",
            "actionable",
            "counts",
            "no_pending_human_interaction",
            "pending_human_interaction",
            "human_interaction",
            "no_currency_item",
            "currency_item",
            "currency",
            "branch_currency",
            "quiet_window_satisfied",
            "quiet_window",
            "quiet_seconds",
        }
        if evidence_keys & set(payload):
            raw = payload
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            fail(
                "merge-ready evidence must be a JSON object",
                "merge-readiness-invalid",
            )
    if not isinstance(raw, dict):
        fail(
            "merge-ready evidence is required",
            "merge-readiness-required",
        )
    raw = dict(raw)
    nested_snapshot = raw.get("snapshot") or raw.get("current_snapshot")
    if isinstance(nested_snapshot, dict):
        merged_snapshot = dict(nested_snapshot)
        merged_snapshot.update(
            {
                key: value
                for key, value in raw.items()
                if key not in {"snapshot", "current_snapshot"}
            }
        )
        raw = merged_snapshot
    for name in ("current_head", "current"):
        nested = raw.get(name)
        if "current_head_sha" not in raw:
            if isinstance(nested, dict):
                nested_head = (
                    nested.get("sha")
                    or nested.get("head_sha")
                    or nested.get("current_head_sha")
                )
                if nested_head is not None:
                    raw["current_head_sha"] = nested_head
            elif isinstance(nested, str):
                raw["current_head_sha"] = nested
    if "current_head_sha" not in raw:
        current_head_value = (
            raw.get("observed_head_sha") or raw.get("snapshot_head_sha")
        )
        if current_head_value is not None:
            raw["current_head_sha"] = current_head_value
    if "mergeability_certain" not in raw and "mergeable_certain" not in raw:
        mergeability = raw.get(
            "mergeability",
            raw.get("mergeable", raw.get("mergeability_status")),
        )
        if isinstance(mergeability, dict):
            mergeability = mergeability.get(
                "certain",
                mergeability.get("status"),
            )
        if isinstance(mergeability, bool):
            raw["mergeability_certain"] = mergeability
        elif isinstance(mergeability, str):
            raw["mergeability_certain"] = mergeability.strip().upper() in {
                "CERTAIN",
                "MERGEABLE",
            }
    if "branch_clean" not in raw and "clean_branch" not in raw:
        branch = raw.get("branch", raw.get("branch_state"))
        if isinstance(branch, bool):
            raw["branch_clean"] = branch
        elif isinstance(branch, str):
            raw["branch_clean"] = branch.strip().lower() == "clean"
    if "branch_clean" not in raw and "clean_branch" not in raw:
        merge_state_status = raw.get("merge_state_status")
        if isinstance(merge_state_status, str):
            raw["branch_clean"] = (
                merge_state_status.strip().upper() == "CLEAN"
            )
    merge_state_status = raw.get("merge_state_status")
    if (
        isinstance(merge_state_status, str)
        and merge_state_status.strip().upper() != "CLEAN"
    ):
        fail(
            "merge-ready evidence reports a non-clean branch",
            "merge-readiness-invalid",
        )
    mergeable = raw.get("mergeable")
    if (
        isinstance(mergeable, str)
        and mergeable.strip().upper() != "MERGEABLE"
    ):
        fail(
            "merge-ready evidence reports a non-mergeable pull request",
            "merge-readiness-invalid",
        )
    base = raw.get("base")
    if isinstance(base, dict) and base.get("identity") != "current":
        fail(
            "merge-ready evidence reports a stale base",
            "merge-readiness-invalid",
        )
    if raw.get("identity_blocker") not in (None, ""):
        fail(
            "merge-ready evidence reports an identity blocker",
            "merge-readiness-invalid",
        )
    if "branch_currency" in raw and raw.get("branch_currency") is not None:
        fail(
            "merge-ready evidence reports a currency item",
            "merge-readiness-invalid",
        )
    required_checks = raw.get("required_checks")
    if isinstance(required_checks, dict):
        if "required_checks_terminal" not in raw:
            raw["required_checks_terminal"] = required_checks.get(
                "terminal",
                required_checks.get("checks_terminal"),
            )
        if "required_checks_successful" not in raw:
            raw["required_checks_successful"] = required_checks.get(
                "successful",
                required_checks.get("success", required_checks.get("ok")),
            )
    elif isinstance(required_checks, list) and required_checks:
        statuses = [
            item.get("status")
            for item in required_checks
            if isinstance(item, dict)
        ]
        conclusions = [
            str(item.get("conclusion") or "").upper()
            for item in required_checks
            if isinstance(item, dict)
        ]
        raw.setdefault(
            "required_checks_terminal",
            all(status == "COMPLETED" for status in statuses)
            and len(statuses) == len(required_checks),
        )
        raw.setdefault(
            "required_checks_successful",
            all(
                conclusion in {"SUCCESS", "NEUTRAL", "SKIPPED"}
                for conclusion in conclusions
            )
            and len(conclusions) == len(required_checks),
        )
    checks = raw.get("checks")
    if isinstance(checks, list) and checks:
        statuses = [
            item.get("status")
            for item in checks
            if isinstance(item, dict)
        ]
        conclusions = [
            str(item.get("conclusion") or "").upper()
            for item in checks
            if isinstance(item, dict)
        ]
        raw.setdefault(
            "required_checks_terminal",
            all(status == "COMPLETED" for status in statuses)
            and len(statuses) == len(checks),
        )
        raw.setdefault(
            "required_checks_successful",
            all(
                conclusion in {"SUCCESS", "NEUTRAL", "SKIPPED"}
                for conclusion in conclusions
            )
            and len(conclusions) == len(checks),
        )
    for nested_name, nested_key, output_key in (
        ("feedback", "actionable", "actionable_feedback"),
        ("human_interaction", "pending", "pending_human_interaction"),
        ("currency", "item", "currency_item"),
    ):
        nested = raw.get(nested_name)
        if isinstance(nested, dict) and nested_key in nested:
            raw[output_key] = nested[nested_key]
    counts = raw.get("counts")
    if isinstance(counts, dict):
        if "actionable_feedback" not in raw:
            raw["actionable_feedback"] = bool(
                counts.get("threads", 0) or counts.get("comments", 0)
            )
        if "pending_human_interaction" not in raw:
            raw["pending_human_interaction"] = bool(
                counts.get("needs_human", 0)
            )
    if "actionable_feedback" not in raw and isinstance(
        raw.get("actionable"),
        dict,
    ):
        actionable = raw["actionable"]
        raw["actionable_feedback"] = bool(
            actionable.get("threads") or actionable.get("comments")
        )
    if (
        "pending_human_interaction" not in raw
        and (
            "review_in_progress" in raw
            or "needs_human_residuals" in raw
        )
    ):
        raw["pending_human_interaction"] = bool(
            raw.get("review_in_progress", False)
            or raw.get("needs_human_residuals")
        )
    if "currency_item" not in raw and "branch_currency" in raw:
        raw["currency_item"] = raw.get("branch_currency") is not None
    quiet_window = raw.get("quiet_window")
    if isinstance(quiet_window, dict):
        raw["quiet_window"] = quiet_window.get("satisfied")
    elif "quiet_window_satisfied" not in raw:
        quiet_seconds = raw.get("quiet_seconds")
        if isinstance(quiet_seconds, (int, float)) and not isinstance(
            quiet_seconds,
            bool,
        ):
            raw["quiet_window_satisfied"] = quiet_seconds >= 300
    if (
        isinstance(raw.get("quiet_seconds"), (int, float))
        and not isinstance(raw.get("quiet_seconds"), bool)
        and raw["quiet_seconds"] < 300
    ):
        fail(
            "merge-ready evidence does not satisfy the quiet window",
            "merge-readiness-invalid",
        )

    def value_for(names: tuple[str, ...], field: str) -> Any:
        present = [raw[name] for name in names if name in raw]
        if not present:
            fail(
                f"merge-ready evidence is missing {field}",
                "merge-readiness-required",
            )
        if len(set(map(repr, present))) != 1:
            fail(
                f"merge-ready evidence disagrees for {field}",
                "merge-readiness-invalid",
            )
        return present[0]

    current_head = sha_value(
        value_for(
            ("current_head_sha", "head_sha"),
            "current_head_sha",
        ),
        "merge_ready_evidence.current_head_sha",
    )
    required_head = observed_head or expected_head
    if current_head != required_head:
        fail(
            "merge-ready evidence is not for the current head",
            "merge-readiness-stale",
        )

    def require_true(names: tuple[str, ...], field: str) -> None:
        value = value_for(names, field)
        if not isinstance(value, bool) or not value:
            fail(
                f"merge-ready evidence requires {field}=true",
                "merge-readiness-invalid",
            )

    def require_clear(
        positive_names: tuple[str, ...],
        negative_names: tuple[str, ...],
        field: str,
    ) -> None:
        present = False
        for name in positive_names:
            if name in raw:
                present = True
                if raw[name] is not True:
                    fail(
                        f"merge-ready evidence requires {field}=true",
                        "merge-readiness-invalid",
                    )
        for name in negative_names:
            if name in raw:
                present = True
                if raw[name] is not False:
                    fail(
                        f"merge-ready evidence requires {field}=true",
                        "merge-readiness-invalid",
                    )
        if not present:
            fail(
                f"merge-ready evidence is missing {field}",
                "merge-readiness-required",
            )

    require_true(
        ("mergeability_certain", "mergeable_certain"),
        "mergeability_certain",
    )
    require_true(("branch_clean", "clean_branch"), "branch_clean")
    require_true(
        ("required_checks_terminal", "checks_terminal"),
        "required_checks_terminal",
    )
    require_true(
        ("required_checks_successful", "checks_successful", "all_checks_ok"),
        "required_checks_successful",
    )
    require_clear(
        ("no_actionable_feedback",),
        ("actionable_feedback",),
        "no_actionable_feedback",
    )
    require_clear(
        ("no_pending_human_interaction",),
        ("pending_human_interaction",),
        "no_pending_human_interaction",
    )
    require_clear(
        ("no_currency_item",),
        ("currency_item",),
        "no_currency_item",
    )
    require_true(
        ("quiet_window_satisfied", "quiet_window"),
        "quiet_window_satisfied",
    )
    return {
        "current_head_sha": current_head,
        "mergeability_certain": True,
        "branch_clean": True,
        "required_checks_terminal": True,
        "required_checks_successful": True,
        "no_actionable_feedback": True,
        "no_pending_human_interaction": True,
        "no_currency_item": True,
        "quiet_window_satisfied": True,
    }


def invalidate_action_record(
    watch_id: str,
    action_id: str,
    metadata: dict[str, str],
    reason: str,
) -> None:
    if metadata.get("watch_id") != watch_id:
        fail("stale action does not belong to watch", "identity-mismatch")
    claim_status = metadata.get("claim_status", "")
    if claim_status not in ACTION_CLEANUP_STATUSES:
        return
    issue, _ = show_bead(action_id, operation="stale action show")
    if issue.get("status") != "closed":
        try:
            metadata_updates(
                action_id,
                {
                    "claim_status": "stale",
                    "terminal_reason": reason,
                },
                status="blocked",
                assignee="",
            )
        except StateError:
            # A concurrently completed action is already safe to detach.
            if issue.get("status") != "closed":
                raise
        try:
            close_action(action_id, "stale")
        except StateError:
            # Native dependency closure can refuse an action with its own
            # open children. Removing this action's edge is sufficient before
            # the watch is cleared or rearmed.
            remove_action_blocks_watch(action_id, watch_id)
    else:
        try:
            metadata_updates(
                action_id,
                {
                    "claim_status": "stale",
                    "terminal_reason": reason,
                },
            )
        except StateError:
            pass


def invalidate_action_claim(
    watch_id: str,
    metadata: dict[str, str],
    reason: str,
) -> None:
    candidates: dict[str, tuple[dict[str, Any], dict[str, str]]] = {}
    action_id = metadata.get("action_id", "")
    if action_id:
        action_id = validate_bead_id(action_id, "action_id")
        existing = show_issue_if_present(action_id, operation="stale action show")
        if existing is not None:
            candidates[action_id] = existing

    for issue, action_metadata_value in action_records_for_watch(watch_id):
        candidate_id = validate_bead_id(issue["id"], "action_id")
        candidates[candidate_id] = (issue, action_metadata_value)

    for candidate_id, (_, action_metadata_value) in candidates.items():
        invalidate_action_record(
            watch_id,
            candidate_id,
            action_metadata_value,
            reason,
        )


def block_claim_setup_failure(
    watch_id: str,
    action_id: str,
    prior_metadata: dict[str, str],
) -> None:
    action_updates = {
        "claim_status": "blocked",
        "blocker_emitted": "true",
        "terminal_reason": "claim-setup-failed",
    }
    try:
        existing = show_issue_if_present(
            action_id,
            operation="claim setup action show",
        )
        if (
            existing is not None
            and existing[0].get("status") != "closed"
            and existing[1].get("watch_id") == watch_id
        ):
            metadata_updates(
                action_id,
                action_updates,
                status="blocked",
                assignee="",
            )
    except StateError:
        pass

    watch_updates = {
        "state": "blocked",
        "generation": prior_metadata.get("generation", ""),
        "head_sha": prior_metadata.get("head_sha", ""),
        "observed_head_sha": prior_metadata.get(
            "observed_head_sha",
            prior_metadata.get("head_sha", ""),
        ),
        "last_snapshot_at": prior_metadata.get("last_snapshot_at", ""),
        "next_snapshot_at": prior_metadata.get("next_snapshot_at", ""),
        "wake_lease_until": "",
        "active_since": prior_metadata.get("active_since", ""),
        "backstop_at": prior_metadata.get("backstop_at", ""),
        "action_kind": "",
        "action_fingerprint": "",
        "action_id": "",
        "attempt_key": prior_metadata.get("attempt_key", ""),
        "attempt_limit": prior_metadata.get("attempt_limit", ""),
        "attempt_history": prior_metadata.get("attempt_history", ""),
        "attempts": prior_metadata.get("attempts", "0"),
        "claim_status": "blocked",
        "expected_old_head": "",
        "expected_new_head": "",
        "expected_old_sha": "",
        "expected_new_sha": "",
        "pushed_sha": "",
        "validation_status": "",
        "make_check_result": "",
        "addressed_thread_ids": "",
        "pending_disposition_action_kind": "",
        "pending_disposition_ids": "",
        "pending_disposition_head_sha": "",
        "pending_disposition_generation": "",
        "formula_attached": "false",
        "formula_root": "",
        "blocker_emitted": "true",
        "terminal_reason": "claim-setup-failed",
    }
    try:
        metadata_updates(
            watch_id,
            watch_updates,
            status="blocked",
            assignee="",
        )
    except StateError:
        pass


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
    *,
    preserve_budget: bool = False,
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
    should_rearm = current_state in REARMABLE_STATES and rearm
    if should_rearm:
        ensure_rearm_formula_roots_clear(watch_id, metadata)
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
    parse_time(observed_at, "observed_at")
    parse_time(next_snapshot_at, "next_snapshot_at")
    reset_budget = should_rearm and not preserve_budget
    if not created and not reset_budget:
        active_since = text_value(
            metadata.get("active_since", ""),
            "active_since",
        )
        if not active_since:
            fail("existing watch is missing active_since", "corrupt-state")
    if reset_budget:
        active_since = observed_at
    active_since_time = parse_time(active_since, "active_since")
    supplied_backstop = payload_value(payload, "backstop_at")
    if reset_budget:
        backstop_at = text_value(
            supplied_backstop or "",
            "backstop_at",
            required=False,
        )
        if backstop_at:
            backstop_time = parse_time(backstop_at, "backstop_at")
            if backstop_time < active_since_time:
                fail("backstop_at must not precede active_since")
        else:
            backstop_at = format_time(active_since_time + BACKSTOP_BUDGET)
    else:
        backstop_at = text_value(
            metadata.get("backstop_at", "")
            if not created or supplied_backstop is None
            else supplied_backstop,
            "backstop_at",
            required=False,
        )
        if not backstop_at:
            backstop_at = format_time(active_since_time + BACKSTOP_BUDGET)
        if backstop_at:
            parse_time(backstop_at, "backstop_at")
    head_changed = current_head != incoming_head
    pending_dispositions = pending_disposition_details(metadata)
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
            attempt_key=metadata.get("attempt_key", ""),
            attempts=attempts_from_metadata(metadata),
            attempt_limit=metadata.get("attempt_limit", ""),
            attempt_history=metadata.get("attempt_history", ""),
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
        if should_rearm:
            clean_rearm_dependencies(watch_id)
        next_generation = generation + 1
        updates = clear_claim_updates(
            "watching",
            next_generation,
            head_sha=incoming_head,
            observed_at=observed_at,
            next_snapshot_at=next_snapshot_at,
            active_since=(
                metadata.get("active_since", active_since)
                if not reset_budget
                else active_since
            ),
            last_pushed_sha=metadata.get("last_pushed_sha", ""),
            backstop_at=backstop_at,
            attempt_key="" if reset_budget else metadata.get("attempt_key", ""),
            attempts=0 if reset_budget else attempts_from_metadata(metadata),
            attempt_limit="" if reset_budget else metadata.get("attempt_limit", ""),
            attempt_history=(
                ""
                if reset_budget
                else metadata.get("attempt_history", "")
            ),
        )
        if pending_dispositions is not None and not should_rearm:
            pending_kind, pending_ids, _, _ = pending_dispositions
            updates.update(
                {
                    "action_kind": pending_kind,
                    "addressed_thread_ids": pending_ids,
                    "pending_disposition_action_kind": pending_kind,
                    "pending_disposition_ids": pending_ids,
                    "pending_disposition_head_sha": incoming_head,
                    "pending_disposition_generation": str(next_generation),
                }
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

    recorded_bases = [
        metadata.get(field, "")
        for field in ("base_ref", "target", "target_branch")
        if metadata.get(field, "")
    ]
    if not recorded_bases:
        fail(
            "publication bead is missing persisted target metadata",
            "identity-mismatch",
        )
    normalized_bases = {
        validate_git_ref(value, "base_ref")
        for value in recorded_bases
    }
    if len(normalized_bases) != 1 or expected_rig["base_ref"] not in normalized_bases:
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


def github_repository_identity(
    value: Any,
    field: str,
    *,
    require_name_with_owner: bool = False,
) -> str:
    if require_name_with_owner and not isinstance(value, dict):
        fail(
            f"GitHub response {field} identity is malformed",
            "github-invalid-response",
        )
    if isinstance(value, dict):
        if require_name_with_owner:
            name_with_owner = value.get("nameWithOwner")
        else:
            name_with_owner = (
                value.get("nameWithOwner")
                or value.get("name_with_owner")
                or value.get("fullName")
                or value.get("full_name")
            )
        if name_with_owner is None and not require_name_with_owner:
            owner_value = value.get("owner")
            if isinstance(owner_value, dict):
                owner_value = owner_value.get("login") or owner_value.get("name")
            name_value = value.get("name")
            if owner_value and name_value:
                name_with_owner = f"{owner_value}/{name_value}"
        value = name_with_owner
    if value is None:
        fail(
            f"GitHub response is missing {field} identity",
            "github-invalid-response",
        )
    try:
        return repository_name_with_owner(value, field)
    except StateError:
        fail(
            f"GitHub response {field} identity is malformed",
            "github-invalid-response",
        )


def github_repository_owner(value: Any, field: str) -> str:
    if isinstance(value, dict):
        value = value.get("login") or value.get("name")
    if value is None or not isinstance(value, str):
        fail(
            f"GitHub response is missing {field} owner",
            "github-invalid-response",
        )
    try:
        return safe_slug(value, f"{field}_owner").lower()
    except StateError:
        fail(
            f"GitHub response {field} owner is malformed",
            "github-invalid-response",
        )


def github_publication_command(context: dict[str, Any]) -> list[str]:
    number = context.get("pr_number")
    if number is None:
        fail("a pull-request number is required", "identity-mismatch")
    repo = f'{context["owner"]}/{context["repository"]}'
    return gh_command() + [
        "pr",
        "view",
        str(number),
        "--repo",
        repo,
        "--json",
        GITHUB_PUBLICATION_FIELDS,
    ]


def query_github_publication(context: dict[str, Any]) -> dict[str, Any]:
    number = context.get("pr_number")
    if number is None:
        fail("a pull-request number is required", "identity-mismatch")
    command = github_publication_command(context)
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
            timeout=GITHUB_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        fail("GitHub pull-request query timed out", "github-query")
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

    cross_value = raw.get("isCrossRepository", raw.get("cross_repository"))
    if cross_value is None:
        fail(
            "GitHub response is missing cross-repository status",
            "github-invalid-response",
        )
    try:
        cross_repository = bool_value(cross_value, "isCrossRepository")
    except StateError:
        fail(
            "GitHub response cross-repository status is malformed",
            "github-invalid-response",
        )
    head_repository = github_repository_identity(
        raw.get("headRepository", raw.get("head_repository")),
        "headRepository",
        require_name_with_owner=True,
    )
    head_repository_owner = github_repository_owner(
        raw.get("headRepositoryOwner", raw.get("head_repository_owner")),
        "headRepositoryOwner",
    )
    expected_repository = f"{context['owner']}/{context['repository']}"
    if (
        cross_repository
        or head_repository != expected_repository
        or head_repository_owner != context["owner"]
    ):
        fail(
            "cross-repository pull-request heads are not supported",
            "cross-repository-head",
        )

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
        "head_repository": head_repository,
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
    *,
    route_status: str = "complete",
    verified: bool | None = None,
) -> dict[str, str]:
    if route_status not in HANDOFF_ROUTE_STATUSES:
        fail("handoff route status is unsupported", "invalid-request")
    if verified is None:
        verified = route_status == "complete"
    return {
        "handoff_verified": "true" if verified else "false",
        "handoff_watch_id": watch_id,
        "handoff_target": target,
        "handoff_publication_bead": publication_bead_id,
        "handoff_route_status": route_status,
    }


def route_timeout_seconds() -> int:
    value = os.environ.get("PR_BABYSIT_ROUTE_TIMEOUT_SECONDS")
    if value is None:
        return ROUTE_TIMEOUT_SECONDS
    if not re.fullmatch(r"[1-9][0-9]*", value):
        fail(
            "PR_BABYSIT_ROUTE_TIMEOUT_SECONDS must be between 1 and 29",
            "configuration",
        )
    timeout = int(value)
    if timeout >= ORDER_TIMEOUT_SECONDS:
        fail(
            "PR_BABYSIT_ROUTE_TIMEOUT_SECONDS must be between 1 and 29",
            "configuration",
        )
    return timeout


def existing_receipt_matches(
    metadata: dict[str, str],
    receipt: dict[str, str],
) -> None:
    receipt_keys = {
        "handoff_watch_id",
        "handoff_target",
        "handoff_publication_bead",
    }
    present = receipt_keys & set(metadata)
    if not present:
        return
    for key in receipt_keys:
        value = receipt[key]
        if key in metadata and metadata.get(key) != value:
            fail(
                "existing handoff receipt does not match",
                "identity-mismatch",
            )
    if (
        "handoff_route_status" in metadata
        and metadata["handoff_route_status"] not in HANDOFF_ROUTE_STATUSES
    ):
        fail(
            "existing handoff receipt has an invalid route status",
            "corrupt-state",
        )
    if (
        "handoff_wake_status" in metadata
        and metadata["handoff_wake_status"] not in HANDOFF_WAKE_STATUSES
    ):
        fail(
            "existing handoff receipt has an invalid wake status",
            "corrupt-state",
        )
    if (
        "handoff_verified" in metadata
        and metadata["handoff_verified"] not in {"true", "false"}
    ):
        fail(
            "existing handoff receipt has an invalid verification flag",
            "corrupt-state",
        )


def has_complete_receipt(
    metadata: dict[str, str],
    receipt: dict[str, str],
) -> bool:
    watch_id = receipt.get("handoff_watch_id", "")
    target = receipt.get("handoff_target", "")
    publication_bead_id = receipt.get("handoff_publication_bead", "")
    route_status = metadata.get("handoff_route_status", "")
    wake_status = metadata.get("handoff_wake_status", "")
    if route_status != "complete":
        return False
    if wake_status != "delivered":
        return False
    return (
        metadata.get("handoff_verified") == "true"
        and bool(watch_id)
        and metadata.get("handoff_watch_id") == watch_id
        and bool(target)
        and target == metadata.get("handoff_target")
        and bool(publication_bead_id)
        and metadata.get("handoff_publication_bead") == publication_bead_id
    )


def require_complete_receipt(
    metadata: dict[str, str],
    watch_id: str,
    target: str,
    publication_bead_id: str,
) -> None:
    receipt = receipt_updates(
        publication_bead_id,
        watch_id,
        target,
    )
    route_status = metadata.get("handoff_route_status", "")
    if route_status == "route-failed":
        fail(
            "publication handoff route previously failed",
            "route-failed",
        )
    if route_status == "pending":
        fail(
            "publication handoff receipt is pending",
            "not-routable",
        )
    if not has_complete_receipt(metadata, receipt):
        fail(
            "publication handoff receipt is missing",
            "not-routable",
        )


def watch_receipt_is_complete(
    metadata: dict[str, str],
    watch_id: str,
) -> bool:
    publication_bead_id = metadata.get("handoff_publication_bead", "")
    rig = metadata.get("rig", "")
    if not publication_bead_id or rig not in RIGS:
        return False
    return has_complete_receipt(
        metadata,
        receipt_updates(
            publication_bead_id,
            watch_id,
            handoff_target(rig),
        ),
    )


def require_watch_receipt(
    metadata: dict[str, str],
    watch_id: str,
) -> None:
    rig = metadata.get("rig", "")
    publication_bead_id = metadata.get("handoff_publication_bead", "")
    if rig not in RIGS or not publication_bead_id:
        fail(
            "watch has no complete publication handoff receipt",
            "not-routable",
        )
    require_complete_receipt(
        metadata,
        watch_id,
        handoff_target(rig),
        publication_bead_id,
    )


def block_route_failure(
    watch_id: str,
    publication_bead_id: str | None = None,
    target: str | None = None,
) -> None:
    _, metadata = show_issue(watch_id)
    state = state_from_metadata(metadata)
    updates = {
        "handoff_route_status": "route-failed",
        "handoff_verified": "false",
        "handoff_wake_status": "failed",
    }
    if publication_bead_id and target:
        updates.update(
            receipt_updates(
                publication_bead_id,
                watch_id,
                target,
                route_status="route-failed",
                verified=False,
            )
        )
    if state not in {"terminal", "exhausted", "merge-ready"}:
        updates.update(
            {
                "state": "blocked",
                "claim_status": "blocked",
                "terminal_reason": "route-failed",
                "blocker_emitted": "true",
            }
        )
        metadata_updates(
            watch_id,
            updates,
            status="blocked",
            assignee="",
        )
    else:
        metadata_updates(watch_id, updates)
    if publication_bead_id:
        try:
            metadata_updates(
                publication_bead_id,
                receipt_updates(
                    publication_bead_id,
                    watch_id,
                    target or metadata.get("handoff_target", ""),
                    route_status="route-failed",
                    verified=False,
                ),
            )
        except StateError:
            pass


def route_watch(target: str, watch_id: str, *, wake: bool = True) -> None:
    command = gc_command() + ["sling"]
    if wake:
        command.append("--nudge")
    command.extend(
        [
            target,
            watch_id,
            "--no-formula",
            "--json",
        ]
    )
    try:
        result = subprocess.run(
            command,
            cwd=beads_cwd(),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
            timeout=route_timeout_seconds(),
        )
    except subprocess.TimeoutExpired:
        fail("Gas City babysitter route timed out", "route-failed")
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
    rearm = bool_value(
        payload_value(payload, "rearm", "allow_rearm"),
        "rearm",
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
    complete_receipt = receipt_updates(
        publication_bead_id,
        watch_id,
        target,
    )
    existing_receipt_matches(publication_metadata, complete_receipt)

    handoff_payload = {
        **identity,
        "verified": True,
        "rearm": rearm,
        "observed_at": payload_value(payload, "observed_at") or iso_now(),
        "next_snapshot_at": payload_value(payload, "next_snapshot_at")
        or payload_value(payload, "observed_at")
        or iso_now(),
        "active_since": payload_value(payload, "active_since")
        or payload_value(payload, "observed_at")
        or iso_now(),
    }
    if payload_value(payload, "backstop_at") is not None:
        handoff_payload["backstop_at"] = payload_value(
            payload,
            "backstop_at",
        )
    initial = initial_watch_metadata(identity, handoff_payload)
    route_failed_rearm = False
    with watch_lock(watch_id):
        _, publication_metadata = show_bead(publication_bead_id)
        existing_receipt_matches(publication_metadata, complete_receipt)
        existing_watch = show_issue_if_present(watch_id)
        if existing_watch is not None:
            _, existing_watch_metadata = existing_watch
            immutable_matches(existing_watch_metadata, identity)
            existing_receipt_matches(
                existing_watch_metadata,
                complete_receipt,
            )
            if (
                not rearm
                and publication_metadata.get("handoff_route_status")
                == "complete"
                and publication_metadata.get("handoff_wake_status") == "ready"
                and existing_watch_metadata.get("handoff_route_status")
                == "complete"
                and existing_watch_metadata.get("handoff_wake_status") == "ready"
                and existing_watch_metadata.get("head_sha")
                == identity["head_sha"]
            ):
                try:
                    route_watch(target, watch_id, wake=True)
                except StateError as error:
                    if error.code in {"route-failed", "route-exec"}:
                        block_route_failure(
                            watch_id,
                            publication_bead_id,
                            target,
                        )
                    raise
                try:
                    metadata_updates(
                        watch_id,
                        {"handoff_wake_status": "delivered"},
                    )
                    metadata_updates(
                        publication_bead_id,
                        {"handoff_wake_status": "delivered"},
                    )
                except StateError:
                    block_route_failure(
                        watch_id,
                        publication_bead_id,
                        target,
                    )
                    raise
                return {
                    "ok": True,
                    "action": "publication-handoff",
                    "rig": context["rig"],
                    "publication_bead_id": publication_bead_id,
                    "watch_id": watch_id,
                    "target": target,
                    "verified": True,
                    "created": False,
                    "reused": True,
                    "wake": True,
                }
            if (
                not rearm
                and has_complete_receipt(
                    publication_metadata,
                    complete_receipt,
                )
                and has_complete_receipt(
                    existing_watch_metadata,
                    complete_receipt,
                )
                and existing_watch_metadata.get(
                    "handoff_wake_status",
                    "",
                )
                == "delivered"
                and publication_metadata.get(
                    "handoff_wake_status",
                    "",
                )
                == "delivered"
                and existing_watch_metadata.get("head_sha")
                == identity["head_sha"]
            ):
                return {
                    "ok": True,
                    "action": "publication-handoff",
                    "rig": context["rig"],
                    "publication_bead_id": publication_bead_id,
                    "watch_id": watch_id,
                    "target": target,
                    "verified": True,
                    "created": False,
                    "reused": True,
                    "wake": False,
                }
            route_failed_rearm = (
                state_from_metadata(existing_watch_metadata) == "blocked"
                and existing_watch_metadata.get("terminal_reason") == "route-failed"
                and not has_complete_receipt(
                    existing_watch_metadata,
                    complete_receipt,
                )
            )
        handoff_payload["rearm"] = rearm or route_failed_rearm
        handoff_result = _handoff_locked(
            handoff_payload,
            identity,
            rearm or route_failed_rearm,
            watch_id,
            initial,
            preserve_budget=route_failed_rearm and not rearm,
        )
        pending_receipt = receipt_updates(
            publication_bead_id,
            watch_id,
            target,
            route_status="pending",
            verified=True,
        )
        pending_receipt["handoff_wake_status"] = "not-started"
        metadata_updates(watch_id, pending_receipt)
        try:
            metadata_updates(publication_bead_id, pending_receipt)
        except StateError:
            block_route_failure(
                watch_id,
                publication_bead_id,
                target,
            )
            raise
        try:
            route_watch(target, watch_id, wake=False)
        except StateError as error:
            if error.code in {"route-failed", "route-exec"}:
                block_route_failure(
                    watch_id,
                    publication_bead_id,
                    target,
                )
            raise

        ready_receipt = {
            **complete_receipt,
            "handoff_wake_status": "ready",
        }
        try:
            metadata_updates(watch_id, ready_receipt)
            metadata_updates(publication_bead_id, ready_receipt)
        except StateError:
            block_route_failure(
                watch_id,
                publication_bead_id,
                target,
            )
            raise

        try:
            route_watch(target, watch_id, wake=True)
        except StateError as error:
            if error.code in {"route-failed", "route-exec"}:
                block_route_failure(
                    watch_id,
                    publication_bead_id,
                    target,
                )
            raise

        try:
            metadata_updates(
                watch_id,
                {"handoff_wake_status": "delivered"},
            )
            metadata_updates(
                publication_bead_id,
                {"handoff_wake_status": "delivered"},
            )
        except StateError:
            block_route_failure(
                watch_id,
                publication_bead_id,
                target,
            )
            raise

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
            "wake": True,
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
        "head_repository",
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
    head_repository = repository_name_with_owner(
        metadata["head_repository"],
        "head_repository",
    )
    expected_repository = f"{context['owner']}/{context['repository']}"
    if head_repository != expected_repository:
        fail(
            "watch head repository does not match publication",
            "identity-mismatch",
        )
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
        "head_repository": head_repository,
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
    recorded_watch_id = publication_metadata.get("handoff_watch_id")
    if recorded_watch_id:
        watch_id = validate_watch_id(recorded_watch_id)
    else:
        if context.get("pr_number") is None:
            fail("publication handoff receipt is missing", "not-routable")
        watch_id = watch_id_for(
            {
                "rig": context["rig"],
                "rig_prefix": context["rig_prefix"],
                "github_host": context["github_host"],
                "owner": context["owner"],
                "repository": context["repository"],
                "pr_number": context["pr_number"],
            }
        )
    target = handoff_target(context["rig"])
    expected_receipt = receipt_updates(publication_bead_id, watch_id, target)
    existing_receipt_matches(publication_metadata, expected_receipt)
    _, watch_metadata = show_issue(watch_id)
    existing_receipt_matches(watch_metadata, expected_receipt)
    watch_state = state_from_metadata(watch_metadata)
    require_complete_receipt(
        publication_metadata,
        watch_id,
        target,
        publication_bead_id,
    )
    require_complete_receipt(
        watch_metadata,
        watch_id,
        target,
        publication_bead_id,
    )
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
    formula_attachment_state(metadata.get("formula_attached"))
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
    require_watch_receipt(metadata, watch_id)
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
    merge_ready_evidence = None
    if desired == "merge-ready":
        merge_ready_evidence = _merge_ready_evidence(
            payload,
            expected_head=metadata["head_sha"],
        )
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
    return metadata_response(
        "transition",
        watch_id,
        metadata,
        changed=True,
        merge_ready_evidence=merge_ready_evidence,
    )


def claim_action(payload: dict[str, Any]) -> dict[str, Any]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    with watch_lock(watch_id):
        return _claim_action_locked(payload, watch_id)


def _claim_action_locked(
    payload: dict[str, Any],
    watch_id: str,
) -> dict[str, Any]:
    action_kind = normalize_action_kind(
        payload_value(payload, "action_kind", "kind"),
    )
    fingerprint = normalize_fingerprint(payload_value(payload, "fingerprint"))
    attempt_limit = action_attempt_limit(action_kind)
    generation_raw = payload_value(payload, "generation")
    head_raw = payload_value(
        payload,
        "head_sha",
        "current_sha",
        "expected_old_sha",
        "expected_old_head",
    )
    expected_generation = integer_value(generation_raw, "generation")
    head_sha = sha_value(head_raw, "head_sha")
    attempt_key = action_attempt_key(action_kind, fingerprint, head_sha)
    _, metadata = show_issue(watch_id)
    if metadata.get("record_kind") != "watch":
        fail("requested Beads record is not a watch", "identity-mismatch")
    require_watch_receipt(metadata, watch_id)
    head_repository = metadata.get("head_repository", "")
    if not head_repository:
        fail(
            "watch head repository identity is missing",
            "identity-mismatch",
        )
    if head_repository != (
        f"{metadata.get('owner', '').lower()}/"
        f"{metadata.get('repository', '').lower()}"
    ):
        fail(
            "watch head repository does not match base repository",
            "cross-repository-head",
        )
    if pending_disposition_details(metadata) is not None:
        fail(
            "pending review dispositions require acknowledgement",
            "pending-dispositions",
        )
    state = state_from_metadata(metadata)
    generation = generation_from_metadata(metadata)
    attempts = attempts_from_metadata(metadata)
    if state == "waiting":
        fail(
            "waiting watch must transition to watching before repair",
            "illegal-transition",
        )
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

    previous_key = metadata.get("attempt_key", "")
    history = parse_attempt_history(metadata.get("attempt_history", ""))
    if previous_key and previous_key not in history:
        history[previous_key] = attempts
    attempts = history.get(attempt_key, 0)
    if attempts >= attempt_limit:
        exhaustion_updates = {
            "state": "exhausted",
            "attempt_key": attempt_key,
            "attempt_limit": str(attempt_limit),
            "attempts": str(attempts),
            "attempt_history": format_attempt_history(history),
            "action_kind": "",
            "action_fingerprint": "",
            "action_id": "",
            "claim_status": "exhausted",
            "expected_old_head": "",
            "expected_new_head": "",
            "expected_old_sha": "",
            "expected_new_sha": "",
            "pushed_sha": "",
            "validation_status": "",
            "make_check_result": "",
            "addressed_thread_ids": "",
            "pending_disposition_action_kind": "",
            "pending_disposition_ids": "",
            "pending_disposition_head_sha": "",
            "pending_disposition_generation": "",
            "formula_attached": "false",
            "formula_root": "",
            "blocker_emitted": "true",
            "terminal_reason": "attempt-budget-exhausted",
        }
        metadata_updates(
            watch_id,
            exhaustion_updates,
            status="blocked",
            assignee="",
        )
        fail(
            "repair attempt budget is exhausted",
            "attempt-budget-exhausted",
        )

    actor = f"pr-babysit-{action_id}"
    claim_result = run_beads(["update", watch_id, "--claim", "--json"], actor=actor)
    if not claim_result.ok:
        error = beads_error(claim_result, "claim")
        if error.code == "already-exists":
            fail("watch is already claimed by another action", "already-claimed")
        raise error

    try:
        action_initial = action_metadata(
            watch_id,
            {
                "rig": metadata.get("rig", ""),
                "rig_prefix": metadata.get("rig_prefix", ""),
                "github_host": metadata.get("github_host", ""),
                "owner": metadata.get("owner", ""),
                "repository": metadata.get("repository", ""),
                "pr_number": metadata.get("pr_number", ""),
                "url": metadata.get("url", ""),
                "base_ref": metadata.get("base_ref", ""),
                "head_ref": metadata.get("head_ref", ""),
                "head_repository": metadata.get("head_repository", ""),
            },
            generation,
            action_kind,
            fingerprint,
            head_sha,
            action_id,
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
            "action_id": action_id,
            "attempt_key": attempt_key,
            "attempt_limit": str(attempt_limit),
            "attempt_history": format_attempt_history(
                {**history, attempt_key: attempts + 1}
            ),
            "claim_status": "claimed",
            "attempts": str(attempts + 1),
            "observed_head_sha": head_sha,
            "expected_old_head": head_sha,
            "expected_new_head": "",
            "expected_old_sha": head_sha,
            "expected_new_sha": "",
            "pushed_sha": "",
            "validation_status": "",
            "make_check_result": "",
            "addressed_thread_ids": "",
            "formula_attached": "false",
            "formula_root": "",
            "blocker_emitted": "false",
            "terminal_reason": "",
        }
        metadata_updates(watch_id, updates)
    except StateError:
        block_claim_setup_failure(watch_id, action_id, metadata)
        raise
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


def formula_result_root(output: str) -> str:
    if not output.strip():
        return ""
    parsed: Any = None
    for line in reversed(output.splitlines()):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        break
    if isinstance(parsed, list):
        parsed = parsed[-1] if parsed else None
    if not isinstance(parsed, dict):
        return ""
    for key in ("root_id", "workflow_root_id", "id", "root"):
        value = parsed.get(key)
        if value:
            try:
                return validate_bead_id(value, key)
            except StateError:
                return ""
    return ""


def repair_formula_vars(
    watch_metadata: dict[str, str],
    action_metadata_value: dict[str, str],
    action_id: str,
    generation: int,
    action_kind: str,
    addressed_thread_ids: str,
) -> list[tuple[str, str]]:
    required = {
        "rig": watch_metadata.get("rig", ""),
        "github_host": watch_metadata.get("github_host", ""),
        "owner": watch_metadata.get("owner", ""),
        "repository": watch_metadata.get("repository", ""),
        "url": watch_metadata.get("url", ""),
        "pr_number": watch_metadata.get("pr_number", ""),
        "base_ref": watch_metadata.get("base_ref", ""),
        "head_ref": watch_metadata.get("head_ref", ""),
        "head_repository": watch_metadata.get("head_repository", ""),
        "observed_head_sha": watch_metadata.get("head_sha", ""),
        "watch_id": action_metadata_value.get("watch_id", ""),
        "action_id": action_id,
        "generation": str(generation),
        "action_kind": action_kind,
        "fingerprint": watch_metadata.get("action_fingerprint", ""),
        "addressed_thread_ids": addressed_thread_ids,
    }
    if any(
        value == ""
        for key, value in required.items()
        if key != "addressed_thread_ids"
    ):
        fail("repair formula provenance is incomplete", "corrupt-state")
    validate_watch_id(required["watch_id"])
    validate_watch_id(required["action_id"])
    parse_url(
        required["url"],
        required["owner"],
        required["repository"],
        integer_value(required["pr_number"], "pr_number"),
    )
    validate_git_ref(required["base_ref"], "base_ref")
    validate_git_ref(required["head_ref"], "head_ref")
    head_repository = repository_name_with_owner(
        required["head_repository"],
        "head_repository",
    )
    if head_repository != f"{required['owner'].lower()}/{required['repository'].lower()}":
        fail("repair head repository does not match publication", "identity-mismatch")
    sha_value(required["observed_head_sha"], "observed_head_sha")
    integer_value(required["generation"], "generation")
    return sorted(required.items())


def attach_repair_formula(
    watch_metadata: dict[str, str],
    action_metadata_value: dict[str, str],
    action_id: str,
    generation: int,
    action_kind: str,
    addressed_thread_ids: str,
) -> str:
    watch_id = validate_watch_id(action_metadata_value.get("watch_id"))
    command = gc_command() + [
        "formula",
        "cook",
        REPAIR_FORMULA,
        "--attach",
        watch_id,
    ]
    for key, value in repair_formula_vars(
        watch_metadata,
        action_metadata_value,
        action_id,
        generation,
        action_kind,
        addressed_thread_ids,
    ):
        command.extend(["--var", f"{key}={value}"])
    command.append("--json")
    try:
        result = subprocess.run(
            command,
            cwd=beads_cwd(),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
            timeout=FORMULA_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        fail("repair formula attachment timed out", "formula-exec")
    except OSError:
        fail("could not execute repair formula", "formula-exec")
    if result.returncode:
        fail("repair formula attachment failed", "formula-attach")
    formula_root = formula_result_root(result.stdout)
    if not formula_root:
        fail(
            "repair formula attachment returned no root ID",
            "formula-invalid-response",
        )
    return formula_root


def block_repair_dispatch(
    watch_id: str,
    action_id: str,
    reason: str,
) -> None:
    metadata_updates(
        action_id,
        {
            "claim_status": "blocked",
            "terminal_reason": reason,
        },
        status="blocked",
        assignee="",
    )
    metadata_updates(
        watch_id,
        {
            "state": "blocked",
            "claim_status": "blocked",
            "terminal_reason": reason,
            "blocker_emitted": "true",
        },
        status="blocked",
        assignee="",
    )


def dispatch_repair(payload: dict[str, Any]) -> dict[str, Any]:
    require_repair_credentials()
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    addressed_thread_ids = safe_identifier_list(
        payload_value(
            payload,
            "addressed_thread_ids",
            "thread_ids",
            "addressed_threads",
            "addressed_ids",
            "ids",
        ),
        "addressed_thread_ids",
    )
    with watch_lock(watch_id):
        claim_result = _claim_action_locked(payload, watch_id)
        action_id = validate_watch_id(claim_result["action_id"])
        (
            _,
            action_id,
            watch_metadata,
            action_metadata_value,
            generation,
            action_kind,
        ) = action_context(
            {
                **payload,
                "watch_id": watch_id,
                "action_id": action_id,
                "generation": claim_result["generation"],
            }
        )
        formula_state = formula_attachment_state(
            action_metadata_value.get("formula_attached")
        )
        recorded_thread_ids = action_metadata_value.get(
            "addressed_thread_ids",
            "",
        )
        if (
            recorded_thread_ids != addressed_thread_ids
            and (
                recorded_thread_ids
                or action_metadata_value.get("formula_attached") == "true"
            )
        ):
            fail(
                "repair action thread scope does not match the claim",
                "identity-mismatch",
            )
        if formula_state == "true":
            formula_root = action_metadata_value.get("formula_root", "")
            if not formula_root:
                fail(
                    "attached repair formula is missing its root ID",
                    "corrupt-state",
                )
            watch_formula_state = formula_attachment_state(
                watch_metadata.get("formula_attached")
            )
            if (
                watch_formula_state != "true"
                or watch_metadata.get("formula_root") != formula_root
            ):
                metadata_updates(
                    watch_id,
                    {
                        "formula_attached": "true",
                        "formula_root": formula_root,
                        "addressed_thread_ids": addressed_thread_ids,
                    },
                )
            return {
                **claim_result,
                "action": "dispatch-repair",
                "formula_attached": True,
                "formula_root": formula_root,
            }
        pending_updates = {
            "formula_attached": "pending",
            "addressed_thread_ids": addressed_thread_ids,
        }
        pending_persisted = formula_state == "pending"
        try:
            if formula_state != "pending":
                metadata_updates(action_id, pending_updates)
            watch_formula_state = formula_attachment_state(
                watch_metadata.get("formula_attached")
            )
            if watch_formula_state != "pending":
                metadata_updates(watch_id, pending_updates)
            pending_persisted = True
            formula_root = attach_repair_formula(
                watch_metadata,
                action_metadata_value,
                action_id,
                generation,
                action_kind,
                addressed_thread_ids,
            )
        except StateError as error:
            if error.code not in {
                "formula-exec",
                "formula-attach",
                "formula-invalid-response",
            }:
                if not pending_persisted:
                    try:
                        block_repair_dispatch(
                            watch_id,
                            action_id,
                            "formula-pending-persist-failed",
                        )
                    except StateError:
                        pass
                raise
            if error.code in {
                "formula-exec",
                "formula-attach",
                "formula-invalid-response",
            }:
                block_repair_dispatch(
                    watch_id,
                    action_id,
                    "formula-attach-failed",
                )
            raise
        updates = {
            "formula_attached": "true",
            "formula_root": formula_root,
            "addressed_thread_ids": addressed_thread_ids,
        }
        metadata_updates(action_id, updates)
        metadata_updates(watch_id, updates)
        return {
            **claim_result,
            "action": "dispatch-repair",
            "formula_attached": True,
            "formula_root": formula_root,
            "addressed_thread_ids": addressed_thread_ids,
        }


def action_context(
    payload: dict[str, Any],
) -> tuple[str, str, dict[str, str], dict[str, str], int, str]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    action_id = validate_watch_id(payload_value(payload, "action_id"))
    _, watch_metadata = show_issue(watch_id)
    if watch_metadata.get("record_kind") != "watch":
        fail("requested Beads record is not a watch", "identity-mismatch")
    require_watch_receipt(watch_metadata, watch_id)
    formula_attachment_state(watch_metadata.get("formula_attached"))
    _, action_metadata_value = show_issue(action_id)
    if action_metadata_value.get("record_kind") != "action":
        fail("requested Beads record is not an action", "identity-mismatch")
    formula_attachment_state(action_metadata_value.get("formula_attached"))
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
    if action_metadata_value.get("action_id") != action_id:
        fail("action provenance has the wrong action ID", "identity-mismatch")
    for key in (
        "provenance_version",
        "rig",
        "rig_prefix",
        "github_host",
        "owner",
        "repository",
        "pr_number",
        "url",
        "base_ref",
        "head_ref",
        "head_repository",
        "head_sha",
        "observed_head_sha",
        "posture",
        "target_posture",
        "generation",
        "action_kind",
        "action_fingerprint",
        "attempt_key",
        "attempt_limit",
    ):
        if key == "provenance_version":
            if action_metadata_value.get(key) != "pr-repair-v1":
                fail("action provenance version is unsupported", "identity-mismatch")
            continue
        if action_metadata_value.get(key) != watch_metadata.get(key):
            if key == "head_sha" and action_metadata_value.get(key) == watch_metadata.get(
                "expected_old_head"
            ):
                continue
            fail("action provenance does not match the watch", "identity-mismatch")
    return (
        watch_id,
        action_id,
        watch_metadata,
        action_metadata_value,
        generation,
        action_kind,
    )


def record_candidate_head(payload: dict[str, Any]) -> dict[str, Any]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    with watch_lock(watch_id):
        (
            watch_id,
            action_id,
            _,
            action_metadata_value,
            generation,
            _,
        ) = action_context(payload)
        candidate_head_sha = sha_value(
            payload_value(
                payload,
                "candidate_head_sha",
                "candidate_sha",
                "head_sha",
            ),
            "candidate_head_sha",
        )
        recorded_candidate = action_metadata_value.get(
            "candidate_head_sha",
            "",
        )
        if recorded_candidate and recorded_candidate != candidate_head_sha:
            fail(
                "candidate head changed after it was recorded",
                "stale-candidate",
            )
        recorded_verdict_head = action_metadata_value.get(
            "review_verdict_head_sha",
            "",
        )
        if recorded_verdict_head and recorded_verdict_head != candidate_head_sha:
            fail(
                "candidate head does not match the reviewer verdict",
                "stale-candidate",
            )
        if not recorded_candidate:
            metadata_updates(
                action_id,
                {"candidate_head_sha": candidate_head_sha},
            )
        return {
            "ok": True,
            "action": "record-candidate-head",
            "watch_id": watch_id,
            "action_id": action_id,
            "generation": generation,
            "candidate_head_sha": candidate_head_sha,
            "reused": bool(recorded_candidate),
        }


def record_review_verdict(payload: dict[str, Any]) -> dict[str, Any]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    with watch_lock(watch_id):
        (
            watch_id,
            action_id,
            _,
            action_metadata_value,
            generation,
            _,
        ) = action_context(payload)
        candidate_head_sha = sha_value(
            payload_value(
                payload,
                "candidate_head_sha",
                "candidate_sha",
                "head_sha",
            ),
            "candidate_head_sha",
        )
        verdict = text_value(
            payload_value(payload, "verdict", "review_verdict"),
            "verdict",
        ).strip().lower()
        if verdict not in REVIEW_VERDICTS:
            fail("review verdict must be passed or failed")
        recorded_candidate = action_metadata_value.get(
            "candidate_head_sha",
            "",
        )
        if recorded_candidate and recorded_candidate != candidate_head_sha:
            fail(
                "review verdict is stale for the candidate head",
                "stale-verdict",
            )
        recorded_verdict = action_metadata_value.get("review_verdict", "")
        if recorded_verdict and (
            recorded_verdict != verdict
            or action_metadata_value.get("review_verdict_action_id")
            != action_id
            or action_metadata_value.get("review_verdict_generation")
            != str(generation)
            or action_metadata_value.get("review_verdict_head_sha")
            != candidate_head_sha
        ):
            fail(
                "review verdict does not match the action claim",
                "stale-verdict",
            )
        updates = {
            "candidate_head_sha": candidate_head_sha,
            "review_verdict": verdict,
            "review_verdict_action_id": action_id,
            "review_verdict_generation": str(generation),
            "review_verdict_head_sha": candidate_head_sha,
        }
        if not recorded_verdict:
            metadata_updates(action_id, updates)
        if verdict == "failed":
            metadata_updates(
                action_id,
                {
                    "claim_status": "blocked",
                    "terminal_reason": "review-failed",
                },
                status="blocked",
                assignee="",
            )
            metadata_updates(
                watch_id,
                {
                    "state": "blocked",
                    "claim_status": "blocked",
                    "terminal_reason": "review-failed",
                    "blocker_emitted": "true",
                },
                status="blocked",
                assignee="",
            )
        return {
            "ok": True,
            "action": "record-review-verdict",
            "watch_id": watch_id,
            "action_id": action_id,
            "generation": generation,
            "candidate_head_sha": candidate_head_sha,
            "review_verdict": verdict,
            "reused": bool(recorded_verdict),
        }


def record_worker_signoff(payload: dict[str, Any]) -> dict[str, Any]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    with watch_lock(watch_id):
        (
            watch_id,
            action_id,
            _,
            action_metadata_value,
            generation,
            _,
        ) = action_context(payload)
        worker_signoff_sha = sha_value(
            payload_value(
                payload,
                "worker_signoff_sha",
                "candidate_head_sha",
                "head_sha",
            ),
            "worker_signoff_sha",
        )
        if worker_signoff_sha == action_metadata_value.get("expected_old_head"):
            fail("worker signoff must identify a new repair commit")
        recorded_signoff = action_metadata_value.get("worker_signoff_sha", "")
        if recorded_signoff and recorded_signoff != worker_signoff_sha:
            fail("worker signoff changed after it was recorded", "stale-signoff")
        recorded_candidate = action_metadata_value.get("candidate_head_sha", "")
        if recorded_candidate and recorded_candidate != worker_signoff_sha:
            fail("worker signoff does not match the candidate head", "stale-signoff")
        if not recorded_signoff:
            metadata_updates(
                action_id,
                {
                    "worker_signoff_sha": worker_signoff_sha,
                    "make_check_result": "passed",
                },
            )
        return {
            "ok": True,
            "action": "record-worker-signoff",
            "watch_id": watch_id,
            "action_id": action_id,
            "generation": generation,
            "worker_signoff_sha": worker_signoff_sha,
            "make_check_result": "passed",
            "reused": bool(recorded_signoff),
        }


def review_verdict_matches(
    metadata: dict[str, str],
    action_id: str,
    generation: int,
    candidate_head_sha: str,
) -> bool:
    return (
        metadata.get("review_verdict") == "passed"
        and metadata.get("review_verdict_action_id") == action_id
        and metadata.get("review_verdict_generation") == str(generation)
        and metadata.get("review_verdict_head_sha") == candidate_head_sha
        and metadata.get("candidate_head_sha") == candidate_head_sha
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
    make_check_result = text_value(
        payload_value(
            payload,
            "make_check_result",
            "make_check",
            "check_result",
        )
        or validation_status,
        "make_check_result",
    ).lower()
    if make_check_result not in VALIDATION_STATUSES:
        fail("make_check_result is not supported")
    result_reason = safe_reason(
        payload_value(payload, "reason", "failure_reason"),
        "reason",
        required=False,
    )
    if validation_status == "passed" and make_check_result != "passed":
        fail("a passed repair result requires a passed make check")
    addressed_thread_ids = safe_identifier_list(
        payload_value(
            payload,
            "addressed_thread_ids",
            "thread_ids",
            "addressed_threads",
            "addressed_ids",
            "ids",
        ),
        "addressed_thread_ids",
    )
    claimed_thread_ids = {
        item
        for item in action_metadata_value.get(
            "addressed_thread_ids",
            "",
        ).split(",")
        if item
    }
    reported_thread_ids = {
        item
        for item in addressed_thread_ids.split(",")
        if item
    }
    if not reported_thread_ids.issubset(claimed_thread_ids):
        fail(
            "repair result addresses an unclaimed thread",
            "identity-mismatch",
        )
    if validation_status == "passed" and not pushed_sha:
        fail("a passed repair result requires pushed_sha")
    if validation_status == "passed" and not review_verdict_matches(
        action_metadata_value,
        action_id,
        generation,
        pushed_sha,
    ):
        block_repair_dispatch(
            watch_id,
            action_id,
            "review-verdict-required",
        )
        fail(
            "a passed repair result requires a current passed review verdict",
            "review-verdict-required",
        )
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
    if validation_status == "passed" and pushed_sha == expected_old_sha:
        validation_status = "ambiguous"
    if remote_head and pushed_sha and remote_head != pushed_sha:
        validation_status = "ambiguous"
    action_updates = {
        "claim_status": "ambiguous"
        if validation_status in {"ambiguous", "failed"}
        else "result-recorded",
        "expected_old_head": expected_old_sha,
        "expected_new_head": pushed_sha,
        "expected_old_sha": expected_old_sha,
        "expected_new_sha": pushed_sha,
        "pushed_sha": pushed_sha,
        "last_pushed_sha": pushed_sha,
        "validation_status": validation_status,
        "make_check_result": make_check_result,
        "addressed_thread_ids": addressed_thread_ids,
        "terminal_reason": (
            AMBIGUOUS_REASON
            if validation_status == "ambiguous"
            else result_reason or "repair-validation-failed"
            if validation_status == "failed"
            else ""
        ),
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
        "make_check_result": make_check_result,
        "addressed_thread_ids": addressed_thread_ids,
        "claim_status": (
            "blocked"
            if validation_status in {"ambiguous", "failed"}
            else "result-recorded"
        ),
    }
    if validation_status == "ambiguous":
        watch_updates.update(
            {
                "state": "blocked",
                "terminal_reason": AMBIGUOUS_REASON,
                "blocker_emitted": "true",
            }
        )
        metadata_updates(watch_id, watch_updates, status="blocked", assignee="")
    elif validation_status == "failed":
        watch_updates.update(
            {
                "state": "blocked",
                "terminal_reason": result_reason or "repair-validation-failed",
                "blocker_emitted": "true",
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
        action_kind,
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
    make_check_result = action_metadata_value.get("make_check_result", "")
    pushed_sha = action_metadata_value.get("pushed_sha", "")
    expected_old_sha = action_metadata_value.get("expected_old_head", "")
    review_verdict_ok = bool(
        pushed_sha
        and review_verdict_matches(
            action_metadata_value,
            action_id,
            generation,
            pushed_sha,
        )
    )
    if (
        not pushed_sha
        or validation_status != "passed"
        or make_check_result != "passed"
        or not review_verdict_ok
    ):
        reason = (
            "review-verdict-failed"
            if not review_verdict_ok
            else
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
                "blocker_emitted": "true",
            },
            status="blocked",
            assignee="",
        )
        _, metadata = show_issue(watch_id)
        fail(
            "repair confirmation fence failed",
            reason,
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
                "blocker_emitted": "true",
            },
            status="blocked",
            assignee="",
        )
        _, metadata = show_issue(watch_id)
        fail(
            "repair confirmation fence failed",
            reason,
        )

    observed_at = text_value(
        payload_value(payload, "observed_at", "last_snapshot_at") or iso_now(),
        "observed_at",
    )
    parse_time(observed_at, "observed_at")
    next_snapshot_at = observed_at
    next_generation = generation + 1
    addressed_thread_ids = action_metadata_value.get(
        "addressed_thread_ids",
        "",
    )
    close_action(action_id, "confirmed")
    updates = clear_claim_updates(
        "watching",
        next_generation,
        head_sha=current_sha,
        observed_at=observed_at,
        next_snapshot_at=next_snapshot_at,
        active_since=watch_metadata["active_since"],
        last_pushed_sha=pushed_sha,
        attempt_key=watch_metadata.get("attempt_key", ""),
        attempts=attempts_from_metadata(watch_metadata),
        attempt_limit=watch_metadata.get("attempt_limit", ""),
        attempt_history=watch_metadata.get("attempt_history", ""),
        backstop_at=watch_metadata.get("backstop_at", ""),
    )
    if (
        addressed_thread_ids
        and (action_kind == "review" or action_kind.startswith("review-"))
    ):
        updates.update(
            {
                "action_kind": action_kind,
                "addressed_thread_ids": addressed_thread_ids,
                "pending_disposition_action_kind": action_kind,
                "pending_disposition_ids": addressed_thread_ids,
                "pending_disposition_head_sha": current_sha,
                "pending_disposition_generation": str(next_generation),
            }
        )
    metadata_updates(
        watch_id,
        updates,
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


def acknowledge_dispositions(payload: dict[str, Any]) -> dict[str, Any]:
    watch_id = validate_watch_id(payload_value(payload, "watch_id", "id"))
    with watch_lock(watch_id):
        _, metadata = show_issue(watch_id)
        if metadata.get("record_kind") != "watch":
            fail("requested Beads record is not a watch", "identity-mismatch")
        require_watch_receipt(metadata, watch_id)
        if metadata.get("state") not in CHECKPOINT_STATES:
            fail(
                "pending dispositions can only be acknowledged on an active watch",
                "not-acknowledgeable",
            )
        pending = pending_disposition_details(metadata)
        if pending is None:
            fail(
                "watch has no pending review dispositions",
                "no-pending-dispositions",
            )
        pending_kind, pending_ids, pending_head, pending_generation = pending
        action_kind = normalize_action_kind(
            payload_value(payload, "action_kind", "kind"),
        )
        addressed_ids = safe_identifier_list(
            payload_value(
                payload,
                "addressed_thread_ids",
                "thread_ids",
                "addressed_threads",
                "addressed_ids",
                "ids",
            ),
            "addressed_thread_ids",
        )
        head_sha = sha_value(
            payload_value(
                payload,
                "head_sha",
                "current_head_sha",
                "observed_head_sha",
            ),
            "head_sha",
        )
        generation = integer_value(
            payload_value(payload, "generation"),
            "generation",
        )
        if (
            generation != generation_from_metadata(metadata)
            or head_sha != metadata.get("head_sha")
            or generation != pending_generation
            or head_sha != pending_head
        ):
            fail(
                "pending dispositions are stale for the current watch",
                "stale-dispositions",
            )
        if action_kind != pending_kind:
            fail(
                "pending disposition action kind does not match",
                "identity-mismatch",
            )
        if addressed_ids != pending_ids:
            fail(
                "pending disposition IDs do not match",
                "identity-mismatch",
            )
        updates = {
            "action_kind": "",
            "addressed_thread_ids": "",
            "pending_disposition_action_kind": "",
            "pending_disposition_ids": "",
            "pending_disposition_head_sha": "",
            "pending_disposition_generation": "",
        }
        metadata_updates(watch_id, updates)
        _, metadata = show_issue(watch_id)
        return metadata_response(
            "acknowledge-dispositions",
            watch_id,
            metadata,
            acknowledged=True,
            action_kind=action_kind,
            addressed_thread_ids=addressed_ids,
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
    require_watch_receipt(metadata, watch_id)
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

    pending_dispositions = pending_disposition_details(metadata)
    if current in CHECKPOINT_STATES and active_claim:
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
    if (
        pending_dispositions is not None
        and not head_changed
        and desired not in {"blocked", "exhausted", "terminal"}
    ):
        fail(
            "pending review dispositions require acknowledgement",
            "pending-dispositions",
        )
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

    merge_ready_evidence = None
    if desired == "merge-ready":
        merge_ready_evidence = _merge_ready_evidence(
            payload,
            expected_head=expected_head,
            observed_head=observed_head,
        )

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
        "observed_head_sha": observed_head,
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
                "action_id": "",
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
                "make_check_result": "",
                "addressed_thread_ids": "",
                "pending_disposition_action_kind": "",
                "pending_disposition_ids": "",
                "pending_disposition_head_sha": "",
                "pending_disposition_generation": "",
                "formula_attached": "false",
                "formula_root": "",
                "blocker_emitted": (
                    "true"
                    if desired in {"blocked", "exhausted"}
                    else "false"
                ),
            }
        )
        if (
            pending_dispositions is not None
            and desired != "terminal"
        ):
            pending_kind, pending_ids, _, _ = pending_dispositions
            updates.update(
                {
                    "action_kind": pending_kind,
                    "addressed_thread_ids": pending_ids,
                    "pending_disposition_action_kind": pending_kind,
                    "pending_disposition_ids": pending_ids,
                    "pending_disposition_head_sha": observed_head,
                    "pending_disposition_generation": str(next_generation),
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
        merge_ready_evidence=merge_ready_evidence,
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
    args = [
        "list",
        "--all",
        "--json",
    ]
    args.extend(["--metadata-field", "record_kind=watch"])
    if rig:
        args.extend(["--metadata-field", f"rig={rig}"])
    result = run_beads(args)
    records = require_beads(result, "list")
    if isinstance(records, dict) and isinstance(records.get("issues"), list):
        records = records["issues"]
    if not isinstance(records, list):
        fail("Beads list returned an invalid result", "beads-invalid-response")
    due: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or not record.get("id"):
            continue
        if record.get("status") != "open":
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
        formula_attachment_state(metadata.get("formula_attached"))
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
        wake_lease_until = metadata.get("wake_lease_until", "")
        if wake_lease_until:
            if parse_time(wake_lease_until, "wake_lease_until") > now:
                continue
        if rig and metadata.get("rig") != rig:
            continue
        if not watch_receipt_is_complete(metadata, record["id"]):
            continue
        if state not in CHECKPOINT_STATES:
            continue
        pending_dispositions = pending_disposition_details(metadata)
        if (
            metadata.get("claim_status", "none") != "none"
            or metadata.get("action_fingerprint", "")
            or (
                pending_dispositions is None
                and metadata.get("action_kind", "")
            )
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


def sweep(payload: dict[str, Any]) -> dict[str, Any]:
    rig = text_value(payload_value(payload, "rig"), "rig")
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

    due_result = list_due(
        {
            **payload,
            "rig": rig,
            "limit": limit,
            "now": format_time(now),
        }
    )
    watches = due_result.get("watches")
    if not isinstance(watches, list):
        fail("list-due returned an invalid watch list", "beads-invalid-response")
    if len(watches) > limit:
        fail("list-due exceeded the sweep limit", "beads-invalid-response")

    target = handoff_target(rig)
    routed = 0
    route_errors: list[StateError] = []
    for watch in watches:
        if not isinstance(watch, dict):
            fail("list-due returned an invalid watch", "beads-invalid-response")
        watch_id = watch.get("watch_id")
        metadata = watch.get("metadata")
        if (
            not isinstance(watch_id, str)
            or not WATCH_ID_RE.fullmatch(watch_id)
            or not isinstance(metadata, dict)
        ):
            fail("list-due returned an unsafe watch", "beads-invalid-response")
        lease_until: str | None = None
        with watch_lock(watch_id, blocking=False) as acquired:
            if not acquired:
                continue
            _, current_metadata = show_issue(watch_id)
            pending_dispositions = pending_disposition_details(
                current_metadata,
            )
            if (
                current_metadata.get("state") not in CHECKPOINT_STATES
                or current_metadata.get("claim_status", "none") != "none"
                or current_metadata.get("action_fingerprint", "")
                or not watch_receipt_is_complete(
                    current_metadata,
                    watch_id,
                )
                or (
                    pending_dispositions is None
                    and current_metadata.get("action_kind", "")
                )
            ):
                continue
            next_time = parse_time(
                current_metadata.get("next_snapshot_at", ""),
                "next_snapshot_at",
            )
            if next_time > now:
                continue
            recorded_lease = current_metadata.get("wake_lease_until", "")
            if recorded_lease and parse_time(
                recorded_lease,
                "wake_lease_until",
            ) > now:
                continue
            lease_until = format_time(now + WAKE_LEASE)
            metadata_updates(
                watch_id,
                {
                    "next_snapshot_at": format_time(now + SWEEP_INTERVAL),
                    "wake_lease_until": lease_until,
                },
            )
        try:
            route_watch(target, watch_id)
        except StateError as error:
            if lease_until is not None:
                try:
                    with watch_lock(watch_id, blocking=False) as acquired:
                        if acquired:
                            _, current_metadata = show_issue(watch_id)
                            if current_metadata.get("wake_lease_until") == lease_until:
                                metadata_updates(
                                    watch_id,
                                    {"wake_lease_until": ""},
                                )
                except StateError:
                    pass
            route_errors.append(error)
            continue
        if lease_until is not None:
            with watch_lock(watch_id, blocking=False) as acquired:
                if acquired:
                    _, current_metadata = show_issue(watch_id)
                    if current_metadata.get("wake_lease_until") == lease_until:
                        metadata_updates(
                            watch_id,
                            {"wake_lease_until": ""},
                        )
            routed += 1

    if route_errors:
        raise route_errors[0]

    return {
        "ok": True,
        "action": "sweep",
        "rig": rig,
        "routed": routed,
    }


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
    request_action = action or data.pop("action", None)
    if request_action is None:
        fail("an action is required")
    request_action = str(request_action).strip().lower()
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
            "transition": ("watch_id", "to", "reason"),
            "claim-action": (
                "watch_id",
                "action_kind",
                "fingerprint",
                "generation",
                "head_sha",
            ),
            "dispatch-repair": (
                "watch_id",
                "action_kind",
                "fingerprint",
                "generation",
                "head_sha",
                "addressed_thread_ids",
            ),
            "record-candidate-head": (
                "watch_id",
                "action_id",
                "generation",
                "candidate_head_sha",
            ),
            "record-worker-signoff": (
                "watch_id",
                "action_id",
                "generation",
                "worker_signoff_sha",
            ),
            "record-review-verdict": (
                "watch_id",
                "action_id",
                "generation",
                "candidate_head_sha",
                "verdict",
            ),
            "record-repair-result": (
                "watch_id",
                "action_id",
                "expected_old_sha",
                "pushed_sha",
                "validation_status",
                "make_check_result",
                "addressed_thread_ids",
            ),
            "confirm-action": ("watch_id", "action_id", "current_sha",),
            "acknowledge-dispositions": (
                "watch_id",
                "action_kind",
                "generation",
                "head_sha",
                "addressed_thread_ids",
            ),
            "checkpoint": (
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
            "verify-handoff": (
                "rig",
                "publication_bead_id",
                "url",
                "pr_number",
            ),
            "sweep": ("rig", "limit"),
        }.get(request_action, ())
        for key, value in zip(positional_fields, positionals):
            data.setdefault(key, value)
    data["action"] = request_action
    return data


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action == "check-credentials":
        return check_repair_credentials()
    if action == "handoff":
        return handoff(payload)
    if action == "publication-handoff":
        return publication_handoff(payload)
    if action == "verify-handoff":
        return verify_handoff(payload)
    if action == "show":
        return show_state(payload)
    if action == "transition":
        return transition(payload)
    if action == "claim-action":
        return claim_action(payload)
    if action == "dispatch-repair":
        return dispatch_repair(payload)
    if action == "record-candidate-head":
        return record_candidate_head(payload)
    if action == "record-worker-signoff":
        return record_worker_signoff(payload)
    if action == "record-review-verdict":
        return record_review_verdict(payload)
    if action == "record-repair-result":
        return record_repair_result(payload)
    if action == "confirm-action":
        return confirm_action(payload)
    if action == "acknowledge-dispositions":
        return acknowledge_dispositions(payload)
    if action == "checkpoint":
        return checkpoint(payload)
    if action == "list-due":
        return list_due(payload)
    if action == "sweep":
        return sweep(payload)
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
