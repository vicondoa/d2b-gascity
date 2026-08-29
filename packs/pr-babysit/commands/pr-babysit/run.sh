#!/usr/bin/env bash

set -euo pipefail

command_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python3}" "$command_dir/../../assets/scripts/pr-babysit-state.py" "$@"
