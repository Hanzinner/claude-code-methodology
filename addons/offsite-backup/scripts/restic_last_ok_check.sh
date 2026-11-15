#!/usr/bin/env bash
# Supervisor check: the age of the last SUCCESSFUL restic backup (the line "=== restic backup done ===" in the backup log).
# Why not the freshness of the log: a broken backup also writes to the log every run (its own error) - one setup showed
# 21 hours of green while the offsite copy was dead (storage quota exhausted). Only the "done" line proves a finished run.
# Env: MAX_MIN (default 150 = two missed hourly runs; use ~1560 for a nightly-only schedule), BACKUP_LOG.
# rc 0 = fresh enough, 1 = too old / no success / no log.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
source "$(dirname "$(readlink -f "$0")")/backup-common.sh"
LOG=$BACKUP_LOG; MAX_MIN=${MAX_MIN:-150}
[[ -f "$LOG" ]] || { echo "no backup log at $LOG"; exit 1; }
# -a: restic's progress bar writes control characters; without -a grep says "binary file matches" and prints nothing.
last=$(grep -a "=== restic backup done ===" "$LOG" | tail -1 | cut -d' ' -f1)
[[ -n "$last" ]] || { echo "no successful backup in the log"; exit 1; }
age=$(( ( $(date +%s) - $(date -d "$last" +%s) ) / 60 ))
# Look for the error only AFTER the last success: otherwise the alarm quotes an old one.
n=$(grep -an "=== restic backup done ===" "$LOG" | tail -1 | cut -d: -f1)
tailog=$(tail -n +"$n" "$LOG")
if grep -aq "storage cap exceeded" <<<"$tailog"; then err="storage hit its size cap - writes are impossible, free space"
elif grep -aq "cap exceeded" <<<"$tailog"; then err="a daily API cap is exhausted (403); it resets daily"
else err=$(grep -aE "^Fatal:|rc=[0-9]+ -" <<<"$tailog" | tail -1 | cut -c1-120); fi
echo "last successful backup ${age} min ago ($last); limit ${MAX_MIN}${err:+; last error: $err}"
(( age <= MAX_MIN ))
