#!/usr/bin/env bash
# System part of the agent-browser add-on. Idempotent. Needs root (except --dry-run, which only prints).
#   setup-agent-browser.sh [--dry-run] [--link] [--browser-service] [--chrome PATH] [--port 9333] [--user NAME]
#   setup-agent-browser.sh --uninstall [--dry-run]
# --link             symlink br and br-ask into /usr/local/bin
# --browser-service  systemd unit "agent-browser.service": a headless Chrome/Chromium with remote debugging on
#                    127.0.0.1:PORT, run as an unprivileged user (created if missing), profile in /var/lib/agent-browser.
#                    Skip this if you already run a Chrome with --remote-debugging-port yourself (then set BR_CDP).
# --uninstall        stops and removes the unit and the symlinks it created. Keeps the profile dir and the user.
set -euo pipefail
here=$(dirname "$(readlink -f "$0")")
UNIT=${AB_UNIT_PATH:-/etc/systemd/system/agent-browser.service}
BIN=${AB_BIN_DIR:-/usr/local/bin}
PROFILE=${AB_PROFILE_DIR:-/var/lib/agent-browser}
dry=0; link=0; svc=0; un=0; chrome=""; port=9333; user=agent-browser
while [ $# -gt 0 ]; do case "$1" in
  --dry-run) dry=1 ;; --link) link=1 ;; --browser-service) svc=1 ;; --uninstall) un=1 ;;
  --chrome) chrome=$2; shift ;; --port) port=$2; shift ;; --user) user=$2; shift ;;
  -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
  *) echo "setup-agent-browser: unknown option $1" >&2; exit 2 ;; esac; shift; done
[[ "$port" =~ ^[0-9]+$ ]] || { echo "setup-agent-browser: --port must be a number" >&2; exit 2; }
[[ "$user" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "setup-agent-browser: bad --user name" >&2; exit 2; }
if [ $dry = 0 ] && [ "$(id -u)" != 0 ]; then echo "setup-agent-browser: run as root (sudo) - it writes a systemd unit and links into $BIN. Use --dry-run to preview." >&2; exit 1; fi
do_() { if [ $dry = 1 ]; then echo "[dry-run] $*"; else echo "+ $*"; "$@"; fi; }
[ $link = 0 ] && [ $svc = 0 ] && [ $un = 0 ] && { echo "nothing selected: pass --link and/or --browser-service (or --uninstall)"; exit 0; }

if [ $un = 1 ]; then
  if [ -e "$UNIT" ]; then do_ systemctl disable --now agent-browser.service || true; do_ rm -f "$UNIT"; do_ systemctl daemon-reload; fi
  for n in br br-ask; do [ -L "$BIN/$n" ] && [ "$(readlink -f "$BIN/$n")" = "$here/$n" ] && do_ rm -f "$BIN/$n"; done
  echo "uninstalled. Kept: $PROFILE (browser profile) and user $user."; exit 0
fi

if [ $link = 1 ]; then
  for n in br br-ask; do
    if [ -L "$BIN/$n" ] && [ "$(readlink -f "$BIN/$n")" = "$here/$n" ]; then echo "$BIN/$n already linked"
    elif [ -e "$BIN/$n" ]; then echo "setup-agent-browser: $BIN/$n exists and is not ours - not touching it" >&2; exit 1
    else do_ ln -s "$here/$n" "$BIN/$n"; fi
  done
fi

if [ $svc = 1 ]; then
  if [ -z "$chrome" ]; then for c in google-chrome-stable google-chrome chromium chromium-browser; do command -v "$c" >/dev/null 2>&1 && { chrome=$(command -v "$c"); break; }; done; fi
  [ -n "$chrome" ] || { [ $dry = 1 ] && chrome=/usr/bin/chromium || { echo "setup-agent-browser: no Chrome/Chromium found - install one or pass --chrome PATH" >&2; exit 1; }; }
  id "$user" >/dev/null 2>&1 || do_ useradd --system --create-home --home-dir "$PROFILE" --shell /usr/sbin/nologin "$user"
  unit="[Unit]
Description=Headless Chrome for agents (remote debugging on 127.0.0.1:$port)
After=network-online.target

[Service]
User=$user
ExecStart=$chrome --headless=new --remote-debugging-port=$port --remote-debugging-address=127.0.0.1 --user-data-dir=$PROFILE/profile --no-first-run --disable-gpu about:blank
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target"
  if [ -e "$UNIT" ] && [ "$(cat "$UNIT")" = "$unit" ]; then echo "$UNIT already up to date"
  elif [ $dry = 1 ]; then echo "[dry-run] would write $UNIT:"; echo "$unit" | sed 's/^/    /'
  else echo "+ write $UNIT"; printf '%s\n' "$unit" > "$UNIT"; fi
  do_ systemctl daemon-reload
  do_ systemctl enable --now agent-browser.service
  echo "browser at http://127.0.0.1:$port  (BR_CDP default). It is a REAL browser profile: anything logged in there is reachable by anyone who can reach that port - keep it on localhost."
fi
