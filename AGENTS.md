# Agent rules for d2b-gascity

## Repository boundary

This is private infrastructure for one portable Gas City city and one
`vicondoa/d2b` rig based on branch `v3`. It is not a copy of the d2b product
repository and must not acquire unrelated product code or full d2b history.

The plan in `docs/plans/` is the authority. Do not edit the plan to record
progress. The separate private `vicondoa/gascity.nix` repository owns runtime
installation and host integration; do not recreate or modify that boundary
here.

The city is owned by native Gas City lifecycle and state. Do not add a second
lifecycle owner, custom wrapper, relay, publication helper, or delivery
verification system.

## Privacy boundary

Never commit or publish:

- private host values, authorities, addresses, users, channels, roles, or
  host configuration;
- credentials, tokens, keys, cookies, password hashes, or credential paths;
- `.gc`, `.beads`, Dolt, databases, worktrees, sessions, sockets, logs,
  reports, or copied runtime state;
- live prompts, model responses, or private pull-request payloads.

Generic placeholders, planted non-sensitive prompts, and `127.0.0.1` are
allowed. `.gitignore` is a convenience, not a security boundary.

## Change and workflow rules

- Make one logical change per commit.
- Keep ownership and merge decisions with a human.
- Use ASCII hyphens only.
- Preserve Apache-2.0 licensing for local content and upstream notices for
  imported content.
- Use the official Gas City core, Beads, Gas City pack, and Discord packs
  pinned in `pack.toml` and `packs.lock`.
- Use `mol-d2b-discord-fix-issue.toml` only as a narrow native
  first-run `origin/v3` workspace-setup extension of the official Discord
  formula. Its resume path must fail closed for dirty worktrees, missing
  branches, and legacy or missing `base_ref`/`fork_sha` provenance.
- Keep `d2b-governance` registered as a global fragment. Publication must
  refuse direct merges and accept only the pull-request handoff; never merge
  or force-push, and keep merge decisions human-owned.
- Host branch protection for `v3` is defense-in-depth: it must require pull
  requests and apply to administrators. This repository does not claim the
  current host is already configured that way.
- Default to Gas City's stock builtin Copilot CLI provider with the Grok
  planning and Luna coding lanes. Keep stock `builtin:codex` available as an
  alternate provider. Do not add a custom Copilot or Codex adapter, alternate
  transport, a city-owned Discord service, a custom relay, or publication
  machinery.
- Keep Copilot Requests, d2b publication, and Discord app credentials
  separate. Do not couple `GH_TOKEN` to a Copilot token.

## Model lanes

Planning and primary review use Grok `grok-4.6` with `high` effort and
`long_context`. Coding uses Luna with `max` effort. Review falls back to Luna
only when Grok is explicitly unsupported or unavailable.

## Validation

Use the smallest check that proves the changed contract. The repository gate
is `python3 tests/test_city.py`, also available as `make check`. An optional
native smoke can set `GC_BIN` to a pinned or host-supplied `gc` executable.
Live authenticated ingress and credentialed publication are redacted manual
smokes, never committed evidence.
