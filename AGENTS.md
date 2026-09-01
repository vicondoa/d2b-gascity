# Agent rules for d2b-gascity

## Repository boundary

This private repository is the portable source for one Gas City city, one
external `vicondoa/d2b` product rig on branch `v3`, and one machine-local
`city-source` clone for changes to this repository on `main`. The only active
city root is `cities/d2b-gascity`; the repository root is not a city and must
not contain a repository-local d2b checkout or bind mount.

The plan in `docs/plans/` is the authority. Do not edit a plan to record
progress. The separate private `vicondoa/gascity.nix` repository owns runtime
installation and host integration; do not recreate that boundary here.

Native Gas City owns the supervisor, city registration, imported services,
sessions, retries, and runtime state. Do not add a second lifecycle owner,
custom wrapper, relay, publication helper, or delivery verification system.
Bind the external product checkout only with native `gc rig add`. Bind
`city-source` to a separate clone or worktree, never the live nested city
checkout. Both paths belong in live `.gc/site.toml`, not in portable source.

## Portable model tiers

The reusable `packs/core-city` pack and nested city define exactly four
aliases:

- `deep-thinker`: `gpt-5.6-sol`, medium effort, `long_context`.
- `reviewer`: `grok-4.6`, high effort, `long_context`.
- `solid-worker`: `gpt-5.6-luna`, max effort, `long_context`.
- `fast-worker`: `gpt-5.6-luna`, medium effort, default context.

The city maps the twelve imported roles for both rigs to those aliases. Stock
`builtin:codex` remains an explicit alternate provider only. Do not add
foreign providers, custom model adapters, or tier-specific routing machinery.

## Mayor and publication rules

The adapted mayor is one city-local native session using the official
`gc.mayor` skill and official Gas City formulas and roles. It plans, creates
beads, dispatches work, monitors results, and waits when idle. It must never
implement source changes, create replacement agents, merge, force-push, or
bypass either repository's pull-request handoff.

Keep `d2b-governance` registered as a global fragment. Publication must
persist and re-read `metadata.merge_strategy=pr` plus the repository-specific
target: `v3` for `d2b`, `main` for `city-source`. The handoff receipt's
`target=<rig>/pr-babysit.pr-babysitter` is the routing target, not the watch
base. The watch stores `base_ref=v3` or `base_ref=main`, while the publication
bead stores `merge_strategy=pr`. Refuse direct merges and accept only the
pull-request handoff. The d2b Discord formula extension is product-only.
Human owners make merge decisions. Host branch protection for `v3` is
defense-in-depth: it must require pull requests and apply to administrators,
but this repository does not claim the current host is already configured
that way.

The rig-imported `pr-babysit` pack provides one binding-qualified babysitter
per rig: `d2b/pr-babysit.pr-babysitter` and
`city-source/pr-babysit.pr-babysitter`. Each is a fresh on-demand
`fast-worker` with one active session and a workdir-local dual projection at
`.github/skills/pr-babysit` and `.agents/skills/pr-babysit`. The mandatory
projection gate runs before any GitHub or repository action.

The city-scoped `core-city` pack exposes the deterministic state command
`gc core-city pr-babysit <action>`. It delegates only to the sibling helper
owned by the rig-imported pack; the rig pack remains the owner of the agent,
skill, order, formula, state helper, and workflows.

Publication calls the native city-scoped command
`gc core-city pr-babysit publication-handoff` and must follow it with
`gc core-city pr-babysit verify-handoff` before closing. The handoff receipt
binds the verified repository, PR number or URL, base, head, current SHA,
watch bead, and babysitter identity. Use `gc core-city pr-babysit show` to
inspect safe watch metadata.

Watch states are `watching`, `waiting`, `repairing`, `merge-ready`, `blocked`,
`exhausted`, and `terminal`. The `claim -> act -> confirm` protocol links an
action child with `bd dep <action-id> --blocks <watch-id>`; native dependency
closure wakes the watch. The `pr-babysit-sweep` cooldown order runs every
`1m` and performs one short checkpoint, not a daemon or resident watcher.
Under the watch lock it rechecks due time and a short `wake_lease_until`,
advances the next snapshot, and retains one five-minute delivery lease after
queueing. The next checkpoint clears that lease; route failure clears it
immediately. Concurrent or repeated sweeps therefore issue one queued nudge,
not an accumulating sling-plus-session pair.
The same order recovers stale unclaimed publisher remediations through the
active native publisher session and restarts a drained named babysitter before
retrying its queued nudge. It does not own either session lifecycle.
Checkpoint order is snapshot, terminal, head, pull-request template, review,
current-head CI, exact branch currency, then one state write.

