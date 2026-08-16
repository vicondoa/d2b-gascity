# Contributing

This repository is private infrastructure for one Gas City city and one
`vicondoa/d2b` rig on `v3`. Contributions must keep the standalone boundary
clear and must not turn this repository into a second d2b product tree.

## Before changing files

Read:

1. [README.md](README.md) for product scope.
2. [AGENTS.md](AGENTS.md) for local agent and contributor rules.
3. [SECURITY.md](SECURITY.md) for trust boundaries and reporting.
4. [PROVENANCE.md](PROVENANCE.md) for the source snapshot and license
   boundary.
5. The applicable section of the plan under `docs/plans/`.

Use portable configuration in Git. Keep machine-local site bindings,
credentials, runtime state, reports, sockets, prompts, responses, and host
configuration outside the repository.

## Change discipline

- Make one logical change per commit.
- Do not edit the plan to mark work complete.
- Keep upstream code and notices attributable to their upstream source.
- Use ASCII hyphens only.
- Do not add Speckit, the d2b panel or signoff system, d2b wave or delivery
  sequencing, or d2b pinning-hardening workflows.
- A human owns merge, branch protection, and release decisions.

## Validation and evidence

Run the smallest relevant validation for the files changed. Before staging,
inspect `git status --short`, the staged file list, and the complete diff.
Check that no ignored or untracked runtime artifact is being included.

## Checks

The complete local gate is:

```bash
make check
```

The repository-local runner owns deterministic discovery, one contributor
runtime, the U3 pack cache, ingress namespace execution, scratch cleanup, and
process-leak detection. Use `make test-policy`, `make test-fixtures`,
`make test-ingress`, `make test-generated`, `make test-privacy`, or
`make check-nix` when narrowing a failure. See [docs/testing.md](docs/testing.md)
for the Nix-sandbox boundary and manual credential-backed acceptance.

Evidence must be redacted and limited to revisions, safe counts, timings,
and pass or fail results. Never commit live prompts or responses, tokens,
cookies, host-specific values, service environments, private databases,
private worktrees, or unredacted logs.

The repository-local privacy scanner is enforcing. Generic fixtures and
RFC1918/RFC5737 addresses are allowed only in tests; live credentials and
host-private values remain manual and must never enter evidence.

## Model lanes

Planning and review use Sol with `xhigh` effort and `long_context`. Coding
uses Luna with `max` effort. Luna may review only when Sol is explicitly
unsupported or unavailable.

## License

Local contributions are under the Apache License, Version 2.0 unless a file
states otherwise. Imported sources retain their own terms. See
[PROVENANCE.md](PROVENANCE.md).
