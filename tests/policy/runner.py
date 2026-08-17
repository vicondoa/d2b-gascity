from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import tests.run as runner
from tests.run import _owned_processes, _stop_group, process_snapshot


ROOT = pathlib.Path(__file__).resolve().parents[2]


class RunnerOwnershipPolicyTests(unittest.TestCase):
    def test_run_id_process_ownership_does_not_cross_concurrent_runs(self) -> None:
        before = process_snapshot()
        owned_environment = os.environ.copy()
        owned_environment["D2B_GASCITY_CHECK_RUN_ID"] = "u9-owned-run"
        other_environment = os.environ.copy()
        other_environment["D2B_GASCITY_CHECK_RUN_ID"] = "u9-other-run"
        owned = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=ROOT,
            env=owned_environment,
            start_new_session=True,
        )
        other = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=ROOT,
            env=other_environment,
            start_new_session=True,
        )
        try:
            after: dict[int, object] = {}
            for _ in range(50):
                after = process_snapshot()
                if owned.pid in after and other.pid in after:
                    break
                time.sleep(0.02)
            selected = _owned_processes(
                before,
                after,
                roots=(owned.pid,),
                run_id="u9-owned-run",
            )
            selected_pids = {info.pid for info in selected}
            self.assertIn(owned.pid, selected_pids)
            self.assertNotIn(other.pid, selected_pids)
            for info in selected:
                _stop_group(info.pgid)
            self.assertIsNone(other.poll())
        finally:
            if owned.poll() is None:
                _stop_group(os.getpgid(owned.pid))
            owned.wait(timeout=5)
            if other.poll() is None:
                _stop_group(os.getpgid(other.pid))
            other.wait(timeout=5)

    def test_runtime_commands_use_contributor_python(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-runtime-python-") as directory:
            runtime = pathlib.Path(directory)
            python = runtime / "bin" / "python3"
            python.parent.mkdir(parents=True)
            python.write_text("#!/bin/sh\n", encoding="utf-8")
            python.chmod(0o755)
            env = {
                "D2B_GASCITY_CHECK_RUN_ID": "u9-runtime-python",
                "D2B_GASCITY_CHECK_RUN_ROOT": directory,
                "GC_CONTRIBUTOR_ROOT": str(runtime),
            }
            seen: list[list[str]] = []

            def capture(command: list[str], **_kwargs: object) -> object:
                seen.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(runner, "_run_command", side_effect=capture):
                runner._run_python_policy(env)
                runner._run_acceptance(env)
                runner._run_rollback(env)
                runner._run_generated(env)
                runner._run_privacy(env)
                runner._run_static(env)

        self.assertTrue(seen)
        for command in seen:
            with self.subTest(command=command):
                self.assertEqual(command[0], str(python))

    def test_python_only_commands_skip_runtime_and_pack_setup(self) -> None:
        commands = {
            "generated": "_run_generated",
            "privacy": "_run_privacy",
            "rollback": "_run_rollback",
            "static": "_run_static",
            "update-generated": "_run_generated",
        }
        for command, operation in commands.items():
            with self.subTest(command=command):
                with (
                    mock.patch.object(runner, "_ensure_runtime") as ensure_runtime,
                    mock.patch.object(runner, "_ensure_pack_cache") as ensure_pack_cache,
                    mock.patch.object(runner, operation) as run_operation,
                ):
                    self.assertEqual(runner.run(command), 0)
                ensure_runtime.assert_not_called()
                ensure_pack_cache.assert_not_called()
                run_operation.assert_called_once()

    def test_per_run_roots_are_external_unique_private_and_exactly_cleaned(self) -> None:
        first_id, first = runner._create_run_root()
        second_id, second = runner._create_run_root()
        try:
            self.assertNotEqual(first_id, second_id)
            self.assertNotEqual(first, second)
            self.assertFalse(first.is_relative_to(ROOT))
            self.assertFalse(second.is_relative_to(ROOT))
            self.assertEqual(first.stat().st_mode & 0o777, 0o700)
            self.assertEqual(second.stat().st_mode & 0o777, 0o700)
        finally:
            runner.cleanup_scratch(first)
            runner.cleanup_scratch(second)
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
