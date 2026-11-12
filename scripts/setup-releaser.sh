#!/usr/bin/env bash
# setup-releaser.sh - the system side of the release queue (scripts/releaser.py). NOT run by default: the installer calls it only on
# an explicit flag. Needs root (refuses otherwise, except --dry-run). Idempotent; prints every change; --dry-run changes nothing.
#
# What it changes on the machine:
#   1. a SYSTEM user  <releaser user> (default `releaser`): no login shell, no home, its own group. Gates and deploy commands run as
#      this user, in its own clone, so they cannot write into the shared tree (see the header of releaser.py).
#   2. folders:  <state>                (root, 0755)      default /var/lib/ccm-release
#                <state>/queue          (<owner>, 0755)   release markers; agents (running as <owner>) put them here
#                <state>/work           (<releaser user>, 0755)  the releaser's clones
#   3. optional, only with --sudo-cmd "<absolute command>" (repeatable): /etc/sudoers.d/ccm-releaser with one line per command,
#      "<releaser user> ALL=(root) NOPASSWD: <command>", checked with visudo before it is installed. For the one thing a gate
#      cannot do without root, e.g. restarting a service in deploy_test. No wildcards, absolute path only.
#   4. optional, only with --cron: /etc/cron.d/ccm-releaser with the three jobs below.
# It does NOT edit methodology.conf: if you pass non-default --user/--state/--owner, it prints the lines to add.
#
# Cron jobs (what --cron writes; or add them to root's crontab by hand):
#   */5 * * * *  root  /usr/bin/python3 <install dir>/scripts/releaser.py run >/dev/null 2>&1
#   30 3 * * *   root  /usr/bin/python3 <install dir>/scripts/project_drift.py >/dev/null 2>&1
#   23 * * * *   root  /usr/bin/python3 <install dir>/scripts/repo_stale.py >/dev/null 2>&1
#
#   setup-releaser.sh [--owner USER] [--user NAME] [--state DIR] [--sudo-cmd CMD]... [--cron] [--dry-run]
# exit: 0 ok · 2 usage · 5 not root
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
INSTALL=$(readlink -f "$HERE/..")
eval "$(python3 "$INSTALL/lib/ccm_conf.py" --shell)"
user=${CCM_RELEASER_USER:-$(python3 "$INSTALL/lib/ccm_conf.py" CCM_RELEASER_USER)}; user=${user:-releaser}
state=${CCM_RELEASER_STATE:-$(python3 "$INSTALL/lib/ccm_conf.py" CCM_RELEASER_STATE)}; state=${state:-/var/lib/ccm-release}
owner=${CCM_RELEASER_OWNER:-$(python3 "$INSTALL/lib/ccm_conf.py" CCM_RELEASER_OWNER)}
[[ -n "$owner" ]] || owner=$(stat -c %U "$CCM_WORKSPACE" 2>/dev/null || true)
sudo_cmds=(); cron=0; dry=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --owner) owner=${2:?}; shift 2 ;;
        --user) user=${2:?}; shift 2 ;;
        --state) state=${2:?}; shift 2 ;;
        --sudo-cmd) sudo_cmds+=("${2:?}"); shift 2 ;;
        --cron) cron=1; shift ;;
        --dry-run) dry=1; shift ;;
        -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
        *) echo "unknown flag $1 (see --help)" >&2; exit 2 ;;
    esac
