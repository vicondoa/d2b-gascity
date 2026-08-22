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
PACK_COMMIT = "5d2a9d023edbb9ba24fdcff554e89fc3d7da72fe"
SLACK_PACK_SOURCE = (
    "https://github.com/gastownhall/gascity-packs/tree/main/slack-full"
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
AUTHORED_FILES = (
    "city.toml",
    "pack.toml",
    "packs.lock",
    "assets/workflows/do-work/prepare-worktree.md",
    "assets/workflows/build-base/publish.md",
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
    def test_root_layout_has_only_authored_city_files(self) -> None:
        for relative in AUTHORED_FILES:
            self.assertTrue((ROOT / relative).is_file(), relative)

        for relative in (
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

    def test_city_has_one_pathless_d2b_rig_and_stock_codex_provider(
        self,
    ) -> None:
        path = ROOT / "city.toml"
        text = path.read_text(encoding="utf-8")
        config = tomllib.loads(text)

        self.assertNotIn("api", config)
        self.assertNotIn("suspended_on_start", config)
        self.assertNotIn("[[session]]", text.lower())
        self.assertNotIn("[session]", text.lower())
        self.assertIn("[[named_session]]", text.lower())

        rigs = config["rigs"]
        self.assertEqual(len(rigs), 1)
        self.assertEqual(
            {key: rigs[0][key] for key in ("name", "prefix", "default_branch")},
            {"name": "d2b", "prefix": "d2b", "default_branch": "v3"},
        )
        self.assertNotIn("path", rigs[0])
        self.assertEqual(
            rigs[0]["imports"]["gc"],
            {
                "source": (
                    "https://github.com/gastownhall/"
                    "gascity-packs/tree/main/gascity/roles"
                ),
                "version": f"sha:{PACK_COMMIT}",
            },
        )

        self.assertEqual(
            set(config["providers"]),
            {"codex"},
        )
        self.assertEqual(
            config["workspace"],
            {"name": "d2b-gascity", "provider": "codex"},
        )
        provider = config["providers"]["codex"]
        self.assertEqual(provider["base"], "builtin:codex")
        self.assertEqual(provider["option_defaults"], {"model": ""})
        for key in ("args", "command", "env"):
            self.assertNotIn(key, provider)
        for marker in (
            "builtin:copilot",
            "COPILOT_GITHUB_TOKEN",
            "GH_TOKEN",
            "--model",
            "gpt-",
            "grok-",
        ):
            self.assertNotIn(marker, text)

        patches = config["patches"]
        self.assertEqual(
            patches["rigs"],
            [
                {
                    "name": "d2b",
                    "formula_vars": {
                        "base_branch": "v3",
                        "base_ref": "origin/v3",
                    },
                }
            ],
        )
        self.assertEqual(
            patches["agent"],
            [
                {
                    "dir": "d2b",
                    "name": "ce-pr-comment-resolver",
                    "provider": "codex",
                },
                {
                    "append_fragments": ["slack-v0"],
                    "dir": "d2b",
                    "name": "codex",
                },
            ]
            + [
                {
                    "dir": "d2b",
                    "name": name,
                    "provider": "codex",
                }
                for name in (
                    "ce-work",
                    "implementation-worker",
                    "publisher",
                )
            ],
        )
        self.assertTrue(
            all(
                set(patch) <= {"append_fragments", "dir", "name", "provider"}
                for patch in patches["agent"]
            )
        )

    def test_city_has_no_obsolete_routing_or_delivery_verification(self) -> None:
        text = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
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
        pack = tomllib.loads((ROOT / "pack.toml").read_text(encoding="utf-8"))
        self.assertEqual(pack["pack"]["schema"], 2)
        self.assertEqual(
            {
                name: import_config["version"]
                for name, import_config in pack["imports"].items()
            },
            {
                "core": f"sha:{GASCITY_COMMIT}",
                "bd": f"sha:{GASCITY_COMMIT}",
                "gc": f"sha:{PACK_COMMIT}",
                "compound-engineering": f"sha:{PACK_COMMIT}",
                "discord": f"sha:{PACK_COMMIT}",
                "slack-full": f"sha:{PACK_COMMIT}",
            },
        )
        self.assertEqual(
            pack["imports"]["slack-full"],
            {"source": SLACK_PACK_SOURCE, "version": f"sha:{PACK_COMMIT}"},
        )

        self.assertNotIn("service", pack)
        for relative in (
            "slack-full",
            "gc-slack-adapter",
            "gc-slack-cli",
        ):
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_lock_and_v3_workflow_shadows_are_pinned(self) -> None:
        lock = tomllib.loads((ROOT / "packs.lock").read_text(encoding="utf-8"))
        expected = {
            (
                "https://github.com/gastownhall/"
                "gascity-packs/tree/main/compound-engineering"
            ): PACK_COMMIT,
            (
                "https://github.com/gastownhall/"
                "gascity-packs/tree/main/discord"
            ): PACK_COMMIT,
            SLACK_PACK_SOURCE: PACK_COMMIT,
            (
                "https://github.com/gastownhall/"
                "gascity-packs/tree/main/gascity/roles"
            ): PACK_COMMIT,
            (
                "https://github.com/gastownhall/"
                "gascity-packs/tree/main/gascity"
            ): PACK_COMMIT,
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
        for source, commit in expected.items():
            self.assertEqual(lock["packs"][source]["version"], f"sha:{commit}")
            self.assertEqual(lock["packs"][source]["commit"], commit)

        worktree = (
            ROOT / "assets/workflows/do-work/prepare-worktree.md"
        ).read_text(encoding="utf-8")
        publish = (
            ROOT / "assets/workflows/build-base/publish.md"
        ).read_text(encoding="utf-8")
        self.assertIn("git fetch --prune origin v3", worktree)
        self.assertIn('git worktree add "$WORKTREE" --detach origin/v3', worktree)
        self.assertIn("gc.publication.base_sha", worktree)
        self.assertNotIn("DEFAULT_BRANCH", worktree)
        for marker in (
            "gc.publication.base_ref",
            "gc.publication.base_sha",
            "vicondoa/d2b",
            "v3",
            "push",
            "open_pr",
            "fail closed",
        ):
            self.assertIn(marker, publish)
        self.assertIn("never merge", publish.lower())
        self.assertIn("never force-push", publish.lower())

    def test_docs_record_host_inheritance_and_slack_credential_boundaries(
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
            )
        )
        for marker in (
            SLACK_PACK_SOURCE,
            "sha:" + PACK_COMMIT,
            "gc-slack-adapter/env",
            "0600",
            "GC_CITY_NAME",
            "GC_CITY_PATH",
            "GC_API_BASE_URL",
            "slack-v0",
            "gc slack-full reply-current",
            "d2b/roles.run-operator",
            "SLACK_CLIENT_ID",
            "SLACK_REDIRECT_URI",
            "apps.json",
            "http_status:404",
            "gc-slack-adapter",
            "gc-slack-cli",
            "Copilot Requests",
            "GH_TOKEN",
        ):
            self.assertIn(marker, docs)
        self.assertIn("source-only", docs.lower())
        self.assertIn("credential separation", docs.lower())

    def test_discord_import_has_no_public_site_mapping(self) -> None:
        text = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in ("city.toml", "pack.toml")
        ).lower()
        for marker in (
            "public_base_domain",
            "interactions_url",
            "external_route",
            "guild_id",
            "channel_id",
            "user_mapping",
        ):
            self.assertNotIn(marker, text)

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
                city = root / "city"
                rig = root / "rig"
                home = root / "home"
                gc_home = root / "gc-home"
                git_config = root / "git-config"
                tool_bin = root / "tools"
                city.mkdir()
                rig.mkdir()
                home.mkdir()
                gc_home.mkdir()
                tool_bin.mkdir()

                for relative in AUTHORED_FILES:
                    destination = city / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / relative, destination)
                city_before = {
                    relative: (city / relative).read_bytes()
                    for relative in AUTHORED_FILES
                }

                env = os.environ.copy()
                env.update(
                    {
                        "HOME": str(home),
                        "GC_HOME": str(gc_home),
                        "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_CONFIG_GLOBAL": str(git_config),
                        "GIT_AUTHOR_NAME": "Gas City Test",
                        "GIT_AUTHOR_EMAIL": "gas-city-test@example.invalid",
                        "GIT_COMMITTER_NAME": "Gas City Test",
                        "GIT_COMMITTER_EMAIL": "gas-city-test@example.invalid",
                    }
                )
                _git(["init", "--quiet", "-b", "main"], cwd=city, env=env)
                _git(["init", "--quiet", "-b", "v3"], cwd=rig, env=env)
                for repository in (city, rig):
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

                codex = tool_bin / "codex"
                true = shutil.which("true")
                self.assertIsNotNone(true)
                codex.symlink_to(true)
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
                        (city / relative).read_bytes(),
                        contents,
                    )
                run_gc("config", "show", "--city", str(city))
                run_gc("import", "check", "--city", str(city))
                run_gc(
                    "rig",
                    "add",
                    str(rig),
                    "--name",
                    "d2b",
                    "--city",
                    str(city),
                )
                run_gc("config", "show", "--city", str(city))

                site = city / ".gc" / "site.toml"
                self.assertTrue(site.is_file())
                site_text = site.read_text(encoding="utf-8")
                self.assertIn(f'path = "{rig}"', site_text)
                self.assertIn('name = "d2b"', site_text)
                native_city = tomllib.loads(
                    (city / "city.toml").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    {
                        key: native_city["rigs"][0][key]
                        for key in ("name", "prefix", "default_branch")
                    },
                    {"name": "d2b", "prefix": "d2b", "default_branch": "v3"},
                )
                self.assertNotIn("path", native_city["rigs"][0])
                for relative in AUTHORED_FILES:
                    self.assertNotIn(
                        str(rig).encode(),
                        (city / relative).read_bytes(),
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
