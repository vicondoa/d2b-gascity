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

- private host values, authorities, addresses, users, channels, or host
  configuration;
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
- Planning and primary review use Grok `grok-4.6` with `high` effort and
  `long_context`.
- Coding uses Luna with `max` effort.
- Review falls back to Luna only when Grok is explicitly unsupported or
  unavailable.
- Use the stock Gas City Codex provider through the host-managed Codex Router,
  the official Compound Engineering and pinned Slack Full pack, and official
  publication. Do not add Copilot CLI profiles, alternate
  transport, a city-owned Slack service, a custom relay, or publication
  machinery.
- Keep Copilot Requests, d2b publication, and Slack credentials separate.
  Only Slack adapter variables may be inherited by the native Slack
  supervisor. Do not restore the `GH_TOKEN=$COPILOT_GITHUB_TOKEN` coupling.

## Validation

Use the smallest check that proves the changed contract. The repository gate
is `python3 tests/test_city.py`, also available as `make check`. An optional
native smoke can set `GC_BIN` to a pinned or host-supplied `gc` executable.
Live authenticated ingress and credentialed Compound Engineering publication
are redacted manual smokes, never committed evidence.
