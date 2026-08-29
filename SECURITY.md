# Security

## Repository status

This is private infrastructure. Do not disclose repository contents,
deployment details, credentials, or security reports publicly. Report a
suspected vulnerability through the repository's access-controlled
maintainer or security channel. If that route is unavailable, ask an
authorized owner for a private reporting route.

## Trust boundaries

- Native Gas City owns the city, imported services, retry, stop, and
  persistent per-user lifecycle.
- The `gc`, `copilot`, optional `codex`, `gh`, and ingress binaries are
  supplied by the host or the separate `vicondoa/gascity.nix` distribution.
- The host supplies user-owned supervisor configuration, authorities,
  addresses, credentials, identifiers, and runtime state. Those values stay
  outside this repository.
- Any public ingress is host-owned and outbound-only. Keep home-router
  inbound ports closed. Protect the dashboard with the host's access policy.
- The Discord pack owns three imported services under `.gc/services/discord`:
  only public `discord-interactions`, tenant/access-policy protected
  `discord-admin`, and private `discord-gateway`. The city authors no
  Discord service, relay, wrapper, or replacement lifecycle.
- The public Interactions endpoint is signed by Discord and uses
  `/v0/discord/interactions`. The tenant admin surface reports setup and
  status without exposing token values and must remain behind the tenant
  access policy. The gateway receives private inbound DM and guild traffic and
  must not be exposed publicly. The official Discord pack owns all three
  services.
- Discord app imports enforce application identity and configured
  guild/channel/role allowlists. Token material is host-owned, mode `0600`,
  and may be streamed through `/dev/stdin`; it must never be stored here.
- Launcher and ambient room features require Discord's Message Content
  Intent. Without that privileged intent, unmentioned guild content is not a
  reliable input.
- Normal agent output is private until an explicit Discord publish or
  reply-current action. Bot-authored messages are ignored on inbound.
- The city defaults to host-supplied Copilot CLI and the Copilot Requests
  credential. Planning and primary review use Grok `grok-4.6` with `high`
  effort and `long_context`. Coding uses Luna with `max` effort. Stock Codex
  is an alternate provider. d2b publication credentials and Discord app
  credentials are separate. Never set `GH_TOKEN` from a Copilot token.
- The d2b formula gate stamps and re-reads `target=v3` and
  `merge_strategy=pr` before inherited submission. Refinery must refuse direct
  merges and never merge or force-push. Host branch protection for `v3` is
  defense-in-depth: it must require pull requests and apply to administrators.
  This repository does not claim that the current host is already configured
  that way. Merge decisions remain human-owned.

## Capability boundaries

The official Discord pack supports signed Interactions, the guild-scoped
`/gc fix` command and modal submission, plain message bodies, exact chat
bindings, managed launcher threads, and explicit workflow publication. It
does not provide general buttons, select menus, context menus, attachment
ingestion/publication, embeds, reactions, presence controls, or arbitrary
slash commands. Do not add a city-owned implementation for those gaps.

## Protected data

Never commit or attach:

- credentials, tokens, keys, cookies, password hashes, or credential paths;
- private host values, authorities, addresses, users, channels, roles, or
  hashes;
- `.gc`, `.beads`, Dolt databases, worktrees, sessions, caches, sockets,
  reports, logs, service dumps, or copied runtime state;
- materialized imported pack binaries or runtime state;
- live prompts, model responses, private pull-request payloads, or
  unredacted logs.

Generic placeholders and `127.0.0.1` in topology tests are acceptable.
File permissions and `.gitignore` do not replace staged-file and diff review.

## Reporting guidance

Use a redacted reproduction with the affected revision, safe counts or
timings, and pass or fail results. Remove credentials, private authorities,
host paths, identifiers, prompts, responses, and payloads before sharing.
Do not copy host state into the portable city.

## Installation boundary

Install the runtime, configure Copilot CLI, optionally configure Codex, and
configure any host ingress through the private `vicondoa/gascity.nix`
repository or another compatible host source. Keep supervisor configuration,
Discord app credentials, and publication credentials outside this
repository. Do not duplicate host module details or embed host values here.
