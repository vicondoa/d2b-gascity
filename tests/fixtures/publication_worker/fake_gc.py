#!/usr/bin/env python3
"""Stateful Gas City fixture for the trusted publication worker."""

from __future__ import annotations

import json
import os
import pathlib
import sys


def _state_path() -> pathlib.Path:
    return pathlib.Path(os.environ["FAKE_GC_STATE"])


def _load() -> dict[str, object]:
    path = _state_path()
    return json.loads(path.read_text(encoding="utf-8"))


def _save(state: dict[str, object]) -> None:
    _state_path().write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")


def _log(state: dict[str, object], argv: list[str]) -> None:
    calls = state.setdefault("calls", [])
    assert isinstance(calls, list)
    calls.append({"argv": argv, "cwd": os.getcwd()})


def _bead(state: dict[str, object], bead_id: str) -> dict[str, object] | None:
    beads = state.setdefault("beads", {})
    assert isinstance(beads, dict)
    value = beads.get(bead_id)
    return value if isinstance(value, dict) else None


def _claim(state: dict[str, object]) -> int:
    claims = state.setdefault("claims", [])
    assert isinstance(claims, list)
    if not claims:
        payload = {
            "schema_version": "1",
            "ok": True,
            "command": "hook",
            "action": "drain",
            "reason": "no_work",
            "drain_acknowledged": True,
        }
    else:
        payload = claims.pop(0)
    print(json.dumps(payload, separators=(",", ":")))
    _save(state)
    return 0


def _update(state: dict[str, object], argv: list[str]) -> int:
    if len(argv) < 2:
        return 2
    bead = _bead(state, argv[1])
    if bead is None:
        return 1
    failure_beads = state.get("update_failure_beads", [])
    if (
        state.get("update_mode") == "failure"
        or (
            isinstance(failure_beads, list)
            and argv[1] in failure_beads
        )
    ):
        _save(state)
        return 1
    metadata = bead.setdefault("metadata", {})
    assert isinstance(metadata, dict)
    for index, item in enumerate(argv):
        if item != "--set-metadata" or index + 1 >= len(argv):
            continue
        key, separator, value = argv[index + 1].partition("=")
        if not separator:
            return 2
        metadata[key] = value
    mismatch_beads = state.get("readback_mismatch_beads", [])
    if (
        state.get("update_mode") == "readback-mismatch"
        or (
            isinstance(mismatch_beads, list)
            and argv[1] in mismatch_beads
        )
    ):
        metadata["gc.outcome"] = "readback-mismatch"
    updates = state.setdefault("updates", [])
    assert isinstance(updates, list)
    updates.append({"bead_id": argv[1], "metadata": dict(metadata)})
    _save(state)
    return 0


def _close(state: dict[str, object], argv: list[str]) -> int:
    if len(argv) < 2:
        return 2
    bead = _bead(state, argv[1])
    if bead is None:
        return 1
    bead["closed"] = True
    closes = state.setdefault("closes", [])
    assert isinstance(closes, list)
    closes.append({"bead_id": argv[1], "argv": argv})
    _save(state)
    return 0


def main(argv: list[str]) -> int:
    state = _load()
    _log(state, argv)

    if argv in (
        ["hook", "--claim", "--drain-ack", "--json"],
        ["gc", "claim"],
    ):
        return _claim(state)
    if argv[:1] == ["bd"] and len(argv) >= 2:
        if argv[1] == "show" and len(argv) >= 3:
            bead = _bead(state, argv[2])
            print(json.dumps([] if bead is None else [bead], separators=(",", ":")))
            _save(state)
            return 0
        if argv[1] == "update":
            return _update(state, argv[1:])
        if argv[1] == "close":
            return _close(state, argv[1:])
    if argv == ["runtime", "drain-ack"]:
        state["drain_acks"] = int(state.get("drain_acks", 0)) + 1
        _save(state)
        return 0
    print(f"unsupported fake gc command: {' '.join(argv)}", file=sys.stderr)
    _save(state)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
