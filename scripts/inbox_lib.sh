#!/usr/bin/env bash
# Shared helpers for inbox_post.sh / inbox_done.sh / inbox_wait.sh (sourced, never run).
# Sets AGENTS_ROOT from the settings (CCM_AGENTS_DIR); INBOX_AGENTS_ROOT overrides it (tests).
_ib_here="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
if [[ -f "$_ib_here/../lib/ccm_conf.py" ]]; then
    eval "$(python3 "$_ib_here/../lib/ccm_conf.py" --shell)"
fi
AGENTS_ROOT="${INBOX_AGENTS_ROOT:-${CCM_AGENTS_DIR:-$HOME/claude-projects/Agents}}"

# Section headers. The swarm template says "## New"; older inboxes may say "## Processed", "## Done" or Ukrainian
# "## Нові" / "## Оброблено". Whatever the file already has wins; a "candidates" variant is used when present.
find_new_hdr() {
    local h
    for h in "## New candidates" "## Нові кандидати" "## New" "## Нові"; do
        grep -qxF -- "$h" "$1" 2>/dev/null && { printf '%s\n' "$h"; return; }
    done
    printf '%s\n' "## New"
}
find_done_hdr() {
    local h
    for h in "## Processed" "## Done" "## Оброблено"; do
        grep -qxF -- "$h" "$1" 2>/dev/null && { printf '%s\n' "$h"; return; }
    done
    printf '%s\n' "## Processed"
}

# Lock a SEPARATE stable file, not the inbox itself: mv swaps the inbox's inode, so two writers could hold locks on
# different inodes (a race). Nobody mv's the .lock. Uses flock; without it (stock macOS) a mkdir spin-lock with
# stale-lock cleanup (a lock dir older than 60 s belongs to a dead writer).
lock_inbox() {   # lock_inbox <inbox> <tool name for messages>
    local inbox="$1" tool="$2" n=0
    if command -v flock >/dev/null 2>&1; then
        exec 9>>"${inbox}.lock"
        flock -w 15 9 || { echo "$tool: lock timeout on $inbox" >&2; exit 3; }
        return 0
    fi
    until mkdir "${inbox}.lock.d" 2>/dev/null; do
        if [[ -n "$(find "${inbox}.lock.d" -maxdepth 0 -mmin +1 2>/dev/null)" ]]; then rmdir "${inbox}.lock.d" 2>/dev/null; continue; fi
        n=$((n+1)); [[ $n -ge 150 ]] && { echo "$tool: lock timeout on $inbox" >&2; exit 3; }
        sleep 0.1
    done
    trap 'rmdir "'"${inbox}"'.lock.d" 2>/dev/null' EXIT
}
