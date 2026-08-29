# Provenance

## Extraction source

The standalone repository begins from a clean source snapshot of
`vicondoa/d2b` at provenance commit `9e0abd0c`. This records source authority
only. It does not import the d2b repository's full history, identities, tags,
worktrees, or runtime state.

The repository contains reviewed Gas City city configuration, not a fork of
the d2b product. The root files are authored for this city and the host
owns runtime installation and integration.

## Upstream inputs

| Component | Source | Pin | License or terms |
| --- | --- | --- | --- |
| Gas City | [gastownhall/gascity](https://github.com/gastownhall/gascity) | `v1.4.1`, `f895c0ff47d6ee9334ed282a416387eb5b084d24` | MIT |
| Gas City packs | [gastownhall/gascity-packs](https://github.com/gastownhall/gascity-packs) | `9f98ea4e1974cb49d18cd0c453eb81b2370cca84` | Retain upstream notices and verify pack terms before redistribution |
| Gas City pack | [gastownhall/gascity-packs/gascity](https://github.com/gastownhall/gascity-packs/tree/9f98ea4e1974cb49d18cd0c453eb81b2370cca84/gascity) | `9f98ea4e1974cb49d18cd0c453eb81b2370cca84` | Retain upstream notices |
| Discord pack | [gastownhall/gascity-packs/discord](https://github.com/gastownhall/gascity-packs/tree/9f98ea4e1974cb49d18cd0c453eb81b2370cca84/discord) | `9f98ea4e1974cb49d18cd0c453eb81b2370cca84` | Retain upstream notices |
| Beads | [steveyegge/beads](https://github.com/steveyegge/beads) | `v1.2.2`, `6c124203e771433a3550c348771a5b5e27fd3c21` | MIT |
| Dolt | [dolthub/dolt](https://github.com/dolthub/dolt) | `2.1.7` | Apache-2.0 |

The Gas City, Beads, Gas City pack, and Discord imports are recorded in
`pack.toml` and `packs.lock`. The city defaults to Gas City's stock builtin
Copilot CLI provider with Grok planning/review and Luna coding lanes, and
keeps stock builtin Codex available. Copilot CLI and optional Codex
installation belong to the separate `vicondoa/gascity.nix` repository or the
compatible host source that supplies those binaries.

The local `formulas/mol-d2b-discord-fix-issue.toml` is a narrow native
extension of the pinned official Discord formula. It overrides only workspace
setup to create first-run work from `origin/v3` and apply fail-closed recorded
branch resume and rebase checks; the official Discord workflow remains the
source for all other steps.
The local `d2b-governance` fragment records the v3 target, PR-only
publication policy, and human-owned merge boundary without adding a service
or transport.

## License boundary

Local repository content is provided under the Apache License, Version 2.0.
Imported packs and binaries retain their upstream licenses and notices.
The imported packs are source-only; materialized build outputs and runtime
state stay outside tracked files. Nothing in this file relicenses an
imported component.

## State and privacy boundary

Only reviewed portable source is tracked. Never copy into this repository:

- full d2b history, unrelated product code, worktrees, or copied checkout
  state;
- `.gc`, `.beads`, Dolt databases, sessions, caches, sockets, reports, logs,
  or service dumps;
- credentials, tokens, keys, cookies, password hashes, private paths,
  authorities, addresses, users, channels, roles, or host configuration;
- live prompts, model responses, or private pull-request payloads.

Generic placeholders and `127.0.0.1` are permitted where needed for portable
topology examples and tests.
