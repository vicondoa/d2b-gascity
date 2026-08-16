#!/usr/bin/env python3
"""Hermetic ACP provider characterization using a fake Copilot executable."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "copilot-provider.py"
FAKE_COPILOT = ROOT / "tests" / "fixtures" / "acp" / "fake_copilot.py"
SCRATCH = pathlib.Path(
    os.environ.get("D2B_GASCITY_CHECK_RUN_ROOT", tempfile.gettempdir())
)


class CopilotAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(
            dir=SCRATCH,
            prefix="copilot-acp-",
        )
        self.base = pathlib.Path(self.temp.name)
        self.worktree = self.base / "worktree"
        self.worktree.mkdir()
        self.runtime = self.base / "runtime"
        self.runtime.mkdir()
        os.chmod(self.runtime, 0o700)
        self.credential = self.base / "copilot-token"
        self.credential.write_text("fixture-token\n", encoding="ascii")
        os.chmod(self.credential, 0o600)
        self.canary = self.base / "forbidden-action-canary"
        self.fake = self.base / "bin" / "copilot"
        self.fake.parent.mkdir()
        shutil.copy2(FAKE_COPILOT, self.fake)
        os.chmod(self.fake, 0o755)
        self.mode_file = self.fake.with_name(self.fake.name + ".mode")
        self.mode_file.write_text("success\n", encoding="ascii")
        self.env = os.environ.copy()
        self.env.update(
            {
                "XDG_RUNTIME_DIR": str(self.runtime),
                "CREDENTIALS_DIRECTORY": str(self.base / "credentials"),
                "UNRELATED_SECRET": "must-not-reach-child",
                "GITHUB_TOKEN": "must-not-reach-child",
                "AWS_SECRET_ACCESS_KEY": "must-not-reach-child",
                "GC_HOME": str(self.base / "gc"),
                "XDG_CONFIG_HOME": str(self.base / "config"),
                "D2B_ACP_CANARY": str(self.canary),
            }
        )
        (self.base / "credentials").mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _command(
        self,
        operation: str,
        *,
        profile: str | None = None,
        policy: str | None = None,
        selection: pathlib.Path | None = None,
        credential: pathlib.Path | None = None,
        runtime: pathlib.Path | None = None,
        timeout: float = 1.0,
    ) -> list[str]:
        command = [
            sys.executable,
            str(SCRIPT),
            operation,
            "--copilot",
            str(self.fake),
            "--worktree",
            str(self.worktree),
            "--credential-file",
            str(credential or self.credential),
            "--runtime-dir",
            str(runtime or self.runtime),
            "--timeout",
            str(timeout),
        ]
        if selection is not None:
            command.extend(["--selection-path", str(selection)])
        if profile is not None:
            command.extend(["--profile", profile])
        if policy is not None:
            command.extend(["--tool-policy", policy])
        return command

    def _run(
        self,
        operation: str,
        *,
        profile: str | None = None,
        policy: str | None = None,
        selection: pathlib.Path | None = None,
        credential: pathlib.Path | None = None,
        runtime: pathlib.Path | None = None,
        timeout: float = 1.0,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self._command(
                operation,
                profile=profile,
                policy=policy,
                selection=selection,
                credential=credential,
                runtime=runtime,
                timeout=timeout,
            ),
            cwd=self.worktree,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def _events(self) -> list[dict[str, object]]:
        path = self.worktree / "fake-copilot-events.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def _selection(self) -> dict[str, object]:
        return json.loads(
            (self.base / "provider-selection.json").read_text(encoding="utf-8")
        )

    def test_code_luna_uses_fixed_argv_environment_and_sandbox(self) -> None:
        result = self._run("run", profile="code-luna", policy="coding")
        self.assertEqual(result.returncode, 0, result.stderr)
        event = self._events()[0]
        self.assertEqual(event["cwd"], str(self.worktree))
        self.assertEqual(event["env"]["token_matches_fixture"], True)
        self.assertEqual(event["env"]["credentials_directory_present"], False)
        self.assertEqual(event["env"]["unrelated_secret_present"], False)
        self.assertEqual(event["env"]["github_token_present"], False)
        self.assertEqual(event["env"]["aws_secret_present"], False)
        self.assertFalse(pathlib.Path(str(event["env"]["copilot_home"])).exists())
        self.assertEqual(
            event["argv"],
            [
                "--acp",
                "--experimental",
                "--model",
                "gpt-5.6-luna",
                "--context",
                "default",
                "--effort",
                "max",
                "--no-custom-instructions",
                "--no-auto-update",
                "--disable-builtin-mcps",
                "--no-remote",
                "--no-remote-export",
                "--no-ask-user",
                "--no-bash-env",
                "--secret-env-vars",
                "COPILOT_GITHUB_TOKEN",
                "--available-tools",
                "bash,view,search,apply_patch",
                "--deny-tool",
                "shell(gh)",
                "--deny-tool",
                "shell(gh *)",
                "--deny-tool",
                "shell(git push)",
                "--deny-tool",
                "shell(git push *)",
                "--deny-tool",
                "shell(discord)",
                "--deny-tool",
                "shell(discord *)",
                "-C",
                str(self.worktree),
            ],
        )
        settings = event["settings"]
        self.assertEqual(settings["model"], "gpt-5.6-luna")
        self.assertEqual(settings["contextTier"], "default")
        self.assertEqual(settings["experimental"], True)
        self.assertEqual(settings["autoUpdate"], False)
        self.assertEqual(settings["memory"], False)
        sandbox = settings["sandbox"]
        self.assertEqual(sandbox["enabled"], True)
        self.assertEqual(sandbox["addCurrentWorkingDirectory"], True)
        self.assertEqual(sandbox["allowBypass"], False)
        self.assertEqual(sandbox["auth"], {"git": False, "gh": False})
        self.assertEqual(sandbox["sandboxMcpServers"], True)
        self.assertEqual(sandbox["sandboxLspServers"], True)
        self.assertEqual(
            sandbox["userPolicy"]["network"],
            {"allowOutbound": True, "allowLocalNetwork": False},
        )
        denied = sandbox["userPolicy"]["filesystem"]["deniedPaths"]
        self.assertIn("/run/credentials", denied)
        self.assertIn("/etc/nixos", denied)
        self.assertIn(str(self.base / "gc"), denied)
        self.assertIn(str(self.base / "config"), denied)

    def test_planning_sol_uses_long_context_and_planning_tools(self) -> None:
        result = self._run("run", profile="planning-sol", policy="planning")
        self.assertEqual(result.returncode, 0, result.stderr)
        event = self._events()[0]
        self.assertEqual(
            event["argv"][event["argv"].index("--model") + 1],
            "gpt-5.6-sol",
        )
        self.assertEqual(
            event["argv"][event["argv"].index("--context") + 1],
            "long_context",
        )
        self.assertEqual(
            event["argv"][event["argv"].index("--effort") + 1],
            "xhigh",
        )
        self.assertEqual(
            event["argv"][event["argv"].index("--available-tools") + 1],
            "view,search,apply_patch",
        )

    def test_readiness_selects_sol_after_code_and_review_probes(self) -> None:
        selection = self.base / "provider-selection.json"
        result = self._run("readiness", selection=selection)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload, self._selection())
        self.assertEqual(payload["coding"], "code-luna")
        self.assertEqual(payload["review"], "review-sol")
        self.assertEqual(payload["ready"], True)
        self.assertIsNone(payload["error_code"])
        self.assertEqual([event["settings"]["model"] for event in self._events()], [
            "gpt-5.6-luna",
            "gpt-5.6-sol",
        ])

    def test_readiness_uses_luna_only_for_sol_unsupported(self) -> None:
        selection = self.base / "provider-selection.json"
        self.mode_file.write_text("success\nunsupported\nsuccess\n", encoding="ascii")
        result = self._run("readiness", selection=selection)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self._selection()
        self.assertEqual(payload["review"], "review-luna")
        self.assertEqual(payload["ready"], True)
        self.assertEqual(
            [event["settings"]["model"] for event in self._events()],
            ["gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-luna"],
        )

    def test_sol_auth_network_quota_malformed_timeout_closed_and_unknown_block(self) -> None:
        for mode, expected in (
            ("auth", "auth"),
            ("network", "network"),
            ("quota", "quota"),
            ("malformed", "malformed"),
            ("timeout", "timeout"),
            ("closed", "closed"),
            ("unknown", "unknown"),
        ):
            with self.subTest(mode=mode):
                self.mode_file.write_text("success\n" + mode + "\n", encoding="ascii")
                selection = self.base / f"{mode}-selection.json"
                result = self._run(
                    "readiness",
                    selection=selection,
                    timeout=0.1 if mode == "timeout" else 1.0,
                )
                self.assertNotEqual(result.returncode, 0)
                payload = json.loads(result.stdout)
                self.assertFalse(payload["ready"])
                self.assertEqual(payload["error_code"], expected)
                self.assertIsNone(payload["review"])
                self.assertEqual(len(self._events()), 2)
                self.worktree.joinpath("fake-copilot-events.jsonl").unlink()
                self.mode_file.with_suffix(self.mode_file.suffix + ".index").unlink(
                    missing_ok=True
                )

    def test_luna_fallback_failure_blocks_readiness(self) -> None:
        selection = self.base / "provider-selection.json"
        self.mode_file.write_text("success\nunsupported\nauth\n", encoding="ascii")
        result = self._run("readiness", selection=selection)
        self.assertNotEqual(result.returncode, 0)
        payload = self._selection()
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["error_code"], "auth")
        self.assertIsNone(payload["review"])
        self.assertEqual(len(self._events()), 3)

    def test_coding_failure_does_not_trigger_review_fallback(self) -> None:
        selection = self.base / "provider-selection.json"
        self.mode_file.write_text("unsupported\nsuccess\n", encoding="ascii")
        result = self._run("readiness", selection=selection)
        self.assertNotEqual(result.returncode, 0)
        payload = self._selection()
        self.assertEqual(payload["error_code"], "unsupported")
        self.assertIsNone(payload["review"])
        self.assertEqual(len(self._events()), 1)

    def test_review_selection_is_required_and_machine_selected(self) -> None:
        selection = self.base / "provider-selection.json"
        selection.write_text(
            json.dumps(
                {
                    "version": 1,
                    "pins": {
                        "copilot": "1.0.79",
                        "profiles": {
                            "code-luna": {
                                "model": "gpt-5.6-luna",
                                "context": "default",
                                "effort": "max",
                            },
                            "planning-sol": {
                                "model": "gpt-5.6-sol",
                                "context": "long_context",
                                "effort": "xhigh",
                            },
                            "review-sol": {
                                "model": "gpt-5.6-sol",
                                "context": "long_context",
                                "effort": "xhigh",
                            },
                            "review-luna": {
                                "model": "gpt-5.6-luna",
                                "context": "long_context",
                                "effort": "max",
                            },
                        },
                    },
                    "coding": "code-luna",
                    "review": "review-luna",
                    "ready": True,
                    "error_code": None,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.chmod(selection, 0o600)
        result = self._run("run", profile="review", policy="review", selection=selection)
        self.assertEqual(result.returncode, 0, result.stderr)
        event = self._events()[0]
        self.assertEqual(event["settings"]["model"], "gpt-5.6-luna")
        self.assertEqual(event["settings"]["contextTier"], "long_context")

    def test_invalid_selection_and_settings_paths_fail_closed(self) -> None:
        invalid_selection = self.base / "invalid-selection.json"
        invalid_selection.write_text("not-json\n", encoding="ascii")
        result = self._run(
            "run",
            profile="review",
            policy="review",
            selection=invalid_selection,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self._events(), [])

        unsafe_runtime = self.base / "unsafe-runtime"
        unsafe_runtime.mkdir()
        os.chmod(unsafe_runtime, 0o777)
        result = self._run(
            "run",
            profile="code-luna",
            policy="coding",
            runtime=unsafe_runtime,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self._events(), [])

    def test_invalid_credentials_fail_closed(self) -> None:
        candidates: list[pathlib.Path] = [
            self.base / "missing-token",
            self.base / "world-readable-token",
            self.base / "oversized-token",
        ]
        candidates[1].write_text("fixture-token\n", encoding="ascii")
        os.chmod(candidates[1], 0o644)
        candidates[2].write_bytes(b"x" * 9000)
        os.chmod(candidates[2], 0o600)
        symlink = self.base / "symlink-token"
        symlink.symlink_to(self.credential)
        candidates.append(symlink)

        for credential in candidates:
            with self.subTest(credential=credential.name):
                selection = self.base / f"{credential.name}.json"
                result = self._run(
                    "readiness",
                    selection=selection,
                    credential=credential,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(
                    json.loads(result.stdout)["error_code"],
                    "credential-invalid",
                )
                self.assertEqual(self._events(), [])

    def test_readiness_discards_response_and_stderr_content(self) -> None:
        selection = self.base / "provider-selection.json"
        self.mode_file.write_text("success\nauth-secret\n", encoding="ascii")
        result = self._run("readiness", selection=selection)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("fixture-token", result.stdout)
        self.assertNotIn("fixture-token", result.stderr)
        self.assertNotIn("fixture-token", selection.read_text(encoding="utf-8"))

    def test_prompt_injection_cannot_disclose_credentials_or_bypass_authority(self) -> None:
        selection = self.base / "provider-selection.json"
        self.mode_file.write_text("prompt-injection\n", encoding="ascii")
        result = self._run("readiness", selection=selection)
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = result.stdout + result.stderr + selection.read_text(encoding="utf-8")
        self.assertNotIn("fixture-token", combined)
        self.assertNotIn("git push", combined)
        event = self._events()[0]
        self.assertNotIn("fixture-token", json.dumps(event, sort_keys=True))
        protected = event["protected_action"]
        self.assertEqual(protected["action"], "shell(git push --force)")
        self.assertEqual(protected["result"], "rejected")
        self.assertFalse(protected["authority_granted"])
        self.assertIn("denied by", protected["rejection"])
        self.assertNotIn("gh", protected["available_tools"])
        self.assertNotIn("publication", protected["available_tools"])
        self.assertFalse(self.canary.exists())
        self.assertFalse(event["settings"]["sandbox"]["allowBypass"])
        self.assertIn("--deny-tool", event["argv"])

    def test_process_group_is_cleaned_on_signal(self) -> None:
        self.mode_file.write_text("linger\n", encoding="ascii")
        process = subprocess.Popen(
            self._command("run", profile="code-luna", policy="coding"),
            cwd=self.worktree,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        child_pid_file = self.worktree / "fake-copilot-child.pid"
        for _ in range(50):
            if child_pid_file.exists():
                break
            time.sleep(0.02)
        self.assertTrue(child_pid_file.exists())
        child_pid = int(child_pid_file.read_text(encoding="ascii"))
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        for _ in range(50):
            if not self._pid_alive(child_pid):
                break
            time.sleep(0.02)
        self.assertFalse(self._pid_alive(child_pid))

    def test_orphaned_child_is_cleaned_after_parent_exit(self) -> None:
        self.mode_file.write_text("orphan\n", encoding="ascii")
        result = self._run("run", profile="code-luna", policy="coding")
        self.assertEqual(result.returncode, 0, result.stderr)
        child_pid = int(
            (self.worktree / "fake-copilot-child.pid").read_text(encoding="ascii")
        )
        for _ in range(50):
            if not self._pid_alive(child_pid):
                break
            time.sleep(0.02)
        self.assertFalse(self._pid_alive(child_pid))

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            status = pathlib.Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        except (FileNotFoundError, PermissionError):
            return False
        fields = status.split()
        return len(fields) < 3 or fields[2] != "Z"


if __name__ == "__main__":
    unittest.main(verbosity=2)
