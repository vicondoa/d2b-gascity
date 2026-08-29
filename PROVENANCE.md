# Provenance

## Extraction source

The standalone repository begins from a clean source snapshot of
`vicondoa/d2b` at provenance commit `9e0abd0c`. This records source authority
only. It does not import the d2b repository's full history, identities, tags,
worktrees, or runtime state.

The repository contains reviewed Gas City city configuration, not a fork of
the d2b product. The portable city is rooted at `cities/d2b-gascity`; the
host-owned external d2b checkout is bound at runtime through `gc rig add` and
is never copied into this repository.

## Upstream inputs

| Component | Source | Pin | License or terms |
| --- | --- | --- | --- |
| Gas City | [gastownhall/gascity](https://github.com/gastownhall/gascity) | `v1.4.1`, `f895c0ff47d6ee9334ed282a416387eb5b084d24` | MIT |
| Gas City packs | [gastownhall/gascity-packs](https://github.com/gastownhall/gascity-packs) | `9f98ea4e1974cb49d18cd0c453eb81b2370cca84` | Retain upstream notices and verify pack terms before redistribution |
| Gas City pack | [gastownhall/gascity-packs/gascity](https://github.com/gastownhall/gascity-packs/tree/9f98ea4e1974cb49d18cd0c453eb81b2370cca84/gascity) | `9f98ea4e1974cb49d18cd0c453eb81b2370cca84` | Retain upstream notices |
| Discord pack | [gastownhall/gascity-packs/discord](https://github.com/gastownhall/gascity-packs/tree/9f98ea4e1974cb49d18cd0c453eb81b2370cca84/discord) | `9f98ea4e1974cb49d18cd0c453eb81b2370cca84` | Retain upstream notices |
| Beads | [steveyegge/beads](https://github.com/steveyegge/beads) | `v1.2.2`, `6c124203e771433a3550c348771a5b5e27fd3c21` | MIT |
| Dolt | [dolthub/dolt](https://github.com/dolthub/dolt) | `2.1.7` | Apache-2.0 |

The official Gas City core, Beads, Gas City pack, and Discord pack imports
are recorded in the nested city's `pack.toml` and `packs.lock`. The city
uses stock `builtin:copilot` through four local aliases:
`deep-thinker` (`gpt-5.6-sol`, medium, `long_context`),
`reviewer` (`grok-4.6`, high, `long_context`),
`solid-worker` (`gpt-5.6-luna`, max, `long_context`), and
`fast-worker` (`gpt-5.6-luna`, medium, `default`). Stock `builtin:codex`
remains available as an alternate provider only. Copilot CLI and optional
Codex installation belong to the separate `vicondoa/gascity.nix` repository
or another compatible host source.

The local `mol-d2b-discord-fix-issue.toml` is a narrow native extension of
the pinned official Discord formula. It overrides only workspace setup to
create first-run work from `origin/v3` and apply fail-closed recorded branch
resume and rebase checks; the official Discord workflow remains the source
for all other steps.

The local `d2b-governance` fragment records the `v3` target, PR-only
publication policy, and human-owned merge boundary without adding a service
or transport. The city-local mayor adapts the cookbook coordinator concept
through the official `gc.mayor` skill and official Gas City formulas and
roles; it never implements or merges.

## Adapted cookbook material

The repository adapts selected concepts and limited text from
[thinkjones/gascity-cookbook](https://github.com/thinkjones/gascity-cookbook),
which is MIT-licensed. The adapted material includes the cookbook-style
`cities/d2b-gascity` layout, reusable model-tier vocabulary, city-local mayor
recipe, and operator-oriented reset guidance. Adaptation is limited to those
portable concepts and wording; cookbook provider families, foreign workflow
machinery, hourly sweeps, runtime state, and private payloads were not copied.
The local implementation preserves official Gas City pins, native lifecycle,
the d2b `v3` PR-only gate, and this repository's privacy boundary.

The [rencire/gascity-flake](https://github.com/rencire/gascity-flake)
repository has no license. No content was copied from it. Any unrelated
development-shell or host-integration ideas remain outside this repository's
ownership boundary.

## License boundary

Local repository content is provided under the Apache License, Version 2.0.
Imported packs and binaries retain their upstream licenses and notices.
Cookbook-derived concepts and text remain identified as MIT-derived above.
Nothing in this file relicenses an imported component.

## State and privacy boundary

Only reviewed portable source is tracked. Never copy into this repository:

- a full d2b history, unrelated product code, worktrees, or copied checkout
  state;
- `.gc`, `.beads`, Dolt databases, sessions, caches, sockets, reports, logs,
  or service dumps;
- credentials, tokens, keys, cookies, password hashes, private paths,
  authorities, addresses, users, channels, roles, mappings, bindings,
  launchers, or host configuration;
- live prompts, model responses, or private pull-request payloads.

The external checkout's product-local `.beads/`, `.gitignore`, and agent
hooks are preserved during the human-only reset but remain outside this
repository. Generic placeholders and `127.0.0.1` are permitted where needed
for portable topology examples and tests.

## Human-owned cutover

The clean reset is an operator procedure, not provenance migration. A
private preflight inventory covers active work and Discord apps, allowlists,
channel and rig maps, room and DM bindings, and launchers. The operator
stops and unregisters the old root city, confirms and unmounts the d2b bind
mount without recursive deletion, removes only confirmed old root-city
runtime paths, sets host-local `GC_CITY_PATH`, initializes the nested city
with `gc init --file city.toml --preserve-existing --no-start .`, binds the
verified external checkout with `gc rig add`, and re-imports Discord through
stdin token input with least privilege and the documented service exposure
boundaries. Copilot Requests, d2b publication, and Discord credentials stay
separate. See [docs/operations.md](docs/operations.md).
