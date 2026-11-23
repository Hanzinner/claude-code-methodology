#!/usr/bin/env bash
# Keeps the dashboard running: a systemd --user unit "ccm-dashboard.service" for dashboard.py (127.0.0.1:PORT), enabled
# and started now, plus `loginctl enable-linger` so it runs after a reboot and after you log out. No root.
# Idempotent; --dry-run only prints. Where there is no systemd (macOS, most containers) it changes nothing and says how
# to start the page by hand - never an error: the page itself works without any of this.
#   setup-dashboard.sh [--dry-run] [--python CMD] [--port 8765]
#   setup-dashboard.sh --uninstall [--dry-run]    # stop, disable, the unit file to the trash; linger is left as it is
# CCM_SYSTEMCTL / CCM_LOGINCTL: the command to call instead of systemctl / loginctl (tests: stand-ins that log).
# exit: 0 done or nothing to do here · 2 usage
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
SYSTEMCTL=${CCM_SYSTEMCTL:-systemctl}
LOGINCTL=${CCM_LOGINCTL:-loginctl}
NAME=ccm-dashboard.service
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/$NAME"
dry=0; un=0; py=python3; port=8765
while [ $# -gt 0 ]; do case "$1" in
  --dry-run) dry=1 ;; --uninstall) un=1 ;;
  --python) py=${2:?--python needs a command}; shift ;;
  --port) port=${2:?--port needs a number}; shift ;;
  -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
  *) echo "setup-dashboard: unknown option $1" >&2; exit 2 ;; esac; shift; done
[[ "$port" =~ ^[0-9]+$ ]] || { echo "setup-dashboard: --port must be a number" >&2; exit 2; }
# ExecStart needs a full path; "py -3" (Windows) stays as it is - there is no systemd there, it only goes into the hint
case "$py" in */*|*" "*) ;; *) p=$(command -v "$py" 2>/dev/null) && py=$p ;; esac
DASH="$here/dashboard.py"
me=$(id -un)
do_() { if [ $dry = 1 ]; then echo "  [dry-run] $*"; else echo "  + $*"; "$@"; fi; }
by_hand() {
  echo "  start it by hand: nohup $(printf '%q' "$py") $(printf '%q' "$DASH") --port $port >> ~/.claude/logs/dashboard.log 2>&1 &"
  echo "  (it stops with the machine; on macOS a launchd agent or a tmux window keeps it running)"
}

if ! command -v "$SYSTEMCTL" >/dev/null 2>&1; then
  echo "dashboard: no systemd on this machine (macOS, a container) - no service set up."; by_hand; exit 0
fi
# the binary can be there while no user manager runs: a container without systemd as PID 1, or a shell with no login
# session (no XDG_RUNTIME_DIR). A unit written then would never start, and enable would only print a bus error.
if ! "$SYSTEMCTL" --user show-environment >/dev/null 2>&1; then
  echo "dashboard: systemd's user manager is not reachable from this shell (a container, or no login session) - no service set up."
  by_hand
  echo "  or, from a login session: bash $(printf '%q' "$here/setup-dashboard.sh")"
  exit 0
fi

if [ $un = 1 ]; then
  do_ "$SYSTEMCTL" --user disable --now "$NAME" || true
  if [ -e "$UNIT" ]; then
    # "delete" = the trash folder of this install (CCM_TRASH_DIR), so an edited unit can be taken back
    trash=$("$py" "$here/../../lib/ccm_conf.py" CCM_TRASH_DIR 2>/dev/null) || trash="$HOME/.claude-trash"
    do_ mkdir -p "$trash"
    do_ mv "$UNIT" "$trash/$NAME.$(date +%Y%m%d-%H%M%S)"
  else echo "  $UNIT not present - ok"; fi
  do_ "$SYSTEMCTL" --user daemon-reload || true
  echo "dashboard service removed. Linger is left as it is (other user services may need it): loginctl disable-linger $me to turn it off."
  exit 0
fi

# systemd reads ExecStart itself: a path with a quote, backslash, % or $ would be read as something else
for v in "$py" "$DASH"; do
  case "$v" in *[\"\\%\$]*) echo "setup-dashboard: this path cannot go into a systemd unit as it is: $v" >&2; by_hand; exit 2 ;; esac
done
unit="[Unit]
Description=claude-code-methodology dashboard (read-only agent status on 127.0.0.1:$port)

[Service]
ExecStart=\"$py\" \"$DASH\" --port $port
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target"
changed=1
if [ -f "$UNIT" ] && [ "$(cat "$UNIT")" = "$unit" ]; then echo "  $UNIT already up to date"; changed=0
elif [ $dry = 1 ]; then echo "  [dry-run] would write $UNIT:"; printf '%s\n' "$unit" | sed 's/^/      /'
else
  echo "  + write $UNIT"
  mkdir -p "$UNIT_DIR"
  printf '%s\n' "$unit" > "$UNIT.tmp" && mv "$UNIT.tmp" "$UNIT"
fi
do_ "$SYSTEMCTL" --user daemon-reload
do_ "$SYSTEMCTL" --user enable "$NAME"
# restart, not start, after a change: start leaves an already running old version as it is
if [ $changed = 1 ]; then do_ "$SYSTEMCTL" --user restart "$NAME"; else do_ "$SYSTEMCTL" --user start "$NAME"; fi

# without linger systemd stops every user service when the last session of this user ends, and starts none at boot
if ! command -v "$LOGINCTL" >/dev/null 2>&1; then
  echo "  no loginctl here: the dashboard runs while you are logged in. To keep it running: sudo loginctl enable-linger $me"
elif [ "$("$LOGINCTL" show-user "$me" --property=Linger --value 2>/dev/null)" = yes ]; then
  echo "  linger already on for $me - it runs after a reboot and after you log out"
elif [ $dry = 1 ]; then echo "  [dry-run] $LOGINCTL enable-linger $me"
elif "$LOGINCTL" enable-linger "$me" 2>/dev/null; then
  echo "  + $LOGINCTL enable-linger $me - it runs after a reboot and after you log out"
else
  echo "  linger could not be turned on without root: the dashboard stops when you log out. Run once: sudo loginctl enable-linger $me"
fi
if [ $dry = 0 ]; then
  st=""
  for _ in 1 2 3 4 5; do   # "activating" for a moment right after the start
    st=$("$SYSTEMCTL" --user is-active "$NAME" 2>/dev/null) || true
    [ "$st" = active ] && break; sleep 1
  done
  if [ "$st" = active ]; then echo "dashboard: running as $NAME - http://127.0.0.1:$port/"
  else echo "dashboard: $NAME is ${st:-not active} - see: systemctl --user status $NAME" >&2; fi
fi
