#!/usr/bin/env bash
# Boot catch-up for the backup (cron: @reboot sleep 180 && backup-catchup.sh).
# Why: a machine that is switched off or crashes misses the scheduled runs - 4 nights without a snapshot in 2 weeks.
# Now: 3 minutes after boot, if the last successful run is older than BACKUP_CATCHUP_MIN (default 90) minutes, run the
# backup right away (without prune - prune is the nightly run's job).
set -uo pipefail
source "$(dirname "$(readlink -f "$0")")/backup-common.sh"
HERE=$(dirname "$(readlink -f "$0")")
mkdir -p "$BACKUP_STATE"
MAX_MIN=${BACKUP_CATCHUP_MIN:-90}
last=$(cat "$BACKUP_STAMP" 2>/dev/null || echo 0); [[ "$last" =~ ^[0-9]+$ ]] || last=0
if (( $(date +%s) - last > MAX_MIN*60 )); then
    echo "$(ccm_now_iso) BOOT-CATCHUP: last success $(( ($(date +%s)-last)/3600 )) h ago - catching up" >> "$BACKUP_LOG"
    SKIP_PRUNE=1 "$HERE/backup-restic.sh" >> "$BACKUP_LOG" 2>&1
fi
