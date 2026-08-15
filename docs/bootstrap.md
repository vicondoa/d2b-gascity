# Standalone bootstrap

U3 bootstrap is a stopped, one-time operation. It materializes only the
portable files from `city/`, initializes the new city with the packaged
Gas City runtime, installs the pinned imports, and registers the `d2b` rig
while it is suspended.

The operator supplies every state path and the packaged runtime explicitly:

```text
python3 scripts/bootstrap.py init \
  --state-root <state-root> \
  --city <city-root> \
  --rig <d2b-v3-checkout> \
  --gc <packaged-runtime>/bin/gc
```

The `init` mode:

1. Refuses a symlink, partial, or non-empty city target.
2. Verifies that the packaged `gc init` exposes `--file`,
   `--preserve-existing`, and `--no-start`.
3. Copies `city.toml`, `pack.toml`, `packs.lock`, and the narrow local
   placeholder directories.
4. Runs `gc init --file ... --preserve-existing --no-start` and skips provider
   readiness until the provider work is available.
5. Installs the exact locked imports, clones or accepts a `v3` d2b checkout,
   and runs `gc rig add --start-suspended`.

If initialization, import installation, or rig setup fails after materializing
the city, bootstrap best-effort stops that city before returning the original
failure. The final stop on a successful init remains enforcing: a cleanup
failure is reported as the init failure.

It never calls `gc register`, starts a supervisor, installs a user unit, or
writes `.gc/site.toml` itself. Gas City creates `.gc/site.toml` during
`gc rig add`; that file binds the machine-local rig path and is never
committed. Root-owned deployment work will start the eventual system unit
in a later unit.

## Existing roots and registration

Repeating `init` is refused. Use the explicit registration mode only after
the root service has been started:

```text
python3 scripts/bootstrap.py register-existing \
  --state-root <state-root> \
  --city <city-root> \
  --rig <d2b-v3-checkout> \
  --gc <packaged-runtime>/bin/gc \
  --allow-start
```

Normal registration requires `GC_SUPERVISOR_SYSTEMD_UNIT` and
`GC_SUPERVISOR_SYSTEMD_SCOPE=system` in the delegated service environment.
`--fixture-supervisor` is reserved for isolated tests and does not claim
that a deployment service exists. U3 does not install or start that service.

## Checks and updates

`check` is read-only. It validates imports, resolved configuration, the
pathless city rig, the machine-local site binding, registration state, and
the absence of an undelegated user supervisor:

```text
python3 scripts/bootstrap.py check \
  --state-root <state-root> \
  --city <city-root> \
  --rig <d2b-v3-checkout> \
  --gc <packaged-runtime>/bin/gc
```

Portable updates require an explicit candidate source. The target must still
match the committed baseline exactly; local drift refuses the update before
any write. Only the portable files are atomically replaced. `.gc`, Beads,
Dolt, worktrees, sessions, and other runtime directories are preserved:

```text
python3 scripts/bootstrap.py portable-update \
  --state-root <state-root> \
  --city <city-root> \
  --rig <d2b-v3-checkout> \
  --gc <packaged-runtime>/bin/gc \
  --portable-source <new-portable-city>
```

Pack caches may be supplied explicitly for offline fixtures with
`--pack-cache`. A cache is machine-local and is not copied into the
repository.
