#!/usr/bin/env bash
# story_status.py in a sandbox: prints the roadmap line, blocker state, open agent items, commits and code carrying the code.
# SS=<path> tests another copy.
HERE="$(cd "$(dirname "$0")" && pwd)"
SS=${SS:-$HERE/../scripts/story_status.py}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent GIT_CONFIG_GLOBAL=/dev/null; mkdir -p "$HOME"
R="$T/repo"; mkdir -p "$R/Project-X" "$R/Agents/X-Dev"
cat > "$R/Project-X/ROADMAP.md" <<'B'
- ⏳ **[E1.S68] Staff address** X-Dev · `blockers: B1, B2`
- 🔄 **[E1.S7] Other**
B
cat > "$R/Project-X/BLOCKERS.md" <<'B'
| B1 | token | human | `true` | 2026-10-20 | |
| ✅ B2 | zone | human | `true` | 2026-10-20 | |
B
printf -- '- [ ] S68 write the router\n- [x] S68 old item\n- [ ] S7 other\n' > "$R/Agents/X-Dev/agent-TODO.md"
echo '# S68 router' > "$R/Project-X/app.py"
( cd "$R" && git init -q && git add -A && git -c user.email=a@b -c user.name=t commit -qm "S68 router skeleton" )
out=$(python3 "$SS" X S68 2>&1); rc=$?
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "$out" | sed 's/^/   /'; fi; }
export STORY_REPO="$R"; out=$(python3 "$SS" X S68 2>&1); rc=$?
ok "1 roadmap line shown" '[ $rc = 0 ] && echo "$out" | grep -q "ROADMAP.md:1: - ⏳ \*\*\[E1.S68\]"'
ok "2 blocker B1 OPEN, B2 CLEARED" 'echo "$out" | grep -q "blocker B1: OPEN" && echo "$out" | grep -q "blocker B2: CLEARED"'
ok "3 only the open item of this story (not S7, not the [x] one)" 'echo "$out" | grep -q "agent-TODO.md:1:.*S68 write the router" && ! echo "$out" | grep -q "S7 other" && ! echo "$out" | grep -q "old item"'
ok "4 commit with the code and the code file" 'echo "$out" | grep -q "S68 router skeleton" && echo "$out" | grep -q "Project-X/app.py"'
out=$(python3 "$SS" X S999 2>&1); ok "5 unknown story -> no roadmap line, 'none' markers, rc 0" '[ $? = 0 ] && ! echo "$out" | grep -q "ROADMAP.md:" && echo "$out" | grep -q "none"'
out=$(python3 "$SS" Nope S1 2>&1); rc=$?; ok "6 unknown project -> rc 4" '[ $rc = 4 ]'
out=$(python3 "$SS" 2>&1); rc=$?; ok "7 wrong usage -> rc 2" '[ $rc = 2 ]'
echo "story-status: $pass pass, $fail fail"; [ $fail = 0 ]
