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
# different inodes (a race). Nobody mv's the .lock. lib/ccm_lock.sh: flock, or where there is none (stock macOS, Git
# Bash) a mkdir lock that a dead writer does not keep (its pid is checked; older than 1 min = stale anyway).
# 30 s: on Windows every command is a new process and costs tens of ms, so 12 writers at once queue for seconds.
source "$_ib_here/../lib/ccm_lock.sh"
source "$_ib_here/../lib/ccm_compat.sh"   # ccm_owner/ccm_group/ccm_mode for ib_same_* below

# A rewritten inbox keeps the owner and mode of the old one (mktemp makes 0600): --reference where chmod/chown have it,
# else the values read by BSD stat (macOS has no --reference; there the copy silently stayed 0600). Never fails.
ib_same_owner() {   # ib_same_owner <reference> <file>
    if chown --version >/dev/null 2>&1; then chown --reference="$1" "$2" 2>/dev/null || true
    else chown "$(ccm_owner "$1"):$(ccm_group "$1")" "$2" 2>/dev/null || true; fi
}
ib_same_mode() {    # ib_same_mode <reference> <file>
    if chmod --version >/dev/null 2>&1; then chmod --reference="$1" "$2" 2>/dev/null || true
    else chmod "$(ccm_mode "$1")" "$2" 2>/dev/null || true; fi
}
lock_inbox() {   # lock_inbox <inbox> <tool name for messages>
    ccm_lock 9 "$1.lock" 30 1 || { echo "$2: lock timeout on $1" >&2; exit 3; }
}

# A rename into place that outlives a moment's refusal. Windows refuses a rename onto (or from) a file another
# process holds open - an antivirus scanning the file just written, the search indexer, a reader - and it passes in a
# moment; under `set -e` a bare mv ended the script there (a letter lost, a .postXXXX left). ~5 s of tries; on Linux
# the first one succeeds. ib_mv_retry <from> <to> -> 0 moved, 1 still refused (the caller decides what is safe).
ib_mv_retry() {
    local i
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16; do
        mv -f "$1" "$2" 2>/dev/null && return 0
        sleep 0.3
    done
    mv -f "$1" "$2"
}
