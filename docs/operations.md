# Operations

This repository is the portable city source. Native Gas City owns the
supervisor, city, imported service, retry, stop, and per-user state lifecycle.
There is no repository-specific wrapper.

## Install the runtime

Install the pinned `gc`, `codex`, `cloudflared`, and `gh` runtimes, plus any
optional integration binaries, through the separate private
`vicondoa/gascity.nix` repository or another compatible host source. This
repository contains no Nix packaging. Follow the sibling repository's
documentation for host configuration and tunnel setup. The city uses Gas
City's stock Codex provider; the host's Codex Router selects the active
Copilot model.

The core distribution is inert: installation does not start a supervisor,
city, tunnel, or custom service.

## Free Cloudflare ingress

The host may run `cloudflared` as a separate outbound-only ingress service.
The Cloudflare Tunnel token, Access policy, and public hostnames are
host-local and must not be placed in this repository or the Nix store.

Use one published application for the dashboard hostname and protect it with
the free Cloudflare Access identity policy for the operator. Use a separate
published application for the Slack hostname without Access login because
Slack cannot complete an Access authentication flow. The Slack adapter still
requires its signing-secret, timestamp, and workspace checks.

The intended local origins are:

- Dashboard: the native Gas City API on the host's loopback supervisor port.
- Slack: `http://127.0.0.1:8765`, with the adapter bound to loopback.

Keep all home-router inbound ports closed. The dashboard and API are served
directly by the native Gas City supervisor through the Cloudflare Tunnel.
Cloudflare Access protects the dashboard hostname; Slack uses its own signed
Events route without Access login. Configure the Slack hostname's published
application to match only `/slack/events`, followed by a catch-all
`http_status:404` rule. Do not publish the adapter's `/healthz`, OAuth, or
other paths in the steady-state route.

## Initialize and start

From a checkout of this repository, initialize in place so authored root
files are preserved:

```text
gc init --file city.toml --preserve-existing --no-start .
```

The host supplies a rendered supervisor configuration. Before the first
start, source the operator-owned Slack environment file in the same shell
that starts Gas City:

```text
SLACK_ENV="${XDG_CONFIG_HOME:-$HOME/.config}/gc-slack-adapter/env"
test -f "$SLACK_ENV"
chmod 600 "$SLACK_ENV"
. "$SLACK_ENV"
```

The file is host-local and must contain only the Slack adapter variables plus
the host values `GC_CITY_NAME=d2b-gascity`, `GC_CITY_PATH`, and the existing
supervisor value for `GC_API_BASE_URL`. Do not use the Slack pack's alternate
API default. Set `LISTEN_PUBLIC=127.0.0.1:8765` so the adapter remains
loopback-only. Keep Codex Router, Copilot Requests, and d2b pull-request
credentials out of this file.

Create the user-owned supervisor link at the native `GC_HOME` location. Use
the path supplied by the host; do not copy the rendered file into this
repository:

```text
GC_HOME="${GC_HOME:-$HOME/.gc}"
ln -s /path/from-host/supervisor.toml "$GC_HOME/supervisor.toml"
```

If `pack.toml` imports Slack Full, do not run `gc start` until the imported
pack is materialized and its source-only binaries are built. Set `GC_PACK_DIR`
to the materialized `slack-full` directory shown by the host's pack
materialization output, verify `manifest/app.json` exists, and build the
adapter and CLI there as described below. Then run:

```text
gc start
```

The first manual `gc start` may install and enable Gas City's native user
supervisor and linger. That persistence is native behavior. Subsequent login
or reboot recovery of a still-registered city is supported upstream; it is
not a second host-wide lifecycle.

## Bind the d2b rig

The root `city.toml` declares exactly one pathless rig named `d2b`, with
prefix `d2b` and default branch `v3`. Bind a checkout with native Gas City:

```text
gc rig add /path/to/d2b --name d2b --city .
gc status
```

The product checkout path is written to live `.gc/site.toml` only. Native
rig setup may add supported bookkeeping to the d2b checkout, but it does not
add a city, provider, pack, or service configuration there.

Use native service diagnosis and restart:

```text
gc service list
gc service doctor
gc service restart <service-name>
```

The city owns no dashboard authentication proxy or replacement wrapper.

## Codex Router and credential boundaries

Gas City launches the native `codex` command. Codex Router is a separate
operator-owned process that supplies the active Copilot model through Codex's
normal configuration path. Keep its Copilot Requests credential in the
router's protected provider state and choose the model from the live account
catalog. Do not put router URLs, model IDs, Copilot token variables, or
`GH_TOKEN=$COPILOT_GITHUB_TOKEN` in `city.toml`.

