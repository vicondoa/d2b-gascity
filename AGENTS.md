# Agent rules for d2b-gascity

## Repository boundary

This private repository is the portable source for one Gas City city, one
external `vicondoa/d2b` product rig on branch `v3`, and one machine-local
`city-source` clone for changes to this repository on `main`. The only active
city root is `cities/d2b-gascity`; the repository root is not a city and must
not contain a repository-local d2b checkout or bind mount.

The plan in `docs/plans/` is the authority. Do not edit a plan to record
progress. The separate private `vicondoa/gascity.nix` repository owns runtime
installation and host integration; do not recreate that boundary here.

Native Gas City owns the supervisor, city registration, imported services,
sessions, retries, and runtime state. Do not add a second lifecycle owner,
custom wrapper, relay, publication helper, or delivery verification system.
Bind the external product checkout only with native `gc rig add`. Bind
`city-source` to a separate clone or worktree, never the live nested city
checkout. Both paths belong in live `.gc/site.toml`, not in portable source.

## Portable model tiers

The reusable `packs/core-city` pack and nested city define exactly four
aliases:

- `deep-thinker`: `gpt-5.6-sol`, medium effort, `long_context`.
- `reviewer`: `grok-4.6`, high effort, `long_context`.
- `solid-worker`: `gpt-5.6-luna`, max effort, `long_context`.
- `fast-worker`: `gpt-5.6-luna`, medium effort, default context.

The city maps the twelve imported roles for both rigs to those aliases. Stock
`builtin:codex` remains an explicit alternate provider only. Do not add
foreign providers, custom model adapters, or tier-specific routing machinery.

## Mayor and publication rules

The adapted mayor is one city-local native session using the official
`gc.mayor` skill and official Gas City formulas and roles. It plans, creates
beads, dispatches work, monitors results, and waits when idle. It must never
implement source changes, create replacement agents, merge, force-push, or
bypass either repository's pull-request handoff.

Keep `d2b-governance` registered as a global fragment. Publication must
persist and re-read `metadata.merge_strategy=pr` plus the repository-specific
target: `v3` for `d2b`, `main` for `city-source`. Refuse direct merges and
accept only the pull-request handoff. The d2b Discord formula extension is
product-only. Human owners make merge decisions. Host branch protection for
`v3` is defense-in-depth: it must require pull requests and apply to
administrators, but this repository does not claim the current host is already
configured that way.

## Source, host, and reset boundaries

Use the official Gas City core, Beads, Gas City pack, and Discord packs pinned
in the nested `pack.toml` and `packs.lock`. The host supplies `gc`, Copilot
CLI, optional Codex, `gh`, ingress, credentials, mounts, mappings, and
launchers.

The clean reset is human-only. Before changing runtime state, inventory
active work and Discord apps, guild/channel/role allowlists, channel and rig
maps, room and DM bindings, and launchers privately. Stop and unregister the
old root city, confirm the d2b bind-mount source, unmount it without
recursive deletion, preserve the external checkout's product-local
`.beads/`, `.gitignore`, and agent hooks, and remove only confirmed old
root-city runtime paths. Set host-local `GC_CITY_PATH` to
`cities/d2b-gascity`, initialize with
`gc init --file city.toml --preserve-existing --no-start .` from that nested
directory, bind the verified checkout with `gc rig add`, and re-import
Discord through native commands. Create a separate d2b-gascity clone or
worktree for `city-source`, seed only its machine-local site binding, and
provision it with `gc rig add --start-suspended`. Never bind it to the live
nested city checkout.

## Privacy and credentials

Never commit or publish:

- private host values, authorities, addresses, users, channels, roles, maps,
  bindings, launchers, or host configuration;
- credentials, tokens, keys, cookies, password hashes, or credential paths;
- `.gc`, `.beads`, Dolt, databases, worktrees, sessions, sockets, logs,
  reports, or copied runtime state;
- live prompts, model responses, or private pull-request payloads.

Discord app tokens must be streamed through `/dev/stdin` and never stored
here. Preserve least-privilege permissions and the official service exposure
boundary: `discord-interactions` is public, `discord-admin` is protected,
and `discord-gateway` is private. Keep Copilot Requests, d2b publication, and
Discord app credentials separate. Never couple `GH_TOKEN` to a Copilot token.

Generic placeholders and `127.0.0.1` are allowed. `.gitignore` is a
convenience, not a security boundary. Review staged files and the complete
diff before any commit.

## Change and validation rules

- Make one logical change per commit.
- Keep ownership and merge decisions with a human.
- Use ASCII hyphens only.
- Preserve Apache-2.0 licensing for local content and upstream notices for
  imported content.
- Use `mol-d2b-discord-fix-issue.toml` only as the narrow native
  first-run `origin/v3` workspace-setup extension of the official Discord
  formula. Its resume path must fail closed for dirty worktrees, missing
  branches, and legacy or missing `base_ref`/`fork_sha` provenance.

Run the smallest check that proves the changed contract:

```text
python3 tests/test_city.py
make check
GC_BIN=/path/to/gc python3 tests/test_city.py
```

The `GC_BIN` command is optional native smoke coverage. Live authenticated
ingress, Copilot execution, Discord traffic, and credentialed publication
are redacted manual smokes, never committed evidence.

See [README.md](README.md), [docs/operations.md](docs/operations.md),
[docs/testing.md](docs/testing.md), and the recipes for the current source
and runtime contracts. Local adapted cookbook material and license boundaries
are recorded in [PROVENANCE.md](PROVENANCE.md).
