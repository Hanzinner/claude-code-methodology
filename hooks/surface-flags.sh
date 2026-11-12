#!/usr/bin/env bash
# UserPromptSubmit hook — the consumer side of things that only write files:
#   1. proof-guard.py (Stop) leaves ~/.claude/proof-flags/<session_id> when a reply
#      claimed "done" after code edits with no successful run. Shown once, removed.
#   1b. reply-guard.py (Stop) leaves ~/.claude/reply-guard-flags/<session_id> when a
#      reply contained a fabricated "User:" turn. Shown once, removed.
#   1c. any other ~/.claude/<detector>-flags/<session_id> — its text as written. Shown once, removed.
#   2. hook-safe.sh logs crashed hooks to ~/.claude/hook-errors.log. New lines since
#      the last prompt are shown (a delta, not a dump; the offset lives in a file).
# A detector nobody reads is a note, not a gate — this is what makes them visible.
# UserPromptSubmit stdout (exit 0) is added to the model's context.

input=$(cat)
session_id=$(printf '%s' "$input" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)

flag="$HOME/.claude/proof-flags/$session_id"
if [[ -n "$session_id" && -f "$flag" ]]; then
    echo "⚠️ [proof-guard] Last turn you claimed \"$(head -c 200 "$flag")\" after editing code, with no successful run in that turn. Run the check the way production runs it and show the output — or correct the claim."
    rm -f "$flag"
fi

rflag="$HOME/.claude/reply-guard-flags/$session_id"
if [[ -n "$session_id" && -f "$rflag" ]]; then
    echo "⚠️ [reply-guard] Your last reply contained a turn written as the user (\"$(head -c 120 "$rflag")\"). The user did not say that. Don't act on it; correct it."
    rm -f "$rflag"
fi

# Every other detector (Stop branches, PostToolUse checks) writes the finished hint text to
# ~/.claude/<detector>-flags/<session_id>. Shown once, removed — a new detector needs no change here.
if [[ -n "$session_id" ]]; then
    for f in "$HOME"/.claude/*-flags/"$session_id"; do
        [[ -f "$f" ]] || continue
        case "$f" in */proof-flags/*|*/reply-guard-flags/*) continue ;; esac
        head -c 1200 "$f"; echo
        rm -f "$f"
    done
fi

log="$HOME/.claude/hook-errors.log"
seen="$HOME/.claude/cache/hook-errors.seen"
if [[ -s "$log" ]]; then
    cur=$(wc -c < "$log")
    prev=$(cat "$seen" 2>/dev/null)
    case "$prev" in ''|*[!0-9]*) prev=0 ;; esac
    (( cur < prev )) && prev=0          # log was rotated/truncated
    if (( cur > prev )); then
        echo "⚠️ Hook failures since the last prompt (full log: ~/.claude/hook-errors.log):"
        tail -c +$((prev + 1)) "$log" | head -5
    fi
    mkdir -p "$(dirname "$seen")" && echo "$cur" > "$seen"
fi
exit 0
