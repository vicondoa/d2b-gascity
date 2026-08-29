#!/bin/sh
set -eu

COMMIT='33d9bd92689d60580e732890f94466e5793385b1'
MARKER='.gascity-vendored-commit'
SKILL_FILES='
SKILL.md
references/branch-currency.md
references/envelope.md
references/pipeline.md
references/report.md
references/settle.md
references/setup.md
references/tick.md
references/watch-loop.md
scripts/pr-snapshot
'

blocker() {
    printf 'project-copilot-skill: BLOCKER: %s\n' "$*" >&2
    exit 1
}

workdir=${GC_DIR:-}
[ -n "$workdir" ] || blocker 'GC_DIR is not set'
case "$workdir" in
    /*) ;;
    *) blocker 'GC_DIR is not an absolute path' ;;
esac
[ -d "$workdir" ] || blocker "GC_DIR does not exist: $workdir"
workdir=$(CDPATH= cd "$workdir" && pwd -P) ||
    blocker 'cannot resolve GC_DIR'
rig_root=${GC_RIG_ROOT:-}
[ -n "$rig_root" ] || blocker 'GC_RIG_ROOT is not set'
case "$rig_root" in
    /*) ;;
    *) blocker 'GC_RIG_ROOT is not an absolute path' ;;
esac
[ -d "$rig_root" ] || blocker "GC_RIG_ROOT does not exist: $rig_root"
rig_root=$(CDPATH= cd "$rig_root" && pwd -P) ||
    blocker 'cannot resolve GC_RIG_ROOT'
[ "$workdir" = "$rig_root/.gc/agents/pr-babysitter" ] ||
    blocker 'GC_DIR is not the configured rig-local babysitter workdir'

script_path=$0
case "$script_path" in
    /*) ;;
    *) script_path=$(CDPATH= cd "$(dirname "$script_path")" && pwd -P)/$(basename "$script_path") ;;
esac
script_dir=$(CDPATH= cd "$(dirname "$script_path")" && pwd -P) ||
    blocker 'cannot resolve setup script directory'
pack_root=$(CDPATH= cd "$script_dir/../.." && pwd -P) ||
    blocker 'cannot resolve pack root'
source_root="$pack_root/skills/pr-babysit"
[ -d "$source_root" ] || blocker "vendored skill is absent: $source_root"
case "$workdir/" in
    "$pack_root/"*) blocker 'GC_DIR overlaps the pack source' ;;
esac

verify_files() {
    root=$1
    for relative in $SKILL_FILES; do
        [ -f "$root/$relative" ] ||
            blocker "vendored skill file is absent: $root/$relative"
    done
}

verify_files "$source_root"

ensure_directory() {
    path=$1
    if [ -L "$path" ]; then
        blocker "refusing symlinked directory: $path"
    fi
    if [ -e "$path" ] && [ ! -d "$path" ]; then
        blocker "refusing non-directory path: $path"
    fi
    mkdir -p "$path" || blocker "cannot create directory: $path"
    [ ! -L "$path" ] || blocker "refusing symlinked directory: $path"
}

github_parent="$workdir/.github/skills"
agents_parent="$workdir/.agents/skills"
ensure_directory "$workdir/.github"
ensure_directory "$github_parent"
ensure_directory "$workdir/.agents"
ensure_directory "$agents_parent"

stage_github_candidate="$github_parent/.pr-babysit.stage.$$"
stage_agents_candidate="$agents_parent/.pr-babysit.stage.$$"
backup_github_candidate="$github_parent/.pr-babysit.backup.$$"
backup_agents_candidate="$agents_parent/.pr-babysit.backup.$$"
stage_github=
stage_agents=
backup_github=
backup_agents=
cleanup() {
    [ -z "$stage_github" ] || rm -rf "$stage_github"
    [ -z "$stage_agents" ] || rm -rf "$stage_agents"
    [ -z "$backup_github" ] || rm -rf "$backup_github"
    [ -z "$backup_agents" ] || rm -rf "$backup_agents"
}
trap cleanup EXIT
trap 'cleanup; exit 1' HUP INT TERM

stage_projection() {
    candidate=$1
    [ ! -e "$candidate" ] && [ ! -L "$candidate" ] ||
        blocker "staging path already exists: $candidate"
    stage=$candidate
    mkdir "$stage" || blocker "cannot create staging directory: $stage"
    if [ "$candidate" = "$stage_github_candidate" ]; then
        stage_github=$stage
    else
        stage_agents=$stage
    fi
    cp -R "$source_root/." "$stage/" ||
        blocker "cannot copy vendored skill to $stage"
    verify_files "$stage"
    marker_tmp="$stage/$MARKER.$$"
    printf '%s\n' "$COMMIT" >"$marker_tmp" ||
        blocker "cannot write projection marker"
    mv "$marker_tmp" "$stage/$MARKER" ||
        blocker "cannot install projection marker"
    marker_value=$(cat "$stage/$MARKER") ||
        blocker "cannot read projection marker"
    [ "$marker_value" = "$COMMIT" ] ||
        blocker "projection marker verification failed"
}

stage_projection "$stage_github_candidate"
stage_projection "$stage_agents_candidate"

replace_projection() {
    target=$1
    stage=$2
    backup_candidate=$3
    moved=0
    if [ -e "$target" ] || [ -L "$target" ]; then
        [ ! -e "$backup_candidate" ] && [ ! -L "$backup_candidate" ] ||
            blocker "backup path already exists: $backup_candidate"
        mv "$target" "$backup_candidate" ||
            blocker "cannot preserve existing projection: $target"
        backup=$backup_candidate
        if [ "$backup_candidate" = "$backup_github_candidate" ]; then
            backup_github=$backup
        else
            backup_agents=$backup
        fi
        moved=1
    fi
    if ! mv "$stage" "$target"; then
        if [ "$moved" = 1 ]; then
            mv "$backup_candidate" "$target" || true
        fi
        blocker "cannot install projection: $target"
    fi
    if [ "$moved" = 1 ]; then
        rm -rf "$backup_candidate" ||
            blocker "cannot remove old projection: $backup_candidate"
        if [ "$backup_candidate" = "$backup_github" ]; then
            backup_github=
        else
            backup_agents=
        fi
    fi
    if [ "$stage" = "$stage_github" ]; then
        stage_github=
    else
        stage_agents=
    fi
}

replace_projection \
    "$github_parent/pr-babysit" \
    "$stage_github_candidate" \
    "$backup_github_candidate"
replace_projection \
    "$agents_parent/pr-babysit" \
    "$stage_agents_candidate" \
    "$backup_agents_candidate"

printf 'project-copilot-skill: projected pr-babysit %s into %s and %s\n' \
    "$COMMIT" "$github_parent" "$agents_parent"
