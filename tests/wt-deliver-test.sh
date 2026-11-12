#!/usr/bin/env bash
# wt_deliver: delivery from an agent worktree into master - in a sandbox clone. Scenarios: clean ff · someone else's file ->
# refusal · red test -> refusal · dirty worktree · conflict · master moved. In every refusal master did NOT move - checked by
# the effect (sha before/after). WD=<path> tests another copy.
set -u
HERE=$(dirname "$(readlink -f "$0")")
WD=${WD:-$HERE/../scripts/wt_deliver.sh}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
R="$T/repo"; W="$T/wt"; mkdir -p "$R" "$W" "$T/h"
g() { /usr/bin/git -c user.email=t@t -c user.name=t "$@"; }
g -C "$R" init -q -b master
mkdir -p "$R/Project-X/src" "$R/Project-X/ui" "$R/Docs"
cat > "$R/Project-X/deliver.conf" <<'C'
AGENTS=X-Dev X-UI
DIR=Project-X
TEST=test ! -e RED && echo tests ok
BUILD=echo built > build.out
OWNERS=Project-X/OWNERS
C
printf '# owners\nProject-X/** X-HQ\nProject-X/src/** X-Dev\nProject-X/ui/** X-UI\nProject-X/*.png *\n' > "$R/Project-X/OWNERS"
printf 'build.out\n' > "$R/.gitignore"
echo a > "$R/Project-X/src/a.js"; echo u > "$R/Project-X/ui/u.js"; echo d > "$R/Docs/d.md"
g -C "$R" add -A; g -C "$R" commit -qm init
g -C "$R" worktree add -q -b x-dev "$W/X-Dev" master
g -C "$R" worktree add -q -b x-ui "$W/X-UI" master
P="$T/post.log"; printf '#!/bin/sh\necho "$@" >> %s\n' "$P" > "$T/post"; chmod +x "$T/post"
run() { GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$R" CCM_WORKTREES_DIR="$W" CCM_WT_DELIVER_LOG="$T/log" CCM_INBOX_POST="$T/post" bash "$WD" "$@" > "$T/out" 2>&1; echo $?; }
m() { g -C "$R" rev-parse master; }
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; sed 's/^/   /' "$T/out"; fi; }

# 1 clean case: own file, master moved by docs (no conflict) -> ff, build, letter
echo a2 >> "$W/X-Dev/Project-X/src/a.js"; g -C "$W/X-Dev" commit -qam "dev: a2"
echo d2 >> "$R/Docs/d.md"; g -C "$R" commit -qam "docs"
rc=$(run X-Dev)
ok "1 own file -> rc 0, master = branch, master has both the doc and the edit" '[ "$rc" = 0 ] && [ "$(m)" = "$(g -C "$W/X-Dev" rev-parse HEAD)" ] && grep -q a2 "$R/Project-X/src/a.js" && grep -q d2 "$R/Docs/d.md"'
ok "1b build in the main tree, letter \"delivered\"" '[ -f "$R/Project-X/build.out" ] && grep -q "X-Dev.*delivered" "$P"'
rc=$(run X-Dev); ok "1c repeat with nothing new -> \"nothing to deliver\", rc 0" '[ "$rc" = 0 ] && grep -q "nothing to deliver" "$T/out"'

# 2 someone else's file -> refusal, master in place
g -C "$W/X-UI" merge -q master; echo hack >> "$W/X-UI/Project-X/src/a.js"; echo u2 >> "$W/X-UI/Project-X/ui/u.js"; g -C "$W/X-UI" commit -qam "ui: reaches into src"
m0=$(m); rc=$(run X-UI)
ok "2 someone else's file -> rc 6, master did not move, file and owner named" '[ "$rc" = 6 ] && [ "$(m)" = "$m0" ] && grep -q "src/a.js (X-Dev)" "$T/out" && grep -q "X-UI.*NOT accepted" "$P"'
g -C "$W/X-UI" reset -q --hard master

