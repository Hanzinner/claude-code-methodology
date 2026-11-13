#!/usr/bin/env bash
# prune_watchman_state.sh: deletes ONLY when switched on. PW=<path> tests another copy.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" HANZ_TEST=1 CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_AGENTS_DIR="$T/Agents"; mkdir -p "$HOME" "$T/ws"
printf "#!/bin/sh\necho \"\$1|\${2:-\$(cat)}\" >> %s/letters\n" "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/letters"; export CCM_INBOX_POST="$T/post"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | sed "s/^/   /"; fi; }
PW=${PW:-$HERE/../scripts/prune_watchman_state.sh}
export WATCHMAN_STATE_DIR="$T/wm"; mkdir -p "$WATCHMAN_STATE_DIR/sub"
reset() { echo x > "$WATCHMAN_STATE_DIR/old1"; echo x > "$WATCHMAN_STATE_DIR/sub/old2"; echo x > "$WATCHMAN_STATE_DIR/new1"; touch -d '40 days ago' "$WATCHMAN_STATE_DIR/old1" "$WATCHMAN_STATE_DIR/sub/old2"; }
reset; out=$(bash "$PW" 2>&1)
ok "1 default (flag off) -> NOTHING deleted, says disabled" '[ -f "$WATCHMAN_STATE_DIR/old1" ] && echo "$out" | grep -q disabled'
out=$(bash "$PW" --dry-run 2>&1)
ok "2 --dry-run lists old files, deletes nothing" '[ -f "$WATCHMAN_STATE_DIR/old1" ] && echo "$out" | grep -q "old1" && echo "$out" | grep -q "2 file(s)"'
out=$(CCM_PRUNE_WATCHMAN_STATE=1 bash "$PW" 2>&1)
ok "3 key on -> old files gone (also in subfolders), fresh kept" '[ ! -f "$WATCHMAN_STATE_DIR/old1" ] && [ ! -f "$WATCHMAN_STATE_DIR/sub/old2" ] && [ -f "$WATCHMAN_STATE_DIR/new1" ]'
reset; out=$(bash "$PW" --yes 2>&1)
ok "4 --yes works without the key" '[ ! -f "$WATCHMAN_STATE_DIR/old1" ] && [ -f "$WATCHMAN_STATE_DIR/new1" ]'
reset; out=$(CCM_PRUNE_WATCHMAN_STATE=1 CCM_PRUNE_DAYS=60 bash "$PW" 2>&1)
ok "5 CCM_PRUNE_DAYS=60 -> 40-day-old files stay" '[ -f "$WATCHMAN_STATE_DIR/old1" ]'
WATCHMAN_STATE_DIR="$T/none" CCM_PRUNE_WATCHMAN_STATE=1 bash "$PW" >/dev/null 2>&1; ok "6 no state dir -> rc 0" '[ $? = 0 ]'
echo "prune-watchman-state: $pass pass, $fail fail"; [ $fail = 0 ]
