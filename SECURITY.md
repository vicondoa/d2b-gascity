# Security

## Repository status

This is a private infrastructure repository. Do not disclose its contents,
deployment details, or security reports publicly. Do not open a public issue
for a suspected vulnerability.

Report suspected vulnerabilities through the repository's access-controlled
maintainer or security channel. If that channel is unavailable, ask an
authorized repository owner for a private reporting route. Do not include
secrets or private deployment data in the report.

## Trust boundaries

- Git content is reviewed input to packaging, NixOS evaluation, operator
  tooling, and Gas City workflows. Treat imported packs and generated input
  as untrusted until checked.
- The Gas City supervisor is the lifecycle owner. Ingress authentication and
  reverse-proxy transport are separate infrastructure boundaries and must
  not become alternate lifecycle owners.
- Host-local configuration supplies authorities, addresses, credentials,
  identifiers, site bindings, and runtime state. These values stay outside
  Git and outside generated source artifacts.
- The d2b rig is the single intended target and uses `v3`. Publication must
  not gain authority to update, merge, force, or bypass protection on that
  branch.

## Local API compatibility boundary

The standalone API compatibility shim for upstream #5262 listens only on
`127.0.0.1:18372` and forwards bytes to the supervisor at
`127.0.0.1:8372` with native `systemd-socket-proxyd`. The nftables output rule
admits only uid 41080. Ordinary host users therefore cannot use this route to
bypass dashboard authentication. The shim is not public ingress and is not a
Gas City lifecycle owner: it never starts, stops, or reconciles the
supervisor. Do not widen its bind, UID gate, or role. Remove it when upstream
identity-aware routing is available.

## Protected data

Never commit or attach:

- credentials, tokens, keys, cookies, password hashes, or secret-bearing
  environment files;
- private host values, authorities, addresses, paths, user or channel IDs,
  or host configuration;
- `.gc`, `.beads`, Dolt, worktree, session, database, socket, cache, report,
  service dump, or prototype state;
- live prompts, model responses, private pull-request payloads, or
  unredacted logs.

Generic placeholders, planted non-sensitive prompts, and `127.0.0.1` in
generic topology tests are acceptable. File permissions and `.gitignore` do
not replace review of the staged file list and diff.

## Reporting guidance

Use a redacted reproduction with the affected revision, safe counts or
timings, and pass or fail results. Remove credentials, cookies, private
authorities, host paths, identifiers, prompts, responses, and log payloads
before sharing. Do not attempt to reproduce a report by copying prototype
state into the standalone root.

## Scope limits

This file defines the U1 repository boundary. Later units must prove
packaging, provider, ingress, publication, restart, and rollback controls
before those capabilities are treated as ready. A missing proof is a stop
condition, not permission to weaken a boundary.
