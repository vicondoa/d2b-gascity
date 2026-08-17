#!/usr/bin/env python3
"""Stopped, portable bootstrap for the standalone d2b Gas City."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import pathlib
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.parse
from collections.abc import Iterable, Mapping


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_PORTABLE_SOURCE = ROOT / "city"
PACK_COMMIT = "5d2a9d023edbb9ba24fdcff554e89fc3d7da72fe"
GASCITY_COMMIT = "f6741d94861aa14f0253deffbe9efb1cb3a35d92"
DEFAULT_D2B_SOURCE = "https://github.com/vicondoa/d2b.git"
RIG_NAME = "d2b"
PORTABLE_FILES = (
    "city.toml",
    "pack.toml",
    "packs.lock",
    "role-provider-matrix.json",
    "worktree-producer-inventory.json",
)
PORTABLE_DIRECTORIES = ("agents", "assets", "formulas", "providers")
REQUIRED_INIT_FLAGS = ("--file", "--preserve-existing", "--no-start")
DOLT_START_READY_TIMEOUT_MS = "120000"
DOLT_SCHEMA_READY_TIMEOUT_SECONDS = 120.0


class BootstrapError(RuntimeError):
    """An actionable bootstrap refusal or command failure."""


def _path(value: str, label: str) -> pathlib.Path:
    candidate = pathlib.Path(value).expanduser()
    if not candidate.is_absolute():
        raise BootstrapError(f"{label} must be an absolute path")
    if candidate == pathlib.Path(candidate.anchor):
        raise BootstrapError(f"{label} must not be the filesystem root")
    current = pathlib.Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            raise BootstrapError(f"{label} must not contain symlink components")
    return candidate


def _runtime_path(value: str, label: str) -> pathlib.Path:
    candidate = pathlib.Path(value).expanduser()
    if not candidate.is_absolute():
        raise BootstrapError(f"{label} must be an absolute path")
    resolved = candidate.resolve(strict=False)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise BootstrapError(f"{label} must resolve to an executable file")
    return candidate


def _arg_path(value: str, label: str) -> pathlib.Path:
    try:
        return _path(value, label)
    except BootstrapError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _arg_runtime_path(value: str, label: str) -> pathlib.Path:
    try:
        return _runtime_path(value, label)
    except BootstrapError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _same_or_below(path: pathlib.Path, parent: pathlib.Path) -> bool:
    return path.resolve(strict=False).is_relative_to(parent.resolve(strict=False))


def _reject_overlapping_paths(city: pathlib.Path, rig: pathlib.Path) -> None:
    if _same_or_below(city, rig) or _same_or_below(rig, city):
        raise BootstrapError("city and rig paths must be separate roots")


def _safe_source(source: str) -> str:
    parsed = urllib.parse.urlparse(source)
    if parsed.username or parsed.password:
        raise BootstrapError("source URLs must not contain credentials")
    if parsed.scheme in {"http", "https", "ssh", "git"} and not parsed.netloc:
        raise BootstrapError("source URL has no host")
    return source


def _redact(text: str) -> str:
    text = re.sub(r"(https?://)([^/@\s]+):([^/@\s]+)@", r"\1<redacted>@", text)
    text = re.sub(r"(?i)(token|password|secret|api[_-]?key)\s*[=:]\s*\S+", r"\1=<redacted>", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "no diagnostic output"


def _run(
    argv: Iterable[str | os.PathLike[str]],
    *,
    env: Mapping[str, str],
    label: str,
    cwd: pathlib.Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [os.fspath(item) for item in argv]
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=dict(env),
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise BootstrapError(f"{label} could not start: {_redact(str(exc))}") from exc
    if result.returncode:
        raise BootstrapError(f"{label} failed: {_redact(result.stderr)}")
    return result


def _best_effort_stop(
    gc: pathlib.Path,
    city: pathlib.Path,
    *,
    env: Mapping[str, str],
) -> None:
    try:
        subprocess.run(
            [gc, "stop", "--city", city, "--force"],
            env=dict(env),
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


@contextlib.contextmanager
def _check_lifecycle(
    gc: pathlib.Path,
    city: pathlib.Path,
    *,
    env: Mapping[str, str],
    initially_running: bool,
):
    try:
        yield
    except BaseException:
        if not initially_running:
            with contextlib.suppress(Exception):
                _best_effort_stop(gc, city, env=env)
        raise
    if not initially_running:
        _run(
            [gc, "stop", "--city", city, "--force"],
            env=env,
            label="gc stop --city --force",
        )


def _read_toml(path: pathlib.Path, label: str) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise BootstrapError(f"invalid {label}: {_redact(str(exc))}") from exc


def _portable_file_set(root: pathlib.Path) -> dict[str, pathlib.Path]:
    files: dict[str, pathlib.Path] = {}
    for entry in PORTABLE_FILES:
        path = root / entry
        if not path.is_file() or path.is_symlink():
            raise BootstrapError(f"portable source is missing regular file {entry}")
        files[entry] = path
    for directory in PORTABLE_DIRECTORIES:
        path = root / directory
        if not path.is_dir() or path.is_symlink():
            raise BootstrapError(f"portable source is missing regular directory {directory}")
        files[directory] = path
        for child in path.rglob("*"):
            if child.is_symlink():
                raise BootstrapError(f"portable source contains symlink {child.relative_to(root)}")
            if child.is_file():
                files[child.relative_to(root).as_posix()] = child
    return files


def _validate_private_text(relative: str, text: str) -> None:
    forbidden_segments = {".gc", ".beads", "dolt", "worktree", "worktrees"}
    if "cities.toml" in pathlib.PurePosixPath(relative).parts or any(
        part in forbidden_segments for part in pathlib.PurePosixPath(relative).parts
    ):
        raise BootstrapError(f"portable source contains a runtime path: {relative}")
    if re.search(
        r"(?:^|[\s=])/(?:var|etc|home|root|run|srv|opt)(?:/|\b)",
        text,
        re.IGNORECASE,
    ):
        raise BootstrapError(f"portable source contains a private or runtime value: {relative}")
    if re.search(
        r"(?im)^\s*(?:token|password|secret|private[_-]?key)\s*=",
        text,
    ):
        raise BootstrapError(f"portable source contains a credential assignment: {relative}")
    if "file://" in text or (
        relative == "city.toml" and re.search(r"(?m)^\s*path\s*=", text)
    ):
        raise BootstrapError(f"portable source contains a machine-local path: {relative}")


def _validate_portable_source(
    source: pathlib.Path,
    *,
    allow_legacy_baseline: bool = False,
) -> dict[str, pathlib.Path]:
    if not source.is_dir() or source.is_symlink():
        raise BootstrapError("portable source must be a non-symlink directory")
    files = _portable_file_set(source)
    for relative, path in files.items():
        if path.is_file():
            _validate_private_text(relative, path.read_text())

    city = _read_toml(source / "city.toml", "portable city.toml")
    if city.get("workspace") != {"provider": "copilot-review"} and not (
        allow_legacy_baseline and "workspace" not in city
    ):
        raise BootstrapError(
            "portable city must define only the copilot-review workspace provider"
        )
    rigs = city.get("rigs", [])
    if len(rigs) != 1 or rigs[0].get("name") != RIG_NAME:
        raise BootstrapError("portable city must define exactly one d2b rig")
    rig = rigs[0]
    if "path" in rig:
        raise BootstrapError("portable city must not contain a rig path")
    if rig.get("prefix") != RIG_NAME or rig.get("default_branch") != "v3":
        raise BootstrapError("portable d2b rig must use prefix d2b and branch v3")
    roles = rig.get("imports", {}).get("roles", {})
    if roles != {
        "source": "https://github.com/gastownhall/gascity-packs/tree/main/gascity/roles",
        "version": f"sha:{PACK_COMMIT}",
    }:
        raise BootstrapError("portable city must pin the current gascity roles import")

    pack = _read_toml(source / "pack.toml", "portable pack.toml")
    if pack.get("pack", {}).get("schema") != 2:
        raise BootstrapError("portable root pack must use schema 2")
    imports = pack.get("imports", {})
    expected_imports = {
        "bd": (
            "https://github.com/gastownhall/gascity.git//examples/bd",
            GASCITY_COMMIT,
        ),
        "compound": (
            "https://github.com/gastownhall/gascity-packs/tree/main/compound-engineering",
            PACK_COMMIT,
        ),
        "core": (
            "https://github.com/gastownhall/gascity.git//internal/bootstrap/packs/core",
            GASCITY_COMMIT,
        ),
        "discord": (
            "https://github.com/gastownhall/gascity-packs/tree/main/discord",
            PACK_COMMIT,
        ),
    }
    if set(imports) != set(expected_imports):
        raise BootstrapError("portable root pack has an unexpected import set")
    for name, (expected_source, expected_commit) in expected_imports.items():
        if imports[name] != {
            "source": expected_source,
            "version": f"sha:{expected_commit}",
        }:
            raise BootstrapError(f"portable import {name} is not pinned to the U3 source")

    lock = _read_toml(source / "packs.lock", "portable packs.lock")
    if lock.get("schema") != 1:
        raise BootstrapError("portable packs.lock must use schema 1")
    expected_locks = {
        **{
            source: PACK_COMMIT
            for source in (
                "https://github.com/gastownhall/gascity-packs/tree/main/compound-engineering",
                "https://github.com/gastownhall/gascity-packs/tree/main/discord",
                "https://github.com/gastownhall/gascity-packs/tree/main/gascity/roles",
            )
        },
        "https://github.com/gastownhall/gascity.git//examples/bd": GASCITY_COMMIT,
        "https://github.com/gastownhall/gascity.git//internal/bootstrap/packs/core": GASCITY_COMMIT,
    }
    packs = lock.get("packs", {})
    if set(packs) != set(expected_locks):
        raise BootstrapError("portable packs.lock has an unexpected source set")
    for source_name, commit in expected_locks.items():
        entry = packs[source_name]
        if entry.get("version") != f"sha:{commit}" or entry.get("commit") != commit:
            raise BootstrapError(f"portable lock entry is not pinned: {source_name}")
    return files


def _copy_file_atomic(source: pathlib.Path, destination: pathlib.Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def _materialize_portable(
    source: pathlib.Path,
    destination: pathlib.Path,
    files: dict[str, pathlib.Path] | None = None,
) -> None:
    files = files or _validate_portable_source(source)
    destination.mkdir(parents=True)
    for relative, path in files.items():
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            _copy_file_atomic(path, target)


def _portable_snapshot(files: dict[str, pathlib.Path]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for relative, path in files.items():
        if path.is_dir():
            continue
        if path.suffix == ".toml":
            parsed = _read_toml(path, relative)
            if relative == "city.toml":
                workspace = parsed.get("workspace")
                if isinstance(workspace, dict):
                    workspace.pop("name", None)
                    if not workspace:
                        parsed.pop("workspace", None)
            if relative == "packs.lock":
                for pack in parsed.get("packs", {}).values():
                    if isinstance(pack, dict):
                        pack.pop("fetched", None)
            snapshot[relative] = json.dumps(
                parsed,
                sort_keys=True,
                separators=(",", ":"),
            )
        else:
            snapshot[relative] = path.read_bytes().hex()
    return snapshot


def _city_env(state_root: pathlib.Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GC_HOME": str(state_root),
            "DOLT_ROOT_PATH": str(state_root / "dolt"),
            "GIT_CONFIG_GLOBAL": str(state_root / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "BD_NON_INTERACTIVE": "1",
            "NO_COLOR": "1",
            "GC_SUPERVISOR_LOG_TEE": "0",
            "XDG_CONFIG_HOME": str(state_root / "xdg-config"),
            "XDG_STATE_HOME": str(state_root / "xdg-state"),
            "XDG_DATA_HOME": str(state_root / "xdg-data"),
            "XDG_RUNTIME_DIR": str(state_root / "runtime"),
        }
    )
    env.setdefault(
        "GC_DOLT_CONCURRENT_START_READY_TIMEOUT_MS",
        DOLT_START_READY_TIMEOUT_MS,
    )
    return env


def _validate_gc_help(gc: pathlib.Path, env: Mapping[str, str]) -> None:
    result = _run([gc, "init", "--help"], env=env, label="gc init --help")
    missing = [flag for flag in REQUIRED_INIT_FLAGS if flag not in result.stdout]
    if missing:
        raise BootstrapError(
            "packaged gc init lacks required flags: " + ", ".join(missing)
        )


def _seed_pack_cache(source: pathlib.Path | None, state_root: pathlib.Path) -> None:
    if source is None:
        return
    source = _path(os.fspath(source), "pack cache")
    if not source.is_dir() or source.is_symlink():
        raise BootstrapError("pack cache must be a non-symlink directory")
    destination = state_root / "cache" / "repos"
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if child.name == ".packman-cache.lock":
            continue
        if child.is_symlink() or not child.is_dir():
            raise BootstrapError("pack cache contains a non-directory entry")
        target = destination / child.name
        if target.exists():
            continue
        shutil.copytree(child, target, symlinks=False)


def _git_command() -> str:
    git = shutil.which("git")
    if not git:
        raise BootstrapError("git is required in the packaged runtime PATH")
    return git


def _dolt_command(gc: pathlib.Path, explicit: str | None) -> pathlib.Path | None:
    if explicit:
        return _runtime_path(explicit, "dolt runtime")
    sibling = gc.parent / "dolt"
    if sibling.is_file():
        return sibling
    found = shutil.which("dolt")
    return pathlib.Path(found) if found else None


def _configure_dolt_identity(args: argparse.Namespace, env: Mapping[str, str]) -> None:
    if not args.dolt_user_name and not args.dolt_user_email:
        return
    if not args.dolt_user_name or not args.dolt_user_email:
        raise BootstrapError("dolt user name and email must be supplied together")
    dolt = _dolt_command(args.gc, args.dolt)
    if dolt is None:
        raise BootstrapError("dolt is required when configuring a fixture identity")
    _run(
        [dolt, "config", "--global", "--add", "user.name", args.dolt_user_name],
        env=env,
        label="dolt user.name configuration",
    )
    _run(
        [dolt, "config", "--global", "--add", "user.email", args.dolt_user_email],
        env=env,
        label="dolt user.email configuration",
    )


def _prepare_rig(args: argparse.Namespace, env: Mapping[str, str]) -> None:
    git = _git_command()
    rig = args.rig
    if rig.exists():
        if rig.is_symlink():
            raise BootstrapError("rig path must not be a symlink")
        if not rig.is_dir():
            raise BootstrapError("rig path is not a directory")
        if any(rig.iterdir()):
            _run([git, "-C", rig, "rev-parse", "--is-inside-work-tree"], env=env, label="d2b rig check")
            branch = _run(
                [git, "-C", rig, "symbolic-ref", "--quiet", "--short", "HEAD"],
                env=env,
                label="d2b rig branch check",
            )
            if branch.stdout.strip() != "v3":
                raise BootstrapError("existing rig must be checked out on v3")
            remote_v3 = subprocess.run(
                [
                    git,
                    "-C",
                    os.fspath(rig),
                    "show-ref",
                    "--verify",
                    "--quiet",
                    "refs/remotes/origin/v3",
                ],
                env=dict(env),
                text=True,
                capture_output=True,
                check=False,
            )
            if remote_v3.returncode != 0:
                raise BootstrapError("existing rig must provide origin/v3")
            _run(
                [git, "-C", rig, "remote", "set-head", "origin", "v3"],
                env=env,
                label="d2b origin HEAD pin",
            )
            return
    else:
        rig.parent.mkdir(parents=True, exist_ok=True)

    source = _safe_source(args.d2b_source)
    _run(
        [git, "clone", "--quiet", "--branch", "v3", "--single-branch", source, str(rig)],
        env=env,
        label="d2b v3 clone",
    )
    _run(
        [git, "-C", rig, "remote", "set-head", "origin", "v3"],
        env=env,
        label="d2b origin HEAD pin",
    )


def _dolt_connection(
    args: argparse.Namespace,
    env: Mapping[str, str],
) -> tuple[pathlib.Path, str, int, str]:
    metadata_path = args.city / ".beads" / "metadata.json"
    config_path = args.city / ".gc" / "runtime" / "packs" / "dolt" / "dolt-config.yaml"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        config = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BootstrapError("managed Dolt readiness metadata is missing") from error
    database = metadata.get("dolt_database")
    if not isinstance(database, str) or not database:
        raise BootstrapError("managed Dolt metadata has no database name")
    match = re.search(r"(?m)^\s*port:\s*(\d+)\s*$", config)
    if match is None:
        port_value = env.get("GC_DOLT_PORT", "").strip()
        if not port_value or port_value == "0":
            raise BootstrapError("managed Dolt configuration has no listener port")
    else:
        port_value = match.group(1)
    try:
        port = int(port_value)
    except ValueError as error:
        raise BootstrapError("managed Dolt listener port is invalid") from error
    dolt = args.gc.parent / "dolt"
    if not dolt.is_file() or not os.access(dolt, os.X_OK):
        raise BootstrapError("packaged runtime is missing dolt for readiness probing")
    host_match = re.search(r"(?m)^\s*host:\s*([^\s#]+)\s*$", config)
    host = host_match.group(1) if host_match else env.get("GC_DOLT_HOST", "127.0.0.1")
    return dolt, host, port, database


def _wait_for_dolt_schema(
    args: argparse.Namespace,
    env: Mapping[str, str],
    *,
    timeout: float = DOLT_SCHEMA_READY_TIMEOUT_SECONDS,
) -> None:
    dolt, host, port, database = _dolt_connection(args, env)
    query = f"SHOW TABLES FROM `{database}`"
    deadline = time.monotonic() + timeout
    last_error = "schema is not ready"
    while time.monotonic() < deadline:
        try:
            result = subprocess.run(
                [
                    dolt,
                    "--no-tls",
                    "--host",
                    host,
                    "--port",
                    str(port),
                    "sql",
                    "-q",
                    query,
                ],
                cwd=args.city,
                env=dict(env),
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as error:
            last_error = str(error)
        else:
            output = result.stdout + result.stderr
            if (
                result.returncode == 0
                and "schema_migrations" in output
                and "issues" in output
            ):
                return
            last_error = output.strip().splitlines()[-1] if output.strip() else last_error
        time.sleep(0.25)
    raise BootstrapError(f"managed Dolt schema did not become ready: {last_error}")


def _start_dolt_server(
    args: argparse.Namespace,
    env: Mapping[str, str],
) -> subprocess.Popen[bytes]:
    dolt, _host, _port, _database = _dolt_connection(args, env)
    config = args.city / ".gc" / "runtime" / "packs" / "dolt" / "dolt-config.yaml"
    try:
        return subprocess.Popen(
            [dolt, "sql-server", "--config", str(config)],
            cwd=args.city,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        raise BootstrapError("managed Dolt server could not be started") from error


def _stop_dolt_server(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait(timeout=10)


def _ensure_dolt_schema(
    args: argparse.Namespace,
    env: Mapping[str, str],
) -> subprocess.Popen[bytes] | None:
    try:
        _wait_for_dolt_schema(args, env, timeout=5.0)
        return None
    except BootstrapError:
        _best_effort_stop(args.gc, args.city, env=env)
    deadline = time.monotonic() + DOLT_SCHEMA_READY_TIMEOUT_SECONDS
    process: subprocess.Popen[bytes] | None = None
    last_error = "schema is not ready"
    while time.monotonic() < deadline:
        if process is None or process.poll() is not None:
            process = _start_dolt_server(args, env)
        try:
            _wait_for_dolt_schema(args, env, timeout=2.0)
            return process
        except BootstrapError as error:
            last_error = str(error)
            time.sleep(0.25)
    _stop_dolt_server(process)
    raise BootstrapError(f"managed Dolt schema did not become ready: {last_error}")


def _run_gc_init(
    args: argparse.Namespace,
    env: Mapping[str, str],
) -> subprocess.Popen[bytes] | None:
    command = [
        args.gc,
        "init",
        "--file",
        args.city / "city.toml",
        "--preserve-existing",
        "--no-start",
        "--skip-provider-readiness",
        "--name",
        "d2b-gascity",
        args.city,
    ]
    try:
        _run(
            command,
            env=env,
            label="gc init --file --preserve-existing --no-start",
        )
        return None
    except BootstrapError as error:
        markers = (
            args.city / ".beads" / "metadata.json",
            args.city / ".gc" / "runtime" / "packs" / "dolt" / "dolt-config.yaml",
        )
        if not all(path.is_file() for path in markers):
            raise
        _best_effort_stop(args.gc, args.city, env=env)
        try:
            return _ensure_dolt_schema(args, env)
        except BootstrapError as recovery_error:
            raise BootstrapError(
                f"{error}; initialization recovery failed: {recovery_error}"
            ) from error


def _initialize_rig_beads(args: argparse.Namespace, env: Mapping[str, str]) -> None:
    beads = args.rig / ".beads"
    config = beads / "config.yaml"
    metadata = beads / "metadata.json"
    if config.is_file() and metadata.is_file():
        return
    if beads.exists():
        raise BootstrapError("rig contains a partial .beads initialization")
    dolt, host, port, _database = _dolt_connection(args, env)
    bd = dolt.parent / "bd"
    if not bd.is_file() or not os.access(bd, os.X_OK):
        raise BootstrapError("packaged runtime is missing bd for rig initialization")
    _run(
        [
            bd,
            "init",
            "--non-interactive",
            "--skip-agents",
            "--skip-hooks",
            "--prefix",
            RIG_NAME,
            "--server",
            "--server-host",
            host,
            "--server-port",
            str(port),
            "--database",
            RIG_NAME,
        ],
        env=env,
        label="bd init rig",
        cwd=args.rig,
    )
    text = config.read_text(encoding="utf-8")
    if not re.search(r"(?m)^\s*issue_prefix\s*:", text):
        config.write_text(
            text.rstrip() + f'\nissue_prefix: "{RIG_NAME}"\n',
            encoding="utf-8",
        )


def _detach_rig_git_federation(
    args: argparse.Namespace,
    env: Mapping[str, str],
) -> None:
    """Drop the git-origin Dolt remote that bd init copies from the checkout.

    Publication uses the worker, not remotesapi. Leave the git remote intact.
    """
    try:
        dolt, _host, _port, _database = _dolt_connection(args, env)
    except BootstrapError:
        return
    bd = dolt.parent / "bd"
    if not bd.is_file() or not os.access(bd, os.X_OK):
        raise BootstrapError("packaged runtime is missing bd for rig federation cleanup")
    for argv in (
        [bd, "federation", "remove-peer", "origin"],
        [bd, "dolt", "remote", "remove", "origin"],
        [bd, "config", "unset", "sync.remote"],
    ):
        subprocess.run(
            [os.fspath(item) for item in argv],
            cwd=args.rig,
            env=dict(env),
            text=True,
            capture_output=True,
            check=False,
        )
    data_dir = args.city / ".beads" / "dolt"
    if not data_dir.is_dir():
        return
    status = subprocess.run(
        [
            os.fspath(dolt),
            "--data-dir",
            str(data_dir),
            "sql",
            "-q",
            f"USE {RIG_NAME}; SELECT table_name FROM dolt_status;",
        ],
        cwd=args.city,
        env=dict(env),
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        return
    dirty = [
        line
        for line in status.stdout.splitlines()
        if line.startswith("|")
        and "table_name" not in line
        and "---" not in line
    ]
    if not dirty:
        return
    commit = subprocess.run(
        [
            os.fspath(dolt),
            "--data-dir",
            str(data_dir),
            "sql",
            "-q",
            f"USE {RIG_NAME}; CALL DOLT_ADD('-A'); "
            "CALL DOLT_COMMIT('-Am', 'Commit local rig store overlay');",
        ],
        cwd=args.city,
        env=dict(env),
        text=True,
        capture_output=True,
        check=False,
    )
    if commit.returncode != 0:
        raise BootstrapError(
            "rig store overlay commit failed: " + _redact(commit.stderr or commit.stdout)
        )


def _site_binding(city: pathlib.Path, rig: pathlib.Path) -> None:
    site_path = city / ".gc" / "site.toml"
    if not site_path.is_file() or site_path.is_symlink():
        raise BootstrapError("gc rig add did not create machine-local .gc/site.toml")
    site = _read_toml(site_path, "machine-local site.toml")
    if site.get("workspace_name") != "d2b-gascity":
        raise BootstrapError("machine-local site workspace must be d2b-gascity")
    entries = site.get("rig", [])
    matching = [entry for entry in entries if entry.get("name") == RIG_NAME]
    if len(matching) != 1 or pathlib.Path(matching[0].get("path", "")).resolve() != rig.resolve():
        raise BootstrapError("machine-local site binding does not point to the requested rig")


def _validate_city_state(
    city: pathlib.Path,
    rig: pathlib.Path,
    *,
    require_site: bool = True,
) -> None:
    if not city.is_dir() or city.is_symlink():
        raise BootstrapError("city must be a non-symlink directory")
    source_files = _validate_portable_source(DEFAULT_PORTABLE_SOURCE)
    target_files = _portable_file_set(city)
    target_city = _read_toml(target_files["city.toml"], "runtime city.toml")
    if target_city.get("workspace", {}) not in (
        {},
        {"name": "d2b-gascity"},
        {"provider": "copilot-review"},
        {"name": "d2b-gascity", "provider": "copilot-review"},
    ):
        raise BootstrapError("runtime city workspace identity is invalid")
    source_snapshot = _portable_snapshot(source_files)
    target_snapshot = _portable_snapshot(target_files)
    if source_snapshot != target_snapshot:
        changed = sorted(
            path
            for path in set(source_snapshot) | set(target_snapshot)
            if source_snapshot.get(path) != target_snapshot.get(path)
        )
        raise BootstrapError(
            "city portable files do not match the committed source: "
            + ", ".join(changed)
        )
    if require_site:
        _site_binding(city, rig)


def _cities_json(gc: pathlib.Path, env: Mapping[str, str]) -> dict:
    result = _run(
        [gc, "cities", "list", "--json"],
        env=env,
        label="gc cities list",
    )
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise BootstrapError("gc cities list did not return JSON") from exc


def _supervisor_json(gc: pathlib.Path, env: Mapping[str, str]) -> dict:
    result = _run(
        [gc, "supervisor", "status", "--json"],
        env=env,
        label="gc supervisor status",
    )
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise BootstrapError("gc supervisor status did not return JSON") from exc


def _check(args: argparse.Namespace) -> int:
    env = _city_env(args.state_root)
    supervisor = _supervisor_json(args.gc, env)
    initially_running = bool(supervisor.get("running") or supervisor.get("pid"))
    scope = env.get("GC_SUPERVISOR_SYSTEMD_SCOPE", "").strip().lower()
    unit = env.get("GC_SUPERVISOR_SYSTEMD_UNIT", "").strip()
    delegated = bool(args.fixture_supervisor or (unit and scope == "system"))
    with _check_lifecycle(
        args.gc,
        args.city,
        env=env,
        initially_running=initially_running,
    ):
        if scope == "user":
            raise BootstrapError("user-scoped supervisor delegation is forbidden")
        if unit and scope != "system":
            raise BootstrapError(
                "GC_SUPERVISOR_SYSTEMD_UNIT requires GC_SUPERVISOR_SYSTEMD_SCOPE=system"
            )
        if initially_running and not delegated:
            raise BootstrapError(
                "a running supervisor requires GC_SUPERVISOR_SYSTEMD_UNIT or --fixture-supervisor"
            )
        _validate_gc_help(args.gc, env)
        _validate_city_state(args.city, args.rig)
        _run(
            [args.gc, "import", "check", "--city", args.city],
            env=env,
            label="gc import check",
        )
        _run(
            [args.gc, "config", "show", "--city", args.city, "--validate"],
            env=env,
            label="gc config show --validate",
        )
        rigs = _run(
            [args.gc, "rig", "list", "--city", args.city, "--json"],
            env=env,
            label="gc rig list",
        )
        try:
            rig_report = json.loads(rigs.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise BootstrapError("gc rig list did not return JSON") from exc
        names = [entry.get("name") for entry in rig_report.get("rigs", [])]
        if names.count(RIG_NAME) != 1:
            raise BootstrapError("city does not contain exactly one d2b rig")

        cities = _cities_json(args.gc, env)
        city_resolved = str(args.city.resolve())
        registered = any(
            pathlib.Path(entry.get("path", "")).resolve() == pathlib.Path(city_resolved)
            for entry in cities.get("cities", [])
        )
        if registered and not delegated:
            raise BootstrapError(
                "registered city has no system supervisor delegation; use the root service"
            )
        report = {
            "city": str(args.city),
            "rig": str(args.rig),
            "registered": registered,
            "supervisor_running": initially_running,
            "supervisor_scope": scope or "unset",
            "supervisor_unit": unit or None,
            "checks": {
                "imports": "ok",
                "config": "ok",
                "city": "ok",
                "rig": "ok",
                "site_binding": "ok",
                "no_user_supervisor": "ok",
            },
        }
    print(json.dumps(report, sort_keys=True))
    return 0


def _init(args: argparse.Namespace) -> int:
    env = _city_env(args.state_root)
    _validate_gc_help(args.gc, env)
    portable_files = _validate_portable_source(args.portable_source)
    _reject_overlapping_paths(args.city, args.rig)
    if args.city.exists():
        if args.city.is_symlink():
            raise BootstrapError("city target must not be a symlink")
        if any(args.city.iterdir()):
            raise BootstrapError(
                "city target already exists or is partial; use register-existing for an initialized city"
            )
    elif args.city.parent.exists() and args.city.parent.is_symlink():
        raise BootstrapError("city parent must not be a symlink")

    if args.rig.exists() and args.rig.is_symlink():
        raise BootstrapError("rig path must not be a symlink")
    if args.rig.exists() and not args.rig.is_dir():
        raise BootstrapError("rig path is not a directory")

    args.city.parent.mkdir(parents=True, exist_ok=True)
    _configure_dolt_identity(args, env)
    _seed_pack_cache(args.pack_cache, args.state_root)
    _materialize_portable(args.portable_source, args.city, portable_files)
    dolt_process: subprocess.Popen[bytes] | None = None
    try:
        dolt_process = _run_gc_init(args, env)
        if dolt_process is None:
            dolt_process = _ensure_dolt_schema(args, env)
        _prepare_rig(args, env)
        _initialize_rig_beads(args, env)
        _run(
            [
                args.gc,
                "rig",
                "add",
                args.rig,
                "--city",
                args.city,
                "--name",
                RIG_NAME,
                "--prefix",
                RIG_NAME,
                "--default-branch",
                "v3",
                "--start-suspended",
                "--adopt",
            ],
            env=env,
            label="gc rig add",
        )
        _detach_rig_git_federation(args, env)
        _run(
            [args.gc, "import", "install", "--city", args.city],
            env=env,
            label="gc import install",
        )
        _site_binding(args.city, args.rig)
    except BootstrapError:
        _stop_dolt_server(dolt_process)
        _best_effort_stop(args.gc, args.city, env=env)
        raise
    _stop_dolt_server(dolt_process)
    _run(
        [args.gc, "stop", "--city", args.city, "--force"],
        env=env,
        label="gc stop --city --force",
    )
    print(
        json.dumps(
            {
                "city": str(args.city),
                "rig": str(args.rig),
                "status": "initialized",
                "no_start": True,
                "registered": False,
                "provider_readiness": "skipped",
            },
            sort_keys=True,
        )
    )
    return 0


def _register(args: argparse.Namespace) -> int:
    env = _city_env(args.state_root)
    _validate_gc_help(args.gc, env)
    _validate_city_state(args.city, args.rig)
    if not args.allow_start:
        raise BootstrapError(
            "register-existing refuses to start or reconcile without --allow-start; "
            "the root service must already be delegated"
        )
    scope = env.get("GC_SUPERVISOR_SYSTEMD_SCOPE", "").strip().lower()
    unit = env.get("GC_SUPERVISOR_SYSTEMD_UNIT", "").strip()
    if scope == "user":
        raise BootstrapError("user-scoped supervisor delegation is forbidden")
    if unit and scope != "system":
        raise BootstrapError(
            "GC_SUPERVISOR_SYSTEMD_UNIT requires GC_SUPERVISOR_SYSTEMD_SCOPE=system"
        )
    if not unit and not args.fixture_supervisor:
        raise BootstrapError(
            "register-existing requires GC_SUPERVISOR_SYSTEMD_UNIT with system scope "
            "or the explicit --fixture-supervisor test guard"
        )
    command = [args.gc, "register", args.city, "--yes", "--json"]
    result = subprocess.run(
        command,
        env=dict(env),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        payload: dict[str, object] | None = None
        try:
            candidate = json.loads(result.stdout.strip().splitlines()[-1])
            if isinstance(candidate, dict):
                payload = candidate
        except (IndexError, json.JSONDecodeError):
            pass
        city_resolved = str(args.city.resolve())
        registered = False
        success_hint = "registered city" in (
            result.stdout + result.stderr
        ).lower()
        if success_hint or (payload is not None and payload.get("ok") is True):
            cities = _cities_json(args.gc, env)
            registered = any(
                pathlib.Path(entry.get("path", "")).resolve() == pathlib.Path(city_resolved)
                for entry in cities.get("cities", [])
            )
        if not registered:
            raise BootstrapError(
                f"gc register failed: {_redact(result.stderr)}"
            )
    _run(
        [args.gc, "rig", "resume", RIG_NAME],
        env=env,
        cwd=args.city,
        label="gc rig resume",
    )
    print(result.stdout, end="")
    return 0


def _portable_update(args: argparse.Namespace) -> int:
    env = _city_env(args.state_root)
    _validate_gc_help(args.gc, env)
    baseline_files = _validate_portable_source(
        args.baseline_source,
        allow_legacy_baseline=True,
    )
    candidate_files = _validate_portable_source(args.portable_source)
    if not args.city.is_dir() or args.city.is_symlink():
        raise BootstrapError("portable update requires an initialized city directory")
    target_files = _portable_file_set(args.city)

    baseline_snapshot = _portable_snapshot(baseline_files)
    target_snapshot = _portable_snapshot(target_files)
    if baseline_snapshot != target_snapshot:
        raise BootstrapError(
            "portable source drift detected; refusing update before changing runtime state"
        )
    updated: list[str] = []
    for relative, source_path in candidate_files.items():
        if source_path.is_dir():
            (args.city / relative).mkdir(parents=True, exist_ok=True)
            continue
        target = args.city / relative
        if target.read_bytes() != source_path.read_bytes():
            _copy_file_atomic(source_path, target)
            updated.append(relative)
    print(
        json.dumps(
            {
                "city": str(args.city),
                "updated": updated,
                "preserved_runtime": True,
            },
            sort_keys=True,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap or validate the stopped standalone d2b Gas City."
    )
    parser.add_argument(
        "mode",
        choices=("init", "register", "register-existing", "check", "portable-update"),
    )
    parser.add_argument("--state-root", required=True, type=lambda value: _arg_path(value, "state root"))
    parser.add_argument("--city", required=True, type=lambda value: _arg_path(value, "city"))
    parser.add_argument("--rig", required=True, type=lambda value: _arg_path(value, "rig"))
    parser.add_argument(
        "--gc", required=True, type=lambda value: _arg_runtime_path(value, "gc runtime")
    )
    parser.add_argument(
        "--portable-source",
        type=lambda value: _arg_path(value, "portable source"),
        default=DEFAULT_PORTABLE_SOURCE,
    )
    parser.add_argument(
        "--baseline-source",
        type=lambda value: _arg_path(value, "baseline source"),
        default=DEFAULT_PORTABLE_SOURCE,
    )
    parser.add_argument("--pack-cache", type=lambda value: _arg_path(value, "pack cache"))
    parser.add_argument("--d2b-source", default=DEFAULT_D2B_SOURCE)
    parser.add_argument("--dolt", type=lambda value: _arg_runtime_path(value, "dolt runtime"))
    parser.add_argument("--dolt-user-name")
    parser.add_argument("--dolt-user-email")
    parser.add_argument("--allow-start", action="store_true")
    parser.add_argument("--fixture-supervisor", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.gc.is_file() or not os.access(args.gc, os.X_OK):
        print("bootstrap: packaged gc runtime is not executable", file=sys.stderr)
        return 2
    try:
        if args.mode == "init":
            return _init(args)
        if args.mode in {"register", "register-existing"}:
            return _register(args)
        if args.mode == "check":
            return _check(args)
        return _portable_update(args)
    except BootstrapError as exc:
        print(f"bootstrap: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
