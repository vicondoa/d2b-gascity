#!/usr/bin/env python3
"""Generate the deterministic repository source and check inventory."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "generated" / "repository-inventory.json"
OUTPUT_RELATIVE = "tests/generated/repository-inventory.json"
FALLBACK_IGNORED_DIRECTORIES = frozenset(
    {
        ".cache",
        ".git",
        ".pytest_cache",
        ".scratch",
        "__pycache__",
        "result",
        "result-1",
    }
)
GOVERNANCE_FILES = frozenset(
    {
        ".gitignore",
        "AGENTS.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "PROVENANCE.md",
        "README.md",
        "SECURITY.md",
    }
)
LIVE_MARKERS = ("feasibility", "live")
TEST_EXECUTION_ROLES = frozenset(
    {
        "documentation",
        "executed policy",
        "executed fixture",
        "explicit hermetic acceptance",
        "ingress acceptance",
        "runner",
        "helper/fixture data",
        "Nix check",
        "VM check",
        "generated data",
        "manual",
    }
)


def _files(root: pathlib.Path, relative: str) -> list[str]:
    path = root / relative
    if path.is_file() or path.is_symlink():
        return [relative]
    if not path.is_dir():
        return []
    return sorted(
        candidate.relative_to(root).as_posix()
        for candidate in path.rglob("*")
        if candidate.is_file() or candidate.is_symlink()
    )


def _git_files(root: pathlib.Path) -> list[str] | None:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-co",
                "--exclude-standard",
                "-z",
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    paths = [
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]
    return sorted(
        path
        for path in paths
        if (root / path).is_file() or (root / path).is_symlink()
    )


def _fallback_files(root: pathlib.Path) -> list[str]:
    result: list[str] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in FALLBACK_IGNORED_DIRECTORIES
            and not (pathlib.Path(current) / directory).is_symlink()
        )
        for name in sorted(files):
            path = pathlib.Path(current) / name
            if path.is_file() or path.is_symlink():
                result.append(path.relative_to(root).as_posix())
    return result


def _repository_files(root: pathlib.Path) -> list[str]:
    return _git_files(root) or _fallback_files(root)


def _flake_names(root: pathlib.Path) -> tuple[list[str], list[str]]:
    text = (root / "flake.nix").read_text(encoding="utf-8")
    checks_start = text.index("      checks =")
    vm_start = text.index("      vmChecks =", checks_start)
    checks_body = text[checks_start:vm_start]
    attr_start = checks_body.rfind("        {\n")
    checks_body = checks_body[attr_start:]
    checks = sorted(
        set(re.findall(r"(?m)^\s{10}([A-Za-z0-9][A-Za-z0-9_-]*)\s*=", checks_body))
    )
    vm_body = text[vm_start:]
    vm = sorted(
        set(re.findall(r"(?m)^\s{8}([A-Za-z0-9][A-Za-z0-9_-]*)\s*=", vm_body))
    )
    return checks, vm


def _category(path: str) -> str:
    if path == OUTPUT_RELATIVE:
        return "generated_excluded"
    if path.startswith(".github/workflows/"):
        return "workflows"
    if path.startswith("tests/"):
        return "tests"
    if path.startswith("docs/"):
        return "docs"
    if path in GOVERNANCE_FILES or path.startswith(".github/"):
        return "governance"
    return "production_sources"


def _runner_acceptance_paths(root: pathlib.Path) -> set[str]:
    runner = root / "tests" / "run.py"
    if not runner.is_file():
        return set()
    text = runner.read_text(encoding="utf-8")
    paths = set(re.findall(r"tests/acceptance/[A-Za-z0-9_.-]+\.py", text))
    paths.update(
        "tests/acceptance/" + name
        for name in re.findall(
            r'ROOT\s*/\s*"tests"\s*/\s*"acceptance"\s*/\s*"([A-Za-z0-9_.-]+\.py)"',
            text,
        )
    )
    return paths


def _runner_literal(source: str, name: str) -> str:
    match = re.search(
        rf"(?m)^{re.escape(name)}\s*=\s*(['\"])(.+?)\1\s*$",
        source,
    )
    if match is None:
        raise ValueError(f"tests/run.py is missing execution constant {name}")
    return match.group(2)


def _runner_execution_paths(
    root: pathlib.Path,
    paths: list[str],
) -> dict[str, set[str]]:
    runner = root / "tests" / "run.py"
    if not runner.is_file():
        return {}
    source = runner.read_text(encoding="utf-8")
    policy_glob = _runner_literal(source, "POLICY_TEST_GLOB")
    fixture_glob = _runner_literal(source, "FIXTURE_TEST_GLOB")
    ingress_acceptance = _runner_literal(source, "INGRESS_FIXTURE_RELATIVE")
    explicit_acceptance = _runner_acceptance_paths(root)
    policy = {
        path
        for path in paths
        if path.startswith("tests/policy/")
        and fnmatch.fnmatch(path.removeprefix("tests/policy/"), policy_glob)
        and pathlib.PurePosixPath(path).name != "__init__.py"
    }
    fixtures = {
        path
        for path in paths
        if path.startswith("tests/fixtures/")
        and fnmatch.fnmatch(pathlib.PurePosixPath(path).name, fixture_glob)
    }
    return {
        "executed policy": policy,
        "executed fixture": fixtures,
        "explicit hermetic acceptance": explicit_acceptance,
        "ingress acceptance": {ingress_acceptance},
        "runner": {"tests/run.py"},
    }


def _flake_test_paths(root: pathlib.Path) -> tuple[set[str], set[str]]:
    flake = root / "flake.nix"
    if not flake.is_file():
        return set(), set()
    text = flake.read_text(encoding="utf-8")
    nix_paths = {
        f"tests/{match.group(1)}/{match.group(2)}"
        for match in re.finditer(
            r"\./tests/(nix|smoke)/([A-Za-z0-9_.-]+\.nix)",
            text,
        )
    }
    vm_paths = {
        f"tests/host/{match.group(1)}"
        for match in re.finditer(
            r"\./tests/host/([A-Za-z0-9_.-]+\.nix)",
            text,
        )
    }
    return nix_paths, vm_paths


def _test_execution_inventory(
    root: pathlib.Path,
    paths: list[str],
) -> list[dict[str, str]]:
    assignments: dict[str, str] = {}

    def assign(path: str, role: str) -> None:
        if path in assignments:
            raise ValueError(
                f"test artifact has multiple execution roles: {path}: "
                f"{assignments[path]}, {role}"
            )
        assignments[path] = role

    runner_paths = _runner_execution_paths(root, paths)
    if runner_paths:
        for role, role_paths in runner_paths.items():
            for path in role_paths:
                if path in paths:
                    assign(path, role)

    nix_paths, vm_paths = _flake_test_paths(root)
    for path in paths:
        if path in assignments:
            continue
        if path == OUTPUT_RELATIVE:
            assign(path, "generated data")
        elif path == "tests/README.md" or (
            path.startswith("tests/") and path.endswith(".md")
        ):
            assign(path, "documentation")
        elif path == "tests/acceptance/copilot-acp-feasibility.py":
            assign(path, "manual")
        elif path in nix_paths:
            assign(path, "Nix check")
        elif path in vm_paths:
            assign(path, "VM check")
        elif path.startswith("tests/fixtures/"):
            assign(path, "helper/fixture data")
        else:
            raise ValueError(f"unclassified test artifact: {path}")

    if runner_paths:
        for role, expected in runner_paths.items():
            actual = {
                path for path, assigned_role in assignments.items() if assigned_role == role
            }
            if actual != expected:
                raise ValueError(
                    "tests/run.py execution inventory drift for "
                    f"{role}: expected={sorted(expected)}, actual={sorted(actual)}"
                )

    unexpected_roles = set(assignments.values()) - TEST_EXECUTION_ROLES
    if unexpected_roles:
        raise ValueError(f"unknown test execution roles: {sorted(unexpected_roles)}")
    if set(assignments) != set(paths):
        raise ValueError(
            "test execution inventory is not exhaustive: "
            f"missing={sorted(set(paths) - set(assignments))}"
        )
    return [
        {"path": path, "role": assignments[path]}
        for path in sorted(assignments)
    ]


def _is_manual_surface(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in LIVE_MARKERS)


def _acceptance_inventory(root: pathlib.Path) -> list[dict[str, object]]:
    paths = sorted(
        path
        for path in _repository_files(root)
        if (
            path.startswith("tests/acceptance/")
            and path.endswith(".py")
        )
        or path.startswith("docs/feasibility/")
    )
    executed = _runner_acceptance_paths(root)
    entries: list[dict[str, object]] = []
    for path in paths:
        if path in executed:
            entries.append(
                {
                    "executed": True,
                    "mode": "hermetic",
                    "path": path,
                    "reason": "executed by tests/run.py fixture graph",
                }
            )
        elif _is_manual_surface(path):
            entries.append(
                {
                    "executed": False,
                    "mode": "manual",
                    "path": path,
                    "reason": "real credential-backed or live feasibility surface",
                }
            )
        else:
            raise ValueError(
                "acceptance surface is neither executed by tests/run.py nor "
                f"explicitly manual: {path}"
            )
    return entries


def inventory(root: pathlib.Path = ROOT) -> dict[str, Any]:
    paths = _repository_files(root)
    categories: dict[str, list[str]] = {
        "docs": [],
        "generated_excluded": [],
        "governance": [],
        "production_sources": [],
        "tests": [],
        "workflows": [],
    }
    for path in paths:
        categories[_category(path)].append(path)
    for values in categories.values():
        values.sort()

    categorized = [
        path
        for values in categories.values()
        for path in values
    ]
    duplicates = sorted(
        path
        for path in set(categorized)
        if categorized.count(path) > 1
    )
    uncategorized = sorted(set(paths) - set(categorized))
    if duplicates or uncategorized or set(categorized) != set(paths):
        raise ValueError(
            "repository inventory categorization is not exhaustive: "
            f"duplicates={duplicates}, uncategorized={uncategorized}"
        )

    test_execution = _test_execution_inventory(
        root,
        sorted(path for path in paths if path.startswith("tests/")),
    )
    checks, vm_checks = _flake_names(root)
    return {
        "categories": categories,
        "docs": categories["docs"],
        "flake_checks": checks,
        "governance": categories["governance"],
        "manual_acceptance": _acceptance_inventory(root),
        "production_sources": categories["production_sources"],
        "schema": 1,
        "tests": categories["tests"],
        "test_execution": test_execution,
        "vm_checks": vm_checks,
        "workflows": categories["workflows"],
    }


def render(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=ROOT)
    parser.add_argument("--output", type=pathlib.Path, default=None)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    output = (args.output or (root / OUTPUT_RELATIVE)).resolve()
    try:
        expected = render(inventory(root))
    except (OSError, ValueError) as error:
        print(f"could not generate repository inventory: {error}", file=sys.stderr)
        return 1
    if args.write:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(expected)
        return 0
    try:
        actual = output.read_bytes()
    except OSError as error:
        print(f"generated inventory is missing: {output}: {error}", file=sys.stderr)
        return 1
    if actual != expected:
        print(f"generated inventory drift: {output}", file=sys.stderr)
        if args.check or not args.write:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
