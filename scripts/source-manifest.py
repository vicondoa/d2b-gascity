#!/usr/bin/env python3
"""Write the deterministic source and package manifest for the flake."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


INPUTS = (
    ("gascity", "gascity"),
    ("gascityPacks", "gascity-packs"),
    ("beads", "beads"),
    ("dolt", "dolt"),
    ("llmAgents", "llm-agents"),
    ("goOfficial", "go-official"),
    ("nixpkgs", "nixpkgs"),
    ("packageNixpkgs", "nixpkgs-gas-city"),
)

RUNTIME_EXECUTABLES = (
    "bd",
    "copilot",
    "dolt",
    "gc",
    "gh",
    "git",
    "go",
    "nginx",
    "python3",
    "tinyauth",
)


def read_json(path: Path) -> Any:
    with path.open(encoding="ascii") as handle:
        return json.load(handle)


def locked_input(lock: dict[str, Any], node_name: str) -> dict[str, Any]:
    try:
        locked = lock["nodes"][node_name]["locked"]
    except (KeyError, TypeError) as error:
        raise SystemExit(f"missing locked flake input: {node_name}") from error

    source = None
    if locked.get("owner") and locked.get("repo"):
        source = f"{locked['owner']}/{locked['repo']}"

    revision = locked.get("rev") or locked.get("ref")
    if source is None or revision is None:
        raise SystemExit(f"incomplete locked flake input: {node_name}")

    result: dict[str, Any] = {
        "revision": revision,
        "source": source,
    }
    for key in ("narHash", "ref"):
        if key in locked:
            result[key] = locked[key]
    return result


def assert_ascii(value: Any, path: str = "manifest") -> None:
    if isinstance(value, str):
        try:
            value.encode("ascii")
        except UnicodeEncodeError as error:
            raise SystemExit(f"non-ASCII value at {path}") from error
    elif isinstance(value, dict):
        for key, child in value.items():
            assert_ascii(key, f"{path}.<key>")
            assert_ascii(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_ascii(child, f"{path}[{index}]")


def build_manifest(lock: dict[str, Any], packages: dict[str, Any]) -> dict[str, Any]:
    inputs = {
        output_name: locked_input(lock, node_name)
        for output_name, node_name in INPUTS
    }
    manifest = {
        "inputs": inputs,
        "packages": packages,
        "runtime": {
            "caBundle": "etc/ssl/certs/ca-bundle.crt",
            "executables": list(RUNTIME_EXECUTABLES),
        },
        "schemaVersion": 1,
    }
    assert_ascii(manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_manifest(read_json(args.lock), read_json(args.packages))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    args.output.write_text(f"{payload}\n", encoding="ascii", newline="\n")


if __name__ == "__main__":
    main()
