#!/usr/bin/env bash
# claim.sh — the ONE sanctioned lock with a TTL for the swarm. Against the recovery deadlock: a process dies -> a claim
# without TTL hangs forever -> deadlock (it cost two hours once). Here a primitive without TTL simply does not exist:
# every claim carries an owner + an expiry; an expired claim is free. Raw claim files outside this script are
# forbidden by the rule.
#
# claim.sh acquire <key> [--ttl <min>] [--owner <who>]   (default ttl 30 min)
# claim.sh check   <key>       -> exit 0 free / exit 1 taken (prints by whom)
# claim.sh release <key> [--owner <who>]
# Events (taking over an expired claim, releasing someone else's) go to ~/.claude/claims.log
# State dir: config CCM_CLAIMS_DIR, default ~/.claude/claims.   Uses flock; without it a mkdir lock (lib/ccm_lock.sh).
set -u
eval "$(python3 "$(dirname "$(readlink -f "$0")")/../lib/ccm_conf.py" --shell 2>/dev/null)" || true
DIR="${CCM_CLAIMS_DIR:-$HOME/.claude/claims}"
LOG="$HOME/.claude/claims.log"
mkdir -p "$DIR" "$(dirname "$LOG")" 2>/dev/null

cmd="${1:-}"; key="${2:-}"
[ -n "$cmd" ] && [ -n "$key" ] || { echo "usage: claim.sh acquire|check|release <key> [--ttl <min>] [--owner <who>]" >&2; exit 2; }
case "$key" in */*|*..*) echo "claim.sh: invalid key '$key'" >&2; exit 2 ;; esac
. "$(dirname "$(readlink -f "$0")")/../lib/ccm_lock.sh"   # flock, or a mkdir lock where there is none (macOS, Git Bash)
shift 2
ttl=30; owner="$(whoami):$PPID"
while [ $# -gt 0 ]; do
    case "$1" in
        --ttl)   ttl="${2:-}"; shift 2 ;;
        --owner) owner="${2:-}"; shift 2 ;;
        *) echo "claim.sh: unknown argument $1" >&2; exit 2 ;;
    esac
done
case "$ttl" in ''|*[!0-9]*) echo "claim.sh: --ttl must be a number of minutes" >&2; exit 2 ;; esac
f="$DIR/$key.claim"
now=$(date +%s)
log(){ echo "$(date '+%Y-%m-%d %H:%M:%S') [$key] $*" >> "$LOG"; }

read_claim(){ # -> C_OWNER, C_EXPIRY (empty if missing/broken)
    C_OWNER=""; C_EXPIRY=""
    [ -f "$f" ] || return 1
    # sed, not grep -oP: BSD grep (macOS) has no -P - there every claim read as "broken" = free, and nothing held
    C_OWNER=$(sed -n 's/^owner=//p' "$f" 2>/dev/null | head -1)
    C_EXPIRY=$(sed -n 's/^expiry=\([0-9][0-9]*\).*/\1/p' "$f" 2>/dev/null | head -1)
    [ -n "$C_EXPIRY" ] || { log "broken claim file (no expiry) — treating it as free"; return 1; }
    return 0
}

ccm_lock 9 "$f.lock" 10 1 || { echo "claim.sh: could not get the meta-lock for '$key'" >&2; exit 3; }

case "$cmd" in
    acquire)
        if read_claim && [ "$now" -lt "$C_EXPIRY" ] && [ "$C_OWNER" != "$owner" ]; then
            left=$(( (C_EXPIRY - now + 59) / 60 ))
            echo "TAKEN: '$key' is held by $C_OWNER (~${left} more min)" >&2
            exit 1
        fi
        if [ -n "${C_OWNER:-}" ] && [ -n "${C_EXPIRY:-}" ] && [ "$now" -ge "$C_EXPIRY" ]; then
            log "TAKEOVER: expired claim of $C_OWNER (expired $(( (now - C_EXPIRY + 59) / 60 )) min ago) -> new owner $owner"
        fi
        printf 'owner=%s\nexpiry=%s\nttl_min=%s\nacquired=%s\n' \
            "$owner" "$((now + ttl * 60))" "$ttl" "$(date '+%Y-%m-%d %H:%M:%S')" > "$f"
        echo "OK: '$key' for $owner for ${ttl} min"
        ;;
    check)
        if read_claim && [ "$now" -lt "$C_EXPIRY" ]; then
            left=$(( (C_EXPIRY - now + 59) / 60 ))
            echo "TAKEN: '$key' is held by $C_OWNER (~${left} more min)"
            exit 1
        fi
        if [ -n "${C_EXPIRY:-}" ] && [ "$now" -ge "${C_EXPIRY:-0}" ] 2>/dev/null && [ -f "$f" ]; then
            log "check: the claim of ${C_OWNER:-?} has expired — treating it as free"
            rm -f "$f"
        fi
        echo "FREE: '$key'"
        ;;
    release)
        if read_claim && [ "$C_OWNER" != "$owner" ]; then
            log "release of SOMEONE ELSE'S claim: held by $C_OWNER, released by $owner"
        fi
        rm -f "$f"
        echo "RELEASED: '$key'"
        ;;
    *) echo "claim.sh: unknown command '$cmd'" >&2; exit 2 ;;
esac
exit 0
