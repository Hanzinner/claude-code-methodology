#!/usr/bin/env bash
# project_drift.py: every red reason, pause, a project without code, zero projects = broken. PD=<path> tests another copy.
set -u
HERE=$(dirname "$(readlink -f "$0")")
PD=${PD:-$HERE/../scripts/project_drift.py}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; R="$T/r"; S="$T/s"; mkdir -p "$R/Agents" "$S" "$T/h"
: > "$R/Agents/paused-projects.txt"
run() { HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$R" CCM_RELEASER_STATE="$S" python3 "$PD" > "$T/out" 2>&1; echo $?; }
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; sed 's/^/   /' "$T/out"; fi; }
rc=$(run); ok "0 zero projects -> rc 3" '[ "$rc" = 3 ]'
mk() { mkdir -p "$R/Project-$1/.git"; echo x > "$R/Project-$1/a.py"; }
mk A; rc=$(run); ok "1 no release.toml -> red" '[ "$rc" = 1 ] && grep -q "Project-A: no release.toml" "$T/out"'
echo 'this = =' > "$R/Project-A/release.toml"; rc=$(run); ok "2 broken toml" 'grep -q "does not parse" "$T/out"'
echo 'test = ""' > "$R/Project-A/release.toml"; rc=$(run); ok "3 no gate" 'grep -q "no gate command" "$T/out"'
echo 'test = "true"' > "$R/Project-A/release.toml"; rc=$(run); ok "4 the releaser never ran" 'grep -q "has not run yet" "$T/out"'
printf '{"ts":%s,"result":"green"}' $(( $(date +%s) - 9*86400 )) > "$S/Project-A.json"; rc=$(run); ok "5 last run too old" 'grep -q "9 days ago" "$T/out"'
printf '{"ts":%s,"result":"red","detail":"broke"}' $(date +%s) > "$S/Project-A.json"; rc=$(run); ok "6 last result red" 'grep -q "result red: broke" "$T/out"'
printf '{"ts":%s,"result":"green"}' $(date +%s) > "$S/Project-A.json"; rc=$(run); ok "7 fresh green -> rc 0" '[ "$rc" = 0 ] && grep -q "projects checked 1, red 0" "$T/out" && grep -q "\"red\": {}" "$S/drift.json"'
mkdir -p "$R/Project-Docs"; echo t > "$R/Project-Docs/a.md"; rc=$(run); ok "8 a project without code is not counted" '[ "$rc" = 0 ] && grep -q "checked 1" "$T/out"'
mk P; echo Project-P > "$R/Agents/paused-projects.txt"; rc=$(run); ok "9 a paused project stays quiet" '[ "$rc" = 0 ]'
mkdir -p "$R/Project-M"; echo x > "$R/Project-M/a.py"; rc=$(run); ok "10 code in the monorepo -> red" '[ "$rc" = 1 ] && grep -q "Project-M: no repo of its own" "$T/out"'
echo "project-drift: $pass pass, $fail fail"; [ $fail = 0 ]
