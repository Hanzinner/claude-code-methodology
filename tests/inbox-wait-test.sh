#!/usr/bin/env bash
# inbox_wait.sh: wakes on a change of the SET of letters in "New" (not on the counter), does not erase another tab's
# pid file, keeps one alarm per agent/tab, honours the modes. IW=<path> tests another copy. Sandbox only.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
IW=${IW:-$HERE/../scripts/inbox_wait.sh}
T=$(mktemp -d); trap 'kill $(jobs -p) 2>/dev/null; rm -rf "$T"' EXIT
export HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_AGENTS_DIR="$T/Agents" ALARM_MODE_DIR="$T/mode" INBOX_WAIT_POLL=1 HANZ_TEST=1
mkdir -p "$HOME" "$T/Agents/T" "$T/mode"
IN="$T/Agents/T/inbox.md"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }
inbox() { printf '# T\n\n## New\n%s\n## Processed\n' "$1" > "$IN"; }
waitfor() { for _ in $(seq 1 "$1"); do [[ -s "$2" ]] && return 0; sleep 1; done; return 1; }   # an event, not a fixed pause

# 1: at the start letter A; the agent closed A, B arrived -> the counter is the same (1), the letter is new -> wake
inbox "- [ ] letter A"
bash "$IW" T --max 60 > "$T/o1" 2>&1 &
sleep 2; inbox "- [ ] letter B"
waitfor 45 "$T/o1"; ok "A closed, B arrived (counter 1->1) -> wakes" 'grep -q "new letter" "$T/o1"'

# the letter was only closed, nothing new -> no wake
inbox "- [ ] letter C"; bash "$IW" T --max 4 > "$T/o2" 2>&1 & p=$!
sleep 2; inbox ""; wait $p
ok "closed, nothing new -> no wake (until --max)" 'grep -q "of waiting passed" "$T/o2" && ! grep -q "new letter" "$T/o2"'

# one of two closed -> no wake
inbox "- [ ] letter D
- [ ] letter E"; bash "$IW" T --max 4 > "$T/o3" 2>&1 & p=$!
sleep 2; inbox "- [ ] letter D"; wait $p
ok "one of two closed -> no wake" 'grep -q "of waiting passed" "$T/o3" && ! grep -q "new letter" "$T/o3"'

# ceiling: a horizon beyond the life of a background task -> a meaningful exit, not "killed"
inbox ""; INBOX_WAIT_CEIL=3 bash "$IW" T --until "$(python3 -c 'import datetime;print((datetime.datetime.now()+datetime.timedelta(hours=2)).strftime("%H:%M"))')" > "$T/o4" 2>&1
ok "--until in 2 h with a 3 s ceiling -> \"served its link... N min left... start it again\"" 'grep -q "served its link" "$T/o4" && grep -qE "11[0-9] min left" "$T/o4" && grep -q "start it again" "$T/o4"'

# one alarm per agent: a second one with a live first exits at once, the pid file stays with the first
inbox ""
bash "$IW" T --max 30 >/dev/null 2>&1 & p1=$!
sleep 2; out=$(timeout 10 bash "$IW" T --max 60 2>&1); rc=$?
ok "a second with a live first -> at once, \"already armed (pid ...)\", rc 0" '[[ $rc == 0 && $out == *"already armed (pid $p1)"* ]]'
ok "...the pid file stayed with the first" '[[ "$(cat "$HOME/.claude/inbox-wait/T" 2>/dev/null)" == "$p1" ]]'
kill $p1 2>/dev/null; wait $p1 2>/dev/null; rm -f "$HOME/.claude/inbox-wait/T"
echo 99999999 > "$HOME/.claude/inbox-wait/T"
bash "$IW" T --max 3 > "$T/o9" 2>&1
ok "a dead pid in the file -> a new alarm takes over and runs to the end" 'grep -q "of waiting passed" "$T/o9" && [[ ! -e "$HOME/.claude/inbox-wait/T" ]]'