Use the operator's existing GitHub and git authorization for d2b branch and
pull-request publication. It is separate from the Copilot Requests
credential, and neither credential belongs in the Slack environment file or
the portable city. This credential separation is deliberate and must remain
visible in host setup reviews.

## Slack Full import

The root Pack v2 imports the pinned stock Slack Full Pack:

```text
source = "https://github.com/gastownhall/gascity-packs/tree/main/slack-full"
version = "sha:5d2a9d023edbb9ba24fdcff554e89fc3d7da72fe"
```

The imported pack owns its `slack` `proxy_process` service. In this city the
materialized import exposes its operator commands as `gc slack-full`; use that
binding rather than adding a city-owned Slack service, a second supervisor, or
a custom relay.

Slack Full carries source-only Go binaries. After the pack is materialized,
set `GC_PACK_DIR` to its materialized `slack-full` directory, verify
`manifest/app.json` exists, and build them using the upstream instructions:

```text
test -f "$GC_PACK_DIR/manifest/app.json"
(cd "$GC_PACK_DIR/adapter" && go build -o gc-slack-adapter)
(cd "$GC_PACK_DIR/cli" && go build -o gc-slack-cli .)
```

These binaries and any pack runtime state remain materialized or ignored.
Do not copy them into this repository or commit them.

After the city and Slack service are running, create the coordinator session
through the native session path, verify the operator's one-to-one DM, and
bind it with `gc slack-full bind-dm`. Attach the imported
`template-fragments/slack-v0.template.md` fragment to that coordinator.
Use the turn-bound `gc slack-full reply-current` path for replies. Do not use
room, launcher, mapping, file-transfer, or direct-adapter flows for the
clarification proof.

For workspace-bound request verification, prefer the stock Slack OAuth install
flow from the imported pack. It records the signing secret with the
workspace/app key in `.gc/slack/apps.json`; after the install, source the
generated `.gc/slack/install.env`, unset `SLACK_CLIENT_ID`,
`SLACK_CLIENT_SECRET`, `SLACK_REDIRECT_URI`, and `SLACK_APP_ID`, and restart
the adapter. The stock adapter uses `SLACK_APP_ID` to select its global
signing-secret branch, so leave it unset when using the workspace-bound
registry. Keep `SLACK_SIGNING_SECRET` out of the long-lived supervisor
environment when the registry contains the stamped secret. The OAuth callback
and its temporary public route are onboarding-only; disable them before the
steady-state Slack route is restricted to `/slack/events` and
`/slack/interactions`. The bootstrap registers the stock `/gc` slash command
against `/slack/interactions`; bind its channel or rig with the stock
`gc slack-full map-channel` or `gc slack-full map-rig` command before using
it. No custom slash-command dispatcher is added.

The bootstrap also invites the six identity bots to each private room. Verify
`gc slack-full peers` reports no membership or binding warnings before a room
mention or company-room proof.

## Discord gateway import

Use the official command with site-local credentials and mappings only:

```text
gc discord import-app \
  --application-id "$DISCORD_APPLICATION_ID" \
  --public-key "$DISCORD_PUBLIC_KEY" \
  --bot-token-file /dev/stdin \
  --guild-allowlist "$DISCORD_GUILD_ID" \
  --channel-allowlist "$DISCORD_CHANNEL_ID" \
  --role-allowlist "$DISCORD_ROLE_ID" \
  < "$DISCORD_TOKEN_FILE"
```

Keep the token file, application values, and guild, channel, role, or user
mappings outside the repository. This is gateway-only operation: do not
publish a public Interactions endpoint or add a public route. Restart the
official gateway service through native Gas City service commands after a
site-local credential rotation.

## Compound Engineering

The city uses native Codex through the host router, the official Compound
Engineering and roles assets, and official publication. The two local
workflow assets select `origin/v3` for worktrees and `v3` for pull requests.
A bounded native launch uses `d2b/roles.run-operator` and the official
`compound-build` formula:

```text
gc sling d2b/roles.run-operator <bead-id> --on compound-build \
  --var artifact_root=<site-local-artifact-root> \
  --var interaction_mode=autonomous \
  --var review_mode=agent \
  --var drain_policy=separate \
  --var push=true \
  --var open_pr=true
```

Use a small non-sensitive work item and a site-local artifact root. The
credential must be scoped to `vicondoa/d2b` content and pull-request writes
only. Stop without changing the remote default or adding a replacement
worker if the worktree or pull request is not for `vicondoa/d2b` and `v3`.
Never merge automatically. Do not store prompts, model responses, pull
request payloads, or live evidence in the repository.

## Stop

Stop and unregister the city with native Gas City:

```text
gc stop
```

Native stop closes the city and its managed services. Do not add a custom
shutdown hook or host lifecycle service.
