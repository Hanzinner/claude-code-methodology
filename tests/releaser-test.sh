#!/usr/bin/env bash
# releaser.py in a sandbox (needs root: it switches between two users). Main point: the shared tree after the gates is
# byte-for-byte the same and its owner is unchanged; the gates run as a separate user (here `nobody`) and cannot write
# into it. Green -> ff into master by the owner (here root). REL=<path> tests another copy.
set -u
HERE=$(dirname "$(readlink -f "$0")")
REL=${REL:-$HERE/../scripts/releaser.py}
if [ "$(id -u)" != 0 ] || ! id nobody >/dev/null 2>&1; then echo "releaser: 0 pass, 0 fail (skipped: needs root and a user 'nobody')"; exit 0; fi
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; chmod 755 "$T"
R="$T/repo"; O="$R/Project-X"; S="$T/state"; mkdir -p "$O" "$S" "$T/home"
printf '#!/bin/sh\necho "$1 $(cat)" >> %s/post.log\n' "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/post.log"
cat > "$O/release.toml" <<E
hq = "X-HQ"
test = "test ! -e BAD"
E
echo a > "$O/a"; printf '.q\nnode_modules\n' > "$O/.gitignore"
g() { /usr/bin/git -c safe.directory='*' -C "$@"; }
g "$O" init -q -b master; g "$O" config user.email t@t; g "$O" config user.name t; g "$O" add -A; g "$O" commit -qm init
wt() { g "$O" worktree add -q "$T/wt-$1" -b "$1" master; }
commit() { # commit <branch> <file> <text>
  echo "$3" > "$T/wt-$1/$2"; g "$T/wt-$1" add -A; g "$T/wt-$1" commit -qm "$2"; g "$T/wt-$1" rev-parse HEAD; }
env_() { env HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$R" CCM_INBOX_POST="$T/post" CCM_RELEASER_APPROVED="$T/approved.json" CCM_RELEASER_LOG="$T/log" CCM_RELEASER_STATE="$S" CCM_RELEASER_USER=nobody CCM_RELEASER_OWNER=root "$@"; }
run() { (cd "$R" && env_ python3 "$REL" "$@") > "$T/out" 2>&1; echo $?; }
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; sed 's/^/   /' "$T/out" | tail -5; tail -3 "$T/log" 2>/dev/null | cut -c1-300; fi; }
mark() { mkdir -p "$S/queue/Project-X"; printf '{"sha":"%s","agent":"%s","summary":"s"}' "$2" "${3:-X-Dev}" > "$S/queue/Project-X/$1.ready"; }
head_() { g "$O" rev-parse master; }
# fingerprint of the shared tree: path, owner, mode, content (outside .git/)
snap() { (cd "$O" && find . -path ./.git -prune -o -printf '%p %u %m\n' | sort; find . -path ./.git -prune -o -type f -print0 | sort -z | xargs -0 sha256sum); }
owners() { find "$O" ! -user root | wc -l; }

wt dev; S1=$(commit dev b b); M0=$(head_)
mark dev "$S1"; rc=$(run run)
ok "1 unapproved command -> nothing executed, master in place, letter to the lead" '[ "$(head_)" = "$M0" ] && grep -q "^X-HQ .*approve X" "$T/post.log" && [ -e "$S/queue/Project-X/dev.ready" ]'
rc=$(run run); ok "1b only one letter about approval" '[ "$(grep -c "^X-HQ .*approve X" "$T/post.log")" = 1 ]'
rc=$(run approve X); ok "2 approve prints the command" '[ "$rc" = 0 ] && grep -q "test ! -e BAD" "$T/out"'
rc=$(run run)
ok "3 green -> master has the sha, file in tree, marker gone, letter to the author" 'g "$O" merge-base --is-ancestor "$S1" master && [ -e "$O/b" ] && [ ! -e "$S/queue/Project-X/dev.ready" ] && grep -q "^X-Dev .*green" "$T/post.log"'
ok "3b owners of the shared tree unchanged, the releaser clone belongs to nobody" '[ "$(owners)" = 0 ] && [ "$(stat -c %U "$S/work/Project-X/.git")" = nobody ] && grep -q "\"result\": \"green\"" "$S/Project-X.json"'

