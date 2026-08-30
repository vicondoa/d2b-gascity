#!/usr/bin/env bash

set -euo pipefail

fail() {
  printf 'pr-babysit: %s\n' "$1" >&2
  exit 1
}

script_dir="$(
  CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null &&
    pwd -P
)" || fail "could not resolve command directory"
core_pack_dir="$(
  CDPATH= cd -- "$script_dir/../.." 2>/dev/null &&
    pwd -P
)" || fail "could not resolve core-city pack directory"
pack_dir="${GC_PACK_DIR:-$core_pack_dir}"

case "$pack_dir" in
  /*) ;;
  *) fail "pack directory is not absolute" ;;
esac
pack_dir="$(
  CDPATH= cd -- "$pack_dir" 2>/dev/null &&
    pwd -P
)" || fail "could not resolve pack directory"
if [ "$pack_dir" != "$core_pack_dir" ]; then
  fail "command wrapper is outside the expected core-city pack"
fi

packs_root="$(
  CDPATH= cd -- "$pack_dir/.." 2>/dev/null &&
    pwd -P
)" || fail "could not resolve packs root"
if [ "$(basename "$pack_dir")" != "core-city" ] ||
  [ "$(basename "$packs_root")" != "packs" ]; then
  fail "command wrapper is outside the expected packs root"
fi

helper="$packs_root/pr-babysit/assets/scripts/pr-babysit-state.py"
if [ ! -f "$helper" ]; then
  fail "helper not found: packs/pr-babysit/assets/scripts/pr-babysit-state.py"
fi
if [ ! -x "$helper" ]; then
  fail "helper is not executable: packs/pr-babysit/assets/scripts/pr-babysit-state.py"
fi

packs_root_real="$(
  readlink -f -- "$packs_root" 2>/dev/null
)" || fail "could not resolve expected packs root"
helper_real="$(
  readlink -f -- "$helper" 2>/dev/null
)" || fail "could not resolve helper"
expected_helper="$packs_root_real/pr-babysit/assets/scripts/pr-babysit-state.py"
if [ "$helper_real" != "$expected_helper" ]; then
  fail "helper resolves outside the expected packs root"
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --city | --rig)
      [ "$#" -ge 2 ] || fail "missing value for global scope flag: $1"
      shift 2
      ;;
    --city=* | --rig=*)
      shift
      ;;
    *)
      break
      ;;
  esac
done

exec "${PYTHON:-python3}" "$helper_real" "$@"
