# d2b-gascity

`d2b-gascity` is the portable source for one Gas City city and one external
`vicondoa/d2b` rig on branch `v3`. It is city configuration, not a second d2b
product repository.

## Source and ownership boundary

The only active city root in this repository is
`cities/d2b-gascity`. Native Gas City owns the supervisor, city registration,
imported services, sessions, retries, and runtime state. The host owns
credentials, mounts, private paths, Discord mappings, and live configuration.
Runtime installation and optional host integration belong to the separately
owned private `vicondoa/gascity.nix` repository or another compatible host
source.

This repository must not contain a repository-local d2b checkout, bind mount,
submodule, copied product tree, or committed rig path. The external checkout
is connected only through native `gc rig add`; its path is live site state in
`.gc/site.toml`, never portable source.

## Layout

```text
.
|-- cities/
|   `-- d2b-gascity/
|       |-- city.toml
|       |-- model-tiers.toml
|       |-- pack.toml
|       |-- packs.lock
|       |-- agents/mayor/
|       |-- formulas/
|       `-- template-fragments/
|-- packs/
|   |-- core-city/
|   |   |-- model-tiers.base.toml
|   |   |-- commands/gen-model-tiers/
|   |   `-- template-fragments/
|   `-- pr-babysit/
|       |-- pack.toml
|       |-- agents/pr-babysitter/
|       |-- commands/pr-babysit/
|       |-- formulas/
|       |-- orders/
|       `-- skills/pr-babysit/
|-- docs/
|   |-- designs/
|   |-- operations.md
|   `-- testing.md
|-- recipes/
`-- tests/test_city.py
```

Only reviewed portable source is tracked. Native `.gc`, Beads and Dolt data,
sessions, worktrees, sockets, logs, credentials, prompts, responses, reports,
and host values remain outside tracked files.

## Model tiers

The reusable `packs/core-city` pack supplies tier data and generic mayor
fragments. The city projects exactly these four aliases:

| Tier | Stock provider | Model | Effort | Context |
| --- | --- | --- | --- | --- |
| `deep-thinker` | `builtin:copilot` | `gpt-5.6-sol` | `medium` | `long_context` |
| `reviewer` | `builtin:copilot` | `grok-4.6` | `high` | `long_context` |
| `solid-worker` | `builtin:copilot` | `gpt-5.6-luna` | `max` | `long_context` |
| `fast-worker` | `builtin:copilot` | `gpt-5.6-luna` | `medium` | `default` |

The twelve imported d2b roles use the deterministic map in
[recipes/model-tiers.md](recipes/model-tiers.md). The mayor, requirements
planner, design author, and task decomposer use `deep-thinker`; six review,
analysis, and triage roles use `reviewer`; `implementation-worker` uses
`solid-worker`; and `run-operator` plus `publisher` use `fast-worker`.

Stock `builtin:codex` remains available only as an explicit alternate provider.
It is not a tier, the workspace default, or a replacement for the stock
Copilot provider. No custom Copilot or Codex adapter, relay, or transport is
part of this city.

## Mayor

The adapted city-local mayor is one always-on native session with
`wake_mode = "fresh"`, `max_active_sessions = 1`, work directory
`.gc/agents/mayor`, and the `deep-thinker` tier. It uses the official
`gc.mayor` skill and official Gas City formulas and roles to plan work, create
beads, dispatch work, monitor results, and wait when idle.

The mayor does not implement source changes, create replacement agents, merge,
force-push, or bypass either repository's pull-request handoff. It routes
product work to `d2b`/`v3` and city source work to `city-source`/`main`.
Human operators own publication and merge decisions. See
[recipes/the-mayor.md](recipes/the-mayor.md).

## Initialize the nested city

Install the pinned `gc`, `copilot`, and `gh` runtimes, plus optional `codex`
and ingress tooling, from the separate host source. From the nested city
directory, initialize in place:

```text
cd cities/d2b-gascity
export GC_CITY_PATH="$(pwd)"  # host-local; do not commit this value
gc init --file city.toml --preserve-existing --no-start .
gc start
```

The command preserves authored Pack v2 files and does not copy repository
metadata or runtime state. Native Gas City owns lifecycle and per-user state;
do not add a wrapper, second supervisor, or city-starting service.

## Bind the product and city-source rigs

Create a separate `d2b-gascity` clone or worktree for automated source work;
never bind `city-source` to the live nested city checkout itself. Seed that
machine-local path in `.gc/site.toml`:

```toml
[[rig]]
name = "city-source"
path = "/path/to/separate/d2b-gascity-checkout"
```

Then provision both work surfaces through native Gas City:

```text
gc rig add <verified-d2b-checkout> --name d2b --city .
gc rig add <separate-d2b-gascity-checkout> \
  --name city-source --start-suspended --city .
