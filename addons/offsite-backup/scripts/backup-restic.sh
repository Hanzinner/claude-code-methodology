#!/usr/bin/env bash
# Incremental encrypted backup of everything irreplaceable on this VM.
# Backend: Filebase (S3-compatible, 5 GB free). Encryption: restic (AES-256, chunk-level).
#
# What restic does that plain tar+gpg didn't:
#   - Chunks all files into ~4 MB blocks; only NEW/CHANGED chunks are uploaded.
#     First backup ~500 MB, every subsequent ~5-20 MB.
#   - Encryption is built-in (AES-256 with key derived from passphrase).
#   - Each run creates a "snapshot" (index of which chunks make up this state).
#     Restoring `latest` gives you exactly the state at last backup.
#
# What we back up:
#   - /home/<user>/claude-projects (memory, sessions, agents, code, secrets)
#   - /home/<user>/.claude (mobile-bot session, per-user config)
#   - /root/.claude (scripts, skills, hooks, sessions, credentials)
#   - /home/<user>/.ssh, /root/.ssh (SSH keys — for remote hosts + GitHub access)
#   - system manifest (cron, pkg lists) dumped to /tmp/system-manifest first
#
# What's excluded: restic-exclude.txt (msdocs, target, .rustup, node_modules, ...).
#
# Rotation: keep 14 daily + 8 weekly + 6 monthly. Runs `restic forget --prune` at end.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
source "$SCRIPT_DIR/restic-env.sh"

LOG=/var/log/restic-backup.log
EXCLUDE_FILE="$SCRIPT_DIR/restic-exclude.txt"
MANIFEST_DIR=/tmp/system-manifest

log() { echo "$(date -Iseconds) $*" | tee -a "$LOG"; }

log "=== restic backup start ==="

# Dump volatile system state that isn't in filesystem paths
rm -rf "$MANIFEST_DIR"
mkdir -p "$MANIFEST_DIR"
crontab -l > "$MANIFEST_DIR/root-crontab.txt" 2>/dev/null || true
sudo -u <user> crontab -l > "$MANIFEST_DIR/<user>-crontab.txt" 2>/dev/null || true
dpkg --get-selections > "$MANIFEST_DIR/apt-packages.txt" 2>/dev/null || true
pip freeze > "$MANIFEST_DIR/root-pip.txt" 2>/dev/null || true
sudo -u <user> pip freeze > "$MANIFEST_DIR/<user>-pip.txt" 2>/dev/null || true
uname -a > "$MANIFEST_DIR/uname.txt"
lsb_release -a > "$MANIFEST_DIR/os-release.txt" 2>/dev/null || true
sudo -u <user> gh auth status > "$MANIFEST_DIR/gh-auth.txt" 2>&1 || true
systemctl status <your-service> --no-pager > "$MANIFEST_DIR/mobile-bot-status.txt" 2>&1 || true
cp /etc/systemd/system/<your-service>.service "$MANIFEST_DIR/" 2>/dev/null || true
date -Iseconds > "$MANIFEST_DIR/backup-timestamp.txt"

# Copy the recovery instructions alongside the manifest — a fresh Claude on
# a new machine reads THIS file first, then follows steps to restore.
cp "$SCRIPT_DIR/RECOVERY.md" "$MANIFEST_DIR/RECOVERY.md"

# Ensure restic repo is initialized (idempotent — succeeds silently if already init'd)
if ! restic snapshots --last 1 >/dev/null 2>&1; then
    log "repo not initialized — running restic init"
    restic init
fi

log "starting incremental backup"
restic backup \
    --exclude-file="$EXCLUDE_FILE" \
    --exclude-caches \
    --tag daily \
    --host <hostname> \
    /home/<user>/claude-projects \
    /home/<user>/.claude \
    /root/.claude \
    /home/<user>/.ssh \
    /root/.ssh \
    "$MANIFEST_DIR" \
    2>&1 | tee -a "$LOG"

log "pruning old snapshots (keep 14d + 8w + 6m)"
restic forget \
    --keep-daily 14 \
    --keep-weekly 8 \
    --keep-monthly 6 \
    --prune \
    2>&1 | tee -a "$LOG"

log "current snapshots on repo:"
restic snapshots --compact 2>&1 | tee -a "$LOG"

rm -rf "$MANIFEST_DIR"

log "=== restic backup done ==="
