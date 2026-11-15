#!/usr/bin/env bash
# setup-offsite-backup.sh - installs the offsite backup add-on: copies its scripts, checks that restic is installed, writes the
# cron lines into the CURRENT user's crontab (a marked block; idempotent). install.sh --with-offsite-backup runs this.
# Run it as the user whose files are backed up (root if you back up /root/.claude too). No root needed: nothing system-wide
# is touched (no systemd, no sudoers, no /etc). --dry-run prints every change and makes none; --uninstall removes the cron block.
#
# What it changes:
#   1. copies scripts/* -> <dest> (default <CCM_CLAUDE_DIR>/scripts/backup); RECOVERY.md only if it is not there yet
#      (it is YOUR filled-in copy afterwards - never overwritten)
#   2. copies restic.env.template -> <CCM_SECRETS_DIR>/restic.env.template (it does NOT create restic.env: that holds your keys)
#   3. checks `restic` is on PATH (not installed: real run stops with rc 3 and an install hint; --dry-run only warns)
#   4. crontab block (backup-restic.sh runs under `timeout 50m`; its own log is <state>/backup.log, cron output <state>/cron.log):
#        hourly schedule (default):  <M> every hour except <H>, SKIP_PRUNE=1 (backup only; prune is heavy)
#                                    <M> <H> * * *   the nightly run: backup + prune (prune only if BACKUP_PRUNE=1 in restic.env)
#                                    @reboot sleep 180 && backup-catchup.sh   (a run missed while the machine was off)
#        nightly schedule:           only the <M> <H> line + @reboot
#   Deleting snapshots happens only when you set BACKUP_PRUNE=1 in restic.env; this script never deletes backup data.
#
#   setup-offsite-backup.sh [--schedule hourly|nightly] [--hour H] [--minute M] [--dest DIR] [--no-copy] [--no-cron]
#                           [--dry-run] [--uninstall]
# exit: 0 ok · 2 usage · 3 restic not installed
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
INSTALL=$(readlink -f "$HERE/../.." 2>/dev/null || true)
conf_get() { local v="${!1:-}"; if [[ -z "$v" && -f "$INSTALL/lib/ccm_conf.py" ]]; then v=$(python3 "$INSTALL/lib/ccm_conf.py" "$1" 2>/dev/null || true); fi; printf '%s' "$v"; }
CLAUDE_DIR=$(conf_get CCM_CLAUDE_DIR); CLAUDE_DIR=${CLAUDE_DIR:-$HOME/.claude}
SECRETS=$(conf_get CCM_SECRETS_DIR); SECRETS=${SECRETS:-$HOME/.config/claude-secrets}
STATE=$(conf_get CCM_BACKUP_STATE); STATE=${STATE:-$HOME/.claude/offsite-backup}
dest="$CLAUDE_DIR/scripts/backup"; schedule=hourly; hour=3; minute=17; copy=1; cron=1; dry=0; uninstall=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --schedule) schedule=${2:?}; shift 2 ;;
        --hour) hour=${2:?}; shift 2 ;;
        --minute) minute=${2:?}; shift 2 ;;
        --dest) dest=${2:?}; shift 2 ;;
        --no-copy) copy=0; shift ;;
        --no-cron) cron=0; shift ;;
        --dry-run) dry=1; shift ;;
        --uninstall) uninstall=1; shift ;;
        -h|--help) sed -n '2,23p' "$0"; exit 0 ;;
        *) echo "unknown flag $1 (see --help)" >&2; exit 2 ;;
    esac
done
[[ "$schedule" == hourly || "$schedule" == nightly ]] || { echo "--schedule must be hourly or nightly" >&2; exit 2; }
[[ "$hour" =~ ^([0-9]|1[0-9]|2[0-3])$ ]] || { echo "--hour must be 0-23" >&2; exit 2; }
[[ "$minute" =~ ^([0-9]|[1-5][0-9])$ ]] || { echo "--minute must be 0-59" >&2; exit 2; }
do_() { echo "  + $*"; (( dry )) || "$@"; }
(( dry )) && echo "(dry run: nothing is changed)"

