#!/usr/bin/env python3
"""Stateful gh fixture for convergent publication tests."""

from __future__ import annotations

import json
import os
import pathlib
import sys


EXPECTED_LIST_FIELDS = (
    "number,state,headRefName,baseRefName,headRefOid,"
    "headRepository,headRepositoryOwner,mergedAt,url"
)


def _state_path() -> pathlib.Path:
    explicit = os.environ.get("FAKE_GH_STATE")
    if explicit:
        return pathlib.Path(explicit)
    return pathlib.Path.cwd() / ".fake-gh-state.json"


def _load(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: pathlib.Path, state: dict[str, object]) -> None:
    path.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")


def _log(state: dict[str, object], argv: list[str]) -> None:
    calls = state.setdefault("calls", [])
    assert isinstance(calls, list)
    calls.append(argv)
    keys = state.setdefault("env_keys", [])
    assert isinstance(keys, list)
    keys.extend(sorted(set(os.environ) - set(keys)))
    attestations = state.setdefault("env_attestations", [])
    assert isinstance(attestations, list)
    attestations.append(
        {
            "gh_token_matches_fixture": os.environ.get("GH_TOKEN")
            == "fixture-token",
            "ambient_secret_keys_present": sorted(
                set(os.environ)
                & {
                    "CREDENTIALS_DIRECTORY",
                    "FAKE_GH_STATE",
                    "GITHUB_TOKEN",
                    "SSH_AUTH_SOCK",
                    "GIT_SSH_COMMAND",
                    "UNRELATED_SECRET",
                }
            ),
        }
    )


def _prs(state: dict[str, object]) -> list[dict[str, object]]:
    value = state.setdefault("prs", [])
    assert isinstance(value, list)
    return value


def _expected_branch(state: dict[str, object]) -> str | None:
    value = state.get("expected_branch")
    if isinstance(value, str) and value:
        return value
    records = _prs(state)
    if records and isinstance(records[0].get("headRefName"), str):
        return records[0]["headRefName"]
    return None


def _validate_list_args(state: dict[str, object], argv: list[str]) -> bool:
    branch = _expected_branch(state)
    expected = [
        "pr",
        "list",
        "--repo",
        "vicondoa/d2b",
        "--state",
        "all",
        "--head",
        branch or "",
        "--limit",
        "1000",
        "--json",
        EXPECTED_LIST_FIELDS,
    ]
    if argv == expected:
        return True
    state["argument_error"] = {
        "expected": expected,
        "actual": argv,
    }
    return False


def _create_pr(state: dict[str, object], argv: list[str]) -> dict[str, object]:
    def option(name: str) -> str:
        index = argv.index(name)
        return argv[index + 1]

    branch = option("--head")
    base = option("--base")
    head_sha = str(state.get("head_sha"))
    number = int(state.get("next_number", 1))
    state["next_number"] = number + 1
    record = {
        "number": number,
        "state": "OPEN",
        "headRefName": branch,
        "baseRefName": base,
        "headRefOid": head_sha,
        "headRepository": {"nameWithOwner": "vicondoa/d2b"},
        "headRepositoryOwner": {"login": "vicondoa"},
        "mergedAt": None,
        "url": f"https://github.com/vicondoa/d2b/pull/{number}",
        "title": "d2b-gascity publication",
    }
    _prs(state).append(record)
    return record


def main(argv: list[str]) -> int:
    path = _state_path()
    state = _load(path)
    _log(state, argv)

    if len(argv) >= 3 and argv[:2] == ["pr", "list"]:
        if not _validate_list_args(state, argv):
            print("unsupported pr list arguments", file=sys.stderr)
            _save(path, state)
            return 2
        if state.get("list_error"):
            print("list unavailable", file=sys.stderr)
            _save(path, state)
            return 1
        payload = state.get("list_payload", _prs(state))
        print(json.dumps(payload, separators=(",", ":")))
        _save(path, state)
        return 0

    if len(argv) >= 3 and argv[:2] == ["pr", "create"]:
        mode = state.get("create_mode", "success")
        record = _create_pr(state, argv)
        _save(path, state)
        if mode == "ambiguous":
            print("create response unavailable", file=sys.stderr)
            return 1
        if mode == "failure":
            _prs(state).pop()
            _save(path, state)
            print("create failed", file=sys.stderr)
            return 1
        print(record["url"])
        return 0

    print(f"unsupported fake gh command: {' '.join(argv)}", file=sys.stderr)
    _save(path, state)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