# "also waiting": a live alarm of another agent from the work-guard list
mkdir -p "$T/Agents/U"; printf '# U\n\n## New\n\n## Processed\n' > "$T/Agents/U/inbox.md"
printf 'T\nU\n' > "$HOME/.claude/work_guard_agents.txt"
bash "$IW" U --max 30 >/dev/null 2>&1 & pu=$!; sleep 2
bash "$IW" T --max 3 > "$T/o10" 2>&1
ok "an exit without a letter -> \"also waiting: U N min\"" 'grep -q "also waiting: U [0-9]* min" "$T/o10"'
rm -f "$HOME/.claude/work_guard_agents.txt"
bash "$IW" T --max 3 > "$T/o10b" 2>&1
ok "no list file -> every live alarm is listed" 'grep -q "also waiting: U " "$T/o10b"'
kill $pu 2>/dev/null; wait $pu 2>/dev/null

# two tabs with the same identity: a live alarm of ANOTHER session (another ancestor named "claude") does not take mine
mkdir -p "$T/fake"; cp /bin/bash "$T/fake/claude"
# "; true" - a second command: otherwise bash -c execs and "claude" disappears from the chain
"$T/fake/claude" -c "bash '$IW' T --max 120; true" >/dev/null 2>&1 & pf=$!; sleep 2; p1=$(cat "$HOME/.claude/inbox-wait/T" 2>/dev/null)
out=$(timeout 60 bash "$IW" T --max 3 2>&1); rc=$?
ok "another tab: \"armed in ANOTHER tab\" and my own alarm ran" '[[ -n $p1 && $out == *"ANOTHER tab (pid $p1)"* && $out == *"of waiting passed"* ]]'
ok "...the pid file stayed with the other tab's alarm (my exit did not erase it)" '[[ "$(cat "$HOME/.claude/inbox-wait/T" 2>/dev/null)" == "$p1" ]]'
kill $p1 $pf 2>/dev/null; wait $pf 2>/dev/null; rm -f "$HOME/.claude/inbox-wait/T"

# an old name via .aliases -> the same inbox, the pid file under the real name
printf '# was\nOldT\n' > "$T/Agents/T/.aliases"
out=$(timeout 30 bash "$IW" OldT --max 2 2>&1); rc=$?
ok "an old name via .aliases -> the alarm works under the real name, not \"no inbox found\"" '[[ $out != *"no inbox found"* && $rc != 2 ]]'
out=$(bash "$IW" Nobody-Here --max 2 2>&1); rc=$?
ok "unknown agent -> rc 2" '[[ $rc == 2 && $out == *"no inbox found"* ]]'

# modes: off does not start · once after a letter -> off · auto after an hour of silence "went out"
echo off > "$T/mode/T"; inbox ""; o=$(bash "$IW" T --max 5 2>&1)
ok "m1 off -> does not start" '[[ "$o" == *"is off"* && "$o" == *"Not starting"* ]]'
echo once > "$T/mode/T"; inbox ""; bash "$IW" T --max 60 > "$T/om" 2>&1 &
sleep 2; inbox "- [ ] letter M"; waitfor 45 "$T/om"
ok "m2 once: woke on a letter -> mode off" 'grep -q "new letter" "$T/om" && [ "$(cat "$T/mode/T")" = off ]'
rm -f "$T/mode/T"; inbox ""; touch -d "-2 hours" "$IN" 2>/dev/null || touch -t "$(python3 -c 'import time;print(time.strftime("%Y%m%d%H%M",time.localtime(time.time()-7200)))')" "$IN"
o=$(ALARM_AUTO_IDLE=3600 bash "$IW" T --max 3 2>&1)
ok "m3 auto (no file), inbox quiet for 2 h -> \"went out\"" '[[ "$o" == *"went out"* ]]'
inbox ""; o=$(bash "$IW" T --max 3 2>&1)
ok "m3b auto, fresh inbox -> the usual \"passed\"" '[[ "$o" == *"of waiting passed"* && "$o" != *"went out"* ]]'
echo always > "$T/mode/T"; touch -t "$(python3 -c 'import time;print(time.strftime("%Y%m%d%H%M",time.localtime(time.time()-7200)))')" "$IN"
o=$(bash "$IW" T --max 3 2>&1)
ok "m4 always: never goes out by itself" '[[ "$o" == *"of waiting passed"* && "$o" != *"went out"* ]]'
echo "inbox-wait: $pass pass, $fail fail"; [ $fail = 0 ]
