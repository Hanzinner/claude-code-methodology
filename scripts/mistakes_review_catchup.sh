#!/usr/bin/env bash
# Catch-up for mistakes_review.sh after weeks when the machine was off (cron does not catch up missed runs).
# @reboot + guard: the review log is older than 7 days -> run the review now.
# Log: MISTAKES_REVIEW_LOG (default ~/.claude/logs/mistakes-review.log), the same file the weekly cron line writes to.
# Cron: @reboot sleep 300 && <dir>/mistakes_review_catchup.sh
set -uo pipefail
HERE=$(dirname "$(readlink -f "$0")")
LOG="${MISTAKES_REVIEW_LOG:-$HOME/.claude/logs/mistakes-review.log}"
mkdir -p "$(dirname "$LOG")"
last=$(stat -c %Y "$LOG" 2>/dev/null || echo 0)
if (( $(date +%s) - last > 7*86400 )); then
    echo "$(date -Iseconds) CATCHUP: log older than 7 days - running the missed weekly review" >> "$LOG"
    "${MISTAKES_REVIEW:-$HERE/mistakes_review.sh}" >> "$LOG" 2>&1
fi
