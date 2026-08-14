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
Discord. The city defaults compose the current gascity roles pack at rig
scope. `packs.lock` records the complete resolved closure.

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

## Machine-local state

The repository contains no rig path, `.gc/site.toml`, cities registry, Beads
metadata, Dolt database, credential, host unit, or service state. The
explicit state root and city path supplied to bootstrap are deployment
inputs. Keep them outside the portable source and protect them with the
host's normal ownership and backup policy.
