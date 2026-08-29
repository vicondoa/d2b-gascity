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

Install the pinned `gc`, `copilot`, and `gh` runtimes, plus optional `codex`
and ingress tooling, through the separate private `vicondoa/gascity.nix`
repository or another compatible host source. The city defaults to Gas
City's stock builtin Copilot CLI provider and keeps stock Codex available.
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

The d2b rig formula defaults set `base_branch = "v3"` and
`target_branch = "v3"`; city-source uses `main` for both. Publication must
persist `metadata.merge_strategy=pr` plus `metadata.target=v3` for d2b or
`metadata.target=main` for city-source and refuse direct merges. Never merge
or force-push. Host branch protection for `v3` is defense-in-depth and must
require pull requests and apply to administrators; this repository does not
claim the current host is already configured that way. Merge decisions remain
human-owned.

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
and keep merge decisions human-owned.

Mappings and command sync are native pack state. The city does not copy or
hard-code them.

## PR babysitting and human-gate recovery

### Supported target-only PR watch

The official imported `ce-babysit-pr` skill is a post-publication watch for an
existing open GitHub pull request. It is GitHub-only and requires the host's
authenticated `gh` tooling plus a checkout that can read the target PR and
push only the authorized working branch when the official skill delegates an
approved fix. The city supports one named PR at a time:

```text
/ce-babysit-pr <PR number or URL>
```

The empty-argument current-branch form is also an upstream capability, but
using an explicit number or URL is the operator contract here. The default
is the skill's self-sustaining in-session watch. These target-only forms are
also supported when the host needs to select the execution mode:

```text
/ce-babysit-pr <PR number or URL> watch
/ce-babysit-pr <PR number or URL> checkpoint
```

`watch` keeps the detector and tick loop in session. `checkpoint` performs
one bounded tick, reports the current state, and pauses monitoring; re-run
the same target-only invocation for another tick. Do not run a second polling
process or copy the skill into this repository.

The official result vocabulary is intentionally preserved:

| Result or residual | Meaning |
| --- | --- |
| `looks-ready` | GitHub reports certain `MERGEABLE` and `CLEAN`, checks and feedback are settled, and the cooling-off rules hold. The report says "your call", not approval. |
| `cautiously looks ready` | An incomplete review lifecycle reached its bounded stale path; this is still not reviewer approval. |
| `blocked-external-drained` | A fork PR's checks still await maintainer approval after the bounded review drain. |
| `needs-human` | A typed review or CI decision, or an unresolved semantic conflict, remains parked. |
| `blocked-failing` | A dispatched check remains terminally failed and is an actionable blocker. |
| `terminal` (`MERGED` or `CLOSED`) | GitHub reports that the PR is no longer open. |
| `budget exhausted` | The active watch budget or its wall-clock backstop ended the run. |
| `paused` | Checkpoint mode ended the one-tick run with monitoring paused. |

`needs-human` and `blocked-failing` are standing residuals while an
in-session watch continues; they are never success-shaped fallbacks. A
failed check remains visible as `blocked-failing`, and an operator
cancellation or checkpoint is reported as a paused handback. The city does
not provide a stack-wide or merge-capable babysitting invocation, automatic
approval, merge, or force-push. Human owners retain all approval and merge
decisions.

Observe the native state without recording private payloads:

```text
gc status
gc bd gate list --json
gc bd gate show <gate-id> --json
gc bd gate resolve <gate-id>
```

For the external d2b rig, publication still persists and re-reads
`metadata.target=v3` and `metadata.merge_strategy=pr`. This city-source
documentation change is delivered to `main` through a pull request.

### Native human-gate orders

The selected Gas City core schedules both human-gate recovery orders as native
supervisor exec orders. The existing mechanical `gate-sweep` remains
composed, but it does not replace these human-gate orders.

| Order | Native behavior |
| --- | --- |
| `notify-on-human-gate-creation` | Runs on `bead.created`, re-fetches the bead, and handles only an open `await_type=human` gate. The addressee is selected from `assignee`, then `gc.deferred_assignee`, then `GC_ESCALATION_RECIPIENT` (default `human`). It sends through `gc mail send --notify` at most once per gate. |
| `renudge-stale-human-gates` | Runs as a `5m` cooldown sweep across the city and rigs. It re-fetches open human gates after `GC_STALE_GATE_THRESHOLD` (default `1h`) and re-notifies a gate no more often than `GC_STALE_GATE_RENUDGE_INTERVAL` (default `1h`). |

Both scripts require `jq` on `PATH`. A successful send advances the
per-gate deduplication timestamp only after delivery. A failed send exits
non-zero, remains visible to the supervisor, and does not advance that
timestamp, so a later sweep can retry it. Resolving the gate removes it from
the open-gate set and stops further stale reminders. The creation order's
lookback retry is opportunistic; the stale sweep is the durable backstop for
an open gate.

Native Beads owns the gate record and native pack state owns the dedup ledgers
under runtime state. After a normal supervisor restart and reconciliation,
the same durable gate is eligible for the same orders without a replacement
watcher, duplicate scheduler, or duplicate notification inside the applicable
interval.

The selected upstream defaults and host-local override names are:

| Override | Default | Applies to |
| --- | --- | --- |
| `GC_NOTIFY_GATE_LOOKBACK` | `5m` | Creation-event lookback. |
| `GC_NOTIFY_GATE_RETENTION` | `1h` | Creation-notification dedup retention. |
| `GC_STALE_GATE_THRESHOLD` | `1h` | Time a gate must remain open before its first re-nudge. |
| `GC_STALE_GATE_RENUDGE_INTERVAL` | `1h` | Minimum time between stale-gate re-nudges. |
| `GC_STALE_GATE_STATE_RETENTION` | `24h` | Stale-gate dedup-state retention. |
| `GC_ESCALATION_RECIPIENT` | `human` | Fallback addressee. |

Override values, recipient mappings, gate identifiers, notification bodies,
and runtime paths belong to the host and must not be committed here.

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
publication.

## Stop or unregister

Stop the city's sessions with native Gas City:

```text
gc stop
```

The city remains registered. Use `gc unregister <city-path>` only when
decommissioning or moving that exact city. Do not add a custom shutdown hook
or host lifecycle service.
