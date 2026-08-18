#!/usr/bin/env python3
"""Apply repository-local static policy without external harnesses."""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys


ACTION_REF = re.compile(
    r"(?m)^\s*(?:-\s*)?(?:[\"']?uses[\"']?)\s*:\s*"
    r"([^\s@#]+)@([^\s#]+)"
)
BLOCK_USES = re.compile(
    r"""^\s*(?:-\s*)?(?:["']?uses["']?)\s*:\s*(.+?)\s*$"""
)


def _yaml_scalar(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    if value[0] in {"'", '"'}:
        try:
            parsed = ast.literal_eval(value.split("#", 1)[0].rstrip())
        except (SyntaxError, ValueError):
            return value
        return parsed if isinstance(parsed, str) else value
    return value.split("#", 1)[0].rstrip()


def _strip_yaml_comment(line: str) -> str:
    quote: str | None = None
    index = 0
    while index < len(line):
        character = line[index]
        if quote is not None:
            if quote == "'" and character == "'" and index + 1 < len(line) and line[index + 1] == "'":
                index += 2
                continue
            if character == "\\" and quote == '"' and index + 1 < len(line):
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
        index += 1
    return line.rstrip()


def _uses_key_occurrences(line: str) -> list[tuple[int, int, bool]]:
    source = _strip_yaml_comment(line)
    occurrences: list[tuple[int, int, bool]] = []
    quote: str | None = None
    flow_depth = 0
    index = 0

    def context_is_key(start: int) -> bool:
        prefix = source[:start].strip()
        if flow_depth:
            return prefix.endswith(("{", "[", ","))
        return prefix in {"", "-"}

    while index < len(source):
        character = source[index]
        if quote is not None:
            if quote == "'" and character == "'" and index + 1 < len(source) and source[index + 1] == "'":
                index += 2
                continue
            if character == "\\" and quote == '"' and index + 1 < len(source):
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue

        if character in {"'", '"'}:
            closing = source.find(character, index + 1)
            if (
                closing == index + 5
                and source[index + 1 : closing] == "uses"
                and source[closing + 1 :].lstrip().startswith(":")
                and context_is_key(index)
            ):
                occurrences.append((index, closing, flow_depth == 0))
                index = closing + 1
                continue
            quote = character
            index += 1
            continue

        if (
            source.startswith("uses", index)
            and (index == 0 or not (source[index - 1].isalnum() or source[index - 1] in "_.-"))
            and (index + 4 == len(source) or not (source[index + 4].isalnum() or source[index + 4] in "_.-"))
        ):
            end = index + 4
            while end < len(source) and source[end].isspace():
                end += 1
            if end < len(source) and source[end] == ":" and context_is_key(index):
                occurrences.append((index, end - 1, flow_depth == 0))
                index = end + 1
                continue

        if character in "{[":
            flow_depth += 1
        elif character in "}]" and flow_depth:
            flow_depth -= 1
        index += 1
    return occurrences


def _workflow_uses_with_unsupported(text: str) -> tuple[list[str], int]:
    values: list[str] = []
    unsupported = 0
    for line in text.splitlines():
        source = _strip_yaml_comment(line)
        for start, end, block_style in _uses_key_occurrences(line):
            if not block_style:
                unsupported += 1
                continue
            match = BLOCK_USES.fullmatch(source)
            if match is None:
                unsupported += 1
                continue
            raw_value = match.group(1).strip()
            if not raw_value or raw_value.startswith(("{", "[")):
                unsupported += 1
                continue
            value = _yaml_scalar(raw_value)
            if not value:
                unsupported += 1
                continue
            values.append(value)
    return values, unsupported


def _workflow_uses(text: str) -> list[str]:
    values, _unsupported = _workflow_uses_with_unsupported(text)
    return values


def _is_pinned_use(value: str) -> bool:
    if value.startswith("./"):
        return True
    if value.startswith("docker://"):
        return re.fullmatch(
            r"docker://[^@\s]+@sha256:[0-9a-fA-F]{64}",
            value,
        ) is not None
    return re.fullmatch(
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[^\s@]+)?@[0-9a-fA-F]{40}",
        value,
    ) is not None


def workflow_findings(root: pathlib.Path) -> list[str]:
    findings: list[str] = []
    workflow_root = root / ".github" / "workflows"
    for path in sorted(workflow_root.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?m)^\s*runs-on:\s*ubuntu-(?:latest|24\.04)\s*$", text):
            findings.append(
                f"{path.relative_to(root)}: runner image must not float"
            )
        values, unsupported = _workflow_uses_with_unsupported(text)
        findings.extend(
            f"{path.relative_to(root)}: unsupported uses syntax"
            for _ in range(unsupported)
        )
        for value in values:
            if not _is_pinned_use(value):
                findings.append(
                    f"{path.relative_to(root)}: unpinned action {value}"
                )
    return findings


def static_findings(root: pathlib.Path) -> list[str]:
    findings = workflow_findings(root)
    makefile = root / "Makefile"
    if makefile.is_file():
        text = makefile.read_text(encoding="utf-8")
        if re.search(r"(?m)^\s*include\s+", text):
            findings.append("Makefile: external include is not allowed")
        for marker in ("tests/runner.sh", "d2b-test", "d2b/Makefile"):
            if marker in text:
                findings.append(f"Makefile: forbidden d2b harness marker {marker}")
    check = root / ".github" / "workflows" / "check.yml"
    if check.is_file():
        text = check.read_text(encoding="utf-8").lower()
        for marker in (
            "secrets.",
            "speckit",
            "signoff",
            "panel",
            "cargo",
            "rustup",
            "tests/acceptance/copilot-acp-feasibility.py",
            "tests/acceptance/live.py",
        ):
            if marker in text:
                findings.append(f".github/workflows/check.yml: forbidden marker {marker}")
    for relative in ("tests/run.py", "scripts/generate_inventory.py", "scripts/privacy_scan.py"):
        path = root / relative
        if path.is_file():
            text = path.read_text(encoding="utf-8").lower()
            for marker in ("tests/runner.sh", "tests/layer1-jobs.json", "speckit", "signoff"):
                if marker in text:
                    findings.append(f"{relative}: forbidden d2b harness marker {marker}")
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--nix", action="store_true", help="reserved for Nix check invocation")
    args = parser.parse_args(argv)
    findings = static_findings(args.root.expanduser().resolve())
    for finding in findings:
        print(finding, file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
