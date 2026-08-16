#!/usr/bin/env python3
"""Offline fake gc for the Discord import helper tests."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys


def main() -> int:
    log_path = pathlib.Path(os.environ["GC_HOME"]) / "fake-gc.jsonl"
    argv = sys.argv[1:]
    stdin = sys.stdin.buffer.read()
    event = {
        "argv": argv,
        "stdin_present": bool(stdin),
        "stdin_sha256": hashlib.sha256(stdin).hexdigest() if stdin else None,
        "environment": {
            "gc_home": os.environ.get("GC_HOME"),
            "unrelated_secret_present": "UNRELATED_SECRET" in os.environ,
            "github_token_present": "GITHUB_TOKEN" in os.environ,
        },
    }
    if "--city" in argv:
        return 7
    if argv[:2] == ["discord", "import-app"]:
        if "--bot-token-file" not in argv:
            return 2
        index = argv.index("--bot-token-file")
        if argv[index + 1 : index + 2] != ["/dev/stdin"]:
            return 3
        event["kind"] = "import-app"
        sys.stdout.buffer.write(stdin)
    elif argv[:2] == ["discord", "bind-dm"]:
        if stdin:
            return 4
        event["kind"] = "bind-dm"
    elif "sync-commands" in argv or "publish" in argv:
        event["kind"] = "forbidden-publication"
        _append(log_path, event)
        return 5
    else:
        return 6
    _append(log_path, event)
    return 0


def _append(path: pathlib.Path, event: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
