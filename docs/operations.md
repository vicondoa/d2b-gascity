# Operations

This repository is the portable source for one Gas City city. The only
active city root is `cities/d2b-gascity`. Native Gas City owns the supervisor,
city registration, imported services, retry, stop, and per-user state
lifecycle. The imported packs are source-only; there is no repository-specific
wrapper, relay, or second supervisor.

The external d2b checkout is not repository content and must not be a local
checkout or bind mount under this repository. Bind it through native
`gc rig add`; the path belongs only in live `.gc/site.toml`.

## Install and initialize

Install the pinned `gc`, `copilot`, and `gh` runtimes, plus `herdr` 0.7.1+
and optional `codex` and ingress tooling, through the separate private
`vicondoa/gascity.nix` repository or another compatible host source. This city
requires `herdr` 0.7.1+ on `PATH`; Gas City's builtin herdr session provider
is verified upstream against that version. Runtime installation remains owned
by the separate host source. The city uses Gas City's stock builtin Copilot
CLI provider for agent models and keeps stock Codex available.
The exact four model tiers are documented below and in
[recipes/model-tiers.md](../recipes/model-tiers.md).

The core distribution is inert: installation does not start a supervisor,
city, tunnel, or custom service. From the nested city directory:

```text
cd cities/d2b-gascity
export GC_CITY_PATH="$(pwd)"  # host-local; do not commit this value
gc init --file city.toml --preserve-existing --no-start .
```

The host supplies the user-owned supervisor configuration. Link it at the
native `GC_HOME` location without copying it into this repository:

```text
GC_HOME="${GC_HOME:-$HOME/.gc}"
ln -s <host-supervisor-config> "$GC_HOME/supervisor.toml"
```

Host-rendered service environments may provide `GC_CITY_NAME=d2b-gascity`,
`GC_CITY_PATH`, and the existing supervisor value for `GC_API_BASE_URL`.
Keep those values host-local. Then start the native city:

```text
gc start
```

The first manual start may install and enable the native user supervisor and
linger. That persistence and reboot recovery are native behavior, not a
second host-wide lifecycle.

## Gas City pack composition

`pack.toml` imports the official core, Beads, Gas City pack, and Discord
packs. The Gas City pack is imported at city scope as `gc`. The `d2b` rig
imports `https://github.com/gastownhall/gascity-packs/tree/main/gascity/roles`
so the rig receives `run-operator`, `implementation-worker`, `publisher`,
`requirements-planner`, and the other official build roles. The city-scope
pack supplies formulas, the `claim` command, and the `gc.mayor` coordinator
skill.

The Gas City pack source is
`https://github.com/gastownhall/gascity-packs/tree/main/gascity` at
`sha:9f98ea4e1974cb49d18cd0c453eb81b2370cca84`. The Discord source is
`https://github.com/gastownhall/gascity-packs/tree/main/discord` at the same
pin. Core and Beads remain pinned to the Gas City `v1.4.1` commit recorded in
`packs.lock`.

The principal formulas include:

- `build-basic`, `implement`, `review`, and `publish`;
- `github-issue-fix` and `github-pr-review`;
- `mol-d2b-discord-fix-issue` for Discord first-run `origin/v3` workspace
  setup.
- the rig-imported `pr-babysit-sweep` order and
  `mol-pr-babysit-repair` Formula v2 for target-only pull-request work.

