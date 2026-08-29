# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows semantic versioning where releases are published.

## [Unreleased]

### Changed

- Moved the only active city root to `cities/d2b-gascity` and documented the
  repository boundary that excludes a local d2b checkout or bind mount.
- Documented native in-place initialization with
  `gc init --file city.toml --preserve-existing --no-start .` from the nested
  city and external rig binding through `gc rig add`.
- Documented exactly four model tiers: `deep-thinker` with
  `gpt-5.6-sol` medium and `long_context`, `reviewer` with `grok-4.6` high
  and `long_context`, `solid-worker` with `gpt-5.6-luna` max and
  `long_context`, and `fast-worker` with `gpt-5.6-luna` medium and
  `default`.
- Kept stock `builtin:codex` as an explicit alternate provider and retained
  the adapted city-local mayor on the official `gc.mayor` skill. The mayor
  never implements source changes or merges.
- Added a human-only clean reset runbook covering private preflight
  inventory, old root-city stop and unregister, bind-mount-safe unmount,
  preservation of the external checkout's product-local `.beads/`,
  `.gitignore`, and hooks, confirmed runtime cleanup, nested initialization,
  external rig binding, and Discord re-import.
- Documented least-privilege Discord permissions, stdin token import,
  allowlists, service exposure boundaries, and separation of Copilot
  Requests, d2b publication, and Discord credentials.
- Recorded MIT provenance for adapted concepts and text from
  `thinkjones/gascity-cookbook`. Recorded that `rencire/gascity-flake` has no
  license and supplied no copied content.
- Composed the official Pack v2 core, Beads, Gas City pack, and Discord
  imports, pinned to the researched upstream revisions.
- Added the official Gas City pack formulas, `gc.mayor` skill, rig roles,
  global fragments, and daemon reliability settings.
- Added the official Discord interactions, tenant admin, private gateway,
  chat bindings, launcher, workflow, and publication capabilities.
- Added the narrow local `mol-d2b-discord-fix-issue` formula extension for
  first-run `origin/v3` setup and fail-closed recorded-branch resume.
- Updated d2b governance to document PR-only publication, refusal of direct
  merges, and the human-owned merge boundary.
- Clarified that only `discord-interactions` is public; `discord-admin`
  stays tenant/access-policy protected and `discord-gateway` stays private.
- Removed the retired local chat fragment, workflow overrides, and redundant
  named worker configuration.
- Made native per-user Gas City commands the documented initialization,
  lifecycle, service diagnosis, rig binding, and stop path.
- Reduced validation to focused portable-city checks with optional native
  smoke coverage and redacted live acceptance boundaries.
- Kept host installation, optional binaries, proxy configuration, credentials,
  runtime state, and private evidence outside the city source.

### Security

- Reiterated that native lifecycle, runtime state, host paths, mounts, and
  credentials remain outside portable source.
- Reiterated that publication persists `metadata.target=v3` and
  `metadata.merge_strategy=pr`, refuses direct merges, and never merges or
  force-pushes.
