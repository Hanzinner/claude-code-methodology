#!/usr/bin/env bash
# memory_consolidation.sh [--force] - nightly READ-ONLY consolidation of the memory corpus.
# A fresh `claude -p` run (cheap model, tools limited to Read,Grep,Glob) reads the memory dir, the library, the
# mistakes journal and the agent briefings and writes a REPORT. It changes nothing: the md5 of the memory dir is taken
# before and after, and a difference is logged and flagged in the letter (a read-only run cannot change memory: either
# someone wrote in parallel or the tool list leaks).
# When (cron runs it hourly, this gate decides): not run today yet AND (the human has been quiet >= QUIET_MIN minutes
# in the prompt timestamps, OR yesterday was missed too - catch-up, OR it is 23:00 or later). History: a pure
# "quiet for 3 hours" condition never happened on a live machine, because every such pause was a machine that was off.
# The quota is NOT gated (a quota meter can be wrong); instead: a cheaper model and once a day.
# Output: <CCM_CONSOLIDATION_DIR>/YYYY-MM-DD.md + one letter to CCM_CONSOLIDATION_KEEPER (empty = no letter).
# Cost: one `claude -p` run per day. Cron: 20 * * * * (see tests/memory-consolidation-test.sh).
# Test overrides: CONSOLIDATION_STAMP, _TSDIR, _LOG, _RUNNER (command that replaces claude_machine.py), _DRY, _MODEL.
set -uo pipefail
export LC_ALL=C.UTF-8
HERE=$(dirname "$(readlink -f "$0")")
eval "$(python3 "$HERE/../lib/ccm_conf.py" --shell)"
MEM="${CCM_MEMORY_DIR:-$HOME/.claude/memory}"
WS="$CCM_WORKSPACE"
OUTDIR="${CCM_CONSOLIDATION_DIR:-$HOME/.claude/consolidation/reports}"
STAMP=${CONSOLIDATION_STAMP:-$HOME/.claude/consolidation/last-run}
TSDIR=${CONSOLIDATION_TSDIR:-$HOME/.claude/cache/prompt-timestamps}
QUIET_MIN=45
MODEL="${CONSOLIDATION_MODEL:-sonnet}"
LOG=${CONSOLIDATION_LOG:-$HOME/.claude/logs/memory-consolidation.log}
KEEPER="${CCM_CONSOLIDATION_KEEPER:-}"
POST="${CCM_INBOX_POST:-$HERE/inbox_post.sh}"
RUNNER="${CONSOLIDATION_RUNNER:-$HERE/claude_machine.py consolidation}"
mkdir -p "$(dirname "$STAMP")" "$OUTDIR" "$(dirname "$LOG")"
log() { echo "$(date -Iseconds) $*" >> "$LOG"; }
letter() { [[ -n "$KEEPER" ]] && "$POST" "$KEEPER" "$1" >/dev/null 2>&1; return 0; }

