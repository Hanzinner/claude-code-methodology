#!/usr/bin/env bash
# take_task.sh: the story must exist in the project's ROADMAP.md; the session id lands in the state dir.
# Runs the repo copy; TT=<path> tests another one. Sandbox: temp workspace/HOME/state, no config file.
set -u
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
TT="${TT:-$HERE/../scripts/take_task.sh}"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent TAKE_TASK_REPO="$T/ws" TAKE_TASK_STATE="$T/state"
mkdir -p "$HOME" "$T/ws/Project-Shop" "$T/ws/Work-Other"
printf '# ROADMAP\n- [ ] E1.S2 cart totals\n- [x] E1.S3 login\n' > "$T/ws/Project-Shop/ROADMAP.md"
printf -- '- [ ] E1.S2 other\n' > "$T/ws/Work-Other/ROADMAP.md"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

out=$(TAKE_TASK_SID=sess-1234abcd "$TT" Shop E1.S2 2>&1); rc=$?
ok "an existing story -> rc 0, the state file holds project + code" '[ $rc = 0 ] && grep -q "^Project-Shop E1.S2 " "$T/state/sess-1234abcd"'
out=$(TAKE_TASK_SID=sess-2 "$TT" Project-Shop E1.S3 2>&1); rc=$?
ok "the project given WITH the folder prefix works too" '[ $rc = 0 ] && grep -q "^Project-Shop E1.S3 " "$T/state/sess-2"'
out=$(TAKE_TASK_SID=sess-3 "$TT" Shop E9.S9 2>&1); rc=$?
ok "a story that is not in the roadmap -> rc 4, no state file" '[ $rc = 4 ] && [ ! -f "$T/state/sess-3" ] && [[ "$out" == *"not in"* ]]'
out=$(TAKE_TASK_SID=sess-4 "$TT" Nothing E1.S2 2>&1); rc=$?
ok "a project without a roadmap -> rc 4" '[ $rc = 4 ]'
out=$(TAKE_TASK_SID=sess-5 "$TT" Shop E1.S 2>&1); rc=$?
ok "a prefix of a code (E1.S vs E1.S2) is not a match -> rc 4" '[ $rc = 4 ]'
out=$(CCM_PROJECTS_GLOB='Work-*' TAKE_TASK_SID=sess-6 "$TT" Other E1.S2 2>&1); rc=$?
ok "CCM_PROJECTS_GLOB=Work-* -> folders with that prefix" '[ $rc = 0 ] && grep -q "^Work-Other E1.S2 " "$T/state/sess-6"'
out=$(env -u TAKE_TASK_SID "$TT" Shop E1.S2 2>&1); rc=$?
ok "no session found (not run from an agent tab) -> rc 2" '[ $rc = 2 ] && [[ "$out" == *"session"* ]]'
out=$("$TT" 2>&1); rc=$?
ok "no arguments -> rc != 0" '[ $rc != 0 ]'
echo "take-task: $pass pass, $fail fail"; [ $fail = 0 ]
