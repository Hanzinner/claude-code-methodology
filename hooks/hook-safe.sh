#!/usr/bin/env bash
# Defensive wrapper for hooks. Principles: fail-open (a crashed hook does NOT
# block the input/tool — exit 0) + a timeout + a central error log
# (~/.claude/hook-errors.log), so a silent failure becomes visible. (Pair it
# with something that surfaces that log — e.g. the briefing-watchman delta.)
#
# Use in settings.json: hook-safe.sh <real-hook-script> [args...]
# The stdin (event JSON) passes through; the real hook's stdout is emitted as-is.
# The real hook's EXIT CODE is intentionally dropped (always 0): none of these
# hooks rely on it — deny-hooks speak via JSON on stdout, which passes through.
#
# ⚠ Do NOT wrap a deliberately fail-CLOSED hook (e.g. memory-write-gate) in this —
# that one is supposed to block on its own errors.
#
# Config: HOOK_TIMEOUT seconds (default 20)

real="$1"; shift
ERRLOG="$HOME/.claude/hook-errors.log"
t="${HOOK_TIMEOUT:-20}"

stderr_tmp=$(mktemp /tmp/hook-stderr.XXXXXX 2>/dev/null) || stderr_tmp=/dev/null
timeout -k 3 "$t" "$real" "$@" 2>"$stderr_tmp"
code=$?
if [ "$code" -ne 0 ]; then
    {
        printf '%s %s failed (exit %s)' "$(date -Iseconds)" "$(basename "$real")" "$code"
        [ "$code" = 124 ] && printf ' [TIMEOUT %ss]' "$t"
        err=$(tail -c 300 "$stderr_tmp" 2>/dev/null | tr '\n' ' ')
        [ -n "$err" ] && printf ' :: %s' "$err"
        printf '\n'
    } >> "$ERRLOG" 2>/dev/null
fi
rm -f "$stderr_tmp" 2>/dev/null
exit 0
