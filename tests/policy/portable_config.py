from __future__ import annotations

import pathlib
import re
import tomllib
import unittest

from scripts.bootstrap import BootstrapError, _validate_private_text


ROOT = pathlib.Path(__file__).resolve().parents[2]
CITY = ROOT / "city"
PACK_COMMIT = "5d2a9d023edbb9ba24fdcff554e89fc3d7da72fe"
GASCITY_COMMIT = "f6741d94861aa14f0253deffbe9efb1cb3a35d92"


class PortableConfigTests(unittest.TestCase):
    def test_portable_files_exist(self) -> None:
        for relative in (
            "city.toml",
            "pack.toml",
            "packs.lock",
            "role-provider-matrix.json",
            "worktree-producer-inventory.json",
        ):
            self.assertTrue((CITY / relative).is_file(), relative)

    def test_city_has_one_pathless_d2b_rig(self) -> None:
        config = tomllib.loads((CITY / "city.toml").read_text())
        self.assertEqual(
            config["api"],
            {"bind": "127.0.0.1", "port": 18372},
        )
        self.assertNotIn("allow_mutations", (CITY / "city.toml").read_text())
        self.assertEqual(
            config["workspace"],
            {"provider": "copilot-review"},
        )
        self.assertNotIn("session", config)
        rigs = config.get("rigs", [])
        self.assertEqual(len(rigs), 1)
        self.assertEqual(rigs[0]["name"], "d2b")
        self.assertEqual(rigs[0]["prefix"], "d2b")
        self.assertEqual(rigs[0]["default_branch"], "v3")
        self.assertNotIn("path", rigs[0])

        roles = config["rigs"][0]["imports"]["roles"]
        self.assertEqual(
            roles["source"],
            "https://github.com/gastownhall/gascity-packs/tree/main/gascity/roles",
        )
        self.assertEqual(roles["version"], f"sha:{PACK_COMMIT}")

    def test_root_pack_declares_pack_v2_and_named_imports(self) -> None:
        pack = tomllib.loads((CITY / "pack.toml").read_text())
        self.assertEqual(pack["pack"]["schema"], 2)
        self.assertEqual(
            pack["imports"]["compound-engineering"]["source"],
            "https://github.com/gastownhall/gascity-packs/tree/main/compound-engineering",
        )
        self.assertEqual(
            pack["imports"]["discord"]["source"],
            "https://github.com/gastownhall/gascity-packs/tree/main/discord",
        )
        self.assertEqual(
            pack["imports"]["gc"]["source"],
            "https://github.com/gastownhall/gascity-packs/tree/main/gascity/roles",
        )
        self.assertEqual(
            pack["imports"]["compound-engineering"]["version"],
            f"sha:{PACK_COMMIT}",
        )
        self.assertEqual(pack["imports"]["discord"]["version"], f"sha:{PACK_COMMIT}")
        self.assertEqual(pack["imports"]["gc"]["version"], f"sha:{PACK_COMMIT}")
        self.assertEqual(
            pack["imports"]["core"]["version"],
            f"sha:{GASCITY_COMMIT}",
        )
        self.assertEqual(pack["imports"]["bd"]["version"], f"sha:{GASCITY_COMMIT}")

    def test_lockfile_contains_only_expected_pins(self) -> None:
        lock = tomllib.loads((CITY / "packs.lock").read_text())
        self.assertEqual(lock["schema"], 1)
        expected = {
            "https://github.com/gastownhall/gascity-packs/tree/main/compound-engineering": (
                PACK_COMMIT
            ),
            "https://github.com/gastownhall/gascity-packs/tree/main/discord": PACK_COMMIT,
            "https://github.com/gastownhall/gascity-packs/tree/main/gascity/roles": PACK_COMMIT,
            "https://github.com/gastownhall/gascity.git//examples/bd": GASCITY_COMMIT,
            "https://github.com/gastownhall/gascity.git//internal/bootstrap/packs/core": (
                GASCITY_COMMIT
            ),
        }
        self.assertEqual(set(lock["packs"]), set(expected))
        for source, commit in expected.items():
            self.assertEqual(lock["packs"][source]["commit"], commit)
            self.assertEqual(lock["packs"][source]["version"], f"sha:{commit}")
            self.assertRegex(lock["packs"][source]["fetched"], r"^\d{4}-\d{2}-\d{2}T")

    def test_portable_source_has_no_runtime_or_private_values(self) -> None:
        forbidden_segments = {".gc", ".beads", "dolt", "worktree", "worktrees"}
        for path in CITY.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(CITY).as_posix()
            parts = pathlib.PurePosixPath(relative).parts
            self.assertNotIn("cities.toml", parts)
            self.assertTrue(forbidden_segments.isdisjoint(parts), relative)
            text = path.read_text()
            self.assertIsNone(
                re.search(
                    r"(?:^|[\s=])/(?:var|etc|home|root|run|srv|opt)(?:/|\b)",
                    text,
                    re.IGNORECASE,
                ),
                relative,
            )
            self.assertIsNone(
                re.search(
                    r"(?im)^\s*(?:token|password|secret|private[_-]?key)\s*=",
                    text,
                ),
                relative,
            )
            if relative == "city.toml":
                self.assertIsNone(re.search(r"(?m)^\s*path\s*=", text), relative)
            self.assertNotIn("file://", text, relative)

    def test_initial_local_pack_has_no_copied_upstream_bodies(self) -> None:
        allowed_names = {"README.md", ".keep"}
        for directory in ("agents", "assets", "formulas", "orders", "providers"):
            root = CITY / directory
            self.assertTrue(root.is_dir(), directory)
            for path in root.rglob("*"):
                if path.is_file():
                    relative = path.relative_to(CITY).as_posix()
                    if relative in {
                        "assets/workflows/do-work/prepare-worktree.md",
                        "assets/workflows/build-base/publish.md",
                        "orders/bd-backup-sync.toml",
                    }:
                        continue
                    self.assertIn(path.name, allowed_names, relative)

    def test_portable_prose_may_describe_worktrees_and_passwords(self) -> None:
        _validate_private_text(
            "assets/workflows/prepare.md",
            "Prepare the worktree without copying a password from host state.",
        )
        with self.assertRaises(BootstrapError):
            _validate_private_text(
                "providers/unsafe.toml",
                'token = "fixture-secret"\n',
            )


if __name__ == "__main__":
    unittest.main()
