#!/usr/bin/env bash
# new_project.sh in a sandbox: all files, agents, commits; repeat and a foreign agent -> refusal; a failed step is named.
# NP=<path> tests another copy.
set -u
HERE=$(dirname "$(readlink -f "$0")")
NP=${NP:-$HERE/../scripts/new_project.sh}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
R="$T/repo"; mkdir -p "$R/Agents" "$T/h"; printf 'x\n' > "$R/.gitignore"
g() { git -c safe.directory='*' -C "$@"; }
g "$R" init -q -b master; g "$R" config user.email t@t; g "$R" config user.name t; g "$R" add -A; g "$R" commit -qm i
cat > "$T/reg" <<E
#!/bin/sh
mkdir -p "$R/Agents/\$1"; echo "# \$1" > "$R/Agents/\$1/briefing.md"
[ -e "$T/reg-fail" ] && exit 5
exit 0
E
chmod +x "$T/reg"
printf "Old-HQ\n" > "$T/wga"
envs() { env HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$R" GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t "$@"; }
run() { envs CCM_PROJECT_WATCH_DOCS="TEAM-WORK.md" CCM_PROJECT_WATCH_DOCS_HQ="METHOD.md" CCM_WORK_GUARD_AGENTS="$T/wga" bash "$NP" "$@" > "$T/out" 2>&1; echo $?; }
runreg() { envs CCM_REGISTER_AGENT="$T/reg" bash "$NP" "$@" > "$T/out" 2>&1; echo $?; }
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; sed 's/^/   /' "$T/out"; fi; }
rc=$(run --own-repo Foo)
ok "1 project created: files, own repo" '[ "$rc" = 0 ] && [ -f "$R/Project-Foo/release.toml" ] && [ -f "$R/Project-Foo/ROADMAP.md" ] && [ -f "$R/Project-Foo/BLOCKERS.md" ] && [ -e "$R/Project-Foo/.git" ]'
ok "1b release.toml parses, lead Foo-HQ" 'python3 -c "import tomllib,sys; d=tomllib.load(open(\"$R/Project-Foo/release.toml\",\"rb\")); sys.exit(0 if d[\"hq\"]==\"Foo-HQ\" else 1)"'
ok "1c first commit in the project repo, top .gitignore committed" '[ "$(g "$R/Project-Foo" log --oneline | wc -l)" = 1 ] && g "$R" log -1 --format=%s | grep -q Project-Foo && g "$R" diff --quiet -- .gitignore && grep -qx "/Project-Foo/" "$R/.gitignore"'
ok "1d built-in scaffold: briefing, inbox, both todo files" 'for f in briefing.md inbox.md agent-TODO.md human-TODO.md; do [ -f "$R/Agents/Foo-HQ/$f" ] && [ -f "$R/Agents/Foo-Dev/$f" ] || exit 1; done'
ok "1e watch docs: team doc for both, method doc for the lead only" 'grep -qx TEAM-WORK.md "$R/Agents/Foo-HQ/.watchlist" && grep -qx TEAM-WORK.md "$R/Agents/Foo-Dev/.watchlist" && grep -qx METHOD.md "$R/Agents/Foo-HQ/.watchlist" && ! grep -qx METHOD.md "$R/Agents/Foo-Dev/.watchlist"'
ok "1f agents in the alarm list with a comment, old entries intact" 'grep -qx Foo-HQ "$T/wga" && grep -qx Foo-Dev "$T/wga" && grep -q "^# Foo (new_project.sh" "$T/wga" && grep -qx Old-HQ "$T/wga"'
rc=$(run --own-repo --profile web Web); ok "2 --profile web -> test/uat/prod" '[ "$rc" = 0 ] && python3 -c "import tomllib,sys; sys.exit(0 if tomllib.load(open(\"$R/Project-Web/release.toml\",\"rb\"))[\"stands\"]==[\"test\",\"uat\",\"prod\"] else 1)"'
rc=$(run --no-code --profile game Gm); ok "2b --profile game -> dev-build/playtest" '[ "$rc" = 0 ] && grep -q "stands = \[\"dev-build\", \"playtest\"\]" "$R/Project-Gm/release.toml"'
rc=$(run --no-code --profile xx Bad); ok "2c unknown profile -> rc 2, no project" '[ "$rc" = 2 ] && [ ! -e "$R/Project-Bad" ]'
rc=$(run --no-code Foo); ok "3 repeat -> rc 3, nothing changed" '[ "$rc" = 3 ] && [ "$(g "$R/Project-Foo" log --oneline | wc -l)" = 1 ]'
rc=$(run --no-code Bar Foo-HQ); ok "4 the agent already exists -> rc 3, no project" '[ "$rc" = 3 ] && [ ! -e "$R/Project-Bar" ]'
rc=$(run --no-code 'x/../y'); ok "5 bad name -> rc 2" '[ "$rc" = 2 ]'
rm "$R/.gitignore"; mkdir "$R/.gitignore"; rc=$(run --own-repo Baz); ok "6 a step fails -> rc 4, the step is named, the project folder stays" '[ "$rc" = 4 ] && grep -q "top-level .gitignore" "$T/out" && [ -d "$R/Project-Baz" ]'; rmdir "$R/.gitignore"; printf 'x\n' > "$R/.gitignore"; rm -rf "$R/Project-Baz"
touch "$T/reg-fail"; rc=$(runreg --no-code Qux Q-HQ); ok "7 registrar hook fails -> rc 4, step \"agents\"" '[ "$rc" = 4 ] && grep -q "\"agents\"" "$T/out"'; rm "$T/reg-fail"
rc=$(run --no-code Own Own-HQ Own-X Own-Y); ok "8 own agent set, the first is the lead" '[ "$rc" = 0 ] && [ -d "$R/Agents/Own-Y" ] && grep -q "hq = \"Own-HQ\"" "$R/Project-Own/release.toml"'
top=$(g "$R" rev-parse HEAD); rc=$(run --no-code Plain); ok "9 --no-code: a folder in the shared repo, no .git of its own, top repo not committed, files exist" '[ "$rc" = 0 ] && [ ! -e "$R/Project-Plain/.git" ] && [ -f "$R/Project-Plain/release.toml" ] && [ "$(g "$R" rev-parse HEAD)" = "$top" ] && grep -q "folder in the shared repo" "$T/out" && ! grep -q Project-Plain "$R/.gitignore"'
ok "9b repeats do not duplicate lines" '[ "$(grep -cx Foo-HQ "$T/wga")" = 1 ]'
mkdir -p "$R/Agents/Amb-HQ"; echo "# my briefing" > "$R/Agents/Amb-HQ/briefing.md"; echo STANDARD.md > "$R/Agents/Amb-HQ/.watchlist"
rc=$(run --no-code Amb); ok "10 lead already exists -> attached, rc 0, briefing intact, Dev created, .watchlist extended without duplicates" '[ "$rc" = 0 ] && [ -f "$R/Project-Amb/release.toml" ] && [ "$(cat "$R/Agents/Amb-HQ/briefing.md")" = "# my briefing" ] && [ -d "$R/Agents/Amb-Dev" ] && grep -qx METHOD.md "$R/Agents/Amb-HQ/.watchlist" && [ "$(grep -cx STANDARD.md "$R/Agents/Amb-HQ/.watchlist")" = 1 ] && grep -qx Amb-HQ "$T/wga"'
mkdir -p "$R/Agents/Bz-Dev"; echo x > "$R/Agents/Bz-Dev/briefing.md"
rc=$(run --no-code Bz); ok "10b the existing one is not the lead but Dev -> rc 3, no project" '[ "$rc" = 3 ] && [ ! -e "$R/Project-Bz" ]'
rc=$(run Nope); ok "11 neither --own-repo nor --no-code -> rc 2 with the hint, no project" '[ "$rc" = 2 ] && grep -q "say explicitly" "$T/out" && [ ! -e "$R/Project-Nope" ]'
rc=$(run --own-repo --no-code Both); ok "11b both together -> rc 2" '[ "$rc" = 2 ] && [ ! -e "$R/Project-Both" ]'
rc=$(envs bash "$NP" --no-code Mini > "$T/out" 2>&1; echo $?); ok "12 no optional keys set -> works, no alarm file, no .watchlist" '[ "$rc" = 0 ] && [ ! -e "$R/Agents/Mini-HQ/.watchlist" ]'
rc=$(envs CCM_PROJECTS_SITE=projects.example.lan bash "$NP" --no-code Site > "$T/out" 2>&1; echo $?); ok "12b projects site key -> mentioned once" '[ "$rc" = 0 ] && grep -q "projects.example.lan" "$T/out"'
echo "new-project: $pass pass, $fail fail"; [ $fail = 0 ]
