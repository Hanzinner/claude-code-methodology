#!/usr/bin/env bash
# SessionStart hook — at most once a week, two memory checks; silent when both are clean. On findings, injects one
# report into the session context so the agent can act on it:
#   1. scripts/curate_memory.py — duplicates, stale facts, broken links;
#   2. decay sweep — memory files whose frontmatter says `verified: inferred` or `verified: unverified` and that haven't
#      changed for 30 days: "re-check or delete". A guess written down once must not harden into a source of truth
#      just by sitting there (the counterpart of memory-write-gate, which makes the writer say how sure it is).
#
# Config: MEMORY_DECAY_DAYS (default 30); CLAUDE_MEMORY_DIR (default <claude dir>/memory, as in memory-write-gate).

set -euo pipefail

CLAUDE_DIR="${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}"
STAMP_DIR="$CLAUDE_DIR/cache"
STAMP="$STAMP_DIR/memory_curation_last"
SCRIPT="$CLAUDE_DIR/scripts/curate_memory.py"
MEM="${CLAUDE_MEMORY_DIR:-$CLAUDE_DIR/memory}"
INTERVAL_SECS=$((7 * 24 * 60 * 60))  # 7 days

mkdir -p "$STAMP_DIR"

now=$(date +%s)
if [[ -f "$STAMP" ]]; then
    last=$(cat "$STAMP" 2>/dev/null || echo 0)
    [[ "$last" =~ ^[0-9]+$ ]] || last=0
    (( now - last < INTERVAL_SECS )) && exit 0
fi

report=""
if [[ -f "$SCRIPT" ]]; then
    set +e
    output=$(CLAUDE_MEMORY_DIR="$MEM" python3 "$SCRIPT" 2>&1)
    exit_code=$?
    set -e
    if (( exit_code != 0 )); then report="$output"; fi
fi

decay=$(MEM="$MEM" python3 - <<'PYEOF' 2>/dev/null || true
import os, re, time
mem, days = os.environ["MEM"], int(os.environ.get("MEMORY_DECAY_DAYS") or 30)
old = []
for root, dirs, files in os.walk(mem):
    dirs[:] = [d for d in dirs if d not in ("episodic", "archive")]
    for f in files:
        if not f.endswith(".md") or f in ("MEMORY.md", "feedback-index.md"):
            continue
        p = os.path.join(root, f)
        try:
            head = open(p, encoding="utf-8").read(2000)
        except OSError:
            continue
        if re.search(r"^\s*verified:\s*['\"]?(inferred|unverified)\b", head, re.M) and \
                time.time() - os.path.getmtime(p) > days * 86400:
            old.append(os.path.relpath(p, mem))
if old:
    print(f"Memory decay: {len(old)} unverified (inferred/unverified) file(s) unchanged for over {days} days — "
          "re-check each against its source and set verified: yes, or delete it:")
    for f in sorted(old)[:10]:
        print("  -", f)
PYEOF
)

echo "$now" > "$STAMP"

[[ -z "$report$decay" ]] && exit 0

context="[memory-curation] Weekly check found signals — review and clean up."
[[ -n "$report" ]] && context+=$'\n\n'"$report"
[[ -n "$decay" ]] && context+=$'\n\n'"$decay"

python3 -c '
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.stdin.read()}}))
' <<< "$context"
