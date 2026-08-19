# Security

## Repository status

This is private infrastructure. Do not disclose repository contents,
deployment details, credentials, or security reports publicly. Report a
suspected vulnerability through the repository's access-controlled
maintainer or security channel. If that route is unavailable, ask an
authorized owner for a private reporting route.

## Trust boundaries

- Native Gas City owns the city, service, retry, stop, and persistent
  per-user lifecycle.
- The `gc` binary, optional Copilot and `gh` binaries, and optional proxy
  adapters are supplied externally by the host or the separate
  `vicondoa/gascity.nix` distribution.
- The host supplies the user-owned supervisor configuration link, proxy
  configuration, authorities, addresses, credentials, identifiers, and
  runtime state. Those values stay outside this repository.
- Proxy services are host-owned optional integrations. They must fail closed
  when authentication or their required binary is absent, and their
  degradation must not prevent the core city from remaining usable.
- Builtin Copilot receives its site-local token through host configuration.
  The city does not store model transcripts or token material.
- Discord operation is gateway-only. App credentials and guild, channel, and
  user mappings are site-local; no public Interactions endpoint is published.
- The official publication identity is scoped to `vicondoa/d2b` content and
  pull-request write only. It must not merge, force-push, or bypass rules.

## Protected data

Never commit or attach:

- credentials, tokens, keys, cookies, password hashes, or credential paths;
- private host values, authorities, addresses, users, channels, or hashes;
- `.gc`, `.beads`, Dolt, databases, worktrees, sessions, sockets, logs,
  reports, service dumps, or copied runtime state;
- live prompts, model responses, private pull-request payloads, or
  unredacted logs.

Generic placeholders and `127.0.0.1` in generic topology tests are
acceptable. File permissions and `.gitignore` do not replace staged-file and
diff review.

## Reporting guidance

Use a redacted reproduction with the affected revision, safe counts or
timings, and pass or fail results. Remove credentials, private authorities,
host paths, identifiers, prompts, responses, and payloads before sharing.
Do not copy host state into the portable city.

## Installation boundary

Install the runtime and configure optional proxy binaries through the private
`vicondoa/gascity.nix` repository or another compatible host source. Follow
that repository's documentation for host configuration; do not duplicate
host module details or embed host values here.
