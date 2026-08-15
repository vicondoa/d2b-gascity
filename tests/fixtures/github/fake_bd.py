#!/usr/bin/env python3
"""Stateful bd fixture for publication anchor tests."""

from __future__ import annotations

import json
import os
import pathlib
import sys


def _state_path() -> pathlib.Path:
    explicit = os.environ.get("FAKE_BD_STATE")
    if explicit:
        return pathlib.Path(explicit)
    return pathlib.Path.cwd() / ".fake-bd-state.json"


def _load(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: pathlib.Path, state: dict[str, object]) -> None:
    path.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")


def _log(state: dict[str, object], argv: list[str]) -> None:
    calls = state.setdefault("calls", [])
    assert isinstance(calls, list)
    calls.append(argv)


def main(argv: list[str]) -> int:
    path = _state_path()
    state = _load(path)
    _log(state, argv)

    if len(argv) == 4 and argv[0] == "show" and argv[2:] == ["--json", "--long"]:
        issue = state.get("issue")
        if issue is None:
            print("[]")
        else:
            print(json.dumps([issue], separators=(",", ":")))
        _save(path, state)
        return 0

    if len(argv) >= 4 and argv[0] == "update" and "--set-metadata" in argv:
        issue_id = argv[1]
        issue = state.get("issue")
        if not isinstance(issue, dict) or issue.get("id") != issue_id:
            print("issue not found", file=sys.stderr)
            _save(path, state)
            return 1
        if state.get("update_mode") == "failure":
            print("update failed", file=sys.stderr)
            _save(path, state)
            return 1
        metadata = issue.setdefault("metadata", {})
        assert isinstance(metadata, dict)
        for index, value in enumerate(argv):
            if value != "--set-metadata":
                continue
            if index + 1 >= len(argv) or "=" not in argv[index + 1]:
                print("invalid metadata", file=sys.stderr)
                _save(path, state)
                return 1
            key, item = argv[index + 1].split("=", 1)
            metadata[key] = item
        if state.get("update_mode") == "readback-mismatch":
            metadata["gc.publication.sha"] = "d" * 40
        _save(path, state)
        return 0

    print(f"unsupported fake bd command: {' '.join(argv)}", file=sys.stderr)
    _save(path, state)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
