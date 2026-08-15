#!/usr/bin/env python3
"""Stateful git fixture for publication and branch-race tests."""

from __future__ import annotations

import base64
import hmac
import json
import os
import pathlib
import sys


EXPECTED_AUTHORIZATION = (
    "Authorization: Basic "
    + base64.b64encode(b"x-access-token:fixture-token").decode("ascii")
)
EXPECTED_REMOTE_CONFIG = {
    "core.hooksPath": "/dev/null",
    "push.followTags": "false",
    "credential.helper": "",
    "core.sshCommand": "/bin/false",
    "http.proxy": "",
    "http.sslVerify": "true",
    "http.sslCAInfo": "",
    "http.sslCert": "",
    "http.sslKey": "",
}
AMBIENT_SECRET_KEYS = {
    "CREDENTIALS_DIRECTORY",
    "FAKE_GIT_STATE",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GIT_SSH_COMMAND",
    "SSH_AUTH_SOCK",
    "UNRELATED_SECRET",
}


def _state_path() -> pathlib.Path:
    explicit = os.environ.get("FAKE_GIT_STATE")
    if explicit:
        return pathlib.Path(explicit)
    return pathlib.Path.cwd() / ".fake-git-state.json"


def _load(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: pathlib.Path, state: dict[str, object]) -> None:
    path.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")


def _log(
    state: dict[str, object],
    argv: list[str],
    command: list[str],
) -> None:
    calls = state.setdefault("calls", [])
    assert isinstance(calls, list)
    calls.append(argv)
    records = state.setdefault("env_records", [])
    assert isinstance(records, list)
    values = "\x00".join(os.environ.values())
    config_values = {
        index: os.environ.get(f"GIT_CONFIG_VALUE_{index}", "")
        for index in range(int(os.environ.get("GIT_CONFIG_COUNT", "0") or "0"))
    }
    config = {
        os.environ.get(f"GIT_CONFIG_KEY_{index}", ""): value
        for index, value in config_values.items()
    }
    is_remote = bool(
        command
        and command[0] in {"fetch", "ls-remote", "push"}
        and any(item.startswith("https://github.com/") for item in command)
    )
    records.append(
        {
            "argv": argv,
            "env_keys": sorted(os.environ),
            "remote": is_remote,
            "git_auth_header_valid": hmac.compare_digest(
                os.environ.get("GIT_CONFIG_COUNT", ""),
                "10",
            )
            and all(config.get(key) == value for key, value in EXPECTED_REMOTE_CONFIG.items())
            and hmac.compare_digest(
                config.get("http.https://github.com/.extraHeader", ""),
                EXPECTED_AUTHORIZATION,
            ),
            "ambient_secret_keys_present": sorted(
                set(os.environ) & AMBIENT_SECRET_KEYS
            ),
            "token_literal_present": "fixture-token" in values,
            "token_in_argv": any("fixture-token" in item for item in argv),
            "hooks_disabled": config_values.get(
                next(
                    (
                        index
                        for index in config_values
                        if os.environ.get(f"GIT_CONFIG_KEY_{index}") == "core.hooksPath"
                    ),
                    -1,
                ),
                "",
            )
            == "/dev/null",
            "follow_tags_disabled": config_values.get(
                next(
                    (
                        index
                        for index in config_values
                        if os.environ.get(f"GIT_CONFIG_KEY_{index}") == "push.followTags"
                    ),
                    -1,
                ),
                "",
            )
            == "false",
        }
    )


