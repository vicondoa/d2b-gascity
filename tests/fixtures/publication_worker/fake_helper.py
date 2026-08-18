#!/usr/bin/env python3
"""Stateful helper fixture for trusted publication-worker tests."""

from __future__ import annotations

import json
import os
import pathlib
import sys


def main(argv: list[str]) -> int:
    path = pathlib.Path(os.environ["FAKE_HELPER_STATE"])
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("calls", []).append(
        {
            "argv": argv,
            "cwd": os.getcwd(),
            "credential_directory": os.environ.get("CREDENTIALS_DIRECTORY", ""),
        }
    )
    path.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    if state.get("mode") == "failure":
        print("fixture-token child diagnostic", file=sys.stderr)
        return 1
    if state.get("mode") == "typed-failure":
        print(
            f"publish-pr: {state.get('error_code', 'remote-state-unavailable')}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(state["record"], separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
