#!/usr/bin/env bash
# Stop dispatcher — one Stop slot, several consumers. Each branch is isolated
# (fail-open): one crashing doesn't touch the others and never blocks the reply
# from finishing. A crash is logged to ~/.claude/hook-errors.log (surface it
# however you surface logs). Add your own branches at the bottom.
#
# Wire this single script to the Stop event; register consumers here.

input=$(cat)
ERRLOG="$HOME/.claude/hook-errors.log"
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"

run_branch() {  # run_branch <name> <command...>
    local name="$1"; shift
    local err
    err=$(printf '%s' "$input" | timeout -k 3 15 "$@" 2>&1 >/dev/null) || \
        echo "$(date -Iseconds) stop-dispatch/$name failed: $(printf '%s' "$err" | tail -c 200)" >> "$ERRLOG" 2>/dev/null
}

run_branch reply_guard python3 "$HOOK_DIR/reply-guard.py"
# run_branch my_other_consumer python3 "$HOOK_DIR/my-consumer.py"
exit 0
