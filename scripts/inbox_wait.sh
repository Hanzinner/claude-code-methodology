#!/usr/bin/env bash
# inbox_wait.sh - an agent's alarm clock. The agent starts it IN THE BACKGROUND (Bash run_in_background) before it
# stands down to wait. It exits as soon as a new item appears in "## New" of the agent's inbox, or the time given in
# --until comes, or --max seconds pass. The exit of a background task wakes the agent in the SAME tab (not a twin).
# Why: agents with open work kept stopping and the human had to pick them up again and again.
#
# Usage: inbox_wait.sh <agent> [--until HH:MM] [--max SECONDS (default and ceiling: 3300 = 55 min)]
# CEILING: a harness may kill a background task after some time ("background time limit", status killed), so an alarm
#   for 3 hours is a promise the environment does not keep. The script exits by itself at the ceiling with a MEANINGFUL
#   line ("time is up, arm again", and how long is left until --until). "STATE: waiting until 10:00" is the goal; the
#   alarm is a chain of 55-minute links, each link one short turn of the agent. 55 min because the prompt cache lives
#   an hour and every read prolongs it: wake-ups stay warm; 25-minute links would double the number of turns.
#   hooks/inbox-wait-timeout.py adds `timeout` to a bare background call as insurance.
# MODE: $CCM_ALARM_MODE_DIR/<agent> (default ~/.claude/alarm-mode) holds one word:
#   off - does not start · once - wakes on a letter, then sets itself to off · auto (default) - a link with no
#   letters after an hour of silence says "gone out" · always - never gives up until --max/--until.
set -uo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
source "$HERE/inbox_lib.sh"
agent="${1:?agent}"; shift || true
until_hm=""; CEIL=${INBOX_WAIT_CEIL:-3300}; max=$CEIL
while [[ $# -gt 0 ]]; do
    case "$1" in
        --until) until_hm="$2"; shift 2 ;;
        --max) max="$2"; shift 2 ;;
        *) shift ;;
    esac
done
inbox=$("${INBOX_RESOLVE:-$HERE/inbox_resolve.sh}" "$agent" 2>/dev/null) || inbox=""
[[ -f "$inbox" ]] || { echo "inbox_wait: no inbox found for '$agent'"; exit 2; }
agent=$(basename "$(dirname "$inbox")")   # an alias or an old name works; from here on we live under the real name
MODE_DIR=${ALARM_MODE_DIR:-${CCM_ALARM_MODE_DIR:-$HOME/.claude/alarm-mode}}; AUTO_IDLE=${ALARM_AUTO_IDLE:-3600}
mode=$(awk 'NR==1{print $1}' "$MODE_DIR/$agent" 2>/dev/null); [[ "$mode" =~ ^(off|once|auto|always)$ ]] || mode=auto
if [[ "$mode" == off ]]; then
    echo "🔕 alarm mode of $agent is off (only the human wakes it). Not starting; end your turn with a STATE line."; exit 0
fi

