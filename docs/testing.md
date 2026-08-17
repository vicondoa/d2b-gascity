# Repository checks

`make check` is the private pull-request-equivalent check. It runs the local
Python policy and fixture graph, the credential-free ACP proof with the fake
Copilot, the exact ingress fixture in its network namespace, privacy and
generated-drift checks, and `nix flake check`. The runner builds one contributor
runtime per process, seeds one pack cache inside a mode-0700 OS temporary root
outside the repository, and removes that exact root before exit.
GitHub Actions invokes it as
`nix develop --no-write-lock-file --command make check` so CI uses the pinned
development-shell tools. After the runner builds the contributor runtime, it
also launches Python tests with that runtime's `python3` instead of the
invoking interpreter.

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
