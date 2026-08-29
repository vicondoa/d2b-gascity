# Cookbook layout and model tiers

Status: accepted design for the `d2b-gascity` source repository.

## Context

The repository is portable city source for one external d2b rig. The active
city is now nested at `cities/d2b-gascity`, while reusable model-tier data and
generic mayor fragments live in `packs/core-city`. The external d2b checkout
is a host-owned source and must not appear as a repository-local checkout or
bind mount.

This design adapts selected cookbook concepts without importing a foreign
provider family, runtime state, workflow implementation, or host integration.
Native Gas City remains the only lifecycle owner. Human operators remain the
owners of reset, publication, and merge decisions.

## Decisions

### Nested source layout

`cities/d2b-gascity` is the only active Gas City root. It contains the
portable city declaration, pinned imports, d2b formula extension, governance
fragment, generated role-tier projection, and city-local mayor. The reusable
`packs/core-city` pack contains only generic tier data, generation support,
and mayor fragments.

There is no repository-local d2b checkout, bind mount, submodule, copied
product tree, or committed rig path. Operators bind the verified external
checkout through native `gc rig add`; only live `.gc/site.toml` records that
host path.

### Four model tiers

The city defines exactly four aliases through stock `builtin:copilot`:

| Tier | Model | Effort | Context |
| --- | --- | --- | --- |
| `deep-thinker` | `gpt-5.6-sol` | `medium` | `long_context` |
| `reviewer` | `grok-4.6` | `high` | `long_context` |
| `solid-worker` | `gpt-5.6-luna` | `max` | `long_context` |
| `fast-worker` | `gpt-5.6-luna` | `medium` | `default` |

The imported roles map to the tiers as follows:

- `deep-thinker`: `requirements-planner`, `design-author`,
  `task-decomposer`, and the city-local mayor;
- `reviewer`: `design-implementation-reviewer`,
  `design-test-risk-reviewer`, `implementation-reviewer`, `gap-analyst`,
  `review-synthesizer`, and `issue-triager`;
- `solid-worker`: `implementation-worker`;
- `fast-worker`: `run-operator` and `publisher`.

Stock `builtin:codex` remains available as an alternate provider only. It is
not a tier, a default, or a custom adapter. The city does not add a Copilot
wrapper, Codex adapter, alternate transport, or router configuration.

### Adapted city-local mayor

The mayor is one always-on city-scoped session with `wake_mode = "fresh"`,
`max_active_sessions = 1`, work directory `.gc/agents/mayor`, and the
`deep-thinker` tier. It uses the official `gc.mayor` skill and official
Gas City formulas and roles to plan, create beads, dispatch work, monitor
results, and wait when idle.

The mayor never implements source changes, creates replacement lifecycle
machinery, merges, force-pushes, or bypasses the d2b `v3` pull-request
handoff. Reusable fragments remain in `packs/core-city`; d2b policy remains
city-local.

### Official imports and governance

The city keeps the official Gas City core, Beads, Gas City pack, and Discord
pack imports pinned in `pack.toml` and `packs.lock`. The local
`mol-d2b-discord-fix-issue` formula is only a narrow first-run
`origin/v3` workspace-setup extension of the official Discord formula.
The `d2b-governance` fragment remains global and requires
`metadata.target=v3`, `metadata.merge_strategy=pr`, refusal of direct merges,
and human-owned pull-request handoff. The city never merges or force-pushes.

## Runtime and host contract

Installation remains inert. From the nested city directory, the operator
initializes in place:

```text
gc init --file city.toml --preserve-existing --no-start .
```

The host sets `GC_CITY_PATH` to `cities/d2b-gascity` and binds the external
checkout with:

```text
gc rig add <verified-d2b-checkout> --name d2b --city .
```

Native Gas City owns supervisor registration, services, sessions, retries,
stop, and runtime state. The host owns private paths, credentials, mounts,
Discord mappings, bindings, launchers, and service exposure. Copilot
Requests, d2b publication, and Discord app credentials remain separate.

## Clean reset contract

Reset is human-only and fail-closed:

1. Make a private redacted preflight inventory of active work and Discord
   apps, allowlists, channel and rig maps, room and DM bindings, launchers,
   and service exposure.
2. Stop and unregister the old root city; verify that root and nested city
   definitions are never active together.
3. Confirm the d2b bind-mount source and users, then unmount the bind mount
   without recursive deletion.
4. Preserve the recorded external checkout, remotes, branches, open pull
   requests, and product-local `.beads/`, `.gitignore`, and agent hooks.
5. Remove only confirmed old root-city `.gc`, `.beads`, session, and worktree
   paths. Never traverse or delete the external checkout.
6. Set host-local `GC_CITY_PATH` and run the nested `gc init`. Create a separate
   d2b-gascity clone or worktree, seed its machine-local `city-source` binding
   in `.gc/site.toml`, then provision `d2b` and `city-source` through native
   `gc rig add`. Confirm one registered city with separate product and
   city-source work surfaces.
7. Re-import Discord with token input through `/dev/stdin`, least-privilege
   permissions, guild/channel/role allowlists, and the service exposure
   boundaries: public `discord-interactions`, protected `discord-admin`, and
   private `discord-gateway`.

No `.gc`, `.beads`, Dolt, sessions, worktrees, mappings, credentials,
prompts, responses, reports, or copied runtime state is migrated.

## Provenance and non-goals

The layout, tier vocabulary, mayor concepts, reset guidance, and selected
wording adapt MIT-licensed material from
[thinkjones/gascity-cookbook](https://github.com/thinkjones/gascity-cookbook).
Only those portable concepts and limited text are adapted. Official pins,
native lifecycle, privacy boundaries, credential separation, and PR-only
publication remain local requirements.

[rencire/gascity-flake](https://github.com/rencire/gascity-flake) has no
license. No content was copied from it. In particular, this repository does
not acquire its host integration, shell machinery, hooks, or development
workflow.

The design does not introduce a second lifecycle owner, a city-owned Discord
service, a relay, publication machinery, a repository-local rig checkout, or
an automated destructive reset.

## Verification

The focused gate is:

```text
python3 tests/test_city.py
```

It checks the nested layout, exact four tiers and twelve assignments, single
mayor, official pins, governance, privacy, and documentation markers. Native
smoke with a host-supplied `GC_BIN` additionally verifies nested
initialization, local pack import, and isolated external rig binding without
source mutation. Authenticated ingress, Copilot execution, Discord traffic,
and credentialed publication remain redacted manual smokes.
