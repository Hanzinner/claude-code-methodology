#!/usr/bin/env bash
# Incremental encrypted backup of everything irreplaceable on this machine, with restic.
# Backend: Backblaze B2 (10 GB free) or any S3-compatible storage - see restic-env.sh / restic.env.template.
#
# What restic does that plain tar+gpg doesn't:
#   - chunks files into ~4 MB blocks; only NEW/CHANGED chunks are uploaded (first run 1-3 GB, then ~5-20 MB);
#   - encryption is built in (AES-256, key derived from the passphrase);
#   - each run is a "snapshot"; restoring `latest` gives exactly the state at the last backup.
#
# What is backed up (BACKUP_PATHS in restic.env, or CCM_BACKUP_PATHS, colon-separated; only existing paths are used):
#   default: ~/.claude, the workspace (CCM_WORKSPACE), ~/.ssh, the secrets dir (CCM_SECRETS_DIR; the passphrase file is
#   excluded) and a small manifest (crontab, package lists) written to $MANIFEST_DIR first.
# Excluded: restic-exclude.txt (regenerable or huge things).
#
# Modes (set by cron, see setup-offsite-backup.sh):
#   hourly run  - SKIP_PRUNE=1: backup only (prune is heavy)
#   nightly run - backup + `restic forget --prune` with the retention below - but ONLY when BACKUP_PRUNE=1 in restic.env.
#                 Without it nothing is ever deleted from the repository (it just grows).
# Stale lock left by a killed run: `restic unlock` before prune removes only stale locks (a killed run once made every prune
# fail for 11 days while the backups themselves kept "succeeding").
# A finished run writes "=== restic backup done ===" to the log and the epoch to the stamp file; the supervisor checks
# (restic_last_ok_check.sh) read the log, backup-catchup.sh reads the stamp.
# Test hook: nothing here talks to anything but the `restic` binary found on PATH (and b2_usage.py on the b2 backend).

set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
source "$SCRIPT_DIR/restic-env.sh"

mkdir -p "$BACKUP_STATE"
LOG=$BACKUP_LOG
EXCLUDE_FILE="$SCRIPT_DIR/restic-exclude.txt"
MANIFEST_DIR=${MANIFEST_DIR:-/tmp/ccm-system-manifest}
SIZE_FILE=$BACKUP_SIZE_FILE
STAMP=$BACKUP_STAMP
HOST=${BACKUP_HOST:-$(hostname 2>/dev/null || echo this-machine)}
PRUNE=${BACKUP_PRUNE:-0}

log() { echo "$(ccm_now_iso) $*" | tee -a "$LOG"; }

# One run at a time: a slow upload must not overlap the next cron run (they fight over the repo lock).
if command -v flock >/dev/null 2>&1; then
    exec 8>"$BACKUP_STATE/backup.lock"
    flock -n 8 || { echo "$(ccm_now_iso) SKIP: another run is still going" >> "$LOG"; exit 0; }
elif [[ -n "${_BC_LIB:-}" && -f "$_BC_LIB/ccm_lock.sh" ]]; then   # no flock (macOS): the mkdir lock of lib/ccm_lock.sh
    . "$_BC_LIB/ccm_lock.sh"
    ccm_lock 8 "$BACKUP_STATE/backup.lock" 0 120 || { echo "$(ccm_now_iso) SKIP: another run is still going" >> "$LOG"; exit 0; }
fi

log "=== restic backup start ==="

# Volatile system state that is not in any file path
rm -rf "$MANIFEST_DIR"; mkdir -p "$MANIFEST_DIR"
crontab -l > "$MANIFEST_DIR/crontab.txt" 2>/dev/null || true
dpkg --get-selections > "$MANIFEST_DIR/apt-packages.txt" 2>/dev/null || true
pip freeze > "$MANIFEST_DIR/pip.txt" 2>/dev/null || true
uname -a > "$MANIFEST_DIR/uname.txt"
cp /etc/os-release "$MANIFEST_DIR/os-release.txt" 2>/dev/null || true
ccm_now_iso > "$MANIFEST_DIR/backup-timestamp.txt"

# The recovery instructions travel inside the snapshot: a fresh Claude on a new machine reads THIS file first.
if [[ -f "$SCRIPT_DIR/RECOVERY.md" ]]; then
    cp "$SCRIPT_DIR/RECOVERY.md" "$MANIFEST_DIR/RECOVERY.md"
else
    log "WARNING: $SCRIPT_DIR/RECOVERY.md missing - the snapshot has no recovery guide (copy RECOVERY.md.template there)"
fi

# Is the repository initialised? rc 10 = no repo; other codes (11 = lock, network, wrong key) are NOT a reason to init
# (a dead process's lock once showed up for 10 h as "not initialised"). restic's stderr goes to the log: a bare "rc=1"
# once hid "storage cap exceeded" for two days.
errf=$(mktemp); rc=0; restic snapshots --latest 1 >/dev/null 2>"$errf" || rc=$?
grep -m3 -E "cap exceeded|Fatal|403|401" "$errf" | sed "s/^/  restic: /" >> "$LOG" || true; rm -f "$errf"
if [ "$rc" = 10 ]; then
    log "repo not initialized - running restic init"
    restic init
elif [ "$rc" = 11 ]; then
    log "repo locked - removing the lock of a dead process (restic unlock touches only stale ones)"
    restic unlock