# 2b nobody's file (outside OWNERS) -> refusal; *.png belongs to anyone
echo x > "$W/X-UI/Docs/ui-notes.md"; echo p > "$W/X-UI/Project-X/shot.png"; g -C "$W/X-UI" add -A; g -C "$W/X-UI" commit -qm "ui: a note outside the project"
m0=$(m); rc=$(run X-UI)
ok "2b file outside OWNERS -> rc 6 \"nobody\"; png under \"*\" does not complain" '[ "$rc" = 6 ] && [ "$(m)" = "$m0" ] && grep -q "Docs/ui-notes.md (nobody)" "$T/out" && ! grep -q "shot.png" "$T/out"'
g -C "$W/X-UI" reset -q --hard master

# 3 red test -> refusal
echo r > "$W/X-Dev/Project-X/RED"; echo a3 >> "$W/X-Dev/Project-X/src/a.js"; g -C "$W/X-Dev" add -A; g -C "$W/X-Dev" commit -qm "dev: red"
m0=$(m); rc=$(run X-Dev)
ok "3 red test -> rc 5, master did not move" '[ "$rc" = 5 ] && [ "$(m)" = "$m0" ] && grep -q "is red" "$T/out"'
g -C "$W/X-Dev" rm -q Project-X/RED; g -C "$W/X-Dev" commit -qm "dev: removed"

# 4 dirty worktree -> refusal
echo wip >> "$W/X-Dev/Project-X/src/a.js"
m0=$(m); rc=$(run X-Dev)
ok "4 uncommitted in the worktree -> rc 3, master did not move" '[ "$rc" = 3 ] && [ "$(m)" = "$m0" ]'
g -C "$W/X-Dev" checkout -q -- Project-X/src/a.js

# 5 conflict with master -> refusal, the worktree has no half-merge
echo "from master" > "$R/Project-X/src/a.js"; g -C "$R" commit -qam "master changes a.js"
echo "from branch" > "$W/X-Dev/Project-X/src/a.js"; g -C "$W/X-Dev" commit -qam "dev: other a.js"
m0=$(m); rc=$(run X-Dev)
ok "5 conflict -> rc 4, master did not move, no MERGE_HEAD in the worktree" '[ "$rc" = 4 ] && [ "$(m)" = "$m0" ] && ! g -C "$W/X-Dev" rev-parse -q --verify MERGE_HEAD >/dev/null && grep -q "src/a.js" "$T/out"'

# 7 an uncommitted edit of the same file in the main tree -> ff impossible, refusal naming the file; master did not move
g -C "$W/X-UI" merge -q master; echo u7 >> "$W/X-UI/Project-X/ui/u.js"; g -C "$W/X-UI" commit -qam "ui: u7"
echo "by hand in master" >> "$R/Project-X/ui/u.js"
m0=$(m); rc=$(run X-UI)
ok "7 uncommitted in the main tree -> rc 7, file named, master did not move, the edit was not eaten" '[ "$rc" = 7 ] && [ "$(m)" = "$m0" ] && grep -q "ui/u.js" "$T/out" && grep -q "by hand in master" "$R/Project-X/ui/u.js"'
g -C "$R" checkout -q -- Project-X/ui/u.js
rc=$(run X-UI); ok "7b main tree clean -> delivered" '[ "$rc" = 0 ] && grep -q u7 "$R/Project-X/ui/u.js"'

# 8 a non-ASCII file name (git without quotepath=off would give "\320..." -> "nobody" -> a false refusal)
mkdir -p "$W/X-Dev/Project-X/src/dáta"; g -C "$W/X-Dev" reset -q --hard master; echo k > "$W/X-Dev/Project-X/src/dáta/mäp-ж.json"; g -C "$W/X-Dev" add -A; g -C "$W/X-Dev" commit -qm "dev: non-ASCII"
rc=$(run X-Dev); ok "8 non-ASCII path in own folder -> delivered" '[ "$rc" = 0 ] && [ -f "$R/Project-X/src/dáta/mäp-ж.json" ]'

