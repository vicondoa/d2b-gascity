from __future__ import annotations

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


ROOT = pathlib.Path(__file__).resolve().parents[1]
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
            self.assertEqual(len(patches), 24)
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
            "comp" + "ound" + "-engineering",
            "comp" + "ound" + " engineering",
            "copilot-planning-grok",
            "copilot-code-luna",
            "cc.mayor",
        ):
            self.assertNotIn(marker, docs.lower())

    def test_docs_record_blocked_babysitting_and_gate_recovery(
        self,
    ) -> None:
        documents = {
            relative: (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                "README.md",
                "docs/operations.md",
                "docs/testing.md",
            )
        }
        docs_flat = " ".join("\n".join(documents.values()).lower().split())
        for marker in (
            "`ce-babysit-pr`",
            "official pack v2 export",
            "compatible gas city core revision",
            "not imported",
            "not scheduled",
            "existing native `gate-sweep`",
            "target-only",
            "metadata.target=v3",
            "metadata.merge_strategy=pr",
            "no local watcher",
            "human-owned",
            "never approve",
            "force-push",
        ):
            self.assertIn(marker, docs_flat)
        self.assertIn(
            "`ce-babysit-pr` is not imported",
            documents["docs/testing.md"].lower(),
        )
        self.assertIn(
            "`notify-on-human-gate-creation`",
            documents["docs/testing.md"].lower(),
        )
        self.assertIn(
            "`renudge-stale-human-gates`",
            documents["docs/testing.md"].lower(),
        )
        self.assertIn(
            "are not scheduled by the pinned gas city core",
            documents["docs/testing.md"].lower(),
        )
        for marker in (
            "/ce-babysit-pr ",
            "the imported official `ce-babysit-pr` skill",
            "official imported `ce-babysit-pr` skill",
            "schedules both human-gate recovery orders",
            "the selected gas city core schedules both",
            "native supervisor exec orders",
        ):
            self.assertNotIn(marker, docs_flat)

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

        scratch = ROOT / ".tmp"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="native-city-",
            dir=scratch,
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
                city_before = {
                    relative: (source / relative).read_bytes()
                    for relative in AUTHORED_FILES
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
                run_gc("config", "show", "--city", str(city))
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
                (city / "city.toml").write_bytes(
                    city_before[str(CITY_RELATIVE / "city.toml")]
                )
                run_gc("config", "show", "--city", str(city))

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
