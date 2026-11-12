#!/usr/bin/env bash
# claim.sh: acquire / taken / same-owner re-acquire / expiry takeover / check / release / bad input.
# Runs the repo copy; CLAIM=<path> tests another one. Sandbox: temp HOME and CCM_CLAIMS_DIR, no config file.
set -u
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
C="${CLAIM:-$HERE/../scripts/claim.sh}"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_CLAIMS_DIR="$T/claims"; mkdir -p "$HOME"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

out=$("$C" acquire build --ttl 5 --owner alice 2>&1); rc=$?
ok "acquire a free key -> rc 0, OK" '[ $rc = 0 ] && [[ "$out" == OK:* ]]'
out=$("$C" acquire build --owner bob 2>&1); rc=$?
ok "another owner while held -> rc 1, TAKEN, names alice" '[ $rc = 1 ] && [[ "$out" == *TAKEN* && "$out" == *alice* ]]'
out=$("$C" acquire build --owner alice 2>&1); rc=$?
ok "the same owner again -> rc 0 (renews)" '[ $rc = 0 ]'
out=$("$C" check build 2>&1); rc=$?
ok "check while held -> rc 1, TAKEN" '[ $rc = 1 ] && [[ "$out" == TAKEN* ]]'
"$C" release build --owner bob >/dev/null
ok "releasing another owner's claim is logged" 'grep -q "SOMEONE ELSE" "$HOME/.claude/claims.log"'
out=$("$C" check build 2>&1); rc=$?
ok "after release -> check FREE, rc 0" '[ $rc = 0 ] && [[ "$out" == FREE* ]]'

# expiry: write an already expired claim file, the next acquire takes it over (and logs it)
printf 'owner=ghost\nexpiry=%s\nttl_min=1\n' "$(( $(date +%s) - 600 ))" > "$CCM_CLAIMS_DIR/old.claim"
out=$("$C" acquire old --owner carol 2>&1); rc=$?
ok "an expired claim is free: takeover rc 0" '[ $rc = 0 ] && grep -q "TAKEOVER" "$HOME/.claude/claims.log" && grep -q "owner=carol" "$CCM_CLAIMS_DIR/old.claim"'
printf 'owner=ghost\nexpiry=%s\n' "$(( $(date +%s) - 600 ))" > "$CCM_CLAIMS_DIR/old2.claim"
out=$("$C" check old2 2>&1); rc=$?
ok "check on an expired claim -> FREE and the file is removed" '[ $rc = 0 ] && [[ "$out" == FREE* ]] && [ ! -f "$CCM_CLAIMS_DIR/old2.claim" ]'
printf 'garbage\n' > "$CCM_CLAIMS_DIR/bad.claim"
out=$("$C" acquire bad --owner dave 2>&1); rc=$?
ok "a broken claim file (no expiry) is treated as free" '[ $rc = 0 ]'

out=$("$C" acquire "../x" 2>&1); rc=$?
ok "a key with .. or / -> rc 2" '[ $rc = 2 ]'
out=$("$C" frobnicate k 2>&1); rc=$?
ok "unknown command -> rc 2" '[ $rc = 2 ]'
out=$("$C" acquire k --ttl abc 2>&1); rc=$?
ok "non-numeric ttl -> rc 2" '[ $rc = 2 ]'
out=$("$C" 2>&1); rc=$?
ok "no arguments -> usage, rc 2" '[ $rc = 2 ] && [[ "$out" == usage* ]]'
echo "claim: $pass pass, $fail fail"; [ $fail = 0 ]
