#!/usr/bin/env bash
# SessionStart hook — runs the memory curation script at most once per week.
# Silent if the memory is clean. On findings, injects the report into the
# session context so the agent can act on it (consolidate duplicates,
# delete stale facts, fix broken links).

set -euo pipefail

CLAUDE_DIR="${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}"
STAMP_DIR="$CLAUDE_DIR/cache"
STAMP="$STAMP_DIR/memory_curation_last"
SCRIPT="$CLAUDE_DIR/scripts/curate_memory.py"
INTERVAL_SECS=$((7 * 24 * 60 * 60))  # 7 days

mkdir -p "$STAMP_DIR"

[[ -f "$SCRIPT" ]] || exit 0

now=$(date +%s)
if [[ -f "$STAMP" ]]; then
    last=$(cat "$STAMP" 2>/dev/null || echo 0)
    age=$((now - last))
    if (( age < INTERVAL_SECS )); then
        exit 0
    fi
fi

set +e
output=$(python3 "$SCRIPT" 2>&1)
exit_code=$?
set -e

echo "$now" > "$STAMP"

if (( exit_code == 0 )); then
    exit 0
fi

context="[memory-curation] Weekly check found signals — review and clean up.

$output"

python3 -c '
import json, sys
ctx = sys.stdin.read()
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": ctx
    }
}))
' <<< "$context"