done
if (( ! dry )) && [[ "$(id -u)" != 0 ]]; then echo "setup-releaser.sh must run as root (it creates a user and writes into /var/lib and /etc); use --dry-run to see what it would do" >&2; exit 5; fi
[[ "$user" =~ ^[a-z_][a-z0-9_-]{0,30}$ ]] || { echo "bad user name: $user" >&2; exit 2; }
[[ -n "$owner" ]] || { echo "cannot tell who owns the shared tree: pass --owner USER" >&2; exit 2; }
id "$owner" >/dev/null 2>&1 || { echo "owner user $owner does not exist" >&2; exit 2; }
for c in "${sudo_cmds[@]:-}"; do
    [[ -z "$c" || ( "$c" == /* && "$c" != *'*'* && "$c" != *$'\n'* && "$c" != *'!'* ) ]] || { echo "--sudo-cmd must be an absolute command without wildcards: $c" >&2; exit 2; }
done
do_() { echo "  + $*"; (( dry )) || "$@"; }
(( dry )) && echo "(dry run: nothing is changed)"
echo "releaser user: $user · shared-tree owner: $owner · state: $state"

# 1. the user
if id "$user" >/dev/null 2>&1; then echo "  user $user exists - ok"
else do_ useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$user"; fi
# 2. folders
mk() { # mk <dir> <owner> <mode>
    if [[ -d "$1" && "$(stat -c '%U %a' "$1")" == "$2 $3" ]]; then echo "  $1 ($2, $3) - ok"; return; fi
    do_ install -d -o "$2" -g "$(id -gn "$2" 2>/dev/null || echo "$2")" -m "$3" "$1"
}
if (( dry )) && ! id "$user" >/dev/null 2>&1; then
    echo "  + install -d $state (root 0755), $state/queue ($owner 0755), $state/work ($user 0755)   [user $user would exist by then]"
else
    mk "$state" root 755; mk "$state/queue" "$owner" 755; mk "$state/work" "$user" 755
fi
# 3. sudoers
if [[ ${#sudo_cmds[@]} -gt 0 ]]; then
    f=/etc/sudoers.d/ccm-releaser; tmp=$(mktemp)
    { echo "# written by setup-releaser.sh: the gate user may run exactly these commands as root"
      for c in "${sudo_cmds[@]}"; do echo "$user ALL=(root) NOPASSWD: $c"; done; } > "$tmp"
    if command -v visudo >/dev/null && ! visudo -cf "$tmp" >/dev/null 2>&1; then echo "the generated sudoers file did not pass visudo:" >&2; cat "$tmp" >&2; rm -f "$tmp"; exit 2; fi
    if [[ -f "$f" ]] && cmp -s "$tmp" "$f"; then echo "  $f already up to date - ok"; rm -f "$tmp"
    else echo "  + install $f (0440):"; sed 's/^/      /' "$tmp"; (( dry )) || install -m 0440 -o root -g root "$tmp" "$f"; rm -f "$tmp"; fi
fi
# 4. cron
cron_body="# written by setup-releaser.sh
*/5 * * * * root /usr/bin/python3 $INSTALL/scripts/releaser.py run >/dev/null 2>&1
30 3 * * * root /usr/bin/python3 $INSTALL/scripts/project_drift.py >/dev/null 2>&1
23 * * * * root /usr/bin/python3 $INSTALL/scripts/repo_stale.py >/dev/null 2>&1"
if (( cron )); then
    f=/etc/cron.d/ccm-releaser
    if [[ -f "$f" ]] && [[ "$(cat "$f")" == "$cron_body" ]]; then echo "  $f already up to date - ok"
    else echo "  + write $f:"; echo "$cron_body" | sed 's/^/      /'; (( dry )) || { printf '%s\n' "$cron_body" > "$f"; chmod 644 "$f"; }; fi
else
    echo "  cron not installed (no --cron). Add these lines to root's crontab:"; echo "$cron_body" | tail -n +2 | sed 's/ root / /; s/^/      /'
fi
# config lines for non-default values
extra=""
[[ "$user" == releaser ]] || extra+="CCM_RELEASER_USER=$user"$'\n'
[[ "$state" == /var/lib/ccm-release ]] || extra+="CCM_RELEASER_STATE=$state"$'\n'
[[ "$owner" == "$(stat -c %U "$CCM_WORKSPACE" 2>/dev/null || true)" ]] || extra+="CCM_RELEASER_OWNER=$owner"$'\n'
[[ -z "$extra" ]] || { echo "  non-default values: put these lines into methodology.conf so releaser.py and git-guard see them:"; printf '%s' "$extra" | sed 's/^/      /'; }
echo "next: each project's lead fills release.toml (test command) and root runs  releaser.py approve <Project>"
echo "done"
