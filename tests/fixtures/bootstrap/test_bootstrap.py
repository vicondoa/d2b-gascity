from __future__ import annotations

import json
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
BOOTSTRAP = ROOT / "scripts" / "bootstrap.py"
PACK_CACHE = os.environ.get("U3_PACK_CACHE")


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
            cls.cache_temp = tempfile.TemporaryDirectory(prefix="d2b-gascity-u3-cache-")
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
        self.base = ROOT / ".scratch" / "u3b" / short_name
        shutil.rmtree(self.base, ignore_errors=True)
        self.base.mkdir(parents=True)
        self.state = self.base / "state"
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
            }
        )

    def tearDown(self) -> None:
        if self.supervisor is not None and self.supervisor.poll() is None:
            self.supervisor.terminate()
            try:
                self.supervisor.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.supervisor.kill()
                self.supervisor.wait(timeout=10)
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
        return subprocess.run(
            command,
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
        )

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
        site = (self.city / ".gc" / "site.toml").read_text()
        self.assertIn(str(self.rig), site)
        self.assertNotIn(f'path = "{self.rig}"', (self.city / "city.toml").read_text())

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

    def test_register_requires_delegation_guard_and_check_is_read_only(self) -> None:
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

    def test_fixture_register_is_idempotent(self) -> None:
        initialized = self._run_bootstrap("init", "--d2b-source", str(self.origin))
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
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
        for _ in range(50):
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
            time.sleep(0.1)
        first = self._run_bootstrap("register-existing", "--allow-start")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self._run_bootstrap("register-existing", "--allow-start")
        self.assertEqual(second.returncode, 0, second.stderr)
        checked = self._run_bootstrap("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertTrue(json.loads(checked.stdout)["registered"])

    def test_portable_update_refuses_drift(self) -> None:
        initialized = self._run_bootstrap("init", "--d2b-source", str(self.origin))
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        city_toml = self.city / "city.toml"
        city_toml.write_text(city_toml.read_text() + "\n# local drift\n")
        candidate = self.base / "candidate-city"
        shutil.copytree(ROOT / "city", candidate)
        update = self._run_bootstrap(
            "portable-update",
            "--portable-source",
            str(candidate),
        )
        self.assertNotEqual(update.returncode, 0)
        self.assertIn("drift", update.stderr.lower())

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