gc status
```

Paths stay in live `.gc/site.toml` only. The external d2b checkout's
`.beads/`, `.gitignore`, and agent hooks are product-local rig bookkeeping and
must survive a clean reset.

## Discord and publication boundaries

The pinned official Discord pack owns `discord-interactions` (public signed
Interactions), `discord-admin` (tenant/access-policy protected), and
`discord-gateway` (private). Re-import apps with a token streamed through
`/dev/stdin`, guild, channel, and role allowlists, and least-privilege bot
permissions. Keep service exposure boundaries unchanged: only
`discord-interactions` is public, while admin remains protected and the
gateway remains private.

Keep Copilot Requests, d2b publication authorization, and Discord app
credentials separate. Never put credentials, token paths, identifiers,
allowlists, mappings, or live payloads in this repository. Publication must
persist and re-read `metadata.merge_strategy=pr` plus a persisted target
(`metadata.base_ref`, `metadata.target`, or `metadata.target_branch`) equal to
`v3` for d2b or `main` for city-source,
refuse direct merges, and never merge or force-push. The publication handoff
result has `target=<rig>/pr-babysit.pr-babysitter` (stored as
`handoff_target` in receipt metadata); that routing target is distinct from
the watch's `base_ref=v3` or `base_ref=main` and the publication bead's
`merge_strategy=pr`. Branch protection for `v3` is
defense-in-depth and must require pull requests and apply to administrators;
this repository does not claim that the current host is already configured
that way. The policy requires pull requests and must apply to administrators.

## PR babysitting and human-gate recovery

The enabled target-only capability is the rig-imported `pr-babysit` Pack v2
pack. It is imported once by each rig, not by the city or `packs/core-city`.
The binding-qualified native identities are
`d2b/pr-babysit.pr-babysitter` and
`city-source/pr-babysit.pr-babysitter`; each is a fresh, on-demand
`fast-worker` session with one active session and workdir
`.gc/agents/pr-babysitter`.

The session setup script projects the vendored skill into both
`.github/skills/pr-babysit` and `.agents/skills/pr-babysit` inside the
workdir. The mandatory projection gate checks the pinned commit and hashes
before any GitHub or repository action. It never writes the rig root or a
user-global skill directory. Inspect the native surfaces with:

```text
gc config show --json
gc config explain --rig d2b --agent pr-babysitter
gc skill list --agent d2b/pr-babysit.pr-babysitter --json
gc skill list --agent city-source/pr-babysit.pr-babysitter --json
```

Publication uses deterministic handoff and receipt commands. The handoff
verifies the repository, PR number or URL, base, head, and current head SHA;
it requires persisted `merge_strategy=pr` plus `base_ref`, `target`, or
`target_branch`, creates or reuses one durable watch record, routes it without
waking, writes matching verified identity receipts, and then nudges the
binding-qualified babysitter. A complete receipt contains
`handoff_verified=true`, the self watch ID, the binding-qualified target, and
the publication bead. `pending` or `route-failed` receipts cannot act, and a
repeated complete receipt does not wake again. Publication must verify that
receipt before it closes:

```text
gc pr-babysit pr-babysit publication-handoff \
  --rig d2b --publication-bead-id <publication-bead-id> \
  --url <pull-request-url> --pr-number <number> --json
gc pr-babysit pr-babysit verify-handoff \
  --rig d2b --publication-bead-id <publication-bead-id> \
  --url <pull-request-url> --pr-number <number> --json
