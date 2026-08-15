from __future__ import annotations

import pathlib
import stat
import tomllib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CITY = ROOT / "city" / "city.toml"
PROVIDER_SCRIPT = ROOT / "scripts" / "copilot-provider.py"
PUBLICATION_WORKER = ROOT / "scripts" / "publication-worker.py"

EXPECTED = {
    "copilot-planning-sol": ("planning-sol", "planning"),
    "copilot-review": ("review", "review"),
    "copilot-review-sol": ("review-sol", "review"),
    "copilot-review-luna": ("review-luna", "review"),
    "copilot-code-luna": ("code-luna", "coding"),
}


class ProviderPolicyTests(unittest.TestCase):
    def test_portable_providers_are_direct_acp_wrappers(self) -> None:
        config = tomllib.loads(CITY.read_text(encoding="utf-8"))
        providers = config.get("providers", {})
        self.assertEqual(set(providers), set(EXPECTED) | {"publication-worker"})
        for name, (profile, policy) in EXPECTED.items():
            with self.subTest(provider=name):
                provider = providers[name]
                self.assertEqual(provider["base"], "builtin:copilot")
                self.assertEqual(
                    provider["command"],
                    "d2b-gascity-copilot-provider",
                )
                self.assertEqual(
                    provider["acp_command"],
                    "d2b-gascity-copilot-provider",
                )
                self.assertEqual(
                    provider["path_check"],
                    "d2b-gascity-copilot-provider",
                )
                self.assertEqual(provider["args"], ["run"])
                self.assertEqual(provider["ready_delay_ms"], 0)
                self.assertTrue(provider["supports_acp"])
                self.assertEqual(
                    provider["acp_args"],
                    [
                        "run",
                        "--profile",
                        profile,
                        "--tool-policy",
                        policy,
                    ],
                )
        self.assertEqual(
            providers["publication-worker"],
            {
                "command": "d2b-gascity-publication-worker",
                "prompt_mode": "none",
                "ready_delay_ms": 0,
                "path_check": "d2b-gascity-publication-worker",
                "supports_acp": False,
            },
        )

    def test_tool_policies_are_closed(self) -> None:
        config = tomllib.loads(CITY.read_text(encoding="utf-8"))
        providers = config["providers"]
        self.assertEqual(
            providers["copilot-planning-sol"]["acp_args"][-1],
            "planning",
        )
        self.assertEqual(
            providers["copilot-review"]["acp_args"][-1],
            "review",
        )
        self.assertEqual(
            providers["copilot-code-luna"]["acp_args"][-1],
            "coding",
        )
        self.assertNotIn("allow-all", CITY.read_text(encoding="utf-8"))

    def test_wrapper_is_packaged_source_and_executable(self) -> None:
        self.assertTrue(PROVIDER_SCRIPT.is_file())
        self.assertTrue(PROVIDER_SCRIPT.stat().st_mode & stat.S_IXUSR)
        self.assertTrue(PUBLICATION_WORKER.is_file())
        self.assertTrue(PUBLICATION_WORKER.stat().st_mode & stat.S_IXUSR)

    def test_publication_worker_is_not_an_acp_provider(self) -> None:
        config = tomllib.loads(CITY.read_text(encoding="utf-8"))
        publisher = next(
            patch
            for patch in config["patches"]["agent"]
            if patch["dir"] == "d2b" and patch["name"] == "publisher"
        )
        self.assertEqual(
            publisher["start_command"],
            "d2b-gascity-publication-worker",
        )
        self.assertEqual(publisher["provider"], "publication-worker")
        self.assertEqual(publisher["session"], "tmux")
        self.assertEqual(publisher["lifecycle"], "one_shot")

    def test_provider_surface_has_no_second_lifecycle_or_transport(self) -> None:
        paths = [
            CITY,
            ROOT / "city" / "providers",
            PROVIDER_SCRIPT,
            ROOT / "tests" / "acceptance" / "copilot-acp.py",
            ROOT / "tests" / "fixtures" / "acp",
        ]
        forbidden = (
            "agent-launcher",
            "agent server",
            "fdproxy",
            "session.db",
            "session database",
            "retry ledger",
            "retry_ledger",
            "per-child",
            "custom lifecycle service",
        )
        for path in paths:
            candidates = [path] if path.is_file() else sorted(path.rglob("*"))
            for candidate in candidates:
                if not candidate.is_file() or candidate.suffix not in {
                    ".json",
                    ".md",
                    ".py",
                    ".toml",
                }:
                    continue
                text = candidate.read_text(encoding="utf-8").lower()
                for marker in forbidden:
                    self.assertNotIn(
                        marker,
                        text,
                        f"{marker} in {candidate.relative_to(ROOT)}",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
