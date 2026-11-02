#!/usr/bin/env bash
# Defensive wrapper for hooks. Principles: fail-open (a crashed hook does NOT
# block the input/tool — exit 0) + a timeout + a central error log
# (~/.claude/hook-errors.log), so a silent failure becomes visible. Surface that
# log somewhere you'll see it (a UserPromptSubmit hook that prints new lines).
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
hook_name=$(basename "$real")   # for the log: after a shebang launch $real is the interpreter
ERRLOG="$HOME/.claude/hook-errors.log"
t="${HOOK_TIMEOUT:-20}"

# /dev/null must be a character device. If something replaced it with a regular
# file, every `>/dev/null` in every tool writes into it. Alert loudly (once a
# minute); restoring it (mknod) is a human decision, not the hook's.
if [ ! -c /dev/null ]; then
    m="/tmp/devnull-alert-$(date +%H%M)"
    [ -e "$m" ] || { : > "$m"; printf '%s /dev/null is NOT a device (%s) — restore: sudo sh -c "rm -f /dev/null; mknod -m 666 /dev/null c 1 3"\n' "$(date -Iseconds)" "$(stat -c %F /dev/null 2>&1)" >> "$ERRLOG"; }
fi

stderr_tmp=$(mktemp /tmp/hook-stderr.XXXXXX 2>/dev/null) || stderr_tmp=/dev/null

# Target without +x (a file-writing tool doesn't set it; a hook was dead for a month
# on exit 126): if it has a shebang, run it through that interpreter + a loud warning.
if [ -f "$real" ] && [ ! -x "$real" ]; then
    shebang=$(head -c 200 "$real" 2>/dev/null | head -1)
    if [ "${shebang#\#!}" != "$shebang" ]; then
        m="/tmp/hook-nox-$hook_name-$(date +%d%H)"
        [ -e "$m" ] || { : > "$m"; printf '%s %s has no +x — ran via its shebang (%s). Fix: chmod +x %s\n' "$(date -Iseconds)" "$hook_name" "${shebang#\#!}" "$real" >> "$ERRLOG"; }
        # shellcheck disable=SC2086 — "/usr/bin/env python3" must split into words
        set -- ${shebang#\#!} "$real" "$@"
        real="$1"; shift
    fi
fi

timeout -k 3 "$t" "$real" "$@" 2>"$stderr_tmp"
code=$?
if [ "$code" -ne 0 ]; then
    {
        printf '%s %s failed (exit %s)' "$(date -Iseconds)" "$hook_name" "$code"
        [ "$code" = 124 ] && printf ' [TIMEOUT %ss]' "$t"
        err=$(tail -c 300 "$stderr_tmp" 2>/dev/null | tr '\n' ' ')
        [ -n "$err" ] && printf ' :: %s' "$err"
        printf '\n'
    } >> "$ERRLOG" 2>/dev/null
fi
# If mktemp failed, stderr_tmp is /dev/null — never delete that (as root it would
# remove the device; this happened).
[ "$stderr_tmp" != /dev/null ] && rm -f "$stderr_tmp" 2>/dev/null
exit 0
