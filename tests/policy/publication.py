from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import base64
import io
import importlib.util
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "publish-pr.py"
FAKE_BD = ROOT / "tests" / "fixtures" / "github" / "fake_bd.py"
FAKE_GIT = ROOT / "tests" / "fixtures" / "github" / "fake_git.py"
FAKE_GH = ROOT / "tests" / "fixtures" / "github" / "fake_gh.py"
HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40
RACE_SHA = "c" * 40
WORK_ID = "bd-fixture-123"


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object], status: int = 201) -> None:
        self._body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.status = status

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]


def _load_module():
    spec = importlib.util.spec_from_file_location("publish_pr", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load publication helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


class PublicationPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tempdir.name)
        self.worktree = self.base / "worktree"
        (self.worktree / ".git").mkdir(parents=True)
        self.credentials = self.base / "credentials"
        self.credentials.mkdir()
        self.policy = self.credentials / "github-publication-policy"
        self.token = self.credentials / "github-publication-token"
        self.app_key = self.credentials / "github-publication-app-key"
        self.app_config = self.credentials / "github-publication-app-config"
        self.policy.write_text(
            json.dumps(self._policy(), sort_keys=True),
            encoding="utf-8",
        )
        self.token.write_text("fixture-token\n", encoding="utf-8")
        self.policy.chmod(0o444)
        self.token.chmod(0o400)
        self._reset_state()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _default_bd_state(self) -> dict[str, object]:
        return {
            "issue": {
                "id": WORK_ID,
                "metadata": {
                    "work_dir": str(self.worktree),
                    "gc.publication.expected_head_sha": HEAD_SHA,
                    "gc.publication.base_sha": BASE_SHA,
                    "gc.publication.base_ref": "origin/v3",
                },
            },
            "update_mode": "success",
            "calls": [],
        }

    def _default_git_state(self) -> dict[str, object]:
        return {
            "head_sha": HEAD_SHA,
            "base_sha": BASE_SHA,
            "current_base_sha": BASE_SHA,
            "remote_url": "https://github.com/vicondoa/d2b.git",
            "push_url": "https://github.com/vicondoa/d2b.git",
            "status": "",
            "remote_branch": None,
            "pushes": 0,
            "rejected_pushes": 0,
            "calls": [],
        }

    def _default_gh_state(self) -> dict[str, object]:
        return {
            "head_sha": HEAD_SHA,
            "expected_branch": f"gascity/{WORK_ID}",
            "prs": [],
            "create_mode": "success",
            "next_number": 1,
            "calls": [],
            "env_keys": [],
            "env_attestations": [],
        }

    def _reset_state(self) -> None:
        self._write_bd(
            self._default_bd_state()
        )
        self._write_git(self._default_git_state())
        self._write_gh(self._default_gh_state())

    def _policy(self) -> dict[str, object]:
        return {
            "version": 1,
            "identity": "d2b-gascity-publication",
            "repository": "vicondoa/d2b",
            "base": "v3",
            "publication_branch_pattern": "gascity/*",
            "publication_branch_create_only": True,
            "can_create_pull_request": True,
            "allow_direct_base_update": False,
            "allow_branch_update": False,
            "allow_force_push": False,
            "allow_force_with_lease": False,
            "allow_merge": False,
            "allow_auto_merge": False,
            "allow_merge_queue": False,
            "allow_ruleset_bypass": False,
        }

    def _write_bd(self, state: dict[str, object]) -> None:
        (self.base / ".fake-bd-state.json").write_text(
            json.dumps(state, sort_keys=True),
            encoding="utf-8",
        )

    def _write_git(self, state: dict[str, object]) -> None:
        (self.worktree / ".fake-git-state.json").write_text(
            json.dumps(state, sort_keys=True),
            encoding="utf-8",
        )

    def _write_gh(self, state: dict[str, object]) -> None:
        (self.worktree / ".fake-gh-state.json").write_text(
            json.dumps(state, sort_keys=True),
            encoding="utf-8",
        )

    def _bd_state(self) -> dict[str, object]:
        return json.loads(
            (self.base / ".fake-bd-state.json").read_text(encoding="utf-8")
        )

    def _git_state(self) -> dict[str, object]:
        return json.loads(
            (self.worktree / ".fake-git-state.json").read_text(encoding="utf-8")
        )

    def _gh_state(self) -> dict[str, object]:
        return json.loads(
            (self.worktree / ".fake-gh-state.json").read_text(encoding="utf-8")
        )

    def _run(
        self,
        *,
        policy: dict[str, object] | None = None,
        **publish_kwargs: object,
    ) -> dict[str, object]:
        if policy is not None:
            self.policy.chmod(0o644)
            self.policy.write_text(json.dumps(policy, sort_keys=True), encoding="utf-8")
            self.policy.chmod(0o444)

        with mock.patch.dict(
            "os.environ",
            {"CREDENTIALS_DIRECTORY": str(self.credentials)},
            clear=False,
        ):
            return MODULE.publish(
                WORK_ID,
                bd_command=str(FAKE_BD),
                git_command=str(FAKE_GIT),
                gh_command=str(FAKE_GH),
                beads_cwd=self.base,
                **publish_kwargs,
            )

    def _run_error(self, **kwargs: object) -> MODULE.PublishError:
        with self.assertRaises(MODULE.PublishError) as context:
            self._run(**kwargs)
        return context.exception

    def test_create_is_exact_and_repeat_is_convergent(self) -> None:
        first = self._run()
        self.assertEqual(first["repository"], "vicondoa/d2b")
        self.assertEqual(first["base"], "v3")
        self.assertEqual(first["branch"], f"gascity/{WORK_ID}")
        self.assertEqual(first["head_sha"], HEAD_SHA)
        self.assertEqual(first["status"], "open")
        self.assertEqual(first["url"], "https://github.com/vicondoa/d2b/pull/1")
        self.assertEqual(self._git_state()["pushes"], 1)
        self.assertEqual(len(self._gh_state()["prs"]), 1)
        metadata = self._bd_state()["issue"]["metadata"]
        self.assertEqual(metadata["gc.publication.url"], first["url"])
        self.assertEqual(metadata["gc.publication.sha"], HEAD_SHA)
        self.assertEqual(metadata["gc.publication.branch"], f"gascity/{WORK_ID}")
        bd_calls = self._bd_state()["calls"]
        self.assertEqual(bd_calls[0], ["show", WORK_ID, "--json", "--long"])
        self.assertIn("--set-metadata", bd_calls[1])

        second = self._run()
        self.assertEqual(second, first)
        self.assertEqual(self._git_state()["pushes"], 1)
        self.assertEqual(len(self._gh_state()["prs"]), 1)

    def test_ambiguous_create_response_is_reconciled(self) -> None:
        state = self._gh_state()
        state["create_mode"] = "ambiguous"
        self._write_gh(state)
        result = self._run()
        self.assertEqual(result["url"], "https://github.com/vicondoa/d2b/pull/1")
        self.assertEqual(len(self._gh_state()["prs"]), 1)
        self.assertEqual(self._git_state()["pushes"], 1)

    def test_ambiguous_push_response_is_reconciled(self) -> None:
        state = self._git_state()
        state["push_mode"] = "ambiguous"
        self._write_git(state)

        result = self._run()
        self.assertEqual(result["url"], "https://github.com/vicondoa/d2b/pull/1")
        self.assertEqual(self._git_state()["remote_branch"], HEAD_SHA)
        self.assertEqual(self._git_state()["pushes"], 1)
        self.assertEqual(len(self._gh_state()["prs"]), 1)

        retry = self._run()
        self.assertEqual(retry, result)
        self.assertEqual(self._git_state()["pushes"], 1)
        self.assertEqual(len(self._gh_state()["prs"]), 1)

    def test_ambiguous_push_with_unavailable_remote_observation_is_retryable(self) -> None:
        state = self._git_state()
        state["push_mode"] = "ambiguous"
        state["publication_remote_observation_error"] = True
        self._write_git(state)

        error = self._run_error()
        self.assertEqual(error.code, "remote-state-unavailable")
        self.assertEqual(self._git_state()["pushes"], 1)
        self.assertEqual(self._gh_state()["prs"], [])

    def test_restart_after_push_reconciles_without_second_push(self) -> None:
        state = self._gh_state()
        state["create_mode"] = "failure"
        self._write_gh(state)
        with self.assertRaises(MODULE.PublishError):
            self._run()
        self.assertEqual(self._git_state()["pushes"], 1)

        state = self._gh_state()
        state["create_mode"] = "success"
        self._write_gh(state)
        result = self._run()
        self.assertEqual(result["status"], "open")
        self.assertEqual(self._git_state()["pushes"], 1)
        self.assertEqual(len(self._gh_state()["prs"]), 1)

    def test_conflicting_pr_states_stop_before_push(self) -> None:
        cases = (
            {"state": "CLOSED", "mergedAt": None},
            {"state": "MERGED", "mergedAt": "fixture"},
            {"state": "OPEN", "headRefOid": "d" * 40, "mergedAt": None},
            {"state": "OPEN", "baseRefName": "main", "mergedAt": None},
        )
        for case in cases:
            with self.subTest(case=case):
                self._reset_state()
                record = self._pr_record(number=9)
                record.update(case)
                state = self._gh_state()
                state["prs"] = [record]
                self._write_gh(state)
                error = self._run_error()
                self.assertEqual(error.code, "publication-conflict")
                self.assertEqual(self._git_state()["pushes"], 0)

    def test_duplicate_open_prs_stop_before_mutation(self) -> None:
        state = self._gh_state()
        state["prs"] = [self._pr_record(number=1), self._pr_record(number=2)]
        self._write_gh(state)
        error = self._run_error()
        self.assertEqual(error.code, "publication-conflict")
        self.assertEqual(self._git_state()["pushes"], 0)

    def test_malformed_or_unrelated_pr_response_stops_before_mutation(self) -> None:
        state = self._gh_state()
        state["list_payload"] = [{"number": "not-an-int"}]
        self._write_gh(state)
        error = self._run_error()
        self.assertEqual(error.code, "github-response-invalid")
        self.assertEqual(self._git_state()["pushes"], 0)

        self._reset_state()
        record = self._pr_record(number=4)
        record["headRefName"] = "gascity/other"
        state = self._gh_state()
        state["list_payload"] = [record]
        self._write_gh(state)
        error = self._run_error()
        self.assertEqual(error.code, "github-response-invalid")
        self.assertEqual(self._git_state()["pushes"], 0)

    def test_wrong_head_repository_and_server_policy_stop_before_push(self) -> None:
        state = self._gh_state()
        record = self._pr_record(number=3)
        record["headRepository"] = {"nameWithOwner": "other/repository"}
        record["url"] = "https://github.com/other/repository/pull/3"
        state["prs"] = [record]
        self._write_gh(state)
        error = self._run_error()
        self.assertEqual(error.code, "publication-conflict")
        self.assertEqual(self._git_state()["pushes"], 0)

        self._write_gh({**self._gh_state(), "prs": [], "calls": []})
        unsupported = self._policy()
        unsupported["allow_merge"] = True
        error = self._run_error(policy=unsupported)
        self.assertEqual(error.code, "server-protection-unsupported")
        self.assertEqual(self._git_state()["pushes"], 0)
        self.assertEqual(self._gh_state()["calls"], [])

    def test_wrong_remote_dirty_head_or_base_fail_before_github(self) -> None:
        for field, value, code in (
            ("remote_url", "https://github.com/other/repository.git", "remote-repository-mismatch"),
            ("status", " M planted", "worktree-dirty"),
        ):
            with self.subTest(field=field):
                self._reset_state()
                state = self._git_state()
                state[field] = value
                self._write_git(state)
                error = self._run_error()
                self.assertEqual(error.code, code)
                self.assertEqual(self._gh_state()["calls"], [])

        self._reset_state()
        state = self._git_state()
        state["current_base_sha"] = "e" * 40
        state["base_on_v3"] = False
        self._write_git(state)
        error = self._run_error()
        self.assertEqual(error.code, "base-not-on-v3")
        self.assertEqual(self._gh_state()["calls"], [])

        self._reset_state()
        state = self._git_state()
        state["head_descends_from_base"] = False
        self._write_git(state)
        error = self._run_error()
        self.assertEqual(error.code, "base-not-ancestor")
        self.assertEqual(self._gh_state()["calls"], [])

    def test_v3_advancement_does_not_invalidate_recorded_base(self) -> None:
        state = self._git_state()
        state["current_base_sha"] = "e" * 40
        self._write_git(state)
        result = self._run()
        self.assertEqual(result["status"], "open")
        self.assertEqual(self._git_state()["tracking_base_sha"], "e" * 40)

    def test_missing_or_mismatched_beads_anchor_stops_before_mutation(self) -> None:
        self._write_bd({"issue": None, "calls": []})
        error = self._run_error()
        self.assertEqual(error.code, "beads-anchor-missing")
        self.assertEqual(self._git_state()["calls"], [])

        self._write_bd(
            {
                "issue": {"id": "different", "metadata": {}},
                "calls": [],
            }
        )
        error = self._run_error()
        self.assertEqual(error.code, "beads-anchor-mismatch")
        self.assertEqual(self._git_state()["calls"], [])

        self._write_bd(
            {
                "issue": {
                    "id": WORK_ID,
                    "metadata": {
                        "work_dir": str(self.worktree),
                        "gc.publication.expected_head_sha": HEAD_SHA,
                        "gc.publication.base_sha": BASE_SHA,
                    },
                },
                "calls": [],
            }
        )
        error = self._run_error()
        self.assertEqual(error.code, "beads-anchor-metadata-missing")
        self.assertEqual(self._git_state()["calls"], [])

    def test_beads_write_failure_and_readback_mismatch_are_failures(self) -> None:
        state = self._bd_state()
        state["update_mode"] = "failure"
        self._write_bd(state)
        error = self._run_error()
        self.assertEqual(error.code, "beads-update-failed")

        self._reset_state()
        state = self._bd_state()
        state["update_mode"] = "readback-mismatch"
        self._write_bd(state)
        error = self._run_error()
        self.assertEqual(error.code, "beads-readback-mismatch")

    def test_beads_failure_after_remote_creation_reconciles_on_retry(self) -> None:
        state = self._bd_state()
        state["update_mode"] = "failure"
        self._write_bd(state)
        error = self._run_error()
        self.assertEqual(error.code, "beads-update-failed")
        self.assertEqual(self._git_state()["pushes"], 1)
        self.assertEqual(len(self._gh_state()["prs"]), 1)

        state = self._bd_state()
        state["update_mode"] = "success"
        self._write_bd(state)
        result = self._run()
        self.assertEqual(result["status"], "open")
        self.assertEqual(self._git_state()["pushes"], 1)
        self.assertEqual(len(self._gh_state()["prs"]), 1)
        metadata = self._bd_state()["issue"]["metadata"]
        self.assertEqual(metadata["gc.publication.sha"], HEAD_SHA)

    def test_concurrent_branch_create_is_rejected_without_force(self) -> None:
        state = self._git_state()
        state["race_on_push"] = True
        state["race_sha"] = RACE_SHA
        state["descendants"] = {RACE_SHA: [HEAD_SHA]}
        self._write_git(state)
        error = self._run_error()
        self.assertEqual(error.code, "remote-head-mismatch")
        state = self._git_state()
        self.assertEqual(state["rejected_pushes"], 1)
        self.assertTrue(state["fast_forward_possible"])
        push_calls = [
            call
            for call in state["calls"]
            if len(call) >= 3 and call[2] == "push"
        ]
        self.assertEqual(len(push_calls), 1)
        self.assertNotIn("--force", push_calls[0])
        self.assertNotIn("--force-with-lease", push_calls[0])

    def test_github_environment_is_dedicated_and_scrubbed(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "GITHUB_TOKEN": "ambient-token",
                "GH_TOKEN": "ambient-token",
                "SSH_AUTH_SOCK": "/run/user/1000/ssh-agent.sock",
                "GIT_SSH_COMMAND": "ssh -i /" + "private/key",
                "UNRELATED_SECRET": "private-value",
            },
            clear=False,
        ):
            self._run()
        gh_state = self._gh_state()
        self.assertIn("GH_TOKEN", gh_state["env_keys"])
        self.assertTrue(
            all(
                attestation["gh_token_matches_fixture"]
                for attestation in gh_state["env_attestations"]
            )
        )
        self.assertTrue(
            all(
                not attestation["ambient_secret_keys_present"]
                for attestation in gh_state["env_attestations"]
            )
        )
        self.assertNotIn("GITHUB_TOKEN", gh_state["env_keys"])
        self.assertNotIn("UNRELATED_SECRET", gh_state["env_keys"])
        self.assertNotIn("FAKE_GH_STATE", gh_state["env_keys"])

        git_state = self._git_state()
        remote_records = [
            record for record in git_state["env_records"] if record["remote"]
        ]
        self.assertTrue(remote_records)
        for record in remote_records:
            self.assertTrue(record["git_auth_header_valid"])
            self.assertEqual(record["ambient_secret_keys_present"], [])
            self.assertFalse(record["token_literal_present"])
            self.assertEqual(
                set(record["env_keys"]),
                {
                    "GIT_CONFIG_GLOBAL",
                    "GIT_CONFIG_COUNT",
                    "GIT_CONFIG_KEY_0",
                    "GIT_CONFIG_KEY_1",
                    "GIT_CONFIG_KEY_2",
                    "GIT_CONFIG_KEY_3",
                    "GIT_CONFIG_KEY_4",
                    "GIT_CONFIG_KEY_5",
                    "GIT_CONFIG_KEY_6",
                    "GIT_CONFIG_KEY_7",
                    "GIT_CONFIG_KEY_8",
                    "GIT_CONFIG_KEY_9",
                    "GIT_CONFIG_NOSYSTEM",
                    "GIT_CONFIG_VALUE_0",
                    "GIT_CONFIG_VALUE_1",
                    "GIT_CONFIG_VALUE_2",
                    "GIT_CONFIG_VALUE_3",
                    "GIT_CONFIG_VALUE_4",
                    "GIT_CONFIG_VALUE_5",
                    "GIT_CONFIG_VALUE_6",
                    "GIT_CONFIG_VALUE_7",
                    "GIT_CONFIG_VALUE_8",
                    "GIT_CONFIG_VALUE_9",
                    "GIT_CONFIG_SYSTEM",
                    "GIT_ASKPASS",
                    "GIT_NO_REPLACE_OBJECTS",
                    "GIT_TERMINAL_PROMPT",
                    "HOME",
                    "LANG",
                    "LC_ALL",
                    "NO_COLOR",
                    "PATH",
                },
            )

        local_records = [
            record for record in git_state["env_records"] if not record["remote"]
        ]
        self.assertTrue(local_records)
        self.assertTrue(
            all(not record["git_auth_header_valid"] for record in local_records)
        )
        self.assertTrue(
            all(not record["ambient_secret_keys_present"] for record in local_records)
        )

    def test_publication_record_is_safe_typed_json(self) -> None:
        record = self._run()
        self.assertEqual(
            set(record),
            {
                "base",
                "beads_record",
                "branch",
                "head_sha",
                "number",
                "repository",
                "status",
                "url",
                "version",
                "work_id",
            },
        )
        encoded = json.dumps(record, sort_keys=True)
        self.assertNotIn("fixture-token", encoded)
        self.assertNotIn(str(self.worktree), encoded)

    def test_safe_cli_does_not_accept_publication_overrides(self) -> None:
        for forbidden in (
            "--repository",
            "--base",
            "--branch",
            "--expected-head-sha",
            "--merge",
            "--auto-merge",
            "--merge-queue",
            "--force",
            "--force-with-lease",
            "--bypass",
        ):
            with self.subTest(option=forbidden):
                rejected = subprocess.run(
                    [sys.executable, str(SCRIPT), forbidden, "value"],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(rejected.returncode, 0)

    def test_credentials_directory_and_files_are_validated(self) -> None:
        missing = self.base / "missing-credentials"
        with mock.patch.dict(
            "os.environ",
            {"CREDENTIALS_DIRECTORY": str(missing)},
            clear=False,
        ):
            with self.assertRaises(MODULE.PublishError) as context:
                MODULE._load_server_policy()
        self.assertEqual(context.exception.code, "server-protection-unverified")

        policy_link = self.credentials / "policy-link"
        policy_link.symlink_to(self.policy)
        self.policy.unlink()
        policy_link.rename(self.policy)
        with mock.patch.dict(
            "os.environ",
            {"CREDENTIALS_DIRECTORY": str(self.credentials)},
            clear=False,
        ):
            with self.assertRaises(MODULE.PublishError) as context:
                MODULE._load_server_policy()
        self.assertEqual(context.exception.code, "server-protection-unverified")

        self.policy.unlink()
        self.policy.write_text(json.dumps(self._policy(), sort_keys=True), encoding="utf-8")
        self.policy.chmod(0o644)
        with mock.patch.dict(
            "os.environ",
            {"CREDENTIALS_DIRECTORY": str(self.credentials)},
            clear=False,
        ):
            with self.assertRaises(MODULE.PublishError) as context:
                MODULE._load_server_policy()
        self.assertEqual(context.exception.code, "server-protection-unverified")

        self.policy.chmod(0o444)
        self.token.chmod(0o644)
        with mock.patch.dict(
            "os.environ",
            {"CREDENTIALS_DIRECTORY": str(self.credentials)},
            clear=False,
        ):
            with self.assertRaises(MODULE.PublishError) as context:
                MODULE._read_github_token()
        self.assertEqual(context.exception.code, "github-credential-unverified")

    def test_systemd_projected_private_modes_are_exact(self) -> None:
        self.token.chmod(0o440)
        with mock.patch.dict(
            "os.environ",
            {"CREDENTIALS_DIRECTORY": str(self.credentials)},
            clear=False,
        ):
            self.assertEqual(MODULE._read_github_token(), "fixture-token")

        for mode in (0o600, 0o640, 0o401):
            with self.subTest(mode=oct(mode)):
                self.token.chmod(mode)
                with (
                    mock.patch.dict(
                        "os.environ",
                        {"CREDENTIALS_DIRECTORY": str(self.credentials)},
                        clear=False,
                    ),
                    self.assertRaises(MODULE.PublishError) as context,
                ):
                    MODULE._read_github_token()
                self.assertEqual(context.exception.code, "github-credential-unverified")

    def test_static_token_invalid_does_not_fall_back_to_app(self) -> None:
        self._write_app_credentials()
        self.token.chmod(0o600)
        self.token.write_text("invalid token\n", encoding="utf-8")
        self.token.chmod(0o400)
        with mock.patch.object(MODULE.urllib.request, "urlopen") as urlopen:
            error = self._run_error()
        self.assertEqual(error.code, "github-credential-invalid")
        urlopen.assert_not_called()

    def test_missing_static_token_mints_app_token_with_exact_jwt_and_request(self) -> None:
        self._write_app_credentials()
        self.token.unlink()
        fake_openssl = self._fake_openssl()
        now = 1_700_000_000
        captured: dict[str, object] = {}

        def urlopen(request: object, *, timeout: float) -> _FakeHTTPResponse:
            captured["request"] = request
            captured["timeout"] = timeout
            return _FakeHTTPResponse(
                {
                    "token": "fixture-installation-token",
                    "expires_at": "2023-11-14T23:13:20Z",
                    "permissions": {
                        "metadata": "read",
                        "contents": "write",
                        "pull_requests": "write",
                    },
                    "repositories": [{"full_name": "vicondoa/d2b"}],
                }
            )

        with (
            mock.patch.object(MODULE.time, "time", return_value=now),
            mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=urlopen),
        ):
            result = self._run(openssl_command=str(fake_openssl))

        self.assertNotIn("fixture-installation-token", json.dumps(result))
        self.assertEqual(captured["timeout"], MODULE.GITHUB_API_TIMEOUT)
        request = captured["request"]
        self.assertEqual(
            request.full_url,
            "https://api.github.com/app/installations/456789/access_tokens",
        )
        self.assertEqual(request.method, "POST")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {
                "repositories": ["d2b"],
                "permissions": {
                    "metadata": "read",
                    "contents": "write",
                    "pull_requests": "write",
                },
            },
        )
        self.assertEqual(
            request.headers["Authorization"].split(" ", 1)[0],
            "Bearer",
        )
        jwt = request.headers["Authorization"].split(" ", 1)[1]
        header, payload, signature = jwt.split(".")
        self.assertEqual(
            json.loads(base64.urlsafe_b64decode(header + "===")),
            {"alg": "RS256", "typ": "JWT"},
        )
        self.assertEqual(
            json.loads(base64.urlsafe_b64decode(payload + "===")),
            {"exp": now + 540, "iat": now - 60, "iss": 123456},
        )
        self.assertEqual(
            signature,
            base64.urlsafe_b64encode(b"fixture-signature").decode().rstrip("="),
        )

        capture = json.loads(
            self.app_key.with_name(self.app_key.name + ".openssl-capture").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            capture["argv"],
            ["dgst", "-sha256", "-sign", str(self.app_key)],
        )
        self.assertEqual(capture["stdin"], f"{header}.{payload}")
        self.assertNotIn("fixture-private-key", json.dumps(capture))

    def test_app_response_permissions_and_repository_are_fail_closed(self) -> None:
        self._write_app_credentials()
        self.token.unlink()
        fake_openssl = self._fake_openssl()
        now = 1_700_000_000
        responses = (
            {
                "permissions": {
                    "metadata": "read",
                    "contents": "admin",
                    "pull_requests": "write",
                },
            },
            {"expires_at": "2023-11-14T22:13:19Z"},
            {"expires_at": "2023-11-14T23:13:21Z"},
            {"token": "fixture token"},
            {
                "permissions": {
                    "metadata": "read",
                    "contents": "write",
                    "pull_requests": "write",
                },
                "repositories": [{"full_name": "other/repository"}],
            },
            {"repositories": None},
            {"repository_selection": "all"},
        )
        for update in responses:
            with self.subTest(update=update):
                base = {
                    "token": "fixture-installation-token",
                    "expires_at": "2023-11-14T23:13:20Z",
                    "permissions": {
                        "metadata": "read",
                        "contents": "write",
                        "pull_requests": "write",
                    },
                    "repositories": [{"full_name": "vicondoa/d2b"}],
                }
                base.update(update)
                with (
                    mock.patch.object(MODULE.time, "time", return_value=now),
                    mock.patch.object(
                        MODULE.urllib.request,
                        "urlopen",
                        return_value=_FakeHTTPResponse(base),
                    ),
                ):
                    error = self._run_error(openssl_command=str(fake_openssl))
                self.assertEqual(error.code, "github-app-response-invalid")

    def _write_app_credentials(self) -> None:
        self.app_key.write_text(
            "-----BEGIN " + "PRIVATE KEY-----\nfixture-private-key\n"
            "-----END " + "PRIVATE KEY-----\n",
            encoding="utf-8",
        )
        self.app_key.chmod(0o440)
        self.app_config.write_text(
            json.dumps(
                {
                    "version": 1,
                    "app_id": 123456,
                    "installation_id": 456789,
                    "repository": "vicondoa/d2b",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        self.app_config.chmod(0o444)

    def _fake_openssl(self) -> pathlib.Path:
        script = self.base / "fake-openssl"
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import pathlib\n"
            "import sys\n"
            "key = pathlib.Path(sys.argv[-1])\n"
            "capture = key.with_name(key.name + '.openssl-capture')\n"
            "capture.write_text(json.dumps({\n"
            "    'argv': sys.argv[1:],\n"
            "    'stdin': sys.stdin.buffer.read().decode('ascii'),\n"
            "}), encoding='utf-8')\n"
            "sys.stdout.buffer.write(b'fixture-signature')\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

    def test_caller_policy_environment_is_ignored(self) -> None:
        with (
            mock.patch.dict(
                "os.environ",
                {
                    "D2B_GASCITY_GITHUB_SERVER_POLICY": str(self.policy),
                    "CREDENTIALS_DIRECTORY": str(self.base / "missing"),
                },
                clear=False,
            ),
        ):
            with self.assertRaises(MODULE.PublishError) as context:
                MODULE._load_server_policy()
        self.assertEqual(context.exception.code, "server-protection-unverified")

    def test_https_origin_and_push_urls_are_required(self) -> None:
        for field, value in (
            ("remote_url", "git@" + "github.com:vicondoa/d2b.git"),
            ("push_url", "ssh://git@" + "github.com/vicondoa/d2b.git"),
            ("remote_url", "https://user:" + "password@" + "github.com/vicondoa/d2b.git"),
            ("remote_url", "https://@github.com/vicondoa/d2b.git"),
        ):
            with self.subTest(field=field, value=value):
                self._reset_state()
                state = self._git_state()
                state[field] = value
                self._write_git(state)
                error = self._run_error()
                self.assertEqual(error.code, "remote-repository-mismatch")
                self.assertEqual(self._gh_state()["calls"], [])

        self._reset_state()
        state = self._git_state()
        state["push_urls"] = [
            "https://github.com/vicondoa/d2b.git",
            "https://github.com/vicondoa/d2b.git",
        ]
        self._write_git(state)
        error = self._run_error()
        self.assertEqual(error.code, "remote-repository-mismatch")
        self.assertEqual(self._gh_state()["calls"], [])

        self._reset_state()
        state = self._git_state()
        state["remote_urls"] = [
            "https://github.com/vicondoa/d2b.git",
            "https://github.com/vicondoa/d2b.git",
        ]
        self._write_git(state)
        error = self._run_error()
        self.assertEqual(error.code, "remote-repository-mismatch")
        self.assertEqual(self._gh_state()["calls"], [])

        self._reset_state()
        state = self._git_state()
        state["remote_url"] = "https://github.com/vicondoa/d2b"
        state["push_url"] = "https://github.com/vicondoa/d2b.git"
        self._write_git(state)
        error = self._run_error()
        self.assertEqual(error.code, "remote-repository-mismatch")
        self.assertEqual(self._gh_state()["calls"], [])

    def test_git_hooks_tags_and_refspec_are_closed(self) -> None:
        self._run()
        state = self._git_state()
        remote_records = [
            record for record in state["env_records"] if record["remote"]
        ]
        self.assertTrue(remote_records)
        self.assertTrue(all(record["hooks_disabled"] for record in remote_records))
        self.assertTrue(
            all(record["follow_tags_disabled"] for record in remote_records)
        )
        push_calls = [
            call
            for call in state["calls"]
            if len(call) >= 3 and call[2] == "push"
        ]
        self.assertEqual(len(push_calls), 1)
        self.assertEqual(
            push_calls[0][-1],
            f"{HEAD_SHA}:refs/heads/gascity/{WORK_ID}",
        )
        remote_calls = [
            call
            for call in state["calls"]
            if (
                len(call) >= 3
                and call[2] in {"fetch", "ls-remote", "push"}
                and any(item.startswith("https://github.com/") for item in call)
            )
        ]
        self.assertTrue(remote_calls)
        self.assertTrue(
            all(
                "https://github.com/vicondoa/d2b.git" in call
                for call in remote_calls
            )
        )
        self.assertTrue(all(call[0] == "--git-dir" for call in remote_calls))
        self.assertTrue(
            all(
                call[0:2] != ["-C", str(self.worktree)]
                for call in remote_calls
            )
        )
        self.assertNotIn("--tags", push_calls[0])
        self.assertNotIn("--force", push_calls[0])
        self.assertNotIn("--force-with-lease", push_calls[0])
        self.assertFalse(state.get("hook_ran"))
        self.assertEqual(state.get("push_follow_tags"), "false")
        self.assertEqual(
            state["pushed_refs"],
            [f"refs/heads/gascity/{WORK_ID}"],
        )

    def test_fake_gh_rejects_pr_list_without_exact_filters(self) -> None:
        command = [
            sys.executable,
            str(FAKE_GH),
            "pr",
            "list",
            "--repo",
            "vicondoa/d2b",
            "--head",
            f"gascity/{WORK_ID}",
            "--limit",
            "1000",
            "--json",
            "number,state,headRefName,baseRefName,headRefOid,headRepository,"
            "headRepositoryOwner,mergedAt,url",
        ]
        result = subprocess.run(
            command,
            cwd=self.worktree,
            env={
                **os.environ,
                "FAKE_GH_STATE": str(self.worktree / ".fake-gh-state.json"),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported pr list arguments", result.stderr)
        self.assertIn('"--state"', FAKE_GH.read_text(encoding="utf-8"))
        self.assertIn("EXPECTED_LIST_FIELDS", FAKE_GH.read_text(encoding="utf-8"))

    def test_token_is_absent_from_records_and_cli_output(self) -> None:
        self._reset_state()
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        for name, source in (
            ("bd", FAKE_BD),
            ("git", FAKE_GIT),
            ("gh", FAKE_GH),
        ):
            (bin_dir / name).symlink_to(source)
        stdout = io.StringIO()
        stderr = io.StringIO()
        old_cwd = pathlib.Path.cwd()
        with (
            mock.patch.dict(
                "os.environ",
                {
                    "CREDENTIALS_DIRECTORY": str(self.credentials),
                    "PATH": (
                        f"{bin_dir}:{pathlib.Path(sys.executable).parent}:"
                        f"{old_cwd / 'bin'}:{os.defpath}"
                    ),
                },
                clear=False,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            os.chdir(self.base)
            try:
                exit_code = MODULE.main([WORK_ID])
            finally:
                os.chdir(old_cwd)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("fixture-token", stdout.getvalue())
        self.assertNotIn("fixture-token", stderr.getvalue())
        serialized = json.dumps(
            {
                "record": json.loads(stdout.getvalue()),
                "bd": self._bd_state(),
                "git": self._git_state(),
                "gh": self._gh_state(),
            },
            sort_keys=True,
        )
        self.assertNotIn("fixture-token", serialized)

    def test_minted_token_is_absent_from_cli_output(self) -> None:
        self._write_app_credentials()
        self.token.unlink()
        fake_openssl = self._fake_openssl()
        bin_dir = self.base / "app-bin"
        bin_dir.mkdir()
        for name, source in (
            ("bd", FAKE_BD),
            ("git", FAKE_GIT),
            ("gh", FAKE_GH),
        ):
            (bin_dir / name).symlink_to(source)
        now = 1_700_000_000
        response = _FakeHTTPResponse(
            {
                "token": "fixture-installation-token",
                "expires_at": "2023-11-14T23:13:20Z",
                "permissions": {
                    "metadata": "read",
                    "contents": "write",
                    "pull_requests": "write",
                },
                "repositories": [{"full_name": "vicondoa/d2b"}],
            }
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        original_command_path = MODULE._command_path

        def command_path(value: str, label: str) -> str:
            if value == "openssl":
                return str(fake_openssl)
            return original_command_path(value, label)

        old_cwd = pathlib.Path.cwd()
        with (
            mock.patch.dict(
                "os.environ",
                {
                    "CREDENTIALS_DIRECTORY": str(self.credentials),
                    "PATH": f"{bin_dir}:{pathlib.Path(sys.executable).parent}:{os.defpath}",
                },
                clear=False,
            ),
            mock.patch.object(MODULE.time, "time", return_value=now),
            mock.patch.object(
                MODULE.urllib.request,
                "urlopen",
                return_value=response,
            ),
            mock.patch.object(MODULE, "_command_path", side_effect=command_path),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            os.chdir(self.base)
            try:
                exit_code = MODULE.main([WORK_ID])
            finally:
                os.chdir(old_cwd)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("fixture-installation-token", stdout.getvalue())
        self.assertNotIn("fixture-installation-token", stderr.getvalue())

    def test_cli_accepts_only_issue_id(self) -> None:
        parser = MODULE._parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([WORK_ID, "--bd", str(FAKE_BD)])

    def test_publication_script_has_no_fixed_host_credential_paths(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("/run/credentials/", source)
        self.assertNotIn("/etc/d2b-gascity/", source)

    def _pr_record(self, number: int) -> dict[str, object]:
        return {
            "number": number,
            "state": "OPEN",
            "headRefName": f"gascity/{WORK_ID}",
            "baseRefName": "v3",
            "headRefOid": HEAD_SHA,
            "headRepository": {"nameWithOwner": "vicondoa/d2b"},
            "headRepositoryOwner": {"login": "vicondoa"},
            "mergedAt": None,
            "url": f"https://github.com/vicondoa/d2b/pull/{number}",
        }


class RealGitPublicationNegativeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tempdir.name)
        self.worktree = self.base / "worktree"
        self.git = MODULE._command_path("git", "git")
        self._git(["init", "-q", str(self.worktree)])
        self._git(["-C", str(self.worktree), "config", "user.name", "Fixture"])
        self._git(
            [
                "-C",
                str(self.worktree),
                "config",
                "user.email",
                "fixture@example.invalid",
            ]
        )
        (self.worktree / "file.txt").write_text("fixture\n", encoding="utf-8")
        self._git(["-C", str(self.worktree), "add", "file.txt"])
        self._git(["-C", str(self.worktree), "commit", "-qm", "fixture"])
        (self.worktree / "second.txt").write_text("second\n", encoding="utf-8")
        self._git(["-C", str(self.worktree), "add", "second.txt"])
        self._git(["-C", str(self.worktree), "commit", "-qm", "second"])
        self._git(
            [
                "-C",
                str(self.worktree),
                "remote",
                "add",
                "origin",
                "https://github.com/vicondoa/d2b.git",
            ]
        )
        self.environment = MODULE._scrubbed_environment(self.git)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _git(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.git, *argv],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )

    def _head_and_parent(self) -> tuple[str, str]:
        head = self._git(["-C", str(self.worktree), "rev-parse", "HEAD"]).stdout.strip()
        parent = self._git(
            ["-C", str(self.worktree), "rev-parse", "HEAD^"]
        ).stdout.strip()
        return head, parent

    def test_real_git_rejects_replacement_refs_and_grafts(self) -> None:
        head, parent = self._head_and_parent()
        self._git(["-C", str(self.worktree), "replace", head, parent])
        with self.assertRaises(MODULE.PublishError) as replacement:
            MODULE._reject_ancestry_overrides(
                self.git,
                self.worktree,
                environment=self.environment,
            )
        self.assertEqual(replacement.exception.code, "replacement-objects-present")
        self._git(["-C", str(self.worktree), "replace", "-d", head])

        grafts = self.worktree / ".git" / "info" / "grafts"
        grafts.write_text(f"{head} {parent}\n", encoding="utf-8")
        with self.assertRaises(MODULE.PublishError) as graft:
            MODULE._reject_ancestry_overrides(
                self.git,
                self.worktree,
                environment=self.environment,
            )
        self.assertEqual(graft.exception.code, "grafts-present")

    def test_real_git_bare_transport_ignores_hostile_worktree_config(self) -> None:
        hostile = (
            ("http.proxy", "http://127.0.0.1:1"),
            ("http.sslVerify", "false"),
            ("credential.helper", "!touch hostile-credential-helper"),
            ("core.hooksPath", str(self.base / "hostile-hooks")),
        )
        for key, value in hostile:
            self._git(["-C", str(self.worktree), "config", key, value])
        head, _ = self._head_and_parent()
        remote_repo = self.base / "remote.git"
        self._git(["init", "--bare", str(remote_repo)])
        self._git(
            [
                "-C",
                str(self.worktree),
                "push",
                str(remote_repo),
                f"{head}:refs/heads/v3",
            ]
        )
        remote_url = remote_repo.as_uri()
        self._git(
            [
                "-C",
                str(self.worktree),
                "config",
                f'url."file:///definitely-invalid".insteadOf',
                remote_url,
            ]
        )

        with MODULE._trusted_bare_repository(
            self.git,
            self.worktree,
            head,
            environment=self.environment,
        ) as bare:
            self.assertEqual(stat.S_IMODE(bare.stat().st_mode), 0o700)
            remote = MODULE._run_command(
                [
                    self.git,
                    "--git-dir",
                    str(bare),
                    "ls-remote",
                    remote_url,
                    "refs/heads/v3",
                ],
                cwd=self.worktree,
                env=MODULE._git_remote_environment(
                    "fixture-token",
                    self.git,
                ),
            )
            self.assertEqual(remote.returncode, 0, remote.stderr)
            self.assertIn(f"{head}\trefs/heads/v3", remote.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
