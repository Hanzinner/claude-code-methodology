#!/usr/bin/env bash
# An agent answers the human in the Telegram bot chat.
# Usage: tg_reply.sh <your agent name> <<'EOF'  ⏎ text ⏎  EOF
# Why: a letter "📱 from <human> (Telegram bot)" came from a phone - the answer must go to the same place.
# The agent does NOT get the bot token: it drops a JSON file into the outbox spool (CCM_TG_OUTBOX); the bot
# picks it up every ~5 s, sends it with the header "📨 from <agent>" (into the agent's topic if there is a
# group) and moves it to sent/. The human replies to that message -> a letter lands in this agent's inbox again.
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
for rel in ../../lib ../../../lib ../lib; do   # installed: <install dir>/mobile-bot/scripts; in the repo: addons/mobile-bot/scripts
  [[ -f "$HERE/$rel/ccm_conf.py" ]] && { eval "$(python3 "$HERE/$rel/ccm_conf.py" --shell)"; break; }
done
SPOOL="${CCM_TG_OUTBOX:-/var/spool/ccm-tg-outbox}"
AGENTS="${CCM_AGENTS_DIR:-$HOME/claude-projects/Agents}"

[[ $# -eq 1 ]] || { echo "usage: tg_reply.sh <agent>   (the text is on stdin)" >&2; exit 2; }
a="$1"
case "$a" in ""|.*|-*|*/*|*\\*|*..*) echo "tg_reply: invalid agent name: '$a'" >&2; exit 2 ;; esac
compgen -G "$AGENTS/$a/briefing.md" >/dev/null || compgen -G "$AGENTS/[!_]*/$a/briefing.md" >/dev/null \
  || compgen -G "$AGENTS/$a/inbox.md" >/dev/null \
  || { echo "tg_reply: no agent '$a' (the exact folder name from the agents dir)" >&2; exit 2; }
[[ -d "$SPOOL" && -w "$SPOOL" ]] || { echo "tg_reply: the outbox $SPOOL does not exist or is not writable (run setup-mobile-bot.sh --with-swarm)" >&2; exit 2; }

raw=$(head -c 20001)
[[ $(printf '%s' "$raw" | wc -c) -le 20000 ]] || { echo "tg_reply: too long (>20 KB) - put it in a file and give the human the path" >&2; exit 2; }
[[ -n "${raw//[[:space:]]/}" ]] || { echo "tg_reply: empty text" >&2; exit 2; }
if printf '%s' "$raw" | grep -qE -- '-----BEGIN [A-Z ]*PRIVATE KEY-----|[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}|sk-ant-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}'; then
  echo "tg_reply: the text looks like a secret (a key/token) - not sending" >&2; exit 2
fi

name="$(date +%s%N)_$$"
tmp="$SPOOL/.$name.tmp"
A="$a" T="$raw" python3 -c 'import json,os,sys,time; json.dump({"agent":os.environ["A"],"text":os.environ["T"],"ts":int(time.time())}, sys.stdout, ensure_ascii=False)' > "$tmp"
chmod 0644 "$tmp"
mv -- "$tmp" "$SPOOL/$name.json"
echo "tg_reply: ✅ queued for Telegram (the bot sends within ~5 s)"
