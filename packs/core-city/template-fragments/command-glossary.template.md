{{ define "command-glossary" -}}
## Gas City command help

Use `gc --help` or `gc <command> --help` before guessing command syntax.
Common entry points are `gc status`, `gc doctor`, `gc bd`, `gc mail`,
`gc formula`, `gc service`, and `gc rig`.

The rig-imported PR babysitter command is doubled by Pack routing:
`gc pr-babysit pr-babysit`. Its canonical read-only watch commands are
`gc pr-babysit pr-babysit show --watch-id <watch-id> --json` and
`gc pr-babysit pr-babysit checkpoint --watch-id <watch-id> --json`;
`dispatch-repair` is the only action-scoped repair dispatch.
{{- end }}
