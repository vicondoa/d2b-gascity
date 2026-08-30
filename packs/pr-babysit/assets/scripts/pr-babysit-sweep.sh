#!/usr/bin/env bash

set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
pack_dir="${GC_PACK_DIR:-$(CDPATH= cd -- "$script_dir/../.." && pwd -P)}"
packs_root="$(CDPATH= cd -- "$pack_dir/.." && pwd -P)"
state_runner="${PR_BABYSIT_STATE_RUNNER:-$packs_root/core-city/commands/pr-babysit/run.sh}"
rig="${GC_RIG:-}"
limit="${PR_BABYSIT_SWEEP_LIMIT:-4}"

exec "$state_runner" sweep --rig "$rig" --limit "$limit" --json
