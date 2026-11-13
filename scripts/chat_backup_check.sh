#!/usr/bin/env bash
# chat_backup_check.sh - watchdog for the local chat backup (backup-chats.sh): the last result line in the log is
# "backup:" (success) and not older than MAX_H hours, and today's folder holds at least one .jsonl.
# A "FAIL" line = rsync failed. Exit: 0 ok | 1 bad/stale | 3 no run in the log.
# Settings: BACKUP_LOG (default ~/.claude/logs/chat-backup.log: redirect the backup cron line there),
# BACKUP_DIR (default ~/.claude-backups, as in backup-chats.sh), MAX_H (default 26).
# The log line format is what backup-chats.sh prints: "[YYYY-MM-DD HH:MM:SS] backup: ..." or "[...] FAIL ...".
set -uo pipefail
L=${BACKUP_LOG:-${L:-$HOME/.claude/logs/chat-backup.log}}; B=${BACKUP_DIR:-${B:-$HOME/.claude-backups}}; MAX_H=${MAX_H:-26}
last=$(grep -E '^\[[0-9-]+ [0-9:]+\] (backup:|Backup done|FAIL)' "$L" 2>/dev/null | tail -1)
[[ -n $last ]] || { echo "no run in $L"; exit 3; }
ts=${last:1:19}; age_h=$(( ($(date +%s) - $(date -d "$ts" +%s)) / 3600 ))
day=$B/${ts:0:10}; n=$(find "$day" -name '*.jsonl' 2>/dev/null | head -1000 | wc -l)
echo "last run ${age_h} h ago: ${last#*] }; .jsonl in ${day##*/}: ${n}"
[[ $last == *FAIL* ]] && exit 1
(( age_h <= MAX_H && n > 0 ))
