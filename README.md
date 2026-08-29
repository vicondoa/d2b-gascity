# d2b-gascity

`d2b-gascity` is the portable source for one Gas City city and one external
`vicondoa/d2b` rig on branch `v3`. It is city configuration, not a second d2b
product repository.

## Source and ownership boundary

The only active city root in this repository is
`cities/d2b-gascity`. Native Gas City owns the supervisor, city registration,
imported services, sessions, retries, and runtime state. The host owns
credentials, mounts, private paths, Discord mappings, and live configuration.
Runtime installation and optional host integration belong to the separately
owned private `vicondoa/gascity.nix` repository or another compatible host
source.

This repository must not contain a repository-local d2b checkout, bind mount,
submodule, copied product tree, or committed rig path. The external checkout
is connected only through native `gc rig add`; its path is live site state in
`.gc/site.toml`, never portable source.

## Layout

```text
.
|-- cities/
|   `-- d2b-gascity/
|       |-- city.toml
|       |-- model-tiers.toml
|       |-- pack.toml
|       |-- packs.lock
|       |-- agents/mayor/
|       |-- formulas/
|       `-- template-fragments/
|-- packs/
|   `-- core-city/
|       |-- model-tiers.base.toml
|       |-- commands/gen-model-tiers/
|       `-- template-fragments/
|-- docs/
|   |-- designs/
|   |-- operations.md
|   `-- testing.md
|-- recipes/
`-- tests/test_city.py
```

Only reviewed portable source is tracked. Native `.gc`, Beads and Dolt data,
sessions, worktrees, sockets, logs, credentials, prompts, responses, reports,
and host values remain outside tracked files.

## Model tiers

The reusable `packs/core-city` pack supplies tier data and generic mayor
fragments. The city projects exactly these four aliases:

| Tier | Stock provider | Model | Effort | Context |
| --- | --- | --- | --- | --- |
| `deep-thinker` | `builtin:copilot` | `gpt-5.6-sol` | `medium` | `long_context` |
| `reviewer` | `builtin:copilot` | `grok-4.6` | `high` | `long_context` |
| `solid-worker` | `builtin:copilot` | `gpt-5.6-luna` | `max` | `long_context` |
| `fast-worker` | `builtin:copilot` | `gpt-5.6-luna` | `medium` | `default` |

The twelve imported d2b roles use the deterministic map in
[recipes/model-tiers.md](recipes/model-tiers.md). The mayor, requirements
planner, design author, and task decomposer use `deep-thinker`; six review,
analysis, and triage roles use `reviewer`; `implementation-worker` uses
`solid-worker`; and `run-operator` plus `publisher` use `fast-worker`.

Stock `builtin:codex` remains available only as an explicit alternate provider.
It is not a tier, the workspace default, or a replacement for the stock
Copilot provider. No custom Copilot or Codex adapter, relay, or transport is
part of this city.

## Mayor

The adapted city-local mayor is one always-on native session with
`wake_mode = "fresh"`, `max_active_sessions = 1`, work directory
`.gc/agents/mayor`, and the `deep-thinker` tier. It uses the official
`gc.mayor` skill and official Gas City formulas and roles to plan work, create
beads, dispatch work, monitor results, and wait when idle.

The mayor does not implement source changes, create replacement agents, merge,
force-push, or bypass the d2b `v3` pull-request handoff. Human operators own
publication and merge decisions. See
[recipes/the-mayor.md](recipes/the-mayor.md).

## Initialize the nested city

Install the pinned `gc`, `copilot`, and `gh` runtimes, plus optional `codex`
and ingress tooling, from the separate host source. From the nested city
directory, initialize in place:

```text
cd cities/d2b-gascity
export GC_CITY_PATH="$(pwd)"  # host-local; do not commit this value
gc init --file city.toml --preserve-existing --no-start .
gc start
```

The command preserves authored Pack v2 files and does not copy repository
metadata or runtime state. Native Gas City owns lifecycle and per-user state;
do not add a wrapper, second supervisor, or city-starting service.

## Bind the external d2b rig

After verifying the external checkout identity, remotes, branch, worktree,
and product-local bookkeeping, bind it while the nested city is selected:

```text
gc rig add <verified-d2b-checkout> --name d2b --city .
gc status
```

The path is written to live `.gc/site.toml` only. Never add a `path` field to
the portable rig declaration and never recreate the checkout under this
repository. The external checkout's `.beads/`, `.gitignore`, and agent hooks
are product-local rig bookkeeping and must survive a clean reset.

## Discord and publication boundaries

The pinned official Discord pack owns `discord-interactions` (public signed
Interactions), `discord-admin` (tenant/access-policy protected), and
`discord-gateway` (private). Re-import apps with a token streamed through
`/dev/stdin`, guild, channel, and role allowlists, and least-privilege bot
permissions. Keep service exposure boundaries unchanged: only
`discord-interactions` is public, while admin remains protected and the
gateway remains private.

Keep Copilot Requests, d2b publication authorization, and Discord app
credentials separate. Never put credentials, token paths, identifiers,
allowlists, mappings, or live payloads in this repository. Publication must
persist and re-read `metadata.target=v3` and
`metadata.merge_strategy=pr`, refuse direct merges, and never merge or
force-push. Branch protection for `v3` is defense-in-depth and must require
pull requests and apply to administrators; this repository does not claim
that the current host is already configured that way.
The policy requires pull requests and must apply to administrators.

## Clean reset

The reset and bind-mount removal are human-only actions. Follow the
fail-closed, redacted runbook in [docs/operations.md](docs/operations.md):
inventory active work and Discord apps, allowlists, maps, bindings, and
launchers privately; stop and unregister the old root city; confirm and
unmount the d2b bind mount without recursive deletion; remove only confirmed
old root-city runtime paths; initialize the nested city; bind the verified
external checkout; and re-import Discord. The runbook preserves the external
checkout and its product-local `.beads/`, `.gitignore`, and hooks.

## Verification and provenance

Run the credential-free focused gate from the repository root:

```text
python3 tests/test_city.py
```

Optional native smoke uses a host-supplied `GC_BIN` and an isolated external
fixture. Live authenticated ingress, Copilot execution, Discord traffic, and
credentialed publication remain redacted manual smokes.

Local content is Apache-2.0. The adapted cookbook layout, tier vocabulary,
mayor concepts, and selected wording are recorded as MIT-derived material
from [thinkjones/gascity-cookbook](https://github.com/thinkjones/gascity-cookbook).
The [rencire/gascity-flake](https://github.com/rencire/gascity-flake)
repository has no license; no content was copied from it. See
[PROVENANCE.md](PROVENANCE.md).