# 9 renaming someone else's file into your folder -> refusal by the OLD path
g -C "$W/X-UI" reset -q --hard master; g -C "$W/X-UI" mv Project-X/src/a.js Project-X/ui/a.js; g -C "$W/X-UI" commit -qm "ui: took a.js"
m0=$(m); rc=$(run X-UI); ok "9 mv of someone else's file -> rc 6, src/a.js (X-Dev) named" '[ "$rc" = 6 ] && [ "$(m)" = "$m0" ] && grep -q "src/a.js (X-Dev)" "$T/out"'
g -C "$W/X-UI" reset -q --hard master

# 10 a broken OWNERS line -> refusal, not "delivered blind"
cp "$R/Project-X/OWNERS" "$T/owners.bak"; echo 'Project-X/docs' >> "$R/Project-X/OWNERS"; g -C "$R" commit -qam "owners: broken line"
echo u10 >> "$W/X-UI/Project-X/ui/u.js"; g -C "$W/X-UI" commit -qam "ui: u10"
m0=$(m); rc=$(run X-UI); ok "10 OWNERS does not parse -> rc 6 \"did not run\", master did not move" '[ "$rc" = 6 ] && [ "$(m)" = "$m0" ] && grep -q "did not run" "$T/out" && grep -q "line" "$T/out"'
cp "$T/owners.bak" "$R/Project-X/OWNERS"; g -C "$R" commit -qam "owners: fixed"

# 11 a new thing in the worktree not added to git -> dirty
echo dep > "$W/X-UI/Project-X/ui/dep.js"
m0=$(m); rc=$(run X-UI); ok "11 a file not added in the worktree -> rc 3 with its name" '[ "$rc" = 3 ] && [ "$(m)" = "$m0" ] && grep -q "ui/dep.js" "$T/out"'
rm "$W/X-UI/Project-X/ui/dep.js"

# 12 the main tree is not on master -> refusal
g -C "$R" checkout -q -b other
rc=$(run X-UI); ok "12 main tree on another branch -> rc 2" '[ "$rc" = 2 ] && grep -q "is not on master" "$T/out"'
g -C "$R" checkout -q master
rc=$(run X-UI); ok "12b back on master -> delivered" '[ "$rc" = 0 ] && grep -q u10 "$R/Project-X/ui/u.js"'

# 6 unknown agent / no argument
rc=$(run Nobody); ok "6 the agent is not in deliver.conf -> rc 2" '[ "$rc" = 2 ]'
rc=$(run); ok "6b no argument -> rc 2" '[ "$rc" = 2 ]'
# 13 a project in its own repo: its own storage, the workspace master does not move, OWNERS patterns from the workspace root
O="$R/Project-O"; mkdir -p "$O/src"; g -C "$O" init -q -b master
printf 'AGENTS=O-Dev\nDIR=Project-O\nTEST=test ! -e RED\nBUILD=true\nOWNERS=Project-O/OWNERS\n' > "$O/deliver.conf"; printf 'Project-O/** O-HQ\nProject-O/src/** O-Dev\n' > "$O/OWNERS"; echo a > "$O/src/a"; echo b > "$O/b"
g -C "$O" add -A; g -C "$O" commit -qm i; g -C "$O" worktree add -q -b o-dev "$W/O-Dev" master; mono=$(m)
echo 2 > "$W/O-Dev/src/a"; g -C "$W/O-Dev" add -A; g -C "$W/O-Dev" commit -qm s; rc=$(run O-Dev)
ok "13 own file in its own repo -> delivered into ITS master, the workspace did not move" '[ "$rc" = 0 ] && grep -q 2 "$O/src/a" && [ "$(m)" = "$mono" ]'
o0=$(g -C "$O" rev-parse master); echo 3 > "$W/O-Dev/b"; g -C "$W/O-Dev" add -A; g -C "$W/O-Dev" commit -qm b; rc=$(run O-Dev)
ok "13b someone else's file in its own repo -> refusal per OWNERS" '[ "$rc" != 0 ] && [ "$(g -C "$O" rev-parse master)" = "$o0" ] && grep -q "b (O-HQ)" "$T/out"'
echo "wt-deliver: $pass pass, $fail fail"; [ $fail = 0 ]
