#!/usr/bin/env bash
# setup-mobile-bot.sh - the system side of the mobile bot add-on. NOT run by default: install.sh calls it only on
# --with-mobile-bot. Needs root (refuses otherwise, except --dry-run). Idempotent; prints every change;
# --dry-run changes nothing; --uninstall takes the system parts back out.
#
# What it changes on the machine:
#   1. the secrets file  <CCM_SECRETS_DIR>/mobile-bot.env  (0600, the bot's user) - created from .env.template if absent.
#      The bot token, the allowlist of Telegram user ids; the PIN hash goes to <CCM_SECRETS_DIR>/mobile-bot-auth.json
#      (written by the bot on /setpin). The script NEVER writes a token and never prints a value.
#   2. a systemd unit  /etc/systemd/system/ccm-mobile-bot.service  (from systemd/claude-mobile-bot.service.template).
#      Started right away unless --no-start (it will not start by itself without a token in the secrets file).
#   3. only with --with-swarm (letters to agents from the phone, answers from agents, "B2 yes" for blockers):
#        /usr/local/sbin/ccm-bot-inbox    root helper: a letter into an agent's inbox (+ optional tab waker)
#        /usr/local/sbin/ccm-bot-blocker  root helper: clear a blocker by the human's word
#        /etc/sudoers.d/ccm-mobile-bot    "<bot user> ALL=(root) NOPASSWD:" for exactly these two files (visudo-checked);
#                                         skipped when the bot runs as root
#        the outbox spool  <outbox>  (default /var/spool/ccm-tg-outbox, the bot's user, mode 1777): where
#                                         scripts/tg_reply.sh of any agent drops its answers for the human
#      --with-wake additionally lets the inbox helper wake an agent's live tab after a letter (a short `claude -p`
#      on Haiku, about 3.6k tokens each time = your quota). Off by default.
#   4. the log /var/log/ccm-mobile-bot.log (the bot's user).
#
#   setup-mobile-bot.sh [--user BOT_USER] [--owner AGENT_OWNER] [--workdir DIR] [--allow-paths A:B] [--with-swarm]
#                       [--with-wake] [--outbox DIR] [--env-file FILE] [--no-start] [--dry-run] [--uninstall]
#   --user     the account the bot runs as (default: the owner of the add-on folder). Give the bot its own narrow account
#              when you can: the secret zones in the gate are a list of known names, not a sandbox.
#   --owner    the account whose ~/.claude holds the agents' sessions (default: the owner of CCM_WORKSPACE)
#   --workdir  the folder Claude works in (default CCM_WORKSPACE)
# exit: 0 ok · 2 usage · 5 not root
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
for rel in .. ../..; do [[ -f "$HERE/$rel/lib/ccm_conf.py" ]] && { INSTALL=$(readlink -f "$HERE/$rel"); break; }; done
[[ -n "${INSTALL:-}" ]] || { echo "cannot find lib/ccm_conf.py above $HERE" >&2; exit 2; }
eval "$(python3 "$INSTALL/lib/ccm_conf.py" --shell)"
bot_user=$(stat -c %U "$HERE"); owner=$(stat -c %U "${CCM_WORKSPACE:-/}" 2>/dev/null || echo "$bot_user")
workdir=${CCM_WORKSPACE}; allow=""; swarm=0; wake=0; outbox=${CCM_TG_OUTBOX:-/var/spool/ccm-tg-outbox}
envfile="$CCM_SECRETS_DIR/mobile-bot.env"; start=1; dry=0; uninstall=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --user) bot_user=${2:?}; shift 2 ;;
        --owner) owner=${2:?}; shift 2 ;;
        --workdir) workdir=${2:?}; shift 2 ;;
        --allow-paths) allow=${2:?}; shift 2 ;;
        --with-swarm) swarm=1; shift ;;
        --with-wake) wake=1; shift ;;
        --outbox) outbox=${2:?}; shift 2 ;;
        --env-file) envfile=${2:?}; shift 2 ;;
        --no-start) start=0; shift ;;
        --dry-run) dry=1; shift ;;
        --uninstall) uninstall=1; shift ;;
        -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
        *) echo "unknown flag $1 (see --help)" >&2; exit 2 ;;
    esac
done
if (( ! dry )) && [[ "$(id -u)" != 0 ]]; then echo "setup-mobile-bot.sh must run as root (it writes into /etc, /usr/local/sbin and /var); use --dry-run to see what it would do" >&2; exit 5; fi
(( wake )) && swarm=1
id "$bot_user" >/dev/null 2>&1 || { echo "bot user $bot_user does not exist" >&2; exit 2; }
id "$owner" >/dev/null 2>&1 || { echo "owner user $owner does not exist" >&2; exit 2; }
for v in "$workdir" "$allow" "$outbox" "$envfile"; do
    [[ "$v" != *[$' \t\n"\\']* ]] || { echo "paths without spaces, quotes or backslashes only (systemd Environment lines): $v" >&2; exit 2; }
done
bot_home=$(getent passwd "$bot_user" | cut -d: -f6); owner_home=$(getent passwd "$owner" | cut -d: -f6)
do_() { echo "  + $*"; (( dry )) || "$@"; }
(( dry )) && echo "(dry run: nothing is changed)"
unit=/etc/systemd/system/ccm-mobile-bot.service
sbin=/usr/local/sbin; sudoers=/etc/sudoers.d/ccm-mobile-bot; log=/var/log/ccm-mobile-bot.log

