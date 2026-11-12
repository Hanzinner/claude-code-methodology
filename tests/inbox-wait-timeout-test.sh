#!/usr/bin/env bash
# inbox-wait-timeout.py: a bare background call of the alarm gets the link's timeout; everything else is untouched.
# H=<path> tests another copy. Sandbox: temp HOME, no settings file.
HERE="$(cd "$(dirname "$0")" && pwd)"
H=${H:-$HERE/../hooks/inbox-wait-timeout.py}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_CLAUDE_DIR="$T/inst" HANZ_TEST=1; mkdir -p "$HOME"
pass=0; fail=0
run() { python3 -c 'import json,sys; ti={"command":sys.argv[1]}; ti.update(json.loads(sys.argv[2])); print(json.dumps({"tool_name":"Bash","tool_input":ti}))' "$1" "${2:-{\}}" | python3 "$H"; }
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }
o=$(run "inbox_wait.sh Some-Agent" '{"run_in_background":true}')
ok "1 a bare call in the background -> timeout 3300000, the command the same" '[[ "$o" == *"\"timeout\": 3300000"* && "$o" == *"inbox_wait.sh Some-Agent\""* && "$o" == *"\"allow\""* ]]'
o=$(run "$T/inst/scripts/inbox_wait.sh Some-Agent --until 21:00" '{"run_in_background":true}'); ok "2 full install path + --until -> adds" '[[ "$o" == *3300000* ]]'
o=$(run "~/.claude/scripts/inbox_wait.sh X --max 600" '{"run_in_background":true}'); ok "2b ~/.claude/scripts + --max -> adds" '[[ "$o" == *3300000* ]]'
o=$(run "inbox_wait.sh X" '{}'); ok "3 not in the background -> untouched" '[ -z "$o" ]'
o=$(run "inbox_wait.sh X; rm -rf /tmp/y" '{"run_in_background":true}'); ok "4 a glued command -> untouched (the allow approves nothing extra)" '[ -z "$o" ]'
o=$(run "inbox_wait.sh X" '{"run_in_background":true,"timeout":7200000}'); ok "5 a longer timeout already -> untouched" '[ -z "$o" ]'
o=$(run "echo inbox_wait.sh X" '{"run_in_background":true}'); ok "6 another command with that word -> untouched" '[ -z "$o" ]'
o=$(run "/tmp/evil/inbox_wait.sh X" '{"run_in_background":true}'); ok "7 a script of that name from a foreign path -> untouched" '[ -z "$o" ]'
o=$(echo 'not json' | python3 "$H"); rc=$?; ok "8 broken stdin -> silent, rc 0" '[ $rc = 0 ] && [ -z "$o" ]'
echo "inbox-wait-timeout: $pass pass, $fail fail"; [ $fail = 0 ]
