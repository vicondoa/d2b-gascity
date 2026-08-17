# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows semantic versioning where releases are published.

## [Unreleased]

### Added

- Established standalone governance for one private Gas City city and one
  `vicondoa/d2b` rig on `v3`.
- Recorded the clean-snapshot extraction boundary, source commit, and
  upstream license provenance.
- Added contribution, security, and privacy rules.
- Added ignore rules for machine-local state, credentials, reports, sockets,
  host overrides, and build outputs.
- Added the pinned Pack v2 role composition, ACP provider matrix, and
  origin/v3 worktree provenance checks; added the stopped official Discord
  import and DM-binding helper with role-based room boundary documentation.
- Pinned the worktree fixture to the current d2b `origin/v3` revision without
  importing d2b process or repository artifacts.
- Added a bounded Beads-bound publication helper for d2b `v3`.
- Added a deterministic trusted publication subprocess with continuation-aware
  claims, source-anchor binding, and safe publish artifacts.
- Added repository-local Make, Python, generated-inventory, privacy, static
  policy, Nix, and private CI checks without the d2b test harness or Rust.
- Hardened publication with dedicated systemd-projected credentials, HTTPS-only
  remotes, disabled hooks and tag following, and scrubbed GitHub child
  environments.
- Hardened publication transport with trusted bare Git, immutable source
  heads, ancestry override rejection, exact GitHub list filters, and
  retryable post-publication Beads persistence.
- Added best-effort city cleanup after failed bootstrap setup while preserving
  the original failure and enforcing cleanup after successful initialization.
- Added the fixed-loopback, split-host TinyAuth and Nginx contract for the
  embedded supervisor dashboard, with an exact HTTPS/OpenResty fixture,
  CookieJar session coverage, source admission and Origin/Referer guards,
  route/grant negatives, restart/SSE checks, and a static accessibility
  heuristic.
- Added a credential-free separate-root rollback fixture and operator
  contract covering old-new-old-new rehearsal, prototype integrity,
  retained closures, offline rollback, and the host receipt gate for U12.
- Added a stateless ACP identity deployment shim that seeds upstream-compatible
  session metadata under the service's private `TMPDIR` before slow Copilot
  handshakes without patching Gas City.
- Added a native systemd-socket-proxyd compatibility route for upstream #5262,
  forwarding the standalone CLI API endpoint to the supervisor without an
  upstream patch or a second lifecycle owner.
- Added on-demand GitHub App installation-token minting for publication with
  strict app-key/config projections, least-privilege permissions, bounded
  response validation, and no token persistence.

### Changed

- Start the city tmux server from `d2b-gascity.service` with `TMUX_TMPDIR`
  under `/run/d2b-gascity` so ACP sessions can start after a supervisor
  restart without leaving PrivateTmp.
- Drop the git-origin Beads federation remote after rig initialization so the
  local city does not expect remotesapi or push issue data into `vicondoa/d2b`.
- Run CI checks and generated-inventory reproduction through the pinned Nix
  development shell, and invoke repository Python tests with the contributor
  runtime interpreter after that runtime is built.
- Fixed the Discord import helper to rely on the validated city cwd and avoid
  forwarding the global `--city` flag into Pack v2 scripts.
- Set the imported city-scoped `bd.dog` agent suspended by default so an idle
  rig does not launch background ACP model work; explicit resume retains the
  portable workspace provider fallback.
- Migrated planning and primary review to Grok `grok-4.6` with `long_context`
  and `high` effort, retained Luna coding and unsupported/unavailable-only
  review fallback, and supplied the machine-selected review provider as the
  portable workspace default.
- Accepted exact `0400` and `0440` modes for systemd-projected private
  credentials while retaining strict explicit credential-file checks.
- Hardened auth Origin matching, decoupled relay and TinyAuth stopping,
  isolated the ingress fixture's fixed supervisor port in an unprivileged
  network namespace, and tightened rotation, SSE restart, cookie-secret
  scanning, and cleanup proofs.
- Moved Gas City firewall programming onto the existing iptables-backed NixOS
  firewall service and atomically replace only `table inet d2b_gascity`.
- Kept the pinned Gas City source and package unpatched; the ACP shim is
  deployment-owned until upstream identity seeding supersedes it. Related
  orphan behavior is tracked by upstream #4714.
- Restricted the standalone API compatibility listener to loopback and uid
  41080, and documented removal once upstream identity-aware routing lands.
