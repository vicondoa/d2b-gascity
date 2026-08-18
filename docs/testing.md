# Repository checks

`make check` is the pull-request check. It runs the portable Python
policy, generated-inventory, privacy, and static workflow tests. It
does not build the contributor runtime, seed a pack cache, or start a
Gas City supervisor. GitHub Actions runs `python3 tests/run.py check`
with a 5-minute timeout.

Live supervisor fixtures, ingress, rollback, and `nix flake check`
stay behind `make test-fixtures`, `make test-ingress`,
`make test-rollback`, and `make check-nix`. Those commands still
build one contributor runtime and seed one pack cache in a mode-0700
temporary root outside the repository.

CI substitutes stock `nginx` from the pinned nixpkgs. Go 1.26.6 comes
from `openserbia/go-flake`. `gc`, `bd`, and `dolt` come from the
official GitHub release tarballs (`gascity v1.4.1`, `beads v1.2.2`,
`dolt v2.1.7`), not from-source Go builds. The workflow also restores
`/nix` from GitHub Actions cache.

Focused commands are available for `make test-policy`, `make test-fixtures`,
`make test-rollback`, `make test-ingress`, `make test-generated`,
`make test-privacy`, `make test-workflow`, and `make check-nix`.
`make test-rollback` runs the credential-free separate-root old-new-old-new
fixture. `make test-vm` builds the named
`vmChecks.x86_64-linux.d2b-gascity` output and is intentionally outside the
default cross-system flake checks.
The fixture suite also starts native `systemd-socket-proxyd` with a local
credential-free HTTP backend and checks method/body and SSE forwarding.

The Nix checks cover deterministic generated drift, tracked-file privacy, and
static workflow policy. Bootstrap and ingress fixtures that need package
installation or a user/network namespace run through Make and CI rather than
inside a Nix sandbox. This is an explicit boundary, not a skipped check.
The privacy scanner also inspects staged Git index blobs and symlink targets,
so a safe working tree does not hide staged private content.

Real ACP feasibility, live providers, deployment acceptance, and host
rollback remain manual. The repository rollback fixture runs in `make check`,
but actual `nixos-rebuild` cutover, retained-closure rollback, and the
redacted host receipt remain manual U10 evidence. BuildBuddy is out of scope
for U9 and this rollback surface: no local acceleration or credential test is
introduced here; its separate integration and failure policy remain owned by
the later delivery boundary.

Generated inventory is reproduced with `make update-generated`. The workflow
`.github/workflows/update-generated.yml` runs that target through the same
pinned development shell, is manual-only, and emits a patch artifact before
failing deliberately so it never silently mutates the default branch.
