#!/usr/bin/env bash

set -euo pipefail

pack_dir="${GC_PACK_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
base="${MODEL_TIERS_BASE:-$pack_dir/model-tiers.base.toml}"
city="${1:-city.toml}"

if [ ! -f "$base" ]; then
  echo "gen-model-tiers: base map not found: $base" >&2
  exit 1
fi
if [ ! -f "$city" ]; then
  echo "gen-model-tiers: city file not found: $city" >&2
  exit 1
fi

mapfile -t rigs < <(
  awk '
    /^\[\[rigs\]\][[:space:]]*$/ { in_rig = 1; next }
    /^\[/ { in_rig = 0 }
    in_rig && /^[[:space:]]*name[[:space:]]*=/ {
      value = $0
      sub(/^[^=]*=[[:space:]]*"/, "", value)
      sub(/".*$/, "", value)
      print value
      in_rig = 0
    }
  ' "$city"
)

if [ "${#rigs[@]}" -eq 0 ]; then
  echo "gen-model-tiers: no rigs found in $city" >&2
  exit 1
fi

printf '# Generated from packs/core-city/model-tiers.base.toml.\n'
printf '# Regenerate from the city directory with: gc core-city gen-model-tiers city.toml\n\n'

while IFS='=' read -r role tier; do
  role="$(printf '%s' "$role" | tr -d '[:space:]')"
  tier="$(printf '%s' "$tier" | tr -d '[:space:]"')"
  [ -n "$role" ] || continue
  case "$tier" in
    deep-thinker | reviewer | solid-worker | fast-worker) ;;
    *)
      echo "gen-model-tiers: unknown tier for $role: $tier" >&2
      exit 1
      ;;
  esac
  case "$role:$tier" in
    *[!A-Za-z0-9._:-]*)
      echo "gen-model-tiers: invalid role or tier: $role=$tier" >&2
      exit 1
      ;;
  esac
  for rig in "${rigs[@]}"; do
    case "$rig" in
      *[!A-Za-z0-9._-]*)
        echo "gen-model-tiers: invalid rig name: $rig" >&2
        exit 1
        ;;
    esac
    if [ "${wrote_patch:-0}" = "1" ]; then
      printf '\n'
    fi
    printf '[[patches.agent]]\n'
    printf 'dir = "%s"\n' "$rig"
    printf 'name = "%s"\n' "$role"
    printf 'provider = "%s"\n' "$tier"
    wrote_patch=1
  done
done < <(
  grep -E '^[A-Za-z][A-Za-z0-9._-]*[[:space:]]*=[[:space:]]*"[A-Za-z0-9._-]+"' "$base"
)

if [ "${wrote_patch:-0}" != "1" ]; then
  echo "gen-model-tiers: no valid role assignments found in $base" >&2
  exit 1
fi
