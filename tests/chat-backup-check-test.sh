#!/usr/bin/env bash
# chat_backup_check.sh. CB=<path> tests another copy.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" HANZ_TEST=1 CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_AGENTS_DIR="$T/Agents"; mkdir -p "$HOME" "$T/ws"
printf "#!/bin/sh\necho \"\$1|\${2:-\$(cat)}\" >> %s/letters\n" "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/letters"; export CCM_INBOX_POST="$T/post"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | sed "s/^/   /"; fi; }
CB=${CB:-$HERE/../scripts/chat_backup_check.sh}
export BACKUP_LOG="$T/b.log" BACKUP_DIR="$T/bk"; mkdir -p "$BACKUP_DIR"
now() { date -d "$1" '+%Y-%m-%d %H:%M:%S'; }
day() { mkdir -p "$BACKUP_DIR/$(date -d "$1" +%F)/home"; echo '{}' > "$BACKUP_DIR/$(date -d "$1" +%F)/home/s.jsonl"; }
run() { out=$(bash "$CB" 2>&1); rc=$?; }
run; ok "1 no log -> rc 3" '[ $rc = 3 ]'
echo "[$(now '1 hour ago')] backup: today=1M total=2M days_kept=3" > "$BACKUP_LOG"; day '1 hour ago'; run
ok "2 fresh success and .jsonl in the day folder -> rc 0" '[ $rc = 0 ]'
echo "[$(now '30 hours ago')] backup: today=1M total=2M days_kept=3" > "$BACKUP_LOG"; day '30 hours ago'; run
ok "3 success but older than 26 h -> rc 1" '[ $rc != 0 ]'
echo "[$(now '1 hour ago')] FAIL rsync rc=23" > "$BACKUP_LOG"; run
ok "4 the last line is FAIL -> rc 1" '[ $rc = 1 ]'
echo "[$(now '1 hour ago')] backup: today=0 total=2M days_kept=3" > "$BACKUP_LOG"; find "$BACKUP_DIR" -mindepth 1 -delete; mkdir -p "$BACKUP_DIR/$(date -d '1 hour ago' +%F)"; run
ok "5 fresh success but no .jsonl in the day folder -> rc 1" '[ $rc != 0 ]'
echo "[$(now '30 hours ago')] backup: x" > "$BACKUP_LOG"; day '30 hours ago'; MAX_H=48 bash "$CB" >/dev/null 2>&1
ok "6 MAX_H=48 accepts 30 h" '[ $? = 0 ]'
echo "chat-backup-check: $pass pass, $fail fail"; [ $fail = 0 ]
