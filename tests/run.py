#!/usr/bin/env python3
"""Run the standalone Gas City repository's deterministic check graph."""

from __future__ import annotations

import argparse
import os
import pathlib
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Iterable


ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "tests" / "policy"
FIXTURE_ROOT = ROOT / "tests" / "fixtures"
POLICY_TEST_GLOB = "*.py"
FIXTURE_TEST_GLOB = "test_*.py"
ACP_ACCEPTANCE_RELATIVE = "tests/acceptance/copilot-acp.py"
INGRESS_FIXTURE_RELATIVE = "tests/fixtures/ingress/run.py"
ROLLBACK_ACCEPTANCE_RELATIVE = "tests/acceptance/rollback.py"
ACP_ACCEPTANCE = ROOT / ACP_ACCEPTANCE_RELATIVE
INGRESS_FIXTURE = ROOT / INGRESS_FIXTURE_RELATIVE
ROLLBACK_ACCEPTANCE = ROOT / ROLLBACK_ACCEPTANCE_RELATIVE
RUNTIME_COMMANDS = frozenset({"policy", "fixtures", "ingress", "workflow", "check"})


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int
    pgid: int
    command: str
    cwd: str
    run_id: str | None


class RunnerError(RuntimeError):
    pass


def _read_process(pid_path: pathlib.Path) -> ProcessInfo | None:
    try:
        raw_stat = (pid_path / "stat").read_text(encoding="utf-8")
        fields = raw_stat.rsplit(")", 1)[1].split()
        ppid = int(fields[1])
        pgid = int(fields[2])
        command = (
            (pid_path / "cmdline").read_bytes()
            .replace(b"\0", b" ")
            .decode("utf-8", errors="replace")
        )
        cwd = os.readlink(pid_path / "cwd")
        run_id = None
        for item in (pid_path / "environ").read_bytes().split(b"\0"):
            if item.startswith(b"D2B_GASCITY_CHECK_RUN_ID="):
                run_id = item.partition(b"=")[2].decode(
                    "utf-8",
                    errors="replace",
                )
                break
    except (FileNotFoundError, PermissionError, OSError, ValueError, IndexError):
        return None
    return ProcessInfo(int(pid_path.name), ppid, pgid, command, cwd, run_id)


def process_snapshot() -> dict[int, ProcessInfo]:
    result: dict[int, ProcessInfo] = {}
    proc = pathlib.Path("/proc")
    if not proc.is_dir():
        return result
    for entry in sorted(proc.iterdir(), key=lambda path: path.name):
        if entry.name.isdigit():
            info = _read_process(entry)
            if info is not None:
                result[info.pid] = info
    return result


def _owned_processes(
    before: dict[int, ProcessInfo],
    after: dict[int, ProcessInfo],
    *,
    roots: Iterable[int],
    run_id: str,
) -> list[ProcessInfo]:
    root_set = set(roots)
    root_groups = {
        after[root].pgid
        for root in root_set
        if root in after
    }
    selected = {
        pid
        for pid in after
        if pid not in before and pid != os.getpid()
        and (
            after[pid].ppid in root_set
            or after[pid].pgid in root_set
            or after[pid].pgid in root_groups
            or after[pid].run_id == run_id
        )
    }
    changed = True
    while changed:
        changed = False
        for pid, info in after.items():
            if pid in selected:
                continue
            if info.ppid in selected or info.ppid in root_set:
                selected.add(pid)
                changed = True
    return [after[pid] for pid in sorted(selected) if pid in after]


def _stop_group(pgid: int) -> None:
    if pgid <= 1 or pgid == os.getpgrp():
        return
    for signum in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, signum)
        except ProcessLookupError:
            return
        except PermissionError as error:
            raise RunnerError(f"cannot clean process group {pgid}: {error}") from error
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                return
            except PermissionError:
                break
            time.sleep(0.02)


