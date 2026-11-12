#!/usr/bin/env bash
# inbox-delta-hint.py: a letter that arrives mid-turn -> a hint on the next tool call; baseline, throttle, silence cases.
# H=<path> tests another copy. Sandbox: temp HOME; the hook runs as a subprocess like in settings.json.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
H=${H:-$HERE/../hooks/inbox-delta-hint.py}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent HANZ_TEST=1; mkdir -p "$HOME/.claude/agent-identity" "$T/Agent"
SID="deltatest-$$"; echo "$T/Agent" > "$HOME/.claude/agent-identity/$SID"
printf '# X - inbox\n\n## New\n\n- [ ] [2026-09-22] old letter\n\n## Processed\n- [x] ancient\n' > "$T/Agent/inbox.md"
run() { echo "{\"session_id\":\"$SID\",\"tool_name\":\"Bash\"}" | INBOX_DELTA_THROTTLE="${THR:-0}" python3 "$H"; }
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "   out=[$out]"; fi; }
bump() { python3 -c 'import os,sys;st=os.stat(sys.argv[1]);os.utime(sys.argv[1],ns=(st.st_atime_ns,st.st_mtime_ns+int(sys.argv[2])*10**9))' "$T/Agent/inbox.md" "$1"; }

out=$(run); ok "1 baseline is silent" '[ -z "$out" ]'
out=$(run); ok "2 no change - silent" '[ -z "$out" ]'
bump 1; out=$(run); ok "3 mtime changed, no new items - silent" '[ -z "$out" ]'
sed -i.bak 's/^## Processed/- [ ] [2026-09-22] HQ: NEW button specification\n\n## Processed/' "$T/Agent/inbox.md"
out=$(run); ok "4 a new letter -> a hint" 'echo "$out" | grep -q "NEW button specification"'
ok "4b valid PostToolUse JSON" 'echo "$out" | python3 -c "import json,sys;d=json.load(sys.stdin);assert d[\"hookSpecificOutput\"][\"hookEventName\"]==\"PostToolUse\""'
ok "4c the old letter is not repeated" '! echo "$out" | grep -q "old letter"'
out=$(run); ok "5 not shown twice" '[ -z "$out" ]'
# throttle: a letter under the throttle is not lost
sed -i.bak 's/^## Processed/- [ ] [2026-09-22] third letter\n\n## Processed/' "$T/Agent/inbox.md"
out=$(THR=3600 run); ok "6 under the throttle - silent" '[ -z "$out" ]'
out=$(THR=0 run); ok "7 after the throttle it arrives" 'echo "$out" | grep -q "third letter"'
# an item in Processed is not a letter
bump 2; sed -i.bak 's/^- \[x\] ancient/- [ ] stray in Processed/' "$T/Agent/inbox.md"
out=$(run); ok "8 an item outside New is ignored" '[ -z "$out" ]'
# the Ukrainian section name still works
sed -i.bak 's/^## New$/## Нові/' "$T/Agent/inbox.md"; bump 3
out=$(run); ok "8b renamed section: nothing new, silent (and no crash)" '[ -z "$out" ]'
sed -i.bak 's/^## Processed/- [ ] [2026-09-22] fourth letter\n\n## Processed/' "$T/Agent/inbox.md"
out=$(run); ok "8c a letter under \"## Нові\" is seen" 'echo "$out" | grep -q "fourth letter"'
# no identity / empty identity / broken stdin / vanished inbox - silent, exit 0
out=$(echo '{"session_id":"nobody-xyz"}' | python3 "$H"); ok "9 no identity - silent" '[ -z "$out" ]'
: > "$HOME/.claude/agent-identity/$SID"; out=$(run); ok "9b empty identity - silent" '[ -z "$out" ]'; echo "$T/Agent" > "$HOME/.claude/agent-identity/$SID"
out=$(echo 'not json' | python3 "$H"); rc=$?; ok "10 broken stdin: exit 0, silent" '[ $rc = 0 ] && [ -z "$out" ]'
rm "$T/Agent/inbox.md"; out=$(run); ok "11 the inbox vanished - silent" '[ -z "$out" ]'
echo "inbox-delta-hint: $pass pass, $fail fail"; [ $fail = 0 ]
