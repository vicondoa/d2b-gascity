{{ define "command-glossary" -}}
## Gas City command help

Use `gc --help` or `gc <command> --help` before guessing command syntax.
Common entry points are `gc status`, `gc doctor`, `gc bd`, `gc mail`,
`gc formula`, `gc service`, and `gc rig`.

The rig-imported PR babysitter command is doubled by Pack routing:
`gc pr-babysit pr-babysit`. Its canonical read-only watch commands are
`gc pr-babysit pr-babysit show --watch-id <watch-id> --json`,
`gc pr-babysit pr-babysit checkpoint --watch-id <watch-id>
--expected-generation <generation> --expected-head-sha <head-sha>
--observed-head-sha <observed-head-sha> --observed-at <RFC3339>
--next-snapshot-at <RFC3339> --to <state> --json`, and
`gc pr-babysit pr-babysit dispatch-repair --watch-id <watch-id>
--action-kind <ci|review> --fingerprint <fingerprint>
--generation <generation> --head-sha <head-sha>
--addressed-thread-ids <ids> --json`. A checkpoint requires all listed
identity and timing flags; `dispatch-repair` is the only action-scoped repair
dispatch and requires a complete handoff receipt:
`handoff_verified=true`, the self watch ID, the binding-qualified target, and
the publication bead.
{{- end }}
