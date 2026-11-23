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

# Windows (Git Bash), or python3 is not a working Python: install.sh wrote lib/pyshim/env.sh - `python3` first in PATH
# runs the real Python, plus UTF-8 and \n line ends. Not there on Linux/macOS. A SessionStart hook also hands that PATH
# to the agent's own Bash commands (CLAUDE_ENV_FILE), so `python3 <script>` works for the agent too.
pyenv="$(dirname "$0")/../lib/pyshim/env.sh"
if [ -f "$pyenv" ]; then
    . "$pyenv"
    if [ -n "${CLAUDE_ENV_FILE:-}" ] && ! grep -qsF "$CCM_PYSHIM" "$CLAUDE_ENV_FILE"; then
        printf 'export PATH="%s:$PATH"\n' "$CCM_PYSHIM" >> "$CLAUDE_ENV_FILE" 2>/dev/null
    fi
fi

# lib/ccm_compat.sh: ccm_timeout (timeout, else gtimeout, else perl - a stock macOS has no timeout, and without the
# fallback every hook here exited 127: all of them silently off) and ccm_now_iso (date -Iseconds is GNU)
compat="$(dirname "$0")/../lib/ccm_compat.sh"
if [ -f "$compat" ]; then . "$compat"; fi
type ccm_timeout >/dev/null 2>&1 || ccm_timeout() { timeout "$@"; }
type ccm_now_iso >/dev/null 2>&1 || ccm_now_iso() { date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S%z; }

real="$1"; shift
hook_name=$(basename "$real")   # for the log: after a shebang launch $real is the interpreter
# "<dir>/hook-safe.sh" python "<dir>/x.py" (install.sh writes it so where python3 is not a working Python): name the script
case "$hook_name" in *.py|*.sh) ;; *) for a in "$@"; do case "$a" in *.py|*.sh) hook_name=$(basename "$a"); break ;; esac; done ;; esac
ERRLOG="$HOME/.claude/hook-errors.log"
t="${HOOK_TIMEOUT:-20}"

# /dev/null must be a character device. If something replaced it with a regular
# file, every `>/dev/null` in every tool writes into it. Alert loudly (once a
# minute); restoring it (mknod) is a human decision, not the hook's.
if [ ! -c /dev/null ]; then
    m="/tmp/devnull-alert-$(date +%H%M)"
    [ -e "$m" ] || { : > "$m"; printf '%s /dev/null is NOT a device (%s) — restore: sudo sh -c "rm -f /dev/null; mknod -m 666 /dev/null c 1 3"\n' "$(ccm_now_iso)" "$(stat -c %F /dev/null 2>/dev/null || stat -f %HT /dev/null 2>&1)" >> "$ERRLOG"; }
fi

stderr_tmp=$(mktemp /tmp/hook-stderr.XXXXXX 2>/dev/null) || stderr_tmp=/dev/null

# install.sh may start this wrapper with a bash 4+ by its full path (a Mac whose /bin/bash is 3.2 and that has a newer
# one, e.g. Homebrew's). A bash hook started by its #! line would get the bash first in PATH again - the old one - so
# then it runs under the same bash as this wrapper. Where the bash in PATH is 4+ (Linux, Git Bash) nothing changes.
if [ "${BASH_VERSINFO:-0}" -ge 4 ] && [ -f "$real" ]; then
    pb=$(command -v bash 2>/dev/null)
    if [ -z "$pb" ] || { [ "$pb" != "$BASH" ] && [ "$("$pb" -c 'echo "${BASH_VERSINFO[0]}"' 2>/dev/null || echo 0)" -lt 4 ]; }; then
        case "$(head -c 200 "$real" 2>/dev/null | head -1)" in '#!'*bash*) set -- "$real" "$@"; real="$BASH" ;; esac
    fi
fi

# Target without +x (a file-writing tool doesn't set it; a hook was dead for a month
# on exit 126): if it has a shebang, run it through that interpreter + a loud warning.
if [ -f "$real" ] && [ ! -x "$real" ]; then
    shebang=$(head -c 200 "$real" 2>/dev/null | head -1)
    if [ "${shebang#\#!}" != "$shebang" ]; then
        m="/tmp/hook-nox-$hook_name-$(date +%d%H)"
        [ -e "$m" ] || { : > "$m"; printf '%s %s has no +x — ran via its shebang (%s). Fix: chmod +x %s\n' "$(ccm_now_iso)" "$hook_name" "${shebang#\#!}" "$real" >> "$ERRLOG"; }
        # shellcheck disable=SC2086 — "/usr/bin/env python3" must split into words
        set -- ${shebang#\#!} "$real" "$@"
        real="$1"; shift
    fi
fi

ccm_timeout -k 3 "$t" "$real" "$@" 2>"$stderr_tmp"
code=$?
if [ "$code" -ne 0 ]; then
    # the line is built whole and written with ONE write: several printf in a row from hooks running in parallel
    # interleaved in the log into one line (three timeouts at the same second)
    line="$(ccm_now_iso) $hook_name failed (exit $code)"
    [ "$code" = 124 ] && line="$line [TIMEOUT ${t}s]"
    err=$(tail -c 300 "$stderr_tmp" 2>/dev/null | tr '\n' ' ')
    [ -n "$err" ] && line="$line :: $err"
    printf '%s\n' "$line" >> "$ERRLOG" 2>/dev/null
fi
# If mktemp failed, stderr_tmp is /dev/null — never delete that (as root it would
# remove the device; this happened).
[ "$stderr_tmp" != /dev/null ] && rm -f "$stderr_tmp" 2>/dev/null
exit 0