new_hdr=$(find_new_hdr "$inbox")
new_items() { awk -v hdr="$new_hdr" 'index($0,hdr)==1{f=1;next} /^## /{f=0} f && /^- \[ \]/' "$inbox" 2>/dev/null; }
count_new() { new_items | awk 'END{print NR}'; }
file_age() { python3 -c 'import os,sys,time;print(int(time.time()-os.path.getmtime(sys.argv[1])))' "$inbox" 2>/dev/null || echo 0; }
# Wake on a NEW line in "New", not on the counter: the agent closed A, B arrived -> the counter is the same but the
# letter is new (an alarm that counts would sleep through it until --max).
until_epoch=""
if [[ -n "$until_hm" ]]; then
    until_epoch=$(python3 - "$until_hm" <<'PY' 2>/dev/null || true
import sys, time, datetime
h, m = sys.argv[1].split(":")
t = datetime.datetime.now().replace(hour=int(h), minute=int(m), second=0, microsecond=0)
if t.timestamp() <= time.time():
    t += datetime.timedelta(days=1)
print(int(t.timestamp()))
PY
)
fi
base=$(count_new); base_file=$(mktemp); new_items | sort > "$base_file"; start=$(date +%s)
# One alarm per agent (agents once started it on every reply: 18 links, every letter woke them all). A live alarm of
# this agent exists -> do not start another link.
mkdir -p "$HOME/.claude/inbox-wait"
alive_waiter() {   # -> pid of a live inbox_wait.sh of this agent, other than me
    local p c; p=$(cat "$HOME/.claude/inbox-wait/$agent" 2>/dev/null)
    if [[ -n "$p" && "$p" != "$$" ]] && c=$(ps -o command= -p "$p" 2>/dev/null) && [[ "$c" == *inbox_wait* && " $c " == *" $agent "* ]]; then
        echo "$p"; return 0; fi
    return 1
}
# The session of a process = its nearest ancestor named "claude" (two tabs with the same identity: "already armed"
# used to look only at the name, and the second tab stayed without an alarm for an hour with 22 letters).
session_of() {
    local p=$1 n=0 c
    while [[ "$p" -gt 1 && $n -lt 40 ]]; do
        c=$(ps -o comm= -p "$p" 2>/dev/null); c=${c##*/}
        [[ "$c" == claude ]] && { echo "$p"; return 0; }
        p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ') || return 1
        [[ -n "$p" ]] || return 1
        n=$((n+1))
    done
    return 1
}
old=""
if old=$(alive_waiter); then
    if [[ "$(session_of "$old")" == "$(session_of $$)" ]]; then
        rm -f "$base_file"
        echo "🔔 the alarm of $agent is already armed (pid $old) - not starting a second. Do nothing: it will wake you on a letter; end your turn with a STATE line."
        exit 0
    fi
    echo "🔔 the alarm of $agent is armed in ANOTHER tab (pid $old) - arming a separate one for this session."
fi
# Marker "someone is waiting" (pid, so it can be checked for life). A live alarm of another tab is not overwritten: on
# exit we would erase the file and its alarm would disappear for anyone who looks, though it stands.
[[ -n "$old" ]] || echo $$ > "$HOME/.claude/inbox-wait/$agent"
# Erase only OUR pid: a second alarm of the same agent overwrote the file - leave it alone.
trap 'rm -f "$base_file"; [[ "$(cat "$HOME/.claude/inbox-wait/$agent" 2>/dev/null)" == "$$" ]] && rm -f "$HOME/.claude/inbox-wait/$agent"' EXIT
# "Also waiting": on an exit without a letter the coordinator sees who else stands waiting and for how long - a chain
# "Dev waited for Design 22 min, the coordinator waited for a letter". Agents from $WORK_GUARD_AGENTS (a list file,
# one name per line); with no such file, every agent that has a live alarm.
etime_min() {   # elapsed minutes of a pid, portable ([[dd-]hh:]mm:ss)
    ps -o etime= -p "$1" 2>/dev/null | awk '{n=split($1,a,/[-:]/); s=0; if(n==2)s=a[1]*60+a[2]; else if(n==3)s=a[1]*3600+a[2]*60+a[3]; else if(n==4)s=a[1]*86400+a[2]*3600+a[3]*60+a[4]; print int(s/60)}'
}
others_waiting() {
    local a p e out="" list="${WORK_GUARD_AGENTS:-$HOME/.claude/work_guard_agents.txt}" names=""
    if [[ -f "$list" ]]; then names=$(cat "$list"); else names=$(ls "$HOME/.claude/inbox-wait" 2>/dev/null); fi
    while read -r a; do
        [[ -z "$a" || "$a" == \#* || "$a" == "$agent" ]] && continue
        p=$(cat "$HOME/.claude/inbox-wait/$a" 2>/dev/null) || continue
        [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null || continue
        e=$(etime_min "$p"); [[ -n "$e" ]] && out+="$a $e min, "
    done <<< "$names"
    [[ -n "$out" ]] && echo "👥 also waiting: ${out%, }"
    return 0
}
while true; do
    now=$(date +%s)
    n=$(count_new)
    # Wake only on a LINE that was not there at the start (closing one of several is not a new letter).
    # No `| grep -q` under pipefail: grep's early exit -> SIGPIPE -> "nothing new" for a new letter.
    if [[ "$n" -gt 0 && -n "$(new_items | sort | comm -13 "$base_file" -)" ]]; then
        if [[ "$mode" == once ]]; then
            { mkdir -p "$MODE_DIR" && echo off > "$MODE_DIR/.$agent.tmp" && mv -f "$MODE_DIR/.$agent.tmp" "$MODE_DIR/$agent"; } 2>/dev/null
            echo "📬 $(date +%H:%M) a new letter in the inbox of $agent ($base -> $n in New). The alarm was one-shot - now off. Read \"New\" and carry on."; exit 0
        fi
        echo "📬 $(date +%H:%M) a new letter in the inbox of $agent ($base -> $n in New). Read \"New\" and carry on."; exit 0
    fi
    if [[ -n "$until_epoch" && "$now" -ge "$until_epoch" ]]; then
        echo "⏰ $(date +%H:%M) the time you were waiting for, $until_hm, has come. Do what you postponed."; exit 0
    fi
    if [[ $((now - start)) -ge "$CEIL" && ( -n "$until_epoch" || "$max" -gt "$CEIL" ) ]]; then      # ceiling of a background task's life: leave on our own before we are killed
        left=""; [[ -n "$until_epoch" ]] && left=" $(( (until_epoch - now) / 60 )) min left until $until_hm."
        echo "⏳ $(date +%H:%M) the alarm served its link ($((CEIL/60)) min - a background task does not live longer), no letters.$left If you are still waiting, start it again with the same command, without a long report."; exit 0
    fi
    if [[ $((now - start)) -ge "$max" ]]; then
        others_waiting
        if [[ "$mode" == auto && $(file_age) -ge "$AUTO_IDLE" ]]; then
            echo "🌙 $(date +%H:%M) auto mode: $((AUTO_IDLE/60)) min without letters - the alarm went out by itself. Do not restart it; you will see a new letter when you are woken."; exit 0
        fi
        echo "⌛ $(date +%H:%M) $((max/60)) min of waiting passed with no letters. Look at your TODO for anything doable; if nothing - STATE: waiting + inbox_wait again."; exit 0
    fi
    sleep "${INBOX_WAIT_POLL:-20}"
done
