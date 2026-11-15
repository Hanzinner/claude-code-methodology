#!/usr/bin/env bash
# System part of the net-change add-on. Idempotent. Needs root (except --dry-run, which only prints).
#   setup-net-change.sh [--dry-run]           install: link net-change into /usr/local/bin, create the state dir
#   setup-net-change.sh --uninstall [--dry-run]   remove the link; keeps the state dir and the log (snapshots are your safety history)
# It does NOT touch any network configuration. A pending rollback timer (systemctl list-timers 'net-change-rollback-*')
# is left alone: finish or cancel it by hand.
set -euo pipefail
here=$(dirname "$(readlink -f "$0")")
BIN=${NC_BIN_DIR:-/usr/local/bin}
STATE=${NC_STATE_DIR:-/var/lib/net-change}
dry=0; un=0
for a in "$@"; do case "$a" in --dry-run) dry=1 ;; --uninstall) un=1 ;; -h|--help) sed -n '2,6p' "$0"; exit 0 ;; *) echo "setup-net-change: unknown option $a" >&2; exit 2 ;; esac; done
if [ $dry = 0 ] && [ "$(id -u)" != 0 ]; then echo "setup-net-change: run as root (sudo) - it links into $BIN and creates $STATE. Use --dry-run to preview." >&2; exit 1; fi
do_() { if [ $dry = 1 ]; then echo "[dry-run] $*"; else echo "+ $*"; "$@"; fi; }
if [ $un = 1 ]; then
  if [ -L "$BIN/net-change" ] && [ "$(readlink -f "$BIN/net-change")" = "$here/net-change" ]; then do_ rm -f "$BIN/net-change"; else echo "$BIN/net-change is not our link - nothing to remove"; fi
  echo "uninstalled. Kept: $STATE and the log."; exit 0
fi
command -v systemd-run >/dev/null 2>&1 || echo "warning: systemd-run not found - the automatic rollback needs systemd; net-change will refuse to run" >&2
if [ -L "$BIN/net-change" ] && [ "$(readlink -f "$BIN/net-change")" = "$here/net-change" ]; then echo "$BIN/net-change already linked"
elif [ -e "$BIN/net-change" ]; then echo "setup-net-change: $BIN/net-change exists and is not ours - not touching it" >&2; exit 1
else do_ ln -s "$here/net-change" "$BIN/net-change"; fi
[ -d "$STATE" ] && echo "$STATE exists" || do_ install -d -m 700 "$STATE"
echo "next: net-change --dry-run -- <your change command>   (shows the detected restart command and the check)"
