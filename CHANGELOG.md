# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows semantic versioning where releases are published.

## [Unreleased]

### Changed

- Refocused the repository as the root portable Gas City city for one
  `vicondoa/d2b` rig on branch `v3`.
- Composed the official Pack v2 core, Beads, Gas City pack, and Discord
  imports, pinned to the researched upstream revisions.
- Added the official Gas City pack formulas, `gc.mayor` skill, rig roles,
  global fragments, and daemon reliability settings.
- Added the official Discord interactions, tenant admin, private gateway,
  chat bindings, launcher, workflow, and publication capabilities.
- Added the narrow local `mol-d2b-discord-fix-issue` formula extension for
  first-run `origin/v3` setup and fail-closed recorded-branch resume.
- Updated d2b governance to document PR-only publication, refusal of
  direct merges, and the human-owned merge boundary.
- Clarified that only `discord-interactions` is public; `discord-admin` stays
  tenant/access-policy protected and `discord-gateway` stays private.
- Removed the retired local chat fragment, workflow overrides, and redundant
  named worker configuration.
- Made native per-user Gas City commands the documented initialization,
  lifecycle, service diagnosis, rig binding, and stop path.
- Reduced validation to focused portable-city checks with optional native
  smoke coverage and redacted live acceptance boundaries.
- Kept host installation, optional binaries, proxy configuration, credentials,
  runtime state, and private evidence outside the city source.
- Defaulted the city to Gas City's builtin Copilot CLI lanes for Grok
  planning/review and Luna coding, while keeping stock Codex available.
- Replaced the Gastown pack with the official Gas City pack at city scope
  and `gascity/roles` on the d2b rig. Coding uses the
  `implementation-worker` Luna patch. Removed the Gastown-only
  `mol-d2b-polecat-work` and `exp-d2b-pr-handoff` formulas.
- Moved workspace identity out of `city.toml` into live `.gc/site.toml`
  so Pack v2 no longer warns on every native command.
- Added a city-scoped always-on `mayor` named session that uses the
  official `gc.mayor` skill.
- Defaulted d2b formula vars to `open_pr=true`, `push=true`, and
  `drain_policy=separate` so builds publish a pull request and implement
  in worktrees.
