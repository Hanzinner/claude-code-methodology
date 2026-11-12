#!/usr/bin/env bash
# wt_deliver.sh <agent> - deliver an agent's work from its worktree into master. The agent calls it itself when its changes are
# ready: the same thing agents used to do by hand, but with a refusal at every step where master could get something
# unchecked or somebody else's. Model: a fast-forward-only release runner.
#
# Steps: dirty worktree -> refuse · merge master into the worktree (conflict -> refuse) · the project's test in the worktree
#   (red -> refuse) · every file the branch changed against master must belong to the agent per <project>/OWNERS
#   (someone else's / nobody's -> refuse) · `git merge --ff-only` of the branch in the main tree (master moved -> merge
#   master again, up to 3 tries) · the project's build in the main tree · a line in the log + a letter to the agent.
#   In every refusal master does not move.
#
# Settings - <project>/deliver.conf (KEY=value lines, the file is PARSED, never executed):
#   AGENTS=Dev-A Dev-B ...   who delivers through this project
#   DIR=Project-X            project folder from the repo root (TEST and BUILD run there)
#   TEST=npm test            test command (in the agent's worktree); empty = no test
#   BUILD=npm run build      build command (in the main tree after the ff); empty = no build
#   OWNERS=Project-X/OWNERS  owners file: "<pattern from the repo root> <agent|*>", the LAST match wins; ** = any depth
# exit: 0 delivered · 2 usage/settings · 3 worktree dirty · 4 conflict · 5 test red · 6 someone else's/nobody's file
#       · 7 ff failed in 3 tries · 8 the build in the main tree failed (master has ALREADY moved - the letter is loud) · 9 busy
# Paths: workspace = CCM_WORKSPACE; worktrees = CCM_WORKTREES_DIR (default <workspace>-wt, one folder per agent name);
# letters through CCM_INBOX_POST (default: inbox_post.sh next to this script); log CCM_WT_DELIVER_LOG
# (default ~/.claude/wt-deliver.log). Test: tests/wt-deliver-test.sh
set -uo pipefail
HERE=$(dirname "$(readlink -f "$0")")
eval "$(python3 "$HERE/../lib/ccm_conf.py" --shell)"
REPO=$CCM_WORKSPACE
WTROOT=${CCM_WORKTREES_DIR:-$(python3 "$HERE/../lib/ccm_conf.py" CCM_WORKTREES_DIR)}; WTROOT=${WTROOT:-$CCM_WORKSPACE-wt}
LOG=${CCM_WT_DELIVER_LOG:-$HOME/.claude/wt-deliver.log}
POST=${CCM_INBOX_POST:-$HERE/inbox_post.sh}
agent=${1:-}
[[ -n "$agent" && "$agent" != -* ]] || { echo "wt_deliver.sh <agent> - see the header"; exit 2; }
WT="$WTROOT/$agent"
u8cut() { head -c "$1" | iconv -f utf-8 -t utf-8 -c 2>/dev/null || true; }   # cut -c cuts by bytes -> a broken character in the letter
say() { echo "$*"; mkdir -p "$(dirname "$LOG")" 2>/dev/null; echo "$(date -Iseconds) $agent: $*" >> "$LOG" 2>/dev/null || true; }
letter() { "$POST" "$agent" "- [ ] [$(date '+%F %H:%M')] wt_deliver · $1" >/dev/null 2>&1 || true; }
refuse() { local rc=$1; shift; say "REFUSED: $*"; letter "delivery NOT accepted, master did not move: $*"; exit "$rc"; }

# ── the agent's project: the <Project>/deliver.conf that lists it in AGENTS
conf=""
for c in "$REPO"/${CCM_PROJECTS_GLOB:-Project-*}/deliver.conf; do
    [[ -f "$c" ]] || continue
    if grep -qE "^AGENTS=(.* )?$agent( |$)" "$c"; then conf=$c; break; fi
