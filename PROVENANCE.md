# Provenance

## Extraction source

The standalone repository begins from a clean source snapshot of
`vicondoa/d2b` at commit `9e0abd0c`. This records source authority only; it
does not import the d2b repository's full history, commit identities, tags,
worktrees, or runtime state.

The snapshot is an extraction of Gas City contributor infrastructure, not a
fork of the d2b product. Every candidate file remains subject to privacy,
license, and scope review before it is copied.

## Planned extraction allowlist

The planned allowlist is limited to these path classes and their standalone
counterparts:

### Source path classes

- `nix/gas-city-contributor/**` for portable city and pack assets, provider
  declarations, operator tooling, and Gas City-specific packaging inputs.
- `nixos-modules/gas-city-contributor/**` for the deployment module and its
  options.
- `pkgs/gascity/**` only for standalone package metadata or build inputs that
  remain necessary after the upstream package review.
- `tests/fixtures/gas-city/**`,
  `tests/host-integration/gas-city-contributor.nix`,
  `tests/unit/nix/cases/gas-city-contributor-*.nix`,
  `tests/unit/nix/helpers/gas-city-contributor.nix`, and
  `tests/unit/smoke/gas-city-package-smoke.nix` for reviewed standalone
  coverage.
- `docs/contributing/gas-city*.md`, `docs/adr/0053-*.md`,
  `docs/adr/0056-*.md`, and selected `docs/plans/**` references for
  standalone operations and decisions.
- `changelog.d/gas-city*.md` and `changelog.d/gascity*.md` as source notes,
  only after privacy and license review.

### Standalone path classes

- Root governance, licensing, provenance, packaging, and changelog files.
- `.github/workflows/**` for standalone checks and generated updates.
- `city/{city.toml,pack.toml,packs.lock}`, `city/agents/**`,
  `city/assets/**`, `city/formulas/**`, and `city/providers/**`.
- `docs/**` for standalone architecture, bootstrap, dashboard proxy,
  feasibility, operations, rollback, and plan documentation.
- `nix/packages/**` and `nix/source-manifest.nix`.
- `nixos-modules/**` for the standalone module and ingress relay.
- `operator/proxy/**`.
- `scripts/**` for bootstrap, provider, operator, publication, and source
  manifest tooling.
- `tests/acceptance/**`, `tests/fixtures/**`, `tests/host/**`, `tests/nix/**`,
  `tests/policy/**`, and `tests/smoke/**`.

These classes are an allowlist, not a request to copy every matching file.
Generic d2b product paths, d2b process or pinning machinery, the separate
`pkgs/gascity-dashboard/**` package, private credential fixtures, reports,
caches, sockets, host overrides, `.gc`, `.beads`, worktrees, and prototype
state are excluded. The dashboard remains an upstream supervisor concern.

## Upstream sources and licenses

Pins below are the first standalone set named by the plan. Versions and
revisions are recorded here so future package metadata can be checked against
one source record.

| Component | Source | Pin | License or terms |
| --- | --- | --- | --- |
| Gas City | [gastownhall/gascity](https://github.com/gastownhall/gascity) | `f6741d94861aa14f0253deffbe9efb1cb3a35d92` | MIT |
| Gas City packs, including Compound Engineering, Discord, and roles | [gastownhall/gascity-packs](https://github.com/gastownhall/gascity-packs) | `5d2a9d023edbb9ba24fdcff554e89fc3d7da72fe` | No repository-level SPDX or license metadata was exposed by the inspected upstream snapshot; retain upstream notices and verify each imported pack before redistribution |
| Beads | [gastownhall/beads](https://github.com/gastownhall/beads) | `bf97b73749ac3ef2fca2365b54537ac041ad4293` | MIT |
| Dolt | [dolthub/dolt](https://github.com/dolthub/dolt) | `2.1.7` | Apache-2.0 |
| Copilot CLI | [github/copilot-cli](https://github.com/github/copilot-cli) | `1.0.79` | GitHub Copilot CLI License, a proprietary license; no source modification or standalone redistribution |
| Copilot CLI packaging | [numtide/llm-agents.nix](https://github.com/numtide/llm-agents.nix) | `387989ee56d550d86d46d9458ad68a55b9e0ca3b` | MIT for the packaging repository; the packaged CLI keeps its own terms |
| TinyAuth | [tinyauthapp/tinyauth](https://github.com/tinyauthapp/tinyauth) | `5.1.3` | AGPL-3.0 |
| Nginx | [nginx/nginx](https://github.com/nginx/nginx) | `1.30.2` | BSD-2-Clause |

The repository [LICENSE](LICENSE) applies to local work. It does not
override an upstream license, the Copilot CLI terms, or notices that must
remain with imported material.

## Clean snapshot policy

Only reviewed source files are copied. The following are never copied from
the d2b checkout or from a deployment host:

- full Git history, identities, tags, or unrelated d2b product code;
- `.gc`, `.beads`, Dolt databases, worktrees, session state, caches, sockets,
  service dumps, reports, or logs;
- credentials, tokens, keys, cookies, password hashes, private paths,
  authorities, addresses, or host configuration;
- live prompts, model responses, private pull-request payloads, or other
  private deployment data.

State is bootstrapped into a new host-local root. Provenance records what may
be copied, not a license to copy private data.