gc pr-babysit pr-babysit show --watch-id <watch-id> --json
```

The durable Beads watch states are `watching`, `waiting`, `repairing`,
`merge-ready`, `blocked`, `exhausted`, and `terminal`. The action protocol is
`claim -> act -> confirm`; an action child is linked with
`bd dep <action-id> --blocks <watch-id>`, so native dependency-close wake
resumes the watch only after confirmation. The `pr-babysit-sweep` cooldown
order runs every `1m` through the canonical state-helper action:

```text
gc pr-babysit pr-babysit sweep --rig d2b --limit 32 --json
```

It lists due records, rechecks their routability, and routes
`<rig>/pr-babysit.pr-babysitter`; it is one short checkpoint, not a daemon or
in-session watcher.
Watch `claim_status` values written by state code are `none`, `claimed`,
`result-recorded`, `blocked`, and `exhausted`. Action records may also use
`ambiguous` and `stale`. `closed` is the Beads issue status written when a
confirmed action child closes, or when a watch reaches terminal; it is not a
`claim_status` value. Watch exhaustion is recorded on the watch. Only a
confirmed passed result closes the action child. Waiting watches may become
`merge-ready` or `blocked`, but must first become `watching` before a repair
claim.

Each checkpoint takes one fresh snapshot, then handles terminal state, head
reconciliation, review feedback, current-head CI, exact branch currency, and
one state write in that order. `mol-pr-babysit-repair` is a bounded Formula v2
with prepare, repair, review, validate-and-report, and close-action steps.
It runs `make check` before a normal push to the existing PR head and records
an independently recorded reviewer verdict and candidate SHA before pushing.
CI repairs get three attempts per head and fingerprint;
review repairs get two attempts. The active budget is eight active hours and
the hard backstop is a three-day backstop.

The first version does not use `update-branch`: the repair identity is
operator-attested with Contents write and Pull requests read only, and the
agent cannot introspect fine-grained permissions. `BEHIND`, dirty, conflicting,
unknown capability, stale-head, or ambiguous push evidence is a human blocker;
an ambiguous push records `ambiguous-outcome` and is never retried. `MERGED`
and `CLOSED` are absorbing `terminal` outcomes. An open `blocked`,
`exhausted`, or `merge-ready` watch may be explicitly rearmed with
`rearm=true`; a terminal watch cannot be rearmed.

Repairs are same-repository-only: `head_repository` must equal the verified
`owner/repository`. Fork or cross-repository PRs are human blockers in v1;
they receive no autonomous repair. Before any repair, the operator must
provide `PR_BABYSIT_VALIDATOR` as an absolute, non-symlink, executable file and set
`PR_BABYSIT_VALIDATOR_ATTESTED=credential-isolated-v1`. It must run
`make check` in a credential- and network-isolated environment. A missing
validator blocks repair, as do an invalid or failed validator. There is no
direct-make fallback.

The reviewer never resolves GitHub threads. After a confirmed review repair,
the babysitter records `handled` or `ignored` feedback disposition locally
with the current snapshot content identity; changed content reopens the item.

The non-network credential check is
`gc pr-babysit pr-babysit check-credentials --json` with the operator
attestation `contents-write,pull-requests-read` and the validator attestation;
it verifies separation but does not introspect fine-grained permissions.

The d2b rig accepts only `v3`; city-source accepts only `main` and remains
suspended-on-start. d2b is enabled first. Do not enable city-source for live
repair until the U8 disposable d2b acceptance passes. Static and native
credential-free tests cover both configurations without mutating GitHub.
Authenticated live evidence remains private and redacted. The capability never
merges, force-pushes, rebases, approves workflow runs, creates a replacement
PR, or changes another target. Human merge ownership remains with human
owners, who retain the final merge decision. No live U8 acceptance is claimed
by this source tree.

## Clean reset

The reset and bind-mount removal are human-only actions. Follow the
fail-closed, redacted runbook in [docs/operations.md](docs/operations.md):
inventory active work and Discord apps, allowlists, maps, bindings, and
launchers privately; stop and unregister the old root city; confirm and
unmount the d2b bind mount without recursive deletion; remove only confirmed
old root-city runtime paths; initialize the nested city; bind the verified
external checkout and a separate city-source clone; and re-import Discord. The
runbook preserves the external checkout and its product-local `.beads/`,
`.gitignore`, and hooks.

## Verification and provenance

Run the credential-free focused gate from the repository root:

```text
python3 tests/test_city.py
```

Optional native smoke uses a host-supplied `GC_BIN` and an isolated external
fixture. Live authenticated ingress, Copilot execution, Discord traffic, and
credentialed publication remain redacted manual smokes.

Local content is Apache-2.0. The adapted cookbook layout, tier vocabulary,
mayor concepts, and selected wording are recorded as MIT-derived material
from [thinkjones/gascity-cookbook](https://github.com/thinkjones/gascity-cookbook).
The [rencire/gascity-flake](https://github.com/rencire/gascity-flake)
repository has no license; no content was copied from it. See
[PROVENANCE.md](PROVENANCE.md).
