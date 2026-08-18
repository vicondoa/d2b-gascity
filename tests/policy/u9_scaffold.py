from __future__ import annotations

import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class U9RepositoryChecksTests(unittest.TestCase):
    def test_public_make_targets_are_repository_local(self) -> None:
        makefile = ROOT / "Makefile"
        self.assertTrue(makefile.is_file())
        text = makefile.read_text(encoding="utf-8")
        for target in (
            "check",
            "test-policy",
            "test-fixtures",
            "test-ingress",
            "test-generated",
            "check-nix",
            "test-vm",
        ):
            self.assertRegex(text, rf"(?m)^{re.escape(target)}\s*:")
        self.assertNotRegex(text, r"(?m)^\s*(?:include|MAKEFILE_LIST).*d2b")
        self.assertNotIn("tests/runner.sh", text)

    def test_repository_runner_is_deterministic_and_owns_runtime_lifecycle(self) -> None:
        runner = ROOT / "tests" / "run.py"
        self.assertTrue(runner.is_file())
        text = runner.read_text(encoding="utf-8")
        for marker in (
            "GC_CONTRIBUTOR_ROOT",
            "U3_PACK_CACHE",
            "D2B_INGRESS_RUNTIME",
            "copilot-acp.py",
            "fixtures/ingress/run.py",
            "RUNTIME_COMMANDS",
            "tempfile.mkdtemp",
            "proc",
            "cleanup",
        ):
            self.assertIn(marker, text)
        self.assertRegex(text, r"sorted\(")
        self.assertNotIn("copilot-acp-feasibility.py", text)
        self.assertNotIn("tests/acceptance/live.py", text)
        self.assertIn("D2B_GASCITY_CHECK_RUN_ID", text)
        self.assertIn('"environ"', text)
        self.assertNotIn("u9-contributor-runtime", text)
        self.assertNotIn("u9-pack-cache", text)
        self.assertNotIn("symlink_to", text)

    def test_generated_inventory_and_generator_exist_without_machine_values(self) -> None:
        generator = ROOT / "scripts" / "generate_inventory.py"
        inventory = ROOT / "tests" / "generated" / "repository-inventory.json"
        self.assertTrue(generator.is_file())
        self.assertTrue(inventory.is_file())
        payload = json.loads(inventory.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("schema"), 1)
        for category in (
            "production_sources",
            "tests",
            "flake_checks",
            "vm_checks",
            "workflows",
            "manual_acceptance",
        ):
            self.assertIn(category, payload)
        rendered = inventory.read_text(encoding="utf-8")
        self.assertNotRegex(rendered, r"20\d\d-\d\d-\d\dT")
        self.assertNotRegex(rendered, r"/(?:home|Users|private|var)/")

    def test_private_ci_workflows_are_hermetic_and_separate(self) -> None:
        check = ROOT / ".github" / "workflows" / "check.yml"
        update = ROOT / ".github" / "workflows" / "update-generated.yml"
        self.assertTrue(check.is_file())
        self.assertTrue(update.is_file())
        check_text = check.read_text(encoding="utf-8")
        update_text = update.read_text(encoding="utf-8")
        for forbidden in (
            "secrets.",
            "d2b",
            "panel",
            "signoff",
            "speckit",
            "cargo",
            "rustup",
            "copilot-acp-feasibility.py",
            "tests/acceptance/live.py",
            "update-generated.yml",
        ):
            self.assertNotIn(forbidden, check_text.lower())
        self.assertIn("workflow_dispatch", update_text)
        self.assertNotIn("push:", update_text)
        self.assertNotIn("pull_request", update_text)
        self.assertNotIn("secrets.", update_text)

    def test_flake_exposes_static_privacy_generated_and_aggregate_checks(self) -> None:
        text = (ROOT / "flake.nix").read_text(encoding="utf-8")
        for marker in (
            "generated-drift",
            "privacy-policy",
            "static-policy",
            "aggregate",
            "vmChecks",
        ):
            self.assertIn(marker, text)
        self.assertIn("aggregate", text)

    def test_privacy_scanner_and_ci_policy_have_planted_negative_apis(self) -> None:
        privacy = ROOT / "scripts" / "privacy_scan.py"
        ci_policy = ROOT / "tests" / "policy" / "ci.py"
        self.assertTrue(privacy.is_file())
        self.assertTrue(ci_policy.is_file())
        privacy_text = privacy.read_text(encoding="utf-8")
        for marker in (
            "ignored",
            "credential",
            "runtime",
            "private",
            "fixture",
            "scan_repository",
        ):
            self.assertIn(marker, privacy_text.lower())
        ci_text = ci_policy.read_text(encoding="utf-8")
        for marker in ("secret", "rust", "speckit", "immutable", "live"):
            self.assertIn(marker, ci_text.lower())

    def test_related_docs_describe_local_boundary_and_manual_credentials(self) -> None:
        docs = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in ("README.md", "CONTRIBUTING.md", "docs/operations.md")
        ).lower()
        self.assertIn("make check", docs)
        self.assertIn("manual", docs)
        self.assertIn("credential", docs)
        self.assertIn("nix sandbox", docs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
