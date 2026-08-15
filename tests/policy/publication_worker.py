from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "publication-worker.py"
FAKE_GC = ROOT / "tests" / "fixtures" / "publication_worker" / "fake_gc.py"
FAKE_HELPER = ROOT / "tests" / "fixtures" / "publication_worker" / "fake_helper.py"
HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40
WORKFLOW_ID = "workflow-fixture"
CONVOY_ID = "convoy-fixture"
SOURCE_ID = "source-fixture"
STEP_ID = "publish-fixture"
MARKER = "gc.publication.worker_marker=d2b-gascity-publication-worker-v1"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "publication_worker_script",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load publication worker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


class PublicationWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = ROOT / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.tempdir = tempfile.TemporaryDirectory(dir=scratch)
        self.base = pathlib.Path(self.tempdir.name)
        self.rig = self.base / "rig"
        self.rig.mkdir()
        self.source = self.base / "source"
        self._git(["init", str(self.source)])
        self._git(["-C", str(self.source), "config", "user.name", "Fixture"])
        self._git(
            ["-C", str(self.source), "config", "user.email", "fixture@example.invalid"]
        )
        (self.source / "file.txt").write_text("fixture\n", encoding="utf-8")
        self._git(["-C", str(self.source), "add", "file.txt"])
        self._git(["-C", str(self.source), "commit", "-m", "fixture"])
        self.head_sha = subprocess.run(
            ["git", "-C", str(self.source), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        self.artifacts = self.base / "artifacts"
        self.artifacts.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        (self.bin / "gc").symlink_to(FAKE_GC)
        (self.bin / "d2b-gascity-publish-pr").symlink_to(FAKE_HELPER)
        self.gc_state_path = self.base / "gc-state.json"
        self.helper_state_path = self.base / "helper-state.json"
        self._write_state(self._default_gc_state())
        self._write_helper(
            {
                "mode": "success",
                "record": {
                    "version": 1,
                    "status": "open",
                    "repository": "vicondoa/d2b",
                    "base": "v3",
                    "branch": f"gascity/{SOURCE_ID}",
                    "work_id": SOURCE_ID,
                    "head_sha": self.head_sha,
                    "number": 17,
                    "url": "https://github.com/vicondoa/d2b/pull/17",
                    "beads_record": {
                        "publication_url": "https://github.com/vicondoa/d2b/pull/17",
                        "publication_sha": self.head_sha,
                        "publication_branch": f"gascity/{SOURCE_ID}",
                    },
                },
                "calls": [],
            }
        )
        self.env = {
            "PATH": (
                f"{self.bin}:{pathlib.Path(sys.executable).parent}:"
                f"{os.defpath}"
            ),
            "FAKE_GC_STATE": str(self.gc_state_path),
            "FAKE_HELPER_STATE": str(self.helper_state_path),
            "GC_ARTIFACT_DIR": str(self.artifacts),
            "CREDENTIALS_DIRECTORY": str(self.base / "credentials"),
        }
        pathlib.Path(self.env["CREDENTIALS_DIRECTORY"]).mkdir()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _default_gc_state(self) -> dict[str, object]:
        description = self._description(push=True, open_pr=True)
        return {
            "claims": [
                {
                    "schema_version": "1",
                    "ok": True,
                    "command": "hook",
                    "action": "work",
                    "reason": "claimed",
                    "bead_id": STEP_ID,
                    "assignee": "d2b/publisher",
                    "root_bead_id": WORKFLOW_ID,
                    "continuation_group": "",
                }
            ],
            "beads": {
                STEP_ID: {
                    "id": STEP_ID,
                    "description": description,
                    "metadata": {
                        "gc.root_bead_id": WORKFLOW_ID,
                        "gc.run_target": "gc.publisher",
                    },
                },
                WORKFLOW_ID: {
                    "id": WORKFLOW_ID,
                    "metadata": {
                        "gc.input_convoy_id": SOURCE_ID,
                        "gc.work_dir": str(self.rig),
                    },
                },
                CONVOY_ID: {
                    "id": CONVOY_ID,
                    "metadata": {},
                },
                SOURCE_ID: {
                    "id": SOURCE_ID,
                    "metadata": {
                        "work_dir": str(self.source),
                        "gc.publication.base_ref": "origin/v3",
                        "gc.publication.base_sha": BASE_SHA,
                    },
                },
            },
            "calls": [],
            "closes": [],
            "updates": [],
            "drain_acks": 0,
        }

    def _description(self, *, push: bool, open_pr: bool, marker: str = MARKER) -> str:
        return "\n".join(
            (
                marker,
                f"gc.publication.push={'true' if push else 'false'}",
                f"gc.publication.open_pr={'true' if open_pr else 'false'}",
            )
        )

    def _write_state(self, state: dict[str, object]) -> None:
        self.gc_state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")

    def _write_helper(self, state: dict[str, object]) -> None:
        self.helper_state_path.write_text(
            json.dumps(state, sort_keys=True),
            encoding="utf-8",
        )

    def _state(self) -> dict[str, object]:
        return json.loads(self.gc_state_path.read_text(encoding="utf-8"))

    def _helper_state(self) -> dict[str, object]:
        return json.loads(self.helper_state_path.read_text(encoding="utf-8"))

    def _run_worker(self) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with mock.patch.dict(os.environ, self.env, clear=False), redirect_stdout(
            stdout
        ), redirect_stderr(stderr):
            code = MODULE.main([])
        return code, stdout.getvalue(), stderr.getvalue()

    def _run_worker_with_error(self) -> tuple[int, str, str]:
        return self._run_worker()

    def test_claim_work_and_drain(self) -> None:
        state = self._state()
        state["claims"] = [
            {
                "schema_version": "1",
                "ok": True,
                "command": "hook",
                "action": "drain",
                "reason": "no_work",
                "drain_acknowledged": True,
            }
        ]
        self._write_state(state)
        code, _, _ = self._run_worker()
        self.assertEqual(code, 0)
        self.assertEqual(len(self._state()["calls"]), 1)
        self.assertEqual(self._state()["closes"], [])

    def test_wrong_marker_closes_only_claimed_step(self) -> None:
        state = self._state()
        state["beads"][STEP_ID]["description"] = self._description(
            push=True,
            open_pr=True,
            marker="gc.publication.worker_marker=other",
        )
        self._write_state(state)
        code, _, _ = self._run_worker()
        self.assertEqual(code, 0)
        self.assertEqual(
            [item["bead_id"] for item in self._state()["closes"]],
            [STEP_ID],
        )
        self.assertNotIn("gc.outcome", self._state()["beads"][WORKFLOW_ID]["metadata"])
        self.assertEqual(self._helper_state()["calls"], [])

    def test_missing_root_or_source_anchor_fails_closed(self) -> None:
        for remove_id in (WORKFLOW_ID, SOURCE_ID):
            with self.subTest(remove_id=remove_id):
                state = self._state()
                state["beads"].pop(remove_id)
                self._write_state(state)
                code, _, _ = self._run_worker()
                self.assertEqual(code, 0)
                self.assertEqual(
                    [item["bead_id"] for item in self._state()["closes"]],
                    [STEP_ID],
                )
                self.tearDown()
                self.setUp()

    def test_synthetic_drain_member_is_authoritative(self) -> None:
        state = self._state()
        state["beads"][WORKFLOW_ID]["metadata"]["gc.input_convoy_id"] = CONVOY_ID
        state["beads"][WORKFLOW_ID]["metadata"]["gc.drain_member_id"] = SOURCE_ID
        state["beads"][CONVOY_ID]["metadata"] = {
            "gc.synthetic_kind": "drain-unit-convoy",
            "gc.drain_member_id": SOURCE_ID,
        }
        self._write_state(state)
        code, _, _ = self._run_worker()
        self.assertEqual(code, 0)
        self.assertEqual(self._helper_state()["calls"][0]["argv"], [SOURCE_ID])

    def test_disabled_publication_records_noop_and_closes(self) -> None:
        state = self._state()
        state["beads"][STEP_ID]["description"] = self._description(
            push=False,
            open_pr=False,
        )
        self._write_state(state)
        code, _, _ = self._run_worker()
        self.assertEqual(code, 0)
        for bead_id in (WORKFLOW_ID, STEP_ID):
            metadata = self._state()["beads"][bead_id]["metadata"]
            self.assertEqual(metadata["gc.build.publish_status"], "noop")
            self.assertEqual(metadata["gc.build.publish_action"], "noop")
            self.assertEqual(metadata["gc.build.publish_reason"], "push=false_open_pr=false")
            self.assertTrue(metadata["gc.build.publish_artifact_path"])
            self.assertEqual(metadata["gc.outcome"], "pass")
        self.assertTrue(list(self.artifacts.glob("*.json")))

    def test_success_binds_head_invokes_helper_and_records_artifact(self) -> None:
        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        state = self._state()
        source_metadata = state["beads"][SOURCE_ID]["metadata"]
        self.assertEqual(source_metadata["gc.publication.expected_head_sha"], self.head_sha)
        self.assertEqual(self._helper_state()["calls"][0]["argv"], [SOURCE_ID])
        self.assertEqual(
            pathlib.Path(self._helper_state()["calls"][0]["cwd"]).resolve(),
            self.source.resolve(),
        )
        self.assertEqual(
            self._helper_state()["calls"][0]["credential_directory"],
            self.env["CREDENTIALS_DIRECTORY"],
        )
        for bead_id in (WORKFLOW_ID, STEP_ID):
            metadata = state["beads"][bead_id]["metadata"]
            self.assertEqual(metadata["gc.build.publish_status"], "published")
            self.assertEqual(metadata["gc.build.publish_action"], "push_pr")
            self.assertEqual(metadata["gc.build.publish_url"], "https://github.com/vicondoa/d2b/pull/17")
            self.assertEqual(metadata["gc.build.publish_sha"], self.head_sha)
            self.assertEqual(metadata["gc.publication.branch"], f"gascity/{SOURCE_ID}")
            self.assertEqual(metadata["gc.outcome"], "pass")
        artifact = pathlib.Path(
            state["beads"][STEP_ID]["metadata"]["gc.build.publish_artifact_path"]
        )
        self.assertEqual(artifact.parent, self.artifacts)
        self.assertEqual(json.loads(artifact.read_text(encoding="utf-8"))["status"], "published")

    def test_existing_expected_head_is_immutable_on_retry(self) -> None:
        state = self._state()
        state["beads"][SOURCE_ID]["metadata"][
            "gc.publication.expected_head_sha"
        ] = self.head_sha
        self._write_state(state)

        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        current = self._state()
        self.assertEqual(
            current["beads"][SOURCE_ID]["metadata"][
                "gc.publication.expected_head_sha"
            ],
            self.head_sha,
        )
        self.assertFalse(
            any(
                update["bead_id"] == SOURCE_ID
                for update in current["updates"]
            )
        )

    def test_changed_head_rejects_existing_expected_head(self) -> None:
        state = self._state()
        state["beads"][SOURCE_ID]["metadata"][
            "gc.publication.expected_head_sha"
        ] = self.head_sha
        self._write_state(state)
        (self.source / "changed.txt").write_text("changed\n", encoding="utf-8")
        self._git(["-C", str(self.source), "add", "changed.txt"])
        self._git(["-C", str(self.source), "commit", "-qm", "changed"])

        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        current = self._state()
        self.assertEqual(
            current["beads"][SOURCE_ID]["metadata"][
                "gc.publication.expected_head_sha"
            ],
            self.head_sha,
        )
        self.assertEqual(self._helper_state()["calls"], [])
        self.assertEqual(
            current["beads"][STEP_ID]["metadata"]["gc.build.publish_reason"],
            "source-head-mismatch",
        )

    def test_git_fsmonitor_is_disabled_and_git_env_is_scrubbed(self) -> None:
        marker = self.base / "fsmonitor-invoked"
        fsmonitor = self.base / "fsmonitor"
        fsmonitor.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"${{CREDENTIALS_DIRECTORY-unset}}\" > {marker}\n",
            encoding="utf-8",
        )
        fsmonitor.chmod(0o700)
        self._git(
            [
                "-C",
                str(self.source),
                "config",
                "core.fsmonitor",
                str(fsmonitor),
            ]
        )
        git_environment = MODULE._git_environment(MODULE._resolve_git())
        self.assertNotIn("CREDENTIALS_DIRECTORY", git_environment)
        self.assertNotIn("UNRELATED_SECRET", git_environment)

        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        self.assertFalse(marker.exists())

    def test_metadata_update_failure_leaves_claimed_step_open(self) -> None:
        state = self._state()
        state["update_failure_beads"] = [STEP_ID]
        self._write_state(state)

        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "publication-worker: bead-update-failed\n")
        current = self._state()
        self.assertEqual(current["closes"], [])
        self.assertFalse(current["beads"][STEP_ID].get("closed", False))

    def test_root_metadata_update_failure_leaves_claimed_step_open(self) -> None:
        state = self._state()
        state["update_failure_beads"] = [WORKFLOW_ID]
        self._write_state(state)

        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "publication-worker: bead-update-failed\n")
        current = self._state()
        self.assertEqual(current["closes"], [])
        self.assertFalse(current["beads"][STEP_ID].get("closed", False))

    def test_metadata_readback_failure_leaves_claimed_step_open(self) -> None:
        state = self._state()
        state["readback_mismatch_beads"] = [STEP_ID]
        self._write_state(state)

        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "publication-worker: bead-readback-mismatch\n")
        current = self._state()
        self.assertEqual(current["closes"], [])
        self.assertFalse(current["beads"][STEP_ID].get("closed", False))

    def test_helper_failure_is_typed_and_does_not_leak_child_output(self) -> None:
        helper = self._helper_state()
        helper["mode"] = "failure"
        self._write_helper(helper)
        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 0)
        self.assertNotIn("fixture-token", stdout)
        self.assertNotIn("fixture-token", stderr)
        state = self._state()
        for bead_id in (WORKFLOW_ID, STEP_ID):
            metadata = state["beads"][bead_id]["metadata"]
            self.assertEqual(metadata["gc.build.publish_status"], "failed")
            self.assertEqual(metadata["gc.build.publish_reason"], "helper-failed")
            self.assertEqual(metadata["gc.failure_class"], "publication_helper")
            self.assertEqual(metadata["gc.outcome"], "fail")

    def test_helper_timeout_leaves_claimed_step_open(self) -> None:
        original_run = MODULE._run
        helper_calls: list[dict[str, object]] = []

        def run(
            argv: list[str],
            **kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            if argv == ["d2b-gascity-publish-pr", SOURCE_ID]:
                helper_calls.append(kwargs)
                raise MODULE.WorkerError("helper-timeout")
            return original_run(argv, **kwargs)

        with mock.patch.object(MODULE, "_run", side_effect=run):
            code, stdout, stderr = self._run_worker()

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "publication-worker: helper-timeout\n")
        self.assertEqual(helper_calls[0]["timeout"], MODULE.HELPER_TIMEOUT)
        self.assertNotIn("fixture-token", stdout)
        self.assertNotIn("fixture-token", stderr)
        current = self._state()
        self.assertEqual(current["closes"], [])
        self.assertFalse(current["beads"][STEP_ID].get("closed", False))

    def test_helper_remote_observation_failure_is_retryable(self) -> None:
        helper = self._helper_state()
        helper["mode"] = "typed-failure"
        helper["error_code"] = "remote-state-unavailable"
        self._write_helper(helper)

        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "publication-worker: helper-retryable\n")
        self.assertNotIn("fixture-token", stdout)
        self.assertNotIn("fixture-token", stderr)
        current = self._state()
        self.assertEqual(current["closes"], [])
        self.assertFalse(current["beads"][STEP_ID].get("closed", False))

    def test_github_response_invalid_is_retryable_and_reconciles(self) -> None:
        helper = self._helper_state()
        helper["mode"] = "typed-failure"
        helper["error_code"] = "github-response-invalid"
        self._write_helper(helper)
        initial = self._state()
        initial_metadata = {
            bead_id: dict(initial["beads"][bead_id]["metadata"])
            for bead_id in (WORKFLOW_ID, STEP_ID)
        }

        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "publication-worker: helper-retryable\n")
        self.assertNotIn("github-response-invalid", stderr)
        self.assertNotIn("fixture-token", stdout)
        self.assertNotIn("fixture-token", stderr)
        current = self._state()
        self.assertEqual(current["closes"], [])
        self.assertFalse(current["beads"][STEP_ID].get("closed", False))
        for bead_id, metadata in initial_metadata.items():
            self.assertEqual(current["beads"][bead_id]["metadata"], metadata)

        helper = self._helper_state()
        helper["mode"] = "success"
        self._write_helper(helper)
        current["claims"] = [
            {
                "schema_version": "1",
                "ok": True,
                "command": "hook",
                "action": "work",
                "reason": "existing_assignment",
                "bead_id": STEP_ID,
                "assignee": "d2b/publisher",
                "root_bead_id": WORKFLOW_ID,
                "continuation_group": "",
            },
            {
                "schema_version": "1",
                "ok": True,
                "command": "hook",
                "action": "drain",
                "reason": "no_work",
                "drain_acknowledged": True,
            },
        ]
        self._write_state(current)

        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")
        current = self._state()
        self.assertTrue(current["beads"][STEP_ID].get("closed", False))
        self.assertEqual(
            current["beads"][STEP_ID]["metadata"]["gc.build.publish_status"],
            "published",
        )
        self.assertEqual(len(self._helper_state()["calls"]), 2)

    def test_post_publication_beads_error_codes_are_retryable(self) -> None:
        for code in (
            "beads-show-unavailable",
            "beads-update-failed",
            "beads-readback-mismatch",
            "beads-response-invalid",
        ):
            with self.subTest(code=code):
                failure = MODULE._helper_failure(f"publish-pr: {code}\n")
                self.assertEqual(failure.code, "helper-retryable")

    def test_post_publication_beads_failure_is_retryable_and_retries_same_head(self) -> None:
        helper = self._helper_state()
        helper["mode"] = "typed-failure"
        helper["error_code"] = "beads-update-failed"
        self._write_helper(helper)

        code, _, stderr = self._run_worker()
        self.assertEqual(code, 2)
        self.assertEqual(stderr, "publication-worker: helper-retryable\n")
        current = self._state()
        self.assertEqual(current["closes"], [])
        self.assertFalse(current["beads"][STEP_ID].get("closed", False))
        expected = current["beads"][SOURCE_ID]["metadata"][
            "gc.publication.expected_head_sha"
        ]

        helper = self._helper_state()
        helper["mode"] = "success"
        self._write_helper(helper)
        current["claims"] = [
            {
                "schema_version": "1",
                "ok": True,
                "command": "hook",
                "action": "work",
                "reason": "existing_assignment",
                "bead_id": STEP_ID,
                "assignee": "d2b/publisher",
                "root_bead_id": WORKFLOW_ID,
                "continuation_group": "",
            },
            {
                "schema_version": "1",
                "ok": True,
                "command": "hook",
                "action": "drain",
                "reason": "no_work",
                "drain_acknowledged": True,
            },
        ]
        self._write_state(current)
        code, _, stderr = self._run_worker()
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        current = self._state()
        self.assertEqual(
            current["beads"][SOURCE_ID]["metadata"][
                "gc.publication.expected_head_sha"
            ],
            expected,
        )
        self.assertTrue(current["beads"][STEP_ID].get("closed", False))
        self.assertEqual(len(self._helper_state()["calls"]), 2)

    def test_claims_errored_drain_is_a_nonzero_typed_failure(self) -> None:
        state = self._state()
        state["claims"] = [
            {
                "schema_version": "1",
                "ok": True,
                "command": "hook",
                "action": "drain",
                "reason": "claims_errored",
                "drain_acknowledged": True,
            }
        ]
        self._write_state(state)
        code, stdout, stderr = self._run_worker()
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "publication-worker: claims-errored\n")
        self.assertEqual(self._state()["drain_acks"], 0)

    def test_continuation_claims_again_until_drain(self) -> None:
        state = self._state()
        state["beads"][STEP_ID]["description"] = self._description(
            push=False,
            open_pr=False,
        )
        state["claims"][0]["continuation_group"] = "publication"
        state["claims"].append(
            {
                "schema_version": "1",
                "ok": True,
                "command": "hook",
                "action": "drain",
                "reason": "no_work",
                "drain_acknowledged": True,
            }
        )
        self._write_state(state)
        code, _, _ = self._run_worker()
        self.assertEqual(code, 0)
        claim_calls = [
            call for call in self._state()["calls"] if call["argv"][0] == "hook"
        ]
        self.assertEqual(len(claim_calls), 2)
        self.assertEqual(self._state()["drain_acks"], 0)

    @staticmethod
    def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            text=True,
            capture_output=True,
            check=True,
        )

if __name__ == "__main__":
    unittest.main(verbosity=2)
