#!/usr/bin/env bash
# check-prompt-gap: the time line (first message / previous + "ago"), machine prompts (CCM_MACHINE_SESSION=1, a
# <task-notification>) go to machine/ and don't count as presence, CCM_TIMEZONE, the per-prompt reminders file.
# CPG=<path> tests another copy. Sandbox: temp HOME, no config file.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
CPG=${CPG:-$HERE/../hooks/check-prompt-gap.sh}
PC=$HERE/../scripts/presence_check.py
T=$(mktemp -d) && [[ -d "$T" && "$T" != / ]] || { echo "no temp dir (mktemp missing?) - refusing to run: every path below would land in /" >&2; exit 2; }
trap 'rm -rf "$T"' EXIT
export HOME=$T/home CLAUDE_METHODOLOGY_CONF=$T/none.conf CCM_TIMEZONE=UTC
unset CLAUDE_METHODOLOGY_DIR CCM_MACHINE_SESSION
mkdir -p "$HOME"
TS=$HOME/.claude/cache/prompt-timestamps
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1 :: ${3:-}"; fi; }
ev() { printf '{"session_id":"%s","prompt":"%s"}' "$1" "$2"; }

o=$(ev s1 hello | bash "$CPG")
ok "1 first prompt -> 'first message of this session', clock in CCM_TIMEZONE" '[[ "$o" == *"first message of this session"* && "$o" == *" UTC "* ]]' "$o"
ok "2 the human's timestamp is at the top level" '[[ -f $TS/s1 && ! -e $TS/machine/s1 ]]'
echo $(( $(date +%s) - 7200 )) > "$TS/s1"
o=$(ev s1 again | bash "$CPG")
ok "3 second prompt -> previous message time + '2 h ago'" '[[ "$o" == *"previous message: "*"(2 h ago)"* ]]' "$o"
echo $(( $(date +%s) - 3*86400 )) > "$TS/s1"
o=$(ev s1 again | bash "$CPG")
ok "4 three days -> '3 d ago'" '[[ "$o" == *"(3 d ago)"* ]]' "$o"
o=$(ev s2 '<task-notification>done</task-notification>' | bash "$CPG")
ok "5 a task notification -> machine/, not the top level" '[[ -f $TS/machine/s2 && ! -e $TS/s2 ]]'
o=$(ev s3 work | CCM_MACHINE_SESSION=1 bash "$CPG")
ok "6 CCM_MACHINE_SESSION=1 -> machine/" '[[ -f $TS/machine/s3 && ! -e $TS/s3 ]]'
rm -f "$TS/s1"
PRESENCE_TS_DIR=$TS python3 "$PC" >/dev/null 2>&1; rc=$?
ok "7 only machine prompts are fresh -> presence is not 'present' (rc != 0)" '[[ $rc != 0 ]]' "rc=$rc"
ev s4 hi | bash "$CPG" >/dev/null
PRESENCE_TS_DIR=$TS python3 "$PC" >/dev/null 2>&1; rc=$?
ok "8 a fresh human prompt -> presence 'present' (rc 0)" '[[ $rc == 0 ]]' "rc=$rc"
printf '# a comment\n\nEnd with the next step; never offer a pause.\n' > "$T/rem.txt"
o=$(ev s4 hi | CCM_PROMPT_REMINDERS=$T/rem.txt bash "$CPG")
ok "9 reminders file -> its lines every prompt, comments and blanks skipped" \
   '[[ "$o" == *"never offer a pause."* && "$o" != *"a comment"* && $(printf "%s\n" "$o" | wc -l) == 2 ]]' "$o"
o=$(ev s4 hi | CCM_PROMPT_REMINDERS=$T/missing.txt bash "$CPG")
ok "10 a missing reminders file -> just the time line" '[[ $(printf "%s\n" "$o" | wc -l) == 1 ]]' "$o"
o=$(printf '{"prompt":"x"}' | bash "$CPG"); rc=$?
ok "11 no session id -> silent, rc 0" '[[ -z "$o" && $rc == 0 ]]' "$o"
echo "check-prompt-gap: $pass pass, $fail fail"; (( fail == 0 ))