if (( uninstall )); then
    echo "uninstall: the unit, the two root helpers and the sudoers file. The secrets file, the PIN file, the outbox and the bot's state stay (remove by hand if you want)."
    command -v systemctl >/dev/null && { do_ systemctl disable --now ccm-mobile-bot.service || true; }
    for f in "$unit" "$sbin/ccm-bot-inbox" "$sbin/ccm-bot-blocker" "$sudoers"; do
        if [[ -e "$f" ]]; then do_ rm -f "$f"; else echo "  $f not present - ok"; fi
    done
    command -v systemctl >/dev/null && { do_ systemctl daemon-reload || true; }
    exit 0
fi

echo "bot user: $bot_user · agent owner: $owner · workdir: $workdir · swarm: $swarm · wake: $wake"
# 1. the secrets file
do_ install -d -o "$bot_user" -m 0700 "$(dirname "$envfile")"
if [[ -f "$envfile" ]]; then echo "  $envfile exists - left as it is"
else do_ install -o "$bot_user" -m 0600 "$HERE/.env.template" "$envfile"; echo "  -> fill TELEGRAM_BOT_TOKEN and ALLOWED_TG_USERS in $envfile"; fi
# 4. the log
if [[ -f "$log" ]]; then echo "  $log exists - ok"; else do_ install -o "$bot_user" -m 0640 /dev/null "$log"; fi
# 3. swarm parts
sudo_prefix="sudo -n"
if (( swarm )); then
    agents=${CCM_AGENTS_DIR}
    fill() { # fill <template> <target>
        local tmp; tmp=$(mktemp)
        sed -e "s|__AGENTS_DIR__|$agents|g" -e "s|__CLAUDE_DIR__|$INSTALL|g" -e "s|__OWNER_HOME__|$owner_home|g" \
            -e "s|__HUMAN_NAME__|${CCM_HUMAN_NAME//|/ }|g" -e "s|__REPLY_CMD__|$HERE/scripts/tg_reply.sh|g" \
            -e "s|__WAKE__|$wake|g" -e "s|__CONF_FILE__|$(python3 "$INSTALL/lib/ccm_conf.py" --file)|g" "$1" > "$tmp"
        if [[ -f "$2" ]] && cmp -s "$tmp" "$2"; then echo "  $2 already up to date - ok"; rm -f "$tmp"
        else echo "  + install $2 (root, 0755)"; (( dry )) || install -o root -g root -m 0755 "$tmp" "$2"; rm -f "$tmp"; fi
    }
    [[ -d "$agents" ]] || echo "  warning: the agents dir $agents does not exist yet (the helpers will refuse until it does)"
    fill "$HERE/helpers/ccm-bot-inbox.template" "$sbin/ccm-bot-inbox"
    fill "$HERE/helpers/ccm-bot-blocker.template" "$sbin/ccm-bot-blocker"
    if [[ "$bot_user" == root ]]; then
        sudo_prefix=""; echo "  the bot runs as root: no sudoers entry, the helpers are called directly"
    else
        t=$(mktemp)
        { echo "# written by setup-mobile-bot.sh: the bot may run exactly these two helpers as root"
          echo "$bot_user ALL=(root) NOPASSWD: $sbin/ccm-bot-inbox, $sbin/ccm-bot-blocker"; } > "$t"
        if command -v visudo >/dev/null && ! visudo -cf "$t" >/dev/null 2>&1; then echo "the generated sudoers file did not pass visudo:" >&2; cat "$t" >&2; rm -f "$t"; exit 2; fi
        if [[ -f "$sudoers" ]] && cmp -s "$t" "$sudoers"; then echo "  $sudoers already up to date - ok"
        else echo "  + install $sudoers (0440):"; sed 's/^/      /' "$t"; (( dry )) || install -m 0440 -o root -g root "$t" "$sudoers"; fi
        rm -f "$t"
    fi
    if [[ -d "$outbox" && "$(stat -c '%U %a' "$outbox")" == "$bot_user 1777" ]]; then echo "  $outbox ($bot_user, 1777) - ok"
    else do_ install -d -o "$bot_user" -m 1777 "$outbox"; fi
fi
# 2. the unit
t=$(mktemp)
sed -e "s|__USER__|$bot_user|g" -e "s|__WORKDIR__|$workdir|g" -e "s|__ENV_FILE__|$envfile|g" -e "s|__BOT_HOME__|$bot_home|g" \
    -e "s|__ALLOW_PATHS__|$allow|g" -e "s|__SWARM__|$swarm|g" -e "s|__SUDO__|$sudo_prefix|g" -e "s|__OUTBOX__|$outbox|g" \
    -e "s|__INSTALL_DIR__|$HERE|g" -e "s|__LOG__|$log|g" "$HERE/systemd/claude-mobile-bot.service.template" > "$t"
if [[ -f "$unit" ]] && cmp -s "$t" "$unit"; then echo "  $unit already up to date - ok"
else echo "  + install $unit (0644)"; (( dry )) || install -m 0644 -o root -g root "$t" "$unit"; fi
rm -f "$t"
if command -v systemctl >/dev/null; then
    do_ systemctl daemon-reload
    if (( start )); then do_ systemctl enable --now ccm-mobile-bot.service; else echo "  (--no-start: not enabled; run: systemctl enable --now ccm-mobile-bot.service)"; fi
else echo "  systemctl not found: start the bot by hand (see README)"; fi
echo "done. Logs: $log"
