from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]

NEGATIVE_SUCCESSORS = {
    "second lifecycle unit": (
        "tests/policy/provider.py",
        "test_provider_surface_has_no_second_lifecycle_or_transport",
    ),
    "committed site/runtime paths": (
        "tests/policy/portable_config.py",
        "test_portable_source_has_no_runtime_or_private_values",
    ),
    "non-loopback supervisor": (
        "tests/policy/topology.py",
        "test_supervisor_is_fixed_loopback_and_forbidden_overrides_are_absent",
    ),
    "non-v3 worktree producer": (
        "tests/policy/composition.py",
        "test_worktree_creators_start_from_origin_v3",
    ),
    "wrong PR state/SHA/base": (
        "tests/policy/publication.py",
        "test_wrong_remote_dirty_head_or_base_fail_before_github",
    ),
    "force/merge/bypass": (
        "tests/policy/publication.py",
        "test_concurrent_branch_create_is_rejected_without_force",
    ),
    "public dashboard bind": (
        "tests/policy/topology.py",
        "test_supervisor_is_fixed_loopback_and_forbidden_overrides_are_absent",
    ),
    "runtime-state additions": (
        "tests/policy/privacy.py",
        "test_planted_runtime_state_is_rejected_even_when_ignored",
    ),
    "target mutation/write/read grants": (
        "tests/policy/topology.py",
        "test_supervisor_is_fixed_loopback_and_forbidden_overrides_are_absent",
    ),
    "allowed_origins": (
        "tests/policy/topology.py",
        "test_supervisor_is_fixed_loopback_and_forbidden_overrides_are_absent",
    ),
    "Host/Origin rewriting": (
        "tests/policy/topology.py",
        "test_browser_headers_methods_bodies_and_streams_survive_relay",
    ),
    "missing allowed_hosts": (
        "tests/policy/topology.py",
        "test_split_hosts_and_complete_auth_request_listener_are_explicit",
    ),
    "dropped fetch-site/CSRF/SSE": (
        "tests/policy/topology.py",
        "test_browser_headers_methods_bodies_and_streams_survive_relay",
    ),
    "X-Forwarded authorization": (
        "tests/policy/topology.py",
        "test_browser_headers_methods_bodies_and_streams_survive_relay",
    ),
    "direct relay auth bypass": (
        "tests/policy/topology.py",
        "test_split_hosts_and_complete_auth_request_listener_are_explicit",
    ),
    "credential over-scope": (
        "tests/acceptance/copilot-acp.py",
        "test_code_luna_uses_fixed_argv_environment_and_sandbox",
    ),
    "prompt injection": (
        "tests/acceptance/copilot-acp.py",
        "test_prompt_injection_cannot_disclose_credentials_or_bypass_authority",
    ),
    "unpinned ingress tools": (
        "tests/policy/topology.py",
        "test_exact_ingress_pins_and_auth_hardening_are_present",
    ),
}


class U9NegativeContractTests(unittest.TestCase):
    def test_every_u9_planted_negative_has_an_enforcing_successor(self) -> None:
        for name, (relative, marker) in NEGATIVE_SUCCESSORS.items():
            with self.subTest(negative=name):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(f"def {marker}", text)

    def test_buildbuddy_is_explicitly_out_of_scope_for_u9(self) -> None:
        docs = (ROOT / "docs" / "testing.md").read_text(encoding="utf-8").lower()
        self.assertIn("buildbuddy", docs)
        self.assertIn("out of scope", docs)
        self.assertIn("u9", docs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
