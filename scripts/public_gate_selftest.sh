#!/usr/bin/env bash
# public_gate_selftest.sh - once a day cron runs the public gate's self-test matrix; the supervisor reads the result.
# Modes: (no arguments) run `public_gate.sh --selftest`, append a line to the log;
#        --check - verdict for the supervisor (rc 0 green | 1 red or stale | 3 no data).
# Why: a gate that is used rarely can break silently and be found broken at the moment of publishing. The run is
# started with a CLEAN environment on purpose (cron has none; an earlier gate broke exactly under that condition).
# Settings: GATE (default <dir>/public_gate.sh), LOG (default ~/.claude/logs/public-gate-selftest.log), MAX_H (26).
# Cron: 25 5 * * *
HERE=$(dirname "$(readlink -f "$0")")
GATE=${GATE:-$HERE/public_gate.sh}
LOG=${LOG:-$HOME/.claude/logs/public-gate-selftest.log}; MAX_H=${MAX_H:-26}
if [[ "${1:-}" == "--check" ]]; then
  last=$(grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:]+ rc=' "$LOG" 2>/dev/null | tail -1)
  [[ -n "$last" ]] || { echo "no run in $LOG"; exit 3; }
  age_h=$(( ( $(date +%s) - $(date -d "${last:0:19}" +%s) ) / 3600 ))
  echo "last selftest ${age_h} h ago: ${last#* * }"
  (( age_h <= MAX_H )) || { echo "run is stale (limit ${MAX_H} h) - cron not running?"; exit 1; }
  [[ "$last" == *" rc=0 "* ]]
  exit
fi
mkdir -p "$(dirname "$LOG")"
out=$(env -i PATH=/usr/local/bin:/usr/bin:/bin HOME="$HOME" bash "$GATE" --selftest 2>&1); rc=$?
fails=$(grep -c 'BAD' <<<"$out")
echo "$(date '+%F %T') rc=$rc $(tail -1 <<<"$out") (failed cases: $fails)" >> "$LOG"
(( rc == 0 )) || grep 'BAD' <<<"$out" | sed 's/^/    /' >> "$LOG"
exit $rc
