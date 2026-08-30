# Security

## Repository status and source boundary

This is private infrastructure. Do not disclose repository contents,
deployment details, credentials, or security reports publicly. Report a
suspected vulnerability through the repository's access-controlled
maintainer or security channel.

The only active city root is `cities/d2b-gascity`. This repository must not
contain a repository-local d2b checkout, bind mount, submodule, copied product
tree, or committed rig path. The external checkout is a host-owned source
bound through native `gc rig add`; only the live `.gc/site.toml` may contain
that path. Native Gas City owns city registration, imported services,
sessions, retry, stop, and persistent per-user lifecycle.

The `gc`, `copilot`, optional `codex`, `gh`, and ingress binaries are supplied
by the host or the separate private `vicondoa/gascity.nix` distribution. The
host supplies supervisor configuration, authorities, addresses, credentials,
identifiers, mappings, bindings, launchers, mounts, and runtime state. Keep
those values outside this repository.

## Trust boundaries

- Any public ingress is host-owned and outbound-only. Keep home-router inbound
  ports closed and protect the dashboard with the host's access policy.
- The official Discord pack owns three imported services under
  `.gc/services/discord`: public `discord-interactions`,
  tenant/access-policy protected `discord-admin`, and private
  `discord-gateway`. The city authors no Discord service, relay, wrapper, or
  replacement lifecycle.
- The signed Interactions endpoint is
  `/v0/discord/interactions`. The tenant admin surface reports setup and
  status without exposing token values and must remain behind the tenant
  access policy. The gateway receives private inbound DM and guild traffic
  and must not be exposed publicly.
- Discord app imports enforce application identity and configured
  guild/channel/role allowlists. Token material is host-owned, mode `0600`,
  and may be streamed through `/dev/stdin`; it must never be stored here.
- Launcher and ambient room features require Discord's Message Content
  Intent. Without that privileged intent, unmentioned guild content is not a
  reliable input.
- Normal agent output is private until an explicit Discord publish or
  `reply-current` action. Bot-authored messages are ignored on inbound.
- The city uses stock `builtin:copilot` and exactly four documented tiers:
  `deep-thinker` is `gpt-5.6-sol` at medium effort with `long_context`;
  `reviewer` is `grok-4.6` at high effort with `long_context`;
  `solid-worker` is `gpt-5.6-luna` at max effort with `long_context`; and
  `fast-worker` is `gpt-5.6-luna` at medium effort with default context.
  Stock `builtin:codex` is an alternate provider only.
- Keep Copilot Requests, d2b publication credentials, and Discord app
  credentials separate. Never set `GH_TOKEN` from a Copilot token.
- Publication stamps and re-reads `merge_strategy=pr` plus the owning rig's
  publication target: `v3` for d2b and `main` for city-source. The handoff
  receipt's `target=<rig>/pr-babysit.pr-babysitter` is a routing target; the
  watch records `base_ref=v3` or `base_ref=main`, and the publication bead
  records `merge_strategy=pr`. The d2b Discord extension is product-only.
  Publication must refuse direct merges and never merge or force-push. Host
  branch protection for `v3` is defense-in-depth: it must require pull
  requests and apply to administrators, but this repository does not claim
  that the current host is already configured that way. Merge decisions remain
  human-owned.

### PR babysitting credentials and authority

The rig-imported `pr-babysit` pack is target-only. Its repair identity is
operator-attested with repository Contents write and Pull requests read only.
It must not have Pull requests write, merge or administration authority,
workflow-approval authority, or Copilot Requests authority. The agent cannot
introspect fine-grained permissions, so the operator attestation is the setup
boundary rather than an inferred permission check.

Keep publication credentials, repair GitHub credentials, Copilot Requests
credentials, and Discord app credentials separate. `GH_TOKEN` and
`GITHUB_TOKEN` must not reuse any Copilot token or token variable. Never print
or persist any of these credentials. The repair path fails closed when the
attestation is missing or when a GitHub token is coupled to a Copilot token.
Before repair, the operator must provide `PR_BABYSIT_VALIDATOR` as an
absolute, non-symlink, executable file and set
`PR_BABYSIT_VALIDATOR_ATTESTED=credential-isolated-v1`. It must run
`make check` in a credential- and network-isolated environment. A missing
validator blocks repair, as do an invalid or failed validator. There is no
direct-make fallback.