The standalone `bd.dog` pool patch is a configuration workaround for
[gastownhall/gascity#5716](https://github.com/gastownhall/gascity/issues/5716).
With `max = 1`, Gas City treats the imported city-scoped dog as one stable
canonical singleton, so claim and actor identity use the same alias while
Dolt maintenance is serialized. The maintenance dog uses the inexpensive
`fast-worker` tier. Remove this patch only after the pinned Gas City version
includes the upstream fix; the linked issue is the durable removal tracker.

The d2b rig formula defaults set `base_branch = "v3"` and
`target_branch = "v3"`; city-source uses `main` for both. Publication must
persist `metadata.merge_strategy=pr` plus `metadata.target=v3` for d2b or
`metadata.target=main` for city-source and refuse direct merges. The handoff
receipt uses `target=<rig>/pr-babysit.pr-babysitter`; the watch records
`base_ref=v3` or `base_ref=main`; and the publication bead records
`merge_strategy=pr`. Never merge or force-push. Host branch protection for
`v3` is defense-in-depth and must require pull requests and apply to
administrators; this repository does not claim the current host is already
configured that way. Merge decisions remain human-owned.

Inspect the composed workflow with native commands such as:

```text
gc status
gc formula show build-basic
gc service list
gc service doctor
```

The local core pack provides the global `command-glossary` and
`operational-awareness` fragments. The official Discord pack provides
`discord-v0`, and the city provides `d2b-governance`. `discord-v0` gives every
session that receives a Discord event the explicit reply contract. The daemon uses
`patrol_interval=30s`, `max_restarts=5`, `restart_window=1h`,
`shutdown_timeout=5s`, and `formula_v2=true`.

## Bind the product and city-source rigs

The nested `cities/d2b-gascity/city.toml` declares two pathless native work
surfaces. The `d2b` product rig uses prefix `d2b` and branch `v3`.
The suspended-on-start `city-source` rig uses prefix `city` and branch `main`
for changes to this repository.

Because `gc rig add` validates every declared rig and accepts one binding per
invocation, seed the machine-local `city-source` binding in `.gc/site.toml`
before binding the external product checkout. The path must be a separate
clone or worktree of `d2b-gascity`, never the live nested city checkout:

```toml
[[rig]]
name = "city-source"
path = "/path/to/a/d2b-gascity-checkout"
```

Then provision both rigs through native Gas City:

```text
gc rig add <d2b-checkout> --name d2b --city .
gc rig add <separate-d2b-gascity-checkout> \
  --name city-source --start-suspended --city .
gc status
```

Checkout paths are written to live `.gc/site.toml` only. Do not add a committed
path, named worker, or service definition to this source repository. The same
model-tier projection applies to both rigs: Sol plans, Grok reviews, Luna
implements, and fast Luna performs mechanical operations. Product publication
targets `v3`; city-source publication targets `main`.

## Discord services and ingress

The official Discord pack supplies three native services under
`.gc/services/discord`:

| Service | Publication | Responsibility |
| --- | --- | --- |
| `discord-interactions` | public | signed Discord Interactions at `/v0/discord/interactions` |
| `discord-admin` | tenant/access-policy protected | app setup and status without token values |
| `discord-gateway` | private | inbound DMs and guild or thread messages |

Only `discord-interactions` is public. `discord-admin` must remain
tenant/access-policy protected and must never be exposed publicly.
`discord-gateway` remains private. The official Discord pack owns all three
native services; this city authors none.

Use native diagnosis and restart:

```text
gc service list
gc service doctor
gc service restart discord-gateway
```

The host may publish the signed Interactions endpoint through an outbound-only
connector. Keep the dashboard behind the host's access policy and keep home
router inbound ports closed. Do not author a Discord service, relay, wrapper,
binary, or publication system here.

## Import Discord apps

Create the app in the Discord Developer Portal with the least-privilege
settings used by the official Discord pack:

- Under OAuth2's install scopes, select `bot` and
  `applications.commands`. Discord includes `applications.commands` with the
  `bot` scope, but selecting both makes the intended install surface clear.
- Under Bot Permissions, grant these permissions:
  - `View Channels`
  - `Send Messages`
  - `Read Message History`
  - `Create Public Threads`
  - `Send Messages in Threads`
- Verify those permissions exist for the bot in every allowed channel and
  thread, including channel-specific permission overwrites.
- Under Bot > Privileged Gateway Intents, enable `Message Content Intent` for
  ambient reads and launcher rooms.

The pack does not require `Administrator`, `Manage Guild`, `Manage Roles`,
`Manage Channels`, `Manage Messages`, or `Manage Webhooks`. It also does not
need `Attach Files`, `Add Reactions`, `Embed Links`, or `Presence Intent`.
Keep those broader permissions and intents disabled; this pack posts plain
message bodies and does not use webhooks, attachments, reactions, embeds, or
presence controls.

Import the app's metadata and token without writing a secret to this
repository:

```text
<host-secret-command> |
  gc discord import-app \
    --application-id <application-id> \
    --public-key <public-key> \
    --bot-token-file /dev/stdin \
    --guild-allowlist <guild-id> \
    --channel-allowlist <channel-id> \
    --role-allowlist <role-id>
```

The default app owns Interactions, `/gc` commands, workflow mappings, and
launcher rooms. Allowlists are enforced for guilds, channels, and roles.
Token material stays host-owned with mode `0600`; never commit an app token,
credential path, real identifier, or live payload.

Named multi-app identities are chat-only for now. Add one with a stable
lowercase name:

```text
<host-secret-command> |
  gc discord import-app \
    --app <chat-app> \
    --application-id <application-id> \
    --public-key <public-key> \
    --bot-token-file /dev/stdin \
    --guild-allowlist <chat-guild-id> \
    --channel-allowlist <chat-channel-id> \
    --role-allowlist <chat-role-id>
```

Each named app has an independent, isolated token, Discord connection, policy,
binding, receipt, and health counters. Keep each named app's guild, channel,
and role allowlists independent from the default app. Restart the gateway
after adding, removing, or rotating an app. Named apps remain chat-only;
Interactions, workflow maps, and launchers continue to use the default app.

## `/gc fix` and workflow mapping

Register the guild-scoped command after installing the default app:

```text
gc discord sync-commands <guild-id>
```

The supported `/gc fix` command opens a modal for a summary and context. If
the modal path cannot be completed, the pack falls back to a prompt. Map a
channel or rig to the `rig/implementation-worker` target and the local
`mol-d2b-discord-fix-issue` formula:

```text
gc discord map-channel <guild-id> <channel-id> <rig>/implementation-worker \
  --fix-formula mol-d2b-discord-fix-issue
gc discord map-rig <guild-id> <rig> <rig>/implementation-worker \
  --fix-formula mol-d2b-discord-fix-issue
```

`mol-d2b-discord-fix-issue` is a narrow local extension of the official
`mol-discord-fix-issue` formula. It changes only workspace setup to create
first-run work from `origin/v3`; it fetches all origin heads, requires a clean
worktree, preserves recorded branches, recreates a missing recorded worktree
only from that branch, validates `base_ref=origin/v3` and the `fork_sha` commit
ancestry, rebases with `--rebase-merges --reapply-cherry-picks --empty=stop`,
and stops on conflicts or missing refs with recovery instructions. All other
official Discord workflow behavior is retained.

Publication is PR-only: persist and verify `merge_strategy=pr` plus
`target=v3` for d2b or `target=main` for city-source, refuse direct merges,
and keep merge decisions human-owned. This publication metadata is distinct
from the handoff receipt's
`target=<rig>/pr-babysit.pr-babysitter` and the watch's `base_ref=v3` or
`base_ref=main`.

Mappings and command sync are native pack state. The city does not copy or
hard-code them.

## PR babysitting and human-gate recovery

### Native surfaces and setup

The enabled capability is the repository-owned, target-only `pr-babysit` Pack
v2 at `packs/pr-babysit`. It is imported once at each rig in
`cities/d2b-gascity/city.toml`; it is not a city-scope or `packs/core-city`
import. The binding-qualified native identities are
`d2b/pr-babysit.pr-babysitter` and
`city-source/pr-babysit.pr-babysitter`. Each identity is a fresh, on-demand
`fast-worker` with `max_active_sessions = 1` and workdir
`.gc/agents/pr-babysitter`.

The session setup script
`packs/pr-babysit/assets/scripts/project-copilot-skill.sh` projects the exact
vendored skill into both `.github/skills/pr-babysit` and
`.agents/skills/pr-babysit` under that workdir. The mandatory prompt gate
checks the pinned commit and every file hash before any `gh`, Git, or
repository action. It fails closed if `GC_DIR`, `GC_RIG_ROOT`, the projection,
or the pinned skill is missing or stale. The projection never writes the rig
root or a user-global directory.

The deterministic state CLI is exposed once by the already city-scoped
`packs/core-city` pack as `gc core-city pr-babysit <action>`. Its wrapper
delegates through the repository-relative sibling path
`packs/pr-babysit/assets/scripts/pr-babysit-state.py` and fails closed when
that helper is absent, not executable, or outside the expected packs root.
The rig-imported pack has no second command entrypoint.

Inspect the native surfaces without starting a service:

```text
gc config show --json
gc config explain --rig d2b --agent pr-babysitter
gc skill list --agent d2b/pr-babysit.pr-babysitter --json
gc skill list --agent city-source/pr-babysit.pr-babysitter --json
gc formula show mol-pr-babysit-repair --rig d2b --json
```

### Publication handoff and receipt

The shadowed `open-pr` publication asset preserves official PR creation, then
calls the local command below with the verified publication bead and PR
identity:

```text
gc core-city pr-babysit publication-handoff \
  --rig d2b --publication-bead-id <publication-bead-id> \
  --url <pull-request-url> --pr-number <number> --json
gc core-city pr-babysit verify-handoff \
  --rig d2b --publication-bead-id <publication-bead-id> \
  --url <pull-request-url> --pr-number <number> --json
```

The handoff queries GitHub and verifies the host, owner, repository, PR number
or URL, open state, draft state, base ref, head ref, and current head SHA. It
requires persisted `merge_strategy=pr` plus `base_ref`, `target`, or
`target_branch`; it never infers a missing target. It derives one stable watch
ID, creates or reuses exactly one Beads watch, routes it without wake, writes
matching verified receipts, and then nudges the binding-qualified babysitter.
A complete receipt requires `handoff_verified=true`, the self watch ID, the
binding-qualified target, the publication bead, `handoff_route_status=complete`,
and `handoff_wake_status=delivered`. `pending`, `ready`, and `route-failed`
receipts cannot act; `ready` is only a recoverable publication-handoff wake
replay intermediate. A repeated complete receipt does not issue another wake.
Publication may close only after
`verify-handoff` re-reads the matching receipt. Inspect safe state with:

```text
gc core-city pr-babysit show --watch-id <watch-id> --json
```

The handoff result carries
`target=<rig>/pr-babysit.pr-babysitter`, stored as `handoff_target` in the
receipt metadata. The watch record carries
`base_ref=v3` for d2b or `base_ref=main` for city-source. The publication bead
must carry `metadata.merge_strategy=pr` and one matching target field:
`metadata.base_ref`, `metadata.target`, or `metadata.target_branch`. These are
publication metadata and separate from the handoff routing target. A missing,
mismatched, draft, wrong-base,
wrong-repository, or absent PR identity creates no watcher and no route.
Repeat the commands with `--rig city-source` and the city-source publication
bead for a `main`-targeted pull request.

### Watch states and checkpoint order

Beads is the durable source of truth. A watch records only safe identity,
posture, generation, observed head SHA, action claim, attempt budget, last
snapshot, next snapshot, and terminal reason. Snapshot bodies and logs remain
ephemeral in the ignored babysitter workdir. The legal watch states are:

| State | Meaning |
| --- | --- |
| `watching` | Eligible for a fresh checkpoint when due. |
| `waiting` | Current checks or review are still in progress. |
| `repairing` | One claimed repair child is active or awaiting confirmation. |
| `merge-ready` | Current evidence supports a human integration handoff. |
| `blocked` | A human or authorization decision is required. |
| `exhausted` | A repair or time budget ended autonomous progress. |
| `terminal` | The PR is merged or closed; no further action is allowed. |

Watch `claim_status` values written by state code are `none`, `claimed`,
`result-recorded`, `blocked`, and `exhausted`. Action records may also use
`ambiguous` and `stale`. Beads issue status `closed` is separate from
`claim_status` and is written when a confirmed action child closes or a watch
reaches terminal. The watch records exhaustion when its repair or time budget
ends. Only a `result-recorded` action with a passed `make check` and matching
pushed SHA plus a current passed reviewer verdict may be confirmed and
closed; failed or ambiguous actions remain human blockers. Only `watching`
watches may claim repairs; `waiting` may transition to `merge-ready` or
`blocked` but not directly to `repairing`. Confirmed review repairs retain
their carried action kind and addressed IDs as pending dispositions; a
claim-free `watching` or `waiting` watch remains sweep-eligible until those
dispositions are acknowledged.

The `pr-babysit-sweep` cooldown order in the rig-imported pack runs every
`1m` through the canonical bounded `sweep` state action. It validates the
rig and limit, lists due records, rechecks that each is still a routable
`watching` or `waiting` record with no claim, and routes the binding-qualified
target:

```text
gc core-city pr-babysit sweep --rig d2b --limit 4 --json
```

Sweep lock acquisition is nonblocking; a busy watch is left due for the next
`1m` tick. State mutation and repair operations retain blocking watch locks.

One checkpoint is one fresh snapshot, one ordered decision pass, and one
durable state write. The fixed order is snapshot, terminal state, head
reconciliation, review feedback, current-head CI, exact branch currency, then
settle or wait. A repair action follows `claim -> act -> confirm`; its child
must be linked with `bd dep <action-id> --blocks <watch-id>`. Native
dependency-close wake resumes the watch only after the action is confirmed.
Due listing uses an unbounded metadata-filtered Beads listing, then sorts by
due time and applies the requested limit, so a large watch set cannot starve
older due records. Each routed watch atomically advances its next snapshot
time and takes a short wake lease under the watch lock; the lease is settled
after routing so concurrent sweeps issue one nudge. The route timeout is
20 seconds, shorter than the native 30-second order budget but long enough for
a fresh provider session to start. Operators may set
`PR_BABYSIT_ROUTE_TIMEOUT_SECONDS` from 1 through 29 when the environment
requires a different bound. The order is short-lived and owns no daemon,
webhook, relay, or in-session watcher process.

### Bounded repair and stop behavior

`mol-pr-babysit-repair` is a Formula v2 graph with
`prepare-worktree`, `repair`, `review`, `validate-and-report`, and
`close-action` steps. It uses the existing PR head and branch, validates
`make check`, records a candidate head and independent reviewer verdict,
performs one normal push, verifies the new remote SHA, and confirms the
action. The Formula workflow is attached to the durable watch bead; the
action child carries the claim and blocks that watch until confirmation. Git
fetch, push, and `ls-remote` calls use a bounded timeout and reconcile the
remote after failures. It never creates a replacement PR or remote branch.
The action persists `formula_attached=false`, then `pending` before native
idempotent cooking, and `true` with the returned root afterward. A cook
failure blocks; a metadata-update failure leaves `pending` for a safe retry.
If a crash leaves an action `claim_status=result-recorded`, replay verifies the
persisted candidate, verdict, validation, pushed SHA, and remote head, then
returns successfully without rerunning validation or pushing; `close-action`
performs the final confirmation.

CI repairs have three attempts per normalized action kind, failure fingerprint,
and head SHA; review repairs have two for that same triple. A new head starts
a fresh counter. The active budget is eight active hours and the hard backstop
is three days. A failed validation, stale remote, missing branch, or uncertain
result is a blocker. An ambiguous push records `ambiguous-outcome`, blocks the
watch, and is never retried.

`merge-ready` requires a structured current-snapshot evidence object with
`current_head_sha`, certain mergeability, a clean branch, terminal and
successful required checks, no actionable feedback, no pending human
interaction, no currency item, and a satisfied quiet window. Missing or false
evidence is rejected.

After a confirmed review repair, the watch retains
`pending_disposition_action_kind` and `pending_disposition_ids` (plus the
head and generation fence). The next fresh snapshot must match each ID to its
current content identity and run the local
`pr-snapshot mark` command for every item before
`acknowledge-dispositions` clears the carryover. Missing or edited IDs remain
actionable and block honestly.

`MERGED` and `CLOSED` are absorbing `terminal` outcomes. An open
`blocked`, `exhausted`, or `merge-ready` watch may be explicitly rearmed with
`rearm=true`; rearming advances the generation and clears stale claims. If a
persisted formula root is still open, rearm fails with a human blocker and
does not detach it. Closed or missing roots have their action and dependency
edges cleaned before rearm proceeds. A terminal watch cannot be rearmed.
`merge-ready` is an evidence handoff only, never permission for an automatic
merge. Repairs are same-repository-only:
`head_repository` must equal the verified `owner/repository`. Fork or
cross-repository PRs are human blockers in v1 and receive no autonomous
repair.

### Credential and target boundary

Version 1 does not call `update-branch`. `BEHIND`, dirty, conflicting, unknown
branch-currency capability, stale-head, and ambiguous push evidence become
human blockers. The repair identity is operator-attested with repository
Contents write and Pull requests read only. It must not have Pull requests
write, merge/admin, workflow-approval, or Copilot Requests authority. The
agent cannot introspect fine-grained permissions, so it fails closed without
the operator attestation. The implementation worker runs the sole
repository-default `make check`, creates the local repair commit only after it
passes, and records `worker_signoff_sha` on the action. The independent
reviewer binds its verdict to the same candidate. Run-operator verifies the
worker signoff, reviewer verdict, exact candidate, worktree cleanliness,
origin identity, and unchanged remote head before one normal push. It does not
rerun `make check`.

The reviewer is read-only with respect to GitHub and never resolves review
threads. After a confirmed review repair, record each addressed thread,
comment, or review locally with `pr-snapshot mark` and its current
content identity using `handled` or `ignored`; changed content reopens the
item.

### Pull-request template gate

Before review feedback, CI, or branch currency, the snapshot validates the PR
body against the canonical template. It requires `Summary`, `Validation
evidence`, and `Notes`, plus checked entries for focused tests, successful
exact `make check`, wider lanes, owner-local tests, changelog, and docs/CI.
Only safe error codes leave the snapshot; body text is never persisted.

For an invalid body, the babysitter runs:

```text
gc core-city pr-babysit dispatch-template-remediation \
  --watch-id <watch-id> --generation <generation> \
  --head-sha <head-sha> \
  --template-errors <comma-separated-safe-error-codes> --json
```

The command creates one deterministic remediation bead, links it as a blocker
of the watch, and slings it to `<rig>/gc.publisher`. The publisher changes only
the PR body. It checks the `make check` item only from actual successful
workflow evidence and routes back to implementation when evidence is absent.
Closing the remediation wakes the waiting watch; a valid fresh snapshot
returns it to `watching`.

The operator may verify the attestation and token separation without a GitHub
request:

```text
PR_BABYSIT_GITHUB_CAPABILITY_ATTESTED=contents-write,pull-requests-read \
  gc core-city pr-babysit check-credentials --json
```

This command checks the operator attestation and token separation only.

Publication credentials, repair GitHub credentials, Copilot Requests
credentials, and Discord app credentials are separate. `GH_TOKEN` and
`GITHUB_TOKEN` must not reuse Copilot tokens. Never print or persist any
credential. The babysitter and repair worker never merge, force-push, rebase,
approve workflows, use `--force-with-lease`, update branch currency, act on
another PR, or bypass the pull-request handoff. Human owners retain merge
ownership.

The host may load the dedicated repair token into the native supervisor as
`GH_TOKEN`, but the city pins both GitHub token variables empty for every
managed session. The d2b babysitter receives only the non-secret capability
attestation required to dispatch a repair; it never receives a GitHub token.
Only the d2b `gc.run-operator` agent rehydrates `GH_TOKEN` from the controller
environment. The implementation worker commits locally without pushing, the
independent reviewer does not mutate GitHub, and the run operator owns the
single validated normal push.

### Rollout and evidence

d2b is enabled first. The `city-source` rig remains suspended-on-start and
must not be enabled for live repair until U8 disposable d2b acceptance passes.
Static and native credential-free tests cover both d2b/`v3` and
city-source/`main` without mutating GitHub. Authenticated live evidence is
host-local, private, and redacted; record only safe pass/fail results outside
this repository. No live U8 acceptance is claimed by this source tree.

The existing `gate-sweep` remains the native mechanical gate sweep. Human-gate
notification and stale-gate re-notification are separate from the
target-only PR babysitter. Do not add a city-owned service, daemon, webhook,
relay, replacement scheduler, or delivery verifier.

## Chat bindings, ambient reads, and launchers

Room/thread bindings and exact DM bindings route messages to named sessions:

```text
gc discord bind-dm <dm-channel-id> <session>
gc discord bind-room --guild-id <guild-id> <channel-id> <session> [<session>...]
gc discord bind-dm --app <chat-app> <dm-channel-id> <session>
gc discord bind-room --app <chat-app> --guild-id <guild-id> \
  <channel-id> <session> [<session>...]
gc discord bind-room --guild-id <guild-id> \
  --enable-ambient-read <channel-id> <session> [<session>...]
gc discord bind-room --guild-id <guild-id> \
  --enable-ambient-read --allow-untargeted-ambient-delivery \
  <channel-id> <session>
# Targeted peer fanout is the canonical safe example.
gc discord bind-room --guild-id <guild-id> \
  --enable-peer-fanout \
  --max-peer-triggered-publishes-per-root <n> \
  --max-peer-triggered-publishes-per-session-per-minute <n> \
  --max-total-peer-deliveries-per-root <n> \
  <channel-id> <session> [<session>...]
```

Each `bind-room` command takes one or more session names after the channel id.
Direct `bind-room` routing and `enable-room-launch` are mutually
exclusive alternatives for the same room; choose one, not both.

Ambient-read rooms are targeted by exact `@session_name` values. A
single-agent binding may opt into untargeted ambient delivery; multi-session
ambient delivery remains targeted-only. Thread bindings inherit the parent
room when appropriate.

Peer fanout should remain targeted, which is the default-safe setting. Add
`--allow-untargeted-peer-fanout` only in the separate opt-in case when
untargeted delivery is intentional:

```text
gc discord bind-room --guild-id <guild-id> \
  --enable-peer-fanout \
  --allow-untargeted-peer-fanout \
  --max-peer-triggered-publishes-per-root <n> \
  --max-peer-triggered-publishes-per-session-per-minute <n> \
  --max-total-peer-deliveries-per-root <n> \
  <channel-id> <session> [<session>...]
```

Keep the per-root, per-session-per-minute, and total-delivery budgets bounded.

Launcher rooms provide the room-first flow:

```text
gc discord enable-room-launch --guild-id <guild-id> <channel-id>
gc discord enable-room-launch --guild-id <guild-id> \
  --response-mode respond_all --default-handle <rig>/<agent> <channel-id>
```

Direct `bind-room` and `enable-room-launch` are mutually exclusive alternatives
for the same room. Launcher rooms use `@@handle` and `--default-handle`; direct
bindings use one or more session names only.

`@@handle` creates a managed thread session. `mention_only` requires a
qualified `@@handle`; `respond_all` can use its configured default while
top-level retargeting still requires `@@handle`. Follow-ups in managed
threads continue to the addressed session. Launcher and ambient room reads
require Discord's Message Content Intent.

Guild and thread messages otherwise require a bot mention. Bot-authored
messages are ignored. Untargeted ordinary room messages can fan out only to
the explicitly bound participants. Direct room peer fanout is disabled by
default; when enabled it is budgeted and retryable. Launcher-managed threads
use the official managed-thread fanout defaults and can disable or constrain
peer targets with the pack's fanout flags.

## Reply and workflow control

Agent output remains private until it is explicitly published:

```text
# Preferred same-app reply to the current Discord turn
gc discord reply-current --body-file <reply-file>

# Explicit publication through a saved binding
gc discord publish --binding room:<channel-id> --body-file <reply-file>

# Explicit publication through a named chat app
gc discord publish --app <chat-app> --binding room:<channel-id> \
  --body-file <reply-file>

# Direct channel/thread status projection
gc discord post-message --channel-id <channel-id> --thread-id <thread-id> \
  --body "Started work"

# Thread-aware explicit publication
gc discord publish --binding room:<channel-id> \
  --conversation-id <conversation-id> --trigger <trigger> \
  --body-file <reply-file>

# Status projection and repair
gc discord post-message --request-id <request-id> --body "Started work"
gc discord retry-peer-fanout <publish-id>
gc discord release-workflow --request-id <request-id>
```

`reply-current` preserves the app and binding that received the turn.
Explicit publication can carry source event metadata and may trigger the
opt-in peer fanout budget. `release-workflow` is the recovery path for a
stalled workflow. Inspect safe status, including JSON:

```text
gc discord status
gc discord status --json
```

The pack posts plain message bodies. It supports the `/gc fix` slash command
and its modal submission, not general buttons, select menus, context menus,
arbitrary slash commands, attachment ingestion or publication, embeds,
reactions, or presence controls.

The `Message Content Intent` setting is required for ambient and launcher
reads.

## Copilot CLI, Codex, and credential boundaries

Gas City defaults to the stock `copilot` command through `builtin:copilot`.
The workspace uses `deep-thinker`, and the d2b role projection uses exactly
these four tier aliases:

| Tier | Model | Effort | Context | Primary roles |
| --- | --- | --- | --- | --- |
| `deep-thinker` | `gpt-5.6-sol` | `medium` | `long_context` | mayor, requirements-planner, design-author, task-decomposer |
| `reviewer` | `grok-4.6` | `high` | `long_context` | six review, analysis, and triage roles |
| `solid-worker` | `gpt-5.6-luna` | `max` | `long_context` | implementation-worker |
| `fast-worker` | `gpt-5.6-luna` | `medium` | `default` | run-operator, publisher |

Stock `providers.codex` remains available as `builtin:codex` for an explicit
alternate agent patch only. It is not a tier or a default role assignment.
See [the cookbook layout and model-tier design](designs/2026-08-28-001-cookbook-layout-and-model-tiers.md)
and [the model-tier recipe](../recipes/model-tiers.md).

Gas City assigns each Copilot-backed session a unique UUID at fresh launch and
resumes that exact ID on restart rather than opening Copilot's interrupted
session selector.

The host supplies the Copilot CLI binary and may export `COPILOT_GITHUB_TOKEN`
in the operator environment. Optional `codex` and Codex Router are host
support for the Codex provider, not required to start the city. Do not put
Copilot token variables, token paths, router URLs, or
`GH_TOKEN=$COPILOT_GITHUB_TOKEN` in `city.toml`.

Keep Copilot Requests, Codex credentials, d2b publication, and Discord app
credentials separate. Discord app tokens belong to the host-managed app
state and are never used as GitHub, Copilot, or Codex credentials. Do not
store prompts, model responses, private pull-request payloads, or live
evidence in this repository.

The adapted city-local mayor uses the official `gc.mayor` skill and official
Gas City formulas and roles. It plans, creates beads, dispatches work,
monitors results, and waits when idle. It must never implement source changes,
merge, force-push, or bypass either the d2b `v3` or city-source `main`
pull-request handoff.

## Human-only clean reset and cutover

This procedure is intentionally human-only. It replaces old native state; it
does not migrate or copy runtime state. Stop if any verification is
ambiguous, if the external checkout cannot be identified, or if a process or
worktree still uses the bind mount.

### 1. Make a private preflight inventory

Before touching the old city, record a redacted inventory outside this
repository. Include:

- active work, sessions, worktrees, branches, pending requests, in-flight
  formulas, and recovery metadata;
- the external d2b checkout's recorded source identity, remotes, branches,
  open pull requests, and product-local `.beads/`, `.gitignore`, and agent
  hooks;
- Discord apps and app owners, guild/channel/role allowlists, channel and
  rig maps, room and DM bindings, launcher rooms, and service exposure.

Record only safe labels and counts. Do not copy tokens, identifiers, live
prompts, responses, reports, or pull-request payloads into this repository.
The inventory is private operator evidence, not a committed migration
artifact.

### 2. Stop and unregister the old root city

Select the old root city explicitly and confirm the nested target is not
registered. Stop its sessions, then unregister that exact old path:

```text
gc stop <old-root-city-path>
gc unregister <old-root-city-path>
```

`gc stop` and `gc unregister` are distinct commands in the pinned CLI.
Verify with native status that the old root city is no longer registered and
that no root and nested city definitions are active together. Do not
unregister by bare name after the nested directory exists, and do not start
or initialize the nested city until this check passes.

### 3. Confirm and unmount the d2b bind mount

Resolve the bind-mount source and mountpoint from host mount inspection.
Confirm that the source is the recorded external d2b checkout, that its Git
identity, remotes, branch, open pull requests, product-local `.beads/`,
`.gitignore`, and agent hooks are intact, and that no process or worktree is
using it.

Unmount the mountpoint only after those checks pass. Unmounting is not
checkout deletion. Do not recursively delete the mount source, and do not
run cleanup that can traverse into the external checkout. If the source,
mountpoint, or users are ambiguous, stop and ask the human owner to resolve
the inventory.

### 4. Remove only confirmed old root-city runtime paths

After the old city is stopped and unregistered, remove only the confirmed
old root-city `.gc`, `.beads`, session, and worktree paths. Verify each path
belongs to the old root city before removal. Never remove the external
checkout's product-local `.beads/`, `.gitignore`, or hooks, and never reuse
old sessions, mappings, worktrees, credentials, logs, prompts, responses, or
reports.

### 5. Initialize and bind the nested city

Set the host-local city selector to the nested source and initialize in
place:

```text
export GC_CITY_PATH="<host-local>/cities/d2b-gascity"
cd cities/d2b-gascity
gc init --file city.toml --preserve-existing --no-start .
```

Create a separate clone or worktree for city-source automation. Never bind
`city-source` to the live nested city checkout. Seed the machine-local binding:

```toml
[[rig]]
name = "city-source"
path = "/path/to/separate/d2b-gascity-checkout"
```

Provision both rigs:

```text
gc rig add <verified-d2b-checkout> --name d2b --city .
gc rig add <separate-d2b-gascity-checkout> \
  --name city-source --start-suspended --city .
gc status
```

`GC_CITY_PATH` is host-local and must not be committed. The `gc init` command
must run from `cities/d2b-gascity`, preserve the authored `city.toml`,
`pack.toml`, `packs.lock`, and local pack import, and create fresh native
state. Rig paths must appear only in live `.gc/site.toml`. Verify one
registered city, the external d2b product rig, and the separate city-source
rig.

### 6. Re-import Discord under the private inventory

Re-import the default app and any named chat app with native commands. Stream
each token through stdin and keep values out of shell history and this
repository:

```text
<host-secret-command> |
  gc discord import-app \
    --application-id <application-id> \
    --public-key <public-key> \
    --bot-token-file /dev/stdin \
    --guild-allowlist <guild-id> \
    --channel-allowlist <channel-id> \
    --role-allowlist <role-id>
```

Restore only the private inventory's intended guild, channel, and role
allowlists, room and DM bindings, channel and rig maps, and launchers. Use
least-privilege Discord permissions: `View Channels`, `Send Messages`, `Read
Message History`, `Create Public Threads`, and `Send Messages in Threads`;
enable `Message Content Intent` only when ambient or launcher reads require
it. Keep `Administrator`, management permissions, webhooks, attachments,
reactions, embeds, and presence controls disabled unless a separately
approved host policy requires them.

Preserve service exposure boundaries: `discord-interactions` is public for
signed `/v0/discord/interactions`, `discord-admin` is tenant/access-policy
protected, and `discord-gateway` is private. The official Discord pack owns
all three services. Keep Copilot Requests, d2b publication, and Discord app
credentials separate, then verify `merge_strategy=pr` plus `target=v3` for
d2b or `target=main` for city-source before any human-owned pull-request
publication. Do not confuse that publication metadata with the handoff
receipt target `<rig>/pr-babysit.pr-babysitter` or the watch `base_ref`.

## Stop or unregister

Stop the city's sessions with native Gas City:

```text
gc stop
```

The city remains registered. Use `gc unregister <city-path>` only when
decommissioning or moving that exact city. Do not add a custom shutdown hook
or host lifecycle service.
