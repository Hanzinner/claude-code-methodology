#!/usr/bin/env bash
# The matrix of EFFECTS for git-guard: we check the state AFTER the command, not the exit code (an exit code lied: some commands
# failed for other reasons and looked "blocked"). GW=<path> tests another copy. The sandbox belongs to the current user.
set -u
HERE=$(dirname "$(readlink -f "$0")")
GW=${GW:-$HERE/../bin/git-guard}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent GIT_CONFIG_GLOBAL=/dev/null; mkdir -p "$HOME"
RG=$(command -v git)
M="$T/main"; W="$T/wt"
export CCM_WORKSPACE="$M" CCM_WORKTREES_DIR="$W" CCM_REAL_GIT="$RG"
H() { bash -c "$1"; }
fresh() {   # a clean shared repo: master + branches b1..b6 (all merged) + a tag + a stash + an uncommitted change in a.txt
    rm -rf "$M" "$W"
    H "mkdir -p '$M' && cd '$M' && '$RG' init -q -b master && '$RG' config user.email t@t && '$RG' config user.name t \
       && echo base > a.txt && '$RG' add a.txt && '$RG' commit -qm base \
       && for b in b1 b2 b3 b4 b5 b6; do '$RG' branch \$b; done && '$RG' tag rel-1 \
       && echo stashed >> a.txt && '$RG' stash -q && echo 'SOMEBODY ELSES UNCOMMITTED WORK' >> a.txt && echo junk > untracked.txt"
}
run() { H "cd '$M' && '$GW' $1" >/dev/null 2>&1; }
branch_exists() { H "cd '$M' && '$RG' rev-parse -q --verify refs/heads/$1" >/dev/null 2>&1; }
work_intact() { grep -q 'SOMEBODY ELSES UNCOMMITTED WORK' "$M/a.txt"; }
pass=0; fail=0
must() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

# ── must be BLOCKED: we check that the EFFECT is absent
fresh; run "branch -D b1";               must "branch -D -> the branch lives"                'branch_exists b1'
fresh; run "branch --delete --force b2"; must "branch --delete --force -> the branch lives"  'branch_exists b2'
fresh; run "branch -d -f b3";            must "branch -d -f -> the branch lives"             'branch_exists b3'
fresh; run "branch -df b4";              must "branch -df (glued) -> the branch lives"       'branch_exists b4'
fresh; run "branch -M b5 b6";            must "branch -M (overwrite) -> b5 and b6 live"      'branch_exists b5 && branch_exists b6'
fresh; run "checkout -f";                must "checkout -f -> uncommitted work intact"       'work_intact'
fresh; run "checkout -- a.txt";          must "checkout -- file -> uncommitted work intact"  'work_intact'
fresh; run "restore a.txt";              must "restore (worktree by default) -> intact"      'work_intact'
fresh; run "restore --worktree --source=HEAD .";  must "restore --worktree --source -> intact" 'work_intact'
fresh; run "switch --discard-changes master";     must "switch --discard-changes -> intact"  'work_intact'
fresh; run "reset --hard";               must "reset --hard -> intact"                       'work_intact'
fresh; run "clean -fd";                  must "clean -fd -> the untracked file lives"        '[ -f "$M/untracked.txt" ]'
fresh; run "stash clear";                must "stash clear -> the stash lives"               '[ "$(H "cd '"'$M'"' && '"$RG"' stash list" | wc -l)" = 1 ]'
fresh; run "stash drop";                 must "stash drop -> the stash lives"                '[ "$(H "cd '"'$M'"' && '"$RG"' stash list" | wc -l)" = 1 ]'
fresh; run "tag -d rel-1";               must "tag -d -> the tag lives"                      'H "cd '"'$M'"' && '"$RG"' rev-parse -q --verify refs/tags/rel-1" >/dev/null'
fresh; run "update-ref -d refs/heads/b1";must "update-ref -d -> the branch lives"            'branch_exists b1'
fresh; n0=$(H "cd '$M' && '$RG' reflog | wc -l"); run "reflog expire --expire-unreachable=now --all"
       must "reflog expire -> the reflog is whole"  '[ "$(H "cd '"'$M'"' && '"$RG"' reflog | wc -l")" = "$n0" ]'
fresh; run "filter-branch -f --msg-filter cat master"
       must "filter-branch -> history is the same"  '[ -z "$(H "cd '"'$M'"' && '"$RG"' for-each-ref refs/original")" ]'

# ── must PASS (over-blocking = a stopped pipeline, which costs more than a hole)
fresh; run "branch -d b1";               must "branch -d of a merged branch (safe) -> deleted" '! branch_exists b1'
fresh; run "restore --staged a.txt";     must "restore --staged (index only) -> passed, work intact" 'work_intact'
fresh; run "tag rel-2";                  must "tag creation -> it exists"                    'H "cd '"'$M'"' && '"$RG"' rev-parse -q --verify refs/tags/rel-2" >/dev/null'
fresh; run "stash list";                 must "stash list -> rc 0"                           'true'
fresh; H "cd '$M' && '$GW' worktree add -q '$W/x' b1" >/dev/null 2>&1
       must "worktree add -> created"      '[ -d "$W/x" ]'
       H "cd '$W/x' && '$GW' reset -q --hard" >/dev/null 2>&1; must "reset --hard in a worktree (a runner) -> not blocked" '[ $? = 0 ]'
       H "cd '$W/x' && echo w >> a.txt && '$GW' checkout -q -f" >/dev/null 2>&1; must "checkout -f in a worktree -> passed (file reverted)" '! grep -q "^w$" "$W/x/a.txt"'
fresh; H "cd '$M' && echo x > b.txt && '$GW' add b.txt && '$GW' commit -qm x" >/dev/null 2>&1
       must "a plain commit in the shared repo -> it exists"  'H "cd '"'$M'"' && '"$RG"' log --oneline" | grep -q " x$"'
echo "git-guard-effects: $pass pass, $fail fail"; [ $fail = 0 ]
