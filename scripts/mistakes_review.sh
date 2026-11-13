#!/usr/bin/env bash
# mistakes_review.sh - weekly ping to the journal's keeper about OPEN entries in the mistakes journal.
# The point is a periodic review of PATTERNS (three of the same kind = a hole in the construction), not a notice of
# new entries. OPEN=0 -> full silence. Keeper (CCM_MISTAKES_KEEPER) empty -> no letter, only the log line.
# Entry: heading "## YYYY-MM-DD ..." (also "## [date]"), status: a line "**Status:** OPEN..." (also "**Статус:**").
# A "Was: OPEN" tail on a status line is history, not the current status.
# Cron: 35 12 * * 0 (weekly) + @reboot catch-up (mistakes_review_catchup.sh). Log line prefix: "mistakes-review:".
# Test overrides: MISTAKES_OVERRIDE. Test: tests/mistakes-review-test.sh
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
eval "$(python3 "$HERE/../lib/ccm_conf.py" --shell)"
MISTAKES="${MISTAKES_OVERRIDE:-$CCM_MISTAKES}"
KEEPER="${CCM_MISTAKES_KEEPER:-}"
POST="${CCM_INBOX_POST:-$HERE/inbox_post.sh}"
[[ -f "$MISTAKES" ]] || exit 0

open_titles=$(awk '
    /^## \[?[0-9]{4}-[0-9]{2}-[0-9]{2}/ { title=$0; sub(/^## /,"",title); next }
    /^\*\*(Status|Статус):\*\*/ { st=$0; sub(/(Was|Було):.*/,"",st); if (st ~ /OPEN/ && title != "") print "  · " title; title="" }
' "$MISTAKES")
open_n=$(printf '%s' "$open_titles" | grep -c '·' || true)
[[ "$open_n" -eq 0 ]] && exit 0

if [[ -n "$KEEPER" ]]; then
    entry="- [ ] [$(date +%Y-%m-%d)] **Mistakes review: ${open_n} open** - look for REPEATS, not single cases. Headings:
${open_titles}"
    "$POST" "$KEEPER" "$entry" >/dev/null
    echo "$(date -Iseconds) mistakes-review: ${open_n} OPEN -> letter to $KEEPER"
else
    echo "$(date -Iseconds) mistakes-review: ${open_n} OPEN (no keeper configured: CCM_MISTAKES_KEEPER)"
fi