`mol-pr-babysit-repair` is Formula v2. It validates `make check`, pushes only
the existing PR head, and records the resulting SHA. Budgets are three CI
attempts and two review attempts per action kind, fingerprint, and head SHA,
plus eight active hours and a three-day backstop. A new head starts a fresh
attempt counter.
Operator-requested source work on an already watched pull request must use
`gc core-city pr-babysit dispatch-requested-repair`; never send it through
generic `do-work`, which starts from the repository target rather than the
current PR head. The requested action explicitly rearms a stopped watch, binds
the work bead, and reuses the exact-head worktree, implementation worker, Grok
reviewer, and one-push Formula fence.
The first version does not use `update-branch`: repair is operator-attested
with Contents write and Pull requests read only, while the agent cannot
introspect fine-grained permissions. Pull requests write, merge/admin,
workflow approval, and Copilot Requests authority are refused. `GH_TOKEN` and
`GITHUB_TOKEN` must never reuse Copilot tokens. Stale, dirty, conflicting,
unknown, or ambiguous push evidence blocks; an ambiguous push is never
retried. Never use `--force-with-lease` or a raw rebase. `rearm=true` may
rearm an open blocked, exhausted, or merge-ready watch, but fails with a human
blocker while its persisted formula root is open. Closed or missing roots are
cleaned before rearm proceeds; a terminal watch is never rearmed.

Watch `claim_status` values written by state code are `none`, `claimed`,
`result-recorded`, `blocked`, and `exhausted`. Action records may also use
`ambiguous` and `stale`; Beads issue status `closed` is separate from
`claim_status` and is written when a confirmed action child closes or a watch
reaches terminal. Repairs are same-repository-only:
`head_repository` must equal `owner/repository`.
Fork or cross-repository PRs are human blockers in v1. The implementation
worker runs the sole repository-default `make check`, commits only after it
passes, and records the exact worker signoff SHA. The independent reviewer
binds its verdict to that candidate. Run-operator verifies those records,
worktree cleanliness, origin, and the unchanged remote head before one normal
push; it does not rerun `make check`. Keep the operator-attested
`contents-write,pull-requests-read` GitHub capability and all Copilot, GitHub,
and Discord credentials separate.

- Require every watched PR body to follow the canonical template before
  review or CI babysitting. The required evidence includes a successful exact
  `make check`. Persist only safe template error codes, never the body.
  `dispatch-template-remediation` creates one publisher-owned correction bead
  that blocks the watch; the publisher must route back to implementation when
  successful gate evidence is missing.

Enable d2b first. The `city-source` rig remains suspended-on-start and must
not be enabled for live repair until the U8 disposable d2b acceptance passes.
Static and native credential-free tests cover both targets without mutating
GitHub; authenticated evidence stays private and redacted. No live U8
acceptance is claimed by this source tree.

## Source, host, and reset boundaries

Use the official Gas City core, Beads, Gas City pack, and Discord packs pinned
in the nested `pack.toml` and `packs.lock`. The host supplies `gc`, Copilot
CLI, optional Codex, `gh`, ingress, credentials, mounts, mappings, and
launchers.

The clean reset is human-only. Before changing runtime state, inventory
active work and Discord apps, guild/channel/role allowlists, channel and rig
maps, room and DM bindings, and launchers privately. Stop and unregister the
old root city, confirm the d2b bind-mount source, unmount it without
recursive deletion, preserve the external checkout's product-local
`.beads/`, `.gitignore`, and agent hooks, and remove only confirmed old
root-city runtime paths. Set host-local `GC_CITY_PATH` to
`cities/d2b-gascity`, initialize with
`gc init --file city.toml --preserve-existing --no-start .` from that nested
directory, bind the verified checkout with `gc rig add`, and re-import
Discord through native commands. Create a separate d2b-gascity clone or
worktree for `city-source`, seed only its machine-local site binding, and
provision it with `gc rig add --start-suspended`. Never bind it to the live
nested city checkout.

## Privacy and credentials

Never commit or publish:

- private host values, authorities, addresses, users, channels, roles, maps,
  bindings, launchers, or host configuration;
- credentials, tokens, keys, cookies, password hashes, or credential paths;
- `.gc`, `.beads`, Dolt, databases, worktrees, sessions, sockets, logs,
  reports, or copied runtime state;
- live prompts, model responses, or private pull-request payloads.

Discord app tokens must be streamed through `/dev/stdin` and never stored
here. Preserve least-privilege permissions and the official service exposure
boundary: `discord-interactions` is public, `discord-admin` is protected,
and `discord-gateway` is private. Keep Copilot Requests, d2b publication, and
Discord app credentials separate. Never couple `GH_TOKEN` to a Copilot token.

Generic placeholders and `127.0.0.1` are allowed. `.gitignore` is a
convenience, not a security boundary. Review staged files and the complete
diff before any commit.

## Change and validation rules

- Make one logical change per commit.
- Keep ownership and merge decisions with a human.
- Use ASCII hyphens only.
- Preserve Apache-2.0 licensing for local content and upstream notices for
  imported content.
- Use `mol-d2b-discord-fix-issue.toml` only as the narrow native
  first-run `origin/v3` workspace-setup extension of the official Discord
  formula. Its resume path must fail closed for dirty worktrees, missing
  branches, and legacy or missing `base_ref`/`fork_sha` provenance.

Run the smallest check that proves the changed contract:

```text
python3 tests/test_city.py
make check
GC_BIN=/path/to/gc python3 tests/test_city.py
```

The `GC_BIN` command is optional native smoke coverage. Live authenticated
ingress, Copilot execution, Discord traffic, and credentialed publication
are redacted manual smokes, never committed evidence.

See [README.md](README.md), [docs/operations.md](docs/operations.md),
[docs/testing.md](docs/testing.md), and the recipes for the current source
and runtime contracts. Local adapted cookbook material and license boundaries
are recorded in [PROVENANCE.md](PROVENANCE.md).
