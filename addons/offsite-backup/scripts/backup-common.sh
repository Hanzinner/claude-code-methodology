#!/usr/bin/env bash
# Sourced by every script of the offsite-backup add-on: where the state lives and how to read a setting.
# Setting lookup: an environment variable of that name wins, then methodology.conf (through lib/ccm_conf.py), then the default.
# State dir (CCM_BACKUP_STATE, default ~/.claude/offsite-backup) holds: backup.log, last-success stamp, bucket-size
# file (+ .hist), lock files. Nothing in here deletes anything.

_BC_HERE=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
_BC_CONF=""
for _d in "$_BC_HERE/../../lib" "$_BC_HERE/../lib" "$HOME/.claude/lib"; do
    [[ -f "$_d/ccm_conf.py" ]] && { _BC_CONF="$_d/ccm_conf.py"; break; }
done
# The same lib folder has ccm_compat.sh (a stock macOS: no date -d / date -Iseconds) and ccm_lock.sh (no flock).
# A copy without them (an old install) keeps the GNU commands, as before.
_BC_LIB=${_BC_CONF%/ccm_conf.py}
if [[ -n "$_BC_CONF" && -f "$_BC_LIB/ccm_compat.sh" ]]; then . "$_BC_LIB/ccm_compat.sh"; fi
type ccm_now_iso >/dev/null 2>&1 || ccm_now_iso() { date -Iseconds; }
type ccm_epoch >/dev/null 2>&1 || ccm_epoch() { date -d "$1" +%s; }

# ccm_get KEY [DEFAULT]
ccm_get() {
    local v="${!1:-}"
    if [[ -z "$v" && -n "$_BC_CONF" ]]; then v=$(python3 "$_BC_CONF" "$1" 2>/dev/null || true); fi
    printf '%s' "${v:-${2:-}}"
}

CCM_SECRETS_DIR=$(ccm_get CCM_SECRETS_DIR "$HOME/.config/claude-secrets")
CCM_WORKSPACE=$(ccm_get CCM_WORKSPACE "$HOME/claude-projects")
BACKUP_STATE=$(ccm_get CCM_BACKUP_STATE "$HOME/.claude/offsite-backup")
BACKUP_LOG=${BACKUP_LOG:-$BACKUP_STATE/backup.log}
BACKUP_STAMP=${BACKUP_STAMP:-$BACKUP_STATE/last-success}     # epoch of the last finished run (read by backup-catchup.sh)
BACKUP_SIZE_FILE=${BACKUP_SIZE_FILE:-$BACKUP_STATE/size}     # "<epoch> <bytes>" written by backup-restic.sh, read by restic_size_check.sh
