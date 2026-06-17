#!/usr/bin/env bash
# UserPromptSubmit hook — prepends the current time and the gap since the
# previous user message in this session. Helps the agent reason about
# temporal context (e.g. "was this immediate follow-up or a 3-day pause?").

CLAUDE_DIR="${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}"
TIMESTAMP_DIR="$CLAUDE_DIR/cache/prompt-timestamps"
mkdir -p "$TIMESTAMP_DIR"

input=$(cat)
session_id=$(echo "$input" | grep -oP '"session_id"\s*:\s*"\K[^"]+' | head -1)
[[ -z "$session_id" ]] && exit 0

TIMESTAMP_FILE="$TIMESTAMP_DIR/$session_id"
now=$(date +%s)
now_human=$(date '+%Y-%m-%d %H:%M %Z')

gap_str=""
if [[ -f "$TIMESTAMP_FILE" ]]; then
    prev=$(cat "$TIMESTAMP_FILE" 2>/dev/null)
    if [[ -n "$prev" ]] && [[ "$prev" -eq "$prev" ]] 2>/dev/null; then
        diff=$((now - prev))
        if [[ "$diff" -lt 60 ]]; then
            gap_str="${diff}s"
        elif [[ "$diff" -lt 3600 ]]; then
            gap_str="$((diff / 60))m $((diff % 60))s"
        elif [[ "$diff" -lt 86400 ]]; then
            gap_str="$((diff / 3600))h $(( (diff % 3600) / 60 ))m"
        else
            gap_str="$((diff / 86400))d $(( (diff % 86400) / 3600 ))h"
        fi
    fi
fi

if [[ -n "$gap_str" ]]; then
    echo "[now: ${now_human} | gap since previous user message: ${gap_str}]"
else
    echo "[now: ${now_human}]"
fi

echo "$now" > "$TIMESTAMP_FILE"
exit 0
