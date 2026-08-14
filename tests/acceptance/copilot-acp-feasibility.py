#!/usr/bin/env python3
"""Verify the already-proven direct ACP path without starting a model."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
EXPECTED_VERSION = "1.0.79"
DEFAULT_REVISION = "9e0abd0c80e878567edc903fdf23f73ff432d34c"
REVISION_PATTERN = re.compile(r"^[0-9a-fA-F]{7,64}$")
COMMAND_TIMEOUT = 10.0

PROFILE_SOURCE = "nix/gas-city-contributor/pack/scripts/copilot-profile.py"
LAUNCHER_SOURCE = "nix/gas-city-contributor/pack/scripts/agent-launcher.py"
TEST_SOURCE = "tests/fixtures/gas-city/acp/test_contracts.py"
MARKERS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "profiles": (
        (
            PROFILE_SOURCE,
            (
                "PROFILE_SETTINGS = {",
                '"review-sol": {',
                '"model": "gpt-5.6-sol"',
                '"review-luna": {',
                '"model": "gpt-5.6-luna"',
                '"contextTier": "long_context"',
                'PROFILE_EFFORT = {',
                '"review-sol": "xhigh"',
            ),
        ),
        (TEST_SOURCE, ("def test_profile_owned_startup_arguments_reject_overrides",)),
    ),
    "protocol": (
        (
            PROFILE_SOURCE,
            (
                'def _frame(',
                "class _ACPReader:",
                "_PROBE_RESPONSE_PHASES = (",
                '(1, "initialize")',
                '(2, "session/new")',
                '(3, "session/prompt")',
            ),
        ),
        (
            TEST_SOURCE,
            ("def test_probe_uses_ndjson_and_closed_is_classified",),
        ),
    ),
    "restart": (
        (
            LAUNCHER_SOURCE,
            (
                "def _send_group_signal(",
                "os.killpg(pgid, signum)",
                "start_new_session=True",
            ),
        ),
        (
            TEST_SOURCE,
            (
                "def test_client_eof_stops_child_and_releases_lease",
                "def test_timeout_kills_exact_process_group_and_releases_slot",
            ),
        ),
    ),
    "errors": (
        (
            TEST_SOURCE,
            (
                "def test_direct_probe_classifies_exception_with_stderr",
                "def test_probe_rejects_malformed_idless_messages",
                "def test_sol_auth_network_quota_malformed_and_unknown_block",
            ),
        ),
    ),
    "redaction": (
        (
            TEST_SOURCE,
            ("def test_only_copilot_auth_survives_environment_projection",),
        ),
    ),
}
class VerificationError(Exception):
    def __init__(
        self,
        code: str,
        checks: dict[str, bool] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.checks = checks or {}
def run_bounded(
    command: list[str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env={
                "PATH": os.pathsep.join(
                    (str(Path(sys.executable).resolve().parent), os.defpath)
                ),
                "HOME": str(Path.cwd()),
                "NO_COLOR": "1",
                "TERM": "dumb",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=COMMAND_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise VerificationError("timeout") from exc
    except OSError as exc:
        raise VerificationError("runtime-unavailable") from exc
def verify_runtime(runtime: Path) -> None:
    root = runtime.expanduser().resolve()
    copilot = root / "bin" / "copilot"
    if not copilot.is_file() or not os.access(copilot, os.X_OK):
        raise VerificationError("runtime-unavailable")

    version = run_bounded([str(copilot), "--version"], cwd=root)
    if version.returncode != 0 or EXPECTED_VERSION.encode() not in version.stdout:
        raise VerificationError("runtime-version")

    help_output = run_bounded([str(copilot), "--help"], cwd=root)
    if help_output.returncode != 0:
        raise VerificationError("runtime-help")
    required_flags = (b"--acp", b"--model", b"--context", b"--effort")
    if not all(flag in help_output.stdout for flag in required_flags):
        raise VerificationError("runtime-acp-unsupported")
def git_show(repo: Path, revision: str, path: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", f"{revision}:{path}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=COMMAND_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise VerificationError("timeout") from exc
    except OSError as exc:
        raise VerificationError("evidence-repo-unavailable") from exc
    if result.returncode != 0:
        raise VerificationError("evidence-source-missing")
    return result.stdout
def verify_evidence(repo: Path, revision: str) -> dict[str, bool]:
    checks = {name: False for name in MARKERS}
    if not repo.is_dir():
        raise VerificationError("evidence-repo-unavailable", checks)
    if not REVISION_PATTERN.fullmatch(revision):
        raise VerificationError("invalid-evidence-revision", checks)
    try:
        resolved = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "rev-parse",
                "--verify",
                f"{revision}^{{commit}}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=COMMAND_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise VerificationError("timeout", checks) from exc
    except OSError as exc:
        raise VerificationError("evidence-repo-unavailable", checks) from exc
    if resolved.returncode != 0:
        raise VerificationError("evidence-revision-missing", checks)

    sources: dict[str, bytes] = {}
    for entries in MARKERS.values():
        for path, _markers in entries:
            if path not in sources:
                sources[path] = git_show(repo, revision, path)

    for name, entries in MARKERS.items():
        checks[name] = all(
            marker.encode("utf-8") in sources[path]
            for path, markers in entries
            for marker in markers
        )
    if not all(checks.values()):
        raise VerificationError("evidence-marker-missing", checks)
    return checks
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--evidence-repo", type=Path, required=True)
    parser.add_argument("--evidence-revision", default=DEFAULT_REVISION)
    return parser.parse_args()
def main() -> int:
    args = parse_args()
    checks = {name: False for name in ("runtime", *MARKERS)}
    error_code: str | None = None

    try:
        verify_runtime(args.runtime)
        checks["runtime"] = True
    except VerificationError as exc:
        error_code = exc.code

    try:
        checks.update(verify_evidence(args.evidence_repo, args.evidence_revision))
    except VerificationError as exc:
        checks.update(exc.checks)
        if error_code is None:
            error_code = exc.code

    payload: dict[str, Any] = {
        "ok": error_code is None and all(checks.values()),
        "mode": "proof-reuse",
        "version": EXPECTED_VERSION,
        "direct": True,
        "evidence_revision": args.evidence_revision,
        "checks": checks,
        "error_code": error_code,
    }
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
