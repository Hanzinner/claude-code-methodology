#!/usr/bin/env bash
# prune_watchman_state.sh - weekly cleanup of the briefing watchman's own state files (per-session markers in
# ~/.claude/briefing-watchman) older than PRUNE_DAYS.
# DELETES, therefore OFF BY DEFAULT: it does nothing unless CCM_PRUNE_WATCHMAN_STATE=1 (methodology.conf or env) or --yes.
# --dry-run lists what would go, deletes nothing, works without the flag. These are only markers (which hint was shown
# in which session), not user data: losing one means one hint is shown again.
# Settings: CCM_PRUNE_DAYS (default 30), WATCHMAN_STATE_DIR (default ~/.claude/briefing-watchman).
# Cron: 30 12 * * 0
set -uo pipefail
HERE=$(dirname "$(readlink -f "$0")")
eval "$(python3 "$HERE/../lib/ccm_conf.py" --shell)"
DIR=${WATCHMAN_STATE_DIR:-$HOME/.claude/briefing-watchman}
DAYS=${CCM_PRUNE_DAYS:-30}
[[ -d "$DIR" ]] || exit 0
mode=off
[[ "${CCM_PRUNE_WATCHMAN_STATE:-0}" == 1 || "${1:-}" == --yes ]] && mode=delete
[[ "${1:-}" == --dry-run ]] && mode=dry
if [[ $mode == off ]]; then echo "prune_watchman_state: disabled (set CCM_PRUNE_WATCHMAN_STATE=1 or pass --yes); nothing deleted"; exit 0; fi
n=$(find "$DIR" -type f -mtime +"$DAYS" | wc -l)
if [[ $mode == dry ]]; then find "$DIR" -type f -mtime +"$DAYS"; echo "prune_watchman_state: dry run, $n file(s) older than $DAYS days"; exit 0; fi
find "$DIR" -type f -mtime +"$DAYS" -delete 2>/dev/null
echo "$(date '+%F %T') prune_watchman_state: deleted $n file(s) older than $DAYS days from $DIR"
