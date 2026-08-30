from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import re
import signal
import shutil
import subprocess
import tempfile
import time
import tomllib
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRATCH_ROOT = ROOT / ".scratch"


def _temporary_root(prefix: str) -> pathlib.Path:
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    return pathlib.Path(
        tempfile.mkdtemp(prefix=prefix, dir=SCRATCH_ROOT)
    )


CITY_RELATIVE = pathlib.Path("cities") / "d2b-gascity"
CITY_ROOT = ROOT / CITY_RELATIVE
CORE_PACK_RELATIVE = pathlib.Path("packs") / "core-city"
CORE_PACK_ROOT = ROOT / CORE_PACK_RELATIVE
PACK_COMMIT = "9f98ea4e1974cb49d18cd0c453eb81b2370cca84"
GASCITY_PACK_SOURCE = (
    "https://github.com/gastownhall/gascity-packs/tree/main/gascity"
)
GASCITY_ROLES_PACK_SOURCE = (
    "https://github.com/gastownhall/gascity-packs/tree/main/gascity/roles"
)
DISCORD_PACK_SOURCE = (
    "https://github.com/gastownhall/gascity-packs/tree/main/discord"
)
GASCITY_COMMIT = "f895c0ff47d6ee9334ed282a416387eb5b084d24"
GASCITY_VERSION = "1.4.1"
GASCITY_ARCHIVE_SHA256 = (
    "8d8c8b511db3fc44931445aab5cb9f212509c0867105c880d6c3d0e6e5d33e42"
)
BEADS_VERSION = "1.2.2"
BEADS_ARCHIVE_SHA256 = (
    "8140098a51d3b81d5548d1c5e6db1a2d9930e5d141efe2a4bff7d079c4d321e8"
)
DOLT_VERSION = "2.1.7"
DOLT_ARCHIVE_SHA256 = (
    "15983e811341ed94e5d47fbfc41d2f57d8c7aa65eee511d25a3c3fd5477e28e7"
)
CITY_AUTHORED_FILES = (
    "city.toml",
    "pack.toml",
    "packs.lock",
    "model-tiers.toml",
    "formulas/mol-d2b-discord-fix-issue.toml",
    "template-fragments/d2b-governance.template.md",
    "agents/mayor/agent.toml",
    "agents/mayor/prompt.template.md",
)
CORE_PACK_FILES = (
    "pack.toml",
    "model-tiers.base.toml",
    "commands/gen-model-tiers/command.toml",
    "commands/gen-model-tiers/run.sh",
    "template-fragments/command-glossary.template.md",
    "template-fragments/operational-awareness.template.md",
    "template-fragments/mayor-operating-rhythm.template.md",
    "template-fragments/efficient-routing-rules.template.md",
    "template-fragments/sdlc-mayor-coding-rules.template.md",
)
AUTHORED_FILES = (
    *(str(CITY_RELATIVE / relative) for relative in CITY_AUTHORED_FILES),
    *(str(CORE_PACK_RELATIVE / relative) for relative in CORE_PACK_FILES),
)
RUNTIME_PATHS = (
    ".gc",
    ".beads",
    ".dolt",
    ".runtime",
    ".state",
    "run",
)
PR_BABYSIT_ROOT = ROOT / "packs" / "pr-babysit"
PR_BABYSIT_SKILL_ROOT = PR_BABYSIT_ROOT / "skills" / "pr-babysit"
PR_BABYSIT_UPSTREAM_REPOSITORY = (
    "https://github.com/EveryInc/compound-engineering-plugin"
)
PR_BABYSIT_UPSTREAM_TAG = "compound-engineering-v3.23.4"
PR_BABYSIT_UPSTREAM_COMMIT = (
    "33d9bd92689d60580e732890f94466e5793385b1"
)
PR_BABYSIT_FILES = {
    "LICENSE": {
        "source": "LICENSE",
        "sha256": (
            "61d89de7646effdaba2d0a4ab7bd0eba60b4094b83efe5bc"
            "73c7940e43e93fc6"
        ),
    },
    "skills/pr-babysit/SKILL.md": {
        "source": "skills/ce-babysit-pr/SKILL.md",
        "sha256": (
            "a611e493ae6979063d71f4990c2f6cda9c9f1a4b114a8371"
            "7c26c66c4cf4bd90"
        ),
    },
    "skills/pr-babysit/references/branch-currency.md": {
        "source": "skills/ce-babysit-pr/references/branch-currency.md",
        "sha256": (
            "8e0101ac1b73946746579630259ae5bac12ed4dd1df78aaad4"
            "df02e0c9934429"
        ),
    },
    "skills/pr-babysit/references/envelope.md": {
        "source": "skills/ce-babysit-pr/references/envelope.md",
        "sha256": (
            "74ffa9b65afccbb8add39cd9cc4b76af1a4cc9532eabde3523"
            "d78ae28e62e59a"
        ),
    },
    "skills/pr-babysit/references/pipeline.md": {
        "source": "skills/ce-babysit-pr/references/pipeline.md",
        "sha256": (
            "6b8403bcc7093d5def36e5dd84096ecc05535c4099e652b38e8"
            "ec98700b91c87"
        ),
    },
    "skills/pr-babysit/references/report.md": {
        "source": "skills/ce-babysit-pr/references/report.md",
        "sha256": (
            "31774e3ad7d5ea97d6360ff5d404ade79331d42a53ec50e8cd"
            "5bae531dc98e5b"
        ),
        "local_sha256": (
            "31d79d87f9e63940714656cb35af5746aed53cc6f263de17a60b4f0e04e6362f"
        ),
    },
    "skills/pr-babysit/references/settle.md": {
        "source": "skills/ce-babysit-pr/references/settle.md",
        "sha256": (
            "e83f49cb2511f68cf9131584737b73a91ae9a2a92435f7fd70"
            "cba40b99fc1759"
        ),
    },
    "skills/pr-babysit/references/setup.md": {
        "source": "skills/ce-babysit-pr/references/setup.md",
        "sha256": (
            "0465242d6116c3f958f76cc332c1af34896f48d8e8cc4c9716b"
            "0f089d1809954"
        ),
    },
    "skills/pr-babysit/references/tick.md": {
        "source": "skills/ce-babysit-pr/references/tick.md",
        "sha256": (
            "cf1fc87e87a3520c9446d997ff09ba2cccacb4a5e0a33f33fb"
            "9752325ede820c"
        ),
    },
    "skills/pr-babysit/references/watch-loop.md": {
        "source": "skills/ce-babysit-pr/references/watch-loop.md",
        "sha256": (
            "f2abb846f4a5fd20468c7e5a4eefa4bf2929d7dcd6256da9442b"
            "751b96213f67"
        ),
    },
    "skills/pr-babysit/scripts/pr-snapshot": {
        "source": "skills/ce-babysit-pr/scripts/pr-snapshot",
        "sha256": (
            "fd8a0b403703714a1257530e7053461e437b662b0ef381f780"
            "b8850439d980e7"
        ),
        "local_sha256": (
            "98fd2ae7a7215968fe1c85f821338f8b568e3afb8b2b234cdf1ae97635d419dc"
        ),
    },
}
PR_BABYSIT_EXCLUDED_SURFACES = {
    "stack and stack-landing behavior",
    "merge, force-push, and raw-rebase mutations",
    "workflow approval",
    "delegation to host plugins",
    "user-global skill installation",
    "scheduler or daemon lifecycle",
    "durable /tmp state",
}
PR_BABYSIT_PROJECTED_FILES = (
    "SKILL.md",
    "references/branch-currency.md",
    "references/envelope.md",
    "references/pipeline.md",
    "references/report.md",
    "references/settle.md",
    "references/setup.md",
    "references/tick.md",
    "references/watch-loop.md",
    "scripts/pr-snapshot",
)
PR_BABYSIT_PROJECTION_MARKER = ".gascity-vendored-commit"
PR_BABYSIT_LOCAL_FILES = (
    "pack.toml",
    "agents/pr-babysitter/agent.toml",
    "agents/pr-babysitter/prompt.template.md",
    "assets/scripts/project-copilot-skill.sh",
)
PR_BABYSIT_AUTHORED_FILES = (
    "LICENSE",
    "UPSTREAM.json",
    "pack.toml",
    "agents/pr-babysitter/agent.toml",
    "agents/pr-babysitter/prompt.template.md",
    "commands/pr-babysit/command.toml",
    "commands/pr-babysit/run.sh",
    "formulas/mol-pr-babysit-repair.toml",
    "orders/pr-babysit-sweep.toml",
    "assets/scripts/pr-babysit-state.py",
    "assets/scripts/pr-babysit-sweep.sh",
    "assets/scripts/project-copilot-skill.sh",
    "assets/workflows/pr-babysit/prepare-worktree.md",
    "assets/workflows/pr-babysit/validate-and-report.md",
    "skills/pr-babysit/SKILL.md",
    "skills/pr-babysit/references/branch-currency.md",
    "skills/pr-babysit/references/envelope.md",
    "skills/pr-babysit/references/pipeline.md",
    "skills/pr-babysit/references/report.md",
    "skills/pr-babysit/references/settle.md",
    "skills/pr-babysit/references/setup.md",
    "skills/pr-babysit/references/tick.md",
    "skills/pr-babysit/references/watch-loop.md",
    "skills/pr-babysit/scripts/pr-snapshot",
)
PR_BABYSIT_STATE_RUNNER = (
    PR_BABYSIT_ROOT / "commands" / "pr-babysit" / "run.sh"
)
PR_BABYSIT_REPAIR_FORMULA = (
    PR_BABYSIT_ROOT / "formulas" / "mol-pr-babysit-repair.toml"
)
PR_BABYSIT_REPAIR_PREPARE = (
    PR_BABYSIT_ROOT
    / "assets"
    / "workflows"
    / "pr-babysit"
    / "prepare-worktree.md"
)
PR_BABYSIT_REPAIR_VALIDATE = (
    PR_BABYSIT_ROOT
    / "assets"
    / "workflows"
    / "pr-babysit"
    / "validate-and-report.md"
)
PUBLISH_OPEN_PR_ASSET = (
    CITY_ROOT / "assets" / "workflows" / "publish" / "open-pr.md"
)
OFFICIAL_OPEN_PR_ASSET = (
    "If open_pr is {{open_pr}}, create a PR only after push succeeds and\n"
    "sanitized title/body from final report {{final_report}} pass policy.\n"
)


