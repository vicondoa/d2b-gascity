# Operations

Gas City owns the city supervisor and its child lifecycle. U3 does not add a
second lifecycle owner, a dashboard service, a Discord sidecar, a publisher,
or a custom service declaration.

## Ordinary start

Bootstrap is not an ordinary-start hook. After a later deployment unit
installs the root service, the service starts the packaged supervisor with
`gc supervisor run`. It then performs delegated registration and
reconciliation using the machine-local site binding. Ordinary start must not
copy the prototype, rewrite portable files, or create a second user
supervisor.

The U3 operator check is explicit-path and read-only:

```text
python3 scripts/operator.py status \
  --state-root <state-root> \
  --city <city-root> \
  --rig <d2b-v3-checkout> \
  --gc <packaged-runtime>/bin/gc
```

`scripts/operator.py validate-request` only validates a small JSON status
request. It does not recreate old control-plane state or accept lifecycle
commands.

## Imports and source updates

`city/pack.toml` contains the Pack v2 root metadata and exact pinned imports
for the current Gas City core and Beads packs, Compound Engineering, and
Discord. The d2b rig composes the current gascity roles pack at rig scope.
`packs.lock` records the complete resolved closure.

Use the packaged runtime for validation:

```text
gc import check --city <city-root>
gc config show --city <city-root> --validate
gc lint <city-root>
gc doctor --city <city-root>
```

Upstream warnings from a stopped city, unavailable providers, or absent
supervisor are diagnostic context, not permission to weaken the portable
contract. Provider-specific readiness and local patches remain placeholders
until their owning units define them.

The resolved model-backed role graph is classified in
`city/role-provider-matrix.json`. The matrix is generated from the pinned
Pack v2 imports and every classified agent is patched to ACP with one of the
portable planning, review, or coding providers. Control and maintenance
agents remain on their upstream subprocess defaults.

Worktree creation is intentionally anchored to `origin/v3`. The core formulas
receive `base_branch = "v3"` through the d2b rig formula variables, and the
single higher-precedence Gas City worktree asset is recorded in
`city/worktree-producer-inventory.json`. The local asset cites the upstream
path and commit and replaces only remote-default branch discovery.
The inventory also records the exact current d2b `origin/v3` proof revision,
`db036097d05ede39009b912805a48f6ef8a74751`, in the local fake-repository
fixture. That fixture models only the `main` remote default, the `v3` branch,
and its revision marker; it does not copy d2b source or repository process
artifacts.

Discord operation is gateway-only in this city. The repository configures no
external publication edge, so the imported `discord-interactions` and
`discord-admin` processes may remain behind the supervisor without being
externally reachable. Do not patch those upstream service definitions or add a
Discord daemon.

Use the stopped helper with a root- or systemd-owned credential file:

```text
d2b-gascity-discord-import \
  --gc <runtime>/bin/gc \
  --state-root <state-root> \
  --city <city-root> \
  --token-file <credential-file> \
  --application-id <application-id> \
  --public-key <64-hex-public-key> \
  --guild-id <guild-id> \
  --channel-id <channel-id> \
  --operator-role-id <operator-role-id> \
  --operator-user-id <user-id>=<qualified-session>
```

The helper always supplies non-empty `--guild-allowlist`,
`--channel-allowlist`, and `--role-allowlist` values to the official
`gc discord import-app` command. The dedicated host-configured operator role
is the room boundary and must be assigned only to authorized operator users.
Direct operator DMs are explicit `gc discord bind-dm` bindings, one per
`--operator-user-id` mapping. Re-running the helper with the same application
ID imports a rotated token; restart the official gateway through the normal
Gas City operator path after rotation:

```text
gc service restart discord-gateway --city <city-root>
```

The helper passes the token through `/dev/stdin`, never argv or its output. It
requires an owner-only state root, rejects unsafe credential files, paths, IDs,
and session names before invoking `gc`, and does not echo child diagnostics.
Public Interactions publication and `sync-commands` are not invoked.
Pack-native behavior includes application and public-key validation, role,
guild, and channel policy, signed-interaction timestamp rejection at the
pack's retention window, duplicate interaction receipts, bot/self filtering
in the gateway, and two retries for Discord API rate-limit responses. The
pack does not provide a configurable inbound rate limiter or a direct room
user allowlist; the host role plus explicit DM bindings are the supported
substitute.

## Machine-local state

The repository contains no rig path, `.gc/site.toml`, cities registry, Beads
metadata, Dolt database, credential, host unit, or service state. The
explicit state root and city path supplied to bootstrap are deployment
inputs. Keep them outside the portable source and protect them with the
host's normal ownership and backup policy.