def _safe_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    blocked = (
        "AWS_",
        "AZURE_",
        "COPILOT_GITHUB_TOKEN",
        "CREDENTIALS_DIRECTORY",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GOOGLE_",
        "OPENAI_",
        "PASSWORD",
        "SECRET",
        "TOKEN",
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not any(key == prefix or key.startswith(prefix) for prefix in blocked)
    }
    environment.update(
        {
            "D2B_GASCITY_ROOT": str(ROOT),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "NO_COLOR": "1",
            "PYTHONPATH": os.pathsep.join(
                (str(ROOT), os.environ.get("PYTHONPATH", ""))
            ).rstrip(os.pathsep),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    if extra:
        environment.update(extra)
    return environment


def _run_command(
    command: list[str],
    *,
    env: dict[str, str],
    cwd: pathlib.Path = ROOT,
    timeout: float = 900,
) -> subprocess.CompletedProcess[str]:
    before = process_snapshot()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        _stop_group(process.pid)
        output, _ = process.communicate(timeout=10)
        raise RunnerError(f"timeout running {' '.join(command)}\n{output[-4000:]}") from error
    finally:
        if process.poll() is None:
            _stop_group(process.pid)
    deadline = time.monotonic() + 5
    after = process_snapshot()
    leaks = _owned_processes(
        before,
        after,
        roots=(process.pid,),
        run_id=env["D2B_GASCITY_CHECK_RUN_ID"],
    )
    while leaks and time.monotonic() < deadline:
        time.sleep(0.1)
        after = process_snapshot()
        leaks = _owned_processes(
            before,
            after,
            roots=(process.pid,),
            run_id=env["D2B_GASCITY_CHECK_RUN_ID"],
        )
    if leaks:
        for info in leaks:
            _stop_group(info.pgid)
        details = "; ".join(
            f"{info.pid}:{info.command or '<no-command>'}" for info in leaks
        )
        raise RunnerError(f"process leak after {' '.join(command)}: {details}")
    result = subprocess.CompletedProcess(command, process.returncode, output, "")
    if result.returncode != 0:
        raise RunnerError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout[-12000:]}"
        )
    return result


def _ensure_runtime(env: dict[str, str], run_root: pathlib.Path) -> pathlib.Path:
    nix = shutil.which("nix")
    if nix is None:
        raise RunnerError("nix is required to build the contributor runtime")
    result = _run_command(
        [
            nix,
            "build",
            ".#gas-city-contributor",
            "--no-link",
            "--print-out-paths",
            "--no-write-lock-file",
        ],
        env=env,
        timeout=1800,
    )
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith("/nix/store/")]
    if not paths:
        raise RunnerError("nix build did not return a contributor runtime path")
    candidate = pathlib.Path(paths[-1]).resolve()
    if not (candidate / "bin" / "gc").is_file():
        raise RunnerError(f"built contributor runtime is missing gc: {candidate}")
    env["GC_CONTRIBUTOR_ROOT"] = str(candidate)
    env["PATH"] = os.pathsep.join((str(candidate / "bin"), env.get("PATH", os.defpath)))
    env["D2B_GASCITY_CHECK_RUN_ROOT"] = str(run_root)
    return candidate


def _ensure_pack_cache(
    runtime: pathlib.Path,
    env: dict[str, str],
    run_root: pathlib.Path,
) -> None:
    seed = run_root / "pack-seed"
    seed.mkdir(mode=0o700, parents=True)
    city = seed / "city"
    shutil.copytree(ROOT / "city", city)
    seed_env = dict(env)
    seed_env.update(
        {
            "GC_HOME": str(seed / "gc"),
            "HOME": str(seed / "home"),
            "XDG_CONFIG_HOME": str(seed / "config"),
            "XDG_DATA_HOME": str(seed / "data"),
            "XDG_STATE_HOME": str(seed / "state"),
        }
    )
    for name in ("home", "config", "data", "state"):
        (seed / name).mkdir(mode=0o700)
    _run_command(
        [str(runtime / "bin" / "gc"), "import", "install", "--city", str(city)],
        env=seed_env,
        timeout=900,
    )
    cache = seed / "gc" / "cache" / "repos"
    if not cache.is_dir():
        raise RunnerError(f"Gas City did not create the expected U3 pack cache: {cache}")
    env["U3_PACK_CACHE"] = str(cache)


def _test_files(kind: str) -> list[pathlib.Path]:
    if kind == "policy":
        return sorted(
            path
            for path in POLICY_ROOT.glob(POLICY_TEST_GLOB)
            if path.name != "__init__.py"
        )
    if kind == "fixtures":
        return sorted(FIXTURE_ROOT.rglob(FIXTURE_TEST_GLOB))
    raise RunnerError(f"unknown test file kind: {kind}")


def _run_python_tests(kind: str, env: dict[str, str]) -> None:
    files = _test_files(kind)
    if kind == "fixtures":
        files = [*files, ACP_ACCEPTANCE]
    for path in files:
        print(f"==> python {path.relative_to(ROOT)}", flush=True)
        _run_command([sys.executable, str(path)], env=env, timeout=1800)


