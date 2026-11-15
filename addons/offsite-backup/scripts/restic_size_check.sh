#!/usr/bin/env bash
# Supervisor check: the REAL size of the storage against the free-tier cap (B2: 10 GB). backup-restic.sh writes
# "<epoch> <bytes>" to the size file on every run, plus a history (.hist).
# Why: measuring `restic stats` (live data only, 8.53 GB) once a night against a 9.4 limit stayed silent while the bucket held
# 9.98 GB, until storage hit the cap (two days without a backup). Now: the real size, a lower threshold, and the growth
# per day (4.3 GB of test runs in two days is what filled it).
# Env: MAX_GB (8.5) threshold · GROW_GB (0.5) max growth per day · MAX_AGE_H (3) a measurement older than this = the backup
# does not reach the measurement · SIZE_FILE. rc 0 ok, 1 problem.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
source "$(dirname "$(readlink -f "$0")")/backup-common.sh"
F=${SIZE_FILE:-$BACKUP_SIZE_FILE}; MAX_GB=${MAX_GB:-8.5}; MAX_AGE_H=${MAX_AGE_H:-3}; GROW_GB=${GROW_GB:-0.5}
read -r ts sz < "$F" 2>/dev/null || { echo "no storage size measurement ($F)"; exit 1; }
[[ $ts =~ ^[0-9]+$ && $sz =~ ^[0-9]+$ ]] || { echo "measurement is corrupt: '$ts $sz'"; exit 1; }
age=$(( ( $(date +%s) - ts ) / 3600 ))
# growth over ~24 h: the oldest history entry not older than a day
old=$(awk -v t=$(( $(date +%s) - 90000 )) '$1>=t {print $2; exit}' "$F.hist" 2>/dev/null)
grow=$(python3 -c "print(f'{($sz-${old:-$sz})/1e9:+.2f}')")
gb=$(python3 -c "print(f'{$sz/1e9:.2f}')")
echo "storage ${gb} GB (limit ${MAX_GB}); per day ${grow} GB (limit +${GROW_GB}); measured ${age} h ago"
(( age <= MAX_AGE_H )) || { echo "measurement is stale (> ${MAX_AGE_H} h) - does the backup reach the measurement step?"; exit 1; }
python3 -c "import sys; sys.exit(0 if $sz/1e9 <= $MAX_GB else 1)" || { echo "-> close to the cap: find what grew (restic diff of the two latest snapshots); put regenerable things into restic-exclude.txt"; exit 1; }
python3 -c "import sys; sys.exit(0 if ($sz-${old:-$sz})/1e9 <= $GROW_GB else 1)" || { echo "-> growing too fast: find what was added (restic diff) and exclude the regenerable"; exit 1; }
