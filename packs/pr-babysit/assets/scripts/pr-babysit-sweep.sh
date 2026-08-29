#!/usr/bin/env bash

set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
pack_dir="${GC_PACK_DIR:-$(CDPATH= cd -- "$script_dir/../.." && pwd -P)}"
state_runner="${PR_BABYSIT_STATE_RUNNER:-$pack_dir/commands/pr-babysit/run.sh}"
rig="${GC_RIG:-}"

case "$rig" in
    d2b|city-source) ;;
    *)
        printf 'pr-babysit-sweep: invalid owning rig\n' >&2
        exit 1
        ;;
esac

limit="${PR_BABYSIT_SWEEP_LIMIT:-32}"
case "$limit" in
    ''|*[!0-9]*)
        printf 'pr-babysit-sweep: invalid sweep limit\n' >&2
        exit 1
        ;;
esac
if [ "$limit" -eq 0 ] || [ "$limit" -gt 100 ]; then
    printf 'pr-babysit-sweep: sweep limit is outside 1..100\n' >&2
    exit 1
fi

due_json="$("$state_runner" list-due --rig "$rig" --limit "$limit" --json)"
rows="$(
    printf '%s\n' "$due_json" |
        "${PYTHON:-python3}" -c '
import json
import re
import sys

try:
    payload = json.load(sys.stdin)
except json.JSONDecodeError as error:
    raise SystemExit(f"invalid list-due JSON: {error.msg}")

if not isinstance(payload, dict) or payload.get("ok") is not True:
    raise SystemExit("list-due did not return a successful result")
watches = payload.get("watches")
if not isinstance(watches, list):
    raise SystemExit("list-due returned an invalid watch list")
if len(watches) > int("'"$limit"'"):
    raise SystemExit("list-due exceeded the sweep limit")

watch_id_re = re.compile(r"^[a-z0-9][a-z0-9-]*$")
allowed_states = {"watching", "waiting"}
for watch in watches:
    if not isinstance(watch, dict):
        raise SystemExit("list-due returned an invalid watch")
    watch_id = watch.get("watch_id")
    metadata = watch.get("metadata")
    if (
        not isinstance(watch_id, str)
        or not watch_id_re.fullmatch(watch_id)
        or not isinstance(metadata, dict)
    ):
        raise SystemExit("list-due returned an unsafe watch")
    if (
        metadata.get("state") not in allowed_states
        or metadata.get("claim_status", "none") != "none"
        or metadata.get("action_kind", "")
        or metadata.get("action_fingerprint", "")
    ):
        raise SystemExit("list-due returned a non-routable watch")
    sys.stdout.write(watch_id + "\n")
'
)"

if [ "${PR_BABYSIT_GC_COMMAND+x}" = x ]; then
    gc_command_text=$PR_BABYSIT_GC_COMMAND
elif [ "${PR_BABYSIT_GC_BIN+x}" = x ]; then
    gc_command_text=$PR_BABYSIT_GC_BIN
elif [ "${GC_BIN+x}" = x ]; then
    gc_command_text=$GC_BIN
else
    gc_command_text=gc
fi
read -r -a gc_command <<< "$gc_command_text"
[ "${#gc_command[@]}" -gt 0 ] || {
    printf 'pr-babysit-sweep: Gas City command is unavailable\n' >&2
    exit 1
}

target="$rig/pr-babysit.pr-babysitter"
routed=0
mapfile -t watch_ids <<< "$rows"
for watch_id in "${watch_ids[@]}"; do
    [ -n "$watch_id" ] || continue
    "${gc_command[@]}" sling --nudge "$target" "$watch_id" \
        --no-formula --json >/dev/null
    routed=$((routed + 1))
done

printf '{"action":"sweep","ok":true,"rig":"%s","routed":%d}\n' \
    "$rig" "$routed"
