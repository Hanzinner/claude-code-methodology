#!/usr/bin/env bash
# quota_real_check.sh in a sandbox: temp HOME, hand-made status files and transcripts. No network. C=<path> tests another copy.
set -u
HERE="$(dirname "$(readlink -f "$0")")"
C=${C:-$HERE/../scripts/quota_real_check.sh}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" HANZ_TEST=1; mkdir -p "$HOME/.claude/projects/p"
F="$T/status.json"; pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1 (rc=$rc out=$out)"; fi; }
chk() { out=$(F="$F" QUOTA_PROJECTS="$HOME/.claude/projects" "$@" bash "$C" 2>&1); rc=$?; }
status() { printf '%s' "$1" > "$F"; }
touch_old() { touch -d "$1 minutes ago" "$2"; }

rm -f "$F"; chk env; ok "1 no file -> rc 3" '[ $rc = 3 ]'
status 'not json'; chk env; ok "2 broken JSON -> rc 3" '[ $rc = 3 ]'
status '{"source":"api","real_age_min":2,"pct":30}'; chk env; ok "3 fresh file, real number -> rc 0" '[ $rc = 0 ]'
touch_old 20 "$F"; chk env; ok "4 file older than 10 min -> rc 1 (cron stopped)" '[ $rc = 1 ] && [[ $out == *cron* ]]'
status '{"source":"api","real_age_min":90,"pct":30}'; chk env; ok "5 real reading older than 60 min -> rc 1" '[ $rc = 1 ]'
chk env MAX_REAL_MIN=120; ok "5b ...but fine with MAX_REAL_MIN=120" '[ $rc = 0 ]'
status '{"source":"estimate","pct":70,"real_error":"HTTP 500"}'; chk env; ok "6 estimate (not real), other error -> rc 1" '[ $rc = 1 ] && [[ $out == *"NOT real"* ]]'
# the 13.11 fix: expired token while nobody works -> quiet; while agents work -> red
status '{"source":"estimate","pct":0,"real_error":"token expired - waiting for the CLI to renew it"}'
touch_old 60 "$HOME/.claude/projects/p/x.jsonl" 2>/dev/null || { echo > "$HOME/.claude/projects/p/x.jsonl"; touch_old 60 "$HOME/.claude/projects/p/x.jsonl"; }
chk env; ok "7 expired + no transcript changed for 15 min -> quiet (rc 0)" '[ $rc = 0 ] && [[ $out == *"nobody was working"* ]]'
echo '{}' > "$HOME/.claude/projects/p/y.jsonl"
chk env; ok "8 expired + a transcript changed just now -> rc 1 (CLI is not renewing)" '[ $rc = 1 ]'
rm "$HOME/.claude/projects/p/y.jsonl"; status '{"source":"estimate","pct":0,"real_error":"HTTP 401"}'
chk env; ok "10 NOT-expired error + nobody working -> still rc 1 (quiet only for expiry)" '[ $rc = 1 ]'
echo "quota-real-check: $pass pass, $fail fail"; [ $fail = 0 ]
