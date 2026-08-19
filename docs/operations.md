# Operations

This repository is the portable city source. Native Gas City owns the
supervisor, city, imported service, retry, stop, and per-user state lifecycle.
There is no repository-specific wrapper.

## Install the runtime

Install the pinned `gc` runtime and any optional `copilot`, `gh`, TinyAuth,
Nginx, or proxy adapter binaries through the separate private
`vicondoa/gascity.nix` repository or another compatible host source. This
repository contains no Nix packaging. Follow the sibling repository's
documentation for host configuration and optional proxy setup.

The core distribution is inert: installation does not start a supervisor,
city, proxy, or custom service. Optional proxy binaries may be absent; the
city remains usable while those services report a degraded state.

## Initialize and start

From a checkout of this repository, initialize in place so authored root
files are preserved:

```text
gc init --file city.toml --preserve-existing --no-start .
```

The host supplies a rendered supervisor configuration. Before the first
start, create the user-owned link at the native `GC_HOME` location. Use the
path supplied by the host; do not copy the rendered file into this
repository:

```text
GC_HOME="${GC_HOME:-$HOME/.gc}"
ln -s /path/from-host/supervisor.toml "$GC_HOME/supervisor.toml"
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

If optional proxy adapters are not installed, the proxy services should be
visibly degraded while core city status remains usable. Do not add a
replacement process or wrapper.

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

The city uses builtin Copilot, the official Compound Engineering and roles
assets, and official publication. The two local workflow assets select
`origin/v3` for worktrees and `v3` for pull requests. A bounded native launch
uses `gc.run-operator` and the official `compound-build` formula:

```text
gc sling gc.run-operator <bead-id> --on compound-build \
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
