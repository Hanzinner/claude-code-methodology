#!/usr/bin/env bash
# remind-hint: "remind me ..." from the human -> a hint naming remind.py and the agent from the session identity;
# any other prompt -> silent. Runs the repo copy; RH=<path> tests another. Sandbox: temp HOME, no config file.
set -u
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
RH="${RH:-$HERE/../hooks/remind-hint.sh}"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_HUMAN_NAME=Sam; unset CCM_LANG_EXTRA
mkdir -p "$HOME/.claude/agent-identity"; echo "/ws/Agents/Helper" > "$HOME/.claude/agent-identity/s1"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }
hook() { python3 -c 'import json,sys;print(json.dumps({"session_id":sys.argv[1],"prompt":sys.argv[2]}))' "$1" "$2" | bash "$RH" 2>&1; }

out=$(hook s1 "remind me in an hour to call the bank")
ok "\"remind me\" -> hint with remind.py, the agent name from identity, the human's name" '[[ "$out" == *"remind.py Helper <when>"* && "$out" == *"Sam"* ]]'
out=$(hook s1 "Please set a reminder for 18:30"); ok "\"set a reminder\" -> hint" '[[ "$out" == *"remind.py"* ]]'
out=$(hook s1 "REMIND ME tomorrow"); ok "case-insensitive" '[[ "$out" == *"remind.py"* ]]'
out=$(hook nosid "remind me at 9"); ok "no identity for the session -> a placeholder name" '[[ "$out" == *"<your-agent-name>"* ]]'
out=$(hook s1 "what time is the next deploy window?"); ok "an ordinary prompt -> silent" '[ -z "$out" ]'
out=$(hook s1 "the reminder module has a bug in its parser"); ok "the word \"reminder\" alone, not a request -> silent" '[ -z "$out" ]'
out=$(hook s1 "нагадай мені через годину"); ok "Ukrainian phrase without the uk list -> silent" '[ -z "$out" ]'
out=$(CCM_LANG_EXTRA=uk hook s1 "нагадай мені через годину"); ok "Ukrainian phrase with the uk list -> hint" '[[ "$out" == *"remind.py Helper"* ]]'
out=$(echo "not json at all" | bash "$RH" 2>&1); rc=$?; ok "garbage input -> rc 0, silent (fail-open)" '[ $rc = 0 ] && [ -z "$out" ]'
echo "remind-hint: $pass pass, $fail fail"; [ $fail = 0 ]
