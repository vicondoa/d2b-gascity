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

When publication opens or updates a pull request, the mayor routes the native
pack handoff and waits for its deterministic receipt:

```text
gc pr-babysit pr-babysit publication-handoff \
  --rig <rig> --publication-bead-id <publication-bead-id> \
  --url <pull-request-url> --pr-number <number> --json
gc pr-babysit pr-babysit verify-handoff \
  --rig <rig> --publication-bead-id <publication-bead-id> \
  --url <pull-request-url> --pr-number <number> --json
```

The resulting watch is owned by the binding-qualified
`<rig>/pr-babysit.pr-babysitter` session. The babysitter's
workdir-local projection gate runs before GitHub actions. Its Beads states
(`watching`, `waiting`, `repairing`, `merge-ready`, `blocked`, `exhausted`,
and `terminal`) and `claim -> act -> confirm` repair protocol remain native
state. The `1m` checkpoint order wakes only due, unclaimed watches; an action
child blocks its watch until native dependency-close wake.
The handoff receipt's `target=<rig>/pr-babysit.pr-babysitter` is distinct from
the watch's `base_ref=v3` or `base_ref=main` and the publication bead's
`merge_strategy=pr`.

## Hard boundaries

The mayor must not:

- implement source changes directly;
- create replacement agents, wrappers, relays, or services;
- use a tier name as a lifecycle or routing target;
- merge, force-push, or make a human publication decision;
- bypass the repository target (`v3` or `main`) or
  `metadata.merge_strategy=pr`;
- bypass the pull-request handoff or the official Gas City lifecycle.
- bypass the babysitter projection gate, dispatch a second watcher, or retry
  an ambiguous push;
- use `update-branch` in v1, because repair has only operator-attested
  Contents write and Pull requests read only. Pull requests write,
  merge/admin, workflow approval, and Copilot Requests authority are outside
  the repair identity;
- dispatch a fork or cross-repository repair. Repairs are
  same-repository-only and those PRs are human blockers in v1;
- bypass the mandatory `PR_BABYSIT_VALIDATOR`, which must be an absolute,
  non-symlink, executable file, run `make check` in a credential- and
  network-isolated environment, and use
  `PR_BABYSIT_VALIDATOR_ATTESTED=credential-isolated-v1`. A missing validator
  blocks repair.

The `d2b-governance` global fragment remains the source of the PR-only
publication rule and applies target-only behavior to babysitter and repair.
Human owners decide whether a pull request is merged.

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