force=0; [[ "${1:-}" == "--force" ]] && force=1
today=$(date +%F)
why=""
if (( ! force )); then
    last=$(cat "$STAMP" 2>/dev/null)
    [[ "$last" == "$today" ]] && exit 0
    newest=$(find "$TSDIR" -maxdepth 1 -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1)
    newest=${newest%.*}; gap_min=$(( ( $(date +%s) - ${newest:-0} ) / 60 ))
    (( gap_min >= QUIET_MIN )) && why="quiet for ${gap_min} min"
    [[ -z "$why" && "$last" < "$(date -d yesterday +%F)" ]] && why="catch-up: last run ${last:-never}"
    [[ -z "$why" ]] && (( 10#$(date +%H) >= 23 )) && why="end of day"   # 10#: "08" is an octal error otherwise
    [[ -z "$why" ]] && exit 0
fi
[[ "${CONSOLIDATION_DRY:-0}" == 1 ]] && { echo "RUN: ${why:-force}"; exit 0; }
[[ -d "$MEM" ]] || { log "no memory dir ($MEM) - skipped"; exit 0; }

work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
sum() { find "$MEM" -type f -name '*.md' -print0 | sort -z | xargs -0 -r md5sum | md5sum | cut -c1-32; }
md5_before=$(sum)
"$HERE/broken_links.py" > "$work/broken_links.txt" 2>&1 || true
out="$OUTDIR/$today.md"

prompt="You are the nightly memory consolidator of an agent swarm. You ONLY READ (Read/Grep/Glob) and change nothing.
Corpus: $MEM (memory files, index MEMORY.md), $WS/LIBRARY.md, $WS/MISTAKES.md, agent briefings $CCM_AGENTS_DIR/*/briefing.md, the episodic log in $MEM/episodic/.
The output of broken_links.py is already in $work/broken_links.txt - do not recount it.
Today is $today. Do exactly these checks:
1. Contradictions of fact between memory files, the library and briefings (cite both places).
2. Stale dated claims: 'current / now / live' with a date older than 30 days in files that describe mechanisms - verify by reading only (does the file/script exist?).
3. Duplicates and overlaps: two memory files about the same thing -> propose a merge (do NOT merge).
4. Broken links: summarise broken_links.txt.
5. MISTAKES: new entries without a class from the index -> propose a class; recount the index totals.
6. Episodic log: a fact repeated on 3+ days without a memory file -> a candidate.
Report format (markdown, short; the keeper reads it in the morning):
## 1. Contradictions  ## 2. Stale dated claims  ## 3. Duplicates  ## 4. Broken links  ## 5. MISTAKES  ## 6. Episodic -> memory candidates
## Mechanical (the keeper can fix alone) / Needs the human (one line, A/B) - the second only for taste, intent, priority; counters, classes, format are mechanical.
Every item needs evidence (file:line or a quote). No evidence - do not write it."

# one run at a time: a manual --force and cron would write the same $out.tmp
exec 8>"$(dirname "$STAMP")/run.lock"
flock -n 8 || { log "another run is in progress - skipped"; exit 0; }
log "start (model $MODEL, force=$force${why:+, $why})"
{
    echo "# Memory consolidation - $today - model $MODEL"
    echo "> Read-only. Script: scripts/memory_consolidation.sh."
    echo
    # shellcheck disable=SC2086
    timeout 1800 $RUNNER -p "$prompt" </dev/null --model "$MODEL" --tools "Read,Grep,Glob" --output-format text
    echo "$?" > "$work/rc"
} > "$out.tmp" 2>&1
rc=$(cat "$work/rc" 2>/dev/null || echo 99)
(( rc == 0 )) || echo "WARNING: claude -p failed (rc=$rc) - the report is INCOMPLETE." >> "$out.tmp"
mv "$out.tmp" "$out"

md5_after=$(sum)
warn=""
if [[ "$md5_before" != "$md5_after" ]]; then
    log "WARNING: memory md5 changed during the run ($md5_before -> $md5_after)"
    warn=" WARNING: the memory dir changed during the run - check whether it was parallel work by agents, not the consolidator."
fi
lines=$(grep -c . "$out")
# a failed run is NOT done: no stamp (tomorrow catches up), and the letter says so plainly
if (( rc != 0 )); then
    letter "- [ ] [$today] Nightly memory consolidation FAILED (claude -p rc=$rc: quota/timeout/network) - partial report: $out. The next attempt is automatic."
    log "FAILED: claude -p rc=$rc - stamp not written"
    exit 1
fi
echo "$today" > "$STAMP"
letter "- [ ] [$today] Nightly memory consolidation - report: $out ($lines lines, model $MODEL, read-only; memory md5 before/after: $([[ -z $warn ]] && echo unchanged || echo CHANGED)).$warn"
log "done: $out ($lines lines), md5 ${warn:+CHANGED}${warn:-unchanged}"