BEGIN="# >>> ccm offsite-backup >>>"; END="# <<< ccm offsite-backup <<<"
strip_block() { awk -v b="$BEGIN" -v e="$END" '$0==b{s=1;next} $0==e{s=0;next} !s' ; }
cur=$(crontab -l 2>/dev/null || true)

if (( uninstall )); then
    echo "uninstall: removing the cron block (scripts, keys, state and the backup data itself stay)"
    if grep -qF "$BEGIN" <<<"$cur"; then
        echo "  + remove the '$BEGIN' block from the crontab"
        (( dry )) || { strip_block <<<"$cur" | crontab -; }
    else echo "  no cron block - ok"; fi
    echo "done"; exit 0
fi

# 1-2. files
if (( copy )); then
    echo "scripts -> $dest"
    do_ mkdir -p "$dest"
    for f in "$HERE"/scripts/*; do do_ cp -p "$f" "$dest/"; done
    if [[ -f "$dest/RECOVERY.md" ]]; then echo "  $dest/RECOVERY.md exists (your copy) - kept"
    else do_ cp "$HERE/RECOVERY.md.template" "$dest/RECOVERY.md"; echo "    -> open it and fill in the <placeholders>"; fi
    do_ mkdir -p "$SECRETS"
    do_ cp "$HERE/restic.env.template" "$SECRETS/restic.env.template"
    if [[ -f "$SECRETS/restic.env" ]]; then echo "  $SECRETS/restic.env exists - kept"
    else echo "  next: cp $SECRETS/restic.env.template $SECRETS/restic.env && chmod 600 $SECRETS/restic.env  (then fill it in)"; fi
fi

# 3. restic
if command -v restic >/dev/null 2>&1; then echo "restic: $(command -v restic) - ok"
else
    echo "restic is NOT installed. Install it: Debian/Ubuntu 'sudo apt-get install restic' · macOS 'brew install restic' · Fedora 'sudo dnf install restic' (need >= 0.14)" >&2
    (( dry )) || exit 3
fi

# 4. cron
if (( cron )); then
    R=$(command -v restic 2>/dev/null || true); rpath="/usr/local/bin:/usr/bin:/bin${R:+:$(dirname "$R")}"
    T=$(command -v timeout 2>/dev/null || echo timeout)
    run="PATH=$rpath $T -k 60 50m $dest/backup-restic.sh >> $STATE/cron.log 2>&1"
    block="$BEGIN
# written by setup-offsite-backup.sh - do not edit inside the block (re-run the script instead)"
    if [[ "$schedule" == hourly ]]; then
        if (( hour == 0 )); then hrs="1-23"; elif (( hour == 23 )); then hrs="0-22"
        else hrs="0-$((hour-1)),$((hour+1))-23"; fi
        block+=$'\n'"$minute $hrs * * * SKIP_PRUNE=1 $run"
    fi
    block+=$'\n'"$minute $hour * * * $run"
    block+=$'\n'"@reboot sleep 180 && PATH=$rpath $dest/backup-catchup.sh >> $STATE/cron.log 2>&1"
    block+=$'\n'"$END"
    do_ mkdir -p "$STATE"
    if grep -qF "$BEGIN" <<<"$cur" && [[ "$(awk -v b="$BEGIN" -v e="$END" '$0==b{s=1} s{print} $0==e{s=0}' <<<"$cur")" == "$block" ]]; then
        echo "crontab block already up to date - ok"
    else
        echo "crontab block:"; sed 's/^/      /' <<<"$block"
        if (( ! dry )); then { strip_block <<<"$cur"; printf '%s\n' "$block"; } | crontab -; fi
    fi
else echo "cron skipped (--no-cron)"; fi
echo "next: fill restic.env, put the passphrase in a file, run  $dest/backup-restic.sh  once by hand to see the first backup finish"
echo "supervisor: install.sh merges addons/offsite-backup/supervisor-checks.json into the registry"
echo "done"