# 4 MAIN: the gate tries to write into the shared tree and fails red -> tree byte-for-byte the same
sed -i "s#^test = .*#test = \"id -un > $T/who; touch $O/pwn; echo x >> $O/a; test ! -e BAD\"#" "$O/release.toml"; rc=$(run approve X); chmod 777 "$T"
wt bad; S2=$(commit bad BAD x); M1=$(head_); : > "$T/post.log"; before=$(snap)
mark bad "$S2"; rc=$(run run)
ok "4 the gate runs as the separate user, not root" '[ "$(cat "$T/who")" = nobody ]'
ok "4b shared tree after a red run is byte-for-byte the same, the gate write did not go through" '[ "$(snap)" = "$before" ] && [ ! -e "$O/pwn" ] && [ "$(owners)" = 0 ]'
ok "4c master in place, .failed, letter, marker stays" '[ "$(head_)" = "$M1" ] && [ -e "$S/queue/Project-X/bad.ready.failed" ] && grep -q "^X-Dev .*NOT merged (gate)" "$T/post.log" && [ -e "$S/queue/Project-X/bad.ready" ]'
cp -p "$O/a" "$T/a.bak"; echo y >> "$O/a"; ok "4d control: a change in the tree changes the fingerprint" '[ "$(snap)" != "$before" ]'; cp -p "$T/a.bak" "$O/a"
n=$(grep -c START "$T/log"); rc=$(run run)
ok "4e the same sha is not run again, no second letter" '[ "$(grep -c START "$T/log")" = "$n" ] && [ "$(grep -c "NOT merged" "$T/post.log")" = 1 ]'
g "$T/wt-bad" rm -q BAD; g "$T/wt-bad" commit -qm fix; S3=$(g "$T/wt-bad" rev-parse HEAD); mark bad "$S3"; rc=$(run run)
ok "5 new sha after red -> green, .failed removed" 'g "$O" merge-base --is-ancestor "$S3" master && [ ! -e "$S/queue/Project-X/bad.ready.failed" ]'
sed -i "s#^test = .*#test = \"test ! -e BAD\"#" "$O/release.toml"; rc=$(run approve X); g "$O" add -A; g "$O" diff --cached --quiet || g "$O" commit -qm toml

wt c1; S4=$(commit c1 a 1); wt c2; S5=$(commit c2 a 2)
: > "$T/post.log"; mark c1 "$S4"; rc=$(run run); M2=$(head_); mark c2 "$S5"; rc=$(run run)
ok "6 conflict -> master in place, letter with the reason" '[ "$(head_)" = "$M2" ] && grep -q "NOT merged (conflict)" "$T/post.log" && grep -q "conflict with master: ." "$T/post.log"'
rm -f "$S/queue/Project-X/"c2.ready*

mark gone "0000000000000000000000000000000000000001"; mark inj "--upload-pack=touch $T/pwn"; rc=$(run run)
ok "7 markers with a missing or malformed sha -> red, nothing executed" '[ -e "$S/queue/Project-X/gone.ready.failed" ] && [ -e "$S/queue/Project-X/inj.ready.failed" ] && [ ! -e "$T/pwn" ]'
rm -f "$S/queue/Project-X/"*

# 8 the toml was edited after the approval
wt d2; S6=$(commit d2 c c); M3=$(head_); cp "$O/release.toml" "$T/toml.bak"; sed -i "s#^test = .*#test = \"touch $T/pwn2\"#" "$O/release.toml"; mark d2 "$S6"; rc=$(run run)
ok "8 a substituted command is not executed" '[ ! -e "$T/pwn2" ] && [ "$(head_)" = "$M3" ] && grep -q "\"unapproved\"" "$S/Project-X.json"'

# 9 master moved during the gate -> not lost: next pass is green on the new master
cat > "$T/mover.sh" <<E
until [ -e "$T/moved" ]; do sleep 0.1; done
/usr/bin/git -c safe.directory='*' -C "$O" commit -q --allow-empty -m moved-during-gate
E
sed -i "s#^test = .*#test = \"touch $T/moved; sleep 2\"#" "$O/release.toml"; rc=$(run approve X); rm -f "$T/moved"; bash "$T/mover.sh" & mv_pid=$!
rc=$(run run); wait $mv_pid
ok "9 master moved during the gate -> retry, marker stays" 'grep -q "\"retry\"" "$S/Project-X.json" && [ -e "$S/queue/Project-X/d2.ready" ] && ! g "$O" merge-base --is-ancestor "$S6" master'
sed -i "s#^test = .*#test = \"true\"#" "$O/release.toml"; rc=$(run approve X); rc=$(run run)
ok "9b next pass -> green, both commits in master" 'g "$O" merge-base --is-ancestor "$S6" master && g "$O" log --format=%s | grep -q moved-during-gate'