def _git(command: list[str], *, cwd: pathlib.Path, env: dict[str, str]) -> None:
    result = subprocess.run(
        ["git", *command],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise AssertionError(f"git {' '.join(command)} failed: {detail}")


def _process_ids_for(path: pathlib.Path) -> set[int]:
    process_ids: set[int] = set()
    needle = str(path).encode()
    proc_root = pathlib.Path("/proc")
    if not proc_root.is_dir():
        return process_ids
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command_line = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if needle in command_line:
            process_ids.add(int(entry.name))
    return process_ids


def _stop_processes_for(path: pathlib.Path) -> None:
    current_pid = os.getpid()
    for _ in range(20):
        process_ids = _process_ids_for(path) - {current_pid}
        if not process_ids:
            return
        for process_id in process_ids:
            try:
                os.kill(process_id, signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(0.1)
    for process_id in _process_ids_for(path) - {current_pid}:
        try:
            os.kill(process_id, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _path_metadata(path: pathlib.Path) -> tuple[int, ...] | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _tracked_runtime_state() -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).decode(
            errors="replace"
        ).strip()
        raise AssertionError(f"git ls-files failed: {detail}")
    runtime_names = {relative.encode() for relative in RUNTIME_PATHS}
    return any(
        component in runtime_names
        for path in result.stdout.split(b"\0")
        if path
        for component in path.split(b"/")
    )


def _tracked_text_files() -> list[pathlib.Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip()
        raise AssertionError(f"git ls-files failed: {detail}")

    paths: list[pathlib.Path] = []
    for raw_relative in result.stdout.split(b"\0"):
        if not raw_relative:
            continue
        relative = pathlib.Path(os.fsdecode(raw_relative))
        if relative.parts[:2] == ("docs", "plans"):
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" not in data:
            paths.append(path)
    return paths


class RootPortableCityTests(unittest.TestCase):
    def test_nested_layout_has_only_authored_city_files(self) -> None:
        for relative in AUTHORED_FILES:
            self.assertTrue((ROOT / relative).is_file(), relative)

        for relative in (
            "city.toml",
            "pack.toml",
            "packs.lock",
            "model-tiers.toml",
            "agents/mayor/agent.toml",
            "agents/mayor/prompt.template.md",
            "formulas/mol-d2b-discord-fix-issue.toml",
            "template-fragments/d2b-governance.template.md",
            "city/city.toml",
            "city/pack.toml",
            "city/packs.lock",
            "city/role-provider-matrix.json",
            "city/worktree-producer-inventory.json",
            "city/providers/README.md",
            "role-provider-matrix.json",
            "worktree-producer-inventory.json",
        ):
            self.assertFalse((ROOT / relative).exists(), relative)
        self.assertEqual(
            {path.name for path in (CITY_ROOT / "formulas").glob("*.toml")},
            {
                pathlib.Path(relative).name
                for relative in CITY_AUTHORED_FILES
                if relative.startswith("formulas/")
            },
        )
        self.assertEqual(
            {
                str(path.relative_to(CORE_PACK_ROOT))
                for path in CORE_PACK_ROOT.rglob("*")
                if path.is_file()
            },
            set(CORE_PACK_FILES),
        )

    def test_city_has_pathless_product_and_source_rigs_with_model_tiers(
        self,
    ) -> None:
        path = CITY_ROOT / "city.toml"
        text = path.read_text(encoding="utf-8")
        config = tomllib.loads(text)
        core_pack = tomllib.loads(
            (CORE_PACK_ROOT / "pack.toml").read_text(encoding="utf-8")
        )
        model_tiers = tomllib.loads(
            (CITY_ROOT / "model-tiers.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(config["include"], ["model-tiers.toml"])
        self.assertNotIn("api", config)
        self.assertNotIn("suspended_on_start", config)
        self.assertNotIn("[[session]]", text.lower())
        self.assertNotIn("[session]", text.lower())
        self.assertEqual(
            config.get("named_session"),
            [
                {
                    "template": "mayor",
                    "scope": "city",
                    "mode": "always",
                }
            ],
        )

        rigs = config["rigs"]
        self.assertEqual(len(rigs), 2)
        rigs_by_name = {rig["name"]: rig for rig in rigs}
        d2b_rig = rigs_by_name["d2b"]
        self.assertEqual(
            {
                key: d2b_rig[key]
                for key in ("name", "prefix", "default_branch")
            },
            {"name": "d2b", "prefix": "d2b", "default_branch": "v3"},
        )
        self.assertNotIn("path", d2b_rig)
        self.assertEqual(
            d2b_rig["imports"]["gc"],
            {
                "source": GASCITY_ROLES_PACK_SOURCE,
                "version": f"sha:{PACK_COMMIT}",
            },
        )
        self.assertEqual(
            d2b_rig["formula_vars"],
            {
                "base_branch": "v3",
                "target_branch": "v3",
                "open_pr": "true",
                "push": "true",
                "drain_policy": "separate",
            },
        )
        city_source_rig = rigs_by_name["city-source"]
        self.assertEqual(
            {
                key: city_source_rig[key]
                for key in ("name", "prefix", "default_branch")
            },
            {
                "name": "city-source",
                "prefix": "city",
                "default_branch": "main",
            },
        )
        self.assertTrue(city_source_rig["suspended_on_start"])
        self.assertNotIn("path", city_source_rig)
        self.assertEqual(
            city_source_rig["imports"]["gc"],
            {
                "source": GASCITY_ROLES_PACK_SOURCE,
                "version": f"sha:{PACK_COMMIT}",
            },
        )
        self.assertEqual(
            city_source_rig["formula_vars"],
            {
                "base_branch": "main",
                "target_branch": "main",
                "open_pr": "true",
                "push": "true",
                "drain_policy": "separate",
            },
        )

        self.assertEqual(
            set(config["providers"]),
            {
                "deep-thinker",
                "reviewer",
                "solid-worker",
                "fast-worker",
                "codex",
            },
        )
        self.assertEqual(
            config["workspace"],
            {
                "provider": "deep-thinker",
                "global_fragments": [
                    "command-glossary",
                    "operational-awareness",
                    "discord-v0",
                    "d2b-governance",
                ],
            },
        )
        local_global_fragments = {
            "command-glossary": (
                CORE_PACK_ROOT
                / "template-fragments"
                / "command-glossary.template.md"
            ),
            "operational-awareness": (
                CORE_PACK_ROOT
                / "template-fragments"
                / "operational-awareness.template.md"
            ),
            "d2b-governance": (
                CITY_ROOT
                / "template-fragments"
                / "d2b-governance.template.md"
            ),
        }
        for name in config["workspace"]["global_fragments"]:
            if name == "discord-v0":
                continue
            self.assertIn(name, local_global_fragments)
            path = local_global_fragments[name]
            self.assertRegex(
                path.read_text(encoding="utf-8"),
                rf'\{{\{{\s*define\s+"{re.escape(name)}"',
            )
        expected_args = {
            "copilot-deep-sol": [
                "--yolo",
                "--model",
                "gpt-5.6-sol",
                "--context",
                "long_context",
                "--effort",
                "medium",
            ],
            "copilot-review-grok": [
                "--yolo",
                "--model",
                "grok-4.6",
                "--context",
                "long_context",
                "--effort",
                "high",
            ],
            "copilot-solid-luna": [
                "--yolo",
                "--model",
                "gpt-5.6-luna",
                "--context",
                "long_context",
                "--effort",
                "max",
            ],
            "copilot-fast-luna": [
                "--yolo",
                "--model",
                "gpt-5.6-luna",
                "--context",
                "default",
                "--effort",
                "medium",
            ],
        }
        for name, args in expected_args.items():
            provider = core_pack["providers"][name]
            self.assertEqual(provider["base"], "builtin:copilot")
            self.assertEqual(provider["args"], args)
            for key in ("command", "env", "option_defaults"):
                self.assertNotIn(key, provider)
        self.assertEqual(
            {
                name: provider["base"]
                for name, provider in config["providers"].items()
                if name != "codex"
            },
            {
                "deep-thinker": "copilot-deep-sol",
                "reviewer": "copilot-review-grok",
                "solid-worker": "copilot-solid-luna",
                "fast-worker": "copilot-fast-luna",
            },
        )
        codex = config["providers"]["codex"]
        self.assertEqual(codex["base"], "builtin:codex")
        self.assertEqual(codex["ready_delay_ms"], 0)
        self.assertEqual(codex["option_defaults"], {"model": ""})
        for key in ("args", "command", "env"):
            self.assertNotIn(key, codex)
        for marker in (
            "COPILOT_GITHUB_TOKEN",
            "GH_TOKEN",
        ):
            self.assertNotIn(marker, text)

        expected_tiers = {
            "requirements-planner": "deep-thinker",
            "design-author": "deep-thinker",
            "task-decomposer": "deep-thinker",
            "design-implementation-reviewer": "reviewer",
            "design-test-risk-reviewer": "reviewer",
            "implementation-reviewer": "reviewer",
            "gap-analyst": "reviewer",
            "review-synthesizer": "reviewer",
            "issue-triager": "reviewer",
            "implementation-worker": "solid-worker",
            "run-operator": "fast-worker",
            "publisher": "fast-worker",
            "pr-babysitter": "fast-worker",
        }
        patches = model_tiers["patches"]["agent"]
        self.assertEqual(len(patches), len(expected_tiers) * len(rigs))
        for rig_name in ("d2b", "city-source"):
            self.assertEqual(
                {
                    patch["name"]: patch["provider"]
                    for patch in patches
                    if patch["dir"] == rig_name
                },
                expected_tiers,
            )
        self.assertEqual(
            {patch["dir"] for patch in patches},
            {"d2b", "city-source"},
        )
        for marker in (
            "secret",
            "token",
            "guild",
            "channel",
            "role-allowlist",
            "mapping",
            "service",
            "relay",
        ):
            self.assertNotIn(marker, text.lower())
        self.assertIn("/gascity/roles", text)
        self.assertNotRegex(text.lower(), r"role[-_]id")
        self.assertEqual(
            config["daemon"],
            {
                "patrol_interval": "30s",
                "max_restarts": 5,
                "restart_window": "1h",
                "shutdown_timeout": "5s",
                "formula_v2": True,
            },
        )

    def test_model_tier_projection_is_deterministic(self) -> None:
        generator = (
            CORE_PACK_ROOT / "commands" / "gen-model-tiers" / "run.sh"
        )

        def generate(
            city: pathlib.Path,
            base: pathlib.Path | None = None,
        ) -> subprocess.CompletedProcess[str]:
            env = os.environ.copy()
            if base is not None:
                env["MODEL_TIERS_BASE"] = str(base)
            return subprocess.run(
                [str(generator), str(city)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        result = generate(CITY_ROOT / "city.toml")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            (CITY_ROOT / "model-tiers.toml").read_text(encoding="utf-8"),
        )

        with tempfile.TemporaryDirectory() as raw_root:
            temporary = pathlib.Path(raw_root)
            invalid_base = temporary / "invalid-base.toml"
            invalid_base.write_text(
                '[tiers]\nimplementation-worker = "unknown-tier"\n',
                encoding="utf-8",
            )
            invalid = generate(CITY_ROOT / "city.toml", invalid_base)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("unknown tier", invalid.stderr)

            empty_base = temporary / "empty-base.toml"
            empty_base.write_text("[tiers]\n", encoding="utf-8")
            empty = generate(CITY_ROOT / "city.toml", empty_base)
            self.assertNotEqual(empty.returncode, 0)
            self.assertIn("no valid role assignments", empty.stderr)

            no_rigs = temporary / "no-rigs.toml"
            no_rigs.write_text(
                '[workspace]\nprovider = "deep-thinker"\n',
                encoding="utf-8",
            )
            missing_rigs = generate(no_rigs)
            self.assertNotEqual(missing_rigs.returncode, 0)
            self.assertIn("no rigs found", missing_rigs.stderr)

            invalid_rig = temporary / "invalid-rig.toml"
            invalid_rig.write_text(
                '[[rigs]]\nname = "invalid rig"\n',
                encoding="utf-8",
            )
            invalid_name = generate(invalid_rig)
            self.assertNotEqual(invalid_name.returncode, 0)
            self.assertIn("invalid rig name", invalid_name.stderr)

            empty_rig = temporary / "empty-rig.toml"
            empty_rig.write_text(
                '[[rigs]]\nname = ""\n',
                encoding="utf-8",
            )
            empty_name = generate(empty_rig)
            self.assertNotEqual(empty_name.returncode, 0)
            self.assertIn("invalid rig name: empty", empty_name.stderr)

            multi_rig = temporary / "multi-rig.toml"
            multi_rig.write_text(
                '[[rigs]]\nname = "alpha"\n\n[[rigs]]\nname = "beta"\n',
                encoding="utf-8",
            )
            multiple = generate(multi_rig)
            self.assertEqual(multiple.returncode, 0, multiple.stderr)
            patches = tomllib.loads(multiple.stdout)["patches"]["agent"]
            self.assertEqual(len(patches), 26)
            self.assertEqual({patch["dir"] for patch in patches}, {"alpha", "beta"})

            missing_city = generate(temporary / "missing-city.toml")
            self.assertNotEqual(missing_city.returncode, 0)
            self.assertIn("city file not found", missing_city.stderr)

            missing_base = generate(
                CITY_ROOT / "city.toml",
                temporary / "missing-base.toml",
            )
            self.assertNotEqual(missing_base.returncode, 0)
            self.assertIn("base map not found", missing_base.stderr)

    def test_mayor_is_single_native_coordinator(self) -> None:
        agent = tomllib.loads(
            (
                CITY_ROOT / "agents" / "mayor" / "agent.toml"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(agent["provider"], "deep-thinker")
        self.assertEqual(agent["scope"], "city")
        self.assertEqual(agent["wake_mode"], "fresh")
        self.assertEqual(agent["max_active_sessions"], 1)
        self.assertEqual(agent["work_dir"], ".gc/agents/mayor")
        self.assertEqual(
            agent["append_fragments"],
            [
                "mayor-operating-rhythm",
                "efficient-routing-rules",
                "sdlc-mayor-coding-rules",
            ],
        )

        text = (
            CITY_ROOT / "agents" / "mayor" / "prompt.template.md"
        ).read_text(
            encoding="utf-8",
        )
        fragments = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                CORE_PACK_ROOT
                / "template-fragments"
            ).glob("*.template.md")
        )
        policy = (text + "\n" + fragments).lower()
        for marker in (
            "gc.mayor",
            "do not implement",
            "official gas city roles and formulas",
            "never merge",
            "force-push",
            "default state is idle",
        ):
            self.assertIn(marker, policy)
        for marker in (
            "claude",
            "feature-workflow",
            "gc.routed_to",
            "gc agent add",
            "hourly",
        ):
            self.assertNotIn(marker, policy)

    def test_city_has_no_obsolete_routing_or_delivery_verification(self) -> None:
        text = "\n".join(
            (CITY_ROOT / relative).read_text(encoding="utf-8")
            for relative in ("city.toml", "pack.toml")
        ).lower()
        for marker in (
            "api",
            "acp",
            "deployment-verification",
            "delivery-verification",
        ):
            self.assertNotIn(marker, text)
        self.assertNotIn("[[session]]", text)
        self.assertNotIn("[session]", text)

    def test_pack_pins_canonical_sources_and_uses_imported_services(
        self,
    ) -> None:
        pack = tomllib.loads(
            (CITY_ROOT / "pack.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(pack["pack"]["schema"], 2)
        self.assertEqual(
            {
                name: import_config["version"]
                for name, import_config in pack["imports"].items()
                if "version" in import_config
            },
            {
                "core": f"sha:{GASCITY_COMMIT}",
                "bd": f"sha:{GASCITY_COMMIT}",
                "gc": f"sha:{PACK_COMMIT}",
                "discord": f"sha:{PACK_COMMIT}",
            },
        )
        self.assertEqual(
            pack["imports"]["core-city"],
            {"source": "../../packs/core-city"},
        )
        self.assertEqual(
            {
                name: import_config["source"]
                for name, import_config in pack["imports"].items()
            },
            {
                "core": (
                    "https://github.com/gastownhall/"
                    "gascity.git//internal/bootstrap/packs/core"
                ),
                "bd": (
                    "https://github.com/gastownhall/"
                    "gascity.git//examples/bd"
                ),
                "core-city": "../../packs/core-city",
                "gc": GASCITY_PACK_SOURCE,
                "discord": DISCORD_PACK_SOURCE,
            },
        )
        self.assertEqual(
            pack["imports"]["gc"],
            {"source": GASCITY_PACK_SOURCE, "version": f"sha:{PACK_COMMIT}"},
        )
        self.assertEqual(
            pack["imports"]["discord"],
            {"source": DISCORD_PACK_SOURCE, "version": f"sha:{PACK_COMMIT}"},
        )

        for key in ("service", "services", "relay", "mappings"):
            self.assertNotIn(key, pack)
        for relative in (
            "services",
            "relay",
            "discord",
            "discord-interactions",
            "discord-admin",
            "discord-gateway",
            "gc-discord-adapter",
            "gc-discord-cli",
        ):
            self.assertFalse((CITY_ROOT / relative).exists(), relative)

    def test_lock_pins_exact_sources(self) -> None:
        lock_path = CITY_ROOT / "packs.lock"
        lock_text = lock_path.read_text(encoding="utf-8")
        lock = tomllib.loads(lock_text)
        expected = {
            GASCITY_PACK_SOURCE: PACK_COMMIT,
            GASCITY_ROLES_PACK_SOURCE: PACK_COMMIT,
            DISCORD_PACK_SOURCE: PACK_COMMIT,
            (
                "https://github.com/gastownhall/"
                "gascity.git//examples/bd"
            ): GASCITY_COMMIT,
            (
                "https://github.com/gastownhall/"
                "gascity.git//internal/bootstrap/packs/core"
            ): GASCITY_COMMIT,
        }
        self.assertEqual(set(lock["packs"]), set(expected))
        self.assertNotIn("file://", lock_text)
        self.assertNotIn(str(ROOT), lock_text)
        self.assertNotIn("../../packs/core-city", lock_text)
        for source, commit in expected.items():
            self.assertEqual(lock["packs"][source]["version"], f"sha:{commit}")
            self.assertEqual(lock["packs"][source]["commit"], commit)

    def test_local_formula_extensions_and_governance_fragment(self) -> None:
        formula_path = (
            CITY_ROOT / "formulas" / "mol-d2b-discord-fix-issue.toml"
        )
        formula = tomllib.loads(formula_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(formula),
            {"formula", "extends", "steps"},
        )
        self.assertEqual(formula["formula"], "mol-d2b-discord-fix-issue")
        self.assertEqual(formula["extends"], ["mol-discord-fix-issue"])
        self.assertEqual(len(formula["steps"]), 1)
        step = formula["steps"][0]
        self.assertEqual(step["id"], "workspace-setup")
        self.assertEqual(step["needs"], ["load-context"])
        description = step["description"]
        for marker in (
            "if ! git fetch --prune origin '+refs/heads/*:refs/remotes/origin/*'; then",
            "git fetch --prune origin '+refs/heads/*:refs/remotes/origin/*'",
            'git show-ref --verify --quiet "refs/remotes/origin/v3"',
            "metadata.work_dir",
            "metadata.branch",
            "metadata.base_ref",
            "metadata.fork_sha",
            "RECORDED_WORKTREE",
            "RECORDED_BRANCH",
            'if [ "$BASE_REF" != "origin/v3" ] || [ -z "$FORK_SHA" ]',
            "legacy or missing extension metadata",
            "Recovery:",
            'git show-ref --verify --quiet "refs/heads/$BRANCH"',
            'git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"',
            'if [ -n "$RECORDED_WORKTREE" ] && [ -d "$RECORDED_WORKTREE" ]',
            'if [ -e "$WORKTREE_PATH" ] || [ -L "$WORKTREE_PATH" ]',
            'git worktree add "$WORKTREE_PATH" "$BRANCH"',
            'git worktree add --track -b "$BRANCH" "$WORKTREE_PATH" "origin/$BRANCH"',
            'git worktree add "$WORKTREE_PATH" --detach origin/v3',
            'gc bd update {{issue}} --set-metadata work_dir="$WORKTREE"',
            "WORKTREE_RECREATED=1",
            "git branch --show-current",
            "recreated worktree is on",
            'git checkout --track -b "$BRANCH" "origin/$BRANCH"',
            "no local or origin branch exists",
            'git status --porcelain',
            'git cat-file -e "$FORK_SHA^{commit}"',
            'git merge-base --is-ancestor "$FORK_SHA" HEAD',
            'git merge-base --is-ancestor "$FORK_SHA" origin/v3',
            "not a commit in this repository",
            "not an ancestor of the recorded branch HEAD",
            "not an ancestor of current origin/v3",
            "establish a verified prior origin/v3 base",
            "git rebase --rebase-merges --reapply-cherry-picks --empty=stop origin/v3",
            "git merge-base --is-ancestor origin/v3 HEAD",
            "--set-metadata base_ref=origin/v3",
            "--set-metadata fork_sha=",
            "Prior work remains intact",
        ):
            self.assertIn(marker, description)
        self.assertNotIn(
            "recorded worktree does not exist",
            description,
        )
        self.assertLess(
            description.index('if [ "$BASE_REF" != "origin/v3" ]'),
            description.index("WORKTREE_RECREATED=0"),
        )
        collision_index = description.index(
            'if [ -e "$WORKTREE_PATH" ] || [ -L "$WORKTREE_PATH" ]'
        )
        local_worktree_index = description.index(
            'git worktree add "$WORKTREE_PATH" "$BRANCH"'
        )
        remote_worktree_index = description.index(
            'git worktree add --track -b "$BRANCH" "$WORKTREE_PATH" "origin/$BRANCH"'
        )
        detached_worktree_index = description.index(
            'git worktree add "$WORKTREE_PATH" --detach origin/v3'
        )
        for worktree_add_index in (
            local_worktree_index,
            remote_worktree_index,
            detached_worktree_index,
        ):
            self.assertLess(collision_index, worktree_add_index)
        self.assertLess(local_worktree_index, detached_worktree_index)
        self.assertLess(remote_worktree_index, detached_worktree_index)
        worktree_metadata_index = description.index(
            'gc bd update {{issue}} --set-metadata work_dir="$WORKTREE"'
        )
        self.assertLess(
            description.index("WORKTREE_RECREATED=1"),
            worktree_metadata_index,
        )
        self.assertLess(local_worktree_index, worktree_metadata_index)
        self.assertLess(remote_worktree_index, worktree_metadata_index)
        self.assertLess(detached_worktree_index, worktree_metadata_index)
        self.assertLess(
            description.index('git status --porcelain'),
            description.index('git checkout "$BRANCH"'),
        )
        self.assertLess(
            description.index('if [ "$WORKTREE_RECREATED" = "1" ]'),
            description.index('git checkout "$BRANCH"'),
        )
        self.assertLess(
            description.index('git cat-file -e "$FORK_SHA^{commit}"'),
            description.index(
                "git rebase --rebase-merges "
                "--reapply-cherry-picks --empty=stop origin/v3"
            ),
        )
        self.assertLess(
            description.index('git merge-base --is-ancestor "$FORK_SHA" HEAD'),
            description.index(
                "git rebase --rebase-merges "
                "--reapply-cherry-picks --empty=stop origin/v3"
            ),
        )
        self.assertLess(
            description.index(
                'git merge-base --is-ancestor "$FORK_SHA" origin/v3'
            ),
            description.index(
                "git rebase --rebase-merges "
                "--reapply-cherry-picks --empty=stop origin/v3"
            ),
        )
        self.assertLess(
            description.index('git cat-file -e "$FORK_SHA^{commit}"'),
            description.index('git merge-base --is-ancestor "$FORK_SHA" HEAD'),
        )
        self.assertLess(
            description.index('git merge-base --is-ancestor "$FORK_SHA" HEAD'),
            description.index(
                'git merge-base --is-ancestor "$FORK_SHA" origin/v3'
            ),
        )
        rebase_index = description.index(
            "git rebase --rebase-merges "
            "--reapply-cherry-picks --empty=stop origin/v3"
        )
        self.assertLess(
            rebase_index,
            description.index(
                "if ! git merge-base --is-ancestor origin/v3 HEAD;",
                rebase_index,
            ),
        )
        self.assertLess(
            detached_worktree_index,
            description.index('git checkout -b "$BRANCH" origin/v3'),
        )
        recorded_recreate_index = description.index(
            'if [ -n "$RECORDED_BRANCH" ]; then',
            description.index("WORKTREE_RECREATED=0"),
        )
        recorded_recreate_block = description[
            recorded_recreate_index:detached_worktree_index
        ]
        self.assertNotIn(
            'git worktree add "$WORKTREE_PATH" --detach origin/v3',
            recorded_recreate_block,
        )
        self.assertNotIn(
            'git checkout -b "$BRANCH" origin/v3',
            recorded_recreate_block,
        )
        self.assertNotIn("git remote show origin", step["description"])

        fragment = (
            CITY_ROOT
            / "template-fragments"
            / "d2b-governance.template.md"
        ).read_text(encoding="utf-8")
        fragment_policy = " ".join(fragment.lower().split())
        for marker in (
            "build-basic",
            "implement",
            "github-issue-fix",
            "publish",
            "mol-d2b-discord-fix-issue",
            "target=v3",
            "merge_strategy=pr",
            "refuse direct merges",
            "pull-request handoff",
            "never merge",
            "force-push",
            "human-owned",
            "city-source",
            "target=main",
        ):
            self.assertIn(marker, fragment_policy)
        self.assertEqual(
            fragment_policy.count("branch protection"),
            1,
        )

    def test_docs_record_host_inheritance_and_discord_boundaries(
        self,
    ) -> None:
        docs = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                "docs/operations.md",
                "docs/testing.md",
                "README.md",
                "SECURITY.md",
                "AGENTS.md",
                "PROVENANCE.md",
                "CHANGELOG.md",
                "docs/designs/2026-08-28-001-cookbook-layout-and-model-tiers.md",
                "recipes/model-tiers.md",
                "recipes/the-mayor.md",
            )
        )
        docs_flat = " ".join(docs.lower().split())
        for marker in (
            "cities/d2b-gascity",
            "packs/core-city",
            "repository-local d2b checkout",
            "bind mount",
            "gc rig add",
            "private preflight inventory",
            "old root city",
            "unmount",
            "recursive deletion",
            "product-local `.beads/`",
            "agent hooks",
            "gc init --file city.toml --preserve-existing --no-start .",
            "city-source",
            "--start-suspended",
            "separate clone or worktree",
            "never bind",
            "metadata.target=main",
            GASCITY_PACK_SOURCE,
            GASCITY_ROLES_PACK_SOURCE,
            DISCORD_PACK_SOURCE,
            "sha:" + PACK_COMMIT,
            "0600",
            "GC_CITY_NAME",
            "GC_CITY_PATH",
            "GC_API_BASE_URL",
            "command-glossary",
            "operational-awareness",
            "discord-v0",
            "d2b-governance",
            "patrol_interval",
            "formula_v2",
            "discord-interactions",
            "discord-admin",
            "discord-gateway",
            "/v0/discord/interactions",
            "bot",
            "applications.commands",
            "View Channels",
            "Send Messages",
            "Read Message History",
            "Create Public Threads",
            "Send Messages in Threads",
            "Message Content Intent",
            "Administrator",
            "Manage Guild",
            "Manage Roles",
            "Manage Channels",
            "Manage Messages",
            "Manage Webhooks",
            "Attach Files",
            "Add Reactions",
            "Embed Links",
            "Presence Intent",
            "--guild-allowlist",
            "--channel-allowlist",
            "--role-allowlist",
            "named app",
            "independent",
            "mol-d2b-discord-fix-issue",
            "base_ref=origin/v3",
            "fork_sha",
            "--rebase-merges",
            "--reapply-cherry-picks",
            "--empty=stop",
            "PR-only",
            "requires pull requests",
            "apply to administrators",
            "/gc fix",
            "modal",
            "Room/thread bindings",
            "@@handle",
            "ambient-read",
            "peer fanout",
            "bot-authored",
            "explicit publish",
            "plain message",
            "gc.mayor",
            "implementation-worker",
            "run-operator",
            "publisher",
            "requirements-planner",
            "build-basic",
            "implement",
            "github-issue-fix",
            "github-pr-review",
            "publish",
            "Copilot Requests",
            "GH_TOKEN",
            "deep-thinker",
            "reviewer",
            "solid-worker",
            "fast-worker",
            "gpt-5.6-sol",
            "grok-4.6",
            "gpt-5.6-luna",
            "medium",
            "high",
            "max",
            "long_context",
            "default",
            "Luna",
            "builtin:copilot",
            "builtin:codex",
            "thinkjones/gascity-cookbook",
            "MIT",
            "rencire/gascity-flake",
            "no license",
            "no content was copied",
        ):
            self.assertIn(marker, docs)
        self.assertIn(
            "mutually exclusive alternatives for the same room",
            docs_flat,
        )
        self.assertIn(
            "branch protection for `v3` is defense-in-depth",
            docs_flat,
        )
        self.assertIn(
            "only `discord-interactions` is public",
            docs_flat,
        )
        self.assertIn(
            "`discord-admin` must remain tenant/access-policy protected",
            docs_flat,
        )
        self.assertIn(
            "`discord-gateway` remains private",
            docs_flat,
        )
        self.assertIn(
            "official discord pack owns all three native services",
            docs_flat,
        )
        self.assertIn("source-only", docs.lower())
        self.assertIn("credential separation", docs.lower())
        self.assertIn("never implement", docs.lower())
        self.assertIn("never merge", docs.lower())
        self.assertIn("stock `builtin:codex`", docs.lower())
        self.assertNotIn(
            "\n|-- city.toml\n",
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )
        for marker in (
            "s" + "lack",
            "comp" + "ound" + " engineering",
            "copilot-planning-grok",
            "copilot-code-luna",
            "cc.mayor",
        ):
            self.assertNotIn(marker, docs.lower())

    def test_docs_record_enabled_babysitting_and_gate_recovery(
        self,
    ) -> None:
        documents = {
            relative: (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                "README.md",
                "AGENTS.md",
                "CONTRIBUTING.md",
                "PROVENANCE.md",
                "SECURITY.md",
                "CHANGELOG.md",
                "docs/operations.md",
                "docs/testing.md",
                "recipes/the-mayor.md",
                "cities/d2b-gascity/template-fragments/d2b-governance.template.md",
            )
        }
        docs_flat = " ".join("\n".join(documents.values()).lower().split())
        for marker in (
            "rig-imported `pr-babysit` pack",
            "`d2b/pr-babysit.pr-babysitter`",
            "`city-source/pr-babysit.pr-babysitter`",
            "workdir-local",
            ".github/skills/pr-babysit",
            ".agents/skills/pr-babysit",
            "mandatory projection gate",
            "publication-handoff",
            "verify-handoff",
            "check-credentials",
            "deterministic",
            "one durable watch record",
            "watching",
            "waiting",
            "repairing",
            "merge-ready",
            "blocked",
            "exhausted",
            "terminal",
            "claim -> act -> confirm",
            "result-recorded",
            "--blocks <watch-id>",
            "pr-babysit-sweep",
            "cooldown",
            "1m",
            "mol-pr-babysit-repair",
            "formula v2",
            "d2b",
            "`v3`",
            "city-source",
            "`main`",
            "update-branch",
            "pull requests read only",
            "contents write",
            "operator-attested",
            "cannot introspect fine-grained permissions",
            "ci repairs get three",
            "review repairs get two",
            "eight active hours",
            "three-day",
            "ambiguous push",
            "rearm=true",
            "target-only",
            "metadata.target=v3",
            "metadata.merge_strategy=pr",
            "target=<rig>/pr-babysit.pr-babysitter",
            "handoff_target",
            "base_ref=v3",
            "base_ref=main",
            "pr_babysit_validator",
            "credential-isolated-v1",
            "absolute, non-symlink, executable",
            "credential- and network-isolated",
            "missing validator blocks repair",
            "same-repository-only",
            "fork or cross-repository prs are human blockers",
            "no live u8 acceptance is claimed",
            "human-owned",
            "human merge",
        ):
            self.assertIn(marker, docs_flat, marker)
        for marker in (
            "current status: blocked",
            "official pack v2 export",
            "compatible gas city core revision",
            "not imported; do not invoke",
            "not scheduled by the pinned gas city core",
            "no local watcher",
            "blocked upstream request",
        ):
            self.assertNotIn(marker, docs_flat, marker)

    def test_review_docs_and_report_use_ascii_text(self) -> None:
        paths = [
            ROOT / relative
            for relative in (
                "README.md",
                "AGENTS.md",
                "CONTRIBUTING.md",
                "PROVENANCE.md",
                "SECURITY.md",
                "CHANGELOG.md",
                "docs/operations.md",
                "docs/testing.md",
                "recipes/the-mayor.md",
                "cities/d2b-gascity/template-fragments/d2b-governance.template.md",
                "docs/plans/2026-08-29-1000-feat-vendored-pr-babysitting-plan.md",
                "packs/pr-babysit/skills/pr-babysit/references/report.md",
            )
        ]
        for path in paths:
            self.assertTrue(
                path.read_text(encoding="utf-8").isascii(),
                str(path.relative_to(ROOT)),
            )

    def test_u7_pack_docs_and_governance_preserve_target_only_privacy(
        self,
    ) -> None:
        documents = [
            ROOT / relative
            for relative in (
                "README.md",
                "AGENTS.md",
                "CONTRIBUTING.md",
                "PROVENANCE.md",
                "SECURITY.md",
                "CHANGELOG.md",
                "docs/operations.md",
                "docs/testing.md",
                "recipes/the-mayor.md",
                "cities/d2b-gascity/template-fragments/d2b-governance.template.md",
            )
        ]
        pack_files = [
            PR_BABYSIT_ROOT / relative
            for relative in PR_BABYSIT_AUTHORED_FILES
            if relative not in {"LICENSE", "UPSTREAM.json"}
        ]
        docs_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in documents
        )
        pack_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in pack_files
        )
        text = docs_text + "\n" + pack_text
        lowered = text.lower()
        pack_lowered = pack_text.lower()
        for marker in (
            "copilot requests",
            "d2b publication",
            "discord app credentials",
            "contents write",
            "pull requests read",
            "pull requests write",
            "merge/admin",
            "workflow-approval",
            "operator-attested",
            "fine-grained permissions",
            "gh_token",
            "github_token",
            "must not reuse",
            "suspended-on-start",
            "u8",
        ):
            self.assertIn(marker, lowered, marker)
        for marker in (
            "[[service]]",
            "[[services]]",
            "webhook handler",
            "custom provider adapter",
            "gh pr merge",
            "git merge --",
            "git rebase --",
            "--force-with-lease",
        ):
            self.assertNotIn(marker, pack_lowered, marker)
        self.assertFalse((PR_BABYSIT_ROOT / "services").exists())
        self.assertFalse((PR_BABYSIT_ROOT / "relay").exists())
        self.assertFalse((PR_BABYSIT_ROOT / "daemon").exists())

        governance = (
            ROOT
            / "cities"
            / "d2b-gascity"
            / "template-fragments"
            / "d2b-governance.template.md"
        ).read_text(encoding="utf-8")
        governance = " ".join(governance.lower().split())
        for marker in (
            "pr-babysitter",
            "mol-pr-babysit-repair",
            "target-only",
            "never merge",
            "never force-push",
            "pull-request handoff",
            "human-owned",
        ):
            self.assertIn(marker, governance, marker)

    def test_u7_documentation_has_no_forbidden_private_values(self) -> None:
        documents = [
            ROOT / relative
            for relative in (
                "README.md",
                "AGENTS.md",
                "CONTRIBUTING.md",
                "PROVENANCE.md",
                "SECURITY.md",
                "CHANGELOG.md",
                "docs/operations.md",
                "docs/testing.md",
                "recipes/the-mayor.md",
                "cities/d2b-gascity/template-fragments/d2b-governance.template.md",
            )
        ]
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in documents
        )
        self.assertNotRegex(text, r"/(?:home|Users|private|var)/")
        for address in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text):
            self.assertEqual(address, "127.0.0.1")

    def test_discord_and_gascity_pack_are_enabled_and_pinned(self) -> None:
        pack = tomllib.loads(
            (CITY_ROOT / "pack.toml").read_text(encoding="utf-8")
        )
        lock = tomllib.loads(
            (CITY_ROOT / "packs.lock").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(pack["imports"]),
            {"core", "bd", "core-city", "gc", "discord"},
        )
        self.assertEqual(
            pack["imports"]["discord"],
            {"source": DISCORD_PACK_SOURCE, "version": f"sha:{PACK_COMMIT}"},
        )
        self.assertEqual(
            lock["packs"][DISCORD_PACK_SOURCE]["commit"],
            PACK_COMMIT,
        )
        self.assertEqual(
            lock["packs"][GASCITY_PACK_SOURCE]["commit"],
            PACK_COMMIT,
        )
        self.assertEqual(
            lock["packs"][GASCITY_ROLES_PACK_SOURCE]["commit"],
            PACK_COMMIT,
        )
        for obsolete in (
            "gastown",
            "s" + "lack" + "-full",
            "comp" + "ound" + "-engineering",
        ):
            self.assertNotIn(obsolete, pack["imports"])
        for obsolete_source in (
            "https://github.com/gastownhall/gascity-packs/tree/main/"
            + "gas"
            + "town",
            "https://github.com/gastownhall/gascity-packs/tree/main/"
            + "s"
            + "lack-full",
            "https://github.com/gastownhall/gascity-packs/tree/main/"
            + "comp"
            + "ound-engineering",
        ):
            self.assertNotIn(obsolete_source, lock["packs"])

    def test_obsolete_local_integrations_are_deleted(self) -> None:
        for relative in (
            "template-fragments/"
            + "s"
            + "lack-progress.template.md",
            "assets/workflows/do-work/prepare-worktree.md",
            "assets/workflows/build-base/publish.md",
        ):
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_authored_city_files_have_only_generic_source_values(self) -> None:
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in _tracked_text_files()
        )
        for marker in (
            "/" + "home/",
            "/" + "Users/",
            "/" + "private/",
            "/" + "var/",
        ):
            self.assertNotIn(marker, text)
        self.assertNotRegex(text, r"\$2[aby]\$\d{2}\$")
        for address in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text):
            self.assertEqual(address, "127.0.0.1")

    def test_gitignore_covers_native_runtime_state(self) -> None:
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for marker in (".gc/", ".beads/", ".dolt/", ".runtime/", ".state/", "run/"):
            self.assertIn(marker, text)

    def test_ci_downloads_and_verifies_the_pinned_gascity_binary(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "check.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "gascity_1.4.1_linux_amd64.tar.gz",
            workflow,
        )
        self.assertIn(
            "https://github.com/gastownhall/gascity/releases/download/"
            "v1.4.1/gascity_1.4.1_linux_amd64.tar.gz",
            workflow,
        )
        self.assertIn(GASCITY_ARCHIVE_SHA256, workflow)
        self.assertIn(
            f"beads_{BEADS_VERSION}_linux_amd64.tar.gz",
            workflow,
        )
        self.assertIn(BEADS_ARCHIVE_SHA256, workflow)
        self.assertIn(
            f"dolt/releases/download/v{DOLT_VERSION}/dolt-linux-amd64.tar.gz",
            workflow,
        )
        self.assertIn(DOLT_ARCHIVE_SHA256, workflow)
        self.assertRegex(workflow, r"sha256sum\s+--check")
        self.assertIn("RUNNER_TEMP", workflow)
        self.assertIn("tar", workflow)
        self.assertIn("GC_BIN=", workflow)
        self.assertIn("python3 tests/test_city.py", workflow)
        self.assertNotIn("nix", workflow.lower())

    def test_native_init_and_rig_binding_stay_out_of_the_source_tree(self) -> None:
        gc_bin = os.environ.get("GC_BIN")
        if not gc_bin:
            self.skipTest("GC_BIN is not set; static checks remain runnable")
        if not os.path.isabs(gc_bin):
            gc_bin = shutil.which(gc_bin) or str((ROOT / gc_bin).resolve())
        bd_bin = shutil.which("bd")
        self.assertIsNotNone(
            bd_bin,
            "native smoke requires Beads v1.2.2",
        )
        bd_version = subprocess.run(
            [bd_bin, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(bd_version.returncode, 0, bd_version.stderr)
        self.assertRegex(
            bd_version.stdout,
            rf"^bd version {re.escape(BEADS_VERSION)} \(",
        )

        before = {
            relative: (ROOT / relative).read_bytes()
            for relative in AUTHORED_FILES
        }
        source_runtime_before = {
            relative: _path_metadata(ROOT / relative)
            for relative in RUNTIME_PATHS
        }
        self.assertFalse(
            _tracked_runtime_state(),
            "tracked or staged runtime state is present",
        )

        SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="native-city-",
            dir=SCRATCH_ROOT,
        ) as raw_root:
            root = pathlib.Path(raw_root)
            try:
                source = root / "source"
                city = source / CITY_RELATIVE
                city_source = root / "city-source"
                rig = root / "rig"
                home = root / "home"
                gc_home = root / "gc-home"
                git_config = root / "git-config"
                tool_bin = root / "tools"
                city.mkdir(parents=True)
                city_source.mkdir()
                rig.mkdir()
                home.mkdir()
                gc_home.mkdir()
                tool_bin.mkdir()

                for relative in AUTHORED_FILES:
                    destination = source / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / relative, destination)
                shutil.copytree(
                    PR_BABYSIT_ROOT,
                    source / "packs" / "pr-babysit",
                )
                city_before = {
                    relative: (source / relative).read_bytes()
                    for relative in AUTHORED_FILES
                }
                pr_babysit_before = {
                    str(path.relative_to(PR_BABYSIT_ROOT)): path.read_bytes()
                    for path in PR_BABYSIT_ROOT.rglob("*")
                    if path.is_file()
                }

                env = {
                    key: value
                    for key, value in os.environ.items()
                    if not key.startswith(("GC_", "BEADS_", "DOLT_"))
                }
                env.update(
                    {
                        "HOME": str(home),
                        "GC_HOME": str(gc_home),
                        "XDG_CACHE_HOME": str(home / ".cache"),
                        "XDG_CONFIG_HOME": str(home / ".config"),
                        "XDG_STATE_HOME": str(home / ".local" / "state"),
                        "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_CONFIG_GLOBAL": str(git_config),
                        "GIT_AUTHOR_NAME": "Gas City Test",
                        "GIT_AUTHOR_EMAIL": "gas-city-test@example.invalid",
                        "GIT_COMMITTER_NAME": "Gas City Test",
                        "GIT_COMMITTER_EMAIL": "gas-city-test@example.invalid",
                    }
                )
                env["GC_BIN"] = gc_bin
                _git(["init", "--quiet", "-b", "main"], cwd=source, env=env)
                _git(
                    ["init", "--quiet", "-b", "main"],
                    cwd=city_source,
                    env=env,
                )
                _git(["init", "--quiet", "-b", "v3"], cwd=rig, env=env)
                for repository in (source, city_source, rig):
                    _git(
                        [
                            "config",
                            "user.name",
                            "Gas City Test",
                        ],
                        cwd=repository,
                        env=env,
                    )
                    _git(
                        [
                            "config",
                            "user.email",
                            "gas-city-test@example.invalid",
                        ],
                        cwd=repository,
                        env=env,
                    )

                dolt_config = home / ".dolt" / "config_global.json"
                dolt_config.parent.mkdir(parents=True, exist_ok=True)
                dolt_config.write_text(
                    json.dumps(
                        {
                            "user.name": "Gas City Test",
                            "user.email": "gas-city-test@example.invalid",
                        }
                    ),
                    encoding="utf-8",
                )

                true = shutil.which("true")
                self.assertIsNotNone(true)
                (tool_bin / "copilot").symlink_to(true)
                (tool_bin / "codex").symlink_to(true)
                env["PATH"] = os.pathsep.join(
                    (str(tool_bin), env.get("PATH", ""))
                )

                def run_gc(*args: str) -> subprocess.CompletedProcess[str]:
                    try:
                        result = subprocess.run(
                            [gc_bin, *args],
                            cwd=city,
                            env=env,
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                    except OSError as error:
                        self.fail(f"GC_BIN could not execute: {error}")
                    if result.returncode:
                        detail = (result.stderr or result.stdout).strip()
                        self.fail(
                            f"gc {' '.join(args)} failed with "
                            f"{result.returncode}: {detail}"
                        )
                    return result

                version = run_gc("version", "--json")
                self.assertEqual(
                    json.loads(version.stdout)["version"],
                    GASCITY_VERSION,
                )
                run_gc(
                    "init",
                    "--file",
                    "city.toml",
                    "--preserve-existing",
                    "--no-start",
                    "--skip-provider-readiness",
                    ".",
                )
                for relative, contents in city_before.items():
                    self.assertEqual(
                        (source / relative).read_bytes(),
                        contents,
                    )
                for relative, contents in pr_babysit_before.items():
                    self.assertEqual(
                        (source / "packs" / "pr-babysit" / relative).read_bytes(),
                        contents,
                    )
                config_show = run_gc(
                    "config",
                    "show",
                    "--city",
                    str(city),
                    "--json",
                )
                config_payload = json.loads(config_show.stdout)
                agent_rows = config_payload["config"]["Agents"]
                self.assertEqual(
                    {
                        (
                            row["Dir"],
                            row["Name"],
                            row["Provider"],
                            row["WorkDir"],
                            row["SessionSetupScript"],
                            row["WakeMode"],
                            row["MaxActiveSessions"],
                        )
                        for row in agent_rows
                        if row["Name"] == "pr-babysitter"
                    },
                    {
                        (
                            "d2b",
                            "pr-babysitter",
                            "fast-worker",
                            "{{.RigRoot}}/.gc/agents/pr-babysitter",
                            "assets/scripts/project-copilot-skill.sh",
                            "fresh",
                            1,
                        ),
                        (
                            "city-source",
                            "pr-babysitter",
                            "fast-worker",
                            "{{.RigRoot}}/.gc/agents/pr-babysitter",
                            "assets/scripts/project-copilot-skill.sh",
                            "fresh",
                            1,
                        ),
                    },
                )
                for rig_name in ("d2b", "city-source"):
                    config_explain = run_gc(
                        "config",
                        "explain",
                        "--rig",
                        rig_name,
                        "--agent",
                        "pr-babysitter",
                    )
                    self.assertIn(
                        f"Agent: {rig_name}/pr-babysit.pr-babysitter",
                        config_explain.stdout,
                    )
                    skill_list = run_gc(
                        "skill",
                        "list",
                        "--agent",
                        f"{rig_name}/pr-babysit.pr-babysitter",
                        "--city",
                        str(city),
                        "--rig",
                        rig_name,
                        "--json",
                    )
                    skill_payload = json.loads(skill_list.stdout)
                    self.assertIn(
                        "pr-babysit.pr-babysit",
                        {
                            entry["name"]
                            for entry in skill_payload["entries"]
                        },
                    )
                run_gc("import", "check", "--city", str(city))
                generated_tiers = run_gc(
                    "core-city",
                    "gen-model-tiers",
                    "city.toml",
                )
                self.assertEqual(
                    generated_tiers.stdout,
                    (city / "model-tiers.toml").read_text(encoding="utf-8"),
                )

                publish_help = run_gc(
                    "discord",
                    "publish",
                    "--help",
                ).stdout
                self.assertIn("--binding", publish_help)
                self.assertIn("--binding room:", publish_help)

                bind_room_help = run_gc(
                    "discord",
                    "bind-room",
                    "--help",
                ).stdout
                for marker in (
                    "--enable-ambient-read",
                    "--allow-untargeted-ambient-delivery",
                    "--enable-peer-fanout",
                    "--allow-untargeted-peer-fanout",
                ):
                    self.assertIn(marker, bind_room_help)

                release_workflow_help = run_gc(
                    "discord",
                    "release-workflow",
                    "--help",
                ).stdout
                self.assertIn("--request-id <id>", release_workflow_help)

                post_message_help = run_gc(
                    "discord",
                    "post-message",
                    "--help",
                ).stdout
                for marker in (
                    "--channel-id <id>",
                    "--thread-id <id>",
                ):
                    self.assertIn(marker, post_message_help)

                site = city / ".gc" / "site.toml"
                site.write_text(
                    site.read_text(encoding="utf-8")
                    + "\n[[rig]]\n"
                    + 'name = "city-source"\n'
                    + f'path = "{city_source}"\n',
                    encoding="utf-8",
                )
                run_gc(
                    "rig",
                    "add",
                    str(rig),
                    "--name",
                    "d2b",
                    "--city",
                    str(city),
                )
                run_gc(
                    "rig",
                    "add",
                    str(city_source),
                    "--name",
                    "city-source",
                    "--prefix",
                    "ct" + re.sub(r"[^a-z0-9]", "", root.name.lower())[-8:],
                    "--start-suspended",
                    "--city",
                    str(city),
                )
                rig_beads = rig / ".beads"
                if not (rig_beads / "config.yaml").is_file():
                    rig_beads.mkdir(parents=True, exist_ok=True)
                    (rig_beads / "config.yaml").write_text(
                        "dolt.local-only: true\n",
                        encoding="utf-8",
                    )
                beads_initialized = subprocess.run(
                    [
                        bd_bin,
                        "init",
                        "--init-if-missing",
                        "--non-interactive",
                        "--skip-hooks",
                        "--skip-agents",
                        "--prefix",
                        "d2b",
                    ],
                    cwd=rig,
                    env=env | {"CI": "1"},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    beads_initialized.returncode,
                    0,
                    beads_initialized.stderr,
                )
                native_watch_id = "d2b-native-smoke-watch"
                native_watch_metadata = {
                    "record_kind": "watch",
                    "state": "watching",
                    "generation": "1",
                    "head_sha": "a" * 40,
                }
                native_watch = subprocess.run(
                    [
                        bd_bin,
                        "create",
                        "--id",
                        native_watch_id,
                        "--title",
                        "native smoke watch",
                        "--description",
                        "credential-free native command smoke",
                        "--type",
                        "task",
                        "--metadata",
                        json.dumps(native_watch_metadata),
                        "--silent",
                        "--json",
                    ],
                    cwd=rig,
                    env=env | {"CI": "1"},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(native_watch.returncode, 0, native_watch.stderr)
                (city / "city.toml").write_bytes(
                    city_before[str(CITY_RELATIVE / "city.toml")]
                )
                run_gc("config", "show", "--city", str(city))

                original_city_toml = (city / "city.toml").read_bytes()
                city_text = original_city_toml.decode("utf-8")
                # Gas City v1.4.1 exposes Pack CLI commands from city imports;
                # keep the production rig imports intact while exercising the
                # local command against the temporary rig store.
                city_text = city_text.replace(
                    "\n[[rigs]]",
                    "\n\n[imports.pr-babysit]\n"
                    'source = "../../packs/pr-babysit"\n'
                    "transitive = false\n\n[[rigs]]",
                    1,
                )
                (city / "city.toml").write_text(
                    city_text,
                    encoding="utf-8",
                )
                env["GC_RIG_ROOT"] = str(rig)
                env["PR_BABYSIT_BEADS_BIN"] = bd_bin
                try:
                    native_show = run_gc(
                        "pr-babysit",
                        "pr-babysit",
                        "show",
                        "--rig",
                        "d2b",
                        "--watch-id",
                        native_watch_id,
                        "--json",
                    )
                    native_show_payload = json.loads(native_show.stdout)
                    self.assertTrue(native_show_payload["ok"])
                    self.assertEqual(native_show_payload["action"], "show")
                    self.assertEqual(
                        native_show_payload["watch_id"],
                        native_watch_id,
                    )
                    self.assertEqual(
                        native_show_payload["metadata"]["record_kind"],
                        "watch",
                    )
                    self.assertEqual(
                        native_show_payload["metadata"]["state"],
                        "watching",
                    )
                finally:
                    (city / "city.toml").write_bytes(original_city_toml)

                def show_formula(name: str, *extra: str) -> dict:
                    result = run_gc(
                        "formula",
                        "show",
                        name,
                        "--city",
                        str(city),
                        *extra,
                        "--json",
                    )
                    self.assertEqual(result.stderr, "")
                    payload = json.loads(result.stdout)
                    self.assertTrue(payload["ok"])
                    self.assertEqual(payload.get("warnings", []), [])
                    return payload

                def step_with_suffix(
                    formula: dict,
                    suffix: str,
                ) -> tuple[int, dict]:
                    matches = [
                        (index, step)
                        for index, step in enumerate(formula["steps"])
                        if step["id"].rsplit(".", 1)[-1] == suffix
                    ]
                    self.assertEqual(len(matches), 1, suffix)
                    return matches[0]

                for rig_name in ("d2b", "city-source"):
                    formula = show_formula(
                        "mol-pr-babysit-repair",
                        "--rig",
                        rig_name,
                    )
                    self.assertTrue(
                        {
                            "prepare-worktree",
                            "repair",
                            "review",
                            "validate-and-report",
                            "close-action",
                        }
                        <= {
                            step["id"].rsplit(".", 1)[-1]
                            for step in formula["steps"]
                        }
                    )
                    self.assertEqual(
                        {
                            (dep["step_id"], dep["depends_on_id"])
                            for dep in formula["deps"]
                            if dep["step_id"].startswith(
                                "mol-pr-babysit-repair."
                            )
                            and dep["depends_on_id"].startswith(
                                "mol-pr-babysit-repair."
                            )
                        },
                        {
                            (
                                "mol-pr-babysit-repair.repair",
                                "mol-pr-babysit-repair.prepare-worktree",
                            ),
                            (
                                "mol-pr-babysit-repair.review",
                                "mol-pr-babysit-repair.repair",
                            ),
                            (
                                "mol-pr-babysit-repair.validate-and-report",
                                "mol-pr-babysit-repair.repair",
                            ),
                            (
                                "mol-pr-babysit-repair.validate-and-report",
                                "mol-pr-babysit-repair.review",
                            ),
                            (
                                "mol-pr-babysit-repair.close-action",
                                "mol-pr-babysit-repair.validate-and-report",
                            ),
                            (
                                "mol-pr-babysit-repair.workflow-finalize",
                                "mol-pr-babysit-repair.close-action",
                            ),
                        },
                    )
                    order_result = run_gc(
                        "order",
                        "show",
                        "pr-babysit-sweep",
                        "--rig",
                        rig_name,
                        "--json",
                    )
                    order_payload = json.loads(order_result.stdout)
                    order_text = json.dumps(order_payload, sort_keys=True)
                    self.assertIn("cooldown", order_text)
                    self.assertIn('"1m"', order_text)
                    self.assertIn(
                        "$PACK_DIR/assets/scripts/pr-babysit-sweep.sh",
                        order_text,
                    )

                d2b_formula = show_formula("mol-d2b-discord-fix-issue")
                d2b_steps = {
                    step["id"].rsplit(".", 1)[-1]
                    for step in d2b_formula["steps"]
                }
                self.assertTrue(
                    {
                        "load-context",
                        "workspace-setup",
                        "understand-bug",
                        "write-tests-first",
                        "implement-fix",
                        "wrap-up",
                    }
                    <= d2b_steps
                )
                _, d2b_workspace = step_with_suffix(
                    d2b_formula,
                    "workspace-setup",
                )
                d2b_workspace_text = d2b_workspace["description"]
                for marker in (
                    "if ! git fetch --prune origin '+refs/heads/*:refs/remotes/origin/*'; then",
                    "origin/v3",
                    "base_ref=origin/v3",
                    "fork_sha",
                    "RECORDED_WORKTREE",
                    "RECORDED_BRANCH",
                    "legacy or missing extension metadata",
                    "Recovery:",
                    'if [ -n "$RECORDED_WORKTREE" ] && [ -d "$RECORDED_WORKTREE" ]',
                    'git worktree add "$WORKTREE_PATH" "$BRANCH"',
                    'git worktree add --track -b "$BRANCH" "$WORKTREE_PATH" "origin/$BRANCH"',
                    'git worktree add "$WORKTREE_PATH" --detach origin/v3',
                    'gc bd update {{issue}} --set-metadata work_dir="$WORKTREE"',
                    "WORKTREE_RECREATED=1",
                    "git branch --show-current",
                    "recreated worktree is on",
                    "git rebase --rebase-merges",
                    "--reapply-cherry-picks",
                    "--empty=stop",
                    'git cat-file -e "$FORK_SHA^{commit}"',
                    'git merge-base --is-ancestor "$FORK_SHA" HEAD',
                    'git merge-base --is-ancestor "$FORK_SHA" origin/v3',
                    "not a commit in this repository",
                    "not an ancestor of the recorded branch HEAD",
                    "not an ancestor of current origin/v3",
                    "establish a verified prior origin/v3 base",
                    "git merge-base --is-ancestor origin/v3 HEAD",
                ):
                    self.assertIn(marker, d2b_workspace_text)
                self.assertNotIn(
                    "recorded worktree does not exist",
                    d2b_workspace_text,
                )
                self.assertLess(
                    d2b_workspace_text.index(
                        'if [ "$BASE_REF" != "origin/v3" ]'
                    ),
                    d2b_workspace_text.index("WORKTREE_RECREATED=0"),
                )
                collision_index = d2b_workspace_text.index(
                    'if [ -e "$WORKTREE_PATH" ] || [ -L "$WORKTREE_PATH" ]'
                )
                local_worktree_index = d2b_workspace_text.index(
                    'git worktree add "$WORKTREE_PATH" "$BRANCH"'
                )
                remote_worktree_index = d2b_workspace_text.index(
                    'git worktree add --track -b "$BRANCH" "$WORKTREE_PATH" "origin/$BRANCH"'
                )
                detached_worktree_index = d2b_workspace_text.index(
                    'git worktree add "$WORKTREE_PATH" --detach origin/v3'
                )
                for worktree_add_index in (
                    local_worktree_index,
                    remote_worktree_index,
                    detached_worktree_index,
                ):
                    self.assertLess(collision_index, worktree_add_index)
                self.assertLess(
                    local_worktree_index,
                    detached_worktree_index,
                )
                self.assertLess(
                    remote_worktree_index,
                    detached_worktree_index,
                )
                worktree_metadata_index = d2b_workspace_text.index(
                    'gc bd update {{issue}} --set-metadata work_dir="$WORKTREE"'
                )
                self.assertLess(
                    detached_worktree_index,
                    worktree_metadata_index,
                )
                self.assertLess(
                    d2b_workspace_text.index('git status --porcelain'),
                    d2b_workspace_text.index('git checkout "$BRANCH"'),
                )
                self.assertLess(
                    d2b_workspace_text.index(
                        'if [ "$WORKTREE_RECREATED" = "1" ]'
                    ),
                    d2b_workspace_text.index('git checkout "$BRANCH"'),
                )
                rebase_index = d2b_workspace_text.index(
                    "git rebase --rebase-merges "
                    "--reapply-cherry-picks --empty=stop origin/v3"
                )
                for provenance_index in (
                    d2b_workspace_text.index(
                        'git cat-file -e "$FORK_SHA^{commit}"'
                    ),
                    d2b_workspace_text.index(
                        'git merge-base --is-ancestor "$FORK_SHA" HEAD'
                    ),
                    d2b_workspace_text.index(
                        'git merge-base --is-ancestor "$FORK_SHA" origin/v3'
                    ),
                ):
                    self.assertLess(provenance_index, rebase_index)
                self.assertLess(
                    d2b_workspace_text.index(
                        'git cat-file -e "$FORK_SHA^{commit}"'
                    ),
                    d2b_workspace_text.index(
                        'git merge-base --is-ancestor "$FORK_SHA" HEAD'
                    ),
                )
                self.assertLess(
                    d2b_workspace_text.index(
                        'git merge-base --is-ancestor "$FORK_SHA" HEAD'
                    ),
                    d2b_workspace_text.index(
                        'git merge-base --is-ancestor "$FORK_SHA" origin/v3'
                    ),
                )
                self.assertLess(
                    rebase_index,
                    d2b_workspace_text.index(
                        "if ! git merge-base --is-ancestor origin/v3 HEAD;",
                        rebase_index,
                    ),
                )
                self.assertLess(
                    detached_worktree_index,
                    d2b_workspace_text.index(
                        'git checkout -b "$BRANCH" origin/v3'
                    ),
                )
                recorded_recreate_index = d2b_workspace_text.index(
                    'if [ -n "$RECORDED_BRANCH" ]; then',
                    d2b_workspace_text.index("WORKTREE_RECREATED=0"),
                )
                recorded_recreate_block = d2b_workspace_text[
                    recorded_recreate_index:detached_worktree_index
                ]
                self.assertNotIn(
                    'git worktree add "$WORKTREE_PATH" --detach origin/v3',
                    recorded_recreate_block,
                )
                self.assertNotIn(
                    'git checkout -b "$BRANCH" origin/v3',
                    recorded_recreate_block,
                )
                self.assertNotIn(
                    "git remote show origin",
                    d2b_workspace_text,
                )

                build_basic = show_formula(
                    "build-basic",
                    "--rig",
                    "d2b",
                )
                self.assertTrue(build_basic["ok"])
                implement = show_formula(
                    "implement",
                    "--rig",
                    "d2b",
                )
                self.assertTrue(implement["ok"])

                config_result = run_gc(
                    "config",
                    "show",
                    "--city",
                    str(city),
                    "--json",
                )
                resolved_config = json.loads(config_result.stdout)
                self.assertEqual(
                    resolved_config["config"]["Workspace"]["Name"],
                    "d2b-gascity",
                )
                resolved_providers = resolved_config["config"]["Providers"]
                expected_resolved_args = {
                    "copilot-deep-sol": [
                        "--yolo",
                        "--model",
                        "gpt-5.6-sol",
                        "--context",
                        "long_context",
                        "--effort",
                        "medium",
                    ],
                    "copilot-review-grok": [
                        "--yolo",
                        "--model",
                        "grok-4.6",
                        "--context",
                        "long_context",
                        "--effort",
                        "high",
                    ],
                    "copilot-solid-luna": [
                        "--yolo",
                        "--model",
                        "gpt-5.6-luna",
                        "--context",
                        "long_context",
                        "--effort",
                        "max",
                    ],
                    "copilot-fast-luna": [
                        "--yolo",
                        "--model",
                        "gpt-5.6-luna",
                        "--context",
                        "default",
                        "--effort",
                        "medium",
                    ],
                }
                for provider_name, provider_args in expected_resolved_args.items():
                    provider = resolved_providers[provider_name]
                    self.assertEqual(provider["Base"], "builtin:copilot")
                    self.assertEqual(provider["Args"], provider_args)
                self.assertEqual(
                    {
                        name: resolved_providers[name]["Base"]
                        for name in (
                            "deep-thinker",
                            "reviewer",
                            "solid-worker",
                            "fast-worker",
                        )
                    },
                    {
                        "deep-thinker": "copilot-deep-sol",
                        "reviewer": "copilot-review-grok",
                        "solid-worker": "copilot-solid-luna",
                        "fast-worker": "copilot-fast-luna",
                    },
                )
                agents = resolved_config["config"].get("Agents")
                self.assertIsInstance(agents, list)
                mayors = [
                    agent
                    for agent in agents
                    if agent.get("Name") == "mayor"
                    and agent.get("Scope") == "city"
                ]
                self.assertEqual(len(mayors), 1)
                self.assertEqual(mayors[0]["Provider"], "deep-thinker")
                self.assertEqual(
                    mayors[0]["AppendFragments"],
                    [
                        "mayor-operating-rhythm",
                        "efficient-routing-rules",
                        "sdlc-mayor-coding-rules",
                    ],
                )
                self.assertEqual(mayors[0]["WakeMode"], "fresh")
                self.assertEqual(mayors[0]["MaxActiveSessions"], 1)
                self.assertEqual(
                    resolved_config["config"]["NamedSessions"],
                    [
                        {
                            "Name": "",
                            "Template": "mayor",
                            "Scope": "city",
                            "Dir": "",
                            "Mode": "always",
                        }
                    ],
                )
                expected_role_providers = {
                    "requirements-planner": "deep-thinker",
                    "design-author": "deep-thinker",
                    "task-decomposer": "deep-thinker",
                    "design-implementation-reviewer": "reviewer",
                    "design-test-risk-reviewer": "reviewer",
                    "implementation-reviewer": "reviewer",
                    "gap-analyst": "reviewer",
                    "review-synthesizer": "reviewer",
                    "issue-triager": "reviewer",
                    "implementation-worker": "solid-worker",
                    "run-operator": "fast-worker",
                    "publisher": "fast-worker",
                }
                for rig_name in ("d2b", "city-source"):
                    self.assertEqual(
                        {
                            agent.get("Name"): agent.get("Provider")
                            for agent in agents
                            if agent.get("Dir") == rig_name
                            and agent.get("Name") in expected_role_providers
                        },
                        expected_role_providers,
                    )
                rendered_mayor_result = run_gc("prime", "mayor", "--strict")
                self.assertEqual(rendered_mayor_result.stderr, "")
                rendered_mayor = rendered_mayor_result.stdout
                rendered_mayor_flat = " ".join(rendered_mayor.split())
                for marker in (
                    "Use `gc --help`",
                    "`gc doctor --json`",
                    "At the start of each turn",
                    "Your default state is idle",
                    "Gas City may show provider profiles as implicit agents",
                    "Do not implement source changes in the mayor session",
                    "Use the bound `d2b` rig",
                    "Use the separately bound `city-source` rig",
                    "repository governance",
                ):
                    self.assertIn(marker, rendered_mayor_flat)

                self.assertTrue(site.is_file())
                site_text = site.read_text(encoding="utf-8")
                self.assertIn(f'path = "{rig}"', site_text)
                self.assertIn('name = "d2b"', site_text)
                self.assertIn(f'path = "{city_source}"', site_text)
                self.assertIn('name = "city-source"', site_text)
                self.assertTrue((city_source / ".beads").is_dir())
                native_city = tomllib.loads(
                    (city / "city.toml").read_text(encoding="utf-8")
                )
                native_rigs = {
                    rig_config["name"]: rig_config
                    for rig_config in native_city["rigs"]
                }
                self.assertEqual(
                    {
                        key: native_rigs["d2b"][key]
                        for key in ("name", "prefix", "default_branch")
                    },
                    {"name": "d2b", "prefix": "d2b", "default_branch": "v3"},
                )
                self.assertNotIn("path", native_rigs["d2b"])
                self.assertNotIn("path", native_rigs["city-source"])
                for relative in AUTHORED_FILES:
                    self.assertNotIn(
                        str(rig).encode(),
                        (source / relative).read_bytes(),
                    )
                    self.assertNotIn(
                        str(city_source).encode(),
                        (source / relative).read_bytes(),
                    )
                self.assertFalse(
                    (home / ".config" / "systemd" / "user").exists()
                )
                self.assertFalse((gc_home / "supervisor.toml").exists())
            finally:
                _stop_processes_for(root)

        for relative, contents in before.items():
            self.assertEqual((ROOT / relative).read_bytes(), contents)
        for relative, metadata in source_runtime_before.items():
            self.assertEqual(
                _path_metadata(ROOT / relative),
                metadata,
                f"source runtime metadata changed: {relative}",
            )
        self.assertFalse(
            _tracked_runtime_state(),
            "tracked or staged runtime state is present",
        )


class VendoredPrBabysitTests(unittest.TestCase):
    def test_pr_babysit_authored_files_are_fully_inventoried(self) -> None:
        actual_files = {
            str(path.relative_to(PR_BABYSIT_ROOT))
            for path in PR_BABYSIT_ROOT.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        self.assertEqual(actual_files, set(PR_BABYSIT_AUTHORED_FILES))
        for relative in PR_BABYSIT_AUTHORED_FILES:
            self.assertTrue((PR_BABYSIT_ROOT / relative).is_file(), relative)

    def test_pr_babysit_manifest_pins_exact_upstream_subset(self) -> None:
        manifest = json.loads(
            (PR_BABYSIT_ROOT / "UPSTREAM.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["upstream"],
            {
                "repository": PR_BABYSIT_UPSTREAM_REPOSITORY,
                "tag": PR_BABYSIT_UPSTREAM_TAG,
                "commit": PR_BABYSIT_UPSTREAM_COMMIT,
            },
        )
        self.assertEqual(
            set(manifest["excluded_surfaces"]),
            PR_BABYSIT_EXCLUDED_SURFACES,
        )
        entries = manifest["files"]
        self.assertEqual(
            {entry["local"] for entry in entries},
            set(PR_BABYSIT_FILES),
        )
        for entry in entries:
            expected = PR_BABYSIT_FILES[entry["local"]]
            expected_keys = {"local", "source", "sha256"}
            if "local_sha256" in expected:
                expected_keys.add("local_sha256")
            self.assertEqual(set(entry), expected_keys)
            self.assertEqual(entry["source"], expected["source"])
            self.assertEqual(entry["sha256"], expected["sha256"])
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(
                (PR_BABYSIT_ROOT / entry["local"]).is_file(),
                entry["local"],
            )
            if "local_sha256" in entry:
                self.assertRegex(
                    entry["local_sha256"],
                    r"^[0-9a-f]{64}$",
                )
                self.assertEqual(
                    entry["local_sha256"],
                    expected["local_sha256"],
                )
                self.assertEqual(
                    entry["local_sha256"],
                    hashlib.sha256(
                        (PR_BABYSIT_ROOT / entry["local"]).read_bytes()
                    ).hexdigest(),
                )

    def test_pr_babysit_license_retains_mit_notice(self) -> None:
        license_path = PR_BABYSIT_ROOT / "LICENSE"
        license_bytes = license_path.read_bytes()
        self.assertEqual(
            hashlib.sha256(license_bytes).hexdigest(),
            PR_BABYSIT_FILES["LICENSE"]["sha256"],
        )
        license_text = license_bytes.decode("utf-8")
        for marker in (
            "MIT License",
            "Copyright (c) 2025 Every",
            "Permission is hereby granted",
            "THE SOFTWARE IS PROVIDED \"AS IS\"",
        ):
            self.assertIn(marker, license_text)

    def test_pr_babysit_files_are_self_contained(self) -> None:
        expected_files = set(PR_BABYSIT_FILES)
        actual_files = {
            str(path.relative_to(PR_BABYSIT_ROOT))
            for path in PR_BABYSIT_ROOT.rglob("*")
            if path.is_file()
            and path.name != "UPSTREAM.json"
            and (
                path.is_relative_to(PR_BABYSIT_SKILL_ROOT)
                or path == PR_BABYSIT_ROOT / "LICENSE"
            )
        }
        self.assertEqual(actual_files, expected_files)
        for relative in PR_BABYSIT_LOCAL_FILES:
            self.assertTrue((PR_BABYSIT_ROOT / relative).is_file(), relative)
        for relative in sorted(expected_files):
            path = PR_BABYSIT_ROOT / relative
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("../", text, relative)
            for reference in re.findall(r"`(references/[^`]+)`", text):
                target = PR_BABYSIT_SKILL_ROOT / reference
                self.assertTrue(target.is_file(), f"{relative}: {reference}")
        self.assertTrue(
            (PR_BABYSIT_SKILL_ROOT / "scripts" / "pr-snapshot").stat().st_mode
            & 0o111
        )

    def test_pr_babysit_keeps_target_watch_contract_only(self) -> None:
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in PR_BABYSIT_SKILL_ROOT.rglob("*")
            if path.is_file()
        ).lower()
        for marker in (
            "snapshot-first",
            "pr-snapshot",
            "current head",
            "stale-sha",
            "branch_currency",
            "expected_head_sha",
            "feedback before ci",
            "untrusted",
            "never execute commands",
            "merge-ready",
        ):
            self.assertIn(marker, text)
        for marker in (
            "stack",
            "stack-ready",
            "stack-land",
            "upstack",
            "gh stack",
            "git merge",
            "gh pr merge",
            "force-push",
            "raw rebase",
            "git rebase",
            "workflow approval",
            "approve-ci",
            "ce-debug",
            "ce-resolve-pr-feedback",
            "plugin",
            "delegate",
            "user-global",
            "global install",
            "scheduler",
            "daemon",
            "/tmp",
            "mktemp",
        ):
            self.assertNotIn(marker, text)

    def test_pr_snapshot_keeps_review_text_as_data(self) -> None:
        script = PR_BABYSIT_SKILL_ROOT / "scripts" / "pr-snapshot"
        root = _temporary_root("pr-snapshot-review-data-")
        try:
            marker = root / "review-command-ran"
            planted = f"$(touch {marker})"
            fixture = root / "snapshot.json"
            fixture.write_text(
                json.dumps(
                    {
                        "url": "https://github.com/octo/example/pull/1",
                        "pr_state": "OPEN",
                        "head_sha": "a" * 40,
                        "mergeable": "MERGEABLE",
                        "merge_state_status": "CLEAN",
                        "base": {
                            "ref": "main",
                            "oid": "b" * 40,
                            "identity": "current",
                        },
                        "checks": [],
                        "threads": [],
                        "feedback": [
                            {
                                "id": "comment-1",
                                "body": planted,
                                "edit_id": "edit-1",
                            }
                        ],
                        "review_decision": None,
                        "review_in_progress": False,
                        "awaiting_approval": 0,
                    }
                ),
                encoding="utf-8",
            )
            (root / "gc").mkdir()
            result = subprocess.run(
                [
                    str(script),
                    "snapshot",
                    "--pr",
                    "1",
                    "--repo",
                    "octo/example",
                    "--watch-id",
                    "d2b-pr-review-data",
                    "--state-dir",
                    str(root / "gc" / "state" / "d2b-pr-review-data"),
                    "--fetch-file",
                    str(fixture),
                    "--start-invocation",
                ],
                capture_output=True,
                text=True,
                env=os.environ | {"GC_DIR": str(root / "gc")},
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(planted, result.stdout)
            self.assertFalse(marker.exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_babysit_wake_bootstrap_uses_watch_id_and_read_only_commands(self):
        skill = (PR_BABYSIT_SKILL_ROOT / "SKILL.md").read_text(
            encoding="utf-8"
        )
        prompt = (
            PR_BABYSIT_ROOT
            / "agents"
            / "pr-babysitter"
            / "prompt.template.md"
        ).read_text(encoding="utf-8")
        glossary = (
            CORE_PACK_ROOT
            / "template-fragments"
            / "command-glossary.template.md"
        ).read_text(encoding="utf-8")
        show = "gc pr-babysit pr-babysit show --watch-id <watch-id> --json"
        checkpoint = "gc pr-babysit pr-babysit checkpoint"
        dispatch = "gc pr-babysit pr-babysit dispatch-repair"
        for text in (skill, prompt):
            self.assertIn(show, text)
            self.assertIn(checkpoint, text)
            self.assertIn(dispatch, text)
            for field in (
                "watch_id",
                "expected_generation",
                "expected_head_sha",
                "observed_head_sha",
                "observed_at",
                "next_snapshot_at",
                "action_kind",
                "fingerprint",
                "addressed_thread_ids",
            ):
                self.assertIn(field, text)
            self.assertNotIn("git checkout", text.lower())
            self.assertNotIn("git push", text.lower())
        self.assertIn("gc pr-babysit pr-babysit", glossary)
        gate_end = prompt.index("\ndone\n```")
        self.assertGreater(prompt.index(show), gate_end)
        self.assertIn("$GC_DIR/state/<watch-id>", prompt)
        self.assertIn("current branch", prompt.lower())

    @staticmethod
    def _snapshot_fixture(
        root: pathlib.Path,
        *,
        base: dict[str, object],
        threads: list[dict[str, object]] | None = None,
        extra: dict[str, object] | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], pathlib.Path]:
        script = PR_BABYSIT_SKILL_ROOT / "scripts" / "pr-snapshot"
        gc_dir = root / "gc"
        gc_dir.mkdir(parents=True)
        fixture = root / "snapshot.json"
        payload: dict[str, object] = {
            "url": "https://github.com/octo/example/pull/7",
            "pr_state": "OPEN",
            "head_ref": "feature/x",
            "head_sha": "a" * 40,
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
            "base": base,
            "checks": [],
            "threads": threads or [],
            "feedback": [],
        }
        payload.update(extra or {})
        fixture.write_text(json.dumps(payload), encoding="utf-8")
        result = subprocess.run(
            [
                str(script),
                "snapshot",
                "--pr",
                "7",
                "--repo",
                "octo/example",
                "--expected-base",
                "main",
                "--expected-head-ref",
                "feature/x",
                "--expected-head-sha",
                "a" * 40,
                "--watch-id",
                "d2b-pr-test",
                "--state-dir",
                str(gc_dir / "state" / "d2b-pr-test"),
                "--fetch-file",
                str(fixture),
                "--start-invocation",
            ],
            cwd=ROOT,
            env=os.environ | {"GC_DIR": str(gc_dir)},
            capture_output=True,
            text=True,
            check=False,
        )
        return result, gc_dir

    def test_pr_snapshot_base_identity_is_current_stale_or_unknown(self):
        cases = (
            ("current", {"ref": "main", "oid": "b" * 40, "current_oid": "b" * 40}),
            ("stale", {"ref": "main", "oid": "b" * 40, "current_oid": "c" * 40}),
            ("unknown", {"ref": "main", "oid": "b" * 40, "identity": "unknown"}),
        )
        for identity, base in cases:
            with self.subTest(identity=identity):
                root = _temporary_root(f"snapshot-base-{identity}-")
                try:
                    result, _ = self._snapshot_fixture(root, base=base)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    snapshot = json.loads(result.stdout)
                    self.assertEqual(snapshot["base"]["identity"], identity)
                    self.assertEqual(snapshot["base_ref_blocker"], None if identity == "current" else identity)
                    self.assertEqual(
                        snapshot["mergeability_certain"],
                        identity == "current",
                    )
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def test_pr_snapshot_live_base_identity_compares_repository_ref(self):
        page = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [],
                            "pageInfo": {
                                "hasNextPage": False,
                                "endCursor": None,
                            },
                        }
                    }
                }
            }
        }
        cases = (
            ("current", {"object": {"sha": "b" * 40}}, True),
            ("stale", {"object": {"sha": "c" * 40}}, True),
            ("unknown", {"object": {}}, False),
        )
        for identity, base, succeeds in cases:
            with self.subTest(identity=identity):
                root = _temporary_root(f"snapshot-live-base-{identity}-")
                try:
                    result, calls = self._run_live_snapshot(
                        root,
                        graphql=[page],
                        base=base,
                    )
                    if succeeds:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        snapshot = json.loads(result.stdout)
                        self.assertEqual(
                            snapshot["base"]["identity"],
                            identity,
                        )
                        self.assertEqual(
                            snapshot["base"]["current_oid"],
                            base["object"]["sha"],
                        )
                        self.assertEqual(
                            [call[0:2] for call in calls[:2]],
                            [["pr", "view"], ["api", "repos/octo/example/git/ref/heads/main"]],
                        )
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("invalid SHA", result.stderr)
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def test_pr_snapshot_rejects_removed_commands_and_flag_aliases(self):
        script = PR_BABYSIT_SKILL_ROOT / "scripts" / "pr-snapshot"
        for command in ("watch", "mark"):
            result = subprocess.run(
                [str(script), command],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0, command)
        aliases = (
            "--expected-base-ref",
            "--expected-base-name",
            "--base-ref",
            "--head-ref",
            "--expected-head",
            "--head-sha",
        )
        for alias in aliases:
            with self.subTest(alias=alias):
                result = subprocess.run(
                    [
                        str(script),
                        "snapshot",
                        "--pr",
                        "7",
                        alias,
                        "main",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0, alias)
                self.assertRegex(
                    result.stderr,
                    r"(unrecognized arguments|ambiguous option)",
                )

    @staticmethod
    def _fake_github_script() -> str:
        return r"""#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
config = json.loads(Path(os.environ["FAKE_GH_CONFIG"]).read_text(encoding="utf-8"))
calls_path = Path(os.environ["FAKE_GH_CALLS"])
calls = json.loads(calls_path.read_text(encoding="utf-8")) if calls_path.exists() else []
calls.append(args)
calls_path.write_text(json.dumps(calls), encoding="utf-8")
if config.get("sleep"):
    time.sleep(float(config["sleep"]))
if args[:2] == ["pr", "view"]:
    print(json.dumps(config["pr"]))
elif args and args[0] == "api" and "graphql" in args:
    index = sum("graphql" in call for call in calls[:-1])
    print(json.dumps(config["graphql"][index]))
elif args and args[0] == "api":
    print(json.dumps(config["base"]))
else:
    print("unexpected GitHub command", file=sys.stderr)
    raise SystemExit(2)
"""

    def _run_live_snapshot(
        self,
        root: pathlib.Path,
        *,
        graphql: list[dict[str, object]],
        pr: dict[str, object] | None = None,
        base: dict[str, object] | None = None,
        timeout: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
        fake = root / "gh"
        fake.write_text(self._fake_github_script(), encoding="utf-8")
        fake.chmod(0o755)
        calls_path = root / "gh-calls.json"
        calls_path.write_text("[]\n", encoding="utf-8")
        config_path = root / "gh-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "pr": pr
                    or {
                        "state": "OPEN",
                        "isDraft": False,
                        "mergeable": "MERGEABLE",
                        "mergeStateStatus": "CLEAN",
                        "reviewDecision": None,
                        "headRefName": "feature/x",
                        "headRefOid": "a" * 40,
                        "baseRefName": "main",
                        "baseRefOid": "b" * 40,
                        "url": "https://github.com/octo/example/pull/7",
                        "statusCheckRollup": [],
                        "comments": [],
                        "reviews": [],
                        "isCrossRepository": False,
                        "headRepository": {"nameWithOwner": "octo/example"},
                        "baseRepository": {"nameWithOwner": "octo/example"},
                    },
                    "base": base or {"object": {"sha": "b" * 40}},
                    "graphql": graphql,
                    "sleep": 1 if timeout is not None else 0,
                }
            ),
            encoding="utf-8",
        )
        gc_dir = root / "gc"
        gc_dir.mkdir(exist_ok=True)
        env = os.environ | {
            "GC_DIR": str(gc_dir),
            "PR_BABYSIT_GH_BIN": str(fake),
            "FAKE_GH_CONFIG": str(config_path),
            "FAKE_GH_CALLS": str(calls_path),
        }
        if timeout is not None:
            env["PR_BABYSIT_GITHUB_TIMEOUT_SECONDS"] = timeout
        result = subprocess.run(
            [
                str(PR_BABYSIT_SKILL_ROOT / "scripts" / "pr-snapshot"),
                "snapshot",
                "--pr",
                "7",
                "--repo",
                "octo/example",
                "--expected-base",
                "main",
                "--expected-head-ref",
                "feature/x",
                "--expected-head-sha",
                "a" * 40,
                "--watch-id",
                "d2b-pr-live",
                "--state-dir",
                str(gc_dir / "state" / "d2b-pr-live"),
                "--start-invocation",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return result, json.loads(calls_path.read_text(encoding="utf-8"))

    def test_pr_snapshot_fetches_paginated_inline_threads_as_data(self):
        root = _temporary_root("snapshot-graphql-")
        marker = root / "review-command-ran"
        planted = f"$(touch {marker})"
        page_one = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "id": "thread-open",
                                    "isResolved": False,
                                    "isOutdated": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": "comment-open",
                                                "author": {"login": "reviewer"},
                                                "body": planted,
                                                "url": "https://github.com/comment/open",
                                            }
                                        ],
                                        "pageInfo": {
                                            "hasNextPage": False,
                                            "endCursor": None,
                                        },
                                    },
                                },
                                {
                                    "id": "thread-resolved",
                                    "isResolved": True,
                                    "isOutdated": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": "comment-resolved",
                                                "author": {"login": "reviewer"},
                                                "body": "resolved",
                                                "url": "https://github.com/comment/resolved",
                                            }
                                        ],
                                        "pageInfo": {
                                            "hasNextPage": False,
                                            "endCursor": None,
                                        },
                                    },
                                },
                            ],
                            "pageInfo": {
                                "hasNextPage": True,
                                "endCursor": "cursor-1",
                            },
                        }
                    }
                }
            }
        }
        page_two = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "id": "thread-outdated",
                                    "isResolved": False,
                                    "isOutdated": True,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": "comment-outdated",
                                                "author": {"login": "reviewer"},
                                                "body": "outdated",
                                                "url": "https://github.com/comment/outdated",
                                            }
                                        ],
                                        "pageInfo": {
                                            "hasNextPage": False,
                                            "endCursor": None,
                                        },
                                    },
                                },
                                {
                                    "id": "thread-open-2",
                                    "isResolved": False,
                                    "isOutdated": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": "comment-open-2",
                                                "author": {"login": "reviewer-2"},
                                                "body": "second open",
                                                "url": "https://github.com/comment/open-2",
                                            }
                                        ],
                                        "pageInfo": {
                                            "hasNextPage": False,
                                            "endCursor": None,
                                        },
                                    },
                                },
                            ],
                            "pageInfo": {
                                "hasNextPage": False,
                                "endCursor": None,
                            },
                        }
                    }
                }
            }
        }
        try:
            result, calls = self._run_live_snapshot(
                root,
                graphql=[page_one, page_two],
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = json.loads(result.stdout)
            threads = {
                item["thread_id"]: item for item in snapshot["threads"]
            }
            self.assertEqual(snapshot["counts"]["threads"], 2)
            self.assertEqual(
                set(threads),
                {
                    "thread-open",
                    "thread-resolved",
                    "thread-outdated",
                    "thread-open-2",
                },
            )
            self.assertEqual(
                threads["thread-open"]["comments"][0]["body"],
                planted,
            )
            self.assertEqual(
                threads["thread-open"]["comments"][0]["author"],
                "reviewer",
            )
            self.assertEqual(
                threads["thread-resolved"]["is_resolved"],
                True,
            )
            self.assertEqual(
                threads["thread-outdated"]["is_outdated"],
                True,
            )
            self.assertFalse(marker.exists())
            self.assertEqual(sum("graphql" in call for call in calls), 2)
            self.assertNotIn(
                planted,
                json.dumps([call for call in calls if "graphql" in call]),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_snapshot_surfaces_fork_identity_without_mapping_head(self):
        root = _temporary_root("snapshot-fork-")
        try:
            result, _ = self._run_live_snapshot(
                root,
                graphql=[
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "reviewThreads": {
                                        "nodes": [],
                                        "pageInfo": {
                                            "hasNextPage": False,
                                            "endCursor": None,
                                        },
                                    }
                                }
                            }
                        }
                    }
                ],
                pr={
                    "state": "OPEN",
                    "isDraft": False,
                    "mergeable": "MERGEABLE",
                    "mergeStateStatus": "CLEAN",
                    "reviewDecision": None,
                    "headRefName": "feature/x",
                    "headRefOid": "a" * 40,
                    "baseRefName": "main",
                    "baseRefOid": "b" * 40,
                    "url": "https://github.com/octo/example/pull/7",
                    "statusCheckRollup": [],
                    "comments": [],
                    "reviews": [],
                    "isCrossRepository": True,
                    "headRepository": {"nameWithOwner": "fork/example"},
                    "baseRepository": {"nameWithOwner": "octo/example"},
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = json.loads(result.stdout)
            self.assertTrue(snapshot["cross_repository"])
            self.assertEqual(
                snapshot["identity_blocker"]["code"],
                "cross-repository-head",
            )
            self.assertEqual(snapshot["head_repository"], "fork/example")
            self.assertFalse(snapshot["mergeability_certain"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_snapshot_github_timeout_fails_closed(self):
        root = _temporary_root("snapshot-timeout-")
        try:
            result, _ = self._run_live_snapshot(
                root,
                graphql=[],
                timeout="0.05",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("timed out", result.stderr.lower())
            self.assertNotIn("traceback", result.stderr.lower())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_u5_decision_contract_uses_normalized_snapshot_fields(self):
        skill = (
            PR_BABYSIT_SKILL_ROOT / "SKILL.md"
        ).read_text(encoding="utf-8")
        tick = (
            PR_BABYSIT_SKILL_ROOT / "references" / "tick.md"
        ).read_text(encoding="utf-8")
        branch_currency = (
            PR_BABYSIT_SKILL_ROOT / "references" / "branch-currency.md"
        ).read_text(encoding="utf-8")
        self.assertLess(
            tick.index("Review feedback."),
            tick.index("Current-head CI."),
        )
        self.assertIn(
            "Running checks are waiting evidence, not repair work.",
            tick,
        )
        self.assertIn("`BEHIND` is a human blocker", branch_currency)
        self.assertIn("`DIRTY` and `CONFLICTING`", branch_currency)
        self.assertIn("feedback before CI", skill)

        def decision(snapshot: dict[str, object]) -> str:
            actionable = snapshot["actionable"]
            if (
                actionable["threads"]
                or actionable["comments"]
            ):
                return "feedback"
            if actionable["ci"]:
                return "ci"
            if snapshot["branch_currency"] is not None:
                return "blocked"
            if (
                snapshot["review_in_progress"]
                or not snapshot["checks_terminal"]
            ):
                return "waiting"
            return "merge-ready"

        cases = (
            (
                "in-progress-check",
                {
                    "checks": [
                        {
                            "key": "required-ci",
                            "name": "required-ci",
                            "status": "IN_PROGRESS",
                            "conclusion": None,
                        }
                    ]
                },
                "waiting",
            ),
            (
                "feedback-before-ci",
                {
                    "checks": [
                        {
                            "key": "required-ci",
                            "name": "required-ci",
                            "status": "COMPLETED",
                            "conclusion": "FAILURE",
                        }
                    ],
                    "feedback": None,
                    "reviews": [
                        {
                            "id": "review-1",
                            "body": "please fix the assertion",
                        }
                    ],
                },
                "feedback",
            ),
            (
                "behind",
                {
                    "merge_state_status": "BEHIND",
                    "branch_currency": {
                        "status": "BEHIND",
                        "route": "normal-base",
                        "head_sha": "a" * 40,
                        "base_oid": "b" * 40,
                        "expected_head_sha": "a" * 40,
                        "host_branch_update_capability": True,
                    },
                },
                "blocked",
            ),
            (
                "dirty",
                {
                    "merge_state_status": "DIRTY",
                    "branch_currency": {
                        "status": "DIRTY",
                        "route": "normal-base",
                        "head_sha": "a" * 40,
                        "base_oid": "b" * 40,
                        "expected_head_sha": "a" * 40,
                        "host_branch_update_capability": False,
                    },
                },
                "blocked",
            ),
            (
                "conflicting",
                {
                    "merge_state_status": "CONFLICTING",
                    "branch_currency": {
                        "status": "CONFLICTING",
                        "route": "normal-base",
                        "head_sha": "a" * 40,
                        "base_oid": "b" * 40,
                        "expected_head_sha": "a" * 40,
                        "host_branch_update_capability": False,
                    },
                },
                "blocked",
            ),
        )
        for name, extra, expected in cases:
            with self.subTest(name=name):
                root = _temporary_root(f"u5-decision-{name}-")
                try:
                    result, _ = self._snapshot_fixture(
                        root,
                        base={
                            "ref": "main",
                            "oid": "b" * 40,
                            "current_oid": "b" * 40,
                        },
                        extra=extra,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    snapshot = json.loads(result.stdout)
                    self.assertEqual(decision(snapshot), expected)
                    if name == "in-progress-check":
                        self.assertFalse(snapshot["checks_terminal"])
                        self.assertFalse(snapshot["all_checks_ok"])
                        self.assertEqual(snapshot["actionable"]["ci"], [])
                    elif name == "feedback-before-ci":
                        self.assertEqual(snapshot["counts"]["comments"], 1)
                        self.assertEqual(snapshot["counts"]["ci"], 1)
                        self.assertEqual(
                            snapshot["feedback"][0]["kind"],
                            "review",
                        )
                        self.assertEqual(
                            snapshot["actionable"]["ci"][0]["head_sha"],
                            snapshot["head_sha"],
                        )
                    else:
                        self.assertEqual(
                            snapshot["branch_currency"]["status"],
                            name.upper(),
                        )
                        self.assertEqual(
                            snapshot["branch_currency"]["attention"],
                            "decide",
                        )
                        self.assertIsNotNone(
                            snapshot["branch_currency_blocker"]
                        )
                finally:
                    shutil.rmtree(root, ignore_errors=True)

        marker_root = _temporary_root("u5-decision-command-data-")
        try:
            marker = marker_root / "review-command-ran"
            planted = f"$(touch {marker})"
            result, _ = self._snapshot_fixture(
                marker_root,
                base={
                    "ref": "main",
                    "oid": "b" * 40,
                    "current_oid": "b" * 40,
                },
                extra={
                    "checks": [
                        {
                            "key": "required-ci",
                            "name": "required-ci",
                            "status": "COMPLETED",
                            "conclusion": "FAILURE",
                        }
                    ],
                    "feedback": None,
                    "reviews": [{"id": "review-1", "body": planted}],
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = json.loads(result.stdout)
            self.assertEqual(decision(snapshot), "feedback")
            self.assertEqual(snapshot["feedback"][0]["body"], planted)
            self.assertFalse(marker.exists())
        finally:
            shutil.rmtree(marker_root, ignore_errors=True)

    def test_pr_snapshot_rejects_symlinked_watch_state_path(self):
        root = _temporary_root("snapshot-symlink-")
        try:
            gc_dir = root / "gc"
            gc_dir.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (gc_dir / "state").symlink_to(outside, target_is_directory=True)
            fixture = root / "fixture.json"
            fixture.write_text(
                json.dumps(
                    {
                        "head_sha": "a" * 40,
                        "base": {
                            "ref": "main",
                            "oid": "b" * 40,
                            "current_oid": "b" * 40,
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(PR_BABYSIT_SKILL_ROOT / "scripts" / "pr-snapshot"),
                    "snapshot",
                    "--pr",
                    "7",
                    "--repo",
                    "octo/example",
                    "--expected-base",
                    "main",
                    "--watch-id",
                    "d2b-pr-symlink",
                    "--state-dir",
                    str(gc_dir / "state" / "d2b-pr-symlink"),
                    "--fetch-file",
                    str(fixture),
                    "--start-invocation",
                ],
                cwd=ROOT,
                env=os.environ | {"GC_DIR": str(gc_dir)},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", result.stderr.lower())
            self.assertFalse((outside / "d2b-pr-symlink").exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_pr_babysit_pack_is_rig_imported_and_on_demand(self) -> None:
        pack = tomllib.loads(
            (PR_BABYSIT_ROOT / "pack.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(pack["pack"]["name"], "pr-babysit")
        self.assertEqual(pack["pack"]["schema"], 2)
        self.assertNotIn("imports", pack)
        self.assertNotIn("named_session", pack)

        agent = tomllib.loads(
            (
                PR_BABYSIT_ROOT
                / "agents"
                / "pr-babysitter"
                / "agent.toml"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            {
                key: agent[key]
                for key in (
                    "scope",
                    "provider",
                    "wake_mode",
                    "work_dir",
                    "max_active_sessions",
                    "session_setup_script",
                )
            },
            {
                "scope": "rig",
                "provider": "fast-worker",
                "wake_mode": "fresh",
                "work_dir": "{{.RigRoot}}/.gc/agents/pr-babysitter",
                "max_active_sessions": 1,
                "session_setup_script": "assets/scripts/project-copilot-skill.sh",
            },
        )
        self.assertNotIn("dir", agent)
        self.assertFalse(agent.get("suspended", False))

        city = tomllib.loads(
            (CITY_ROOT / "city.toml").read_text(encoding="utf-8")
        )
        root_pack = tomllib.loads(
            (CITY_ROOT / "pack.toml").read_text(encoding="utf-8")
        )
        core_pack = tomllib.loads(
            (CORE_PACK_ROOT / "pack.toml").read_text(encoding="utf-8")
        )
        self.assertNotIn("pr-babysit", root_pack.get("imports", {}))
        self.assertNotIn("pr-babysit", core_pack.get("imports", {}))

        rigs = {rig["name"]: rig for rig in city["rigs"]}
        self.assertEqual(set(rigs), {"d2b", "city-source"})
        expected_runtime_names = {
            "d2b": "d2b/pr-babysit.pr-babysitter",
            "city-source": "city-source/pr-babysit.pr-babysitter",
        }
        for rig_name, rig in rigs.items():
            self.assertEqual(
                rig["imports"]["pr-babysit"],
                {"source": "../../packs/pr-babysit"},
            )
            # Pack v2 stamps a rig-imported agent as
            # <rig>/<binding>.<local-agent>.
            self.assertEqual(
                f"{rig_name}/pr-babysit.pr-babysitter",
                expected_runtime_names[rig_name],
            )

    def test_pr_babysit_model_tier_is_fast_luna_and_deterministic(self) -> None:
        base = tomllib.loads(
            (
                CORE_PACK_ROOT / "model-tiers.base.toml"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(base["tiers"]["pr-babysitter"], "fast-worker")

        city = tomllib.loads(
            (CITY_ROOT / "city.toml").read_text(encoding="utf-8")
        )
        generated = tomllib.loads(
            (CITY_ROOT / "model-tiers.toml").read_text(encoding="utf-8")
        )
        patches = generated["patches"]["agent"]
        for rig in city["rigs"]:
            matches = [
                patch
                for patch in patches
                if patch["dir"] == rig["name"]
                and patch["name"] == "pr-babysitter"
            ]
            self.assertEqual(
                matches,
                [
                    {
                        "dir": rig["name"],
                        "name": "pr-babysitter",
                        "provider": "fast-worker",
                    }
                ],
            )
        self.assertNotIn(
            "pr-babysit.pr-babysitter",
            {patch["name"] for patch in patches},
        )

        result = subprocess.run(
            [
                str(
                    CORE_PACK_ROOT
                    / "commands"
                    / "gen-model-tiers"
                    / "run.sh"
                ),
                str(CITY_ROOT / "city.toml"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            (CITY_ROOT / "model-tiers.toml").read_text(encoding="utf-8"),
        )

    def test_pr_babysit_prompt_fails_closed_before_github_actions(self) -> None:
        prompt = (
            PR_BABYSIT_ROOT
            / "agents"
            / "pr-babysitter"
            / "prompt.template.md"
        ).read_text(encoding="utf-8")
        lowered = prompt.lower()
        for marker in (
            PR_BABYSIT_UPSTREAM_COMMIT,
            "gc_dir",
            ".github/skills/pr-babysit",
            ".agents/skills/pr-babysit",
            PR_BABYSIT_PROJECTION_MARKER,
            "blocker",
            "do not",
            "v3",
            "main",
        ):
            self.assertIn(marker.lower(), lowered)
        gate = lowered.index(PR_BABYSIT_PROJECTION_MARKER)
        show = "gc pr-babysit pr-babysit show --watch-id <watch-id> --json"
        self.assertGreater(lowered.index(show), gate)
        self.assertNotIn("git checkout", lowered)
        self.assertNotIn("git push", lowered)
        for marker in (
            "user-global",
            "/tmp",
        ):
            self.assertNotIn(marker, lowered)
        for marker in (
            "gh_token",
            "github_token",
            "copilot token",
            "operator-attested",
            "contents write",
            "pull requests read",
            "fine-grained permissions",
            "untrusted input",
            "addressed thread ids",
        ):
            self.assertIn(marker, lowered)
        for relative in PR_BABYSIT_PROJECTED_FILES:
            match = re.search(
                rf"verify_file '([0-9a-f]{{64}})' "
                rf"'{re.escape(relative)}'",
                prompt,
            )
            self.assertIsNotNone(match, relative)
            self.assertEqual(
                match.group(1),
                hashlib.sha256(
                    (PR_BABYSIT_SKILL_ROOT / relative).read_bytes()
                ).hexdigest(),
            )

    def test_pr_babysit_projection_is_idempotent_and_fail_closed(self) -> None:
        script = PR_BABYSIT_ROOT / "assets" / "scripts" / "project-copilot-skill.sh"
        root = _temporary_root("pr-babysit-projection-")

        def tree_bytes(path: pathlib.Path) -> dict[str, bytes]:
            return {
                str(entry.relative_to(path)): entry.read_bytes()
                for entry in sorted(path.rglob("*"))
                if entry.is_file()
            }

        source_before = tree_bytes(PR_BABYSIT_ROOT)
        try:
            rig_source = root / "rig-source"
            rig_source.mkdir()
            workdir = rig_source / ".gc" / "agents" / "pr-babysitter"
            workdir.mkdir(parents=True)
            (rig_source / "keep.txt").write_text(
                "source checkout sentinel\n",
                encoding="utf-8",
            )
            for vendor_root, unrelated_name in (
                (workdir / ".github" / "skills", "unrelated-github"),
                (workdir / ".agents" / "skills", "unrelated-agents"),
            ):
                (vendor_root / unrelated_name).mkdir(parents=True)
                (vendor_root / unrelated_name / "keep.txt").write_text(
                    "unrelated skill\n",
                    encoding="utf-8",
                )
                stale = vendor_root / "pr-babysit"
                stale.mkdir()
                (stale / PR_BABYSIT_PROJECTION_MARKER).write_text(
                    "stale-commit\n",
                    encoding="utf-8",
                )
                (stale / "stale.txt").write_text(
                    "stale projection\n",
                    encoding="utf-8",
                )

            env = os.environ.copy()
            env.update(
                {
                    "GC_DIR": str(workdir),
                    "GC_RIG_ROOT": str(rig_source),
                }
            )
            result = subprocess.run(
                [str(script)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(PR_BABYSIT_UPSTREAM_COMMIT, result.stdout)

            for vendor_root in (
                workdir / ".github" / "skills",
                workdir / ".agents" / "skills",
            ):
                projected = vendor_root / "pr-babysit"
                self.assertEqual(
                    (projected / PR_BABYSIT_PROJECTION_MARKER).read_text(
                        encoding="utf-8"
                    ).strip(),
                    PR_BABYSIT_UPSTREAM_COMMIT,
                )
                for relative in PR_BABYSIT_PROJECTED_FILES:
                    self.assertEqual(
                        (projected / relative).read_bytes(),
                        (PR_BABYSIT_SKILL_ROOT / relative).read_bytes(),
                        relative,
                    )
                self.assertFalse((projected / "stale.txt").exists())

            self.assertEqual(
                (workdir / ".github" / "skills" / "unrelated-github" / "keep.txt")
                .read_text(encoding="utf-8"),
                "unrelated skill\n",
            )
            self.assertEqual(
                (workdir / ".agents" / "skills" / "unrelated-agents" / "keep.txt")
                .read_text(encoding="utf-8"),
                "unrelated skill\n",
            )
            workdir_after_first = tree_bytes(workdir)
            result = subprocess.run(
                [str(script)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(tree_bytes(workdir), workdir_after_first)
            self.assertEqual((rig_source / "keep.txt").read_text(encoding="utf-8"), "source checkout sentinel\n")
            self.assertFalse((rig_source / ".github").exists())
            self.assertFalse((rig_source / ".agents").exists())
            self.assertEqual(tree_bytes(PR_BABYSIT_ROOT), source_before)

            bad_pack = root / "bad-pack"
            shutil.copytree(PR_BABYSIT_ROOT, bad_pack)
            (bad_pack / "skills" / "pr-babysit" / "references" / "setup.md").unlink()
            bad_rig_source = root / "bad-rig-source"
            bad_workdir = bad_rig_source / ".gc" / "agents" / "pr-babysitter"
            bad_target = bad_workdir / ".github" / "skills" / "pr-babysit"
            bad_target.mkdir(parents=True)
            (bad_target / PR_BABYSIT_PROJECTION_MARKER).write_text(
                "previous-commit\n",
                encoding="utf-8",
            )
            (bad_target / "keep.txt").write_text(
                "previous projection\n",
                encoding="utf-8",
            )
            bad_env = env | {
                "GC_DIR": str(bad_workdir),
                "GC_RIG_ROOT": str(bad_rig_source),
            }
            bad_result = subprocess.run(
                [
                    str(
                        bad_pack
                        / "assets"
                        / "scripts"
                        / "project-copilot-skill.sh"
                    )
                ],
                cwd=ROOT,
                env=bad_env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(bad_result.returncode, 0)
            self.assertIn("BLOCKER", bad_result.stderr)
            self.assertEqual(
                tree_bytes(bad_workdir),
                {
                    ".github/skills/pr-babysit/.gascity-vendored-commit": b"previous-commit\n",
                    ".github/skills/pr-babysit/keep.txt": b"previous projection\n",
                },
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)


class PrBabysitStateTests(unittest.TestCase):
    _HANDOFF = {
        "rig": "d2b",
        "prefix": "d2b",
        "url": "https://github.com/octo/example/pull/7",
        "owner": "octo",
        "repository": "example",
        "pr_number": 7,
        "base_ref": "v3",
        "head_ref": "feature/u3",
        "head_repository": "octo/example",
        "head_sha": "a" * 40,
        "current_sha": "a" * 40,
        "observed_at": "2026-08-29T19:00:00Z",
        "next_snapshot_at": "2026-08-29T19:05:00Z",
        "active_since": "2026-08-29T19:00:00Z",
        "backstop_at": "2026-09-01T19:00:00Z",
        "pr_state": "OPEN",
    }

    @staticmethod
    def _fake_beads_script() -> str:
        return r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["FAKE_BEADS_ROOT"])
state_path = root / "beads.json"
calls_path = root / "calls.json"


def load(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


argv = sys.argv[1:]
calls = load(calls_path, [])
calls.append({"argv": argv, "actor": os.environ.get("BEADS_ACTOR", "")})
save(calls_path, calls)
records = load(state_path, [])
command_index = next(
    (index for index, value in enumerate(argv)
     if value in {"create", "show", "update", "close", "list", "dep"}),
    None,
)
if command_index is None:
    print("unknown command", file=sys.stderr)
    raise SystemExit(2)
command = argv[command_index]
args = argv[command_index + 1:]


KNOWN_FLAGS = {
    "create": {"--id", "--title", "--description", "--type", "--metadata", "--silent", "--json"},
    "show": {"--json"},
    "update": {"--claim", "--status", "--assignee", "--parent", "--set-metadata", "--json"},
    "close": {"--reason", "--json"},
    "list": {"--all", "--status", "--limit", "--sort", "--metadata-field", "--json"},
    "dep": {"--blocks", "--json"},
}
VALUE_FLAGS = {
    "--id",
    "--title",
    "--description",
    "--type",
    "--metadata",
    "--status",
    "--assignee",
    "--parent",
    "--set-metadata",
    "--reason",
    "--limit",
    "--sort",
    "--metadata-field",
    "--blocks",
}
values = {}
positionals = []
index = 0
while index < len(args):
    item = args[index]
    if not item.startswith("--"):
        positionals.append(item)
        index += 1
        continue
    flag, separator, inline_value = item.partition("=")
    if flag not in KNOWN_FLAGS[command]:
        print("Error: unknown flag: " + flag, file=sys.stderr)
        raise SystemExit(2)
    if flag in VALUE_FLAGS:
        if separator:
            value = inline_value
        elif index + 1 < len(args) and not args[index + 1].startswith("--"):
            value = args[index + 1]
            index += 1
        else:
            print("Error: flag needs an argument: " + flag, file=sys.stderr)
            raise SystemExit(2)
        if flag in {"--set-metadata", "--metadata-field"}:
            values.setdefault(flag, []).append(value)
        else:
            values[flag] = value
    else:
        values[flag] = True
    index += 1


def value(flag, default=""):
    return values.get(flag, default)


def positional(index=0, default=""):
    return positionals[index] if index < len(positionals) else default


def fail_once(kind):
    if os.environ.get("FAKE_BEADS_FAIL_ON") != kind:
        return
    marker = root / ("failure-" + kind)
    if marker.exists():
        return
    marker.write_text("failed\n", encoding="utf-8")
    print(kind + " failed", file=sys.stderr)
    raise SystemExit(1)


if command == "create" and "-action-" in value("--id"):
    fail_once("action-create")
if command == "dep":
    fail_once("dependency")
if command == "close" and "-action-" in positional():
    fail_once("close-action")
if command == "update":
    update_id = positional()
    metadata_values = {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for item in values.get("--set-metadata", [])
        if "=" in item
    }
    if metadata_values.get("state") == "repairing":
        fail_once("watch-repairing")
    if (
        metadata_values.get("state") == "watching"
        and "-action-" not in update_id
    ):
        fail_once("watch-confirm")


def record_for(issue_id):
    for record in records:
        if record["id"] == issue_id:
            return record
    return None


if command == "create":
    issue_id = value("--id")
    metadata = json.loads(value("--metadata", "{}"))
    existing = record_for(issue_id)
    if existing is not None:
        existing["title"] = value(
            "--title",
            positional(),
        )
        existing["description"] = value("--description")
        existing["metadata"] = metadata
        save(state_path, records)
        print(json.dumps(existing, sort_keys=True))
        raise SystemExit(0)
    record = {
        "id": issue_id,
        "title": value("--title", positional()),
        "description": value("--description"),
        "status": "open",
        "assignee": "",
        "metadata": metadata,
        "issue_type": value("--type", "task"),
    }
    records.append(record)
    save(state_path, records)
    print(json.dumps(record, sort_keys=True))
    raise SystemExit(0)


if command == "show":
    issue_id = positional()
    record = record_for(issue_id)
    if record is None:
        print("not found", file=sys.stderr)
        raise SystemExit(1)
    shown = dict(record)
    dependencies = []
    for dependency_id in record.get("blocked_by", []):
        dependency = record_for(dependency_id)
        if dependency is not None:
            dependencies.append(
                dict(dependency, dependency_type="blocks")
            )
    if dependencies:
        shown["dependencies"] = dependencies
    shown["dependency_count"] = len(dependencies)
    shown["dependent_count"] = 0
    print(json.dumps([shown], sort_keys=True))
    raise SystemExit(0)


if command == "list":
    listed = records
    if "--all" not in args:
        statuses = {value("--status")} if "--status" in values else {
            "open",
            "in_progress",
            "blocked",
            "deferred",
        }
        listed = [
            record
            for record in listed
            if record.get("status") in statuses
        ]
    for field in values.get("--metadata-field", []):
        key, separator, expected = field.partition("=")
        if separator:
            listed = [
                record
                for record in listed
                if (record.get("metadata") or {}).get(key) == expected
            ]
    sort_field = value("--sort")
    if sort_field:
        listed = sorted(
            listed,
            key=lambda record: record.get(sort_field, ""),
        )
    list_limit = value("--limit")
    if list_limit:
        listed = listed[: int(list_limit)]
    print(json.dumps(listed, sort_keys=True))
    raise SystemExit(0)


if command == "dep":
    blocker = positional()
    blocked = value("--blocks")
    blocker_record = record_for(blocker)
    blocked_record = record_for(blocked)
    if blocker_record is None or blocked_record is None:
        print("not found", file=sys.stderr)
        raise SystemExit(1)
    dependencies = set(blocked_record.get("blocked_by", []))
    dependencies.add(blocker)
    blocked_record["blocked_by"] = sorted(dependencies)
    save(state_path, records)
    print(
        json.dumps(
            {
                "blocked_id": blocked,
                "blocker_id": blocker,
                "schema_version": 1,
                "status": "added",
                "type": "blocks",
            },
            sort_keys=True,
        )
    )
    raise SystemExit(0)


if command == "update":
    issue_id = positional()
    record = record_for(issue_id)
    if record is None:
        print("not found", file=sys.stderr)
        raise SystemExit(1)
    actor = os.environ.get("BEADS_ACTOR", "fake")
    if "--claim" in values:
        if record["assignee"] and record["assignee"] != actor:
            print("issue already claimed by " + record["assignee"], file=sys.stderr)
            raise SystemExit(1)
        if record["status"] not in {"open", "in_progress"}:
            print("issue not claimable", file=sys.stderr)
            raise SystemExit(1)
        record["assignee"] = actor
        record["status"] = "in_progress"
    if "--status" in values:
        record["status"] = value("--status")
    if "--assignee" in values:
        record["assignee"] = value("--assignee")
    if "--parent" in values:
        record["parent"] = value("--parent")
    metadata = dict(record.get("metadata") or {})
    for item in values.get("--set-metadata", []):
        key, separator, item_value = item.partition("=")
        if separator:
            metadata[key] = item_value
    record["metadata"] = metadata
    save(state_path, records)
    print(json.dumps([record], sort_keys=True))
    raise SystemExit(0)


if command == "close":
    issue_id = positional()
    record = record_for(issue_id)
    if record is None:
        print("not found", file=sys.stderr)
        raise SystemExit(1)
    blockers = [
        dependency_id
        for dependency_id in record.get("blocked_by", [])
        if (
            record_for(dependency_id) is not None
            and record_for(dependency_id).get("status") != "closed"
        )
    ]
    if blockers:
        print(
            f"cannot close {issue_id}: blocked by open issues "
            f"[{', '.join(blockers)}] (use --force to override)",
            file=sys.stderr,
        )
        raise SystemExit(1)
    record["status"] = "closed"
    record["assignee"] = ""
    save(state_path, records)
    print(json.dumps([record], sort_keys=True))
    raise SystemExit(0)
"""

    def _fixture(self, name: str) -> tuple[pathlib.Path, dict[str, str]]:
        root = _temporary_root(f"u3-state-{name}-")
        fake = root / "fake-beads"
        fake.write_text(self._fake_beads_script(), encoding="utf-8")
        fake.chmod(0o755)
        (root / "beads.json").write_text("[]\n", encoding="utf-8")
        (root / "calls.json").write_text("[]\n", encoding="utf-8")
        return root, {
            "PR_BABYSIT_BEADS_BIN": str(fake),
            "FAKE_BEADS_ROOT": str(root),
            "PR_BABYSIT_BEADS_CWD": str(root),
            "GC_RIG_ROOT": str(root),
            "PR_BABYSIT_ALLOWED_HOSTS": "github.com,github.example",
        }

    def _run(
        self,
        env: dict[str, str],
        action: str,
        payload: dict[str, object] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(PR_BABYSIT_STATE_RUNNER), action]
        return subprocess.run(
            command,
            cwd=ROOT,
            env=os.environ | env,
            input=json.dumps(payload or {}),
            capture_output=True,
            text=True,
            check=False,
        )

    def _json(self, result: subprocess.CompletedProcess[str]) -> dict:
        self.assertTrue(result.stdout, result.stderr)
        return json.loads(result.stdout)

    @staticmethod
    def _state_module():
        spec = importlib.util.spec_from_file_location(
            "pr_babysit_state_for_tests",
            PR_BABYSIT_ROOT
            / "assets"
            / "scripts"
            / "pr-babysit-state.py",
        )
        if spec is None or spec.loader is None:
            raise AssertionError("could not load PR babysit state helper")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_subprocess_timeouts_fail_closed_with_existing_error_codes(self):
        module = self._state_module()
        timeout = subprocess.TimeoutExpired(["command"], 1)
        with mock.patch.dict(
            os.environ,
            {
                "PR_BABYSIT_BEADS_BIN": "bd",
                "PR_BABYSIT_BEADS_CWD": str(ROOT),
            },
            clear=False,
        ), mock.patch.object(module.subprocess, "run", side_effect=timeout):
            with self.assertRaises(module.StateError) as raised:
                module.run_beads(["show", "watch", "--json"])
        self.assertEqual(raised.exception.code, "beads-exec")

        context = {
            "github_host": "github.com",
            "owner": "octo",
            "repository": "example",
            "pr_number": 7,
            "input_url": "https://github.com/octo/example/pull/7",
        }
        with mock.patch.dict(
            os.environ,
            {
                "PR_BABYSIT_GH_BIN": "gh",
                "PR_BABYSIT_BEADS_CWD": str(ROOT),
                "PR_BABYSIT_ALLOWED_HOSTS": "github.com",
            },
            clear=False,
        ), mock.patch.object(module.subprocess, "run", side_effect=timeout):
            with self.assertRaises(module.StateError) as raised:
                module.query_github_publication(context)
        self.assertEqual(raised.exception.code, "github-query")

        with mock.patch.dict(
            os.environ,
            {
                "PR_BABYSIT_GC_BIN": "gc",
                "PR_BABYSIT_BEADS_CWD": str(ROOT),
            },
            clear=False,
        ), mock.patch.object(module.subprocess, "run", side_effect=timeout):
            with self.assertRaises(module.StateError) as raised:
                module.route_watch("d2b/pr-babysit.pr-babysitter", "d2b-watch")
        self.assertEqual(raised.exception.code, "route-failed")

        with mock.patch.dict(
            os.environ,
            {
                "PR_BABYSIT_GC_BIN": "gc",
                "PR_BABYSIT_BEADS_CWD": str(ROOT),
            },
            clear=False,
        ), mock.patch.object(
            module,
            "repair_formula_vars",
            return_value=[("watch_id", "d2b-watch")],
        ), mock.patch.object(module.subprocess, "run", side_effect=timeout):
            with self.assertRaises(module.StateError) as raised:
                module.attach_repair_formula(
                    {},
                    {"watch_id": "d2b-watch"},
                    "d2b-watch-action",
                    1,
                    "ci",
                    "",
                )
        self.assertEqual(raised.exception.code, "formula-exec")

        with mock.patch.object(module.subprocess, "run", side_effect=timeout):
            with self.assertRaises(module.StateError) as raised:
                module.validate_git_ref("v3", "base_ref")
        self.assertEqual(raised.exception.code, "configuration")

    def test_handoff_is_idempotent_and_preserves_existing_state(self) -> None:
        root, env = self._fixture("handoff")
        try:
            first = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_json = self._json(first)
            watch_id = first_json["watch_id"]
            waiting = self._run(
                env,
                "transition",
                {"watch_id": watch_id, "to": "waiting"},
            )
            self.assertEqual(waiting.returncode, 0, waiting.stderr)
            before = self._json(
                self._run(env, "show", {"watch_id": watch_id})
            )
            second = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(second.returncode, 0, second.stderr)
            second_json = self._json(second)
            self.assertEqual(first_json["watch_id"], second_json["watch_id"])
            self.assertTrue(first_json["created"])
            self.assertTrue(second_json["reused"])
            self.assertEqual(second_json["state"], "waiting")
            self.assertEqual(second_json["generation"], before["generation"])
            self.assertEqual(second_json["metadata"], before["metadata"])
            records = json.loads((root / "beads.json").read_text())
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["metadata"]["pr_number"], "7")
            creates = [
                call
                for call in json.loads((root / "calls.json").read_text())
                if call["argv"] and call["argv"][0] == "create"
            ]
            self.assertEqual(len(creates), 1)
            lock_dir = root / ".beads" / "pr-babysit-locks"
            self.assertTrue(lock_dir.is_dir())
            self.assertEqual(
                (lock_dir / f"{watch_id}.lock").read_bytes(),
                b"",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cli_rejects_undeployed_action_aliases(self) -> None:
        root, env = self._fixture("action-aliases")
        try:
            aliases = (
                "credential-check",
                "check-capability",
                "check_credentials",
                "publish-handoff",
                "handoff-publication",
                "publication_handoff",
                "verify-publication-handoff",
                "verify_handoff",
                "state",
                "state-show",
                "claim",
                "claim_action",
                "dispatch",
                "dispatch_repair",
                "repair",
                "record",
                "repair-result",
                "record_repair_result",
                "confirm",
                "confirm_action",
                "checkpoint-state",
                "record-checkpoint",
                "due",
                "list_due",
            )
            for alias in aliases:
                result = self._run(env, alias)
                self.assertNotEqual(result.returncode, 0, alias)
                error = self._json(result)["error"]
                self.assertEqual(
                    error["code"],
                    "invalid-request",
                    alias,
                )
                self.assertEqual(
                    error["message"],
                    "unsupported action",
                    alias,
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_concurrent_handoffs_create_one_watch(self) -> None:
        root, env = self._fixture("concurrent-handoff")
        try:
            command = [str(PR_BABYSIT_STATE_RUNNER), "handoff"]
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        subprocess.run,
                        command,
                        cwd=ROOT,
                        env=os.environ | env,
                        input=json.dumps(self._HANDOFF),
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    for _ in range(2)
                ]
                results = [future.result() for future in futures]
            self.assertTrue(
                all(result.returncode == 0 for result in results),
                results,
            )
            outputs = [json.loads(result.stdout) for result in results]
            self.assertEqual(
                {output["watch_id"] for output in outputs},
                {outputs[0]["watch_id"]},
            )
            self.assertEqual(
                sorted(output["created"] for output in outputs),
                [False, True],
            )
            records = json.loads((root / "beads.json").read_text())
            self.assertEqual(len(records), 1)
            creates = [
                call
                for call in json.loads((root / "calls.json").read_text())
                if call["argv"] and call["argv"][0] == "create"
            ]
            self.assertEqual(len(creates), 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_concurrent_differing_claims_have_one_winner(self) -> None:
        root, env = self._fixture("concurrent-claims")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            payloads = (
                {
                    "watch_id": watch_id,
                    "generation": 1,
                    "head_sha": "a" * 40,
                    "kind": "ci",
                    "fingerprint": "check-failed",
                },
                {
                    "watch_id": watch_id,
                    "generation": 1,
                    "head_sha": "a" * 40,
                    "kind": "review",
                    "fingerprint": "thread-open",
                },
            )
            command = [str(PR_BABYSIT_STATE_RUNNER), "claim-action"]
            with ThreadPoolExecutor(max_workers=len(payloads)) as executor:
                futures = [
                    executor.submit(
                        subprocess.run,
                        command,
                        cwd=ROOT,
                        env=os.environ | env,
                        input=json.dumps(payload),
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    for payload in payloads
                ]
                results = [future.result() for future in futures]
            self.assertEqual(
                sorted(result.returncode for result in results),
                [0, 1],
                results,
            )
            winner = next(
                json.loads(result.stdout)
                for result in results
                if result.returncode == 0
            )
            loser = next(
                json.loads(result.stdout)
                for result in results
                if result.returncode != 0
            )
            self.assertEqual(winner["watch_id"], watch_id)
            self.assertEqual(loser["error"]["code"], "already-claimed")
            records = json.loads((root / "beads.json").read_text())
            self.assertEqual(
                len([record for record in records if record["id"] != watch_id]),
                1,
            )
            watch = next(record for record in records if record["id"] == watch_id)
            self.assertEqual(watch["metadata"]["state"], "repairing")
            self.assertEqual(watch["metadata"]["claim_status"], "claimed")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_existing_action_is_reused_without_overwrite(self) -> None:
        root, env = self._fixture("action-reuse")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            claim_payload = {
                "watch_id": watch_id,
                "generation": 1,
                "head_sha": "a" * 40,
                "kind": "ci",
                "fingerprint": "check-failed",
            }
            claim = self._run(env, "claim-action", claim_payload)
            self.assertEqual(claim.returncode, 0, claim.stderr)
            action_id = self._json(claim)["action_id"]
            records = json.loads((root / "beads.json").read_text())
            watch = next(record for record in records if record["id"] == watch_id)
            action = next(record for record in records if record["id"] == action_id)
            action["title"] = "preserved action title"
            action["metadata"]["terminal_reason"] = "preserved-action-state"
            watch["status"] = "open"
            watch["assignee"] = ""
            watch["metadata"].update(
                {
                    "state": "watching",
                    "action_kind": "",
                    "action_fingerprint": "",
                    "claim_status": "none",
                }
            )
            (root / "beads.json").write_text(
                json.dumps(records, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )
            reused = self._run(env, "claim-action", claim_payload)
            self.assertEqual(reused.returncode, 0, reused.stderr)
            self.assertTrue(self._json(reused)["reused"])
            records = json.loads((root / "beads.json").read_text())
            action = next(record for record in records if record["id"] == action_id)
            self.assertEqual(action["title"], "preserved action title")
            self.assertEqual(
                action["metadata"]["terminal_reason"],
                "preserved-action-state",
            )
            creates = [
                call
                for call in json.loads((root / "calls.json").read_text())
                if call["argv"] and call["argv"][0] == "create"
            ]
            self.assertEqual(len(creates), 2)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_fake_beads_matches_real_contract_and_rejects_unknown_flags(self):
        root, env = self._fixture("beads-contract")
        fake = pathlib.Path(env["PR_BABYSIT_BEADS_BIN"])

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [str(fake), *args],
                cwd=root,
                env=os.environ | env | {"BEADS_ACTOR": "contract-test"},
                capture_output=True,
                text=True,
                check=False,
            )

        try:
            created = run(
                "create",
                "--id",
                "d2b-watch",
                "--title",
                "watch",
                "--description",
                "watch description",
                "--type",
                "task",
                "--metadata",
                '{"record_kind":"watch","state":"watching"}',
                "--silent",
                "--json",
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            self.assertIsInstance(json.loads(created.stdout), dict)

            overwritten = run(
                "create",
                "--id",
                "d2b-watch",
                "--title",
                "overwritten",
                "--description",
                "new description",
                "--type",
                "task",
                "--metadata",
                '{"record_kind":"watch","state":"waiting"}',
                "--silent",
                "--json",
            )
            self.assertEqual(overwritten.returncode, 0, overwritten.stderr)
            self.assertEqual(
                json.loads(overwritten.stdout)["title"],
                "overwritten",
            )

            shown = run("show", "d2b-watch", "--json")
            self.assertEqual(shown.returncode, 0, shown.stderr)
            shown_payload = json.loads(shown.stdout)
            self.assertIsInstance(shown_payload, list)
            self.assertEqual(shown_payload[0]["title"], "overwritten")

            updated = run(
                "update",
                "d2b-watch",
                "--claim",
                "--set-metadata",
                "state=repairing",
                "--json",
            )
            self.assertEqual(updated.returncode, 0, updated.stderr)
            updated_payload = json.loads(updated.stdout)
            self.assertIsInstance(updated_payload, list)
            self.assertEqual(updated_payload[0]["status"], "in_progress")
            self.assertEqual(
                updated_payload[0]["metadata"]["state"],
                "repairing",
            )

            action = run(
                "create",
                "--id",
                "d2b-action",
                "--title",
                "action",
                "--description",
                "action description",
                "--type",
                "task",
                "--metadata",
                '{"record_kind":"action","state":"open"}',
                "--silent",
                "--json",
            )
            self.assertEqual(action.returncode, 0, action.stderr)
            dependency = run(
                "dep",
                "d2b-action",
                "--blocks",
                "d2b-watch",
                "--json",
            )
            self.assertEqual(dependency.returncode, 0, dependency.stderr)
            self.assertEqual(
                json.loads(dependency.stdout),
                {
                    "blocked_id": "d2b-watch",
                    "blocker_id": "d2b-action",
                    "schema_version": 1,
                    "status": "added",
                    "type": "blocks",
                },
            )

            listed = run(
                "list",
                "--all",
                "--metadata-field",
                "state=repairing",
                "--json",
            )
            self.assertEqual(listed.returncode, 0, listed.stderr)
            listed_payload = json.loads(listed.stdout)
            self.assertIsInstance(listed_payload, list)
            self.assertEqual([item["id"] for item in listed_payload], ["d2b-watch"])

            blocked_close = run(
                "close",
                "d2b-watch",
                "--reason",
                "blocked",
                "--json",
            )
            self.assertNotEqual(blocked_close.returncode, 0)
            self.assertIn("blocked by open issues", blocked_close.stderr)

            close_action = run(
                "close",
                "d2b-action",
                "--reason",
                "done",
                "--json",
            )
            self.assertEqual(close_action.returncode, 0, close_action.stderr)
            self.assertIsInstance(json.loads(close_action.stdout), list)
            close_watch = run(
                "close",
                "d2b-watch",
                "--reason",
                "done",
                "--json",
            )
            self.assertEqual(close_watch.returncode, 0, close_watch.stderr)
            self.assertIsInstance(json.loads(close_watch.stdout), list)

            unknown_commands = (
                (
                    "create",
                    "--id",
                    "d2b-unknown",
                    "--title",
                    "unknown",
                    "--unknown",
                    "flag",
                ),
                ("show", "d2b-watch", "--unknown"),
                ("update", "d2b-watch", "--unknown", "flag"),
                ("list", "--unknown"),
                ("dep", "d2b-action", "--blocks", "d2b-watch", "--unknown"),
                ("close", "d2b-action", "--unknown"),
            )
            for command in unknown_commands:
                result = run(*command)
                self.assertNotEqual(result.returncode, 0, command)
                self.assertIn("unknown flag", result.stderr.lower(), command)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_lock_override_rejects_relative_symlink_and_non_directory(
        self,
    ) -> None:
        scenarios = (
            "relative",
            "symlink",
            "parent-symlink",
            "non-directory",
        )
        for scenario in scenarios:
            root, env = self._fixture(f"lock-{scenario}")
            try:
                if scenario == "relative":
                    env["PR_BABYSIT_LOCK_DIR"] = "relative-locks"
                elif scenario == "symlink":
                    target = root / "lock-target"
                    target.mkdir()
                    link = root / "lock-link"
                    link.symlink_to(target, target_is_directory=True)
                    env["PR_BABYSIT_LOCK_DIR"] = str(link)
                elif scenario == "parent-symlink":
                    target = root / "lock-target"
                    target.mkdir()
                    link = root / "lock-link"
                    link.symlink_to(target, target_is_directory=True)
                    env["PR_BABYSIT_LOCK_DIR"] = str(link / "nested")
                else:
                    path = root / "lock-file"
                    path.write_text("not a directory\n", encoding="utf-8")
                    env["PR_BABYSIT_LOCK_DIR"] = str(path)
                result = self._run(env, "handoff", self._HANDOFF)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(
                    json.loads((root / "calls.json").read_text()),
                    [],
                )
            finally:
                shutil.rmtree(root, ignore_errors=True)

    def test_optional_real_bd_contract(self) -> None:
        bd = shutil.which("bd")
        if bd is None:
            self.skipTest("bd unavailable")
        version = subprocess.run(
            [bd, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertRegex(
            version.stdout,
            rf"^bd version {re.escape(BEADS_VERSION)} \(",
        )
        root = _temporary_root("u3-real-bd-")
        try:
            self.assertEqual(
                subprocess.run(
                    ["git", "init", "-q"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=False,
                ).returncode,
                0,
            )
            beads_root = root / ".beads"
            beads_root.mkdir(mode=0o700)
            (beads_root / "config.yaml").write_text(
                "dolt.local-only: true\n",
                encoding="utf-8",
            )
            initialized = subprocess.run(
                [
                    bd,
                    "init",
                    "--non-interactive",
                    "--skip-hooks",
                    "--skip-agents",
                    "--prefix",
                    "d2b",
                ],
                cwd=root,
                env=os.environ | {"CI": "1"},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)

            def run_bd(*args: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [bd, *args],
                    cwd=root,
                    env=os.environ
                    | {
                        "CI": "1",
                        "BEADS_ACTOR": "contract-test",
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )

            def run_json(*args: str) -> object:
                result = run_bd(*args, "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            created = run_json(
                "create",
                "--id",
                "d2b-watch",
                "--title",
                "watch",
                "--description",
                "watch description",
                "--type",
                "task",
                "--metadata",
                '{"record_kind":"watch","state":"watching"}',
                "--silent",
            )
            self.assertEqual(created["id"], "d2b-watch")
            overwritten = run_json(
                "create",
                "--id",
                "d2b-watch",
                "--title",
                "overwritten",
                "--description",
                "new description",
                "--type",
                "task",
                "--metadata",
                '{"record_kind":"watch","state":"waiting"}',
                "--silent",
            )
            self.assertEqual(overwritten["title"], "overwritten")
            shown = run_json("show", "d2b-watch")
            self.assertEqual(shown[0]["title"], "overwritten")

            updated = run_json(
                "update",
                "d2b-watch",
                "--claim",
                "--set-metadata",
                "state=repairing",
                "--set-metadata",
                "attempts=1",
            )
            self.assertEqual(updated[0]["status"], "in_progress")
            self.assertEqual(updated[0]["assignee"], "contract-test")
            self.assertEqual(updated[0]["metadata"]["state"], "repairing")
            self.assertEqual(updated[0]["metadata"]["attempts"], 1)

            run_json(
                "create",
                "--id",
                "d2b-action",
                "--title",
                "action",
                "--description",
                "action description",
                "--type",
                "task",
                "--metadata",
                '{"record_kind":"action","state":"open"}',
                "--silent",
            )
            dependency = run_json(
                "dep",
                "d2b-action",
                "--blocks",
                "d2b-watch",
            )
            self.assertEqual(
                dependency,
                {
                    "blocked_id": "d2b-watch",
                    "blocker_id": "d2b-action",
                    "schema_version": 1,
                    "status": "added",
                    "type": "blocks",
                },
            )
            listed = run_json(
                "list",
                "--all",
                "--metadata-field",
                "state=repairing",
            )
            self.assertEqual([item["id"] for item in listed], ["d2b-watch"])

            blocked_close = run_bd(
                "close",
                "d2b-watch",
                "--reason",
                "blocked",
                "--json",
            )
            self.assertNotEqual(blocked_close.returncode, 0)
            self.assertIn("blocked by open issues", blocked_close.stderr)
            self.assertEqual(run_json("close", "d2b-action")[0]["status"], "closed")
            self.assertEqual(run_json("close", "d2b-watch")[0]["status"], "closed")

            unknown_commands = (
                (
                    "create",
                    "--id",
                    "d2b-unknown",
                    "--title",
                    "unknown",
                    "--unknown",
                    "flag",
                ),
                ("show", "d2b-watch", "--unknown"),
                ("update", "d2b-watch", "--unknown", "flag"),
                ("list", "--unknown"),
                ("dep", "d2b-action", "--blocks", "d2b-watch", "--unknown"),
                ("close", "d2b-action", "--unknown"),
            )
            for command in unknown_commands:
                result = run_bd(*command)
                self.assertNotEqual(result.returncode, 0, command)
                self.assertIn("unknown flag", result.stderr.lower(), command)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_handoff_rejects_identity_before_any_bead_write(self) -> None:
        root, env = self._fixture("identity")
        try:
            invalid = dict(self._HANDOFF, url=self._HANDOFF["url"] + "?unsafe=1")
            result = self._run(env, "handoff", invalid)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(
                json.loads((root / "calls.json").read_text()),
                [],
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_handoff_rejects_unsafe_hosts_slugs_refs_bases_and_rigs(self) -> None:
        invalid_inputs = (
            {"url": "https://evil.example/octo/example/pull/7"},
            {"owner": "octo/unsafe"},
            {"repository": "bad repo"},
            {"head_ref": "feature..u3"},
            {"head_ref": "feature\u0000u3"},
            {"base_ref": "main"},
            {"rig": "unknown"},
        )
        for index, changes in enumerate(invalid_inputs):
            root, env = self._fixture(f"unsafe-{index}")
            try:
                result = self._run(env, "handoff", dict(self._HANDOFF, **changes))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(
                    json.loads((root / "calls.json").read_text()),
                    [],
                )
            finally:
                shutil.rmtree(root, ignore_errors=True)

    def test_same_pr_number_in_other_repository_and_rig_has_distinct_watch(
        self,
    ) -> None:
        root, env = self._fixture("identity-scope")
        try:
            first = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(first.returncode, 0, first.stderr)
            other_repo = dict(
                self._HANDOFF,
                repository="other",
                head_repository="octo/other",
                url="https://github.com/octo/other/pull/7",
            )
            other_rig = dict(
                self._HANDOFF,
                rig="city-source",
                prefix="city",
                base_ref="main",
                repository="example",
                head_repository="octo/example",
                url="https://github.com/octo/example/pull/7",
            )
            second = self._run(env, "handoff", other_repo)
            third = self._run(env, "handoff", other_rig)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(third.returncode, 0, third.stderr)
            ids = {
                self._json(first)["watch_id"],
                self._json(second)["watch_id"],
                self._json(third)["watch_id"],
            }
            self.assertEqual(len(ids), 3)
            self.assertTrue(all(item.startswith(("d2b-", "city-")) for item in ids))
            self.assertTrue(all(re.fullmatch(r"[a-z0-9-]+", item) for item in ids))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_claim_is_one_writer_and_action_id_hides_fingerprint(self) -> None:
        root, env = self._fixture("claim")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            fingerprint = "Review body\n$(touch should-not-run) with secret log"
            claim = self._run(
                env,
                "claim-action",
                {
                    "watch_id": watch_id,
                    "generation": 1,
                    "head_sha": "a" * 40,
                    "kind": "review",
                    "fingerprint": fingerprint,
                },
            )
            self.assertEqual(claim.returncode, 0, claim.stderr)
            claim_json = self._json(claim)
            self.assertNotIn(fingerprint, (root / "beads.json").read_text())
            self.assertNotIn(fingerprint, (root / "calls.json").read_text())
            other = self._run(
                env,
                "claim-action",
                {
                    "watch_id": watch_id,
                    "generation": 1,
                    "head_sha": "a" * 40,
                    "kind": "ci",
                    "fingerprint": "different",
                },
            )
            self.assertNotEqual(other.returncode, 0)
            same = self._run(
                env,
                "claim-action",
                {
                    "watch_id": watch_id,
                    "generation": 1,
                    "head_sha": "a" * 40,
                    "kind": "review",
                    "fingerprint": fingerprint,
                },
            )
            self.assertEqual(same.returncode, 0, same.stderr)
            self.assertTrue(self._json(same)["reused"])
            self.assertTrue(
                re.fullmatch(
                    r"d2b-[a-z0-9-]+",
                    claim_json["action_id"],
                )
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_claim_requires_generation_before_head_sha(self) -> None:
        root, env = self._fixture("claim-positionals")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            result = subprocess.run(
                [
                    str(PR_BABYSIT_STATE_RUNNER),
                    "claim-action",
                    watch_id,
                    "ci",
                    "check-failed",
                    "a" * 40,
                    "1",
                ],
                cwd=ROOT,
                env=os.environ | env,
                input="{}\n",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(
                self._json(result)["error"]["code"],
                "invalid-request",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_head_change_invalidates_claim_and_increments_generation(self) -> None:
        root, env = self._fixture("head-change")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            claim = self._run(
                env,
                "claim-action",
                {
                    "watch_id": watch_id,
                    "generation": 1,
                    "head_sha": "a" * 40,
                    "kind": "ci",
                    "fingerprint": "check-failed",
                },
            )
            self.assertEqual(claim.returncode, 0, claim.stderr)
            moved = dict(
                self._HANDOFF,
                head_sha="b" * 40,
                current_sha="b" * 40,
            )
            refreshed = self._run(env, "handoff", moved)
            self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
            state = self._json(self._run(env, "show", {"watch_id": watch_id}))
            self.assertEqual(state["metadata"]["generation"], "2")
            self.assertEqual(state["metadata"]["claim_status"], "none")
            self.assertEqual(state["metadata"]["head_sha"], "b" * 40)
            records = json.loads((root / "beads.json").read_text())
            actions = [
                record
                for record in records
                if record["id"] != watch_id
            ]
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["metadata"]["claim_status"], "stale")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_transition_enforces_the_watch_state_machine(self) -> None:
        root, env = self._fixture("transitions")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            waiting = self._run(
                env,
                "transition",
                {"watch_id": watch_id, "to": "waiting"},
            )
            self.assertEqual(waiting.returncode, 0, waiting.stderr)
            illegal = self._run(
                env,
                "transition",
                {"watch_id": watch_id, "to": "exhausted"},
            )
            self.assertNotEqual(illegal.returncode, 0)
            watching = self._run(
                env,
                "transition",
                {"watch_id": watch_id, "to": "watching"},
            )
            self.assertEqual(watching.returncode, 0, watching.stderr)
            repairing = self._run(
                env,
                "transition",
                {"watch_id": watch_id, "to": "repairing"},
            )
            self.assertEqual(repairing.returncode, 0, repairing.stderr)
            exhausted = self._run(
                env,
                "transition",
                {
                    "watch_id": watch_id,
                    "to": "exhausted",
                    "reason": "retry-limit",
                },
            )
            self.assertEqual(exhausted.returncode, 0, exhausted.stderr)
            state = self._json(self._run(env, "show", {"watch_id": watch_id}))
            self.assertEqual(state["metadata"]["state"], "exhausted")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_ambiguous_repair_confirmation_blocks_without_retry(self) -> None:
        root, env = self._fixture("ambiguous")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            claim = self._run(
                env,
                "claim-action",
                {
                    "watch_id": watch_id,
                    "generation": 1,
                    "head_sha": "a" * 40,
                    "kind": "ci",
                    "fingerprint": "check-failed",
                },
            )
            self.assertEqual(claim.returncode, 0, claim.stderr)
            action_id = self._json(claim)["action_id"]
            recorded = self._run(
                env,
                "record-repair-result",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "expected_old_sha": "a" * 40,
                    "pushed_sha": "b" * 40,
                    "validation_status": "passed",
                },
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            confirmed = self._run(
                env,
                "confirm-action",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "current_sha": "a" * 40,
                },
            )
            self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
            result = self._json(confirmed)
            self.assertEqual(result["state"], "blocked")
            self.assertEqual(result["terminal_reason"], "ambiguous-outcome")
            retry = self._run(
                env,
                "claim-action",
                {
                    "watch_id": watch_id,
                    "generation": 1,
                    "head_sha": "a" * 40,
                    "kind": "ci",
                    "fingerprint": "check-failed",
                },
            )
            self.assertNotEqual(retry.returncode, 0)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_confirmed_repair_advances_head_and_generation(self) -> None:
        root, env = self._fixture("confirm")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            claim = self._run(
                env,
                "claim-action",
                {
                    "watch_id": watch_id,
                    "generation": 1,
                    "head_sha": "a" * 40,
                    "kind": "ci",
                    "fingerprint": "check-failed",
                },
            )
            self.assertEqual(claim.returncode, 0, claim.stderr)
            action_id = self._json(claim)["action_id"]
            recorded = self._run(
                env,
                "record-repair-result",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "expected_old_sha": "a" * 40,
                    "pushed_sha": "b" * 40,
                    "validation_status": "passed",
                },
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            confirmed = self._run(
                env,
                "confirm-action",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "current_sha": "b" * 40,
                    "observed_at": "2026-08-29T19:10:00Z",
                },
            )
            self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
            state = self._json(confirmed)
            self.assertEqual(state["state"], "watching")
            self.assertEqual(state["generation"], 2)
            self.assertEqual(state["metadata"]["head_sha"], "b" * 40)
            self.assertEqual(state["metadata"]["claim_status"], "none")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_terminal_absorbs_rearm_and_nonterminal_states_can_rearm_safely(
        self,
    ) -> None:
        root, env = self._fixture("rearm")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            blocked = self._run(
                env,
                "transition",
                {
                    "watch_id": watch_id,
                    "to": "blocked",
                    "reason": "external-authority",
                },
            )
            self.assertEqual(blocked.returncode, 0, blocked.stderr)
            no_rearm = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(no_rearm.returncode, 0, no_rearm.stderr)
            self.assertEqual(self._json(no_rearm)["state"], "blocked")
            rearmed = self._run(
                env,
                "handoff",
                dict(self._HANDOFF, rearm=True),
            )
            self.assertEqual(rearmed.returncode, 0, rearmed.stderr)
            self.assertEqual(self._json(rearmed)["state"], "watching")
            terminal = self._run(
                env,
                "transition",
                {
                    "watch_id": watch_id,
                    "to": "terminal",
                    "reason": "closed",
                },
            )
            self.assertEqual(terminal.returncode, 0, terminal.stderr)
            absorbed = self._run(
                env,
                "handoff",
                dict(
                    self._HANDOFF,
                    current_sha="c" * 40,
                    head_sha="c" * 40,
                    rearm=True,
                    pr_state="CLOSED",
                ),
            )
            self.assertEqual(absorbed.returncode, 0, absorbed.stderr)
            self.assertTrue(self._json(absorbed)["absorbed"])
            state = self._json(self._run(env, "show", {"watch_id": watch_id}))
            self.assertEqual(state["metadata"]["state"], "terminal")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_list_due_returns_only_due_nonterminal_watches_deterministically(
        self,
    ) -> None:
        root, env = self._fixture("due")
        try:
            first = dict(self._HANDOFF, next_snapshot_at="2026-08-29T18:00:00Z")
            second = dict(
                self._HANDOFF,
                repository="later",
                head_repository="octo/later",
                url="https://github.com/octo/later/pull/7",
                next_snapshot_at="2026-08-29T20:00:00Z",
            )
            self.assertEqual(self._run(env, "handoff", first).returncode, 0)
            self.assertEqual(self._run(env, "handoff", second).returncode, 0)
            result = self._run(
                env,
                "list-due",
                {"rig": "d2b", "now": "2026-08-29T19:00:00Z"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            due = self._json(result)
            self.assertEqual(len(due["watches"]), 1)
            self.assertEqual(
                due["watches"][0]["metadata"]["next_snapshot_at"],
                "2026-08-29T18:00:00Z",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_list_due_filters_open_records_before_slicing(self) -> None:
        root, env = self._fixture("due-pagination")
        try:
            first = dict(
                self._HANDOFF,
                next_snapshot_at="2026-08-29T18:00:00Z",
            )
            second = dict(
                self._HANDOFF,
                repository="later",
                head_repository="octo/later",
                url="https://github.com/octo/later/pull/7",
                next_snapshot_at="2026-08-29T18:30:00Z",
            )
            self.assertEqual(self._run(env, "handoff", first).returncode, 0)
            second_result = self._run(env, "handoff", second)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            second_watch_id = self._json(second_result)["watch_id"]
            records = json.loads((root / "beads.json").read_text())
            first_record = next(
                record
                for record in records
                if record["metadata"]["repository"] == "example"
            )
            first_record["id"] = "a-closed"
            first_record["status"] = "closed"
            first_record["metadata"]["state"] = "terminal"
            (root / "beads.json").write_text(
                json.dumps(records, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )
            result = self._run(
                env,
                "list-due",
                {
                    "rig": "d2b",
                    "now": "2026-08-29T19:00:00Z",
                    "limit": 1,
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            due = self._json(result)
            self.assertEqual(
                [item["watch_id"] for item in due["watches"]],
                [second_watch_id],
            )
            calls = json.loads((root / "calls.json").read_text())
            list_call = next(
                call["argv"]
                for call in calls
                if call["argv"] and call["argv"][0] == "list"
            )
            self.assertNotIn("--all", list_call)
            self.assertEqual(
                list_call[list_call.index("--status") + 1],
                "open",
            )
            self.assertEqual(
                list_call[list_call.index("--limit") + 1],
                "100",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_state_json_is_canonical_for_same_verified_input(self) -> None:
        outputs = []
        for name in ("deterministic-a", "deterministic-b"):
            root, env = self._fixture(name)
            try:
                result = self._run(env, "handoff", self._HANDOFF)
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append(result.stdout)
            finally:
                shutil.rmtree(root, ignore_errors=True)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(
            outputs[0],
            json.dumps(
                json.loads(outputs[0]),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
        )


class PrBabysitCheckpointTests(unittest.TestCase):
    _HANDOFF = dict(PrBabysitStateTests._HANDOFF)

    def _fixture(self, name: str) -> tuple[pathlib.Path, dict[str, str]]:
        root = _temporary_root(f"u5-checkpoint-{name}-")
        fake = root / "fake-beads"
        fake.write_text(
            PrBabysitStateTests._fake_beads_script(),
            encoding="utf-8",
        )
        fake.chmod(0o755)
        (root / "beads.json").write_text("[]\n", encoding="utf-8")
        (root / "calls.json").write_text("[]\n", encoding="utf-8")
        return root, {
            "PR_BABYSIT_BEADS_BIN": str(fake),
            "FAKE_BEADS_ROOT": str(root),
            "PR_BABYSIT_BEADS_CWD": str(root),
            "GC_RIG_ROOT": str(root),
            "PR_BABYSIT_ALLOWED_HOSTS": "github.com",
        }

    def _run(
        self,
        env: dict[str, str],
        action: str,
        payload: dict[str, object] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PR_BABYSIT_STATE_RUNNER), action],
            cwd=ROOT,
            env=os.environ | env,
            input=json.dumps(payload or {}),
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _json(result: subprocess.CompletedProcess[str]) -> dict:
        if not result.stdout:
            raise AssertionError(result.stderr)
        return json.loads(result.stdout)

    def _watch_id(
        self,
        env: dict[str, str],
        payload: dict[str, object] | None = None,
    ) -> str:
        handoff = self._run(env, "handoff", payload or self._HANDOFF)
        self.assertEqual(handoff.returncode, 0, handoff.stderr)
        return self._json(handoff)["watch_id"]

    def test_checkpoint_persists_snapshot_and_one_legal_transition(self) -> None:
        root, env = self._fixture("legal")
        try:
            watch_id = self._watch_id(env)
            checkpoint = self._run(
                env,
                "checkpoint",
                {
                    "watch_id": watch_id,
                    "expected_generation": 1,
                    "expected_head_sha": "a" * 40,
                    "observed_head_sha": "a" * 40,
                    "observed_at": "2026-08-29T19:01:00Z",
                    "next_snapshot_at": "2026-08-29T19:02:00Z",
                    "to": "waiting",
                },
            )
            self.assertEqual(checkpoint.returncode, 0, checkpoint.stderr)
            state = self._json(checkpoint)
            self.assertEqual(state["state"], "waiting")
            self.assertEqual(state["metadata"]["last_snapshot_at"], "2026-08-29T19:01:00Z")
            self.assertEqual(state["metadata"]["next_snapshot_at"], "2026-08-29T19:02:00Z")
            self.assertEqual(state["metadata"]["generation"], "1")

            resumed = self._run(
                env,
                "checkpoint",
                {
                    "watch_id": watch_id,
                    "expected_generation": 1,
                    "expected_head_sha": "a" * 40,
                    "observed_head_sha": "a" * 40,
                    "observed_at": "2026-08-29T19:02:00Z",
                    "next_snapshot_at": "2026-08-29T19:03:00Z",
                    "to": "watching",
                },
            )
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(self._json(resumed)["state"], "watching")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_checkpoint_rejects_stale_generation_or_head_without_writing(self) -> None:
        root, env = self._fixture("stale")
        try:
            watch_id = self._watch_id(env)
            before = (root / "beads.json").read_bytes()
            for payload in (
                {
                    "expected_generation": 2,
                    "expected_head_sha": "a" * 40,
                    "observed_head_sha": "a" * 40,
                },
                {
                    "expected_generation": 1,
                    "expected_head_sha": "b" * 40,
                    "observed_head_sha": "a" * 40,
                },
            ):
                result = self._run(
                    env,
                    "checkpoint",
                    {
                        "watch_id": watch_id,
                        **payload,
                        "observed_at": "2026-08-29T19:01:00Z",
                        "next_snapshot_at": "2026-08-29T19:02:00Z",
                        "to": "waiting",
                    },
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((root / "beads.json").read_bytes(), before)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_checkpoint_reconciles_head_and_invalidates_claim(self) -> None:
        root, env = self._fixture("head")
        try:
            watch_id = self._watch_id(env)
            claim = self._run(
                env,
                "claim-action",
                {
                    "watch_id": watch_id,
                    "generation": 1,
                    "head_sha": "a" * 40,
                    "kind": "ci",
                    "fingerprint": "check-failed",
                },
            )
            self.assertEqual(claim.returncode, 0, claim.stderr)
            checkpoint = self._run(
                env,
                "checkpoint",
                {
                    "watch_id": watch_id,
                    "expected_generation": 1,
                    "expected_head_sha": "a" * 40,
                    "observed_head_sha": "b" * 40,
                    "observed_at": "2026-08-29T19:01:00Z",
                    "next_snapshot_at": "2026-08-29T19:02:00Z",
                    "to": "watching",
                },
            )
            self.assertEqual(checkpoint.returncode, 0, checkpoint.stderr)
            state = self._json(checkpoint)
            self.assertEqual(state["state"], "watching")
            self.assertEqual(state["generation"], 2)
            self.assertEqual(state["metadata"]["head_sha"], "b" * 40)
            self.assertEqual(state["metadata"]["claim_status"], "none")
            records = json.loads((root / "beads.json").read_text(encoding="utf-8"))
            action = next(record for record in records if record["id"] != watch_id)
            self.assertEqual(action["metadata"]["claim_status"], "stale")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_checkpoint_exhausts_active_time_and_backstop(self) -> None:
        for name, observed_at, reason in (
            (
                "active-budget",
                "2026-08-29T08:00:00Z",
                "time-budget-exhausted",
            ),
            (
                "backstop",
                "2026-09-01T19:00:00Z",
                "backstop-expired",
            ),
        ):
            with self.subTest(name=name):
                root, env = self._fixture(name)
                try:
                    handoff_payload = self._HANDOFF
                    if name == "active-budget":
                        handoff_payload = dict(
                            self._HANDOFF,
                            active_since="2026-08-29T00:00:00Z",
                            backstop_at="2026-09-01T00:00:00Z",
                        )
                    watch_id = self._watch_id(env, handoff_payload)
                    result = self._run(
                        env,
                        "checkpoint",
                        {
                            "watch_id": watch_id,
                            "expected_generation": 1,
                            "expected_head_sha": "a" * 40,
                            "observed_head_sha": "a" * 40,
                            "observed_at": observed_at,
                            "next_snapshot_at": "2026-09-02T00:00:00Z",
                            "to": "watching",
                        },
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    state = self._json(result)
                    self.assertEqual(state["state"], "exhausted")
                    self.assertEqual(state["terminal_reason"], reason)
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def test_checkpoint_terminal_absorbs_later_requests(self) -> None:
        root, env = self._fixture("terminal")
        try:
            watch_id = self._watch_id(env)
            closed = self._run(
                env,
                "checkpoint",
                {
                    "watch_id": watch_id,
                    "expected_generation": 1,
                    "expected_head_sha": "a" * 40,
                    "observed_head_sha": "a" * 40,
                    "pr_state": "CLOSED",
                    "observed_at": "2026-08-29T19:01:00Z",
                    "next_snapshot_at": "2026-08-29T19:02:00Z",
                },
            )
            self.assertEqual(closed.returncode, 0, closed.stderr)
            self.assertEqual(self._json(closed)["state"], "terminal")
            absorbed = self._run(
                env,
                "checkpoint",
                {
                    "watch_id": watch_id,
                    "expected_generation": 1,
                    "expected_head_sha": "a" * 40,
                    "observed_head_sha": "a" * 40,
                    "observed_at": "2026-08-29T19:03:00Z",
                    "next_snapshot_at": "2026-08-29T19:04:00Z",
                    "to": "watching",
                },
            )
            self.assertEqual(absorbed.returncode, 0, absorbed.stderr)
            self.assertTrue(self._json(absorbed)["absorbed"])
            self.assertEqual(self._json(self._run(
                env,
                "show",
                {"watch_id": watch_id},
            ))["metadata"]["state"], "terminal")
        finally:
            shutil.rmtree(root, ignore_errors=True)


class PrBabysitSweepTests(unittest.TestCase):
    _HANDOFF = dict(PrBabysitStateTests._HANDOFF)
    _SWEEP = PR_BABYSIT_ROOT / "assets" / "scripts" / "pr-babysit-sweep.sh"

    @staticmethod
    def _fake_gc_script() -> str:
        return r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["FAKE_GC_ROOT"])
path = root / "gc-calls.json"
calls = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
calls.append(sys.argv[1:])
path.write_text(
    json.dumps(calls, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
if os.environ.get("FAKE_GC_FAIL") == "1":
    print("route failed", file=sys.stderr)
    raise SystemExit(1)
"""

    def _fixture(self, name: str) -> tuple[pathlib.Path, dict[str, str]]:
        root = _temporary_root(f"u5-sweep-{name}-")
        beads = root / "fake-beads"
        beads.write_text(
            PrBabysitStateTests._fake_beads_script(),
            encoding="utf-8",
        )
        beads.chmod(0o755)
        gc = root / "fake-gc"
        gc.write_text(self._fake_gc_script(), encoding="utf-8")
        gc.chmod(0o755)
        (root / "beads.json").write_text("[]\n", encoding="utf-8")
        (root / "calls.json").write_text("[]\n", encoding="utf-8")
        (root / "gc-calls.json").write_text("[]\n", encoding="utf-8")
        return root, {
            "PR_BABYSIT_BEADS_BIN": str(beads),
            "FAKE_BEADS_ROOT": str(root),
            "PR_BABYSIT_BEADS_CWD": str(root),
            "GC_RIG_ROOT": str(root),
            "GC_RIG": "d2b",
            "GC_BIN": str(gc),
            "FAKE_GC_ROOT": str(root),
            "PR_BABYSIT_ALLOWED_HOSTS": "github.com",
            "PR_BABYSIT_NOW": "2026-08-29T19:00:00Z",
        }

    def _run_state(
        self,
        env: dict[str, str],
        action: str,
        payload: dict[str, object],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PR_BABYSIT_STATE_RUNNER), action],
            cwd=ROOT,
            env=os.environ | env,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _json(result: subprocess.CompletedProcess[str]) -> dict:
        if not result.stdout:
            raise AssertionError(result.stderr)
        return json.loads(result.stdout)

    def _handoff(
        self,
        env: dict[str, str],
        payload: dict[str, object],
    ) -> str:
        result = self._run_state(env, "handoff", payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self._json(result)["watch_id"]

    def _run_sweep(
        self,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self._SWEEP)],
            cwd=ROOT,
            env=os.environ | env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_state_sweep_validates_rig_and_limit(self) -> None:
        root, env = self._fixture("validation")
        try:
            for payload in (
                {"rig": "unknown", "limit": 32},
                {"rig": "d2b", "limit": 0},
                {"rig": "d2b", "limit": 101},
            ):
                with self.subTest(payload=payload):
                    result = self._run_state(env, "sweep", payload)
                    self.assertNotEqual(result.returncode, 0)
            result = self._run_state(
                env,
                "sweep",
                {"rig": "d2b", "limit": 32},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                self._json(result),
                {
                    "action": "sweep",
                    "ok": True,
                    "rig": "d2b",
                    "routed": 0,
                },
            )
            self.assertEqual(
                json.loads((root / "gc-calls.json").read_text(encoding="utf-8")),
                [],
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_order_uses_pinned_cooldown_exec_shape(self) -> None:
        order = tomllib.loads(
            (
                PR_BABYSIT_ROOT
                / "orders"
                / "pr-babysit-sweep.toml"
            ).read_text(encoding="utf-8")
        )["order"]
        self.assertEqual(order["trigger"], "cooldown")
        self.assertEqual(order["interval"], "1m")
        self.assertEqual(
            order["exec"],
            "$PACK_DIR/assets/scripts/pr-babysit-sweep.sh",
        )
        self.assertTrue(self._SWEEP.stat().st_mode & 0o111)

    def test_sweep_routes_due_watches_to_binding_qualified_target(self) -> None:
        root, env = self._fixture("routes")
        try:
            first = self._handoff(
                env,
                dict(self._HANDOFF, next_snapshot_at="2026-08-29T18:00:00Z"),
            )
            second = self._handoff(
                env,
                dict(
                    self._HANDOFF,
                    repository="later",
                    head_repository="octo/later",
                    url="https://github.com/octo/later/pull/7",
                    next_snapshot_at="2026-08-29T18:30:00Z",
                ),
            )
            waiting = self._run_state(
                env,
                "transition",
                {"watch_id": second, "to": "waiting"},
            )
            self.assertEqual(waiting.returncode, 0, waiting.stderr)
            result = self._run_sweep(env)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = self._json(result)
            self.assertEqual(
                summary,
                {
                    "action": "sweep",
                    "ok": True,
                    "rig": "d2b",
                    "routed": 2,
                },
            )
            calls = json.loads((root / "gc-calls.json").read_text(encoding="utf-8"))
            self.assertEqual(
                calls,
                [
                    [
                        "sling",
                        "--nudge",
                        "d2b/pr-babysit.pr-babysitter",
                        first,
                        "--no-formula",
                        "--json",
                    ],
                    [
                        "sling",
                        "--nudge",
                        "d2b/pr-babysit.pr-babysitter",
                        second,
                        "--no-formula",
                        "--json",
                    ],
                ],
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_sweep_skips_stopped_and_repairing_watches(self) -> None:
        root, env = self._fixture("skip")
        try:
            states = ("repairing", "merge-ready", "blocked", "exhausted", "terminal")
            for index, state in enumerate(states):
                payload = dict(
                    self._HANDOFF,
                    repository=f"skip-{index}",
                    head_repository=f"octo/skip-{index}",
                    url=f"https://github.com/octo/skip-{index}/pull/7",
                    next_snapshot_at="2026-08-29T18:00:00Z",
                )
                watch_id = self._handoff(env, payload)
                if state == "repairing":
                    transition = self._run_state(
                        env,
                        "claim-action",
                        {
                            "watch_id": watch_id,
                            "generation": 1,
                            "head_sha": "a" * 40,
                            "kind": "ci",
                            "fingerprint": "same",
                        },
                    )
                elif state == "exhausted":
                    claimed = self._run_state(
                        env,
                        "claim-action",
                        {
                            "watch_id": watch_id,
                            "generation": 1,
                            "head_sha": "a" * 40,
                            "kind": "ci",
                            "fingerprint": "same",
                        },
                    )
                    self.assertEqual(claimed.returncode, 0, claimed.stderr)
                    transition = self._run_state(
                        env,
                        "transition",
                        {
                            "watch_id": watch_id,
                            "to": state,
                            "reason": "test-stop",
                        },
                    )
                else:
                    transition = self._run_state(
                        env,
                        "transition",
                        {
                            "watch_id": watch_id,
                            "to": state,
                            **({"reason": "test-stop"} if state == "terminal" else {}),
                        },
                    )
                self.assertEqual(transition.returncode, 0, transition.stderr)
            result = self._run_sweep(env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads((root / "gc-calls.json").read_text(encoding="utf-8")),
                [],
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_sweep_fails_nonzero_on_malformed_state_and_route_failure(self) -> None:
        root, env = self._fixture("failures")
        try:
            watch_id = self._handoff(
                env,
                dict(self._HANDOFF, next_snapshot_at="2026-08-29T18:00:00Z"),
            )
            records = json.loads((root / "beads.json").read_text(encoding="utf-8"))
            records[0]["metadata"]["state"] = "not-a-state"
            (root / "beads.json").write_text(
                json.dumps(records, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            malformed = self._run_sweep(env)
            self.assertNotEqual(malformed.returncode, 0)

            records[0]["metadata"]["state"] = "watching"
            (root / "beads.json").write_text(
                json.dumps(records, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            failed_route = self._run_sweep(env | {"FAKE_GC_FAIL": "1"})
            self.assertNotEqual(failed_route.returncode, 0)
            self.assertEqual(
                self._json(
                    self._run_state(
                        env,
                        "show",
                        {"watch_id": watch_id},
                    )
                )["metadata"]["state"],
                "watching",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_sweep_has_no_watcher_loop_or_branch_update_path(self) -> None:
        order = (
            PR_BABYSIT_ROOT / "orders" / "pr-babysit-sweep.toml"
        ).read_text(encoding="utf-8")
        script = self._SWEEP.read_text(encoding="utf-8")
        text = "\n".join([
            (
                PR_BABYSIT_ROOT / "skills" / "pr-babysit" / "SKILL.md"
            ).read_text(encoding="utf-8"),
            (
                PR_BABYSIT_ROOT
                / "skills"
                / "pr-babysit"
                / "references"
                / "tick.md"
            ).read_text(encoding="utf-8"),
            (
                PR_BABYSIT_ROOT
                / "skills"
                / "pr-babysit"
                / "references"
                / "envelope.md"
            ).read_text(encoding="utf-8"),
            (
                PR_BABYSIT_ROOT
                / "skills"
                / "pr-babysit"
                / "references"
                / "settle.md"
            ).read_text(encoding="utf-8"),
        ]).lower()
        self.assertIn("exec \"$state_runner\" sweep", script)
        self.assertNotIn("list-due", script)
        self.assertNotIn("while true", script)
        self.assertNotIn("sleep ", script)
        for marker in (
            "pr-snapshot watch",
            "update-branch",
            "gh pr merge",
            "git merge",
            "git rebase",
            "force-push",
        ):
            self.assertNotIn(marker, order.lower() + "\n" + script.lower() + "\n" + text)


class PrBabysitPublicationHandoffTests(unittest.TestCase):
    _D2B_PUBLICATION = {
        "id": "publication-1",
        "status": "open",
        "assignee": "",
        "metadata": {
            "record_kind": "publication",
            "rig": "d2b",
            "github_host": "github.com",
            "owner": "octo",
            "repository": "example",
            "base_ref": "v3",
            "merge_strategy": "pr",
        },
    }
    _D2B_GITHUB = {
        "number": 7,
        "url": "https://github.com/octo/example/pull/7",
        "state": "OPEN",
        "isDraft": False,
        "isCrossRepository": False,
        "headRepository": {"nameWithOwner": "octo/example"},
        "headRepositoryOwner": {"login": "octo"},
        "baseRefName": "v3",
        "headRefName": "feature/u4",
        "headRefOid": "b" * 40,
        "repository": {"nameWithOwner": "octo/example"},
    }

    @staticmethod
    def _fake_gh_script() -> str:
        return r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["FAKE_PUBLICATION_ROOT"])
calls_path = root / "gh-calls.json"
calls = []
if calls_path.exists():
    calls = json.loads(calls_path.read_text(encoding="utf-8"))
calls.append(sys.argv[1:])
calls_path.write_text(
    json.dumps(calls, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
if os.environ.get("FAKE_GH_FAIL") == "1":
    print("pull request not found", file=sys.stderr)
    raise SystemExit(1)
payload = json.loads(
    (root / "github.json").read_text(encoding="utf-8")
)
print(json.dumps(payload, sort_keys=True))
"""

    @staticmethod
    def _fake_gc_script() -> str:
        return r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["FAKE_PUBLICATION_ROOT"])
calls_path = root / "gc-calls.json"
calls = []
if calls_path.exists():
    calls = json.loads(calls_path.read_text(encoding="utf-8"))
calls.append(sys.argv[1:])
calls_path.write_text(
    json.dumps(calls, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
if os.environ.get("FAKE_GC_FAIL") == "1":
    print("sling failed", file=sys.stderr)
    raise SystemExit(1)
print(json.dumps({"ok": True}))
"""

    def _fixture(
        self,
        name: str,
        *,
        publication: dict | None = None,
        github: dict | None = None,
    ) -> tuple[pathlib.Path, dict[str, str]]:
        root = _temporary_root(f"u4-publication-{name}-")
        fake_beads = root / "fake-beads"
        fake_beads.write_text(
            PrBabysitStateTests._fake_beads_script(),
            encoding="utf-8",
        )
        fake_beads.chmod(0o755)
        fake_gh = root / "fake-gh"
        fake_gh.write_text(self._fake_gh_script(), encoding="utf-8")
        fake_gh.chmod(0o755)
        fake_gc = root / "fake-gc"
        fake_gc.write_text(self._fake_gc_script(), encoding="utf-8")
        fake_gc.chmod(0o755)
        (root / "beads.json").write_text(
            json.dumps(
                [publication or self._D2B_PUBLICATION],
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "calls.json").write_text("[]\n", encoding="utf-8")
        (root / "github.json").write_text(
            json.dumps(github or self._D2B_GITHUB, sort_keys=True),
            encoding="utf-8",
        )
        (root / "gh-calls.json").write_text("[]\n", encoding="utf-8")
        (root / "gc-calls.json").write_text("[]\n", encoding="utf-8")
        return root, {
            "PR_BABYSIT_BEADS_BIN": str(fake_beads),
            "FAKE_BEADS_ROOT": str(root),
            "PR_BABYSIT_BEADS_CWD": str(root),
            "GC_RIG_ROOT": str(root),
            "PR_BABYSIT_ALLOWED_HOSTS": "github.com,github.example",
            "PR_BABYSIT_GH_BIN": str(fake_gh),
            "PR_BABYSIT_GC_BIN": str(fake_gc),
            "FAKE_PUBLICATION_ROOT": str(root),
            "PR_BABYSIT_NOW": "2026-08-29T19:00:00Z",
        }

    def _run(
        self,
        env: dict[str, str],
        action: str,
        payload: dict[str, object] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PR_BABYSIT_STATE_RUNNER), action],
            cwd=ROOT,
            env=os.environ | env,
            input=json.dumps(payload or {}),
            capture_output=True,
            text=True,
            check=False,
        )

    def _payload(
        self,
        *,
        rig: str = "d2b",
        publication_id: str = "publication-1",
        url: str | None = "https://github.com/octo/example/pull/7",
        pr_number: int | None = 7,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "rig": rig,
            "publication_bead_id": publication_id,
        }
        if url is not None:
            payload["url"] = url
        if pr_number is not None:
            payload["pr_number"] = pr_number
        return payload

    @staticmethod
    def _json(result: subprocess.CompletedProcess[str]) -> dict:
        if not result.stdout:
            raise AssertionError(result.stderr)
        return json.loads(result.stdout)

    @staticmethod
    def _bead_calls(root: pathlib.Path) -> list[dict]:
        return json.loads((root / "calls.json").read_text(encoding="utf-8"))

    def test_shadow_retains_official_pr_creation_and_requires_verification(self):
        asset = PUBLISH_OPEN_PR_ASSET.read_text(encoding="utf-8")
        self.assertTrue(asset.startswith(OFFICIAL_OPEN_PR_ASSET))
        self.assertIn("gascity/formulas/publish.formula.toml", asset)
        handoff = asset.index("publication-handoff")
        verify = asset.index("verify-handoff")
        self.assertLess(handoff, verify)
        self.assertIn("immediately before closing", asset.lower())
        self.assertNotIn(
            "template-fragments/pr-babysit-publication.template.md",
            asset,
        )
        lowered = asset.lower()
        for marker in (
            "never merge",
            "never force-push",
            "never rebase",
            "pull-request-only",
        ):
            self.assertIn(marker, lowered)

    def test_verified_d2b_handoff_queries_github_and_routes_exact_target(self):
        root, env = self._fixture("d2b")
        try:
            result = self._run(
                env,
                "publication-handoff",
                self._payload(),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = self._json(result)
            self.assertTrue(receipt["verified"])
            self.assertEqual(receipt["rig"], "d2b")
            self.assertEqual(
                receipt["target"],
                "d2b/pr-babysit.pr-babysitter",
            )
            self.assertTrue(receipt["watch_id"].startswith("d2b-pr-"))

            gh_calls = json.loads(
                (root / "gh-calls.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(gh_calls), 1)
            self.assertEqual(gh_calls[0][:3], ["pr", "view", "7"])
            self.assertIn("--repo", gh_calls[0])
            requested_fields = gh_calls[0][gh_calls[0].index("--json") + 1]
            for field in (
                "isCrossRepository",
                "headRepository",
                "headRepositoryOwner",
            ):
                self.assertIn(field, requested_fields)

            gc_calls = json.loads(
                (root / "gc-calls.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                gc_calls,
                [[
                    "sling",
                    "--nudge",
                    "d2b/pr-babysit.pr-babysitter",
                    receipt["watch_id"],
                    "--no-formula",
                    "--json",
                ]],
            )
            records = json.loads((root / "beads.json").read_text(encoding="utf-8"))
            watch = next(
                record
                for record in records
                if record["metadata"].get("record_kind") == "watch"
            )
            self.assertEqual(watch["metadata"]["head_repository"], "octo/example")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_verified_city_source_handoff_targets_main_and_city_binding(self):
        publication = {
            "id": "publication-city",
            "status": "open",
            "assignee": "",
            "metadata": {
                "record_kind": "publication",
                "rig": "city-source",
                "github_host": "github.com",
                "owner": "octo",
                "repository": "gascity",
                "base_ref": "main",
                "merge_strategy": "pr",
            },
        }
        github = dict(
            self._D2B_GITHUB,
            number=8,
            url="https://github.com/octo/gascity/pull/8",
            baseRefName="main",
            headRefName="feature/city-source",
            repository={"nameWithOwner": "octo/gascity"},
            headRepository={"nameWithOwner": "octo/gascity"},
            headRepositoryOwner={"login": "octo"},
        )
        root, env = self._fixture(
            "city-source",
            publication=publication,
            github=github,
        )
        try:
            result = self._run(
                env,
                "publication-handoff",
                self._payload(
                    rig="city-source",
                    publication_id="publication-city",
                    url=github["url"],
                    pr_number=8,
                ),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = self._json(result)
            self.assertEqual(receipt["target"], "city-source/pr-babysit.pr-babysitter")
            self.assertTrue(receipt["watch_id"].startswith("city-pr-"))
            gc_calls = json.loads(
                (root / "gc-calls.json").read_text(encoding="utf-8")
            )
            self.assertEqual(gc_calls[0][2], "city-source/pr-babysit.pr-babysitter")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_invalid_publication_identity_writes_no_beads_or_route(self):
        cases = (
            ("draft", dict(self._D2B_GITHUB, isDraft=True), {}),
            ("wrong-base", dict(self._D2B_GITHUB, baseRefName="main"), {}),
            (
                "wrong-repository",
                dict(
                    self._D2B_GITHUB,
                    url="https://github.com/octo/other/pull/7",
                    repository={"nameWithOwner": "octo/other"},
                ),
                {},
            ),
            ("absent-pr", self._D2B_GITHUB, {"FAKE_GH_FAIL": "1"}),
            (
                "malformed-head",
                dict(self._D2B_GITHUB, headRefOid="not-a-sha"),
                {},
            ),
            (
                "cross-repository",
                dict(
                    self._D2B_GITHUB,
                    isCrossRepository=True,
                    headRepository={"nameWithOwner": "fork/example"},
                    headRepositoryOwner={"login": "fork"},
                ),
                {},
            ),
            (
                "mismatched-head-repository",
                dict(
                    self._D2B_GITHUB,
                    headRepository={"nameWithOwner": "fork/example"},
                    headRepositoryOwner={"login": "fork"},
                ),
                {},
            ),
            (
                "missing-cross-repository-status",
                {
                    key: value
                    for key, value in self._D2B_GITHUB.items()
                    if key != "isCrossRepository"
                },
                {},
            ),
            (
                "missing-head-repository",
                {
                    key: value
                    for key, value in self._D2B_GITHUB.items()
                    if key != "headRepository"
                },
                {},
            ),
            (
                "missing-head-repository-owner",
                {
                    key: value
                    for key, value in self._D2B_GITHUB.items()
                    if key != "headRepositoryOwner"
                },
                {},
            ),
            (
                "head-repository-without-name-with-owner",
                dict(
                    self._D2B_GITHUB,
                    headRepository={
                        "name": "example",
                        "owner": {"login": "octo"},
                    },
                ),
                {},
            ),
        )
        for name, github, extra_env in cases:
            with self.subTest(name=name):
                root, env = self._fixture(name, github=github)
                try:
                    result = self._run(
                        env | extra_env,
                        "publication-handoff",
                        self._payload(),
                    )
                    self.assertNotEqual(result.returncode, 0)
                    calls = self._bead_calls(root)
                    self.assertFalse(
                        [
                            call
                            for call in calls
                            if call["argv"]
                            and call["argv"][0] in {"create", "update", "close"}
                        ]
                    )
                    self.assertEqual(
                        json.loads(
                            (root / "gc-calls.json").read_text(
                                encoding="utf-8"
                            )
                        ),
                        [],
                    )
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def test_route_failure_blocks_watch_without_receipt(self):
        root, env = self._fixture("route-failure")
        try:
            result = self._run(
                env | {"FAKE_GC_FAIL": "1"},
                "publication-handoff",
                self._payload(),
            )
            self.assertNotEqual(result.returncode, 0)
            records = json.loads((root / "beads.json").read_text(encoding="utf-8"))
            publication = next(
                record for record in records if record["id"] == "publication-1"
            )
            watch = next(
                record
                for record in records
                if record["id"] != "publication-1"
            )
            self.assertEqual(watch["metadata"]["state"], "blocked")
            self.assertEqual(
                watch["metadata"]["terminal_reason"],
                "route-failed",
            )
            for record in (publication, watch):
                self.assertNotIn("handoff_verified", record["metadata"])
                self.assertNotIn("handoff_watch_id", record["metadata"])
                self.assertNotIn("handoff_target", record["metadata"])

            verify = self._run(
                env,
                "verify-handoff",
                self._payload(),
            )
            self.assertNotEqual(verify.returncode, 0)
            self.assertEqual(
                self._json(verify)["error"]["code"],
                "route-failed",
            )

            retry = self._run(
                env,
                "publication-handoff",
                self._payload(),
            )
            self.assertEqual(retry.returncode, 0, retry.stderr)
            self.assertEqual(self._json(retry)["watch_id"], watch["id"])
            state = self._run(
                env,
                "verify-handoff",
                self._payload(),
            )
            self.assertEqual(state.returncode, 0, state.stderr)
            records = json.loads((root / "beads.json").read_text(encoding="utf-8"))
            watch = next(
                record
                for record in records
                if record["id"] != "publication-1"
            )
            self.assertEqual(watch["metadata"]["state"], "watching")
            self.assertEqual(watch["metadata"]["claim_status"], "none")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_publication_rearm_recovers_blocked_exhausted_and_merge_ready(self):
        for state in ("blocked", "exhausted", "merge-ready"):
            with self.subTest(state=state):
                root, env = self._fixture("rearm-" + state)
                try:
                    result = self._run(
                        env,
                        "publication-handoff",
                        self._payload(),
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    watch_id = self._json(result)["watch_id"]
                    if state == "exhausted":
                        stopped = self._run(
                            env,
                            "checkpoint",
                            {
                                "watch_id": watch_id,
                                "expected_generation": 1,
                                "expected_head_sha": "b" * 40,
                                "observed_head_sha": "b" * 40,
                                "observed_at": "2026-09-02T00:00:00Z",
                                "next_snapshot_at": "2026-09-02T00:05:00Z",
                            },
                        )
                    else:
                        stopped = self._run(
                            env,
                            "transition",
                            {
                                "watch_id": watch_id,
                                "to": state,
                                **(
                                    {"reason": "later-blocker"}
                                    if state == "blocked"
                                    else {}
                                ),
                            },
                        )
                    self.assertEqual(stopped.returncode, 0, stopped.stderr)
                    rearmed = self._run(
                        env,
                        "publication-handoff",
                        self._payload() | {"rearm": True},
                    )
                    self.assertEqual(rearmed.returncode, 0, rearmed.stderr)
                    metadata = self._json(
                        self._run(
                            env,
                            "show",
                            {"watch_id": watch_id},
                        )
                    )["metadata"]
                    self.assertEqual(metadata["state"], "watching")
                    self.assertEqual(metadata["attempts"], "0")
                    self.assertEqual(metadata["attempt_history"], "")
                    self.assertEqual(metadata["blocker_emitted"], "false")
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def test_publication_retry_does_not_auto_rearm_completed_receipt_blocker(self):
        root, env = self._fixture("completed-receipt-blocker")
        try:
            result = self._run(
                env,
                "publication-handoff",
                self._payload(),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            watch_id = self._json(result)["watch_id"]
            blocked = self._run(
                env,
                "transition",
                {
                    "watch_id": watch_id,
                    "to": "blocked",
                    "reason": "later-blocker",
                },
            )
            self.assertEqual(blocked.returncode, 0, blocked.stderr)
            before = self._json(
                self._run(env, "show", {"watch_id": watch_id})
            )
            retry = self._run(
                env,
                "publication-handoff",
                self._payload(),
            )
            self.assertEqual(retry.returncode, 0, retry.stderr)
            after = self._json(
                self._run(env, "show", {"watch_id": watch_id})
            )
            self.assertEqual(after["metadata"]["state"], "blocked")
            self.assertEqual(
                after["metadata"]["generation"],
                before["metadata"]["generation"],
            )
            self.assertEqual(
                after["metadata"]["terminal_reason"],
                "later-blocker",
            )
            verify = self._run(
                env,
                "verify-handoff",
                self._payload(),
            )
            self.assertNotEqual(verify.returncode, 0)
            self.assertEqual(
                self._json(verify)["error"]["code"],
                "not-routable",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_duplicate_publisher_retry_reuses_one_watch_and_route(self):
        root, env = self._fixture("duplicate")
        try:
            first = self._run(
                env,
                "publication-handoff",
                self._payload(),
            )
            second = self._run(
                env,
                "publication-handoff",
                self._payload(),
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            first_receipt = self._json(first)
            second_receipt = self._json(second)
            self.assertNotEqual(first_receipt["watch_id"], "")
            self.assertEqual(first_receipt["watch_id"], second_receipt["watch_id"])
            self.assertTrue(first_receipt["created"])
            self.assertTrue(second_receipt["reused"])
            records = json.loads((root / "beads.json").read_text(encoding="utf-8"))
            self.assertEqual(
                len(
                    [
                        record
                        for record in records
                        if record["metadata"].get("record_kind") == "watch"
                    ]
                ),
                1,
            )
            creates = [
                call
                for call in self._bead_calls(root)
                if call["argv"] and call["argv"][0] == "create"
            ]
            self.assertEqual(len(creates), 1)
            gc_calls = json.loads(
                (root / "gc-calls.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(gc_calls), 2)
            self.assertEqual(gc_calls[0], gc_calls[1])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_handoff_receipt_is_safe_on_publication_and_watch_records(self):
        root, env = self._fixture("receipt")
        try:
            result = self._run(
                env,
                "publication-handoff",
                self._payload(),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = self._json(result)
            records = json.loads((root / "beads.json").read_text(encoding="utf-8"))
            publication = next(
                record for record in records if record["id"] == "publication-1"
            )
            watch = next(
                record
                for record in records
                if record["id"] == receipt["watch_id"]
            )
            for record in (publication, watch):
                metadata = record["metadata"]
                self.assertEqual(metadata["handoff_verified"], "true")
                self.assertEqual(metadata["handoff_watch_id"], receipt["watch_id"])
                self.assertEqual(metadata["handoff_target"], receipt["target"])
                self.assertNotIn("payload", metadata)
                self.assertNotIn("credential", metadata)
                self.assertNotIn("path", metadata)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_verify_handoff_re_reads_records_and_reports_failure_or_success(self):
        root, env = self._fixture("verify")
        try:
            handoff = self._run(
                env,
                "publication-handoff",
                self._payload(),
            )
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            receipt = self._json(handoff)
            calls_before = len(self._bead_calls(root))
            verified = self._run(
                env,
                "verify-handoff",
                self._payload(),
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            verified_receipt = self._json(verified)
            self.assertTrue(verified_receipt["verified"])
            self.assertEqual(verified_receipt["watch_id"], receipt["watch_id"])
            self.assertEqual(len(self._bead_calls(root)), calls_before + 2)

            records = json.loads((root / "beads.json").read_text(encoding="utf-8"))
            publication = next(
                record for record in records if record["id"] == "publication-1"
            )
            publication["metadata"]["handoff_target"] = "wrong/target"
            (root / "beads.json").write_text(
                json.dumps(records, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            failed = self._run(
                env,
                "verify-handoff",
                self._payload(),
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(
                len(
                    [
                        call
                        for call in self._bead_calls(root)
                        if call["argv"]
                        and call["argv"][0] in {"create", "update", "close"}
                    ]
                ),
                3,
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)


class PrBabysitRepairTests(unittest.TestCase):
    _HANDOFF = dict(PrBabysitStateTests._HANDOFF)

    def _fixture(self, name: str) -> tuple[pathlib.Path, dict[str, str]]:
        root = _temporary_root(f"u6-repair-{name}-")
        fake = root / "fake-beads"
        fake.write_text(
            PrBabysitStateTests._fake_beads_script(),
            encoding="utf-8",
        )
        fake.chmod(0o755)
        (root / "beads.json").write_text("[]\n", encoding="utf-8")
        (root / "calls.json").write_text("[]\n", encoding="utf-8")
        return root, {
            "PR_BABYSIT_BEADS_BIN": str(fake),
            "FAKE_BEADS_ROOT": str(root),
            "PR_BABYSIT_BEADS_CWD": str(root),
            "GC_RIG_ROOT": str(root),
            "PR_BABYSIT_ALLOWED_HOSTS": "github.com",
        }

    def _run(
        self,
        env: dict[str, str],
        action: str,
        payload: dict[str, object] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PR_BABYSIT_STATE_RUNNER), action],
            cwd=ROOT,
            env=os.environ | env,
            input=json.dumps(payload or {}),
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _json(result: subprocess.CompletedProcess[str]) -> dict:
        if not result.stdout:
            raise AssertionError(result.stderr)
        return json.loads(result.stdout)

    @staticmethod
    def _fake_gc_script() -> str:
        return r"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["FAKE_REPAIR_ROOT"])
calls_path = root / "gc-calls.json"
calls = json.loads(calls_path.read_text(encoding="utf-8")) if calls_path.exists() else []
calls.append(sys.argv[1:])
calls_path.write_text(
    json.dumps(calls, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
if os.environ.get("FAKE_GC_FAIL") == "1":
    print("formula attach failed", file=sys.stderr)
    raise SystemExit(1)
print(json.dumps({"ok": True, "root_id": "repair-root"}))
"""

    def _repair_fixture(
        self,
        name: str,
    ) -> tuple[pathlib.Path, dict[str, str]]:
        root, env = self._fixture(f"repair-{name}")
        fake_gc = root / "fake-gc"
        fake_gc.write_text(self._fake_gc_script(), encoding="utf-8")
        fake_gc.chmod(0o755)
        (root / "gc-calls.json").write_text("[]\n", encoding="utf-8")
        env.update(
            {
                "PR_BABYSIT_GC_BIN": str(fake_gc),
                "FAKE_REPAIR_ROOT": str(root),
                "PR_BABYSIT_GITHUB_CAPABILITY_ATTESTED": (
                    "contents-write,pull-requests-read"
                ),
                "PR_BABYSIT_VALIDATOR_ATTESTED": "credential-isolated-v1",
            }
        )
        return root, env

    def _dispatch(
        self,
        env: dict[str, str],
        watch_id: str,
        *,
        generation: int,
        head_sha: str,
        action_kind: str,
        fingerprint: str,
        addressed_thread_ids: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            env,
            "dispatch-repair",
            {
                "watch_id": watch_id,
                "generation": generation,
                "head_sha": head_sha,
                "action_kind": action_kind,
                "fingerprint": fingerprint,
                "addressed_thread_ids": addressed_thread_ids or [],
            },
        )

    def _complete(
        self,
        env: dict[str, str],
        watch_id: str,
        *,
        generation: int,
        old_sha: str,
        new_sha: str,
        action_kind: str,
        fingerprint: str,
    ) -> str:
        dispatched = self._dispatch(
            env,
            watch_id,
            generation=generation,
            head_sha=old_sha,
            action_kind=action_kind,
            fingerprint=fingerprint,
            addressed_thread_ids=["thread-1"],
        )
        self.assertEqual(dispatched.returncode, 0, dispatched.stderr)
        action_id = self._json(dispatched)["action_id"]
        recorded = self._run(
            env,
            "record-repair-result",
            {
                "watch_id": watch_id,
                "action_id": action_id,
                "generation": generation,
                "expected_old_sha": old_sha,
                "pushed_sha": new_sha,
                "validation_status": "passed",
                "make_check_result": "passed",
                "addressed_thread_ids": ["thread-1"],
            },
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        confirmed = self._run(
            env,
            "confirm-action",
            {
                "watch_id": watch_id,
                "action_id": action_id,
                "generation": generation,
                "current_sha": new_sha,
            },
        )
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
        return action_id

    def _validation_fixture(
        self,
        name: str,
        *,
        validator_mode: str = "ok",
        push_mode: str = "success",
        make_check_failure: bool = False,
    ) -> tuple[pathlib.Path, dict[str, str], str, str, str]:
        root = _temporary_root(f"u6-validation-{name}-")
        repository = root / "repository"
        remote = root / "remote.git"
        worktree = (
            repository
            / ".gc"
            / "agents"
            / "pr-babysitter"
            / "worktrees"
            / "action-1"
        )
        bin_dir = root / "bin"
        bin_dir.mkdir()
        subprocess.run(
            ["git", "init", "-q", str(repository)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        (repository / ".gitignore").write_text(".gc/\n", encoding="utf-8")
        (repository / "Makefile").write_text(
            ".PHONY: check\ncheck:\n\t@"
            + ("false" if make_check_failure else ":")
            + "\n",
            encoding="utf-8",
        )
        (repository / "tracked.txt").write_text("old\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(repository), "add", "."],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "commit", "-qm", "old"],
            check=True,
        )
        old_sha = subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        subprocess.run(
            ["git", "init", "--bare", "-q", str(remote)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "remote", "add", "origin", str(remote)],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "push",
                "-q",
                "origin",
                f"HEAD:refs/heads/feature/u4",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "worktree",
                "add",
                "--detach",
                "-q",
                str(worktree),
                old_sha,
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        (worktree / "tracked.txt").write_text("new\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(worktree), "add", "tracked.txt"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "commit", "-qm", "repair"],
            check=True,
        )
        new_sha = subprocess.check_output(
            ["git", "-C", str(worktree), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        subprocess.run(
            [
                "git",
                "-C",
                str(worktree),
                "push",
                "-q",
                "origin",
                "HEAD:refs/heads/validator-seed",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "commit", "--allow-empty", "-qm", "other"],
            check=True,
        )
        other_sha = subprocess.check_output(
            ["git", "-C", str(worktree), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        subprocess.run(
            [
                "git",
                "-C",
                str(worktree),
                "push",
                "-q",
                "origin",
                "HEAD:refs/heads/validator-other",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "reset", "--hard", new_sha],
            check=True,
            stdout=subprocess.DEVNULL,
        )

        action = {
            "id": "action-1",
            "status": "open",
            "assignee": "",
            "metadata": {
                "record_kind": "action",
                "provenance_version": "pr-repair-v1",
                "action_id": "action-1",
                "watch_id": "d2b-watch",
                "rig": "d2b",
                "rig_prefix": "d2b",
                "github_host": "github.com",
                "owner": "octo",
                "repository": "example",
                "head_repository": "octo/example",
                "pr_number": "7",
                "url": "https://github.com/octo/example/pull/7",
                "base_ref": "v3",
                "head_ref": "feature/u4",
                "head_sha": old_sha,
                "observed_head_sha": old_sha,
                "posture": "target",
                "target_posture": "target",
                "generation": "1",
                "action_kind": "ci",
                "action_fingerprint": "f" * 64,
                "claim_status": "claimed",
                "expected_old_head": old_sha,
                "worktree_provenance": "pr-repair-v1",
                "worktree_head_sha": old_sha,
                "worktree_head_ref": "feature/u4",
                "worktree_base_ref": "v3",
                "worktree_generation": "1",
                "worktree_action_id": "action-1",
            },
        }
        gc_script = bin_dir / "gc"
        gc_script.write_text(
            f"""#!{shutil.which("python3")}
import json
import sys
from pathlib import Path

root = Path({str(root)!r})
calls_path = root / "gc-calls.json"
calls = json.loads(calls_path.read_text()) if calls_path.exists() else []
args = sys.argv[1:]
calls.append(args)
calls_path.write_text(json.dumps(calls, sort_keys=True) + "\\n")
if args[:2] == ["bd", "show"]:
    print(json.dumps({json.dumps(action, sort_keys=True)}))
else:
    print(json.dumps({{"ok": True}}))
""",
            encoding="utf-8",
        )
        gc_script.chmod(0o755)
        git_script = bin_dir / "git"
        remote_sha = {
            "success": "",
            "new": new_sha,
            "old": old_sha,
            "other": other_sha,
        }[push_mode]
        git_script.write_text(
            f"""#!{shutil.which("python3")}
import json
import os
import subprocess
import sys
from pathlib import Path

real_git = {shutil.which("git")!r}
root = Path({str(root)!r})
args = sys.argv[1:]
if "push" in args:
    (root / "push-called").write_text("1\\n")
    (root / "push-args.json").write_text(json.dumps(args) + "\\n")
    if {push_mode!r} != "success":
        subprocess.run(
            [
                real_git,
                "--git-dir",
                {str(remote)!r},
                "update-ref",
                "refs/heads/feature/u4",
                {remote_sha!r},
            ],
            check=True,
        )
        raise SystemExit(1)
os.execv(real_git, [real_git, *args])
""",
            encoding="utf-8",
        )
        git_script.chmod(0o755)
        validator = root / "validator"
        validator.write_text(
            f"""#!{shutil.which("python3")}
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path({str(root)!r})
worktree = sys.argv[1]
names = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "COPILOT_GITHUB_TOKEN",
    "COPILOT_REQUESTS_TOKEN",
    "COPILOT_TOKEN",
    "PR_BABYSIT_GITHUB_CAPABILITY_ATTESTED",
    "PR_BABYSIT_VALIDATOR_ATTESTED",
    "GIT_ASKPASS",
    "GIT_TERMINAL_PROMPT",
    "GIT_SSH",
    "GIT_SSH_COMMAND",
    "GIT_SSH_VARIANT",
    "GIT_USERNAME",
    "GIT_PASSWORD",
    "GIT_AUTH_TOKEN",
    "GIT_HTTP_EXTRAHEADER",
    "GIT_CREDENTIAL_HELPER",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_KEY_0",
    "GIT_CONFIG_VALUE_0",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "GIT_PUSH_OPTION_COUNT",
    "SSH_AUTH_SOCK",
)
(root / "validator-env.json").write_text(
    json.dumps({{name: os.environ.get(name) for name in names}}, sort_keys=True) + "\\n"
)
check = subprocess.run(["make", "-C", worktree, "check"], check=False)
if check.returncode:
    raise SystemExit(check.returncode)
mode = {validator_mode!r}
if mode == "head":
    subprocess.run(["git", "-C", worktree, "reset", "--hard", "HEAD~1"], check=True)
elif mode == "config":
    subprocess.run(["git", "-C", worktree, "config", "--local", "validator.mutated", "1"], check=True)
elif mode == "origin":
    subprocess.run(["git", "-C", worktree, "remote", "set-url", "origin", "file:///mutated"], check=True)
elif mode == "status":
    Path(worktree, "tracked.txt").write_text("mutated\\n")
elif mode == "fail":
    raise SystemExit(7)
""",
            encoding="utf-8",
        )
        validator.chmod(0o755)
        script = self._render_validate_script(
            root,
            {
                "rig": "d2b",
                "github_host": "github.com",
                "owner": "octo",
                "repository": "example",
                "head_repository": "octo/example",
                "url": "https://github.com/octo/example/pull/7",
                "pr_number": "7",
                "base_ref": "v3",
                "head_ref": "feature/u4",
                "observed_head_sha": old_sha,
                "watch_id": "d2b-watch",
                "action_id": "action-1",
                "generation": "1",
                "action_kind": "ci",
                "fingerprint": "f" * 64,
                "addressed_thread_ids": "",
            },
        )
        env = {
            "GC_BIN": str(gc_script),
            "GC_RIG": "d2b",
            "GC_RIG_ROOT": str(repository),
            "PR_BABYSIT_WORKTREE": str(worktree),
            "PR_BABYSIT_VALIDATOR": str(validator),
            "PR_BABYSIT_VALIDATOR_ATTESTED": "credential-isolated-v1",
            "PR_BABYSIT_GITHUB_CAPABILITY_ATTESTED": (
                "contents-write,pull-requests-read"
            ),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        }
        return root, env, old_sha, new_sha, other_sha

    @staticmethod
    def _render_workflow_script(
        source: pathlib.Path,
        root: pathlib.Path,
        values: dict[str, str],
        name: str,
    ) -> pathlib.Path:
        text = source.read_text(encoding="utf-8")
        for key, value in values.items():
            text = text.replace("{{" + key + "}}", value)
        matches = re.findall(
            r"```(?:bash|sh)\n(.*?)\n```",
            text,
            flags=re.DOTALL,
        )
        if len(matches) != 1:
            raise AssertionError(
                f"{source} must contain one fenced shell workflow"
            )
        script = root / name
        script.write_text("#!/usr/bin/env bash\n" + matches[0], encoding="utf-8")
        script.chmod(0o755)
        return script

    @staticmethod
    def _render_validate_script(
        root: pathlib.Path,
        values: dict[str, str],
    ) -> pathlib.Path:
        return PrBabysitRepairTests._render_workflow_script(
            PR_BABYSIT_REPAIR_VALIDATE,
            root,
            values,
            "validate.sh",
        )

    def _prepare_fixture(
        self,
        name: str,
        *,
        worktree_mode: str = "none",
        stale_remote: bool = False,
    ) -> tuple[pathlib.Path, dict[str, str], str, str, pathlib.Path]:
        root = _temporary_root(f"u6-prepare-{name}-")
        repository = root / "repository"
        remote = root / "remote.git"
        worktree = (
            repository
            / ".gc"
            / "agents"
            / "pr-babysitter"
            / "worktrees"
            / "action-1"
        )
        bin_dir = root / "bin"
        bin_dir.mkdir()
        subprocess.run(
            ["git", "init", "-q", "-b", "v3", str(repository)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "config",
                "user.email",
                "test@example.invalid",
            ],
            check=True,
        )
        (repository / ".gitignore").write_text(".gc/\n", encoding="utf-8")
        (repository / "tracked.txt").write_text("old\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(repository), "add", "."],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "commit", "-qm", "old"],
            check=True,
        )
        old_sha = subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        subprocess.run(
            ["git", "init", "--bare", "-q", str(remote)],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "remote",
                "add",
                "origin",
                str(remote),
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "push",
                "-q",
                "origin",
                f"HEAD:refs/heads/feature/u4",
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "commit",
                "--allow-empty",
                "-qm",
                "new",
            ],
            check=True,
        )
        new_sha = subprocess.check_output(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        if stale_remote:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "push",
                    "-q",
                    "origin",
                    "HEAD:refs/heads/stale-seed",
                ],
                check=True,
            )
        subprocess.run(
            ["git", "-C", str(repository), "reset", "--hard", old_sha],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        if stale_remote:
            subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(remote),
                    "update-ref",
                    "refs/heads/feature/u4",
                    new_sha,
                ],
                check=True,
            )

        metadata = {
            "record_kind": "action",
            "provenance_version": "pr-repair-v1",
            "action_id": "action-1",
            "watch_id": "d2b-watch",
            "rig": "d2b",
            "github_host": "github.com",
            "owner": "octo",
            "repository": "example",
            "head_repository": "octo/example",
            "pr_number": "7",
            "url": "https://github.com/octo/example/pull/7",
            "base_ref": "v3",
            "head_ref": "feature/u4",
            "head_sha": old_sha,
            "observed_head_sha": old_sha,
            "expected_old_head": old_sha,
            "generation": "1",
            "action_kind": "ci",
            "action_fingerprint": "f" * 64,
            "claim_status": "claimed",
        }
        if worktree_mode in {"clean", "dirty"}:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "worktree",
                    "add",
                    "--detach",
                    "-q",
                    str(worktree),
                    old_sha,
                ],
                check=True,
            )
            metadata.update(
                {
                    "worktree_provenance": "pr-repair-v1",
                    "worktree_head_sha": old_sha,
                    "worktree_head_ref": "feature/u4",
                    "worktree_base_ref": "v3",
                    "worktree_generation": "1",
                    "worktree_action_id": "action-1",
                }
            )
            if worktree_mode == "dirty":
                (worktree / "tracked.txt").write_text(
                    "dirty\n",
                    encoding="utf-8",
                )
        elif worktree_mode == "collision":
            worktree.parent.mkdir(parents=True, exist_ok=True)
            worktree.write_text("collision\n", encoding="utf-8")

        action = {
            "id": "action-1",
            "status": "open",
            "assignee": "",
            "metadata": metadata,
        }
        gc_script = bin_dir / "gc"
        gc_script.write_text(
            f"""#!{shutil.which("python3")}
import json
import sys
from pathlib import Path

root = Path({str(root)!r})
calls_path = root / "gc-calls.json"
calls = json.loads(calls_path.read_text()) if calls_path.exists() else []
args = sys.argv[1:]
calls.append(args)
calls_path.write_text(json.dumps(calls, sort_keys=True) + "\\n")
if args[:2] == ["bd", "show"]:
    print(json.dumps([{json.dumps(action, sort_keys=True)}]))
elif args[:2] == ["bd", "update"]:
    print(json.dumps({{"ok": True}}))
else:
    print("unexpected gc command", file=sys.stderr)
    raise SystemExit(2)
""",
            encoding="utf-8",
        )
        gc_script.chmod(0o755)
        (root / "gc-calls.json").write_text("[]\n", encoding="utf-8")
        values = {
            "rig": "d2b",
            "github_host": "github.com",
            "owner": "octo",
            "repository": "example",
            "head_repository": "octo/example",
            "url": "https://github.com/octo/example/pull/7",
            "pr_number": "7",
            "base_ref": "v3",
            "head_ref": "feature/u4",
            "observed_head_sha": old_sha,
            "watch_id": "d2b-watch",
            "action_id": "action-1",
            "generation": "1",
            "action_kind": "ci",
            "fingerprint": "f" * 64,
        }
        script = self._render_workflow_script(
            PR_BABYSIT_REPAIR_PREPARE,
            root,
            values,
            "prepare.sh",
        )
        env = {
            "GC_BIN": str(gc_script),
            "GC_RIG": "d2b",
            "GC_RIG_ROOT": str(repository),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "PR_BABYSIT_GITHUB_CAPABILITY_ATTESTED": (
                "contents-write,pull-requests-read"
            ),
        }
        return root, env, old_sha, new_sha, worktree

    def test_prepare_workflow_executes_exact_head_and_rejects_reuse_failures(
        self,
    ):
        root, env, old_sha, _, worktree = self._prepare_fixture("exact-head")
        try:
            prepared = subprocess.run(
                [str(root / "prepare.sh")],
                cwd=ROOT,
                env=os.environ | env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertIn("prepared action-scoped worktree", prepared.stdout)
            self.assertTrue(worktree.is_dir())
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(worktree), "rev-parse", "HEAD"],
                    text=True,
                ).strip(),
                old_sha,
            )
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(worktree), "branch", "--show-current"],
                    text=True,
                ).strip(),
                "",
            )
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(worktree), "status", "--porcelain"],
                    text=True,
                ),
                "",
            )
            calls = json.loads((root / "gc-calls.json").read_text())
            self.assertEqual(calls[0][:3], ["bd", "show", "action-1"])
            self.assertEqual(calls[1][:3], ["bd", "update", "action-1"])
            metadata_args = calls[1]
            self.assertIn("worktree_provenance=pr-repair-v1", metadata_args)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        for name, kwargs, message in (
            (
                "stale",
                {"stale_remote": True},
                "remote pull-request head changed after observation",
            ),
            (
                "dirty",
                {"worktree_mode": "dirty"},
                "recorded action worktree is dirty",
            ),
            (
                "collision",
                {"worktree_mode": "collision"},
                "action-scoped worktree path collision",
            ),
        ):
            with self.subTest(name=name):
                root, env, _, _, worktree = self._prepare_fixture(
                    "failure-" + name,
                    **kwargs,
                )
                try:
                    failed = subprocess.run(
                        [str(root / "prepare.sh")],
                        cwd=ROOT,
                        env=os.environ | env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertNotEqual(failed.returncode, 0)
                    self.assertIn(message, failed.stderr)
                    calls = json.loads(
                        (root / "gc-calls.json").read_text()
                    )
                    self.assertFalse(
                        any(call[:2] == ["bd", "update"] for call in calls)
                    )
                    if name == "stale":
                        self.assertFalse(worktree.exists())
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def _run_validation(
        self,
        root: pathlib.Path,
        env: dict[str, str],
        *,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(root / "validate.sh")],
            cwd=ROOT,
            env=os.environ | env | (extra_env or {}),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_validator_is_credential_isolated_before_a_push(self):
        root, env, _, new_sha, _ = self._validation_fixture(
            "isolated",
        )
        try:
            result = self._run_validation(
                root,
                env,
                extra_env={
                    "GH_TOKEN": "push-secret",
                    "GITHUB_TOKEN": "push-secret-2",
                    "COPILOT_GITHUB_TOKEN": "copilot-secret",
                    "COPILOT_REQUESTS_TOKEN": "requests-secret",
                    "COPILOT_TOKEN": "token-secret",
                    "PR_BABYSIT_GITHUB_CAPABILITY_ATTESTED": (
                        "contents-write,pull-requests-read"
                    ),
                    "PR_BABYSIT_VALIDATOR_ATTESTED": "credential-isolated-v1",
                    "GIT_ASKPASS": "/secret/askpass",
                    "GIT_TERMINAL_PROMPT": "1",
                    "GIT_SSH": "/secret/ssh",
                    "GIT_SSH_COMMAND": "ssh -i /secret/key",
                    "GIT_SSH_VARIANT": "ssh",
                    "GIT_USERNAME": "secret-user",
                    "GIT_PASSWORD": "secret-password",
                    "GIT_AUTH_TOKEN": "secret-auth",
                    "GIT_HTTP_EXTRAHEADER": "Authorization: secret",
                    "GIT_CREDENTIAL_HELPER": "secret-helper",
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "credential.helper",
                    "GIT_CONFIG_VALUE_0": "secret-helper",
                    "GH_ENTERPRISE_TOKEN": "secret-enterprise",
                    "GITHUB_ENTERPRISE_TOKEN": "secret-enterprise-2",
                    "GIT_PUSH_OPTION_COUNT": "1",
                    "SSH_AUTH_SOCK": "/secret/agent.sock",
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            isolated = json.loads(
                (root / "validator-env.json").read_text(encoding="utf-8")
            )
            self.assertTrue(isolated)
            self.assertTrue(all(value is None for value in isolated.values()))
            self.assertEqual(
                subprocess.check_output(
                    ["git", "--git-dir", str(root / "remote.git"), "rev-parse", "refs/heads/feature/u4"],
                    text=True,
                ).strip(),
                new_sha,
            )
            self.assertTrue((root / "push-called").is_file())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validator_missing_bad_or_symlink_fails_closed(self):
        for kind in ("missing", "bad", "symlink"):
            with self.subTest(kind=kind):
                root, env, _, _, _ = self._validation_fixture("validator-" + kind)
                try:
                    if kind == "missing":
                        env.pop("PR_BABYSIT_VALIDATOR")
                    elif kind == "bad":
                        validator = pathlib.Path(env["PR_BABYSIT_VALIDATOR"])
                        validator.chmod(0o644)
                    else:
                        validator = pathlib.Path(env["PR_BABYSIT_VALIDATOR"])
                        target = root / "validator-target"
                        target.write_bytes(validator.read_bytes())
                        target.chmod(0o755)
                        validator.unlink()
                        validator.symlink_to(target)
                    result = self._run_validation(root, env)
                    self.assertNotEqual(result.returncode, 0, result.stderr)
                    self.assertFalse((root / "push-called").exists())
                    calls = json.loads((root / "gc-calls.json").read_text())
                    self.assertTrue(
                        any(
                            "--validation-status" in call
                            and "failed" in call
                            for call in calls
                        )
                    )
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def test_validator_mutations_block_push(self):
        for mode in ("head", "config", "origin", "status"):
            with self.subTest(mode=mode):
                root, env, _, _, _ = self._validation_fixture(
                    "mutation-" + mode,
                    validator_mode=mode,
                )
                try:
                    result = self._run_validation(root, env)
                    self.assertNotEqual(result.returncode, 0, result.stderr)
                    self.assertFalse((root / "push-called").exists())
                    calls = json.loads((root / "gc-calls.json").read_text())
                    result_call = calls[-1]
                    self.assertIn("--validation-status", result_call)
                    self.assertEqual(
                        result_call[
                            result_call.index("--validation-status") + 1
                        ],
                        "failed",
                    )
                    self.assertIn("--reason", result_call)
                    self.assertEqual(
                        result_call[result_call.index("--reason") + 1],
                        "validator-invariant",
                    )
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def test_validator_failure_records_failed_without_push(self):
        root, env, _, _, _ = self._validation_fixture(
            "validator-failure",
            validator_mode="fail",
        )
        try:
            result = self._run_validation(root, env)
            self.assertNotEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / "push-called").exists())
            calls = json.loads((root / "gc-calls.json").read_text())
            result_call = calls[-1]
            self.assertEqual(
                result_call[result_call.index("--validation-status") + 1],
                "failed",
            )
            self.assertEqual(
                result_call[result_call.index("--reason") + 1],
                "validator-failed",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_make_check_failure_records_failed_without_push(self):
        root, env, _, _, _ = self._validation_fixture(
            "make-check-failure",
            make_check_failure=True,
        )
        try:
            result = self._run_validation(root, env)
            self.assertNotEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / "push-called").exists())
            calls = json.loads((root / "gc-calls.json").read_text())
            result_call = calls[-1]
            self.assertEqual(
                result_call[result_call.index("--validation-status") + 1],
                "failed",
            )
            self.assertEqual(
                result_call[result_call.index("--make-check-result") + 1],
                "failed",
            )
            self.assertEqual(
                result_call[result_call.index("--reason") + 1],
                "validator-failed",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_push_failure_is_classified_from_remote_observation(self):
        for mode, expected_status, expected_returncode in (
            ("new", "passed", 0),
            ("old", "failed", 1),
            ("other", "ambiguous", 1),
        ):
            with self.subTest(mode=mode):
                root, env, old_sha, new_sha, other_sha = self._validation_fixture(
                    "push-" + mode,
                    push_mode=mode,
                )
                try:
                    result = self._run_validation(root, env)
                    self.assertEqual(
                        result.returncode,
                        expected_returncode,
                        result.stderr,
                    )
                    calls = json.loads((root / "gc-calls.json").read_text())
                    result_call = calls[-1]
                    status = result_call[
                        result_call.index("--validation-status") + 1
                    ]
                    self.assertEqual(status, expected_status)
                    self.assertEqual(
                        result_call[
                            result_call.index("--make-check-result") + 1
                        ],
                        "passed",
                    )
                    self.assertEqual(
                        calls.count(
                            [
                                "bd",
                                "show",
                                "action-1",
                                "--json",
                            ]
                        ),
                        1,
                    )
                    if mode == "new":
                        self.assertEqual(
                            result_call[
                                result_call.index("--pushed-sha") + 1
                            ],
                            new_sha,
                        )
                    elif mode == "old":
                        self.assertIn("--reason", result_call)
                        self.assertEqual(
                            result_call[result_call.index("--reason") + 1],
                            "push-failed",
                        )
                        self.assertNotIn("--pushed-sha", result_call)
                    else:
                        self.assertEqual(
                            result_call[
                                result_call.index("--remote-head-sha") + 1
                            ],
                            other_sha,
                        )
                    self.assertTrue((root / "push-called").is_file())
                    push_args = json.loads(
                        (root / "push-args.json").read_text()
                    )
                    self.assertEqual(
                        push_args[-3:],
                        ["push", "origin", "HEAD:refs/heads/feature/u4"],
                    )
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def test_repair_formula_declares_v2_targets_dependencies_and_assets(self):
        formula = tomllib.loads(
            PR_BABYSIT_REPAIR_FORMULA.read_text(encoding="utf-8")
        )
        self.assertEqual(formula["formula"], "mol-pr-babysit-repair")
        self.assertEqual(formula["version"], 2)
        self.assertEqual(
            formula["requires"]["formula_compiler"],
            ">=2.0.0",
        )
        steps = formula["steps"]
        self.assertEqual(
            [step["id"] for step in steps],
            [
                "prepare-worktree",
                "repair",
                "review",
                "validate-and-report",
                "close-action",
            ],
        )
        targets = {
            step["id"]: step["metadata"]["gc.run_target"]
            for step in steps
        }
        self.assertEqual(
            targets,
            {
                "prepare-worktree": "gc.run-operator",
                "repair": "gc.implementation-worker",
                "review": "gc.implementation-reviewer",
                "validate-and-report": "gc.run-operator",
                "close-action": "gc.run-operator",
            },
        )
        by_id = {step["id"]: step for step in steps}
        self.assertIn("head_repository", formula["vars"])
        self.assertEqual(by_id["repair"]["needs"], ["prepare-worktree"])
        self.assertEqual(by_id["review"]["needs"], ["repair"])
        self.assertEqual(
            by_id["validate-and-report"]["needs"],
            ["repair", "review"],
        )
        self.assertEqual(
            by_id["close-action"]["needs"],
            ["validate-and-report"],
        )
        self.assertIn(
            "description_file",
            by_id["prepare-worktree"],
        )
        self.assertIn(
            "description_file",
            by_id["validate-and-report"],
        )
        for path in (PR_BABYSIT_REPAIR_PREPARE, PR_BABYSIT_REPAIR_VALIDATE):
            self.assertTrue(path.is_file(), path)

    def test_repair_formula_compiles_with_native_formula_v2(self):
        gc = shutil.which("gc")
        if gc is None:
            self.skipTest("gc unavailable")
        result = subprocess.run(
            [
                gc,
                "formula",
                "show",
                "mol-pr-babysit-repair",
                "--city",
                str(CITY_ROOT),
                "--rig",
                "d2b",
                "--json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        compiled = json.loads(result.stdout)
        self.assertTrue(compiled["ok"])
        self.assertEqual(
            {
                (dep["step_id"], dep["depends_on_id"])
                for dep in compiled["deps"]
                if dep["step_id"].startswith("mol-pr-babysit-repair.")
                and dep["depends_on_id"].startswith("mol-pr-babysit-repair.")
            },
            {
                (
                    "mol-pr-babysit-repair.repair",
                    "mol-pr-babysit-repair.prepare-worktree",
                ),
                (
                    "mol-pr-babysit-repair.review",
                    "mol-pr-babysit-repair.repair",
                ),
                (
                    "mol-pr-babysit-repair.validate-and-report",
                    "mol-pr-babysit-repair.repair",
                ),
                (
                    "mol-pr-babysit-repair.validate-and-report",
                    "mol-pr-babysit-repair.review",
                ),
                (
                    "mol-pr-babysit-repair.close-action",
                    "mol-pr-babysit-repair.validate-and-report",
                ),
                (
                    "mol-pr-babysit-repair.workflow-finalize",
                    "mol-pr-babysit-repair.close-action",
                ),
            },
        )

    def test_repair_workflows_bind_identity_and_fail_closed(self):
        prepare = PR_BABYSIT_REPAIR_PREPARE.read_text(encoding="utf-8")
        validate = PR_BABYSIT_REPAIR_VALIDATE.read_text(encoding="utf-8")
        prompt = (
            PR_BABYSIT_ROOT
            / "agents"
            / "pr-babysitter"
            / "prompt.template.md"
        ).read_text(encoding="utf-8")
        text = "\n".join((prepare, validate, prompt)).lower()
        for marker in (
            "github host",
            "repository",
            "head_repository",
            "pr number",
            "base_ref",
            "head_ref",
            "observed_head_sha",
            "head_repository",
            "action_id",
            "generation",
            "dirty",
            "symlink",
            "stale",
            "contents write",
            "pull requests read",
            "operator-attested",
            "untrusted data",
            "explicitly addressed thread",
            "make check",
            "refs/heads/",
        ):
            self.assertIn(marker, text, marker)
        for marker in (
            "d2b) EXPECTED_BASE='v3'",
            "city-source) EXPECTED_BASE='main'",
            "recorded action worktree is missing",
            "recorded action worktree is dirty",
            "legacy or incomplete worktree provenance",
            "action-scoped worktree path collision",
            "remote pull-request head changed after observation",
            "remote head is stale",
            "push outcome is ambiguous",
            "credential-isolated-v1",
            "pr_babysit_validator",
            "validator-invariant",
            "push-failed",
        ):
            self.assertIn(marker.lower(), prepare.lower() + "\n" + validate.lower())
        self.assertIn(
            'git -C "$WORKTREE" push origin \\\n'
            '    "HEAD:refs/heads/$HEAD_REF"',
            validate,
        )
        self.assertIn(
            'refs/heads/$HEAD_REF:refs/remotes/origin/$HEAD_REF',
            prepare,
        )
        self.assertNotIn("fork_sha", prepare.lower())
        self.assertNotIn("origin/v3", prepare.lower())
        self.assertNotIn("owning source checkout is dirty", prepare.lower())
        self.assertNotIn(".pr-babysit-state.json", validate)
        self.assertNotIn('(cd "$WORKTREE" && make check)', validate)
        self.assertIn('"$VALIDATOR" "$WORKTREE"', validate)
        for marker in (
            "git -C \"$WORKTREE\" config --local --list",
            "git -C \"$WORKTREE\" remote get-url origin",
            "remote\\..*\\.fetch",
            "-u GH_TOKEN",
            "-u GITHUB_TOKEN",
            "-u COPILOT_TOKEN",
            "-u PR_BABYSIT_GITHUB_CAPABILITY_ATTESTED",
        ):
            self.assertIn(marker, validate)
        self.assertEqual(validate.count("record_result()"), 1)
        self.assertEqual(
            validate.count("gc pr-babysit pr-babysit record-repair-result"),
            1,
        )
        for call in (
            "record_result failed failed",
            "record_result ambiguous passed",
            "record_result passed passed",
        ):
            self.assertIn(call, validate)
        for forbidden in (
            "git merge",
            "git rebase",
            "--force",
            "--force-with-lease",
            "gh pr merge",
            "approve workflow",
            "create a replacement",
        ):
            self.assertNotIn(forbidden, prepare.lower() + "\n" + validate.lower())
        self.assertIn(
            "GH_TOKEN",
            prepare,
        )
        self.assertIn(
            "GITHUB_TOKEN",
            prepare,
        )

    def test_dispatch_claims_before_idempotent_formula_and_blocks_watch(self):
        root, env = self._repair_fixture("dispatch")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            dispatched = self._dispatch(
                env,
                watch_id,
                generation=1,
                head_sha="a" * 40,
                action_kind="ci",
                fingerprint="check failed",
                addressed_thread_ids=["thread-1"],
            )
            self.assertEqual(dispatched.returncode, 0, dispatched.stderr)
            result = self._json(dispatched)
            action_id = result["action_id"]
            records = json.loads((root / "beads.json").read_text())
            action = next(record for record in records if record["id"] == action_id)
            watch = next(record for record in records if record["id"] == watch_id)
            self.assertEqual(action["metadata"]["claim_status"], "claimed")
            self.assertEqual(action["metadata"]["formula_attached"], "true")
            self.assertIn(action_id, watch["blocked_by"])
            calls = json.loads((root / "gc-calls.json").read_text())
            self.assertEqual(len(calls), 1)
            self.assertEqual(
                calls[0][:4],
                ["formula", "cook", "mol-pr-babysit-repair", "--attach"],
            )
            self.assertEqual(calls[0][4], watch_id)
            dep_calls = [
                call["argv"]
                for call in json.loads((root / "calls.json").read_text())
                if call["argv"] and call["argv"][0] == "dep"
            ]
            self.assertEqual(
                dep_calls,
                [["dep", action_id, "--blocks", watch_id]],
            )

            reused = self._dispatch(
                env,
                watch_id,
                generation=1,
                head_sha="a" * 40,
                action_kind="ci",
                fingerprint="CHECK   FAILED",
                addressed_thread_ids=["thread-1"],
            )
            self.assertEqual(reused.returncode, 0, reused.stderr)
            self.assertTrue(self._json(reused)["reused"])
            self.assertEqual(
                len(json.loads((root / "gc-calls.json").read_text())),
                1,
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_claim_setup_failures_block_watch_without_advancing_attempts(self):
        for failure_kind in ("action-create", "dependency", "watch-repairing"):
            root, env = self._repair_fixture("claim-failure-" + failure_kind)
            try:
                handoff = self._run(env, "handoff", self._HANDOFF)
                self.assertEqual(handoff.returncode, 0, handoff.stderr)
                watch_id = self._json(handoff)["watch_id"]
                failed = self._run(
                    env | {"FAKE_BEADS_FAIL_ON": failure_kind},
                    "claim-action",
                    {
                        "watch_id": watch_id,
                        "generation": 1,
                        "head_sha": "a" * 40,
                        "action_kind": "ci",
                        "fingerprint": "claim setup failure",
                    },
                )
                self.assertNotEqual(failed.returncode, 0)
                state = self._json(
                    self._run(env, "show", {"watch_id": watch_id})
                )
                metadata = state["metadata"]
                self.assertEqual(metadata["state"], "blocked")
                self.assertEqual(
                    metadata["terminal_reason"],
                    "claim-setup-failed",
                )
                self.assertEqual(metadata["claim_status"], "blocked")
                self.assertEqual(metadata["attempts"], "0")
                self.assertEqual(metadata["attempt_key"], "")
                self.assertEqual(metadata["attempt_history"], "")
                records = json.loads(
                    (root / "beads.json").read_text(encoding="utf-8")
                )
                watch = next(record for record in records if record["id"] == watch_id)
                self.assertEqual(watch["assignee"], "")
                actions = [
                    record
                    for record in records
                    if record["id"] != watch_id
                ]
                if failure_kind == "action-create":
                    self.assertEqual(actions, [])
                else:
                    self.assertEqual(len(actions), 1)
                    action = actions[0]
                    self.assertEqual(action["status"], "blocked")
                    self.assertEqual(action["assignee"], "")
                    self.assertEqual(
                        action["metadata"]["claim_status"],
                        "blocked",
                    )
                    self.assertEqual(
                        action["metadata"]["terminal_reason"],
                        "claim-setup-failed",
                    )
            finally:
                shutil.rmtree(root, ignore_errors=True)

    def test_result_records_sha_check_and_threads_then_closes_action(self):
        root, env = self._repair_fixture("result")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            action_id = self._complete(
                env,
                watch_id,
                generation=1,
                old_sha="a" * 40,
                new_sha="b" * 40,
                action_kind="review",
                fingerprint="thread needs fix",
            )
            records = json.loads((root / "beads.json").read_text())
            action = next(record for record in records if record["id"] == action_id)
            watch = next(record for record in records if record["id"] == watch_id)
            self.assertEqual(action["status"], "closed")
            self.assertEqual(action["metadata"]["expected_old_sha"], "a" * 40)
            self.assertEqual(action["metadata"]["pushed_sha"], "b" * 40)
            self.assertEqual(action["metadata"]["make_check_result"], "passed")
            self.assertEqual(
                action["metadata"]["addressed_thread_ids"],
                "thread-1",
            )
            self.assertEqual(watch["metadata"]["head_sha"], "b" * 40)
            self.assertEqual(watch["metadata"]["state"], "watching")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_confirm_close_failure_leaves_repairing_and_retry_reconciles(self):
        root, env = self._repair_fixture("close-failure")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            dispatched = self._dispatch(
                env,
                watch_id,
                generation=1,
                head_sha="a" * 40,
                action_kind="ci",
                fingerprint="close failure",
            )
            self.assertEqual(dispatched.returncode, 0, dispatched.stderr)
            action_id = self._json(dispatched)["action_id"]
            recorded = self._run(
                env,
                "record-repair-result",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "expected_old_sha": "a" * 40,
                    "pushed_sha": "b" * 40,
                    "validation_status": "passed",
                    "make_check_result": "passed",
                },
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            failed = self._run(
                env | {"FAKE_BEADS_FAIL_ON": "close-action"},
                "confirm-action",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "current_sha": "b" * 40,
                },
            )
            self.assertNotEqual(failed.returncode, 0)
            state = self._json(
                self._run(env, "show", {"watch_id": watch_id})
            )
            self.assertEqual(state["metadata"]["state"], "repairing")
            self.assertEqual(
                state["metadata"]["claim_status"],
                "result-recorded",
            )
            retried = self._run(
                env,
                "confirm-action",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "current_sha": "b" * 40,
                },
            )
            self.assertEqual(retried.returncode, 0, retried.stderr)
            records = json.loads((root / "beads.json").read_text(encoding="utf-8"))
            action = next(record for record in records if record["id"] == action_id)
            watch = next(record for record in records if record["id"] == watch_id)
            self.assertEqual(action["status"], "closed")
            self.assertEqual(watch["metadata"]["state"], "watching")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_confirm_retries_closed_action_after_watch_update_failure(self):
        root, env = self._repair_fixture("watch-update-failure")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            dispatched = self._dispatch(
                env,
                watch_id,
                generation=1,
                head_sha="a" * 40,
                action_kind="ci",
                fingerprint="watch update failure",
            )
            self.assertEqual(dispatched.returncode, 0, dispatched.stderr)
            action_id = self._json(dispatched)["action_id"]
            recorded = self._run(
                env,
                "record-repair-result",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "expected_old_sha": "a" * 40,
                    "pushed_sha": "b" * 40,
                    "validation_status": "passed",
                    "make_check_result": "passed",
                },
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            failed = self._run(
                env | {"FAKE_BEADS_FAIL_ON": "watch-confirm"},
                "confirm-action",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "current_sha": "b" * 40,
                },
            )
            self.assertNotEqual(failed.returncode, 0)
            records = json.loads((root / "beads.json").read_text(encoding="utf-8"))
            action = next(record for record in records if record["id"] == action_id)
            watch = next(record for record in records if record["id"] == watch_id)
            self.assertEqual(action["status"], "closed")
            self.assertEqual(watch["metadata"]["state"], "repairing")
            self.assertEqual(
                watch["metadata"]["claim_status"],
                "result-recorded",
            )
            retried = self._run(
                env,
                "confirm-action",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "current_sha": "b" * 40,
                },
            )
            self.assertEqual(retried.returncode, 0, retried.stderr)
            records = json.loads((root / "beads.json").read_text(encoding="utf-8"))
            watch = next(record for record in records if record["id"] == watch_id)
            self.assertEqual(watch["metadata"]["state"], "watching")
            close_calls = [
                call
                for call in json.loads((root / "calls.json").read_text())
                if call["argv"] and call["argv"][0] == "close"
            ]
            self.assertEqual(len(close_calls), 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_result_rejects_unclaimed_or_command_like_thread_ids(self):
        root, env = self._repair_fixture("thread-fence")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            dispatched = self._dispatch(
                env,
                watch_id,
                generation=1,
                head_sha="a" * 40,
                action_kind="review",
                fingerprint="thread-fence",
                addressed_thread_ids=["thread-1"],
            )
            self.assertEqual(dispatched.returncode, 0, dispatched.stderr)
            action_id = self._json(dispatched)["action_id"]
            for thread_id in ("thread-2", "$(touch marker)"):
                result = self._run(
                    env,
                    "record-repair-result",
                    {
                        "watch_id": watch_id,
                        "action_id": action_id,
                        "generation": 1,
                        "expected_old_sha": "a" * 40,
                        "pushed_sha": "b" * 40,
                        "validation_status": "passed",
                        "make_check_result": "passed",
                        "addressed_thread_ids": [thread_id],
                    },
                )
                self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "marker").exists())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_attempt_budgets_survive_heads_and_reset_for_new_fingerprints(self):
        root, env = self._repair_fixture("budgets")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            old_sha = "a" * 40
            for generation, new_sha in (
                (1, "b" * 40),
                (2, "c" * 40),
                (3, "d" * 40),
            ):
                self._complete(
                    env,
                    watch_id,
                    generation=generation,
                    old_sha=old_sha,
                    new_sha=new_sha,
                    action_kind="ci",
                    fingerprint="same failing check",
                )
                old_sha = new_sha
                state = self._json(self._run(env, "show", {"watch_id": watch_id}))
                self.assertEqual(state["metadata"]["attempts"], str(generation))
            exhausted = self._dispatch(
                env,
                watch_id,
                generation=4,
                head_sha=old_sha,
                action_kind="ci",
                fingerprint="same failing check",
            )
            self.assertNotEqual(exhausted.returncode, 0)
            self.assertEqual(
                self._json(exhausted)["error"]["code"],
                "attempt-budget-exhausted",
            )
            state = self._json(self._run(env, "show", {"watch_id": watch_id}))
            self.assertEqual(state["metadata"]["state"], "exhausted")
            self.assertEqual(
                len(json.loads((root / "gc-calls.json").read_text())),
                3,
            )

            reset_root, reset_env = self._repair_fixture("fingerprint-reset")
            try:
                handoff = self._run(reset_env, "handoff", self._HANDOFF)
                self.assertEqual(handoff.returncode, 0, handoff.stderr)
                reset_watch = self._json(handoff)["watch_id"]
                self._complete(
                    reset_env,
                    reset_watch,
                    generation=1,
                    old_sha="a" * 40,
                    new_sha="b" * 40,
                    action_kind="review",
                    fingerprint="thread-one",
                )
                next_dispatch = self._dispatch(
                    reset_env,
                    reset_watch,
                    generation=2,
                    head_sha="b" * 40,
                    action_kind="review",
                    fingerprint="thread-two",
                )
                self.assertEqual(next_dispatch.returncode, 0, next_dispatch.stderr)
                state = self._json(
                    self._run(reset_env, "show", {"watch_id": reset_watch})
                )
                self.assertEqual(state["metadata"]["attempts"], "1")
            finally:
                shutil.rmtree(reset_root, ignore_errors=True)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_explicit_rearm_starts_a_fresh_budget_epoch(self):
        root, env = self._repair_fixture("rearm-attempt")
        try:
            handoff = self._run(
                env,
                "handoff",
                dict(
                    self._HANDOFF,
                    active_since="2026-08-29T00:00:00Z",
                    backstop_at="2026-09-01T00:00:00Z",
                ),
            )
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            old_sha = "a" * 40
            for generation, new_sha in (
                (1, "b" * 40),
                (2, "c" * 40),
                (3, "d" * 40),
            ):
                self._complete(
                    env,
                    watch_id,
                    generation=generation,
                    old_sha=old_sha,
                    new_sha=new_sha,
                    action_kind="ci",
                    fingerprint="same failing check",
                )
                old_sha = new_sha
            exhausted = self._dispatch(
                env,
                watch_id,
                generation=4,
                head_sha=old_sha,
                action_kind="ci",
                fingerprint="same failing check",
            )
            self.assertNotEqual(exhausted.returncode, 0)
            self.assertEqual(
                self._json(exhausted)["error"]["code"],
                "attempt-budget-exhausted",
            )
            rearmed = self._run(
                env,
                "handoff",
                dict(
                    self._HANDOFF,
                    head_sha=old_sha,
                    current_sha=old_sha,
                    observed_at="2026-09-02T00:00:00Z",
                    backstop_at="2026-09-05T00:00:00Z",
                    rearm=True,
                ),
            )
            self.assertEqual(rearmed.returncode, 0, rearmed.stderr)
            metadata = self._json(rearmed)["metadata"]
            self.assertEqual(metadata["state"], "watching")
            self.assertEqual(metadata["attempts"], "0")
            self.assertEqual(metadata["attempt_key"], "")
            self.assertEqual(metadata["attempt_limit"], "")
            self.assertEqual(metadata["attempt_history"], "")
            self.assertEqual(metadata["blocker_emitted"], "false")
            self.assertEqual(metadata["active_since"], "2026-09-02T00:00:00Z")
            self.assertEqual(metadata["backstop_at"], "2026-09-05T00:00:00Z")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_explicit_rearm_resets_time_exhaustion_and_defaults_backstop(self):
        root, env = self._repair_fixture("rearm-time")
        try:
            handoff = self._run(
                env,
                "handoff",
                dict(
                    self._HANDOFF,
                    active_since="2026-08-20T00:00:00Z",
                    backstop_at="2026-08-30T00:00:00Z",
                ),
            )
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            exhausted = self._run(
                env,
                "checkpoint",
                {
                    "watch_id": watch_id,
                    "expected_generation": 1,
                    "expected_head_sha": "a" * 40,
                    "observed_head_sha": "a" * 40,
                    "observed_at": "2026-08-20T08:00:00Z",
                    "next_snapshot_at": "2026-08-20T08:05:00Z",
                },
            )
            self.assertEqual(exhausted.returncode, 0, exhausted.stderr)
            self.assertEqual(self._json(exhausted)["state"], "exhausted")
            rearm_payload = dict(
                self._HANDOFF,
                observed_at="2026-08-21T00:00:00Z",
                active_since="2026-08-21T00:00:00Z",
                rearm=True,
            )
            rearm_payload.pop("backstop_at")
            rearmed = self._run(env, "handoff", rearm_payload)
            self.assertEqual(rearmed.returncode, 0, rearmed.stderr)
            metadata = self._json(rearmed)["metadata"]
            self.assertEqual(metadata["state"], "watching")
            self.assertEqual(metadata["attempts"], "0")
            self.assertEqual(metadata["attempt_history"], "")
            self.assertEqual(
                metadata["backstop_at"],
                "2026-08-24T00:00:00Z",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_review_budget_is_two_across_new_heads(self):
        root, env = self._repair_fixture("review-budget")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            self._complete(
                env,
                watch_id,
                generation=1,
                old_sha="a" * 40,
                new_sha="b" * 40,
                action_kind="review",
                fingerprint="same review",
            )
            self._complete(
                env,
                watch_id,
                generation=2,
                old_sha="b" * 40,
                new_sha="c" * 40,
                action_kind="review",
                fingerprint="same review",
            )
            exhausted = self._dispatch(
                env,
                watch_id,
                generation=3,
                head_sha="c" * 40,
                action_kind="review",
                fingerprint="same review",
            )
            self.assertNotEqual(exhausted.returncode, 0)
            self.assertEqual(
                self._json(exhausted)["error"]["code"],
                "attempt-budget-exhausted",
            )
            state = self._json(self._run(env, "show", {"watch_id": watch_id}))
            self.assertEqual(state["metadata"]["state"], "exhausted")
            self.assertEqual(state["metadata"]["attempts"], "2")
            self.assertEqual(
                len(json.loads((root / "gc-calls.json").read_text())),
                2,
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_credential_coupling_and_ambiguous_push_fail_closed(self):
        root, env = self._repair_fixture("credentials")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            coupled = self._dispatch(
                env
                | {
                    "GH_TOKEN": "same-token",
                    "COPILOT_REQUESTS_TOKEN": "same-token",
                },
                watch_id,
                generation=1,
                head_sha="a" * 40,
                action_kind="ci",
                fingerprint="coupled",
            )
            self.assertNotEqual(coupled.returncode, 0)
            self.assertEqual(
                self._json(coupled)["error"]["code"],
                "credential-coupling",
            )
            self.assertEqual(
                json.loads((root / "gc-calls.json").read_text()),
                [],
            )
            records = json.loads((root / "beads.json").read_text())
            self.assertEqual(len(records), 1)

            dispatched = self._dispatch(
                env,
                watch_id,
                generation=1,
                head_sha="a" * 40,
                action_kind="ci",
                fingerprint="ambiguous",
            )
            self.assertEqual(dispatched.returncode, 0, dispatched.stderr)
            action_id = self._json(dispatched)["action_id"]
            recorded = self._run(
                env,
                "record-repair-result",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "expected_old_sha": "a" * 40,
                    "pushed_sha": "b" * 40,
                    "remote_head_sha": "c" * 40,
                    "validation_status": "passed",
                    "make_check_result": "passed",
                },
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            state = self._json(self._run(env, "show", {"watch_id": watch_id}))
            self.assertEqual(state["metadata"]["state"], "blocked")
            self.assertEqual(
                state["metadata"]["terminal_reason"],
                "ambiguous-outcome",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_repair_dispatch_requires_validator_attestation(self):
        root, env = self._repair_fixture("validator-attestation")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            missing = self._dispatch(
                env | {"PR_BABYSIT_VALIDATOR_ATTESTED": ""},
                watch_id,
                generation=1,
                head_sha="a" * 40,
                action_kind="ci",
                fingerprint="validator-attestation",
            )
            self.assertNotEqual(missing.returncode, 0)
            error = self._json(missing)["error"]
            self.assertEqual(error["code"], "credential-validator")
            self.assertEqual(
                json.loads((root / "gc-calls.json").read_text()),
                [],
            )
            records = json.loads((root / "beads.json").read_text())
            self.assertEqual(len(records), 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_check_credentials_requires_validator_attestation(self):
        root, env = self._repair_fixture("check-credentials")
        try:
            valid = self._run(env, "check-credentials")
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertTrue(self._json(valid)["validator_attested"])
            result = self._run(
                env | {"PR_BABYSIT_VALIDATOR_ATTESTED": ""},
                "check-credentials",
            )
            self.assertNotEqual(result.returncode, 0)
            error = self._json(result)["error"]
            self.assertEqual(error["code"], "credential-validator")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_repair_result_preserves_safe_push_failure_reason(self):
        root, env = self._repair_fixture("push-failure-reason")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            dispatched = self._dispatch(
                env,
                watch_id,
                generation=1,
                head_sha="a" * 40,
                action_kind="ci",
                fingerprint="push-failure-reason",
            )
            self.assertEqual(dispatched.returncode, 0, dispatched.stderr)
            action_id = self._json(dispatched)["action_id"]
            recorded = self._run(
                env,
                "record-repair-result",
                {
                    "watch_id": watch_id,
                    "action_id": action_id,
                    "generation": 1,
                    "expected_old_sha": "a" * 40,
                    "validation_status": "failed",
                    "make_check_result": "failed",
                    "reason": "push-failed",
                },
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            records = json.loads((root / "beads.json").read_text())
            action = next(record for record in records if record["id"] == action_id)
            watch = next(record for record in records if record["id"] == watch_id)
            self.assertEqual(action["metadata"]["terminal_reason"], "push-failed")
            self.assertEqual(watch["metadata"]["terminal_reason"], "push-failed")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_formula_attach_failure_blocks_without_dispatch_retry(self):
        root, env = self._repair_fixture("formula-failure")
        try:
            handoff = self._run(env, "handoff", self._HANDOFF)
            self.assertEqual(handoff.returncode, 0, handoff.stderr)
            watch_id = self._json(handoff)["watch_id"]
            failed = self._dispatch(
                env | {"FAKE_GC_FAIL": "1"},
                watch_id,
                generation=1,
                head_sha="a" * 40,
                action_kind="ci",
                fingerprint="formula failure",
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(
                self._json(failed)["error"]["code"],
                "formula-attach",
            )
            state = self._json(self._run(env, "show", {"watch_id": watch_id}))
            self.assertEqual(state["metadata"]["state"], "blocked")
            self.assertEqual(
                state["metadata"]["terminal_reason"],
                "formula-attach-failed",
            )
            self.assertEqual(
                len(json.loads((root / "gc-calls.json").read_text())),
                1,
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
