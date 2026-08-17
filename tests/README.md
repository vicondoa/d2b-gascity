# Test layout

`tests/run.py` is the repository-local runner. It discovers policy modules and
credential-free fixture modules in sorted path order, runs the fake-Copilot ACP
acceptance, builds the contributor runtime once per runner process, seeds a
per-run pack cache in a mode-0700 OS temporary root outside the repository,
supplies `GC_CONTRIBUTOR_ROOT` and `U3_PACK_CACHE`, runs Python tests with that
runtime's `python3` instead of the invoking interpreter, runs the ingress proof inside
its network namespace, removes the exact per-run root, and rejects owned
process leaks using the exact run identifier.

Use `make check` for the complete graph. The separate-root rollback fixture is
hermetic and runs there; the real ACP feasibility script and any live or host
acceptance require explicit manual commands and are not included in the
hermetic graph. Nix checks cover only sandbox-safe deterministic policy;
package-install and namespace fixtures run through Make and CI.