The repair path uses only the existing PR head and normal push. Version 1 does
not use `update-branch`; `BEHIND`, dirty, conflicting, stale-head, unknown
capability, and ambiguous push evidence become human blockers. An ambiguous
push records `ambiguous-outcome` and is never retried. The agent never merges,
force-pushes (including `--force-with-lease`), performs a raw rebase, approves
workflows, creates a replacement PR, or changes another target. A
`merge-ready` result is a handoff, not human merge authorization. No service
change, daemon, webhook, relay, custom provider, or separate custom
publication machinery is introduced. Repairs are same-repository-only:
`head_repository` must equal the verified `owner/repository`. Fork or
cross-repository PRs are human blockers in v1 and receive no autonomous
repair.

The deterministic state CLI is city-scoped at `gc core-city pr-babysit
<action>`. Its wrapper accepts only the sibling helper under
`packs/pr-babysit/assets/scripts/`, verifies that the helper is executable,
and rejects symlinks or paths resolving outside the expected packs root.
The rig-imported pack is not imported city-wide and does not expose a second
command entrypoint.

### PR babysitting rollout

d2b is enabled first. The `city-source` rig remains suspended-on-start and
must not be enabled for live repair until the U8 disposable d2b acceptance
passes. Static and native credential-free tests cover both d2b/`v3` and
city-source/`main` without mutating GitHub. Live authenticated acceptance
evidence stays private and redacted; only safe pass/fail results may be shared.
No live U8 acceptance is claimed by this source tree.

## Human-only clean reset

Reset is a destructive operator action, not an agent or automated service
responsibility. Follow the full ordered runbook in
[docs/operations.md](docs/operations.md). The security gates are:

1. Make a private, redacted preflight inventory of active work, sessions,
   worktrees, branches, pending requests, and recovery metadata. Inventory
   Discord apps and app owners, guild/channel/role allowlists, channel and
   rig maps, room and DM bindings, launchers, and service exposure. Record
   counts and safe labels only; never copy identifiers, tokens, prompts, or
   payloads into this repository.
2. Stop and unregister the old root city before selecting or initializing
   the nested city. Confirm that root and nested city definitions are never
   active together.
3. Confirm the d2b bind-mount source and that no process or worktree is
   using it. Unmount the bind mount only. Never recursively delete the mount
   source or treat an unmount as checkout deletion.
4. Preserve the recorded external checkout, remotes, branches, open pull
   requests, and its product-local `.beads/`, `.gitignore`, and agent hooks.
   Remove only confirmed old root-city `.gc`, `.beads`, session, and worktree
   paths; cleanup must not traverse the external checkout.
5. Set host-local `GC_CITY_PATH` to `cities/d2b-gascity`, initialize from
   that nested directory with
   `gc init --file city.toml --preserve-existing --no-start .`, and bind the
   verified checkout with `gc rig add`.
6. Re-import Discord through native commands with stdin token input,
   least-privilege permissions, guild/channel/role allowlists, and the
   service exposure boundaries above. Keep Copilot Requests, publication,
   and Discord credentials separate.

## Capability boundaries

The official Discord pack supports signed Interactions, the guild-scoped
`/gc fix` command and modal submission, plain message bodies, exact chat
bindings, managed launcher threads, and explicit workflow publication. It
does not provide general buttons, select menus, context menus, attachment
ingestion or publication, embeds, reactions, presence controls, or arbitrary
slash commands. Do not add a city-owned implementation for those gaps.

## Protected data

Never commit or attach:

- credentials, tokens, keys, cookies, password hashes, or credential paths;
- private host values, authorities, addresses, users, channels, roles, maps,
  bindings, launchers, or hashes;
- `.gc`, `.beads`, Dolt databases, worktrees, sessions, caches, sockets,
  reports, logs, service dumps, or copied runtime state;
- materialized imported pack binaries or runtime state;
- live prompts, model responses, private pull-request payloads, or
  unredacted logs.

Generic placeholders and `127.0.0.1` in topology tests are acceptable.
File permissions and `.gitignore` do not replace staged-file and diff review.

## Reporting guidance

Use a redacted reproduction with the affected revision, safe counts or
timings, and pass or fail results. Remove credentials, private authorities,
host paths, identifiers, prompts, responses, and payloads before sharing.
Do not copy host state into the portable city.

## Installation boundary

Install the runtime, configure Copilot CLI, optionally configure Codex, and
configure host ingress through the private `vicondoa/gascity.nix` repository
or another compatible host source. Keep supervisor configuration, Discord app
credentials, and publication credentials outside this repository. Do not
duplicate host module details or embed host values here.