def _run_acceptance(env: dict[str, str]) -> None:
    runtime = pathlib.Path(env["GC_CONTRIBUTOR_ROOT"])
    env["D2B_INGRESS_RUNTIME"] = str(runtime)
    env["U3_PACK_CACHE"] = env.get("U3_PACK_CACHE", "")
    env["D2B_INGRESS_RUN_ROOT"] = env["D2B_GASCITY_CHECK_RUN_ROOT"]
    print(f"==> ingress {INGRESS_FIXTURE.relative_to(ROOT)}", flush=True)
    _run_command([sys.executable, str(INGRESS_FIXTURE)], env=env, timeout=1800)


def _run_python_policy(env: dict[str, str]) -> None:
    _run_python_tests("policy", env)


def _run_python_fixtures(env: dict[str, str]) -> None:
    _run_python_tests("fixtures", env)


def _run_rollback(env: dict[str, str]) -> None:
    print(f"==> rollback {ROLLBACK_ACCEPTANCE.relative_to(ROOT)}", flush=True)
    _run_command([sys.executable, str(ROLLBACK_ACCEPTANCE)], env=env, timeout=1800)


def _run_generated(env: dict[str, str], *, write: bool = False) -> None:
    command = [sys.executable, str(ROOT / "scripts" / "generate_inventory.py")]
    command.append("--write" if write else "--check")
    _run_command(command, env=env)


def _run_privacy(env: dict[str, str]) -> None:
    _run_command(
        [
            sys.executable,
            str(ROOT / "scripts" / "privacy_scan.py"),
            "--root",
            str(ROOT),
        ],
        env=env,
    )


def _run_static(env: dict[str, str]) -> None:
    _run_command(
        [sys.executable, str(ROOT / "scripts" / "static_policy.py"), "--root", str(ROOT)],
        env=env,
    )


def _create_run_root() -> tuple[str, pathlib.Path]:
    for _ in range(10):
        safe_id = f"r-{secrets.token_hex(8)}"
        try:
            run_root = pathlib.Path(
                tempfile.mkdtemp(prefix=f"d2b-gascity-check-{safe_id}-")
            )
        except OSError:
            continue
        os.chmod(run_root, 0o700)
        return safe_id, run_root
    raise RunnerError("could not allocate a unique per-run check root")


def cleanup_scratch(run_root: pathlib.Path) -> None:
    try:
        shutil.rmtree(run_root)
    except FileNotFoundError:
        pass


def run(command: str) -> int:
    try:
        run_id, run_root = _create_run_root()
    except RunnerError as error:
        print(f"FAIL repository check: {error}", file=sys.stderr)
        return 1
    env = _safe_environment(
        {
            "D2B_GASCITY_CHECK_RUN_ID": run_id,
            "D2B_GASCITY_CHECK_RUN_ROOT": str(run_root),
        }
    )
    try:
        if command in RUNTIME_COMMANDS:
            runtime = _ensure_runtime(env, run_root)
            _ensure_pack_cache(runtime, env, run_root)
        if command == "policy":
            _run_python_policy(env)
        elif command == "fixtures":
            _run_python_fixtures(env)
        elif command == "ingress":
            _run_acceptance(env)
        elif command == "rollback":
            _run_rollback(env)
        elif command == "generated":
            _run_generated(env)
        elif command == "privacy":
            _run_privacy(env)
        elif command == "workflow":
            _run_static(env)
            _run_python_tests("policy", env)
        elif command == "static":
            _run_static(env)
        elif command == "check":
            _run_python_policy(env)
            _run_python_tests("fixtures", env)
            _run_rollback(env)
            _run_generated(env)
            _run_privacy(env)
            _run_static(env)
            _run_acceptance(env)
        elif command == "update-generated":
            _run_generated(env, write=True)
        else:
            raise RunnerError(f"unknown command: {command}")
    except RunnerError as error:
        print(f"FAIL repository check: {error}", file=sys.stderr)
        return 1
    finally:
        cleanup_scratch(run_root)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "policy",
            "fixtures",
            "ingress",
            "rollback",
            "generated",
            "privacy",
            "workflow",
            "static",
            "check",
            "update-generated",
        ),
    )
    args = parser.parse_args(argv)
    return run(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
