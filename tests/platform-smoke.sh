#!/usr/bin/env bash
# Install smoke test for any OS (CI: Linux and macOS runners; by hand: a throwaway machine). From THIS checkout, into a
# throwaway HOME: install.sh --user --yes, check-install.py, then every hook command from the installed settings.json
# fed a minimal payload (a hook that exits other than 0/2 is a failure), then hook-errors.log. Touches nothing of the
# user's: HOME is a temp dir that the script removes at the end (KEEP=1 keeps it for a look); crontab untouched unless
# SMOKE_CRON=1 (CI sets it: the runner's crontab is thrown away with the runner).
# Exit: 0 all green · 1 something failed (the lines above say what) · 2 no temp dir.
set -u
REPO=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d "${TMPDIR:-/tmp}/ccm-smoke.XXXXXX") || exit 2
[[ -d "$T" ]] || exit 2
[[ "${KEEP:-0}" = 1 ]] || trap 'rm -rf "$T"' EXIT
mkdir -p "$T/home" "$T/ws"
export HOME="$T/home" CCM_WORKSPACE="$T/ws"
bad=0
echo "== env"
uname -a; echo "bash on PATH: $(command -v bash) ($(bash -c 'echo $BASH_VERSION'))"; echo "/bin/bash: $(/bin/bash -c 'echo $BASH_VERSION')"
for c in python3 git flock timeout gtimeout setsid crontab jq getent readlink stat date; do printf '  %-9s %s\n' "$c" "$(command -v "$c" || echo MISSING)"; done
locale -a 2>/dev/null | grep -i -E '^c\.utf-?8$' >/dev/null && echo "  locale C.UTF-8: yes" || echo "  locale C.UTF-8: NO"

echo "== install"
CRON=(--no-cron); [[ "${SMOKE_CRON:-0}" = 1 ]] && CRON=()   # CI: the runner's own crontab; by hand: never touch yours
# ${CRON[@]+...} below: on bash 3.2 (stock macOS) "${CRON[@]}" of an empty array under set -u is an error
( cd "$REPO" && ./install.sh --user --yes ${CRON[@]+"${CRON[@]}"} </dev/null ) > "$T/install.log" 2>&1; rc=$?
echo "install exit=$rc"; tail -30 "$T/install.log"; [[ $rc = 0 ]] || bad=1

echo "== check-install"
( cd "$REPO" && python3 check-install.py --user ) > "$T/check.log" 2>&1; rc=$?
echo "check exit=$rc"; tail -20 "$T/check.log"; [[ $rc = 0 ]] || bad=1

echo "== hooks"
S="$HOME/.claude/settings.json"
if [[ ! -f "$S" ]]; then echo "no $S"; exit 1; fi
python3 - "$S" > "$T/hooks.txt" <<'P'
import json, sys
s = json.load(open(sys.argv[1]))
for ev, groups in s.get("hooks", {}).items():
    for g in groups:
        for h in g.get("hooks", []):
            if h.get("type", "command") == "command":
                print(ev + "\t" + h["command"])
P
n=0; f=0
while IFS=$'\t' read -r ev cmd; do
    n=$((n+1))
    case $ev in
        PreToolUse|PostToolUse|PostToolUseFailure|PermissionDenied)
            p='{"session_id":"t","hook_event_name":"'$ev'","tool_name":"Bash","tool_input":{"command":"echo hi"},"tool_response":{"stdout":"hi"},"cwd":"'$T/ws'"}' ;;
        UserPromptSubmit) p='{"session_id":"t","hook_event_name":"UserPromptSubmit","prompt":"hello","cwd":"'$T/ws'"}' ;;
        *) p='{"session_id":"t","hook_event_name":"'$ev'","cwd":"'$T/ws'","transcript_path":"'$T'/none.jsonl"}' ;;
    esac
    # Claude Code runs a hook command through the user's shell; here: /bin/sh -c, the most basic case
    out=$(printf '%s' "$p" | /bin/sh -c "$cmd" 2>&1); rc=$?
    if [[ $rc -ne 0 && $rc -ne 2 ]]; then f=$((f+1)); echo "FAIL rc=$rc $ev: ${cmd:0:120} :: ${out:0:300}"; fi
done < "$T/hooks.txt"
echo "$n hook commands ran, $f failed"; [[ $f = 0 ]] || bad=1

echo "== hook-errors.log (a hook under hook-safe.sh that broke is logged here and exits 0)"
if [[ -s "$HOME/.claude/hook-errors.log" ]]; then tail -40 "$HOME/.claude/hook-errors.log"; bad=1; else echo "(empty)"; fi
echo "== result: $([[ $bad = 0 ]] && echo GREEN || echo RED)"
exit $bad
