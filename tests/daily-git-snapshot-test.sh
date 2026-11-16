#!/usr/bin/env bash
# daily-git-snapshot.sh: a change -> "commit OK"; nothing changed -> "no changes", rc 0; a commit refused (a pre-commit
# hook) -> a FAIL line and rc 1 — and git_snapshot_2fail_check.sh turns two such in a row red. DS=<path> tests another copy.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
DS=${DS:-$HERE/../scripts/daily-git-snapshot.sh}
CK=$HERE/../scripts/git_snapshot_2fail_check.sh
T=$(mktemp -d) && [[ -d "$T" && "$T" != / ]] || { echo "no temp dir (mktemp missing?) - refusing to run: every path below would land in /" >&2; exit 2; }
trap 'rm -rf "$T"' EXIT
export HOME=$T GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t LOG=$T/snap.log
git init -q "$T/r" && echo a > "$T/r/a" && git -C "$T/r" add a && git -C "$T/r" commit -qm init
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1 :: ${3:-}"; fi; }

echo b >> "$T/r/a"; bash "$DS" "$T/r"; rc=$?
ok "1 a change -> commit OK, rc 0" '[[ $rc == 0 ]] && tail -1 "$LOG" | grep -q "commit OK (1 files)"' "rc=$rc $(tail -2 "$LOG")"
bash "$DS" "$T/r"; rc=$?
ok "2 nothing changed -> 'no changes', rc 0" '[[ $rc == 0 ]] && tail -1 "$LOG" | grep -q "no changes"' "rc=$rc"
printf '#!/bin/sh\necho "hook says no" >&2\nexit 1\n' > "$T/r/.git/hooks/pre-commit"; chmod +x "$T/r/.git/hooks/pre-commit"
echo c >> "$T/r/a"; bash "$DS" "$T/r"; rc=$?
ok "3 a refused commit -> FAIL line, rc 1 (not a silent exit)" '[[ $rc == 1 ]] && tail -1 "$LOG" | grep -q "FAIL: git commit"' "rc=$rc $(tail -3 "$LOG")"
sleep 1; bash "$DS" "$T/r"
SNAP_LOG=$LOG bash "$CK" >/dev/null; rc=$?
ok "4 two refused commits in a row -> the supervisor check is red (rc 1)" '[[ $rc == 1 ]]' "rc=$rc"
bash "$DS" "$T/nope" 2>/dev/null; rc=$?
ok "5 not a repo -> rc 1 and an ERROR line" '[[ $rc != 0 ]] && tail -1 "$LOG" | grep -q "ERROR\|FAIL"' "rc=$rc $(tail -1 "$LOG")"
echo "daily-git-snapshot: $pass pass, $fail fail"; (( fail == 0 ))
