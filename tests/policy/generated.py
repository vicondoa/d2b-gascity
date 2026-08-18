from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
import unittest

from scripts.generate_inventory import inventory, render


ROOT = pathlib.Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "tests" / "generated" / "repository-inventory.json"


class GeneratedInventoryPolicyTests(unittest.TestCase):
    def test_inventory_matches_deterministic_generator(self) -> None:
        self.assertEqual(INVENTORY.read_bytes(), render(inventory(ROOT)))

    def test_inventory_covers_every_current_surface(self) -> None:
        payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
        categories = payload["categories"]
        self.assertEqual(
            set(categories),
            {
                "docs",
                "generated_excluded",
                "governance",
                "production_sources",
                "tests",
                "workflows",
            },
        )
        categorized = [
            path
            for values in categories.values()
            for path in values
        ]
        self.assertEqual(len(categorized), len(set(categorized)))
        self.assertEqual(
            set(categorized),
            {
                path
                for values in categories.values()
                for path in values
            },
        )
        self.assertIn(
            "tests/generated/repository-inventory.json",
            categories["generated_excluded"],
        )
        self.assertIn("Makefile", payload["production_sources"])
        self.assertIn("flake.nix", payload["production_sources"])
        self.assertIn("tests/run.py", payload["tests"])
        self.assertIn(".github/workflows/check.yml", payload["workflows"])
        self.assertIn("d2b-gascity", payload["vm_checks"])
        self.assertIn("package-smoke", payload["flake_checks"])
        acceptance = {
            entry["path"]: entry
            for entry in payload["manual_acceptance"]
        }
        self.assertEqual(acceptance["tests/acceptance/copilot-acp.py"]["mode"], "hermetic")
        self.assertTrue(acceptance["tests/acceptance/copilot-acp.py"]["executed"])
        self.assertEqual(acceptance["tests/acceptance/rollback.py"]["mode"], "hermetic")
        self.assertTrue(acceptance["tests/acceptance/rollback.py"]["executed"])
        self.assertEqual(
            acceptance["tests/acceptance/copilot-acp-feasibility.py"]["mode"],
            "manual",
        )

    def test_test_execution_classifies_each_test_artifact_once(self) -> None:
        payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
        entries = payload["test_execution"]
        paths = [entry["path"] for entry in entries]
        self.assertEqual(paths, sorted(set(paths)))
        self.assertEqual(
            set(paths),
            set(payload["tests"]) | set(payload["categories"]["generated_excluded"]),
        )
        self.assertEqual(
            {entry["role"] for entry in entries},
            {
                "documentation",
                "executed policy",
                "executed fixture",
                "explicit hermetic acceptance",
                "ingress acceptance",
                "runner",
                "helper/fixture data",
                "Nix check",
                "VM check",
                "generated data",
                "manual",
            },
        )
        by_role = {
            role: {entry["path"] for entry in entries if entry["role"] == role}
            for role in {entry["role"] for entry in entries}
        }
        self.assertEqual(by_role["runner"], {"tests/run.py"})
        self.assertEqual(by_role["generated data"], {"tests/generated/repository-inventory.json"})
        self.assertEqual(by_role["documentation"], {"tests/README.md"})
        self.assertEqual(
            by_role["explicit hermetic acceptance"],
            {
                "tests/acceptance/copilot-acp.py",
                "tests/acceptance/rollback.py",
            },
        )
        self.assertEqual(
            by_role["ingress acceptance"],
            {"tests/fixtures/ingress/run.py"},
        )
        self.assertEqual(
            by_role["manual"],
            {"tests/acceptance/copilot-acp-feasibility.py"},
        )
        self.assertEqual(
            by_role["VM check"],
            {"tests/host/d2b-gascity.nix"},
        )
        self.assertEqual(
            by_role["Nix check"],
            {"tests/nix/module.nix", "tests/smoke/package.nix"},
        )
        self.assertEqual(
            by_role["executed policy"],
            {
                path
                for path in payload["tests"]
                if path.startswith("tests/policy/") and path.endswith(".py")
            },
        )
        self.assertEqual(
            by_role["executed fixture"],
            {
                path
                for path in payload["tests"]
                if path.startswith("tests/fixtures/")
                and pathlib.PurePosixPath(path).name.startswith("test_")
            },
        )

    def test_unclassified_test_artifact_fails_inventory_generation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-generated-") as directory:
            root = pathlib.Path(directory)
            shutil.copy2(ROOT / "flake.nix", root / "flake.nix")
            (root / "tests").mkdir()
            (root / "tests" / "regression.py").write_text("fixture\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unclassified test artifact"):
                inventory(root)

    def test_planted_source_addition_requires_inventory_regeneration(self) -> None:
        with tempfile.TemporaryDirectory(prefix="u9-generated-") as directory:
            root = pathlib.Path(directory)
            for relative in ("flake.nix",):
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            (root / "scripts").mkdir()
            (root / "scripts" / "generate_inventory.py").write_text(
                (ROOT / "scripts" / "generate_inventory.py").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "tests").mkdir()
            (root / "tests" / "generated").mkdir()
            (root / "scripts" / "new-policy.py").write_text("fixture\n", encoding="utf-8")
            expected = render(inventory(root))
            self.assertIn(b"scripts/new-policy.py", expected)
            self.assertNotEqual(expected, INVENTORY.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
