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
