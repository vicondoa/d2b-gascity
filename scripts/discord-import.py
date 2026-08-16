#!/usr/bin/env python3
"""Import the official Discord app and bind explicitly authorized DMs."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import stat
import subprocess
import sys
from collections.abc import Sequence


MAX_TOKEN_BYTES = 4096
COMMAND_TIMEOUT_SECONDS = 120
SNOWFLAKE = re.compile(r"^[0-9]{17,20}$")
PUBLIC_KEY = re.compile(r"^[0-9a-fA-F]{64}$")
SESSION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
SAFE_ENV_NAMES = frozenset(
    {
        "HOME",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "NO_COLOR",
        "NO_PROXY",
        "PATH",
        "SSL_CERT_FILE",
        "TERM",
        "TMPDIR",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
        "XDG_STATE_HOME",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
)


class DiscordImportError(ValueError):
    """A safe, operator-facing validation or command error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _reject_symlink_components(path: pathlib.Path) -> None:
    current = pathlib.Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise DiscordImportError("unsafe-path")


def _safe_existing_path(value: str, label: str) -> pathlib.Path:
    if (
        not value
        or "\x00" in value
        or "\n" in value
        or "\r" in value
        or value == "/"
        or value.startswith("//")
        or "//" in value[1:]
    ):
        raise DiscordImportError(f"unsafe-{label}-path")
    path = pathlib.Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise DiscordImportError(f"unsafe-{label}-path")
    try:
        _reject_symlink_components(path)
        path.lstat()
    except (OSError, ValueError):
        raise DiscordImportError(f"invalid-{label}-path") from None
    return path


def _owner_is_trusted(uid: int) -> bool:
    return uid in {os.getuid(), 0}


def _validate_directory(
    value: str,
    label: str,
    *,
    private: bool = False,
) -> pathlib.Path:
    path = _safe_existing_path(value, label)
    try:
        info = path.stat()
    except OSError:
        raise DiscordImportError(f"invalid-{label}-path") from None
    if not stat.S_ISDIR(info.st_mode) or not _owner_is_trusted(info.st_uid):
        raise DiscordImportError(f"unsafe-{label}-path")
    if (private and info.st_mode & 0o077) or info.st_mode & 0o022:
        raise DiscordImportError(f"unsafe-{label}-path")
    return path


def _validate_executable(value: str) -> pathlib.Path:
    path = _safe_existing_path(value, "gc")
    try:
        info = path.stat()
    except OSError:
        raise DiscordImportError("invalid-gc-path") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or not _owner_is_trusted(info.st_uid)
        or info.st_mode & 0o022
        or not info.st_mode & 0o111
    ):
        raise DiscordImportError("unsafe-gc-path")
    return path


def _read_token(value: str) -> str:
    path = _safe_existing_path(value, "token")
    try:
        info = path.stat()
    except OSError:
        raise DiscordImportError("invalid-token-file") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or not _owner_is_trusted(info.st_uid)
        or info.st_mode & 0o077
        or info.st_size <= 0
        or info.st_size > MAX_TOKEN_BYTES
    ):
        raise DiscordImportError("unsafe-token-file")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                opened.st_dev != info.st_dev
                or opened.st_ino != info.st_ino
                or opened.st_size != info.st_size
            ):
                raise DiscordImportError("unsafe-token-file")
            raw = stream.read(MAX_TOKEN_BYTES + 1)
    except DiscordImportError:
        raise
    except (OSError, UnicodeError):
        raise DiscordImportError("invalid-token-file") from None
    if len(raw) > MAX_TOKEN_BYTES:
        raise DiscordImportError("token-too-large")
    try:
        token = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise DiscordImportError("invalid-token-file") from None
    if not token or any(character.isspace() for character in token):
        raise DiscordImportError("invalid-token-file")
    return token


def _snowflake(value: str, label: str) -> str:
    normalized = value.strip()
    if not SNOWFLAKE.fullmatch(normalized) or not normalized.strip("0"):
        raise DiscordImportError(f"invalid-{label}")
    return normalized


def _public_key(value: str) -> str:
    normalized = value.strip().lower()
    if not PUBLIC_KEY.fullmatch(normalized):
        raise DiscordImportError("invalid-public-key")
    return normalized


def _session(value: str) -> str:
    normalized = value.strip()
    if not SESSION_NAME.fullmatch(normalized):
        raise DiscordImportError("invalid-session")
    return normalized


def _operator_bindings(args: argparse.Namespace) -> list[tuple[str, str]]:
    mapped: list[tuple[str, str]] = []
    bare_users: list[str] = []
    for raw in args.operator_user_id:
        if "=" in raw:
            user_id, session_name = raw.split("=", 1)
            if not user_id or not session_name:
                raise DiscordImportError("invalid-operator-binding")
            mapped.append((_snowflake(user_id, "operator-user-id"), _session(session_name)))
        else:
            bare_users.append(_snowflake(raw, "operator-user-id"))
    if bare_users:
        if len(bare_users) != len(args.dm_session):
            raise DiscordImportError("operator-session-count")
        mapped.extend(
            (user_id, _session(session_name))
            for user_id, session_name in zip(bare_users, args.dm_session, strict=True)
        )
    elif args.dm_session:
        raise DiscordImportError("operator-session-without-user")
    user_ids = [user_id for user_id, _ in mapped]
    session_names = [session_name.casefold() for _, session_name in mapped]
    if len(set(user_ids)) != len(user_ids) or len(set(session_names)) != len(session_names):
        raise DiscordImportError("duplicate-operator-binding")
    return mapped


