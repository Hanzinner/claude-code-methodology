#!/usr/bin/env bash
# git_empty_objects_check.sh. GE=<path> tests another copy. Uses a throw-away git repo.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" HANZ_TEST=1 CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_AGENTS_DIR="$T/Agents"; mkdir -p "$HOME" "$T/ws"
printf "#!/bin/sh\necho \"\$1|\${2:-\$(cat)}\" >> %s/letters\n" "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/letters"; export CCM_INBOX_POST="$T/post"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | sed "s/^/   /"; fi; }
GE=${GE:-$HERE/../scripts/git_empty_objects_check.sh}
R="$T/repo"; mkdir -p "$R"; ( cd "$R" && git init -q . && git config user.email t@t && git config user.name t && echo a > a && git add a && git commit -qm i )
export REPO="$R" STATE="$T/state"
out=$(CCM_GIT_KEEPER=Keeper bash "$GE" 2>&1); rc=$?
ok "1 healthy repo -> rc 0, no letter" '[ $rc = 0 ] && [ ! -s "$T/letters" ]'
obj=$(find "$R/.git/objects" -type f | grep -v pack | head -1); chmod u+w "$obj"; : > "$obj"   # git writes objects 0444: only root could truncate without chmod
out=$(CCM_GIT_KEEPER=Keeper bash "$GE" 2>&1); rc=$?
ok "2 a zero-byte object -> rc 1 and ONE letter with the path" '[ $rc = 1 ] && [ "$(grep -c "^Keeper|" "$T/letters")" = 1 ] && grep -q "objects/" "$T/letters"'
out=$(CCM_GIT_KEEPER=Keeper bash "$GE" 2>&1); rc=$?
ok "3 the same set again -> rc 1 but no second letter" '[ $rc = 1 ] && [ "$(grep -c "^Keeper|" "$T/letters")" = 1 ]'
: > "$T/letters"; rm -f "$STATE"; out=$(bash "$GE" 2>&1); rc=$?
ok "4 keeper empty -> rc 1, no letter, repo not touched" '[ $rc = 1 ] && [ ! -s "$T/letters" ] && [ -f "$obj" ]'
out=$(REPO="$T/nothing" bash "$GE" 2>&1); rc=$?
ok "5 not a git repo -> rc 0, nothing to check" '[ $rc = 0 ]'
rm -f "$obj"; out=$(bash "$GE" 2>&1); rc=$?
ok "6 repaired (object gone) -> rc 0 and the state is cleared" '[ $rc = 0 ] && [ ! -f "$STATE" ]'
echo "git-empty-objects: $pass pass, $fail fail"; [ $fail = 0 ]
