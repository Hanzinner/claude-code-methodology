#!/usr/bin/env bash
# git-guard (PATH wrapper) in a sandbox: shared repo, worktrees, nested repos, a project repo, a project under the release queue.
# GW=<path> tests another copy. Sandbox repos belong to the current user; the real workspace is never touched.
set -u
HERE=$(dirname "$(readlink -f "$0")")
GW=${GW:-$HERE/../bin/git-guard}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent GIT_CONFIG_GLOBAL=/dev/null; mkdir -p "$HOME"
RG=$(command -v git)
M="$T/main"; W="$T/wt"; O="$T/other"
rg_() { "$RG" -c user.email=t@t -c user.name=t "$@"; }
for d in "$M" "$O"; do mkdir -p "$d" && (cd "$d" && rg_ init -q -b master && echo a > a && rg_ add a && rg_ commit -qm i); done
rg_ -C "$M" worktree add -q "$W/x" -b x >/dev/null 2>&1
export CCM_WORKSPACE="$M" CCM_WORKTREES_DIR="$W" CCM_REAL_GIT="$RG" CCM_GIT_GUARD_BLOCK_REMOTE=1
g() { local dir=$1; shift; (cd "$dir" && "$GW" -c user.email=t@t -c user.name=t "$@") >/dev/null 2>&1; echo $?; }
pass=0; fail=0
ok() { if [ "$2" = "$3" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1 (expected $3, got $2)"; fi; }

ok "1 remote add in the shared repo -> 88"            "$(g "$M" remote add origin https://example.com/r.git)" 88
ok "2 remote set-url -> 88"                           "$(g "$M" remote set-url origin https://example.com/r.git)" 88
ok "3 remote -v (read) -> 0"                          "$(g "$M" remote -v)" 0
ok "4 config remote.x.url ... -> 88"                  "$(g "$M" config remote.origin.url https://example.com/r.git)" 88
ok "5 config --get remote.x.url (read) -> not 88"     "$([ "$(g "$M" config --get remote.origin.url)" = 88 ] && echo 88 || echo ok)" ok
ok "6 config url.*.insteadOf -> 88"                   "$(g "$M" config url.https://x/.insteadOf gh:)" 88
ok "7 push (any) -> 88"                               "$(g "$M" push /tmp/nowhere HEAD)" 88
ok "8 remote add in a worktree (shared .git) -> 88"   "$(g "$W/x" remote add origin https://example.com/r.git)" 88
ok "9 remote add in a repo outside the workspace -> 0" "$(g "$O" remote add origin https://example.com/r.git)" 0
N="$M/nested"; mkdir -p "$N" && (cd "$N" && rg_ init -q && echo n > n && rg_ add n && rg_ commit -qm n)
ok "9b nested self-standing repo (like a notes vault): remote add -> 0" "$(g "$N" remote add origin https://example.com/n.git)" 0
ok "9c nested repo: push is not blocked by the wrapper (not 88)" "$([ "$(g "$N" push /tmp/nowhere-$$ HEAD)" = 88 ] && echo 88 || echo ok)" ok
ok "9d nested repo: reset --hard is not blocked (not 88)" "$([ "$(g "$N" reset --hard)" = 88 ] && echo 88 || echo ok)" ok
ok "10 status in the shared repo -> 0"                "$(g "$M" status --short)" 0
ok "11 reset --hard in the shared repo -> 88"         "$(g "$M" reset --hard)" 88
ok "12 no remote left in the shared repo after the attempts" "$(rg_ -C "$M" remote | wc -l)" 0
# remote blocking is OFF unless the key is set
ok "12b CCM_GIT_GUARD_BLOCK_REMOTE=0 -> remote add allowed in the shared repo" "$(CCM_GIT_GUARD_BLOCK_REMOTE=0 g "$M" remote add okremote https://example.com/z.git)" 0
rg_ -C "$M" remote remove okremote
# ── repair of a broken branch: update-ref is allowed ONLY when the branch points at an unreadable object
hz() { rg_ -C "$M" "$@" 2>/dev/null; }
(cd "$M" && echo two > two && rg_ add two && rg_ commit -qm two) >/dev/null 2>&1
BR=$(hz symbolic-ref HEAD); GOOD=$(hz rev-parse HEAD~1); TIP=$(hz rev-parse HEAD)
ok "13 healthy branch: update-ref <branch> <commit> -> 88" "$(g "$M" update-ref "$BR" "$GOOD")" 88
ok "13b ...and the branch did not move"               "$(hz rev-parse HEAD)" "$TIP"
OBJ="$M/.git/objects/${TIP:0:2}/${TIP:2}"; chmod u+w "$OBJ"; : > "$OBJ"       # as after a cut-off write: the commit object is empty
ok "14 branch on an empty object: update-ref -d -> 88 (deleting is not repair)" "$(g "$M" update-ref -d "$BR")" 88
ok "14b ...to a non-existent commit -> 88"            "$(g "$M" update-ref "$BR" 1111111111111111111111111111111111111111)" 88
ok "14c ...refs/tags/* is not repaired -> 88"         "$(g "$M" update-ref refs/tags/v1 "$GOOD")" 88
ok "15 branch on an empty object: update-ref <branch> <intact commit> -> 0" "$(g "$M" update-ref "$BR" "$GOOD")" 0
ok "15b the branch is on an intact commit, git is alive" "$(hz rev-parse HEAD)" "$GOOD"
ok "15c after the repair the same call is blocked again -> 88" "$(g "$M" update-ref "$BR" "$GOOD")" 88
# 16 a project's own repo: destructive verbs as in the shared repo; remote/push are free
P="$M/Project-Pil"; mkdir -p "$P" && (cd "$P" && rg_ init -q -b master && echo a > f && rg_ add -A && rg_ commit -qm i)
echo b > "$P/f"
ok "16 project repo: reset --hard -> 88"              "$(g "$P" reset --hard)" 88
ok "16b ...the file is intact"                        "$(cat "$P/f")" b
ok "16c filter-repo -> 88"                            "$(g "$P" filter-repo --force)" 88
ok "16d remote add is not blocked -> 0"               "$(g "$P" remote add origin https://example.com/r.git)" 0
ok "16e push is not blocked (not 88)"                 "$([ "$(g "$P" push /tmp/nowhere-$$ HEAD)" = 88 ] && echo 88 || echo ok)" ok
D="$M/Project-Pil/deep"; mkdir -p "$D" && (cd "$D" && rg_ init -q)
ok "16h a deeper nested repo (Project-X/y/.git) is not a project repo: reset not blocked" "$([ "$(g "$D" reset --hard)" = 88 ] && echo 88 || echo ok)" ok
# 17 a project under the release queue: master is moved only by the queue; branches and reads are free; without a state file as before
RS="$T/rstate"; mkdir -p "$RS"; export CCM_RELEASER_STATE="$RS"
R="$M/Project-Rel"; mkdir -p "$R" && (cd "$R" && rg_ init -q -b master && echo a > f && rg_ add -A && rg_ commit -qm i && echo b > f && rg_ commit -qam two && rg_ branch side)
RW="$W/rel"; rg_ -C "$R" worktree add -q "$RW" side >/dev/null 2>&1
touch "$RS/Project-Rel.json"; TIPR=$(rg_ -C "$R" rev-parse master)
echo c > "$R/g"; ok "17 commit onto master of a project under the releaser -> 88" "$(g "$R" add g)$(g "$R" commit -qm g)" 088
ok "17b merge into master -> 88"                      "$(g "$R" merge side)" 88
ok "17c reset HEAD~1 (no flag) -> 88"                 "$(g "$R" reset HEAD~1)" 88
ok "17d reset -- g (unstage) -> 0"                    "$(g "$R" reset -q -- g)" 0
ok "17e status/log -> 0"                              "$(g "$R" status --short)$(g "$R" log --oneline -1)" 00
ok "17f from an agent worktree: push . HEAD:master -> 88" "$(g "$RW" push . HEAD:master)" 88
ok "17g from the worktree: update-ref refs/heads/master -> 88" "$(g "$RW" update-ref refs/heads/master HEAD)" 88
ok "17h from the worktree: branch -f master -> 88"    "$(g "$RW" branch -f master HEAD)" 88
echo d > "$RW/h"; ok "17i commit on its own branch in the worktree -> 0" "$(g "$RW" add h)$(g "$RW" commit -qm h)" 00
ok "17j master did not move"                          "$(rg_ -C "$R" rev-parse master)" "$TIPR"
rm "$RS/Project-Rel.json"; ok "17k without a releaser state file - commit onto master as before -> 0" "$(g "$R" add g)$(g "$R" commit -qm g2)" 00
# 18 the real git is found by skipping the wrapper itself (a symlink named git in an earlier PATH dir)
mkdir -p "$T/bin"; ln -s "$(readlink -f "$GW")" "$T/bin/git"; unset CCM_REAL_GIT
out=$(cd "$O" && PATH="$T/bin:$PATH" git --version 2>&1); ok "18 symlink named git: finds the real git, no recursion" "$([[ "$out" == "git version"* ]] && echo ok)" ok
out=$(cd "$M" && PATH="$T/bin:$PATH" git reset --hard 2>&1; echo "rc=$?"); ok "18b through the symlink: still blocks" "$([[ "$out" == *"BLOCKED"*"rc=88" ]] && echo ok)" ok
echo "git-guard: $pass pass, $fail fail"; [ $fail = 0 ]
