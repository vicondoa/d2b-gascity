from __future__ import annotations

import pathlib
import re
import tempfile
import unittest

from scripts.static_policy import ACTION_REF, workflow_findings


ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECK_WORKFLOW = ROOT / ".github" / "workflows" / "check.yml"
UPDATE_WORKFLOW = ROOT / ".github" / "workflows" / "update-generated.yml"


def validate_check_workflow(text: str) -> list[str]:
    lowered = text.lower()
    forbidden = (
        "secrets.",
        "d2b test harness",
        "tests/runner.sh",
        "panel",
        "signoff",
        "speckit",
        "cargo",
        "rustup",
        "copilot-acp-feasibility.py",
        "tests/acceptance/live.py",
        "buildbuddy",
    )
    return [marker for marker in forbidden if marker in lowered]


class WorkflowPolicyTests(unittest.TestCase):
    def test_check_workflow_is_secret_free_and_runs_complete_local_check(self) -> None:
        text = CHECK_WORKFLOW.read_text(encoding="utf-8")
        self.assertFalse(validate_check_workflow(text))
        self.assertIn("runs-on: ubuntu-22.04", text)
        self.assertNotIn("ubuntu-latest", text)
        self.assertNotIn("ubuntu-24.04", text)
        self.assertIn("pull_request:", text)
        self.assertIn("push:", text)
        self.assertIn("cache-nix-action", text)
        self.assertIn("substituters = https://cache.nixos.org", text)
        self.assertNotIn("feat/**", text)
        self.assertRegex(
            text,
            r"(?m)^\s*-\s*run:\s*nix develop --no-write-lock-file "
            r"--command make check\s*$",
        )
        self.assertNotIn("if: ${{ secrets.", text)
        preflight = text.index("Preflight unprivileged user and network namespaces")
        check = text.index(
            "run: nix develop --no-write-lock-file --command make check"
        )
        self.assertLess(preflight, check)
        for marker in (
            'command -v unshare',
            'command -v ip',
            "--user --map-root-user --net",
            "link set lo up",
            "::error::",
        ):
            self.assertIn(marker, text)

    def test_check_workflow_uses_immutable_action_references(self) -> None:
        findings = workflow_findings(ROOT)
        self.assertEqual(findings, [])
        for action, reference in ACTION_REF.findall(CHECK_WORKFLOW.read_text(encoding="utf-8")):
            with self.subTest(action=action):
                self.assertRegex(reference, r"^[0-9a-f]{40}$")

    def test_update_workflow_is_manual_and_cannot_mutate_main_silently(self) -> None:
        text = UPDATE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("push:", text)
        self.assertIn("git diff", text)
        self.assertIn("repository-inventory.patch", text)
        self.assertNotIn("secrets.", text.lower())
        self.assertRegex(text, r"actions/upload-artifact@[0-9a-f]{40}")
        self.assertIn(
            "nix develop --no-write-lock-file --command make update-generated",
            text,
        )

    def test_planted_unpinned_action_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-ci-") as directory:
            root = pathlib.Path(directory)
            workflow = root / ".github" / "workflows"
            workflow.mkdir(parents=True)
            (workflow / "check.yml").write_text(
                "jobs:\n  check:\n    steps:\n      - uses: actions/checkout@v4\n",
                encoding="utf-8",
            )
            findings = workflow_findings(root)
        self.assertEqual(len(findings), 1)
        self.assertIn("unpinned action", findings[0])

    def test_nested_and_docker_action_refs_are_pinned(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-ci-") as directory:
            root = pathlib.Path(directory)
            workflow = root / ".github" / "workflows"
            workflow.mkdir(parents=True)
            (workflow / "nested.yml").write_text(
                "jobs:\n"
                "  build:\n"
                "    steps:\n"
                "      - uses: acme/action/path@v1\n"
                "  reusable:\n"
                "    uses: acme/repo/.github/workflows/reusable.yml@main\n"
                "  docker:\n"
                "    uses: docker://alpine:3\n",
                encoding="utf-8",
            )
            findings = workflow_findings(root)
        self.assertEqual(len(findings), 3)
        self.assertTrue(all("unpinned action" in finding for finding in findings))

    def test_flow_style_action_reference_is_rejected_as_unsupported_syntax(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-ci-") as directory:
            root = pathlib.Path(directory)
            workflow = root / ".github" / "workflows"
            workflow.mkdir(parents=True)
            (workflow / "flow.yml").write_text(
                "jobs:\n"
                "  check:\n"
                "    steps: [{uses: actions/checkout@v4}]\n",
                encoding="utf-8",
            )
            findings = workflow_findings(root)
        self.assertTrue(any("unsupported uses syntax" in finding for finding in findings))

    def test_comments_and_quoted_run_values_do_not_trigger_uses_detection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-ci-") as directory:
            root = pathlib.Path(directory)
            workflow = root / ".github" / "workflows"
            workflow.mkdir(parents=True)
            (workflow / "comments.yml").write_text(
                "# uses: actions/checkout@v4\n"
                "jobs:\n"
                "  check:\n"
                "    steps:\n"
                "      - run: 'echo uses: actions/checkout@v4'\n",
                encoding="utf-8",
            )
            self.assertEqual(workflow_findings(root), [])

    def test_nested_pinned_and_local_action_refs_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-ci-") as directory:
            root = pathlib.Path(directory)
            workflow = root / ".github" / "workflows"
            workflow.mkdir(parents=True)
            (workflow / "nested.yml").write_text(
                "jobs:\n"
                "  build:\n"
                "    steps:\n"
                "      - uses: acme/action/path@"
                + "a" * 40
                + "\n"
                "  reusable:\n"
                "    uses: acme/repo/.github/workflows/reusable.yml@"
                + "b" * 40
                + "\n"
                "  local:\n"
                "    uses: ./.github/actions/local\n"
                "  docker:\n"
                "    uses: docker://alpine:3@sha256:"
                + "c" * 64
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(workflow_findings(root), [])

    def test_live_and_credential_acceptance_are_manual_inventory_surfaces(self) -> None:
        inventory = (
            ROOT / "tests" / "generated" / "repository-inventory.json"
        ).read_text(encoding="utf-8")
        self.assertIn("copilot-acp-feasibility.py", inventory)
        self.assertIn('"mode": "manual"', inventory)
        check = CHECK_WORKFLOW.read_text(encoding="utf-8").lower()
        self.assertNotIn("copilot-acp-feasibility.py", check)
        self.assertNotIn("tests/acceptance/live.py", check)


if __name__ == "__main__":
    unittest.main(verbosity=2)
