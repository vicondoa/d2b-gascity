# Agent rules for d2b-gascity

## Repository boundary

This is a private infrastructure repository for one Gas City city and one
`vicondoa/d2b` rig based on branch `v3`. It is not a copy of the d2b product
repository and must not acquire unrelated d2b product code or full d2b
history.

The plan in `docs/plans/` is the authority for this extraction. Do not edit
the plan to record progress. Keep progress in Git status, commits, and
handoffs.

## Privacy boundary

Never commit or publish:

- private host values, authorities, addresses, user or channel identifiers,
  or host configuration;
- credentials, tokens, keys, cookies, password hashes, or credential paths;
- `.gc`, `.beads`, Dolt, database, worktree, session, or other runtime state;
- reports, service dumps, sockets, logs with private content, or copied
  prototype state;
- live prompts, model responses, or private pull-request payloads.

Generic placeholders, planted non-sensitive prompts, and the literal
`127.0.0.1` topology are allowed. `.gitignore` reduces accidents but does
not replace a staged-file and diff review.

## Change rules

- Make one logical change per commit.
- Keep ownership and merge decisions with a human.
- Use ASCII hyphens only. Do not add typographic dash characters.
- Preserve Apache-2.0 licensing for local content and preserve upstream
  notices for imported content.
- Prefer the smallest validation that proves the changed contract. Redact
  all evidence before storing or sharing it.

## Model and workflow rules

- Planning and primary review use Grok `grok-4.6` with `high` effort and
  `long_context`.
- Coding uses Luna with `max` effort.
- Review fallback to Luna is allowed only when Grok is explicitly unsupported
  or unavailable.
- This standalone repository does not use Speckit, the d2b panel, d2b
  signoff, d2b wave or delivery sequencing, or d2b pinning-hardening
  workflows.

Do not add a second Gas City lifecycle owner or invent a custom relay
service merely to work around a missing proof. The planned ingress relay is
separate deployment infrastructure and must not carry private values in
source. Follow the plan's stop conditions and record blockers without
weakening them.
