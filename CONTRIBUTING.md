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
5. [docs/operations.md](docs/operations.md) and
   [docs/testing.md](docs/testing.md).
6. The applicable plan section under `docs/plans/`.

Do not edit the plan to record progress. Do not touch the separate
`vicondoa/gascity.nix` repository from this checkout.

## Change discipline

- Make one logical change per commit.
- Keep merges, branch protection, and release decisions human-owned.
- Use ASCII hyphens only.
- Preserve upstream licenses and notices.
- Keep portable values in Git and site bindings, credentials, runtime state,
  logs, prompts, responses, and host configuration outside the repository.

## Validation and evidence

Run the smallest relevant check:

```text
python3 tests/test_city.py
make check
GC_BIN=/path/to/gc python3 tests/test_city.py
```

The `GC_BIN` command is optional and performs the native initialization and
rig-binding smoke when the pinned executable and its dependencies are
available. CI downloads and verifies the exact upstream archive pins before
running the focused check. Authenticated ingress and credentialed
Compound Engineering to a pull request are live, redacted smokes, not test
code or committed reports.

Before staging, inspect `git status --short`, the staged file list, and the
complete diff. Remove any private values or runtime artifacts.

## Model lanes

Planning and primary review use Grok `grok-4.6` with `high` effort and
`long_context`. Coding uses Luna with `max` effort. Luna may review only when
Grok is explicitly unsupported or unavailable.

## License

Local contributions are under the Apache License, Version 2.0 unless a file
states otherwise. Imported sources retain their own terms. See
[PROVENANCE.md](PROVENANCE.md).
