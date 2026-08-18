from __future__ import annotations

import json
import hashlib
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
BOOTSTRAP = ROOT / "scripts" / "bootstrap.py"
PACK_CACHE = os.environ.get("U3_PACK_CACHE")
SCRATCH = pathlib.Path(
    os.environ.get("D2B_GASCITY_CHECK_RUN_ROOT", tempfile.gettempdir())
)


def packaged_binary(name: str) -> pathlib.Path | None:
    explicit = os.environ.get(f"U3_{name.upper()}_BIN")
    if explicit:
        return pathlib.Path(explicit)
    contributor = os.environ.get("GC_CONTRIBUTOR_ROOT")
    if contributor:
        candidate = pathlib.Path(contributor) / "bin" / name
        if candidate.is_file():
            return candidate
    found = shutil.which(name)
    return pathlib.Path(found) if found else None


class BootstrapFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gc = packaged_binary("gc")
        cls.dolt = packaged_binary("dolt")
        if cls.gc is None or cls.dolt is None:
            raise unittest.SkipTest("packaged gc and dolt are required")
        cls.cache_temp: tempfile.TemporaryDirectory[str] | None = None
        if PACK_CACHE:
            cls.pack_cache = pathlib.Path(PACK_CACHE)
            if not cls.pack_cache.is_dir():
                raise RuntimeError("U3_PACK_CACHE does not name a directory")
        else:
            SCRATCH.mkdir(mode=0o700, parents=True, exist_ok=True)
            cls.cache_temp = tempfile.TemporaryDirectory(
                prefix="d2b-gascity-u3-cache-",
                dir=SCRATCH,
            )
            cache_root = pathlib.Path(cls.cache_temp.name)
            city = cache_root / "city"
            shutil.copytree(ROOT / "city", city)
            env = os.environ.copy()
            env.update(
                {
                    "GC_HOME": str(cache_root / "gc"),
                    "GIT_TERMINAL_PROMPT": "0",
                    "NO_COLOR": "1",
                    "PATH": os.pathsep.join(
                        (str(cls.gc.parent), env.get("PATH", os.defpath))
                    ),
                }
            )
            installed = subprocess.run(
                [str(cls.gc), "import", "install", "--city", str(city)],
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=120,
            )
            if installed.returncode != 0:
                raise RuntimeError(
                    "could not seed pinned pack cache: " + installed.stderr[-500:]
                )
            cls.pack_cache = cache_root / "gc" / "cache" / "repos"

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.cache_temp is not None:
            cls.cache_temp.cleanup()

    def setUp(self) -> None:
        short_name = hashlib.sha1(self._testMethodName.encode(), usedforsecurity=False).hexdigest()[:10]
        self.base = SCRATCH / "bootstrap" / short_name
        shutil.rmtree(self.base, ignore_errors=True)
        self.base.mkdir(parents=True)
        self.state = self.base / "state"
        with (
            socket.socket(socket.AF_INET, socket.SOCK_STREAM) as supervisor_probe,
            socket.socket(socket.AF_INET, socket.SOCK_STREAM) as dolt_probe,
        ):
            supervisor_probe.bind(("127.0.0.1", 0))
            dolt_probe.bind(("127.0.0.1", 0))
            self.supervisor_port = int(supervisor_probe.getsockname()[1])
            self.dolt_port = int(dolt_probe.getsockname()[1])
        self.state.mkdir()
        (self.state / "supervisor.toml").write_text(
            f'[supervisor]\nbind = "127.0.0.1"\nport = {self.supervisor_port}\n',
            encoding="utf-8",
        )
        self.city = self.base / "city"
        self.rig = self.base / "rig"
        self.cache = self.base / "pack-cache"
        self.supervisor: subprocess.Popen[str] | None = None
        shutil.copytree(self.pack_cache, self.cache)
        self.origin = self._make_fake_d2b_repository()
        self.env = os.environ.copy()
        self.env.update(
            {
                "GC_HOME": str(self.state),
                "DOLT_ROOT_PATH": str(self.state / "dolt"),
                "GIT_CONFIG_GLOBAL": str(self.state / "gitconfig"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "BD_NON_INTERACTIVE": "1",
                "NO_COLOR": "1",
                "GC_SUPERVISOR_LOG_TEE": "0",
                "GC_DOLT_PORT": str(self.dolt_port),
            }
        )
        subprocess.run(
            [str(self.gc.parent / "bd"), "metrics", "off"],
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def tearDown(self) -> None:
        if self.supervisor is not None and self.supervisor.poll() is None:
            self.supervisor.terminate()
            try:
                self.supervisor.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.supervisor.kill()
                self.supervisor.wait(timeout=10)
        if self.city.exists():
            subprocess.run(
                [str(self.gc), "stop", "--city", str(self.city), "--force"],
                env=self.env,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        shutil.rmtree(self.base, ignore_errors=True)

    def _run_bootstrap(self, mode: str, *extra: str) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(BOOTSTRAP),
            mode,
            "--state-root",
            str(self.state),
            "--city",
            str(self.city),
            "--rig",
            str(self.rig),
            "--gc",
            str(self.gc),
            "--dolt",
            str(self.dolt),
            "--dolt-user-name",
            "fixture",
            "--dolt-user-email",
            "fixture@example.test",
            "--pack-cache",
            str(self.cache),
            *extra,
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
        )
        return result

    def _managed_processes(self) -> list[str]:
        marker = f"GC_HOME={self.state}".encode()
        city_marker = str(self.city).encode()
        processes: list[str] = []
        proc_root = pathlib.Path("/proc")
        if not proc_root.is_dir():
            return processes
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ")
            except (OSError, PermissionError):
                continue
            if city_marker in cmdline:
                processes.append(f"{entry.name}:{cmdline.decode(errors='replace').strip()}")
                continue
            if b"gc" not in cmdline and b"dolt" not in cmdline:
                continue
            try:
                environment = (entry / "environ").read_bytes()
            except (OSError, PermissionError):
                continue
            if marker in environment:
                processes.append(f"{entry.name}:{cmdline.decode(errors='replace').strip()}")
        return processes

    def _assert_no_managed_processes(self) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            processes = self._managed_processes()
            if not processes:
                return
            time.sleep(0.1)
        self.fail("managed process remained: " + "; ".join(processes))

    def _start_fixture_supervisor(self, *, system_delegated: bool = True) -> None:
        if system_delegated:
            self.env.update(
                {
                    "GC_SUPERVISOR_SYSTEMD_UNIT": "d2b-gascity.service",
                    "GC_SUPERVISOR_SYSTEMD_SCOPE": "system",
                }
            )
        self.supervisor = subprocess.Popen(
            [str(self.gc), "supervisor", "run"],
            env=self.env,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(200):
            status = subprocess.run(
                [str(self.gc), "supervisor", "status", "--json"],
                env=self.env,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            if status.returncode == 0 and '"running":true' in status.stdout.replace(" ", ""):
                break
            if self.supervisor.poll() is not None:
                raise RuntimeError("fixture supervisor exited before becoming ready")
            time.sleep(0.1)
        else:
            raise RuntimeError("fixture supervisor did not report running")

    def _make_fake_d2b_repository(self) -> pathlib.Path:
        work = self.base / "d2b-source"
        subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.name", "fixture"], check=True)
        subprocess.run(
            ["git", "-C", str(work), "config", "user.email", "fixture@example.test"],
            check=True,
        )
        (work / "README.md").write_text("fixture\n")
        subprocess.run(["git", "-C", str(work), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(work), "commit", "-qm", "fixture"], check=True)
        subprocess.run(["git", "-C", str(work), "branch", "v3"], check=True)
        origin = self.base / "d2b-origin.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(work), str(origin)], check=True)
        subprocess.run(
            ["git", "--git-dir", str(origin), "symbolic-ref", "HEAD", "refs/heads/main"],
            check=True,
        )
        return origin

    def test_fresh_init_is_stopped_and_pathless(self) -> None:
        result = self._run_bootstrap("init", "--d2b-source", str(self.origin))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.city / ".gc" / "site.toml").is_file())
        self.assertFalse((self.state / "cities.toml").is_file())
        self.assertTrue(json.loads(result.stdout)["no_start"])
        supervisor = subprocess.run(
            [str(self.gc), "supervisor", "status", "--json"],
            env=self.env,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(supervisor.returncode, 0, supervisor.stderr)
        self.assertFalse(json.loads(supervisor.stdout)["running"])

        config = subprocess.run(
            [str(self.gc), "config", "show", "--city", str(self.city), "--validate"],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(config.returncode, 0, config.stderr)
        resolved_config = subprocess.run(
            [str(self.gc), "config", "show", "--city", str(self.city), "--json"],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(resolved_config.returncode, 0, resolved_config.stderr)
        payload = json.loads(resolved_config.stdout.strip().splitlines()[-1])
        resolved_agents = {
            (agent.get("Dir", ""), agent["Name"]): agent
            for agent in payload["config"]["Agents"]
        }
        workspace_provider = payload["config"]["Workspace"]["Provider"]
        self.assertEqual(workspace_provider, "copilot-review")
        self.assertTrue(resolved_agents[("", "dog")]["Suspended"])
        self.assertEqual(resolved_agents[("", "dog")]["Provider"], "")
        self.assertEqual(
            resolved_agents[("", "dog")]["Provider"] or workspace_provider,
            "copilot-review",
        )
        matrix = json.loads(
            (ROOT / "city" / "role-provider-matrix.json").read_text(
                encoding="utf-8"
            )
        )
        expected = {
            (entry["dir"], entry["name"]): entry for entry in matrix["agents"]
        }
        resolved_model = {
            (agent.get("Dir", ""), agent["Name"])
            for agent in payload["config"]["Agents"]
            if (agent.get("Dir", ""), agent["Name"]) in expected
        }
        self.assertEqual(
            resolved_model,
            set(expected),
        )
        for identity, entry in expected.items():
            with self.subTest(resolved_agent=identity):
                self.assertEqual(
                    resolved_agents[identity]["Provider"],
                    entry["provider"],
                )
                self.assertEqual(
                    resolved_agents[identity]["Session"],
                    entry["session"],
                )
        site = (self.city / ".gc" / "site.toml").read_text()
        self.assertIn('workspace_name = "d2b-gascity"', site)
        self.assertIn(str(self.rig), site)
        self.assertNotIn(f'path = "{self.rig}"', (self.city / "city.toml").read_text())
        rig_beads = (self.rig / ".beads" / "config.yaml").read_text(encoding="utf-8")
        self.assertNotRegex(rig_beads, r"(?m)^\s*sync\.remote\s*:")
        remotes = subprocess.run(
            [
                str(self.dolt),
                "--data-dir",
                str(self.city / ".beads" / "dolt"),
                "sql",
                "-q",
                "USE d2b; SELECT name, url FROM dolt_remotes;",
            ],
            env=self.env,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(remotes.returncode, 0, remotes.stderr)
        self.assertNotIn("origin", remotes.stdout)
        self.assertNotIn("git+", remotes.stdout)
        origin_head = subprocess.run(
            [
                "git",
                "-C",
                str(self.rig),
                "symbolic-ref",
                "refs/remotes/origin/HEAD",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(origin_head.stdout.strip(), "refs/remotes/origin/v3")

    def test_repeat_and_partial_init_refuse_before_mutation(self) -> None:
        first = self._run_bootstrap("init", "--d2b-source", str(self.origin))
        self.assertEqual(first.returncode, 0, first.stderr)
        before = (self.city / "city.toml").read_bytes()
        repeat = self._run_bootstrap("init", "--d2b-source", str(self.origin))
        self.assertNotEqual(repeat.returncode, 0)
        self.assertIn("register-existing", repeat.stderr)
        self.assertEqual(before, (self.city / "city.toml").read_bytes())

        partial = self.base / "partial-city"
        partial.mkdir()
        (partial / "city.toml").write_text("[workspace]\nname = 'partial'\n")
        command = [
            sys.executable,
            str(BOOTSTRAP),
            "init",
            "--state-root",
            str(self.base / "partial-state"),
            "--city",
            str(partial),
            "--rig",
            str(self.base / "partial-rig"),
            "--gc",
            str(self.gc),
            "--portable-source",
            str(ROOT / "city"),
        ]
        failed = subprocess.run(command, cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("partial", failed.stderr.lower())

    def test_register_requires_delegation_guard_and_check_is_state_preserving(self) -> None:
        initialized = self._run_bootstrap("init", "--d2b-source", str(self.origin))
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        before = {
            path: path.read_bytes()
            for path in (self.city / "city.toml", self.city / "pack.toml", self.city / "packs.lock")
        }
        refused = self._run_bootstrap("register-existing")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("--allow-start", refused.stderr)

        checked = self._run_bootstrap("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(
            before,
            {
                path: path.read_bytes()
                for path in (self.city / "city.toml", self.city / "pack.toml", self.city / "packs.lock")
            },
        )
        report = json.loads(checked.stdout)
        self.assertEqual(report["city"], str(self.city))
        self.assertFalse(report["registered"])

    def test_stopped_check_leaves_no_managed_child_or_process(self) -> None:
        initialized = self._run_bootstrap("init", "--d2b-source", str(self.origin))
        self.assertEqual(initialized.returncode, 0, initialized.stderr)

        checked = self._run_bootstrap("check")

        self.assertEqual(checked.returncode, 0, checked.stderr)
        supervisor = subprocess.run(
            [str(self.gc), "supervisor", "status", "--json"],
            env=self.env,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(supervisor.returncode, 0, supervisor.stderr)
        self.assertFalse(json.loads(supervisor.stdout)["running"])
        self._assert_no_managed_processes()

    def test_fixture_supervisor_remains_running_during_check(self) -> None:
        initialized = self._run_bootstrap("init", "--d2b-source", str(self.origin))
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self._start_fixture_supervisor(system_delegated=False)

        checked = self._run_bootstrap("check", "--fixture-supervisor")

        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIsNone(
            self.supervisor.poll(),
            "state-preserving check stopped the fixture supervisor",
        )

    def test_fixture_register_is_idempotent(self) -> None:
        initialized = self._run_bootstrap("init", "--d2b-source", str(self.origin))
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self._start_fixture_supervisor()
        first = self._run_bootstrap("register-existing", "--allow-start")
        self.assertEqual(first.returncode, 0, first.stderr)
        listed = subprocess.run(
            [str(self.gc), "rig", "list"],
            env=self.env,
            cwd=self.city,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertNotIn("d2b (suspended)", listed.stdout)
        second = self._run_bootstrap("register-existing", "--allow-start")
        self.assertEqual(second.returncode, 0, second.stderr)
        checked = self._run_bootstrap("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertTrue(json.loads(checked.stdout)["registered"])

    def test_portable_update_refuses_drift(self) -> None:
        initialized = self._run_bootstrap("init", "--d2b-source", str(self.origin))
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        city_toml = self.city / "city.toml"
        current = city_toml.read_text()
        drifted = current.replace(
            'prefix = "d2b"',
            'prefix = "locally-drifted"',
            1,
        )
        self.assertNotEqual(current, drifted)
        city_toml.write_text(drifted)
        candidate = self.base / "candidate-city"
        shutil.copytree(ROOT / "city", candidate)
        update = self._run_bootstrap(
            "portable-update",
            "--portable-source",
            str(candidate),
        )
        self.assertNotEqual(update.returncode, 0)
        self.assertIn("drift", update.stderr.lower())

    def test_portable_update_migrates_legacy_workspace(self) -> None:
        initialized = self._run_bootstrap("init", "--d2b-source", str(self.origin))
        self.assertEqual(initialized.returncode, 0, initialized.stderr)

        legacy = self.base / "legacy-source"
        shutil.copytree(ROOT / "city", legacy)
        legacy_city = legacy / "city.toml"
        legacy_text = legacy_city.read_text(encoding="utf-8").replace(
            '[workspace]\nprovider = "copilot-review"\n\n',
            "",
            1,
        )
        legacy_city.write_text(legacy_text, encoding="utf-8")
        self.assertNotIn("workspace", tomllib.loads(legacy_text))

        runtime_city = self.city / "city.toml"
        runtime_text = runtime_city.read_text(encoding="utf-8").replace(
            '[workspace]\nprovider = "copilot-review"\n\n',
            '[workspace]\nname = "d2b-gascity"\n\n',
            1,
        )
        runtime_city.write_text(runtime_text, encoding="utf-8")
        self.assertEqual(
            tomllib.loads(runtime_text)["workspace"],
            {"name": "d2b-gascity"},
        )

        update = self._run_bootstrap(
            "portable-update",
            "--baseline-source",
            str(legacy),
            "--portable-source",
            str(ROOT / "city"),
        )
        self.assertEqual(update.returncode, 0, update.stderr)
        self.assertIn("city.toml", json.loads(update.stdout)["updated"])
        self.assertEqual(
            tomllib.loads(runtime_city.read_text(encoding="utf-8"))["workspace"],
            {"provider": "copilot-review"},
        )

        checked = self._run_bootstrap("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        config = subprocess.run(
            [str(self.gc), "config", "show", "--city", str(self.city), "--validate"],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(config.returncode, 0, config.stderr)

    def test_symlink_city_target_is_refused(self) -> None:
        actual = self.base / "actual-city"
        actual.mkdir()
        link = self.base / "city-link"
        link.symlink_to(actual, target_is_directory=True)
        command = [
            sys.executable,
            str(BOOTSTRAP),
            "init",
            "--state-root",
            str(self.base / "state"),
            "--city",
            str(link),
            "--rig",
            str(self.base / "rig"),
            "--gc",
            str(self.gc),
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr.lower())

    def test_existing_rig_must_be_checked_out_on_v3(self) -> None:
        subprocess.run(
            ["git", "clone", "-q", str(self.origin), str(self.rig)],
            check=True,
        )
        branch = subprocess.run(
            ["git", "-C", str(self.rig), "branch", "--show-current"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(branch.stdout.strip(), "main")
        result = self._run_bootstrap("init")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checked out on v3", result.stderr)


if __name__ == "__main__":
    unittest.main()