def main(argv: list[str]) -> int:
    path = _state_path()
    state = _load(path)

    if len(argv) >= 3 and argv[0] == "-C":
        worktree = argv[1]
        command = argv[2:]
        git_dir = None
    elif len(argv) >= 3 and argv[0] == "--git-dir":
        worktree = str(pathlib.Path.cwd())
        command = argv[2:]
        git_dir = argv[1]
    else:
        worktree = str(pathlib.Path.cwd())
        command = argv
        git_dir = None
    _log(state, argv, command)

    if command == ["rev-parse", "--show-toplevel"]:
        print(worktree)
    elif command == ["rev-parse", "HEAD"]:
        print(state["head_sha"])
    elif command == ["remote", "get-url", "--all", "origin"]:
        urls = state.get("remote_urls")
        if not isinstance(urls, list):
            urls = [state.get("remote_url", "https://github.com/vicondoa/d2b.git")]
        for url in urls:
            print(url)
    elif command == ["remote", "get-url", "--push", "--all", "origin"]:
        urls = state.get("push_urls")
        if not isinstance(urls, list):
            urls = [
                state.get(
                    "push_url",
                    state.get("remote_url", "https://github.com/vicondoa/d2b.git"),
                )
            ]
        for url in urls:
            print(url)
    elif command == ["status", "--porcelain"]:
        print(state.get("status", ""))
    elif command == ["replace", "-l"]:
        for replacement in state.get("replace_refs", []):
            print(replacement)
    elif command == ["rev-parse", "--git-path", "info/grafts"]:
        print(pathlib.Path(worktree) / ".git" / "info" / "grafts")
    elif command[:3] == ["init", "--bare", "--quiet"] and len(command) == 4:
        state["trusted_git_dir"] = command[3]
    elif command and command[0] == "fetch":
        spec = next(
            (item for item in command[1:] if ":refs/" in item),
            "",
        )
        source = next(
            (
                item
                for item in command[1:]
                if not item.startswith("-") and item != spec
            ),
            "",
        )
        if source.startswith("https://github.com/"):
            if not spec.endswith("refs/d2b/base"):
                print("unsupported remote fetch", file=sys.stderr)
                _save(path, state)
                return 2
            if state.get("fetch_error"):
                print("fetch failed", file=sys.stderr)
                _save(path, state)
                return 1
            state["fetched"] = True
            state["tracking_base_sha"] = state.get(
                "current_base_sha",
                state.get("base_sha"),
            )
        else:
            expected = state.get("head_sha")
            if spec != f"{expected}:refs/d2b/head":
                print("unsupported local head import", file=sys.stderr)
                _save(path, state)
                return 2
            state["imported_head"] = expected
    elif command[0] == "ls-remote" and len(command) == 3:
        reference = command[2]
        if reference == "refs/heads/v3":
            base_sha = state.get("current_base_sha", state.get("base_sha"))
            if base_sha:
                print(f"{base_sha}\t{reference}")
        else:
            if (
                state.get("publication_remote_observation_error")
                and state.get("remote_branch")
            ):
                print("publication remote unavailable", file=sys.stderr)
                _save(path, state)
                return 1
            remote_branch = state.get("remote_branch")
            if remote_branch:
                print(f"{remote_branch}\t{reference}")
    elif (
        command[:2] == ["rev-parse", "--verify"]
        and len(command) == 3
        and command[2] in {
            "refs/remotes/origin/v3^{commit}",
            "refs/d2b/base^{commit}",
            "refs/d2b/head^{commit}",
        }
    ):
        if command[2] == "refs/d2b/head^{commit}":
            print(state.get("imported_head", state.get("head_sha", "")))
        else:
            print(state.get("tracking_base_sha", state.get("base_sha", "")))
    elif command[:2] == ["merge-base", "--is-ancestor"] and len(command) == 4:
        ancestor, descendant = command[2:]
        base_sha = state.get("base_sha")
        current_base_sha = state.get("current_base_sha", base_sha)
        head_sha = state.get("head_sha")
        if (
            ancestor == base_sha
            and descendant == current_base_sha
            and not state.get("base_on_v3", True)
        ):
            _save(path, state)
            return 1
        if (
            ancestor == base_sha
            and descendant in {head_sha, "refs/d2b/head"}
            and not state.get("head_descends_from_base", True)
        ):
            _save(path, state)
            return 1
    elif command[:2] == ["push", "--porcelain"] and len(command) == 4:
        _, _, remote, spec = command
        if not remote.startswith("https://github.com/") or ":refs/heads/" not in spec:
            print("unsupported push", file=sys.stderr)
            _save(path, state)
            return 2
        config_values = {
            os.environ.get(f"GIT_CONFIG_KEY_{index}", ""): os.environ.get(
                f"GIT_CONFIG_VALUE_{index}", ""
            )
            for index in range(int(os.environ.get("GIT_CONFIG_COUNT", "0") or "0"))
        }
        if config_values.get("core.hooksPath") != "/dev/null":
            state["hook_ran"] = True
            _save(path, state)
            print("pre-push hook ran", file=sys.stderr)
            return 1
        state["hook_ran"] = False
        state["push_follow_tags"] = config_values.get("push.followTags")
        sha, _ = spec.split(":", 1)
        if state.get("race_on_push") and not state.get("race_applied"):
            state["remote_branch"] = state.get("race_sha", "c" * 40)
            state["race_applied"] = True
        pushed_refs = state.setdefault("pushed_refs", [])
        assert isinstance(pushed_refs, list)
        pushed_refs.append(spec.split(":", 1)[1])
        existing = state.get("remote_branch")
        if existing:
            descendants = state.get("descendants", {})
            if (
                isinstance(descendants, dict)
                and sha in descendants.get(existing, [])
            ):
                state["fast_forward_possible"] = True
            state["rejected_pushes"] = int(state.get("rejected_pushes", 0)) + 1
            print("create-only branch update rejected", file=sys.stderr)
            _save(path, state)
            return 1
        state["remote_branch"] = sha
        state["pushes"] = int(state.get("pushes", 0)) + 1
        if state.get("push_mode") == "ambiguous" or state.get("ambiguous_push"):
            print("push response unavailable", file=sys.stderr)
            _save(path, state)
            return 1
        print(f" refs/heads/{spec.rsplit('/', 1)[-1]}")
    else:
        print(f"unsupported fake git command: {' '.join(argv)}", file=sys.stderr)
        _save(path, state)
        return 2

    _save(path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
