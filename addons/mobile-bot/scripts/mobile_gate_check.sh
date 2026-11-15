#!/usr/bin/env bash
# Supervisor check: the safety gate of the phone bot. It checks the RESULT, not that files exist: run as the bot's
# user with CLAUDE_MOBILE_BOT=1, a secret read and `rm -rf` must be blocked (rc 2) and a plain read let through (rc 0);
# the hooks must be there and executable; the bot must switch the flag on. (Why: a check that read only another
# user's settings once said "green" for a gate that was not wired at all.)
# Usage: mobile_gate_check.sh [--user BOT_USER]   (default: the current user; as root with --user it drops to that user)
# Output: one line; exit 0 = green, 1 = red (what is wrong).
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
HERE=$(dirname "$(readlink -f "$0")"); ADDON=$(readlink -f "$HERE/..")
H=${H:-$ADDON/hooks}; BOT=$ADDON/bot.py
user=""; [[ "${1:-}" == "--user" ]] && user=${2:-}
bad=()
for f in mobile-restrict.sh mobile_restrict.py mobile-audit.sh; do
  [[ -f $H/$f ]] || bad+=("$f missing")
done
[[ -x $H/mobile-restrict.sh ]] || bad+=("mobile-restrict.sh is not executable")
[[ -x $H/mobile-audit.sh ]] || bad+=("mobile-audit.sh is not executable")
grep -q 'CLAUDE_MOBILE_BOT="1"' "$BOT" 2>/dev/null || bad+=("the bot does not switch on CLAUDE_MOBILE_BOT")
grep -q 'mobile-restrict.sh' "$BOT" 2>/dev/null || bad+=("the bot does not pass the gate hook to claude")
secret="${CCM_SECRETS_DIR:-$HOME/.config/claude-secrets}/mobile-bot.env"
run_hook() {   # the hook as the bot would run it
  if [[ -n "$user" && "$(id -u)" == 0 ]]; then
    runuser -u "$user" -- env CLAUDE_MOBILE_BOT=1 PATH=/usr/bin:/bin "$H/mobile-restrict.sh"
  else env CLAUDE_MOBILE_BOT=1 PATH=/usr/bin:/bin "$H/mobile-restrict.sh"; fi
}
t(){ printf '%s' "$2" | run_hook >/dev/null 2>&1; rc=$?; [[ $rc == "$1" ]] || bad+=("expected rc=$1, got $rc: ${2:0:70}"); }
t 2 "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"cat $secret\"}}"
t 2 '{"tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/x"}}'
t 0 '{"tool_name":"Bash","tool_input":{"command":"ls /tmp"}}'
((${#bad[@]})) && { printf '%s; ' "${bad[@]}"; echo; exit 1; }
echo "phone gate: 2 prohibitions caught, 1 allowance passed; hooks in place; the bot switches the flag on"
