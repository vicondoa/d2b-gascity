from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

from scripts.privacy_scan import scan_repository


ROOT = pathlib.Path(__file__).resolve().parents[2]


class PrivacyPolicyTests(unittest.TestCase):
    def test_repository_has_no_private_values_or_runtime_state(self) -> None:
        findings = scan_repository(ROOT)
        self.assertEqual(findings, [], "\n".join(map(str, findings)))

    def test_generic_fixture_values_are_allowed_in_tests(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            fixture = root / "tests" / "fixtures"
            fixture.mkdir(parents=True)
            (fixture / "credential.txt").write_text(
                "to" + "ken = \"fixture-token\"\n"
                "pass" + "word = \"fixture-pass\"\n"
                "address = \"192.0.2.10\"\n"
                "url = \"https://gascity.example.test\"\n",
                encoding="utf-8",
            )
            self.assertEqual(scan_repository(root), [])

    def test_planted_runtime_state_is_rejected_even_when_ignored(self) -> None:
        dangerous = (
            ".cache/runtime/state",
            "cache/repos/index",
            ".gc/site.toml",
            ".beads/beads.db",
            "Dolt/state.db",
            "worktrees/private/HEAD",
            "sessions/one/session.json",
            "logs/service.log",
            "sockets/control.sock",
        )
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            for relative in dangerous:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("runtime\n", encoding="utf-8")
            findings = scan_repository(root)
        rules = {finding.rule for finding in findings}
        self.assertIn("runtime-path", rules)
        self.assertIn("runtime-file", rules)

    def test_tracked_runtime_state_is_rejected_without_ignored_only_exception(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            runtime = root / ".gc" / "site.toml"
            runtime.parent.mkdir(parents=True)
            runtime.write_text("runtime\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(root), "add", ".gc/site.toml"], check=True)
            findings = scan_repository(root)
        self.assertIn("runtime-path", {finding.rule for finding in findings})
        self.assertNotIn("ignored-or-untracked", {finding.rule for finding in findings})

    def test_planted_private_paths_addresses_ids_and_payloads_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            path = root / "README.md"
            path.write_text(
                "auth" + "ority = \"cor" + "p.internal\"\n"
                "instance" + "_id = \"real-instance-123\"\n"
                "path = \"/home/" + "alice/private/state\"\n"
                "endpoint = \"https://" + "8.8." + "8.8/private\"\n"
                "operator = \"alice@" + "corp.invalid\"\n"
                "live_" + "response = \"private operator payload\"\n",
                encoding="utf-8",
            )
            findings = scan_repository(root)
        rules = {finding.rule for finding in findings}
        self.assertIn("private-assignment", rules)
        self.assertIn("host-private-path", rules)
        self.assertIn("host-private-address", rules)
        self.assertIn("host-private-authority", rules)
        self.assertIn("unredacted-private-" + "payload", rules)

    def test_quoted_structured_secret_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            (root / "config.json").write_text(
                '{"' + "token" + '": "real-secret-value"}\n',
                encoding="utf-8",
            )
            (root / "config.yaml").write_text(
                '"' + "private-key" + '": "real-private-value"\n',
                encoding="utf-8",
            )
            (root / "config.toml").write_text(
                '"' + "client-secret" + '" = "real-client-secret"\n',
                encoding="utf-8",
            )
            findings = scan_repository(root)
        self.assertIn("credential-assignment", {finding.rule for finding in findings})

    def test_unquoted_structured_secret_and_private_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            (root / "config.json").write_text(
                '{"' + "token" + '": real-secret-value}\n',
                encoding="utf-8",
            )
            (root / "config.yaml").write_text(
                "auth" + "ority: corp.internal\n",
                encoding="utf-8",
            )
            (root / "config.toml").write_text(
                "pass" + "word = real-password-value\n",
                encoding="utf-8",
            )
            findings = scan_repository(root)
        rules = {finding.rule for finding in findings}
        self.assertIn("credential-assignment", rules)
        self.assertIn("private-assignment", rules)

    def test_null_and_safe_placeholder_values_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            (root / "config.yaml").write_text(
                "token: null\n"
                "password: false\n"
                "authority: example.invalid\n"
                "host: 127.0.0.1\n",
                encoding="utf-8",
            )
            fixture = root / "tests" / "fixtures"
            fixture.mkdir(parents=True)
            (fixture / "config.toml").write_text(
                "to" + "ken = fixture-token\n"
                "auth" + "ority = fixture.internal\n",
                encoding="utf-8",
            )
            self.assertEqual(scan_repository(root), [])

    def test_placeholder_assignments_are_not_exempt_in_production(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            (root / "config.toml").write_text(
                "to" + "ken = fixture-token\n",
                encoding="utf-8",
            )
            findings = scan_repository(root)
        self.assertIn("credential-assignment", {finding.rule for finding in findings})

    def test_private_values_fail_inside_test_fixtures(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            fixture = root / "tests" / "fixtures"
            fixture.mkdir(parents=True)
            (fixture / "private.json").write_text(
                '{"path": "/home/' + "alice/private" + '", '
                '"endpoint": "8.8.' + "8.8" + '", '
                '"operator": "alice@' + "corp.invalid" + '", '
                '"private_' + "payload" + '": "operator response"}\n',
                encoding="utf-8",
            )
            findings = scan_repository(root)
        rules = {finding.rule for finding in findings}
        self.assertIn("host-private-path", rules)
        self.assertIn("host-private-address", rules)
        self.assertIn("host-private-authority", rules)
        self.assertIn("unredacted-private-" + "payload", rules)

    def test_planted_secret_material_is_rejected_outside_tests(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            for name, value in (
                ("token.txt", "ghp_" + "123456789012345678901234567890"),
                ("key.pem", "-----BEGIN " + "PRIVATE KEY-----\nsecret\n"),
                ("config.toml", "to" + "ken = \"not-a-fixture-secret\"\n"),
            ):
                (root / name).write_text(value, encoding="utf-8")
            findings = scan_repository(root)
        rules = {finding.rule for finding in findings}
        self.assertIn("credential-material", rules)
        self.assertIn("credential-assignment", rules)

    def test_real_token_material_is_rejected_even_in_test_fixtures(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            fixture = root / "tests" / "fixtures"
            fixture.mkdir(parents=True)
            (fixture / "real-token.txt").write_text(
                "ghp_" + "123456789012345678901234567890\n",
                encoding="utf-8",
            )
            findings = scan_repository(root)
        self.assertIn("credential-material", {finding.rule for finding in findings})

    def test_tracked_only_mode_excludes_ignored_runtime_but_not_tracked_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            (root / "README.md").write_text(
                "to" + "ken = \"not-a-fixture-secret\"\n",
                encoding="utf-8",
            )
            runtime = root / ".gc" / "site.toml"
            runtime.parent.mkdir()
            runtime.write_text("runtime\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
            findings = scan_repository(root, tracked_only=True)
        rules = {finding.rule for finding in findings}
        self.assertNotIn("runtime-path", rules)
        self.assertIn("credential-assignment", rules)

    def test_staged_secret_is_rejected_when_worktree_is_safe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            path = root / "config.toml"
            path.write_text(
                "to" + "ken = \"staged-real-secret\"\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(root), "add", "config.toml"], check=True)
            path.write_text(
                "to" + "ken = \"fixture-token\"\n",
                encoding="utf-8",
            )
            findings = scan_repository(root)
        self.assertIn("credential-assignment", {finding.rule for finding in findings})

    def test_symlink_target_is_scanned_without_dereferencing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            target = root / "target.txt"
            target.write_text("fixture\n", encoding="utf-8")
            link = root / "link.txt"
            link.symlink_to("/home/" + "alice/private")
            findings = scan_repository(root)
        rules = {finding.rule for finding in findings}
        self.assertIn("host-private-path", rules)
        self.assertIn("unsafe-symlink-target", rules)

    def test_relative_symlink_escape_is_rejected_without_dereferencing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            link = root / "nested" / "link.txt"
            link.parent.mkdir()
            link.symlink_to("../../private/credential")
            findings = scan_repository(root)
        self.assertIn("unsafe-symlink-target", {finding.rule for finding in findings})

    def test_tracked_symlink_escape_is_rejected_without_dereferencing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            link = root / "link.txt"
            link.symlink_to("../private/credential")
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(root), "add", "link.txt"], check=True)
            findings = scan_repository(root)
        self.assertIn("unsafe-symlink-target", {finding.rule for finding in findings})

    def test_tracked_binary_blob_is_rejected_by_default(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-privacy-") as directory:
            root = pathlib.Path(directory)
            binary = root / "fixture.bin"
            binary.write_bytes(b"\x00\x01\x02binary\n")
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(root), "add", "fixture.bin"], check=True)
            findings = scan_repository(root)
        self.assertIn("tracked-binary", {finding.rule for finding in findings})


if __name__ == "__main__":
    unittest.main(verbosity=2)
