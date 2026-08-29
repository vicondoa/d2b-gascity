# Contributing

This repository is private infrastructure for one portable Gas City city and
one `vicondoa/d2b` rig on `v3`. Keep the repository a city source, not a
second d2b product tree or a host deployment repository.

## Before changing files

Read:

1. [README.md](README.md) for scope and layout.
2. [AGENTS.md](AGENTS.md) for local rules.
3. [SECURITY.md](SECURITY.md) for trust boundaries.
4. [PROVENANCE.md](PROVENANCE.md) for source and license boundaries.
5. [docs/operations.md](docs/operations.md),
   [docs/testing.md](docs/testing.md), and the applicable design under
   [docs/designs/](docs/designs/).
6. The applicable plan section under `docs/plans/`.

Do not edit the plan to record progress. Do not touch the separate
`vicondoa/gascity.nix` repository from this checkout.

## Change discipline

- Make one logical change per commit.
- Keep merges, branch protection, and release decisions human-owned.
- Use `mol-d2b-discord-fix-issue.toml` only as the thin official Discord
  workspace-setup extension; resume may recreate a missing worktree only from
  its recorded branch, and must fail closed for missing branches or guessed
  legacy provenance.
- Use the official Gas City pack formulas (`build-basic`, `implement`,
  `github-issue-fix`, `publish`) for d2b work. Publication must persist and
  re-read `target=v3` and `merge_strategy=pr`.
- Publication must refuse direct merges and never merge or force-push. Host
  branch protection for `v3` is defense-in-depth and must require pull
  requests and apply to administrators; this repository does not claim the
  current host is already configured that way. Merge decisions remain
  human-owned.
- Use ASCII hyphens only.
- Preserve upstream licenses and notices.
- Keep portable values in Git and site bindings, credentials, runtime state,
  logs, prompts, responses, and host configuration outside the repository.
- Use native Gas City lifecycle and imported pack services; do not add a
  wrapper, relay, duplicate service, or publication helper.

## Validation and evidence

Run the smallest relevant check:

```text
python3 tests/test_city.py
make check
GC_BIN=/path/to/gc python3 tests/test_city.py
```

The `GC_BIN` command is optional and performs native initialization and
rig-binding smoke coverage when the pinned executable and its dependencies
are available. Authenticated Discord ingress, Copilot CLI, optional Codex,
and credentialed publication are live, redacted smokes, not test code or
committed reports.

Before staging, inspect `git status --short`, the staged file list, and the
complete diff. Remove private values and runtime artifacts.

## Model lanes

Planning and primary review use Grok `grok-4.6` with `high` effort and
`long_context`. Coding uses Luna with `max` effort. Luna may review only when
Grok is explicitly unsupported or unavailable.

## License

Local contributions are under the Apache License, Version 2.0 unless a file
states otherwise. Imported sources retain their own terms. See
[PROVENANCE.md](PROVENANCE.md).
