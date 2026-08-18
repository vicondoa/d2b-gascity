# d2b-gascity

Private Gas City infrastructure for one city and one `vicondoa/d2b` rig on
branch `v3`.

## Scope

This repository is the standalone owner for the Gas City contributor
deployment. It will contain the portable city and Pack v2 configuration,
runtime packaging, NixOS deployment module, operator tooling, tests, and
deployment documentation needed by that one rig.

The repository is infrastructure, not a second d2b product repository. It
does not contain d2b product code, a second city, or a second rig. The target
rig is fixed to:

- repository: `vicondoa/d2b`
- base branch: `v3`

The standalone repository starts from a clean source snapshot. It does not
carry the full d2b Git history or prototype runtime state. See
[PROVENANCE.md](PROVENANCE.md) for the extraction boundary and source
licenses.

## State and privacy

Portable files belong in Git. Machine-local site bindings, credentials,
runtime state, reports, sockets, host configuration, live prompts and
responses, and private deployment values do not. They must be supplied by
the host through supported configuration or transient projection. The
literal `127.0.0.1` is allowed in generic topology documentation and tests;
host-specific authorities, addresses, paths, and identifiers are not.

The ignore rules are a convenience, not a security boundary. Review the
staged file list and diff before every commit.

## Contribution rules

Read [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md),
[SECURITY.md](SECURITY.md), and [PROVENANCE.md](PROVENANCE.md) before
changing the repository. In particular:

- Keep each commit to one logical change.
- Merges are human-owned.
- Use ASCII hyphens in source, documentation, configuration, and messages.
- Planning and primary review use Grok `grok-4.6` with `high` effort and
  `long_context`.
- Coding uses Luna with `max` effort.
- Review falls back to Luna only when Grok is explicitly unsupported or
  unavailable.
- Do not introduce Speckit, the d2b panel or signoff system, d2b wave or
  delivery sequencing, or d2b pinning-hardening workflows here.

## Validation

Run `make check` for the complete repository-local check graph. It is
credential-free and does not use a d2b test harness, panel, Speckit, or Rust
toolchain. Focused targets and the manual credential boundary are documented
in [docs/testing.md](docs/testing.md). Nix sandbox checks stay limited to
deterministic repository policy; real ACP feasibility and live host acceptance
are explicit manual commands only.

## License

Local repository content is provided under the Apache License, Version 2.0.
Third-party sources keep their own licenses and notices. See
[LICENSE](LICENSE) and [PROVENANCE.md](PROVENANCE.md).
