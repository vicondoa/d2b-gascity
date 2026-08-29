{{ define "operational-awareness" -}}
## Operational awareness

Run `gc prime` after compaction, clearing context, or starting a new session.
Use the identity and assignment it reports; do not infer either from files,
directories, or unrelated beads.

At the start of each turn, run `gc mail check --inject` once. Assigned beads
and Gas City mail are durable control channels; session nudges are appropriate
for ephemeral coordination. Escalate ambiguous destructive, lifecycle,
publication, merge, or force-push requests instead of guessing authority.

Use one bounded health sweep rather than polling. Run `gc status` and
`gc doctor --json`, then escalate the evidence before restarting or repairing
city infrastructure. Use `bd dolt` lifecycle commands only under explicit
operator direction. Never delete Dolt or Gas City runtime data manually.
{{- end }}
