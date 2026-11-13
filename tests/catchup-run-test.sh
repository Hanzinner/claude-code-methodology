#!/usr/bin/env bash
# bin/catchup-run in a sandbox: runs once per period; a failure leaves .fail and a re-run; a success clears .fail; --after holds
# the job until its hour; rc 75 = deferred (no state); usage errors rc 2; the command does not inherit the lock fd.
# CR=<path> tests another copy. Temp HOME, state and log dirs; no network.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CR=${CR:-$HERE/../bin/catchup-run}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home"; mkdir -p "$HOME"
export CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_CRON_STATE="$T/state" CCM_CRON_LOGDIR="$T/log"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }
H=$((10#$(date +%H)))

"$CR" job1 daily -- sh -c 'echo run >> "$0"' "$T/count" ; rc=$?
ok "1 first run: rc 0, command ran, .ok written with today's key" '[ $rc = 0 ] && [ "$(wc -l < "$T/count")" = 1 ] && grep -q "$(date +%F)\$" "$T/state/job1.ok"'
"$CR" job1 daily -- sh -c 'echo run >> "$0"' "$T/count"
ok "2 second run in the same period: skipped" '[ "$(wc -l < "$T/count")" = 1 ]'
ok "3 the command output went to the log" 'grep -q "start (daily" "$T/log/job1.log"'

"$CR" job2 daily -- sh -c 'exit 7'; rc=$?
ok "4 failing command: its rc is returned, .fail written, no .ok" '[ $rc = 7 ] && grep -q "rc=7" "$T/state/job2.fail" && [ ! -e "$T/state/job2.ok" ]'
"$CR" job2 daily -- sh -c 'echo again >> "$0"' "$T/again"
ok "5 after a failure the next tick tries again; success clears .fail" '[ -f "$T/again" ] && [ ! -e "$T/state/job2.fail" ] && [ -s "$T/state/job2.ok" ]'

if [ $H -lt 23 ]; then
    "$CR" job3 daily --after 23 -- sh -c 'echo x >> "$0"' "$T/early"; rc=$?
    ok "6 --after later than now: not run, rc 0, no state" '[ $rc = 0 ] && [ ! -e "$T/early" ] && [ ! -e "$T/state/job3.ok" ]'
fi
"$CR" job4 daily --after 0 -- sh -c 'echo x >> "$0"' "$T/late"
ok "7 --after 0: runs" '[ -f "$T/late" ]'

"$CR" job5 daily -- sh -c 'exit 75'; rc=$?
ok "8 rc 75 = deferred: rc 0, neither .ok nor .fail, noted in the log" '[ $rc = 0 ] && [ ! -e "$T/state/job5.ok" ] && [ ! -e "$T/state/job5.fail" ] && grep -q DEFERRED "$T/log/job5.log"'

"$CR" weekly1 weekly -- true; "$CR" month1 monthly -- true
ok "9 weekly / monthly keys: ISO week and month" 'grep -q "$(date +%G-W%V)\$" "$T/state/weekly1.ok" && grep -q "$(date +%Y-%m)\$" "$T/state/month1.ok"'

"$CR" 2>/dev/null; r1=$?; "$CR" x yearly -- true 2>/dev/null; r2=$?; "$CR" a/b daily -- true 2>/dev/null; r3=$?; "$CR" x daily --after zz -- true 2>/dev/null; r4=$?
ok "10 usage errors (none / bad period / slash in name / bad --after): rc 2" '[ $r1 = 2 ] && [ $r2 = 2 ] && [ $r3 = 2 ] && [ $r4 = 2 ]'

# the command must not hold the lock: a background child that outlives the run must not block the next period's run
"$CR" job6 daily -- sh -c '(sleep 3) & exit 0'
rm -f "$T/state/job6.ok"
timeout 2 "$CR" job6 daily -- sh -c 'echo x >> "$0"' "$T/lockchild"
ok "11 a lingering child of the command does not hold the lock" '[ -f "$T/lockchild" ]'

# the state is usable by cron_state_check.py (the supervisor's age check)
out=$(CCM_CRON_STATE="$T/state" python3 "$HERE/../scripts/cron_state_check.py" job1 36 2>&1); rc=$?
ok "12 cron_state_check.py reads what catchup-run wrote: green for job1" '[ $rc = 0 ]'
out=$(CCM_CRON_STATE="$T/state" python3 "$HERE/../scripts/cron_state_check.py" job2 36 2>&1); rc=$?
ok "12b ... and green again for job2 after its recovery" '[ $rc = 0 ]'

echo "catchup-run: $pass pass, $fail fail"
[ $fail -eq 0 ]
