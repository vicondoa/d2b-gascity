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
- The `gc`, `codex`, `gh`, `cloudflared`, and Codex Router binaries are
  supplied externally by the host or the separate
  `vicondoa/gascity.nix` distribution.
- The host supplies the user-owned supervisor configuration link, tunnel
  configuration, authorities, addresses, credentials, identifiers, and runtime
  state. Those values stay outside this repository.
- The host may publish the dashboard and Slack adapter through a free
  Cloudflare Tunnel. `cloudflared` uses outbound-only connections; the home
  firewall must not expose the dashboard or Slack adapter ports.
- Cloudflare Access protects the dashboard hostname and allowlists the
  operator identity. Slack uses a separate hostname/path without Access
  login, because Slack authenticates Events requests with its signing secret
  and workspace check instead.
- The host-managed Codex Router owns the Copilot Requests credential and the
  active account-visible model. The city does not store router URLs, model
  IDs, Copilot token variables, model transcripts, or token material.
- Slack Full is an imported source-only pack. Its `slack` `proxy_process`
  remains under native Gas City lifecycle; the city must not add a second
  Slack service or relay. The adapter is allowed only the Slack variables
  from the operator-owned mode-`0600` environment file.
- Slack Events ingress is host-owned and public. Slack signing verification
  and workspace checks must pass before an event is accepted. The proof is
  restricted to an operator-verified one-to-one DM, not a general
  authorization layer for rooms or multi-party conversations.
- Discord operation is gateway-only. App credentials and guild, channel, and
  user mappings are site-local; no public Interactions endpoint is published.
- The d2b publication identity is separate from Copilot Requests and Slack.
  It is scoped to `vicondoa/d2b` content and pull-request write only. It must
  not merge, force-push, or bypass rules.
- Dashboard authentication is provided by Cloudflare Access; no city-owned
  authentication proxy or local reverse proxy is required.

## Protected data

Never commit or attach:

- credentials, tokens, keys, cookies, password hashes, or credential paths;
- private host values, authorities, addresses, users, channels, or hashes;
- `.gc`, `.beads`, Dolt, databases, worktrees, sessions, sockets, logs,
  reports, service dumps, or copied runtime state;
- materialized Slack adapter or CLI binaries, build outputs, or imported pack
  runtime state;
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

Install the runtime, configure Codex Router and Cloudflare Tunnel through the
private `vicondoa/gascity.nix` repository or another compatible host source.
Keep
`${XDG_CONFIG_HOME:-$HOME/.config}/gc-slack-adapter/env` outside the
repository at mode `0600`, source it in the same shell as `gc start`, and
inherit only Slack adapter variables plus host routing values. Do not
duplicate host module details or embed host values here.
