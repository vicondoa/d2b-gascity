#!/usr/bin/env python3
"""Run one bounded Copilot ACP session with an immutable provider profile."""

from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from typing import Any


COPILOT_VERSION = "1.0.79"
DEFAULT_SELECTION_PATH = "/var/lib/d2b-gascity/config/provider-selection.json"
MAX_CREDENTIAL_BYTES = 8192
MAX_ACP_LINE_BYTES = 64 * 1024
DEFAULT_PROBE_TIMEOUT = 10.0

PROFILES: dict[str, dict[str, str]] = {
    "planning-sol": {
        "model": "gpt-5.6-sol",
        "context": "long_context",
        "effort": "xhigh",
    },
    "review-sol": {
        "model": "gpt-5.6-sol",
        "context": "long_context",
        "effort": "xhigh",
    },
    "review-luna": {
        "model": "gpt-5.6-luna",
        "context": "long_context",
        "effort": "max",
    },
    "code-luna": {
        "model": "gpt-5.6-luna",
        "context": "default",
        "effort": "max",
    },
}
TOOL_POLICIES = {
    "review": "view,search",
    "planning": "view,search,apply_patch",
    "coding": "bash,view,search,apply_patch",
}
PROFILE_POLICIES = {
    "planning-sol": "planning",
    "review": "review",
    "review-sol": "review",
    "review-luna": "review",
    "code-luna": "coding",
}
PROFILE_PINS = {
    "copilot": COPILOT_VERSION,
    "profiles": {
        name: {
            "model": values["model"],
            "context": values["context"],
            "effort": values["effort"],
        }
        for name, values in PROFILES.items()
    },
}
SAFE_ENV_NAMES = frozenset(
    {
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "HOME",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "NO_COLOR",
        "NO_PROXY",
        "PATH",
        "PWD",
        "SSL_CERT_FILE",
        "TERM",
        "TMPDIR",
        "XDG_RUNTIME_DIR",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
)
DENIED_FIXED_PATHS = (
    "/run/credentials",
    "/var/lib/d2b-gascity/gc",
    "/var/lib/d2b-gascity/config",
    "/var/lib/d2b-gascity/state",
    "/var/lib/d2b-gascity/cache",
    "/etc/nixos",
    "/etc/ssh",
    "/root/.ssh",
    "/root/.gnupg",
    "/root/.config/gh",
    "/root/.config/git",
)
DENIED_ENV_PATHS = (
    "GC_HOME",
    "GIT_CONFIG_GLOBAL",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
)
STOP_REASONS = frozenset(
    {
        "cancelled",
        "end_turn",
        "max_tokens",
        "max_turn_requests",
        "refusal",
    }
)


class ProviderError(RuntimeError):
    """An operator-safe typed provider failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ACPReader:
    def __init__(self, stream: Any):
        self._fd = stream.fileno()
        self._buffer = bytearray()

    def read(self, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                line = bytes(self._buffer[:newline])
                del self._buffer[: newline + 1]
                if line.endswith(b"\r"):
                    line = line[:-1]
                if not line:
                    raise ProviderError("malformed")
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ProviderError("malformed") from error
                if not isinstance(value, dict):
                    raise ProviderError("malformed")
                return value

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError("timeout")
            ready, _, _ = select.select([self._fd], [], [], remaining)
            if not ready:
                raise ProviderError("timeout")
            data = os.read(self._fd, 64 * 1024)
            if not data:
                raise ProviderError("closed")
            self._buffer.extend(data)
            if len(self._buffer) > MAX_ACP_LINE_BYTES:
                raise ProviderError("malformed")


def _safe_absolute_path(value: str, label: str) -> pathlib.Path:
    if not value or "\x00" in value:
        raise ProviderError(f"{label}-invalid")
    if not value.startswith("/") or value.startswith("//"):
        raise ProviderError(f"{label}-invalid")
    if "//" in value[1:]:
        raise ProviderError(f"{label}-invalid")
    path = pathlib.PurePosixPath(value)
    if any(part in {".", ".."} for part in path.parts):
        raise ProviderError(f"{label}-invalid")
    return pathlib.Path(value)


def _owned_directory(path: pathlib.Path, label: str) -> None:
    try:
        info = path.lstat()
    except OSError as error:
        raise ProviderError(f"{label}-invalid") from error
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o022
    ):
        raise ProviderError(f"{label}-invalid")


def _credential_path(argument: str | None) -> pathlib.Path:
    if argument is not None:
        return _safe_absolute_path(argument, "credential")
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        raise ProviderError("credential-invalid")
    root = _safe_absolute_path(directory, "credential")
    return root / "copilot-token"


def _credential_owner_allowed(owner: int, *, projected: bool) -> bool:
    return owner == os.geteuid() or (projected and owner == 0)


def _read_credential(argument: str | None) -> str:
    projected = argument is None
    path = _credential_path(argument)
    try:
        info = path.lstat()
    except OSError as error:
        raise ProviderError("credential-invalid") from error
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or not _credential_owner_allowed(info.st_uid, projected=projected)
        or info.st_mode & 0o077
        or info.st_mode & 0o111
        or not info.st_mode & 0o400
        or info.st_size <= 0
        or info.st_size > MAX_CREDENTIAL_BYTES
    ):
        raise ProviderError("credential-invalid")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if (
                stat.S_ISLNK(opened.st_mode)
                or not stat.S_ISREG(opened.st_mode)
                or not _credential_owner_allowed(
                    opened.st_uid,
                    projected=projected,
                )
                or opened.st_mode & 0o077
                or opened.st_mode & 0o111
                or not opened.st_mode & 0o400
                or opened.st_size <= 0
                or opened.st_size > MAX_CREDENTIAL_BYTES
                or opened.st_dev != info.st_dev
                or opened.st_ino != info.st_ino
            ):
                raise ProviderError("credential-invalid")
            data = stream.read(MAX_CREDENTIAL_BYTES + 1)
    except ProviderError:
        raise
    except OSError as error:
        raise ProviderError("credential-invalid") from error
    if len(data) == 0 or len(data) > MAX_CREDENTIAL_BYTES:
        raise ProviderError("credential-invalid")
    try:
        token = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProviderError("credential-invalid") from error
    token = token.rstrip("\r\n")
    if not token or any(ord(character) < 0x21 or ord(character) > 0x7E for character in token):
        raise ProviderError("credential-invalid")
    return token


def _selection_path(argument: str | None) -> pathlib.Path:
    path = _safe_absolute_path(
        argument or DEFAULT_SELECTION_PATH,
        "selection",
    )
    if path == pathlib.Path("/"):
        raise ProviderError("selection-invalid")
    _owned_directory(path.parent, "selection")
    try:
        info = path.lstat()
    except FileNotFoundError:
        return path
    except OSError as error:
        raise ProviderError("selection-invalid") from error
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
        or info.st_mode & 0o111
        or not info.st_mode & 0o400
    ):
        raise ProviderError("selection-invalid")
    return path


def _read_selection(path: pathlib.Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderError("selection-invalid") from error
    if not isinstance(value, dict):
        raise ProviderError("selection-invalid")
    if set(value) != {"version", "pins", "coding", "review", "ready", "error_code"}:
        raise ProviderError("selection-invalid")
    if (
        value["version"] != 1
        or value["pins"] != PROFILE_PINS
        or value["coding"] != "code-luna"
        or value["review"] not in {"review-sol", "review-luna"}
        or value["ready"] is not True
        or value["error_code"] is not None
    ):
        raise ProviderError("selection-invalid")
    return value


def _selection_payload(
    review: str | None,
    error_code: str | None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "pins": copy.deepcopy(PROFILE_PINS),
        "coding": "code-luna",
        "review": review,
        "ready": review is not None and error_code is None,
        "error_code": error_code,
    }


def _write_selection(path: pathlib.Path, value: Mapping[str, Any]) -> None:
    _owned_directory(path.parent, "selection")
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    except OSError as error:
        raise ProviderError("selection-invalid") from error
    if info is not None and (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ProviderError("selection-invalid")
    temporary: pathlib.Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".provider-selection-",
            dir=path.parent,
        )
        temporary = pathlib.Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise ProviderError("selection-write") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _worktree(argument: str | None) -> pathlib.Path:
    raw = argument or os.getcwd()
    if not raw.startswith("/"):
        raw = str(pathlib.Path(raw).resolve())
    try:
        path = pathlib.Path(raw).resolve(strict=True)
    except OSError as error:
        raise ProviderError("worktree-invalid") from error
    if not path.is_dir():
        raise ProviderError("worktree-invalid")
    return path


def _copilot_path(argument: str | None) -> pathlib.Path:
    candidate = argument or shutil.which("copilot")
    if not candidate:
        raise ProviderError("unavailable")
    if not candidate.startswith("/"):
        candidate = shutil.which(candidate) or candidate
    try:
        path = pathlib.Path(candidate).resolve(strict=True)
        info = path.stat()
    except OSError as error:
        raise ProviderError("unavailable") from error
    if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK):
        raise ProviderError("unavailable")
    return path


def _profile_for_request(
    requested: str,
    policy: str,
    selection: pathlib.Path | None,
) -> str:
    if requested == "review":
        if selection is None:
            raise ProviderError("selection-invalid")
        requested = str(_read_selection(selection)["review"])
    if requested not in PROFILES or PROFILE_POLICIES.get(requested) != policy:
        raise ProviderError("profile-invalid")
    return requested


def _runtime_directory(argument: str | None) -> pathlib.Path:
    value = argument or os.environ.get("XDG_RUNTIME_DIR")
    if not value:
        raise ProviderError("runtime-invalid")
    path = _safe_absolute_path(value, "runtime")
    _owned_directory(path, "runtime")
    return path


def _settings(
    profile: str,
    worktree: pathlib.Path,
) -> dict[str, Any]:
    denied = list(DENIED_FIXED_PATHS)
    for name in DENIED_ENV_PATHS:
        value = os.environ.get(name)
        if value and value.startswith("/"):
            try:
                denied.append(str(_safe_absolute_path(value, "settings")))
            except ProviderError:
                continue
    home = os.environ.get("HOME")
    if home and home.startswith("/"):
        for suffix in (".ssh", ".gnupg", ".config/gh", ".config/git", ".aws"):
            denied.append(str(pathlib.Path(home) / suffix))
    unique_denied = list(dict.fromkeys(denied))
    values = PROFILES[profile]
    return {
        "model": values["model"],
        "contextTier": values["context"],
        "experimental": True,
        "autoUpdate": False,
        "memory": False,
        "sandbox": {
            "enabled": True,
            "addCurrentWorkingDirectory": True,
            "allowDevToolAccess": False,
            "allowBypass": False,
            "auth": {"git": False, "gh": False},
            "sandboxMcpServers": True,
            "sandboxLspServers": True,
            "userPolicy": {
                "filesystem": {
                    "deniedPaths": unique_denied,
                    "clearPolicyOnExit": True,
                },
                "network": {
                    "allowOutbound": True,
                    "allowLocalNetwork": False,
                },
            },
        },
    }


def _create_home(
    runtime: pathlib.Path,
    profile: str,
    worktree: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path]:
    home: pathlib.Path | None = None
    try:
        home = pathlib.Path(tempfile.mkdtemp(prefix="d2b-copilot-", dir=runtime))
        os.chmod(home, 0o700)
        settings_path = home / "settings.json"
        descriptor = os.open(
            settings_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                _settings(profile, worktree),
                stream,
                separators=(",", ":"),
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        return home, settings_path
    except OSError as error:
        if home is not None:
            shutil.rmtree(home, ignore_errors=True)
        raise ProviderError("settings-invalid") from error


def _child_environment(
    token: str,
    home: pathlib.Path,
    worktree: pathlib.Path,
) -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in SAFE_ENV_NAMES
    }
    environment.setdefault("PATH", os.defpath)
    environment["HOME"] = str(home)
    environment["PWD"] = str(worktree)
    environment["COPILOT_HOME"] = str(home)
    environment["COPILOT_GITHUB_TOKEN"] = token
    return environment


def _child_arguments(
    executable: pathlib.Path,
    profile: str,
    policy: str,
    worktree: pathlib.Path,
) -> list[str]:
    values = PROFILES[profile]
    return [
        str(executable),
        "--acp",
        "--experimental",
        "--model",
        values["model"],
        "--context",
        values["context"],
        "--effort",
        values["effort"],
        "--no-custom-instructions",
        "--no-auto-update",
        "--disable-builtin-mcps",
        "--no-remote",
        "--no-remote-export",
        "--no-ask-user",
        "--no-bash-env",
        "--secret-env-vars",
        "COPILOT_GITHUB_TOKEN",
        "--available-tools",
        TOOL_POLICIES[policy],
        "--deny-tool",
        "shell(gh)",
        "--deny-tool",
        "shell(gh *)",
        "--deny-tool",
        "shell(git push)",
        "--deny-tool",
        "shell(git push *)",
        "--deny-tool",
        "shell(discord)",
        "--deny-tool",
        "shell(discord *)",
        "-C",
        str(worktree),
    ]


def _probe_arguments(
    executable: pathlib.Path,
    profile: str,
    worktree: pathlib.Path,
) -> list[str]:
    arguments = _child_arguments(executable, profile, "review", worktree)
    index = arguments.index("--available-tools")
    arguments[index + 1] = ""
    return arguments


def _signal_group(process: subprocess.Popen[Any], signum: int) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def _stop_group(process: subprocess.Popen[Any]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired as error:
            raise ProviderError("cleanup") from error
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return
    except PermissionError as error:
        raise ProviderError("cleanup") from error
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.02)
    raise ProviderError("cleanup")


def _run(
    args: argparse.Namespace,
) -> int:
    selection = (
        _selection_path(args.selection_path)
        if args.profile == "review"
        else None
    )
    token = _read_credential(args.credential_file)
    worktree = _worktree(args.worktree)
    runtime = _runtime_directory(args.runtime_dir)
    profile = _profile_for_request(args.profile, args.tool_policy, selection)
    executable = _copilot_path(args.copilot)
    home, _ = _create_home(runtime, profile, worktree)
    environment = _child_environment(token, home, worktree)
    process: subprocess.Popen[Any] | None = None
    previous_handlers: dict[int, Any] = {}

    try:
        process = subprocess.Popen(
            _child_arguments(executable, profile, args.tool_policy, worktree),
            cwd=worktree,
            env=environment,
            stdin=None,
            stdout=None,
            stderr=None,
            start_new_session=True,
        )

        def forward(signum: int, _frame: Any) -> None:
            if process is not None:
                _signal_group(process, signum)

        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, forward)
        return process.wait()
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if process is not None:
            _stop_group(process)
        shutil.rmtree(home, ignore_errors=False)


def _frame(value: Mapping[str, Any]) -> bytes:
    encoded = json.dumps(value, separators=(",", ":")).encode("utf-8")
    if b"\n" in encoded or b"\r" in encoded:
        raise ProviderError("malformed")
    return encoded + b"\n"


def _send(process: subprocess.Popen[Any], value: Mapping[str, Any]) -> None:
    if process.stdin is None:
        raise ProviderError("closed")
    try:
        process.stdin.write(_frame(value))
        process.stdin.flush()
    except (BrokenPipeError, OSError) as error:
        raise ProviderError("closed") from error


def _classify(value: object) -> str:
    if isinstance(value, ProviderError):
        return value.code
    text = str(value).lower()
    if any(marker in text for marker in ("authentication", "unauthorized", "invalid token", "401", "403")):
        return "auth"
    if any(marker in text for marker in ("quota", "rate limit", "429", "credits")):
        return "quota"
    if any(marker in text for marker in ("network", "connection", "dns", "proxy", "tls")):
        return "network"
    if any(marker in text for marker in ("timeout", "timed out")):
        return "timeout"
    if any(marker in text for marker in ("unsupported", "not supported", "unknown model", "model not found")):
        return "unsupported"
    if "unavailable" in text:
        return "unavailable"
    if any(marker in text for marker in ("malformed", "invalid json", "protocol", "parse")):
        return "malformed"
    if any(marker in text for marker in ("closed", "eof", "end of file")):
        return "closed"
    return "unknown"


def _response(
    reader: ACPReader,
    request_id: int,
    timeout: float,
) -> dict[str, Any]:
    while True:
        value = reader.read(timeout)
        if "method" in value:
            if "id" in value:
                raise ProviderError("malformed")
            continue
        if value.get("jsonrpc") != "2.0" or value.get("id") != request_id:
            raise ProviderError("malformed")
        if "error" in value:
            raise ProviderError(_classify(value["error"]))
        result = value.get("result")
        if not isinstance(result, dict):
            raise ProviderError("malformed")
        return result


def _model_observations(value: object) -> tuple[list[str], list[str]]:
    models: list[str] = []
    contexts: list[str] = []

    def visit(current: object) -> None:
        if isinstance(current, dict):
            for key, nested in current.items():
                if key in {
                    "currentModelId",
                    "current_model_id",
                    "effectiveModel",
                    "effective_model",
                }:
                    if not isinstance(nested, str) or not nested:
                        raise ProviderError("malformed")
                    models.append(nested)
                elif key in {"contextTier", "context_tier"}:
                    if not isinstance(nested, str) or not nested:
                        raise ProviderError("malformed")
                    contexts.append(nested)
                else:
                    visit(nested)
        elif isinstance(current, list):
            for nested in current:
                visit(nested)

    visit(value)
    return models, contexts


def _probe_exchange(
    process: subprocess.Popen[Any],
    profile: str,
    worktree: pathlib.Path,
    timeout: float,
) -> None:
    reader = ACPReader(process.stdout)
    observations: list[object] = []
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": 1,
            "clientCapabilities": {},
            "clientInfo": {"name": "d2b-gascity-readiness", "version": "1"},
        },
    }
    _send(process, initialize)
    observations.append(_response(reader, 1, timeout))
    new_session = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "session/new",
        "params": {"cwd": str(worktree), "mcpServers": []},
    }
    _send(process, new_session)
    session = _response(reader, 2, timeout)
    session_id = session.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        raise ProviderError("malformed")
    observations.append(session)
    prompt = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "session/prompt",
        "params": {
            "sessionId": session_id,
            "prompt": [
                {
                    "type": "text",
                    "text": "Readiness probe. Report readiness and stop.",
                }
            ],
        },
    }
    _send(process, prompt)
    final = _response(reader, 3, timeout)
    observations.append(final)
    stop_reason = final.get("stopReason")
    if stop_reason not in STOP_REASONS:
        raise ProviderError("malformed")

    expected = PROFILES[profile]
    reported_models: list[str] = []
    reported_contexts: list[str] = []
    for observation in observations:
        models, contexts = _model_observations(observation)
        reported_models.extend(models)
        reported_contexts.extend(contexts)
    if reported_models and set(reported_models) != {expected["model"]}:
        raise ProviderError("unsupported")
    if reported_contexts and set(reported_contexts) != {expected["context"]}:
        raise ProviderError("malformed")


def _probe(
    profile: str,
    executable: pathlib.Path,
    token: str,
    runtime: pathlib.Path,
    worktree: pathlib.Path,
    timeout: float,
) -> str | None:
    home: pathlib.Path | None = None
    process: subprocess.Popen[Any] | None = None
    error_code: str | None = None
    try:
        home, _ = _create_home(runtime, profile, worktree)
        environment = _child_environment(token, home, worktree)
        process = subprocess.Popen(
            _probe_arguments(executable, profile, worktree),
            cwd=worktree,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        _probe_exchange(process, profile, worktree, timeout)
        error_code = None
    except ProviderError as error:
        error_code = error.code
    except (OSError, ValueError):
        error_code = "unavailable"
    finally:
        if process is not None:
            try:
                _stop_group(process)
            except ProviderError:
                pass
            if process.stderr is not None:
                try:
                    stderr = process.stderr.read(MAX_ACP_LINE_BYTES)
                except OSError:
                    stderr = b""
                if error_code in {"closed", "unknown"} and stderr:
                    error_code = _classify(stderr.decode("utf-8", errors="replace"))
                process.stderr.close()
            if process.stdout is not None:
                process.stdout.close()
            if process.stdin is not None:
                process.stdin.close()
        if home is not None:
            try:
                shutil.rmtree(home)
            except OSError:
                if error_code is None:
                    error_code = "cleanup"
    return error_code


def _readiness(args: argparse.Namespace) -> int:
    try:
        selection = _selection_path(args.selection_path)
    except ProviderError as error:
        payload = _selection_payload(None, error.code)
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 1

    error_code: str | None = None
    review: str | None = None
    try:
        token = _read_credential(args.credential_file)
        worktree = _worktree(args.worktree)
        runtime = _runtime_directory(args.runtime_dir)
        executable = _copilot_path(args.copilot)
        coding_error = _probe(
            "code-luna",
            executable,
            token,
            runtime,
            worktree,
            args.timeout,
        )
        if coding_error is not None:
            error_code = coding_error
        else:
            sol_error = _probe(
                "review-sol",
                executable,
                token,
                runtime,
                worktree,
                args.timeout,
            )
            if sol_error is None:
                error_code = None
                review = "review-sol"
            elif sol_error in {"unsupported", "unavailable"}:
                fallback_error = _probe(
                    "review-luna",
                    executable,
                    token,
                    runtime,
                    worktree,
                    args.timeout,
                )
                if fallback_error is None:
                    error_code = None
                    review = "review-luna"
                else:
                    error_code = fallback_error
            else:
                error_code = sol_error
    except ProviderError as error:
        error_code = error.code

    payload = _selection_payload(review, error_code)
    try:
        _write_selection(selection, payload)
    except ProviderError as error:
        payload = _selection_payload(None, error.code)
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 1
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0 if payload["ready"] else 1


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--copilot", help=argparse.SUPPRESS)
    parser.add_argument("--credential-file", help=argparse.SUPPRESS)
    parser.add_argument("--runtime-dir", help=argparse.SUPPRESS)
    parser.add_argument("--worktree", help="Assigned worktree.")
    parser.add_argument(
        "--selection-path",
        default=DEFAULT_SELECTION_PATH,
        help="Machine-local readiness selection path.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_PROBE_TIMEOUT,
        help="Bound the readiness ACP exchange.",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    run = subparsers.add_parser("run", help="Run one ACP session.")
    _common_arguments(run)
    run.add_argument(
        "--profile",
        choices=("planning-sol", "review", "review-sol", "review-luna", "code-luna"),
        required=True,
    )
    run.add_argument(
        "--tool-policy",
        choices=tuple(TOOL_POLICIES),
        required=True,
    )
    run.set_defaults(handler=_run)

    readiness = subparsers.add_parser(
        "readiness",
        help="Select review readiness once for the service generation.",
    )
    _common_arguments(readiness)
    readiness.set_defaults(handler=_readiness)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except ProviderError as error:
        if args.operation == "readiness":
            payload = _selection_payload(None, error.code)
            print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            return 1
        print(f"d2b-gascity-copilot-provider: {error.code}", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        if args.operation == "readiness":
            payload = _selection_payload(None, "unknown")
            print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            return 1
        print("d2b-gascity-copilot-provider: unknown", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