# 10 an uncommitted change blocks the ff -> red with the reason, the human's work is intact
wt d3; S7=$(commit d3 e e); M4=$(head_); echo dirty > "$O/e"; : > "$T/post.log"; mark d3 "$S7"; rc=$(run run)
ok "10 uncommitted change blocks ff -> master in place, letter, file intact" '[ "$(head_)" = "$M4" ] && grep -q "NOT merged (ff)" "$T/post.log" && grep -q dirty "$O/e"'
rm -f "$O/e" "$S/queue/Project-X/"*

# 11 ready: dirty worktree refused; clean -> marker outside the tree; from master refused
cd "$T/wt-d3"; echo z > z
env_ python3 "$REL" ready X-Dev "something" > "$T/out" 2>&1; rc=$?; ok "11 ready with uncommitted files -> rc 6, no marker" '[ "$rc" = 6 ] && [ -z "$(ls "$S/queue/Project-X/" 2>/dev/null)" ]'
mkdir sub; cd sub; env_ python3 "$REL" ready X-Dev "something" > "$T/out" 2>&1; rc=$?; ok "11a dirt above the current folder is refused too" '[ "$rc" = 6 ]'; cd ..; rmdir sub
rm z; env_ python3 "$REL" ready X-Dev "something" > "$T/out" 2>&1; rc=$?; ok "11b ready clean -> marker with the sha" '[ "$rc" = 0 ] && grep -q "$S7" "$S/queue/Project-X/d3.ready"'
cd "$O"; env_ python3 "$REL" ready X-Dev "something" > "$T/out" 2>&1; rc=$?; ok "11c ready from master -> rc 6" '[ "$rc" = 6 ]'
rm -f "$S/queue/Project-X/"*; cd "$T"

# 12 a project without its own repo and a broken toml do not take down the rest; 13 no such user; 14 links
mkdir -p "$R/Project-Mono" "$R/Project-Z"; printf 'test = "true"\n' > "$R/Project-Mono/release.toml"; echo 'this = not toml =' > "$R/Project-Z/release.toml"; rc=$(run run)
ok "12 monorepo folder and broken toml -> reasons in the log" 'grep -q "Project-Mono.*no repo of its own" "$T/log" && grep -q "Project-Z/release.toml" "$T/log"'
rm -rf "$R/Project-Mono" "$R/Project-Z"
wt d4; S8=$(commit d4 f f); mark d4 "$S8"; (cd "$R" && env_ CCM_RELEASER_USER=no-such-user python3 "$REL" run) > "$T/out" 2>&1
ok "13 no such user -> nothing run, marker intact" 'grep -q "user no-such-user does not exist" "$T/log" && [ -e "$S/queue/Project-X/d4.ready" ] && ! g "$O" merge-base --is-ancestor "$S8" master'
printf 'links = ["../../etc", "node_modules"]\n' >> "$O/release.toml"; mkdir "$O/node_modules"; sed -i 's#^test = .*#test = "test -L node_modules \&\& test ! -e etc"#' "$O/release.toml"; rc=$(run approve X); rc=$(run run)
ok "14 links: own path as a symlink, one with .. skipped, green" 'g "$O" merge-base --is-ancestor "$S8" master && grep -q "links .* is outside the project" "$T/log"'
# 15 run_as in the toml does nothing: root cannot be chosen
printf 'run_as = "root"\n' >> "$O/release.toml"; sed -i "s#^test = .*#test = \"id -un > $T/who2\"#" "$O/release.toml"; rc=$(run approve X); wt d5; S9=$(commit d5 g g); mark d5 "$S9"; rc=$(run run)
ok "15 run_as = root is ignored, the gate runs as the separate user" '[ "$(cat "$T/who2")" = nobody ]'
# 16 a non-root user cannot approve (the code is copied into the sandbox: the unprivileged user may not read the checkout)
mkdir -p "$T/code/scripts" "$T/code/lib"; cp "$REL" "$T/code/scripts/releaser.py"; cp "$(dirname "$REL")/../lib/ccm_conf.py" "$T/code/lib/"; chmod -R a+rX "$T/code"
rc=$(cd "$T" && setpriv --reuid=65534 --regid=65534 --clear-groups env HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$R" CCM_RELEASER_STATE="$S" CCM_RELEASER_APPROVED="$T/approved.json" python3 "$T/code/scripts/releaser.py" approve X >/dev/null 2>&1; echo $?)
ok "16 approve as non-root -> rc 5" '[ "$rc" = 5 ]'
echo "releaser: $pass pass, $fail fail"; [ $fail = 0 ]
