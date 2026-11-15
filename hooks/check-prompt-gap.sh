#!/usr/bin/env bash
# UserPromptSubmit hook — prepends the current time, the time of the previous user message in this session and how
# long ago it was ("2 h ago": one unit, rounded). Helps the agent reason about temporal context ("an immediate
# follow-up or a 3-day pause?").
#
# The timestamps double as the PRESENCE signal (scripts/presence_check.py, the night memory consolidation): a prompt
# in the last minutes = the human is at the keyboard. So prompts that are NOT the human go to a machine/ subfolder —
# the gap line still works for them, presence doesn't see them:
#   - a session started by a script (CCM_MACHINE_SESSION=1 in its environment — e.g. stats_corrections.py);
#   - a system notice injected as a prompt (a background task finished: <task-notification>). Without this, presence
#     read "present" all night while agents worked, and the consolidation that waits for the human to be away never ran.
#
# Config: CCM_TIMEZONE (IANA name for the clock; empty = system), CCM_PROMPT_REMINDERS (a file; each non-empty,
# non-# line is printed on EVERY prompt — a fresh line each turn is not pushed out by a long context; use it for the one
# or two rules that drift, e.g. "end with the next step, don't offer a pause"; empty = none).

CLAUDE_DIR="${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}"
TIMESTAMP_DIR="$CLAUDE_DIR/cache/prompt-timestamps"
CONF="$(dirname "$(readlink -f "$0")")/../lib/ccm_conf.py"
cv() { python3 "$CONF" "$1" 2>/dev/null; }

input=$(cat)
session_id=$(printf '%s' "$input" | grep -oP '"session_id"\s*:\s*"\K[^"]+' | head -1)
[[ -z "$session_id" ]] && exit 0

dir="$TIMESTAMP_DIR"
if [[ -n "${CCM_MACHINE_SESSION:-}" ]] || printf '%s' "$input" | grep -qE 'task-notification|SYSTEM NOTIFICATION'; then
    dir="$TIMESTAMP_DIR/machine"
fi
mkdir -p "$dir"
TIMESTAMP_FILE="$dir/$session_id"

tz=$(cv CCM_TIMEZONE)
tdate() { if [[ -n "$tz" ]]; then TZ="$tz" date "$@"; else date "$@"; fi; }
now=$(date +%s)
now_human=$(tdate -d "@$now" '+%Y-%m-%d %H:%M %Z')

prev_line=""
if [[ -f "$TIMESTAMP_FILE" ]]; then
    prev=$(cat "$TIMESTAMP_FILE" 2>/dev/null)
    if [[ "$prev" =~ ^[0-9]+$ ]]; then
        diff=$((now - prev))
        if (( diff < 60 )); then ago="${diff} s ago"
        elif (( diff < 3600 )); then ago="$((diff / 60)) min ago"
        elif (( diff < 86400 )); then ago="$(( (diff + 1800) / 3600 )) h ago"
        else ago="$(( (diff + 43200) / 86400 )) d ago"
        fi
        prev_line="previous message: $(tdate -d "@$prev" '+%Y-%m-%d %H:%M') (${ago})"
    fi
fi

echo "[now: ${now_human} · ${prev_line:-first message of this session}]"
echo "$now" > "$TIMESTAMP_FILE"

rem=$(cv CCM_PROMPT_REMINDERS)
if [[ -n "$rem" && -f "$rem" ]]; then
    grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' "$rem" 2>/dev/null | head -5
fi
exit 0