done
[[ -n "$conf" ]] || { echo "$agent is not listed in any project's deliver.conf (AGENTS=...)"; exit 2; }
cfg() { sed -n "s/^$1=//p" "$conf" | tail -1; }
DIR=$(cfg DIR); TEST=$(cfg TEST); BUILD=$(cfg BUILD); OWNERS=$(cfg OWNERS)
[[ -n "$DIR" && -n "$OWNERS" && -f "$REPO/$OWNERS" ]] || { echo "$conf lacks DIR/OWNERS or the file $OWNERS does not exist"; exit 2; }
OWNERS_FILE="$REPO/$OWNERS"; PROJ=$(basename "$DIR"); FPRE=""
# A project with a repo of its own: the storage is its own, the OWNERS patterns stay "from the workspace root"
if [[ -e "$REPO/$DIR/.git" ]]; then FPRE="$DIR/"; REPO="$REPO/$DIR"; DIR=.; fi
[[ -d "$WT/.git" || -f "$WT/.git" ]] || { echo "no worktree $WT (git worktree)"; exit 2; }
branch=$(git -C "$WT" rev-parse --abbrev-ref HEAD)
[[ "$branch" != HEAD && "$branch" != master ]] || { echo "$WT is not on the agent's branch ($branch)"; exit 2; }

# ── one delivery per project at a time. Redirect in braces: a bare `exec 8>... 2>/dev/null` silenced the whole script's stderr
{ exec 8>"/var/lock/wt_deliver-$PROJ.lock"; } 2>/dev/null || exec 8>"${TMPDIR:-/tmp}/wt_deliver-$PROJ.lock"
flock -w 120 8 || { echo "another delivery of $DIR has been running for over 2 min - try later"; exit 9; }

# the main tree must stand on master - otherwise the ff would move somebody else's branch and we would say "delivered to master"
head=$(git -C "$REPO" symbolic-ref --short HEAD 2>/dev/null) || head="?"
[[ "$head" == master ]] || { echo "the main tree $REPO is not on master ($head) - not delivering"; exit 2; }

# dirty worktree: uncommitted AND not added to git (the test would see a file master will not have); ignored files do not count
dirty=$(git -c core.quotepath=off -C "$WT" status --porcelain) || refuse 3 "git status in $WT failed - is the worktree broken?"
[[ -z "$dirty" ]] || refuse 3 "worktree $WT is dirty (uncommitted/not added: $(echo "$dirty" | head -5 | cut -c4- | tr '\n' ' ')) - commit yours, remove the rest or put it in .gitignore"

run_in() {   # run_in <dir> <command> -> rc; output in $out_file
    ( cd "$1" && bash -c "$2" ) > "$out_file" 2>&1
}
out_file=$(mktemp); trap 'rm -f "$out_file"' EXIT

owners_bad() {   # owners_bad <sha> -> stdout: someone else's/nobody's files; rc != 0 - OWNERS could not be parsed
    # --no-renames: renaming someone else's file into your folder would otherwise show only the NEW name; -z: non-ASCII names without quotes
    git -C "$WT" diff --no-renames --name-only -z "master...$1" | python3 -c '
import re, sys
agent, owners, fpre = sys.argv[1], sys.argv[2], sys.argv[3]
rules = []
for n, ln in enumerate(open(owners, encoding="utf-8"), 1):
    ln = ln.split("#", 1)[0].strip()
    if not ln: continue
    parts = ln.rsplit(None, 1)
    if len(parts) != 2:
        sys.exit(f"OWNERS line {n}: \"{ln}\" - expected \"<pattern> <agent>\"")
    pat, who = parts
    # **/ -> zero or more folders; ** -> anything; * and ? - within one folder
    rx = "^" + "".join("(?:.*/)?" if t == "**/" else ".*" if t == "**" else "[^/]*" if t == "*" else "[^/]" if t == "?" else re.escape(t)
                       for t in re.split(r"(\*\*/|\*\*|\*|\?)", pat.rstrip("/")) if t) + "(?:/.*)?$"
    rules.append((re.compile(rx), who))
for f in sys.stdin.buffer.read().decode("utf-8", "surrogateescape").split("\0"):
    if not f: continue
    who = None
    for rx, w in rules:
        if rx.match(fpre + f): who = w
    if who is None: print(f"{f} (nobody)")
    elif who not in ("*", agent): print(f"{f} ({who})")
' "$agent" "$OWNERS_FILE" "$FPRE"
}

