{{ define "command-glossary" -}}
## Gas City command help

Use `gc --help` or `gc <command> --help` before guessing command syntax.
Common entry points are `gc status`, `gc doctor`, `gc bd`, `gc mail`,
`gc formula`, `gc service`, and `gc rig`.

The city-scoped PR babysitter command is
`gc core-city pr-babysit`. Its canonical read-only watch commands are
`gc core-city pr-babysit show --watch-id <watch-id> --json`,
`gc core-city pr-babysit checkpoint --watch-id <watch-id>
--expected-generation <generation> --expected-head-sha <head-sha>
--observed-head-sha <observed-head-sha> --observed-at <RFC3339>
--next-snapshot-at <RFC3339> --to <watching|waiting|merge-ready|blocked|terminal>
--merge-ready-evidence '<JSON>' --json`.
The mutating action-scoped repair dispatch is
`gc core-city pr-babysit dispatch-repair --watch-id <watch-id>
--action-kind <ci|review> --fingerprint <fingerprint>
--generation <generation> --head-sha <head-sha>
--addressed-thread-ids <ids> --json`. A checkpoint requires all listed
identity and timing flags. `dispatch-repair` requires a complete handoff receipt:
`handoff_verified=true`, the self watch ID, the binding-qualified target, and
the publication bead.
When `pr-snapshot` reports an invalid pull-request template, use
`gc core-city pr-babysit dispatch-template-remediation --watch-id <watch-id>
--generation <generation> --head-sha <head-sha>
--template-errors <comma-separated-safe-error-codes> --json`. It creates one
deterministic remediation bead, makes it block the watch, and routes it to the
owning rig's publisher.
After a confirmed review repair, use
`gc core-city pr-babysit acknowledge-dispositions --watch-id <watch-id>
--action-kind <pending-action-kind> --generation <fresh-show-generation>
--head-sha <fresh-snapshot-head-sha>
--addressed-thread-ids <pending-addressed-ids> --json` only after every
current-snapshot `pr-snapshot mark` succeeds. A caller does not request
`exhausted`; budget expiry transitions to it automatically.
{{- end }}