elif [ "$rc" != 0 ]; then
    log "restic snapshots rc=$rc - not starting the backup"
    exit "$rc"
fi

# Storage ceiling (BEFORE the backup, so a cleanup can free space before the new write hits the cap).
# B2's free tier is 10 GB; hitting it stopped the backups for two days. Every run measures the REAL bucket size (not
# `restic stats`, which cannot see unused pack parts) and keeps a history for restic_size_check.sh (threshold + growth rate).
# Above BACKUP_SOFT_BYTES an emergency prune runs at once (only with BACKUP_PRUNE=1): it repacks no more than the free room
# and no more than 450 MB (free download is 1 GB/day), and at most once per 20 h.
CAP=${BACKUP_CAP_BYTES:-10000000000}; SOFT=${BACKUP_SOFT_BYTES:-$(( CAP / 10 * 9 ))}
if [[ "${BACKUP_BACKEND:-b2}" == b2 ]]; then sz=$(python3 -I "$SCRIPT_DIR/b2_usage.py" 2>>"$LOG") || sz=""
else sz=$(restic stats --mode raw-data --json 2>>"$LOG" | python3 -c 'import sys,json;print(json.load(sys.stdin)["total_size"])' 2>/dev/null) || sz=""; fi
if [[ "$sz" =~ ^[0-9]+$ ]]; then
    echo "$(date +%s) $sz" > "$SIZE_FILE.tmp" && mv "$SIZE_FILE.tmp" "$SIZE_FILE"
    echo "$(date +%s) $sz" >> "$SIZE_FILE.hist"; tail -n 400 "$SIZE_FILE.hist" > "$SIZE_FILE.hist.tmp" && mv "$SIZE_FILE.hist.tmp" "$SIZE_FILE.hist"
    log "storage size: $sz bytes"
    if (( sz > SOFT )); then
        room=$(( CAP - sz - 12000000 )); (( room > 450000000 )) && room=450000000
        EMERG="$BACKUP_STATE/emergency-prune"
        if [[ "$PRUNE" != 1 ]]; then
            log "WARN: storage above $SOFT bytes but BACKUP_PRUNE is not 1 - nothing is cleaned; free space by hand (see RECOVERY.md)"
        elif (( room > 8000000 )) && [ -z "$(find "$EMERG" -mmin -1200 2>/dev/null)" ]; then
            log "WARN: storage above $SOFT - emergency prune, repacking up to $room bytes"
            touch "$EMERG"
            restic prune --max-unused 3% --max-repack-size "$room" 2>&1 | grep -E 'to repack:|unused size after|Fatal' | tee -a "$LOG" || log "WARN: emergency prune failed"
        elif (( room > 8000000 )); then
            log "storage above $SOFT; an emergency prune already ran within 20 h - waiting (download limit)"
        else
            log "WARN: storage almost full ($sz) - no room even for a prune; a manual cleanup is needed"
        fi
    fi
else
    log "WARN: could not measure the storage size"
fi

# Back up only paths that exist (a missing one would fail the whole run)
paths_spec=${BACKUP_PATHS:-$(ccm_get CCM_BACKUP_PATHS "$HOME/.claude:$CCM_WORKSPACE:$HOME/.ssh:$CCM_SECRETS_DIR")}
paths=()
IFS=: read -ra _p <<< "$paths_spec"
for p in "${_p[@]}"; do [[ -n "$p" && -e "$p" ]] && paths+=("$p"); done
[[ ${#paths[@]} -gt 0 ]] || { log "no backup path exists ($paths_spec) - nothing to do"; exit 1; }

log "starting incremental backup"
restic backup \
    --exclude-file="$EXCLUDE_FILE" \
    --exclude-caches \
    ${BACKUP_COMPRESSION:+--compression "$BACKUP_COMPRESSION"} \
    --tag daily \
    --host "$HOST" \
    ${paths[@]+"${paths[@]}"} \
    "$MANIFEST_DIR" \
    2>&1 | tee -a "$LOG"

if [[ -z "${SKIP_PRUNE:-}" ]]; then
    if [[ "$PRUNE" == 1 ]]; then
        log "pruning old snapshots (keep ${BACKUP_KEEP_HOURLY:-24} hourly + ${BACKUP_KEEP_DAILY:-7} daily + ${BACKUP_KEEP_WEEKLY:-4} weekly + ${BACKUP_KEEP_MONTHLY:-3} monthly)"
        restic unlock >/dev/null 2>&1 || true
        restic forget \
            --keep-hourly "${BACKUP_KEEP_HOURLY:-24}" \
            --keep-daily "${BACKUP_KEEP_DAILY:-7}" \
            --keep-weekly "${BACKUP_KEEP_WEEKLY:-4}" \
            --keep-monthly "${BACKUP_KEEP_MONTHLY:-3}" \
            --prune --max-unused 5% --max-repack-size "${BACKUP_MAX_REPACK:-450M}" \
            2>&1 | tee -a "$LOG"
        log "current snapshots on repo:"
        restic snapshots --compact 2>&1 | tee -a "$LOG"
    else
        log "BACKUP_PRUNE is not 1 - old snapshots are kept (nothing is deleted)"
    fi
fi

rm -rf "$MANIFEST_DIR"
date +%s > "$STAMP"
log "=== restic backup done ==="
