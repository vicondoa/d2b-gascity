#!/usr/bin/env python3
"""Bounded, read-only operator helpers for the standalone city."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts" / "bootstrap.py"
MAX_REQUEST_BYTES = 8192


def _path(value: str, label: str) -> pathlib.Path:
    path = pathlib.Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError(f"{label} must be absolute")
    return path


def _status(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(BOOTSTRAP),
        "check",
        "--state-root",
        str(args.state_root),
        "--city",
        str(args.city),
        "--rig",
        str(args.rig),
        "--gc",
        str(args.gc),
    ]
    if args.fixture_supervisor:
        command.append("--fixture-supervisor")
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return result.returncode


def _validate_request(args: argparse.Namespace) -> int:
    payload = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(payload) > MAX_REQUEST_BYTES:
        print("operator: request exceeds the 8192-byte limit", file=sys.stderr)
        return 2
    try:
        request = json.loads(payload)
    except json.JSONDecodeError as exc:
        print(f"operator: invalid JSON request: {exc.msg}", file=sys.stderr)
        return 2
    if not isinstance(request, dict):
        print("operator: request must be a JSON object", file=sys.stderr)
        return 2
    if set(request) != {"action", "request_id"}:
        print("operator: request fields must be action and request_id", file=sys.stderr)
        return 2
    if request["action"] not in {"status", "check"}:
        print("operator: unsupported action", file=sys.stderr)
        return 2
    if (
        not isinstance(request["request_id"], str)
        or not request["request_id"]
        or len(request["request_id"]) > 128
    ):
        print("operator: request_id must be a bounded non-empty string", file=sys.stderr)
        return 2
    print(json.dumps({"accepted": True, "request_id": request["request_id"]}))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only d2b Gas City operator helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="run the explicit-path bootstrap check")
    status.add_argument("--state-root", required=True, type=lambda value: _path(value, "state root"))
    status.add_argument("--city", required=True, type=lambda value: _path(value, "city"))
    status.add_argument("--rig", required=True, type=lambda value: _path(value, "rig"))
    status.add_argument("--gc", required=True, type=lambda value: _path(value, "gc runtime"))
    status.add_argument("--fixture-supervisor", action="store_true")
    status.set_defaults(handler=_status)

    request = subparsers.add_parser("validate-request", help="validate a bounded JSON request")
    request.set_defaults(handler=_validate_request)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
