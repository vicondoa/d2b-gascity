#!/usr/bin/env python3
"""Scan repository content for private values and runtime state."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import pathlib
import posixpath
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Iterable


RUNTIME_COMPONENTS = frozenset(
    {
        ".beads",
        ".cache",
        ".dolt",
        ".gc",
        ".runtime",
        ".state",
        "cache",
        "Dolt",
        "db",
        "database",
        "log",
        "logs",
        "run",
        "session",
        "sessions",
        "socket",
        "sockets",
        "worktree",
        "worktrees",
    }
)
RUNTIME_SUFFIXES = (
    ".cache",
    ".db",
    ".dump",
    ".log",
    ".sock",
    ".socket",
    ".sqlite",
    ".sqlite3",
)
GENERIC_PATHS = (
    "/etc/d2b-gascity",
    "/etc/nixos",
    "/nix/store",
    "/run/d2b-gascity",
    "/var/lib/d2b-gascity",
    "/var/lib/d2b-gascity-tinyauth",
)
ALLOWED_EMAIL_DOMAINS = frozenset({"example.com", "example.invalid", "example.test"})
GENERIC_PLACEHOLDERS = frozenset(
    {
        "fake",
        "false",
        "fixture",
        "none",
        "null",
        "placeholder",
        "redacted",
        "test",
        "true",
        "unset",
    }
)
SAFE_NULL_VALUES = frozenset({"", "~", "false", "none", "null", "true", "unset"})
ASSIGNMENT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".conf",
        ".env",
        ".ini",
        ".json",
        ".md",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)

TOKEN_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b"),
)
SECRET_KEY = (
    r"(?:api[_-]?key|client[_-]?secret|password|private[_-]?key|secret|token)"
)
PRIVATE_KEY = (
    r"(?:authority|host|instance[_-]?id|tenant[_-]?id|user[_-]?id|"
    r"channel[_-]?id|credential[_-]?path)"
)
ASSIGNMENT_VALUE = (
    r'(?:"(?:\\.|[^"\\\r\n])*"|'
    r"'(?:''|[^'\r\n])*'|"
    r"[^\s,#}\]]+)"
)


def _assignment_key(key: str) -> str:
    return rf'(?:"(?:{key})"|\'(?:{key})\'|(?:{key}))'


SECRET_ASSIGNMENT = re.compile(
    rf"(?im)(?:^|[{{,])\s*-?\s*{_assignment_key(SECRET_KEY)}"
    rf"\s*[:=]\s*(?P<value>{ASSIGNMENT_VALUE})",
)
PRIVATE_ASSIGNMENT = re.compile(
    rf"(?im)(?:^|[{{,])\s*-?\s*{_assignment_key(PRIVATE_KEY)}"
    rf"\s*[:=]\s*(?P<value>{ASSIGNMENT_VALUE})",
)
ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_.-])/(?:home|Users|private|srv|opt)/[^\s\"']+")
IP_ADDRESS = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
EMAIL_ADDRESS = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PRIVATE_PAYLOAD_MARKERS = (
    re.compile(
        r"(?i)\b(?:live[_-]prompt|live[_-]response|private[_-]?"
        r"payload)\b"
    ),
    re.compile(
        r"(?i)(?<![\w-])[\"']?(?:assistant_response|model_response|private_"
        r"payload)"
        r"[\"']?\s*[:=]"
    ),
)


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    detail: str


@dataclass(frozen=True)
class GitIndexEntry:
    mode: int
    path: str
    oid: str


def _is_generic_path(value: str) -> bool:
    return any(value == item or value.startswith(item + "/") for item in GENERIC_PATHS)


def _is_generic_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in GENERIC_PLACEHOLDERS or normalized.startswith(
        (
            "fake-",
            "fake_",
            "fake.",
            "fixture-",
            "fixture_",
            "fixture.",
            "test-",
            "test_",
            "test.",
        )
    )


def _is_test_path(relative: pathlib.PurePosixPath) -> bool:
    return bool(relative.parts) and relative.parts[0] == "tests"


def _is_safe_assignment_value(
    value: str,
    relative: pathlib.PurePosixPath,
    *,
    private: bool,
) -> bool:
    normalized = value.strip().lower()
    if normalized in SAFE_NULL_VALUES or normalized in {"placeholder", "redacted"}:
        return True
    if _is_test_path(relative) and _is_generic_placeholder(value):
        return True
    if private:
        if normalized in {"localhost", "127.0.0.1", "::1"}:
            return True
        if _contains_example_domain(value):
            return True
        try:
            ipaddress.ip_address(value)
        except ValueError:
            pass
        else:
            return _is_allowed_ip(value)
    return False


def _assignment_value(match: re.Match[str]) -> str:
    value = match.group("value").strip().rstrip(",")
    if len(value) < 2 or value[0] not in {"'", '"'}:
        return value
    if value[0] == '"':
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
        return parsed if isinstance(parsed, str) else value
    return value[1:-1].replace("''", "'")


def _contains_example_domain(value: str) -> bool:
    lowered = value.lower()
    return any(
        re.search(
            rf"(?<![a-z0-9-])(?:[a-z0-9-]+\.)*{re.escape(domain)}"
            r"(?![a-z0-9-])",
            lowered,
        )
        for domain in ALLOWED_EMAIL_DOMAINS
    )


def _is_allowed_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return True
    if address.is_loopback:
        return True
    return any(
        address in ipaddress.ip_network(network)
        for network in (
            "0.0.0.0/32",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "192.0.2.0/24",
            "198.51.100.0/24",
            "203.0.113.0/24",
        )
    )


def _iter_files(root: pathlib.Path) -> Iterable[pathlib.Path]:
    active_run_root: pathlib.Path | None = None
    configured_run_root = os.environ.get("D2B_GASCITY_CHECK_RUN_ROOT")
    if configured_run_root:
        active_run_root = pathlib.Path(configured_run_root).expanduser().resolve(
            strict=False
        )
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = pathlib.Path(current)
        if active_run_root is not None and current_path.resolve(
            strict=False
        ).is_relative_to(active_run_root):
            directories[:] = []
            files[:] = []
            continue
        retained_directories: list[str] = []
        for directory in sorted(directories):
            candidate = current_path / directory
            if directory == ".git" or directory in {
                "result",
                "result-1",
                "__pycache__",
                ".pytest_cache",
            }:
                continue
            if candidate.is_symlink():
                yield candidate
                continue
            retained_directories.append(directory)
        directories[:] = retained_directories
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink() or path.is_file():
                yield path


def _git_index_entries(root: pathlib.Path) -> dict[str, GitIndexEntry] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-s", "-z"],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    entries: dict[str, GitIndexEntry] = {}
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        try:
            header, raw_path = item.split(b"\t", 1)
            mode, oid, _stage = header.split()
            mode_value = int(mode, 8)
        except (ValueError, IndexError):
            continue
        path = raw_path.decode("utf-8", errors="surrogateescape")
        entries[path] = GitIndexEntry(
            mode=mode_value,
            path=path,
            oid=oid.decode("ascii"),
        )
    return entries


def _git_tracked(root: pathlib.Path) -> set[str] | None:
    entries = _git_index_entries(root)
    return None if entries is None else set(entries)


def _git_blob(root: pathlib.Path, oid: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "cat-file", "blob", oid],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _is_binary(data: bytes) -> bool:
    if b"\0" in data:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    controls = sum(byte < 0x09 or 0x0E <= byte < 0x20 for byte in data)
    return bool(data) and controls * 20 > len(data)


def _read_text(path: pathlib.Path) -> str | None:
    try:
        if path.is_symlink():
            return os.readlink(path)
        data = path.read_bytes()
    except OSError as error:
        return f"<unreadable: {error}>"
    if b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")


def _scan_symlink_target(
    relative: pathlib.PurePosixPath,
    target: str,
) -> list[Finding]:
    if target.startswith("/"):
        return [
            Finding(
                relative.as_posix(),
                "unsafe-symlink-target",
                target,
            )
        ]
    normalized = posixpath.normpath(
        posixpath.join(relative.parent.as_posix(), target)
    )
    if normalized == ".." or normalized.startswith("../"):
        return [
            Finding(
                relative.as_posix(),
                "unsafe-symlink-target",
                target,
            )
        ]
    return []


def _scan_path(relative: pathlib.PurePosixPath, tracked: bool) -> list[Finding]:
    findings: list[Finding] = []
    parts = set(relative.parts)
    dangerous = bool(parts & RUNTIME_COMPONENTS) or relative.name.lower().endswith(
        RUNTIME_SUFFIXES
    )
    if parts & RUNTIME_COMPONENTS:
        component = sorted(parts & RUNTIME_COMPONENTS)[0]
        findings.append(Finding(relative.as_posix(), "runtime-path", component))
    if relative.name.lower().endswith(RUNTIME_SUFFIXES):
        findings.append(Finding(relative.as_posix(), "runtime-file", relative.name))
    if not tracked and dangerous:
        findings.append(Finding(relative.as_posix(), "ignored-or-untracked", "dangerous file"))
    return findings


def _scan_text(
    relative: pathlib.PurePosixPath,
    text: str,
    *,
    tracked: bool,
) -> list[Finding]:
    findings: list[Finding] = []
    for pattern in TOKEN_PATTERNS:
        if pattern.search(text):
            findings.append(Finding(relative.as_posix(), "credential-material", pattern.pattern))
            break

    if pathlib.PurePosixPath(relative).suffix.lower() in ASSIGNMENT_SUFFIXES:
        for match in SECRET_ASSIGNMENT.finditer(text):
            value = _assignment_value(match)
            if not _is_safe_assignment_value(value, relative, private=False):
                findings.append(
                    Finding(
                        relative.as_posix(),
                        "credential-assignment",
                        "secret-like assignment",
                    )
                )
                break

        for match in PRIVATE_ASSIGNMENT.finditer(text):
            value = _assignment_value(match)
            if not _is_safe_assignment_value(value, relative, private=True):
                findings.append(
                    Finding(
                        relative.as_posix(),
                        "private-assignment",
                        "host-private value",
                    )
                )
                break

    for match in ABSOLUTE_PATH.finditer(text):
        value = match.group(0)
        if not _is_generic_path(value):
            findings.append(Finding(relative.as_posix(), "host-private-path", value))
            break

    for match in IP_ADDRESS.finditer(text):
        if not _is_allowed_ip(match.group(0)):
            findings.append(Finding(relative.as_posix(), "host-private-address", match.group(0)))
            break

    for match in EMAIL_ADDRESS.finditer(text):
        domain = match.group(1).lower()
        if domain not in ALLOWED_EMAIL_DOMAINS and not any(
            domain.endswith("." + allowed) for allowed in ALLOWED_EMAIL_DOMAINS
        ):
            findings.append(Finding(relative.as_posix(), "host-private-authority", match.group(0)))
            break

    for pattern in PRIVATE_PAYLOAD_MARKERS:
        if pattern.search(text):
            findings.append(
                Finding(
                    relative.as_posix(),
                    "unredacted-private-" "payload",
                    pattern.pattern,
                )
            )
            break
    return findings


def scan_repository(root: pathlib.Path, *, tracked_only: bool = False) -> list[Finding]:
    root = root.expanduser().resolve()
    index_entries = _git_index_entries(root)
    tracked = None if index_entries is None else set(index_entries)
    findings: list[Finding] = []
    for path in _iter_files(root):
        relative = pathlib.PurePosixPath(path.relative_to(root).as_posix())
        relative_name = relative.as_posix()
        is_tracked = tracked is None or relative_name in tracked
        path_findings = _scan_path(relative, is_tracked)
        if tracked_only and tracked is not None and not is_tracked:
            path_findings = []
        findings.extend(path_findings)
        if tracked_only and tracked is not None and not is_tracked:
            continue
        text = _read_text(path)
        if text is not None:
            if path.is_symlink():
                findings.extend(
                    _scan_symlink_target(
                        relative,
                        text,
                    )
                )
            findings.extend(
                _scan_text(
                    relative,
                    text,
                    tracked=is_tracked,
                )
            )
        elif is_tracked and not path.is_symlink():
            findings.append(
                Finding(
                    relative_name,
                    "tracked-binary",
                    "working-tree content is binary",
                )
            )

    if index_entries is not None:
        for relative_name, entry in sorted(index_entries.items()):
            relative = pathlib.PurePosixPath(relative_name)
            findings.extend(_scan_path(relative, True))
            blob = _git_blob(root, entry.oid)
            if blob is None:
                findings.append(
                    Finding(relative_name, "git-object-unreadable", entry.oid)
                )
                continue
            if entry.mode == 0o120000:
                target = blob.decode("utf-8", errors="replace")
                findings.extend(_scan_symlink_target(relative, target))
                findings.extend(
                    _scan_text(relative, target, tracked=True)
                )
            elif _is_binary(blob):
                findings.append(Finding(relative_name, "tracked-binary", entry.oid))
            else:
                findings.extend(
                    _scan_text(
                        relative,
                        blob.decode("utf-8", errors="replace"),
                        tracked=True,
                    )
                )
    return sorted(set(findings), key=lambda finding: (finding.path, finding.rule, finding.detail))


def render_findings(findings: Iterable[Finding]) -> str:
    return json.dumps([asdict(finding) for finding in findings], indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--tracked-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    findings = scan_repository(args.root, tracked_only=args.tracked_only)
    if args.json:
        sys.stdout.write(render_findings(findings))
    else:
        for finding in findings:
            print(f"{finding.path}: {finding.rule}: {finding.detail}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
