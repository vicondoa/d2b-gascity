from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "nix" / "packages" / "gascity.nix"
PATCH = ROOT / "nix" / "patches" / "gascity-acp-session-identity.patch"
PROVENANCE = ROOT / "PROVENANCE.md"


class GasCityPatchPolicyTests(unittest.TestCase):
    def test_package_applies_named_patch_and_runs_its_focused_tests(self) -> None:
        source = PACKAGE.read_text(encoding="ascii")
        self.assertIn(
            "../patches/gascity-acp-session-identity.patch",
            source,
        )
        self.assertIn("./internal/runtime/acp/...", source)
        self.assertIn("pkgs.python3", source)

    def test_patch_is_ascii_narrow_and_identity_only(self) -> None:
        source = PATCH.read_text(encoding="ascii")
        paths = {
            match.group(1)
            for match in re.finditer(r"^diff --git a/(.*?) b/.*$", source, re.MULTILINE)
        }
        self.assertEqual(
            paths,
            {
                "internal/runtime/acp/acp.go",
                "internal/runtime/acp/acp_test.go",
                "internal/runtime/acp/conn.go",
            },
        )
        for key in (
            "GC_SESSION_ID",
            "GC_INSTANCE_TOKEN",
            "GC_RUNTIME_EPOCH",
        ):
            self.assertIn(f'"{key}"', source)
        self.assertIn(
            "TestStart_SeedsIdentityMetadataBeforeHandshakeCompletes",
            source,
        )
        self.assertNotIn("for k, v := range cfg.Env", source)
        self.assertNotIn("COPILOT_GITHUB_TOKEN", source)

    def test_provenance_names_scope_removal_and_related_orphan_issue(self) -> None:
        source = PROVENANCE.read_text(encoding="ascii")
        self.assertIn("gascity-acp-session-identity.patch", source)
        self.assertIn("gastownhall/gascity#4714", source)
        self.assertIn(
            "can be removed when upstream",
            source,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
