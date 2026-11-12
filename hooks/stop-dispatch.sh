#!/usr/bin/env bash
# Stop dispatcher — one Stop slot, many consumers.
#
# BLOCKING branches run first, one by one: a branch that prints {"decision":"block"} stops the reply from ending
# (the agent continues), and the rest are skipped this time — they run on the next stop.
# DETECTOR branches then run IN PARALLEL with one shared deadline: each one only writes a log line and/or a flag file
# (~/.claude/<detector>-flags/<session_id>) that surface-flags.sh shows on the next prompt. Their stdout is discarded.
# Why parallel: one after another, a dozen detectors at 0.3–0.9 s each fit easily — until the machine is under load,
# each takes ~5 s, and the budget ran out on the 4th; the rest were silently skipped.
# Every branch is fail-open: a crash or timeout is logged to ~/.claude/hook-errors.log and never blocks the reply.
# A branch whose file isn't installed is skipped — add yours to the lists below.

input=$(cat)
ERRLOG="$HOME/.claude/hook-errors.log"
HOOK_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
BUDGET=${STOP_DISPATCH_BUDGET:-17}     # below hook-safe.sh's 20 s, so this script still gets to write its log
SLOW=5
t0=$(date +%s)
skipped=()

BLOCKING=(pause-guard)
DETECTORS=(proof-guard reply-guard strawman-guard abbr-guard source-guard link-guard input-guard cost-guard draft-guard)

left() { echo $(( BUDGET - ($(date +%s) - t0) )); }
log() { echo "$(date -Iseconds) stop-dispatch/$*" >> "$ERRLOG" 2>/dev/null; }

blocking() {  # blocking <name> — its stdout ({"decision":"block"}) goes to the harness
    local name="$1" f="$HOOK_DIR/$1.py" out l s rc
    [[ -f "$f" ]] || return 1
    l=$(left); (( l > 10 )) && l=10
    if (( l < 2 )); then skipped+=("$name"); return 1; fi
    s=$(date +%s)
    out=$(printf '%s' "$input" | timeout -k 1 "$l" python3 "$f" 2>>"$ERRLOG"); rc=$?
    (( rc == 124 || rc == 137 )) && log "$name did not finish in $l s — its block was not checked"
    (( $(date +%s) - s >= SLOW )) && log "$name slow: $(( $(date +%s) - s )) s"
    case "$out" in *'"decision"'*) printf '%s\n' "$out"; return 0 ;; esac
    return 1
}

finish() {
    (( ${#skipped[@]} )) && log "budget of ${BUDGET} s used up — skipped: ${skipped[*]}"
    exit 0
}

for b in "${BLOCKING[@]}"; do blocking "$b" && finish; done

l=$(left); (( l > 12 )) && l=12
if (( l < 2 )); then skipped+=("${DETECTORS[@]}"); finish; fi
tmp=$(mktemp -d) || finish
for name in "${DETECTORS[@]}"; do
    [[ -f "$HOOK_DIR/$name.py" ]] || continue
    ( s=$(date +%s); printf '%s' "$input" | timeout -k 1 "$l" python3 "$HOOK_DIR/$name.py" \
          >/dev/null 2>"$tmp/$name.err"; echo "$? $(( $(date +%s) - s ))" > "$tmp/$name.rc" ) &
done
wait
for name in "${DETECTORS[@]}"; do
    [[ -f "$tmp/$name.rc" ]] || continue
    read -r rc d < "$tmp/$name.rc"
    if [[ $rc == 124 || $rc == 137 ]]; then log "$name did not finish in $l s (parallel)"
    elif [[ $rc != 0 ]]; then log "$name failed (rc=$rc): $(tail -c 200 "$tmp/$name.err" 2>/dev/null)"
    elif (( d >= SLOW )); then log "$name slow: $d s"
    fi
done
rm -rf "$tmp"
finish
