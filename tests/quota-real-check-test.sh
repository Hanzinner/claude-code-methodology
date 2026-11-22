#!/usr/bin/env bash
# quota_real_check.sh in a sandbox: temp HOME, hand-made status files and transcripts. No network. C=<path> tests another copy.
set -u
HERE="$(dirname "$(readlink -f "$0")")"
C=${C:-$HERE/../scripts/quota_real_check.sh}
T=$(mktemp -d) || exit 2; trap 'rm -rf "$T"' EXIT
export HOME="$T/home" CCM_TEST=1; mkdir -p "$HOME/.claude/projects/p"
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
# 11. Windows (Git Bash): python3 is not in /usr/bin - it is our shim (<install>/lib/pyshim) or python.exe somewhere in
#     the caller's PATH. The script reset PATH to the standard folders and lost it ("broken JSON", rc 3, every run).
#     Imitated in a private mount namespace: each standard folder holding python3 is replaced by a view of itself
#     without python3; the working python3 is only in a separate folder of the caller's PATH.
if [[ -n ${MSYSTEM:-} ]] || ! unshare -rm true 2>/dev/null; then
    echo "SKIP: 11 needs Linux user namespaces (unshare -rm) to hide python3 in /usr/bin; on Windows the cases above already run with the shim"
else
    mkdir -p "$T/shim"; printf '#!/bin/sh\necho "api 2 30"\n' > "$T/shim/python3"; chmod +x "$T/shim/python3"
    cp "$C" "$T/qrc.sh"   # inside the namespace root has no rights over other users' folders: run a copy from $T
    cat > "$T/hide.sh" <<'HIDE'
T=$1
for d in /usr/local/sbin /usr/local/bin /usr/sbin /usr/bin /sbin /bin; do
    [ -L "$d" ] || [ ! -e "$d/python3" ] && continue      # /bin -> usr/bin on a merged /usr
    k="$T/ns${d//\//_}"; mkdir -p "$k/real" "$k/view"
    mount --bind "$d" "$k/real" || exit 9
    for f in "$k/real"/* "$k/real"/.[!.]*; do [ -e "$f" ] || [ -L "$f" ] || continue; n=${f##*/}; [ "$n" = python3 ] || ln -s "$f" "$k/view/$n"; done
    mount --bind "$k/view" "$d" || exit 9
done
command -v python3 >/dev/null && [ "$(command -v python3)" != "$T/shim/python3" ] && { echo "imitation failed: $(command -v python3)"; exit 9; }
exec bash "$T/qrc.sh"
HIDE
    status '{"source":"api","real_age_min":2,"pct":30}'
    out=$(F="$F" PATH="$T/shim:$PATH" unshare -rm bash "$T/hide.sh" "$T" 2>&1); rc=$?
    ok "11 python3 only in the caller's PATH (a shim), none in the standard folders -> still found, rc 0" '[ $rc = 0 ] && [[ $out == *"source api"* ]]'
fi
echo "quota-real-check: $pass pass, $fail fail"; [ $fail = 0 ]
