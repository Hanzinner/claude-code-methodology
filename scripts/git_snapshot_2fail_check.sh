#!/usr/bin/env bash
# Not scheduled by install.sh and not in the supervisor template: the backup/snapshot scripts it reads are run by hand.
# If you schedule them, add an entry {"name": ..., "kind": "cmd", "cmd": "<install dir>/scripts/git_snapshot_2fail_check.sh"} to checks.json.
# git_snapshot_2fail_check.sh - the doc snapshot job (daily-git-snapshot.sh, log SNAP_LOG): the last two results in a row
# FAIL / skipped -> exit 1 (the supervisor turns it into a red check for the human: "two failures in a row must wake the
# owner, not lie in an inbox"). One failure alone is not enough.
# One run = one timestamp: a "skipped" WARN and a FAIL of the same run are ONE failure (a false "twice" once).
# Result lines: "<ISO time> commit OK ..." | "<ISO time> ... FAIL ..." | "<ISO time> ... skipped ..." (also "no changes"
# is NOT a result). Exit: 0 ok | 1 two bad | 3 no log / fewer than two results.
set -uo pipefail
L=${SNAP_LOG:-${L:-$HOME/.claude/logs/git-snapshot.log}}
[[ -f $L ]] || { echo "no $L"; exit 3; }
mapfile -t R < <(grep -E '^20[0-9-]+T[0-9:+]+ (commit OK|ERROR|FAIL|.*skipped)' "$L" | awk '{r[$1]=$0; if(!($1 in s)){o[++n]=$1; s[$1]=1}} END{for(i=n-1;i<=n;i++) if(i>0) print r[o[i]]}')
(( ${#R[@]} == 2 )) || { echo "fewer than two results in the log"; exit 3; }
bad=0; for r in "${R[@]}"; do [[ $r == *"commit OK"* ]] || ((bad++)); done
echo "last two: ${R[0]:0:60} | ${R[1]:0:60}"
(( bad < 2 )) || { echo "git snapshot failed TWICE in a row - the documents are not being saved to git"; exit 1; }
