#!/usr/bin/env bash
# git_snapshot_2fail_check.sh. SF=<path> tests another copy.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" HANZ_TEST=1 CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_AGENTS_DIR="$T/Agents"; mkdir -p "$HOME" "$T/ws"
printf "#!/bin/sh\necho \"\$1|\${2:-\$(cat)}\" >> %s/letters\n" "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/letters"; export CCM_INBOX_POST="$T/post"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | sed "s/^/   /"; fi; }
SF=${SF:-$HERE/../scripts/git_snapshot_2fail_check.sh}
export SNAP_LOG="$T/snap.log"
run() { out=$(bash "$SF" 2>&1); rc=$?; }
printf '2026-01-01T10:00:00+0000 commit OK (3 files)\n' > "$SNAP_LOG"; run
ok "1 only one result -> rc 3 (no verdict)" '[ $rc = 3 ]'
printf '2026-01-01T10:10:00+0000 commit OK (3 files)\n' >> "$SNAP_LOG"; run
ok "2 two OK -> rc 0" '[ $rc = 0 ]'
printf '2026-01-01T10:20:00+0000 ERROR: not a git repo: /x\n' >> "$SNAP_LOG"; run
ok "3 OK then one failure -> rc 0 (a single failure is another check)" '[ $rc = 0 ]'
printf '2026-01-01T10:30:00+0000 ERROR: not a git repo: /x\n' >> "$SNAP_LOG"; run
ok "4 two failures in a row -> rc 1 and the message" '[ $rc = 1 ] && echo "$out" | grep -q "TWICE"'
printf '2026-01-01T10:40:00+0000 commit OK (1 files)\n' >> "$SNAP_LOG"; run
ok "5 recovered -> rc 0" '[ $rc = 0 ]'
printf '2026-01-01T10:50:00+0000 WARN skipped\n2026-01-01T10:50:00+0000 ERROR x\n' >> "$SNAP_LOG"; run
ok "6 a WARN and an ERROR of ONE run (same timestamp) = ONE failure -> rc 0" '[ $rc = 0 ]'
printf '2026-01-01T10:55:00+0000 no changes - skipping\n' >> "$SNAP_LOG"; run
ok "6b \"no changes\" is not a result" '[ $rc = 0 ]'
SNAP_LOG="$T/none.log" bash "$SF" >/dev/null 2>&1; ok "7 no log -> rc 3" '[ $? = 3 ]'
echo "git-snapshot-2fail: $pass pass, $fail fail"; [ $fail = 0 ]
