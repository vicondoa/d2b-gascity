# Copilot ACP feasibility

U13 is a proof-reuse stop gate, not a second live model experiment. The
deployed d2b system already validated direct Copilot ACP create, prompt,
termination, restart, and prompt again with Copilot CLI `1.0.79`. That proof
is authoritative. This repository only verifies the matching U2 closure and
the proof sources at an immutable d2b Git revision.

## Authoritative proof

The evidence revision is
`9e0abd0c80e878567edc903fdf23f73ff432d34c` in the d2b repository. The
verifier reads these paths with `git show <revision>:<path>`:

- `nix/gas-city-contributor/pack/scripts/copilot-profile.py`
  - `PROFILE_SETTINGS` and `PROFILE_EFFORT` define the Sol and Luna profiles.
  - `child_argv` constructs the direct `--acp` command.
  - `_frame`, `_ACPReader`, and `_PROBE_RESPONSE_PHASES` establish NDJSON
    `initialize`, `session/new`, and `session/prompt` handling.
- `nix/gas-city-contributor/pack/scripts/agent-launcher.py`
  - `_send_group_signal`, `os.killpg`, `start_new_session`, and `_spawn_child`
    establish process-group ownership and cleanup.
- `tests/fixtures/gas-city/acp/test_contracts.py`
  - `test_profile_owned_startup_arguments_reject_overrides`
  - `test_probe_uses_ndjson_and_closed_is_classified`
  - `test_client_probe_preserves_initialize_session_new_and_diagnostic_prompt`
  - `test_client_eof_stops_child_and_releases_lease`
  - `test_timeout_kills_exact_process_group_and_releases_slot`
  - `test_direct_probe_classifies_exception_with_stderr`
  - `test_probe_rejects_malformed_idless_messages`
  - `test_sol_auth_network_quota_malformed_and_unknown_block`
  - `test_only_copilot_auth_survives_environment_projection`

The standalone U2 closure pins Gas City
`f6741d94861aa14f0253deffbe9efb1cb3a35d92`, llm-agents.nix
`387989ee56d550d86d46d9458ad68a55b9e0ca3b`, and Copilot CLI `1.0.79`.

## Credential-free verifier

Build the exact U2 runtime:

```text
nix build .#packages.x86_64-linux.gas-city-contributor
```

From the standalone checkout, use generic repo-relative paths for the runtime
and the d2b evidence repository:

```text
python3 tests/acceptance/copilot-acp-feasibility.py \
  --runtime ./result \
  --evidence-repo ../d2b \
  --evidence-revision 9e0abd0c80e878567edc903fdf23f73ff432d34c
```

The verifier does not start Copilot ACP, handle credentials, send prompts, or
parse model responses. It checks that `runtime/bin/copilot` is executable,
reports `1.0.79`, and advertises `--acp`, `--model`, `--context`, and
`--effort`. It then checks the selected revision and proof markers from the
committed d2b sources and tests.

Output is one compact JSON object with `ok`, `mode: "proof-reuse"`, `version`,
`direct`, `evidence_revision`, boolean `checks` for `runtime`, `profiles`,
`protocol`, `restart`, `errors`, and `redaction`, plus a safe `error_code`.
No fake ACP server or standalone protocol implementation is needed.