def _command_environment(state_root: pathlib.Path) -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in SAFE_ENV_NAMES
    }
    environment.setdefault("PATH", os.defpath)
    environment["GC_HOME"] = str(state_root)
    return environment


def _run_gc(
    command: Sequence[str],
    *,
    environment: dict[str, str],
    cwd: pathlib.Path,
    token: str | None = None,
) -> None:
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            env=environment,
            input=(token + "\n").encode("utf-8") if token is not None else None,
            stdin=None if token is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
            close_fds=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise DiscordImportError("gc-command-failed") from None
    if result.returncode:
        raise DiscordImportError("gc-command-failed")


def _import_app(
    gc: pathlib.Path,
    city: pathlib.Path,
    state_root: pathlib.Path,
    token: str,
    application_id: str,
    public_key: str,
    guild_ids: Sequence[str],
    channel_ids: Sequence[str],
    role_ids: Sequence[str],
) -> None:
    command: list[str] = [
        str(gc),
        "--city",
        str(city),
        "discord",
        "import-app",
        "--application-id",
        application_id,
        "--public-key",
        public_key,
        "--bot-token-file",
        "/dev/stdin",
    ]
    for guild_id in guild_ids:
        command.extend(("--guild-allowlist", guild_id))
    for channel_id in channel_ids:
        command.extend(("--channel-allowlist", channel_id))
    for role_id in role_ids:
        command.extend(("--role-allowlist", role_id))
    _run_gc(
        command,
        environment=_command_environment(state_root),
        cwd=city,
        token=token,
    )


def _bind_dm(
    gc: pathlib.Path,
    city: pathlib.Path,
    state_root: pathlib.Path,
    user_id: str,
    session_name: str,
) -> None:
    _run_gc(
        [
            str(gc),
            "--city",
            str(city),
            "discord",
            "bind-dm",
            user_id,
            session_name,
        ],
        environment=_command_environment(state_root),
        cwd=city,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import the official Discord app and bind authorized operator DMs."
    )
    parser.add_argument("--gc", required=True, help="Absolute Gas City executable path")
    parser.add_argument("--state-root", required=True, help="Absolute GC_HOME path")
    parser.add_argument("--city", required=True, help="Absolute city path")
    parser.add_argument(
        "--token-file",
        "--bot-token-file",
        dest="token_file",
        required=True,
        help="Root/systemd credential file containing the bot token",
    )
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument(
        "--guild-id",
        "--guild-allowlist",
        dest="guild_ids",
        action="append",
        required=True,
    )
    parser.add_argument(
        "--channel-id",
        "--channel-allowlist",
        dest="channel_ids",
        action="append",
        required=True,
    )
    parser.add_argument(
        "--operator-role-id",
        "--role-id",
        "--role-allowlist",
        dest="role_ids",
        action="append",
        required=True,
    )
    parser.add_argument(
        "--operator-user-id",
        action="append",
        default=[],
        help="Discord user id=session name, repeatable; or pair with --dm-session",
    )
    parser.add_argument("--dm-session", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        gc = _validate_executable(args.gc)
        state_root = _validate_directory(args.state_root, "state", private=True)
        city = _validate_directory(args.city, "city")
        token = _read_token(args.token_file)
        application_id = _snowflake(args.application_id, "application-id")
        public_key = _public_key(args.public_key)
        guild_ids = [_snowflake(value, "guild-id") for value in args.guild_ids]
        channel_ids = [_snowflake(value, "channel-id") for value in args.channel_ids]
        role_ids = [_snowflake(value, "operator-role-id") for value in args.role_ids]
        bindings = _operator_bindings(args)
        if len(set(guild_ids)) != len(guild_ids):
            raise DiscordImportError("duplicate-guild-id")
        if len(set(channel_ids)) != len(channel_ids):
            raise DiscordImportError("duplicate-channel-id")
        if len(set(role_ids)) != len(role_ids):
            raise DiscordImportError("duplicate-role-id")
        _import_app(
            gc,
            city,
            state_root,
            token,
            application_id,
            public_key,
            guild_ids,
            channel_ids,
            role_ids,
        )
        for user_id, session_name in bindings:
            _bind_dm(gc, city, state_root, user_id, session_name)
    except DiscordImportError as exc:
        print(f"discord-import: {exc.code}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("discord-import: interrupted", file=sys.stderr)
        return 130
    print(
        f"discord-import: imported default app; bound {len(bindings)} operator DM(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
