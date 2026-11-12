#!/usr/bin/env bash
# setup-git-guard.sh - put the git-guard wrapper in front of the real git. NOT run by default: the installer calls it only on an
# explicit flag. Idempotent; prints every change; --dry-run changes nothing.
#
# What it changes (user scope, no root needed):
#   1. creates a symlink  <DIR>/git -> <install dir>/bin/git-guard   (DIR default: ~/.local/bin; created if missing)
#   2. only with --rc-file FILE: appends a marked block to FILE that puts DIR first in PATH
#      (needed when DIR is not already before the real git in PATH; the script says so)
# Why a symlink in a PATH directory and not a replaced /usr/bin/git: the wrapper finds the real git by walking PATH and skipping
# itself, so the real git stays untouched, and removing the symlink restores the old behaviour at once. The wrapper only protects
# callers whose PATH has DIR before the real git: a shell, Claude Code's Bash tool, hooks and cron jobs started from it. A job with its
# own PATH (cron without PATH=...) bypasses the wrapper - add DIR to that crontab's PATH line.
# --system: DIR=/usr/local/bin for every user of the machine (needs root).
#
#   setup-git-guard.sh [--dir DIR] [--rc-file FILE] [--system] [--uninstall] [--dry-run]
# exit: 0 ok · 2 usage/refused · 5 --system without root
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
GUARD=$(readlink -f "$HERE/../bin/git-guard")
dir="$HOME/.local/bin"; rc=""; dry=0; un=0; system=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir) dir=${2:?--dir needs a folder}; shift 2 ;;
        --rc-file) rc=${2:?--rc-file needs a file}; shift 2 ;;
        --system) system=1; dir=/usr/local/bin; shift ;;
        --uninstall) un=1; shift ;;
        --dry-run) dry=1; shift ;;
        -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
        *) echo "unknown flag $1 (see --help)" >&2; exit 2 ;;
    esac
done
if (( system )) && (( ! dry )) && [[ "$(id -u)" != 0 ]]; then echo "setup-git-guard --system must run as root (it writes into /usr/local/bin)" >&2; exit 5; fi
[[ -x "$GUARD" ]] || { echo "cannot find $GUARD" >&2; exit 2; }
do_() { echo "  + $*"; (( dry )) || "$@"; }
(( dry )) && echo "(dry run: nothing is changed)"
link="$dir/git"
MARK_B="# >>> ccm git-guard >>>"; MARK_E="# <<< ccm git-guard <<<"

if (( un )); then
    if [[ -L "$link" && "$(readlink -f "$link")" == "$GUARD" ]]; then do_ rm "$link"; else echo "  $link is not our symlink - not touching it"; fi
    if [[ -n "$rc" && -f "$rc" ]] && grep -qF "$MARK_B" "$rc"; then
        echo "  + remove the marked block from $rc"
        (( dry )) || { tmp=$(mktemp); sed "/$MARK_B/,/$MARK_E/d" "$rc" > "$tmp"; cat "$tmp" > "$rc"; rm -f "$tmp"; }
    fi
    echo "done"; exit 0
fi

# the real git, looked for WITHOUT our directory in PATH
clean_path=$(echo "$PATH" | tr ':' '\n' | grep -vxF "$dir" | paste -sd:)
real=$(PATH="$clean_path" command -v git || true)
[[ -n "$real" ]] || { echo "no real git found in PATH (without $dir) - install git first" >&2; exit 2; }
echo "real git: $real"

if [[ -e "$link" || -L "$link" ]]; then
    if [[ -L "$link" && "$(readlink -f "$link")" == "$GUARD" ]]; then echo "  $link already points to the guard - ok"
    else echo "$link already exists and is not our symlink - refusing to overwrite it (move it away or use --dir)" >&2; exit 2; fi
else
    [[ -d "$dir" ]] || do_ mkdir -p "$dir"
    do_ ln -s "$GUARD" "$link"
fi

# is DIR before the real git in PATH of this shell?
pos() { echo "$PATH" | tr ':' '\n' | grep -nxF "$1" | head -1 | cut -d: -f1; }
pd=$(pos "$dir" || true); pr=$(pos "$(dirname "$real")" || true)
if [[ -n "$pd" && -n "$pr" && "$pd" -lt "$pr" ]]; then
    echo "  $dir is already before $(dirname "$real") in PATH - the wrapper is active in new shells"
else
    line="export PATH=\"$dir:\$PATH\""
    if [[ -n "$rc" ]]; then
        if [[ -f "$rc" ]] && grep -qF "$MARK_B" "$rc"; then echo "  $rc already has the block - ok"
        else
            echo "  + append to $rc:  $line"
            (( dry )) || printf '\n%s\n%s\n%s\n' "$MARK_B" "$line" "$MARK_E" >> "$rc"
        fi
    else
        echo "  $dir is NOT before $(dirname "$real") in PATH. Add this to your shell startup file (or rerun with --rc-file ~/.bashrc):"
        echo "      $line"
    fi
fi
echo "check:  PATH=\"$dir:\$PATH\" type -a git   (the first entry must be $link)"
echo "done"
