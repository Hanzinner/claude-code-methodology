#!/usr/bin/env bash
# blockers.py in a sandbox: a check turns green -> blocker ✅, a story with no other blockers ⏳->🔄, messages to the agents named in
# the story line, a line for the human; a story with another open blocker does not move; `manual` is cleared only by `clear`;
# `add` appends a row to the table; a command not approved is never run. BL=<path> tests another copy.
HERE="$(cd "$(dirname "$0")" && pwd)"
BL=${BL:-$HERE/../scripts/blockers.py}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent; mkdir -p "$HOME"
R="$T/repo"; mkdir -p "$R/Project-X" "$R/Agents/X-Dev" "$R/Agents/X-Ops"
cat > "$R/Project-X/BLOCKERS.md" <<'B'
# BLOCKERS

| No | What | Who | Check | Date | Stories |
|---|---|---|---|---|---|
| B1 | token permissions | human | `test -e FLAG1 \|\| false` | 2026-10-20 | S1 |
| B2 | a conversation | human | `manual` | 2026-10-26 | S2 |
| B3 | domain | human | `test -e FLAG3` | 2026-10-27 | S2 |
| B4 | description, no command | human | curl something -> not empty | 2026-10-27 | |
B
cat > "$R/Project-X/ROADMAP.md" <<'B'
# ROADMAP
- ⏳ **[E1.S1] First** X-Dev + X-Ops · `blockers: B1` · text
- ⏳ **[E1.S2] Second** X-Dev · `blockers: B2, B3`
- 🔄 **[E1.S3] Third** no blockers
B
printf '#!/bin/sh\necho "$1 $(cat)" >> %s/post.log\n' "$T" > "$T/post"; chmod +x "$T/post"
run() { (cd "$R" && BLOCKERS_REPO="$R" BLOCKERS_POST="$T/post" BLOCKERS_STATE="$T/state" python3 "$BL" "$@") > "$T/out" 2>&1; echo $?; }
LOG="$T/state/blockers.log"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; sed 's/^/   /' "$T/out"; fi; }
run approve X B1 >/dev/null; run approve X B3 >/dev/null
rc=$(run run); ok "1 checks red -> nothing cleared, story stays" '[ "$rc" = 0 ] && grep -q "open 4, cleared now -" "$T/out" && grep -q "^- ⏳ \*\*\[E1.S1\]" "$R/Project-X/ROADMAP.md"'
ok "1b description without a command -> 'not machine-readable' in the log" 'grep -q "B4: check is not machine-readable" "$LOG"'
touch "$R/FLAG1"; rc=$(run run)
ok "2 B1 turns green -> ✅ B1 in the register with a trace" 'grep -q "^| ✅ B1 |.*cleared .*(check)" "$R/Project-X/BLOCKERS.md"'
ok "2b S1 ⏳->🔄 with the watcher trace" 'grep -q "^- 🔄 \*\*\[E1.S1\].*blockers watcher.*B1 cleared" "$R/Project-X/ROADMAP.md"'
ok "2c message to both agents of S1, X-Dev once" '[ "$(grep -c "^X-Dev .*E1.S1" "$T/post.log")" = 1 ] && grep -q "^X-Ops .*E1.S1 is in progress" "$T/post.log"'
ok "2d a line for the human in cleared.log" 'grep -q "✅ X B1 cleared (token permissions) -> in progress: E1.S1" "$T/state/cleared.log"'
rc=$(run run); ok "3 a second pass duplicates nothing" '[ "$(grep -c "E1.S1" "$T/post.log")" = 2 ] && [ "$(grep -c "blockers watcher" "$R/Project-X/ROADMAP.md")" = 1 ]'
touch "$R/FLAG3"; rc=$(run run)
ok "4 B3 cleared, but B2 (manual) still open -> S2 does not move" 'grep -q "^| ✅ B3 |" "$R/Project-X/BLOCKERS.md" && grep -q "^- ⏳ \*\*\[E1.S2\]" "$R/Project-X/ROADMAP.md"'
rc=$(run clear X B2 "the human on the board"); ok "5 clear of a manual one -> S2 🔄, message to X-Dev" '[ "$rc" = 0 ] && grep -q "^- 🔄 \*\*\[E1.S2\]" "$R/Project-X/ROADMAP.md" && grep -q "^X-Dev .*E1.S2" "$T/post.log"'
rc=$(run clear X B2 "again"); ok "5b a repeated clear -> rc 4" '[ "$rc" = 4 ]'
rc=$(run add X "live payment key" "human" "test -s /nope"); ok "6 add -> B5 right after B4 in the table" '[ "$rc" = 0 ] && grep -q "^B5" "$T/out" && [ "$(grep -n "^| B5 |" "$R/Project-X/BLOCKERS.md" | cut -d: -f1)" = "$(( $(grep -n "^| B4 |" "$R/Project-X/BLOCKERS.md" | cut -d: -f1) + 1 ))" ]'
rc=$(run list X --json); ok "7 list --json: open B4, B5; no closed ones" 'python3 -c "import json,sys; L=json.load(open(\"$T/out\")); sys.exit(0 if [b[\"id\"] for b in L]==[\"B4\",\"B5\"] else 1)"'
rc=$(run add Nope a b c); ok "8 no such project -> rc 4" '[ "$rc" = 4 ]'
# 9 an agent edited the register (its own Edit tool) between our read and our write -> our write must not overwrite it
cat > "$T/race.py" <<'PY'
import importlib.machinery, importlib.util, os, sys, time
os.environ["BLOCKERS_STATE"] = sys.argv[3]
sp = importlib.util.spec_from_file_location("bl", sys.argv[1], loader=importlib.machinery.SourceFileLoader("bl", sys.argv[1])); bl = importlib.util.module_from_spec(sp); sp.loader.exec_module(bl)
p = sys.argv[2]; seen = bl.mt(p); lines = open(p).read().split("\n")
time.sleep(0.02); open(p, "a").write("| B99 | agent edit | human | `manual` | 2026-10-28 | |\n")
print("write:", bl.write(p, lines + ["spoiled our write"], seen))
PY
python3 "$T/race.py" "$BL" "$R/Project-X/BLOCKERS.md" "$T/state" > "$T/out" 2>&1
ok "9 file changed under us -> write False, the agent's edit intact, our line not written" 'grep -q "write: False" "$T/out" && grep -q "B99 | agent edit" "$R/Project-X/BLOCKERS.md" && ! grep -q "spoiled" "$R/Project-X/BLOCKERS.md"'
# a row appended without approval is not executed - even when the command would go green
rm -f "$T/pwn" "$T/post.log"; mkdir -p "$R/Agents/X-HQ"
printf '| B20 | foreign row | someone | `touch %s/pwn` | 2026-11-02 | |\n' "$T" >> "$R/Project-X/BLOCKERS.md"
rc=$(run run); ok "10 unapproved command not run, blocker stays open, message to the lead" '[ ! -e "$T/pwn" ] && grep -q "^| B20 |" "$R/Project-X/BLOCKERS.md" && grep -q "^X-HQ .*B20" "$T/post.log"'
rc=$(run run --dry); ok "10b --dry does not run it either" '[ ! -e "$T/pwn" ]'
rc=$(run run); ok "10c one message to the lead per command" '[ "$(grep -c "^X-HQ .*B20" "$T/post.log")" = 1 ]'
rc=$(run approve X B20); ok "11 approve prints the command, the next pass runs it" '[ "$rc" = 0 ] && grep -q "touch" "$T/out" && [ "$(run run)" = 0 ] && [ -e "$T/pwn" ] && grep -q "^| ✅ B20 |" "$R/Project-X/BLOCKERS.md"'
rm -f "$T/pwn2"; printf '| B21 | swap | someone | `test -e %s/nope` | 2026-11-02 | |\n' "$T" >> "$R/Project-X/BLOCKERS.md"
rc=$(run approve X B21); sed -i "s#test -e $T/nope#touch $T/pwn2#" "$R/Project-X/BLOCKERS.md"
rc=$(run run); ok "12 an approved command was swapped in the file -> the new one is not run" '[ ! -e "$T/pwn2" ] && grep -q "^| B21 |" "$R/Project-X/BLOCKERS.md"'
sed -i "s#touch $T/pwn2#true#" "$R/Project-X/BLOCKERS.md"; rc=$(run approve X B21); chmod 644 "$T/state/approved-checks.json"; rc=$(run run)
ok "13 approvals file open to others -> nothing is run" 'grep -q "^| B21 |" "$R/Project-X/BLOCKERS.md" && grep -q "not owner-only 0600" "$LOG"'
chmod 600 "$T/state/approved-checks.json"
rc=$(run add X "new" "human" "test -e $T/nope3"); touch "$T/nope3"; rc=$(run run); ok "14 a command written by add is approved by add itself" 'grep -q "^| ✅ B[0-9]* | new" "$R/Project-X/BLOCKERS.md"'
mkdir -p "$R/Project-Y"; printf '| B1 | a | b | `manual` | 2026-11-02 | |\n' > "$R/Project-Y/BLOCKERS.md"
rc=$(run clear Y B1 "human"); ok "16 clear without ROADMAP -> rc 0, blocker ✅, no traceback" '[ "$rc" = 0 ] && grep -q "^| ✅ B1" "$R/Project-Y/BLOCKERS.md" && ! grep -q Traceback "$T/out"'
mkdir -p "$R/Project-E"; rc=$(run clear E B1 "x"); ok "17 clear in a project without BLOCKERS.md -> rc 4, no traceback" '[ "$rc" = 4 ] && ! grep -q Traceback "$T/out"'
mkdir -p "$R/Project-A0"; printf '| B1 | a | b | `true` | 2026-11-02 | |\n' > "$R/Project-A0/BLOCKERS.md"; rc=$(run approve A0 B1)
echo x > "$R/Project-A0/ROADMAP.md"; mkdir "$R/Project-A0/ROADMAP.md.lock"; rc=$(run run)
ok "18 a crash in one project does not leave the rest: reason in the log, Project-X passed" 'grep -q "Project-A0/BLOCKERS.md: pass crashed" "$LOG" && grep -q "Project-X:" "$T/out"'
# 19 another project glob: CCM_PROJECTS_GLOB=Work-*
mkdir -p "$R/Work-Z"; printf '| B1 | a | b | `manual` | 2026-11-02 | |\n' > "$R/Work-Z/BLOCKERS.md"
out=$(cd "$R" && CCM_PROJECTS_GLOB='Work-*' BLOCKERS_REPO="$R" BLOCKERS_POST="$T/post" BLOCKERS_STATE="$T/state" python3 "$BL" list Z 2>&1); echo "$out" > "$T/out"
ok "19 CCM_PROJECTS_GLOB=Work-* -> short name Z finds Work-Z" 'grep -q "^Z B1" "$T/out"'
echo "blockers: $pass pass, $fail fail"; [ $fail = 0 ]
