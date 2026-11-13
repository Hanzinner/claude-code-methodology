#!/usr/bin/env bash
# swarm_tools_check.sh. ST=<path> tests another copy.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" HANZ_TEST=1 CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_AGENTS_DIR="$T/Agents"; mkdir -p "$HOME" "$T/ws"
printf "#!/bin/sh\necho \"\$1|\${2:-\$(cat)}\" >> %s/letters\n" "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/letters"; export CCM_INBOX_POST="$T/post"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | sed "s/^/   /"; fi; }
ST=${ST:-$HERE/../scripts/swarm_tools_check.sh}
S="$T/s"; mkdir -p "$S" "$T/bin"; export SWARM_TOOLS_DIRS="$S:$T/bin"
printf '# tools\n- known_tool: does a thing\n- helper: x\n' > "$T/ws/SWARM-TOOLS.md"
echo x > "$S/known_tool.sh"; echo x > "$S/helper.py"; echo x > "$S/old.sh.bak1"; echo x > "$S/run.log"
out=$(CCM_SWARM_TOOLS_OWNER=Owner bash "$ST" 2>&1)
ok "1 everything catalogued (.bak/.log ignored) -> one log line, no letter" 'echo "$out" | grep -q "every script is in the catalog" && [ ! -s "$T/letters" ]'
echo x > "$S/brand_new.sh"; printf '#!/bin/sh\n' > "$T/bin/newbin"; chmod +x "$T/bin/newbin"; echo x > "$T/bin/notexec"
out=$(CCM_SWARM_TOOLS_OWNER=Owner bash "$ST" 2>&1)
ok "2 two missing (a script and an executable) -> ONE letter naming both" '[ "$(grep -c "^Owner|" "$T/letters")" = 1 ] && grep -q "brand_new.sh" "$T/letters" && grep -q "newbin" "$T/letters"'
ok "2b a non-executable file in bin/ is not a tool" '! grep -q "notexec" "$T/letters"'
: > "$T/letters"; out=$(bash "$ST" 2>&1)
ok "3 owner empty -> no letter, the log line still shows the count" '[ ! -s "$T/letters" ] && echo "$out" | grep -q "2 without a line"'
printf '# Inbox\n## New\n- [ ] [2026-01-01] swarm_tools_check: 2 script(s) without a line in SWARM-TOOLS.md - brand_new.sh newbin. Add a line\n## Done\n' > "$T/inbox.md"
out=$(SWARM_TOOLS_INBOX="$T/inbox.md" CCM_SWARM_TOOLS_OWNER=Owner bash "$ST" 2>&1)
ok "4 the same list already in ## New -> not repeated" 'echo "$out" | grep -q "already waiting" && [ ! -s "$T/letters" ]'
printf '# Inbox\n## New\n## Done\n- [ ] swarm_tools_check: 2 script(s) - brand_new.sh newbin.\n' > "$T/inbox.md"
out=$(SWARM_TOOLS_INBOX="$T/inbox.md" CCM_SWARM_TOOLS_OWNER=Owner bash "$ST" 2>&1)
ok "5 the old letter sits in ## Done, not ## New -> posted again" '[ "$(grep -c "^Owner|" "$T/letters")" = 1 ]'
rm "$T/ws/SWARM-TOOLS.md"; : > "$T/letters"; out=$(CCM_SWARM_TOOLS_OWNER=Owner bash "$ST" 2>&1)
ok "6 no catalog -> silent exit" '[ -z "$out" ] && [ ! -s "$T/letters" ]'
echo "swarm-tools-check: $pass pass, $fail fail"; [ $fail = 0 ]
