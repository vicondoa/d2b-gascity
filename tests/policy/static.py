from __future__ import annotations

import pathlib
import tempfile
import unittest

from scripts.static_policy import static_findings


ROOT = pathlib.Path(__file__).resolve().parents[2]


class StaticPolicyTests(unittest.TestCase):
    def test_repository_static_policy_is_clean(self) -> None:
        self.assertEqual(static_findings(ROOT), [])

    def test_planted_external_make_include_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-static-") as directory:
            root = pathlib.Path(directory)
            (root / "Makefile").write_text("include ../d2b/Makefile\n", encoding="utf-8")
            self.assertTrue(static_findings(root))

    def test_planted_rust_or_harness_workflow_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-static-") as directory:
            root = pathlib.Path(directory)
            workflow = root / ".github" / "workflows"
            workflow.mkdir(parents=True)
            (workflow / "check.yml").write_text(
                "steps:\n"
                "  - run: cargo test\n"
                "    uses: actions/checkout@v4\n",
                encoding="utf-8",
            )
            findings = static_findings(root)
        self.assertTrue(any("unpinned action" in finding for finding in findings))
        self.assertTrue(any("cargo" in finding for finding in findings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
