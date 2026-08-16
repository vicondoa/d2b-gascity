from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "discord-import.py"
FAKE_GC = pathlib.Path(__file__).with_name("fake_gc.py")
SNOWFLAKES = {
    "application": "123456789012345678",
    "guild": "223456789012345678",
    "channel": "323456789012345678",
    "role": "423456789012345678",
    "operator_a": "523456789012345678",
    "operator_b": "623456789012345678",
}
PUBLIC_KEY = "ab" * 32
TOKEN = "fixture-discord-token-not-for-output"


class DiscordImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tempdir.name)
        self.state = self.base / "state"
        self.city = self.base / "city"
        self.state.mkdir(mode=0o700)
        self.city.mkdir(mode=0o700)
        self.token_file = self.base / "token"
        self.token_file.write_text(TOKEN + "\n", encoding="utf-8")
        self.token_file.chmod(0o600)
        self.fake_gc = self.base / "gc"
        shutil.copy2(FAKE_GC, self.fake_gc)
        self.fake_gc.chmod(0o700)
        self.log = self.state / "fake-gc.jsonl"
        self.environment = dict(
            os.environ,
            UNRELATED_SECRET="must-not-reach-gc",
            GITHUB_TOKEN="must-not-reach-gc",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _command(self, *extra: str) -> list[str]:
        return [
            sys.executable,
            str(SCRIPT),
            "--gc",
            str(self.fake_gc),
            "--state-root",
            str(self.state),
            "--city",
            str(self.city),
            "--token-file",
            str(self.token_file),
            "--application-id",
            SNOWFLAKES["application"],
            "--public-key",
            PUBLIC_KEY,
            "--guild-id",
            SNOWFLAKES["guild"],
            "--channel-id",
            SNOWFLAKES["channel"],
            "--operator-role-id",
            SNOWFLAKES["role"],
            *extra,
        ]

    def _run(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self._command(*extra),
            cwd=ROOT,
            env=self.environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def _events(self) -> list[dict[str, object]]:
        if not self.log.exists():
            return []
        return [
            json.loads(line)
            for line in self.log.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def test_import_binds_every_operator_and_keeps_token_out_of_outputs(self) -> None:
        result = self._run(
            "--operator-user-id",
            f"{SNOWFLAKES['operator_a']}=d2b/sky",
            "--operator-user-id",
            f"{SNOWFLAKES['operator_b']}=d2b/review",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "discord-import: imported default app; bound 2 operator DM(s)\n",
        )
        self.assertNotIn(TOKEN, result.stdout + result.stderr)

        events = self._events()
        self.assertEqual([event["kind"] for event in events], ["import-app", "bind-dm", "bind-dm"])
        import_event = events[0]
        argv = import_event["argv"]
        self.assertTrue(import_event["stdin_present"])
        self.assertEqual(
            import_event["stdin_sha256"],
            hashlib.sha256((TOKEN + "\n").encode()).hexdigest(),
        )
        self.assertNotIn(TOKEN, json.dumps(events))
        self.assertTrue(all(event["environment"]["gc_home"] == str(self.state) for event in events))
        self.assertTrue(all(not event["environment"]["unrelated_secret_present"] for event in events))
        self.assertTrue(all(not event["environment"]["github_token_present"] for event in events))
        self.assertIn("--bot-token-file", argv)
        self.assertIn("/dev/stdin", argv)
        for flag, value in (
            ("--guild-allowlist", SNOWFLAKES["guild"]),
            ("--channel-allowlist", SNOWFLAKES["channel"]),
            ("--role-allowlist", SNOWFLAKES["role"]),
        ):
            self.assertEqual(argv.count(flag), 1)
            self.assertIn(value, argv)
        self.assertIn(SNOWFLAKES["application"], argv)
        self.assertIn(PUBLIC_KEY, argv)
        bound = {tuple(event["argv"][-2:]) for event in events[1:]}
        self.assertEqual(
            bound,
            {
                (SNOWFLAKES["operator_a"], "d2b/sky"),
                (SNOWFLAKES["operator_b"], "d2b/review"),
            },
        )
        self.assertFalse(any(event.get("kind") == "forbidden-publication" for event in events))

    def test_rotation_reimports_same_app_with_new_token(self) -> None:
        first = self._run("--operator-user-id", f"{SNOWFLAKES['operator_a']}=d2b/sky")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.token_file.write_text("rotated-fixture-token\n", encoding="utf-8")
        self.token_file.chmod(0o600)
        second = self._run("--operator-user-id", f"{SNOWFLAKES['operator_a']}=d2b/sky")
        self.assertEqual(second.returncode, 0, second.stderr)
        imports = [event for event in self._events() if event["kind"] == "import-app"]
        self.assertEqual(len(imports), 2)
        self.assertNotEqual(imports[0]["stdin_sha256"], imports[1]["stdin_sha256"])

    def test_rejects_bad_ids_sessions_and_required_boundary(self) -> None:
        cases = (
            ("--application-id", "bad"),
            ("--application-id", "000000000000000000"),
            ("--public-key", "not-hex"),
            ("--guild-id", "bad"),
            ("--channel-id", "bad"),
            ("--operator-role-id", "bad"),
            ("--operator-user-id", f"{SNOWFLAKES['operator_a']}=bad session"),
            ("--token-file", "token"),
            ("--state-root", "state"),
            ("--city", "city"),
            ("--gc", "gc"),
        )
        for option, value in cases:
            with self.subTest(option=option):
                result = self._run(
                    "--operator-user-id",
                    f"{SNOWFLAKES['operator_a']}=d2b/sky",
                    option,
                    value,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(TOKEN, result.stdout + result.stderr)
        missing_role = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--gc",
                str(self.fake_gc),
                "--state-root",
                str(self.state),
                "--city",
                str(self.city),
                "--token-file",
                str(self.token_file),
                "--application-id",
                SNOWFLAKES["application"],
                "--public-key",
                PUBLIC_KEY,
                "--guild-id",
                SNOWFLAKES["guild"],
                "--channel-id",
                SNOWFLAKES["channel"],
            ],
            cwd=ROOT,
            env=self.environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(missing_role.returncode, 0)
        self.assertEqual(self._events(), [])

    def test_rejects_symlink_and_world_readable_token_files(self) -> None:
        target = self.base / "real-token"
        target.write_text(TOKEN + "\n", encoding="utf-8")
        target.chmod(0o600)
        self.token_file.unlink()
        self.token_file.symlink_to(target)
        symlink_result = self._run("--operator-user-id", f"{SNOWFLAKES['operator_a']}=d2b/sky")
        self.assertNotEqual(symlink_result.returncode, 0)
        self.assertEqual(self._events(), [])

        self.token_file.unlink()
        self.token_file.write_text(TOKEN + "\n", encoding="utf-8")
        self.token_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IROTH)
        mode_result = self._run("--operator-user-id", f"{SNOWFLAKES['operator_a']}=d2b/sky")
        self.assertNotEqual(mode_result.returncode, 0)
        self.assertNotIn(TOKEN, mode_result.stdout + mode_result.stderr)
        self.assertEqual(self._events(), [])


if __name__ == "__main__":
    unittest.main()
