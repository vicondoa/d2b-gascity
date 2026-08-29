# Contributing

This private repository is the portable source for one Gas City city and one
external `vicondoa/d2b` rig on branch `v3`. The only active city root is
`cities/d2b-gascity`. Keep the repository a city source, not a second d2b
product tree or a host deployment repository.

## Before changing files

Read:

1. [README.md](README.md) for scope and the nested layout.
2. [AGENTS.md](AGENTS.md) for local rules.
3. [SECURITY.md](SECURITY.md) for trust boundaries and reset hazards.
4. [PROVENANCE.md](PROVENANCE.md) for source and license boundaries.
5. [docs/operations.md](docs/operations.md), [docs/testing.md](docs/testing.md),
   and the applicable design and recipe.
6. The applicable plan section under `docs/plans/`.

Do not edit the plan to record progress. Do not touch the separate
`vicondoa/gascity.nix` repository from this checkout. Do not add a
repository-local d2b checkout or bind mount. The external checkout is bound
only with native `gc rig add`, and its path remains live `.gc/site.toml`
state.

## Change discipline

- Make one logical change per commit.
- Keep merges, branch protection, and release decisions human-owned.
- Keep the four tier aliases exact:
  `deep-thinker` (`gpt-5.6-sol`, medium, `long_context`),
  `reviewer` (`grok-4.6`, high, `long_context`),
  `solid-worker` (`gpt-5.6-luna`, max, `long_context`), and
  `fast-worker` (`gpt-5.6-luna`, medium, `default`).
- Keep stock `builtin:codex` as an explicit alternate provider only. Do not
  add a custom Copilot or Codex adapter, alternate transport, relay, or
  city-owned service.
- Use `mol-d2b-discord-fix-issue.toml` only as the thin official Discord
  workspace-setup extension. Resume may recreate a missing worktree only from
  its recorded branch and must fail closed for missing branches or guessed
  legacy provenance.
- Use the official Gas City formulas (`build-basic`, `implement`,
  `github-issue-fix`, `publish`) for d2b work. Publication must persist and
  re-read `target=v3` and `merge_strategy=pr`.
- Publication must refuse direct merges and never merge or force-push. Host
  branch protection for `v3` is defense-in-depth and must require pull
  requests and apply to administrators; this repository does not claim the
  current host is already configured that way. Merge decisions remain
  human-owned.
- Preserve upstream licenses and notices. Use ASCII hyphens only.
- Keep portable source in Git. Keep credentials, runtime state, logs,
  prompts, responses, mappings, bindings, and host configuration outside the
  repository.
- Use native Gas City lifecycle and imported pack services; do not add a
  wrapper, relay, duplicate service, or publication helper.

## Mayor and operator boundaries

The city-local mayor uses the official `gc.mayor` skill and never implements
source changes or merges. It creates beads, dispatches official roles and
formulas, monitors results, and waits when idle. Human operators own the
clean reset, Discord re-import, publication, and final cutover.

The reset runbook is intentionally human-only. Inventory active work and
Discord apps, allowlists, channel and rig maps, room and DM bindings, and
launchers privately. Stop and unregister the old root city, confirm and
unmount the d2b bind mount without recursive deletion, preserve the external
checkout's product-local `.beads/`, `.gitignore`, and hooks, and remove only
confirmed old root-city runtime paths. Set host-local `GC_CITY_PATH`, run
`gc init --file city.toml --preserve-existing --no-start .` from
`cities/d2b-gascity`, bind the verified source checkout with `gc rig add`,
and re-import Discord with stdin token input, least-privilege permissions,
allowlists, and the documented service exposure boundaries.

## Validation and evidence

Run the smallest relevant check:

```text
python3 tests/test_city.py
make check
GC_BIN=/path/to/gc python3 tests/test_city.py
```

The `GC_BIN` command is optional native initialization and rig-binding smoke
coverage. Authenticated Discord ingress, Copilot CLI, optional Codex, and
credentialed publication are live, redacted smokes, not test code or
committed reports. Keep Copilot Requests, d2b publication credentials, and
Discord app credentials separate; never couple `GH_TOKEN` to a Copilot token.

Before staging, inspect `git status --short`, the staged file list, and the
complete diff. Remove private values, live payloads, and runtime artifacts.

## License

Local contributions are under the Apache License, Version 2.0 unless a file
states otherwise. Imported sources retain their own terms. Adapted
thinkjones/gascity-cookbook concepts and text are MIT-derived and documented
in [PROVENANCE.md](PROVENANCE.md). The unlicensed
rencire/gascity-flake supplied no copied content.
