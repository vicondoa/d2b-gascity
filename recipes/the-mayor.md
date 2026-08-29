# The mayor

The adapted mayor is a city-local coordinator, not a second lifecycle owner.
It runs as the single always-on `mayor` session in
`cities/d2b-gascity/agents/mayor/agent.toml`:

- scope: `city`;
- tier: `deep-thinker`;
- wake mode: `fresh`;
- maximum active sessions: `1`;
- work directory: `.gc/agents/mayor`.

## Responsibilities

The mayor uses the official `gc.mayor` skill and official Gas City formulas
and roles to:

1. read the current work state and plan the next bounded action;
2. create or update Beads work;
3. dispatch official formulas and imported roles on the repository-owning rig;
4. monitor results and surface blockers; and
5. wait for the operator when no actionable work exists.

The mayor uses `d2b` for product work targeting `v3` and the separately bound,
suspended-on-start `city-source` rig for this repository targeting `main`. It
does not copy either checkout, create private mappings, or own runtime state.

## Hard boundaries

The mayor must not:

- implement source changes directly;
- create replacement agents, wrappers, relays, or services;
- use a tier name as a lifecycle or routing target;
- merge, force-push, or make a human publication decision;
- bypass the repository target (`v3` or `main`) or
  `metadata.merge_strategy=pr`;
- bypass the pull-request handoff or the official Gas City lifecycle.

The `d2b-governance` global fragment remains the source of the PR-only
publication rule. Human owners decide whether a pull request is merged.

## Composition

Reusable operating rhythm, routing, and coding rules live in
`packs/core-city/template-fragments`. The city-local prompt supplies only the
identity and d2b governance context. This keeps the mayor adapted to the
cookbook concept without copying unsupported provider families, foreign
workflow machinery, hourly sweeps, or runtime state.

## Operator checks

Inspect the native composition from `cities/d2b-gascity`:

```text
gc status
gc formula show build-basic
gc service list
gc service doctor
```

Use the human-only reset runbook in
[docs/operations.md](../docs/operations.md) for a clean cutover. The mayor
does not stop or unregister the old city, remove a bind mount, delete
runtime paths, re-import Discord, or choose credentials.
