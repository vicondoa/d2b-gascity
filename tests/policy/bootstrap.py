from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import bootstrap as MODULE


ROOT = pathlib.Path(__file__).resolve().parents[2]


class BootstrapCleanupPolicyTests(unittest.TestCase):
    def _args(self, base: pathlib.Path) -> argparse.Namespace:
        return argparse.Namespace(
            state_root=base / "state",
            city=base / "city",
            rig=base / "rig",
            gc=pathlib.Path("/bin/true"),
            portable_source=ROOT / "city",
            baseline_source=ROOT / "city",
            pack_cache=None,
            d2b_source="https://github.com/vicondoa/d2b.git",
            dolt=None,
            dolt_user_name=None,
            dolt_user_email=None,
            allow_start=False,
            fixture_supervisor=False,
        )

    def test_failed_init_best_effort_stops_and_preserves_original_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw)
            args = self._args(base)
            calls: list[str] = []

            def run(
                _argv: list[object],
                *,
                env: object,
                label: str,
                cwd: pathlib.Path | None = None,
            ) -> None:
                calls.append(label)
                if label == "gc import install":
                    raise MODULE.BootstrapError("original-import-failure")

            with (
                mock.patch.object(MODULE, "_validate_gc_help"),
                mock.patch.object(
                    MODULE,
                    "_validate_portable_source",
                    return_value=MODULE._portable_file_set(ROOT / "city"),
                ),
                mock.patch.object(MODULE, "_configure_dolt_identity"),
                mock.patch.object(MODULE, "_seed_pack_cache"),
                mock.patch.object(MODULE, "_ensure_dolt_schema", return_value=None),
                mock.patch.object(MODULE, "_prepare_rig"),
                mock.patch.object(MODULE, "_initialize_rig_beads"),
                mock.patch.object(MODULE, "_site_binding"),
                mock.patch.object(MODULE, "_run", side_effect=run),
                mock.patch.object(MODULE, "_best_effort_stop") as stop,
            ):
                with self.assertRaisesRegex(
                    MODULE.BootstrapError,
                    "original-import-failure",
                ):
                    MODULE._init(args)

            stop.assert_called_once_with(args.gc, args.city, env=mock.ANY)
            self.assertEqual(
                calls,
                [
                    "gc init --file --preserve-existing --no-start",
                    "gc rig add",
                    "gc import install",
                ],
            )

    def test_successful_init_still_reports_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw)
            args = self._args(base)

            def run(
                _argv: list[object],
                *,
                env: object,
                label: str,
                cwd: pathlib.Path | None = None,
            ) -> None:
                if label == "gc stop --city --force":
                    raise MODULE.BootstrapError("cleanup-failure")

            with (
                mock.patch.object(MODULE, "_validate_gc_help"),
                mock.patch.object(
                    MODULE,
                    "_validate_portable_source",
                    return_value=MODULE._portable_file_set(ROOT / "city"),
                ),
                mock.patch.object(MODULE, "_configure_dolt_identity"),
                mock.patch.object(MODULE, "_seed_pack_cache"),
                mock.patch.object(MODULE, "_ensure_dolt_schema", return_value=None),
                mock.patch.object(MODULE, "_prepare_rig"),
                mock.patch.object(MODULE, "_initialize_rig_beads"),
                mock.patch.object(MODULE, "_site_binding"),
                mock.patch.object(MODULE, "_run", side_effect=run),
                mock.patch.object(MODULE, "_best_effort_stop") as stop,
            ):
                with self.assertRaisesRegex(
                    MODULE.BootstrapError,
                    "cleanup-failure",
                ):
                    MODULE._init(args)

            stop.assert_not_called()

    def test_init_uses_managed_dolt_readiness_timeout_without_fixture_retry(self) -> None:
        source = (ROOT / "scripts" / "bootstrap.py").read_text(encoding="utf-8")
        self.assertIn("GC_DOLT_CONCURRENT_START_READY_TIMEOUT_MS", source)
        self.assertIn("DOLT_START_READY_TIMEOUT_MS", source)
        self.assertNotIn("_dolt_schema_race", source)
        self.assertNotIn("_reset_failed_init", source)

    def test_check_observes_supervisor_first_and_stops_initially_stopped_city(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            args = self._args(pathlib.Path(raw))
            events: list[str] = []

            def run(
                _argv: list[object],
                *,
                env: object,
                label: str,
                cwd: pathlib.Path | None = None,
            ) -> subprocess.CompletedProcess[str]:
                events.append(label)
                stdout = (
                    json.dumps({"rigs": [{"name": "d2b"}]})
                    if label == "gc rig list"
                    else ""
                )
                if label == "gc stop --city --force":
                    events.append("stopped")
                return subprocess.CompletedProcess([], 0, stdout, "")

            def supervisor(_gc: pathlib.Path, _env: object) -> dict[str, object]:
                events.append("gc supervisor status")
                return {"running": False}

            with (
                mock.patch.object(MODULE, "_city_env", return_value={}),
                mock.patch.object(MODULE, "_supervisor_json", side_effect=supervisor),
                mock.patch.object(MODULE, "_validate_gc_help", side_effect=lambda *_: events.append("help")),
                mock.patch.object(MODULE, "_validate_city_state", side_effect=lambda *_: events.append("state")),
                mock.patch.object(MODULE, "_cities_json", return_value={"cities": []}),
                mock.patch.object(MODULE, "_run", side_effect=run),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(MODULE._check(args), 0)

            self.assertEqual(events[0], "gc supervisor status")
            self.assertEqual(events[-1], "stopped")

    def test_successful_check_reports_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            args = self._args(pathlib.Path(raw))

            def run(
                _argv: list[object],
                *,
                env: object,
                label: str,
                cwd: pathlib.Path | None = None,
            ) -> subprocess.CompletedProcess[str]:
                if label == "gc stop --city --force":
                    raise MODULE.BootstrapError("cleanup-failure")
                stdout = (
                    json.dumps({"rigs": [{"name": "d2b"}]})
                    if label == "gc rig list"
                    else ""
                )
                return subprocess.CompletedProcess([], 0, stdout, "")

            with (
                mock.patch.object(MODULE, "_city_env", return_value={}),
                mock.patch.object(MODULE, "_supervisor_json", return_value={"running": False}),
                mock.patch.object(MODULE, "_validate_gc_help"),
                mock.patch.object(MODULE, "_validate_city_state"),
                mock.patch.object(MODULE, "_cities_json", return_value={"cities": []}),
                mock.patch.object(MODULE, "_run", side_effect=run),
                mock.patch("builtins.print"),
            ):
                with self.assertRaisesRegex(MODULE.BootstrapError, "cleanup-failure"):
                    MODULE._check(args)

    def test_check_failure_preserves_original_error_when_cleanup_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            args = self._args(pathlib.Path(raw))

            with (
                mock.patch.object(MODULE, "_city_env", return_value={}),
                mock.patch.object(MODULE, "_supervisor_json", return_value={"running": False}),
                mock.patch.object(MODULE, "_validate_gc_help"),
                mock.patch.object(
                    MODULE,
                    "_validate_city_state",
                    side_effect=MODULE.BootstrapError("original-check-failure"),
                ),
                mock.patch.object(
                    MODULE,
                    "_best_effort_stop",
                    side_effect=MODULE.BootstrapError("cleanup-failure"),
                ) as stop,
            ):
                with self.assertRaisesRegex(
                    MODULE.BootstrapError,
                    "original-check-failure",
                ):
                    MODULE._check(args)

            stop.assert_called_once_with(args.gc, args.city, env=mock.ANY)

    def test_running_delegated_check_does_not_stop_supervisor(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            args = self._args(pathlib.Path(raw))
            calls: list[str] = []

            def run(
                _argv: list[object],
                *,
                env: object,
                label: str,
                cwd: pathlib.Path | None = None,
            ) -> subprocess.CompletedProcess[str]:
                calls.append(label)
                stdout = (
                    json.dumps({"rigs": [{"name": "d2b"}]})
                    if label == "gc rig list"
                    else ""
                )
                return subprocess.CompletedProcess([], 0, stdout, "")

            with (
                mock.patch.object(
                    MODULE,
                    "_city_env",
                    return_value={
                        "GC_SUPERVISOR_SYSTEMD_SCOPE": "system",
                        "GC_SUPERVISOR_SYSTEMD_UNIT": "d2b-gascity.service",
                    },
                ),
                mock.patch.object(MODULE, "_supervisor_json", return_value={"running": True, "pid": 42}),
                mock.patch.object(MODULE, "_validate_gc_help"),
                mock.patch.object(MODULE, "_validate_city_state"),
                mock.patch.object(MODULE, "_cities_json", return_value={"cities": []}),
                mock.patch.object(MODULE, "_run", side_effect=run),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(MODULE._check(args), 0)

            self.assertNotIn("gc stop --city --force", calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