sync_and_check() {   # merge master into the worktree -> test (the first time, or when master brought something into DIR) -> owners; sets $sha
    local before; before=$(git -C "$WT" rev-parse HEAD)
    if ! git -C "$WT" merge --no-edit -q master > "$out_file" 2>&1; then
        local cf; cf=$(git -c core.quotepath=off -C "$WT" diff --name-only --diff-filter=U | head -5 | tr '\n' ' ')
        git -C "$WT" merge --abort >/dev/null 2>&1 || true
        refuse 4 "merging master into $branch failed: ${cf:+conflict in $cf}${cf:-$(tail -2 "$out_file" | tr '\n' ' ')}. Resolve it in your worktree: git merge master"
    fi
    # we deliver exactly THIS commit: whatever is committed into the worktree during the test does not travel to master unchecked
    sha=$(git -C "$WT" rev-parse HEAD)
    local need=0
    [[ "${1:-}" == first ]] && need=1
    git -C "$WT" diff --quiet "$before" "$sha" -- "$DIR" 2>/dev/null || need=1   # master brought something into the project -> test again
    if [[ -n "$TEST" && "$need" == 1 ]] && ! run_in "$WT/$DIR" "$TEST"; then
        refuse 5 "test \"$TEST\" is red in the worktree: $(tail -5 "$out_file" | tr '\n' ' ' | u8cut 400)"
    fi
    [[ "$(git -C "$WT" rev-parse HEAD)" == "$sha" ]] || refuse 3 "something was committed into the worktree DURING the delivery - deliver again when you are done"
    local bad
    bad=$(owners_bad "$sha" 2>"$out_file") || refuse 6 "the owners check did not run (not delivering blind): $(tail -2 "$out_file" | tr '\n' ' ' | u8cut 300)"
    [[ -z "$bad" ]] || refuse 6 "branch $branch changes files that are not yours: $(echo "$bad" | head -8 | tr '\n' ';' ) - the owner delivers them (send a letter) or the lead changes ownership in $OWNERS"
}

sync_and_check first
n=$(git -C "$WT" rev-list --count "master..$sha")
[[ "$n" -gt 0 ]] || { say "nothing to deliver: $branch is not ahead of master"; exit 0; }

ok=0
for try in 1 2 3; do
    if git -C "$REPO" merge --ff-only -q "$sha" > "$out_file" 2>&1; then ok=1; break; fi
    # master moved (a snapshot, another delivery) or local changes in the main tree are in the way
    if git -C "$REPO" merge-base --is-ancestor master "$sha"; then
        clash=$(grep -A5 "overwritten" "$out_file" | grep -E '^\s' | head -5 | tr -s ' \n' ' ')
        [[ -z "$clash" ]] || refuse 7 "the main tree has uncommitted changes to the same files (${clash}) - ff is impossible; let the snapshot commit them, then retry"
    fi
    sleep 2; sync_and_check
done
[[ "$ok" == 1 ]] || refuse 7 "ff-only into master failed in 3 tries: $(tail -2 "$out_file" | tr '\n' ' ')"
sha=$(git -C "$REPO" rev-parse --short "$sha")

if [[ -n "$BUILD" ]] && ! run_in "$REPO/$DIR" "$BUILD"; then
    say "BUILD FAILED: master is ALREADY at $sha, but the build \"$BUILD\" in the main tree failed: $(tail -3 "$out_file" | tr '\n' ' ' | u8cut 300)"
    letter "master is ALREADY at $sha ($n commits from $branch), but the build \"$BUILD\" in the main tree failed - fix it and deliver again: $(tail -3 "$out_file" | tr '\n' ' ' | u8cut 300)"
    exit 8
fi
say "delivered: $branch -> master $sha ($n commits)${TEST:+, test green}${BUILD:+, build ok}"
letter "delivered: $branch -> master $sha ($n commits)${TEST:+, test \"$TEST\" green}${BUILD:+, \"$BUILD\" in the main tree ok}"
exit 0
