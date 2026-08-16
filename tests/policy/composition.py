from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import uuid


ROOT = pathlib.Path(__file__).resolve().parents[2]
CITY = ROOT / "city"
MATRIX = CITY / "role-provider-matrix.json"
INVENTORY = CITY / "worktree-producer-inventory.json"
AGENT_FIXTURE = ROOT / "tests" / "fixtures" / "composition" / "resolved-agents.json"
WORKTREE_FIXTURE = (
    ROOT / "tests" / "fixtures" / "worktree-producers" / "remote-default-main.json"
)
GASCITY_COMMIT = "f6741d94861aa14f0253deffbe9efb1cb3a35d92"
PACK_COMMIT = "5d2a9d023edbb9ba24fdcff554e89fc3d7da72fe"
D2B_V3_COMMIT = "db036097d05ede39009b912805a48f6ef8a74751"


class CompositionPolicyTests(unittest.TestCase):
    def _agents(self) -> dict:
        resolved_config = os.environ.get("U6_RESOLVED_CONFIG")
        if resolved_config:
            raw = json.loads(pathlib.Path(resolved_config).read_text(encoding="utf-8"))
            agents = raw.get("config", {}).get("Agents", [])
            non_model = {
                ("", "dog"),
                ("", "control-dispatcher"),
                ("d2b", "control-dispatcher"),
                ("d2b", "publisher"),
            }
            normalized = []
            for agent in agents:
                identity = (agent.get("Dir", ""), agent["Name"])
                model_backed = identity not in non_model and bool(
                    agent.get("PromptTemplate")
                    or agent.get("Provider")
                    or agent.get("Session") == "acp"
                )
                normalized.append(
                    {
                        "dir": identity[0],
                        "name": identity[1],
                        "model_backed": model_backed,
                    }
                )
            return {
                "generated_from": {
                    "gascity": GASCITY_COMMIT,
                    "gascity_packs": PACK_COMMIT,
                },
                "agents": normalized,
            }
        path = pathlib.Path(os.environ.get("U6_RESOLVED_AGENTS", AGENT_FIXTURE))
        return json.loads(path.read_text(encoding="utf-8"))

    def test_role_matrix_is_complete_against_resolved_model_graph(self) -> None:
        fixture = self._agents()
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        self.assertEqual(matrix["generated_from"]["gascity"], GASCITY_COMMIT)
        self.assertEqual(matrix["generated_from"]["gascity_packs"], PACK_COMMIT)
        resolved = {
            (agent["dir"], agent["name"]): agent
            for agent in fixture["agents"]
            if agent["model_backed"]
        }
        classified = {
            (agent["dir"], agent["name"]): agent for agent in matrix["agents"]
        }
        self.assertEqual(set(classified), set(resolved))
        self.assertEqual(len(classified), len(matrix["agents"]))
        self.assertTrue(set(matrix["categories"]) == {
            "planning-design-decomposition",
            "review-synthesis-triage-analysis",
            "implementation-fix-work",
        })
        self.assertNotIn(("", "dog"), classified)
        self.assertNotIn(("", "control-dispatcher"), classified)
        self.assertNotIn(("d2b", "publisher"), classified)

    def test_every_model_agent_has_exact_acp_patch_and_control_agents_do_not(self) -> None:
        city = tomllib.loads((CITY / "city.toml").read_text(encoding="utf-8"))
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        all_patches = {
            (patch["dir"], patch["name"]): patch
            for patch in city.get("patches", {}).get("agent", [])
        }
        expected = {
            (agent["dir"], agent["name"]): agent for agent in matrix["agents"]
        }
        patches = {
            identity: patch
            for identity, patch in all_patches.items()
            if identity in expected
        }
        self.assertEqual(set(patches), set(expected))
        for identity, entry in expected.items():
            with self.subTest(agent=identity):
                self.assertEqual(patches[identity]["provider"], entry["provider"])
                self.assertEqual(patches[identity]["session"], "acp")
        for identity in (
            ("", "control-dispatcher"),
            ("d2b", "control-dispatcher"),
            ("d2b", "publisher"),
        ):
            self.assertNotIn(identity, patches)

        resolved_config = os.environ.get("U6_RESOLVED_CONFIG")
        if resolved_config:
            raw = json.loads(pathlib.Path(resolved_config).read_text(encoding="utf-8"))
            resolved = {
                (agent.get("Dir", ""), agent["Name"]): agent
                for agent in raw["config"]["Agents"]
            }
            for identity, entry in expected.items():
                with self.subTest(resolved_agent=identity):
                    self.assertEqual(resolved[identity]["Provider"], entry["provider"])
                    self.assertEqual(resolved[identity]["Session"], "acp")

    def test_city_scoped_dog_is_an_exact_suspended_only_control_patch(self) -> None:
        city = tomllib.loads((CITY / "city.toml").read_text(encoding="utf-8"))
        dog_patches = [
            patch
            for patch in city.get("patches", {}).get("agent", [])
            if patch["dir"] == "" and patch["name"] == "dog"
        ]
        self.assertEqual(
            dog_patches,
            [{"dir": "", "name": "dog", "suspended": True}],
        )
        all_patches = {
            (patch["dir"], patch["name"]): patch
            for patch in city.get("patches", {}).get("agent", [])
        }
        for identity in (
            ("", "control-dispatcher"),
            ("d2b", "control-dispatcher"),
        ):
            self.assertNotIn(identity, all_patches)

        fixture = json.loads(AGENT_FIXTURE.read_text(encoding="utf-8"))
        dog = next(
            agent
            for agent in fixture["agents"]
            if agent["dir"] == "" and agent["name"] == "dog"
        )
        self.assertFalse(dog["model_backed"])
        self.assertEqual(dog["scope"], "city")
        self.assertTrue(dog["suspended"])

        resolved_config = os.environ.get("U6_RESOLVED_CONFIG")
        if resolved_config:
            raw = json.loads(pathlib.Path(resolved_config).read_text(encoding="utf-8"))
            resolved = {
                (agent.get("Dir", ""), agent["Name"]): agent
                for agent in raw["config"]["Agents"]
            }
            resolved_dog = resolved[("", "dog")]
            self.assertTrue(resolved_dog["Suspended"])
            self.assertEqual(resolved_dog.get("Provider", ""), "")
            workspace_provider = raw["config"]["Workspace"]["Provider"]
            self.assertEqual(workspace_provider, "copilot-review")
            self.assertEqual(
                resolved_dog.get("Provider", "") or workspace_provider,
                "copilot-review",
            )

    def test_workspace_provider_supplies_fallback(self) -> None:
        city = tomllib.loads((CITY / "city.toml").read_text(encoding="utf-8"))
        workspace = city["workspace"]
        self.assertEqual(workspace["provider"], "copilot-review")
        self.assertIn(workspace["provider"], city["providers"])

    def test_publisher_is_a_deterministic_control_subprocess(self) -> None:
        city = tomllib.loads((CITY / "city.toml").read_text(encoding="utf-8"))
        publisher = next(
            patch
            for patch in city["patches"]["agent"]
            if patch["dir"] == "d2b" and patch["name"] == "publisher"
        )
        self.assertEqual(
            publisher,
            {
                "dir": "d2b",
                "name": "publisher",
                "provider": "publication-worker",
                "session": "tmux",
                "start_command": "d2b-gascity-publication-worker",
                "lifecycle": "one_shot",
                "max_active_sessions": 1,
            },
        )
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        self.assertEqual(
            matrix["control_agents"],
            [
                {
                    "classification": "control/maintenance-subprocess",
                    "dir": "d2b",
                    "lifecycle": "one_shot",
                    "name": "publisher",
                    "provider": "publication-worker",
                    "prompt_mode": "none",
                    "start_command": "d2b-gascity-publication-worker",
                }
            ],
        )
        fixture = json.loads(AGENT_FIXTURE.read_text(encoding="utf-8"))
        resolved = next(
            agent
            for agent in fixture["agents"]
            if agent["dir"] == "d2b" and agent["name"] == "publisher"
        )
        self.assertFalse(resolved["model_backed"])
        self.assertEqual(
            resolved["classification"],
            "control/maintenance-subprocess",
        )

        resolved_config = os.environ.get("U6_RESOLVED_CONFIG")
        if resolved_config:
            raw = json.loads(pathlib.Path(resolved_config).read_text(encoding="utf-8"))
            publisher = next(
                agent
                for agent in raw["config"]["Agents"]
                if agent.get("Dir") == "d2b" and agent.get("Name") == "publisher"
            )
            self.assertEqual(
                {
                    key: publisher[key]
                    for key in (
                        "Provider",
                        "Session",
                        "StartCommand",
                        "Lifecycle",
                        "MaxActiveSessions",
                    )
                },
                {
                    "Provider": "publication-worker",
                    "Session": "tmux",
                    "StartCommand": "d2b-gascity-publication-worker",
                    "Lifecycle": "one_shot",
                    "MaxActiveSessions": 1,
                },
            )
            provider = raw["config"]["Providers"]["publication-worker"]
            self.assertEqual(provider["PromptMode"], "none")
            self.assertFalse(provider["SupportsACP"])
            effective_prompt_mode = publisher.get("PromptMode") or provider["PromptMode"]
            self.assertEqual(effective_prompt_mode, "none")

    def test_roles_are_rig_scoped_and_base_branch_is_v3(self) -> None:
        city = tomllib.loads((CITY / "city.toml").read_text(encoding="utf-8"))
        self.assertNotIn("defaults", city)
        rig = city["rigs"][0]
        self.assertEqual(
            rig["imports"]["roles"],
            {
                "source": "https://github.com/gastownhall/gascity-packs/tree/main/gascity/roles",
                "version": f"sha:{PACK_COMMIT}",
            },
        )
        rig_patches = {
            patch["name"]: patch for patch in city["patches"]["rigs"]
        }
        self.assertEqual(rig_patches["d2b"]["formula_vars"]["base_branch"], "v3")
        self.assertEqual(
            rig_patches["d2b"]["formula_vars"]["base_ref"], "origin/v3"
        )

    def test_inventory_has_every_resolved_worktree_or_base_marker(self) -> None:
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
        self.assertEqual(inventory["generated_from"]["gascity"], GASCITY_COMMIT)
        self.assertEqual(inventory["generated_from"]["gascity_packs"], PACK_COMMIT)
        proof_target = inventory["proof_target"]
        fixture = json.loads(WORKTREE_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(
            set(proof_target),
            {"repository", "branch", "resolved_ref", "origin_v3_commit", "fixture"},
        )
        self.assertEqual(set(fixture), {"schema", "target", "remote"})
        self.assertEqual(
            set(fixture["target"]),
            {"repository", "branch", "resolved_ref", "origin_v3_commit"},
        )
        self.assertEqual(
            set(fixture["remote"]),
            {"default_branch", "main_marker", "v3_marker", "v3_commit_marker"},
        )
        self.assertEqual(proof_target["repository"], "vicondoa/d2b")
        self.assertEqual(proof_target["branch"], "v3")
        self.assertEqual(proof_target["resolved_ref"], "origin/v3")
        self.assertEqual(proof_target["origin_v3_commit"], D2B_V3_COMMIT)
        self.assertEqual(
            proof_target["fixture"],
            "tests/fixtures/worktree-producers/remote-default-main.json",
        )
        self.assertEqual(
            fixture["target"],
            {
                key: proof_target[key]
                for key in ("repository", "branch", "resolved_ref", "origin_v3_commit")
            },
        )
        self.assertEqual(fixture["target"]["origin_v3_commit"], D2B_V3_COMMIT)
        self.assertEqual(fixture["remote"]["default_branch"], "main")
        paths = {(producer["pack"], producer["path"]): producer for producer in inventory["producers"]}
        expected = {
            ("gascity-core", "internal/bootstrap/packs/core/formulas/mol-scoped-work.toml"),
            ("gascity-core", "internal/bootstrap/packs/core/formulas/mol-polecat-commit.toml"),
            ("gascity-core", "internal/bootstrap/packs/core/formulas/mol-polecat-base.toml"),
            ("gascity-core", "internal/bootstrap/packs/core/formulas/mol-review-quorum.toml"),
            ("gascity-roles", "gascity/assets/workflows/do-work/prepare-worktree.md"),
            ("gascity-beads", "examples/bd/template-fragments/bead-worktree.template.md"),
            ("compound-engineering", "skills/ce-work/SKILL.md"),
            ("compound-engineering", "vendor/compound-engineering-plugin/skills/ce-work/SKILL.md"),
        }
        self.assertEqual(set(paths), expected)
        for producer in paths.values():
            self.assertTrue(producer["capabilities"])
            self.assertTrue(producer["markers"])
        override = inventory["required_override"]
        self.assertEqual(override["upstream_commit"], GASCITY_COMMIT)
        self.assertEqual(
            override["path"],
            "city/assets/workflows/do-work/prepare-worktree.md",
        )

    def test_resolved_cache_has_no_unaccounted_creator_markers_when_supplied(self) -> None:
        raw = os.environ.get("U6_PACK_ROOTS")
        if not raw:
            return
        roots = json.loads(raw)
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
        indexed = {(item["pack"], item["path"]): item for item in inventory["producers"]}
        marker_patterns = (
            "git worktree add",
            "symbolic-ref refs/remotes/origin/HEAD",
            "git remote show",
            "origin/{{base_branch}}",
            "base_ref",
        )
        scan_roots = (
            "assets/",
            "commands/",
            "formulas/",
            "skills/",
            "template-fragments/",
            "vendor/",
        )
        # These fields are GitHub API payload metadata, not worktree selectors.
        non_creator_markers = {
            ("gascity-roles", "gascity/assets/scripts/github_api.py", "base_ref"),
            (
                "gascity-roles",
                "gascity/assets/workflows/github-pr-review/snapshot.md",
                "base_ref",
            ),
        }
        found: set[tuple[str, str]] = set()
        for item in roots:
            pack = item["pack"]
            root = pathlib.Path(item["root"])
            prefix = item.get("prefix", "").strip("/")
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                relative = path.relative_to(root).as_posix()
                if not relative.startswith(scan_roots):
                    continue
                indexed_path = f"{prefix}/{relative}" if prefix else relative
                hits = [
                    marker
                    for marker in marker_patterns
                    if marker in text
                    and (pack, indexed_path, marker) not in non_creator_markers
                ]
                if hits:
                    key = (pack, indexed_path)
                    self.assertIn(key, indexed, f"unaccounted producer: {key}")
                    found.add(key)
        self.assertEqual(found, set(indexed))

    def test_override_requires_origin_v3_and_rejects_remote_default(self) -> None:
        override = (CITY / "assets/workflows/do-work/prepare-worktree.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("origin/v3", override)
        self.assertIn("git fetch --prune origin v3", override)
        self.assertIn("gc.publication.base_ref=origin/v3", override)
        self.assertIn("gc.publication.base_sha", override)
        self.assertNotIn("git remote show origin", override)
        self.assertNotRegex(override, r"origin/(?:HEAD|main|master)")

    def test_resolved_publication_step_reaches_local_asset(self) -> None:
        gc = shutil.which("gc")
        self.assertIsNotNone(gc, "gc is required to resolve the pinned Pack graph")
        with tempfile.TemporaryDirectory() as temp:
            resolved_city = pathlib.Path(temp) / "city"
            shutil.copytree(CITY, resolved_city)
            result = subprocess.run(
                [
                    gc,
                    "formula",
                    "show",
                    "compound-build",
                    "--city",
                    str(resolved_city),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        resolved = json.loads(result.stdout)
        publish = next(
            step for step in resolved["steps"] if step["id"] == "compound-build.publish"
        )
        self.assertEqual(publish["metadata"]["gc.run_target"], "gc.publisher")
        self.assertIn("d2b-gascity-publish-pr", publish["description"])
        self.assertIn("gc.publication.expected_head_sha", publish["description"])
        self.assertIn(
            "gc.publication.worker_marker=d2b-gascity-publication-worker-v1",
            publish["description"],
        )
        self.assertIn("gc.publication.push={{push}}", publish["description"])
        self.assertIn("gc.publication.open_pr={{open_pr}}", publish["description"])

    def test_discord_helper_uses_official_gateway_only_seams(self) -> None:
        helper = (ROOT / "scripts" / "discord-import.py").read_text(encoding="utf-8")
        import_helper = helper[
            helper.index("def _import_app") : helper.index("def _bind_dm")
        ]
        bind_helper = helper[helper.index("def _bind_dm") : helper.index("def _parser")]
        self.assertIn(
            '"discord",\n        "import-app"',
            import_helper,
        )
        self.assertIn(
            '"discord",\n            "bind-dm"',
            bind_helper,
        )
        self.assertNotIn('"--city"', import_helper)
        self.assertNotIn("'--city'", import_helper)
        self.assertNotIn('"--city"', bind_helper)
        self.assertNotIn("'--city'", bind_helper)
        self.assertEqual(helper.count("cwd=city"), 2)
        self.assertIn('city = _validate_directory(args.city, "city")', helper)
        self.assertIn('"--bot-token-file"', helper)
        self.assertIn('"/dev/stdin"', helper)
        self.assertIn('"--role-allowlist"', helper)
        self.assertNotIn('"sync-commands"', helper)
        self.assertNotIn('"publish"', helper)
        city_text = (CITY / "city.toml").read_text(encoding="utf-8")
        self.assertNotIn("[services.discord", city_text)

    def test_worktree_creators_start_from_origin_v3(self) -> None:
        fixture = json.loads(WORKTREE_FIXTURE.read_text(encoding="utf-8"))
        remote_spec = fixture["remote"]
        target = fixture["target"]
        base = pathlib.Path(tempfile.mkdtemp(prefix=f"u6-worktree-{uuid.uuid4().hex}-"))
        try:
            remote = base / "remote.git"
            seed = base / "seed"
            self._git(["init", "--bare", str(remote)], ROOT)
            self._git(["init", str(seed)], ROOT)
            self._git(["-C", str(seed), "config", "user.name", "Fixture"], ROOT)
            self._git(["-C", str(seed), "config", "user.email", "fixture@example.invalid"], ROOT)
            (seed / "branch.txt").write_text(remote_spec["main_marker"], encoding="utf-8")
            self._git(["-C", str(seed), "add", "branch.txt"], ROOT)
            self._git(["-C", str(seed), "commit", "-m", "main"], ROOT)
            self._git(["-C", str(seed), "branch", "-M", remote_spec["default_branch"]], ROOT)
            self._git(["-C", str(seed), "remote", "add", "origin", str(remote)], ROOT)
            self._git(["-C", str(seed), "push", "origin", remote_spec["default_branch"]], ROOT)
            self._git(["-C", str(seed), "switch", "-c", target["branch"]], ROOT)
            (seed / "branch.txt").write_text(remote_spec["v3_marker"], encoding="utf-8")
            (seed / "v3-origin-commit.txt").write_text(
                remote_spec["v3_commit_marker"], encoding="utf-8"
            )
            self._git(["-C", str(seed), "add", "branch.txt", "v3-origin-commit.txt"], ROOT)
            self._git(["-C", str(seed), "commit", "-m", target["branch"]], ROOT)
            self._git(["-C", str(seed), "push", "origin", target["branch"]], ROOT)
            self._git(
                ["--git-dir", str(remote), "symbolic-ref", "HEAD", f"refs/heads/{remote_spec['default_branch']}"],
                ROOT,
            )
            launcher = base / "launcher"
            self._git(["clone", str(remote), str(launcher)], ROOT)
            self._git(["-C", str(launcher), "fetch", "--prune", "origin"], ROOT)
            inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
            creators = [p for p in inventory["producers"] if "worktree-add" in p["capabilities"]]
            for index, _producer in enumerate(creators):
                worktree = base / f"worktree-{index}"
                self._git(
                    [
                        "-C",
                        str(launcher),
                        "worktree",
                        "add",
                        "--detach",
                        str(worktree),
                        target["resolved_ref"],
                    ],
                    ROOT,
                )
                self.assertEqual(
                    self._git(["-C", str(worktree), "rev-parse", "HEAD"], ROOT).stdout.strip(),
                    self._git(
                        ["-C", str(launcher), "rev-parse", target["resolved_ref"]], ROOT
                    ).stdout.strip(),
                )
                self.assertEqual((worktree / "branch.txt").read_text(), remote_spec["v3_marker"])
                self.assertEqual(
                    (worktree / "v3-origin-commit.txt").read_text(),
                    remote_spec["v3_commit_marker"],
                )
                self._git(["-C", str(launcher), "worktree", "remove", "--force", str(worktree)], ROOT)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_planted_remote_default_and_removed_override_are_red(self) -> None:
        fixture = json.loads(WORKTREE_FIXTURE.read_text(encoding="utf-8"))
        remote_spec = fixture["remote"]
        target = fixture["target"]
        base = pathlib.Path(
            tempfile.mkdtemp(prefix=f"u6-worktree-negative-{uuid.uuid4().hex}-")
        )
        try:
            remote = base / "remote.git"
            seed = base / "seed"
            self._git(["init", "--bare", str(remote)], ROOT)
            self._git(["init", str(seed)], ROOT)
            self._git(["-C", str(seed), "config", "user.name", "Fixture"], ROOT)
            self._git(["-C", str(seed), "config", "user.email", "fixture@example.invalid"], ROOT)
            (seed / "branch.txt").write_text(remote_spec["main_marker"], encoding="utf-8")
            self._git(["-C", str(seed), "add", "branch.txt"], ROOT)
            self._git(["-C", str(seed), "commit", "-m", "main"], ROOT)
            self._git(["-C", str(seed), "branch", "-M", remote_spec["default_branch"]], ROOT)
            self._git(["-C", str(seed), "remote", "add", "origin", str(remote)], ROOT)
            self._git(["-C", str(seed), "push", "origin", remote_spec["default_branch"]], ROOT)
            self._git(["-C", str(seed), "switch", "-c", target["branch"]], ROOT)
            (seed / "branch.txt").write_text(remote_spec["v3_marker"], encoding="utf-8")
            self._git(["-C", str(seed), "commit", "-am", target["branch"]], ROOT)
            self._git(["-C", str(seed), "push", "origin", target["branch"]], ROOT)
            self._git(
                ["--git-dir", str(remote), "symbolic-ref", "HEAD", f"refs/heads/{remote_spec['default_branch']}"],
                ROOT,
            )
            launcher = base / "launcher"
            self._git(["clone", str(remote), str(launcher)], ROOT)
            self._git(["-C", str(launcher), "fetch", "--prune", "origin"], ROOT)
            worktree = base / "wrong-worktree"
            self._git(
                ["-C", str(launcher), "worktree", "add", "--detach", str(worktree), "origin/HEAD"],
                ROOT,
            )
            self.assertNotEqual((worktree / "branch.txt").read_text(), remote_spec["v3_marker"])
            self._git(["-C", str(launcher), "worktree", "remove", "--force", str(worktree)], ROOT)
            override = (CITY / "assets/workflows/do-work/prepare-worktree.md").read_text(encoding="utf-8")
            planted = override.replace("origin/v3", "origin/HEAD")
            self.assertNotIn("origin/v3", planted)
            self.assertRegex("git remote show origin", r"remote show origin")
        finally:
            shutil.rmtree(base, ignore_errors=True)

    @staticmethod
    def _git(args: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=True,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
