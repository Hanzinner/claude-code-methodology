#!/usr/bin/env bash
# PreCompact hook — NOT a reminder to the agent. This hook's stdout is returned
# as newCustomInstructions and appended to the TAIL of the compaction prompt
# ("Additional Instructions:", the most influential position) — i.e. it speaks to
# the process that decides what survives compaction. The default compaction is
# lossy by design; this steers it to keep the load-bearing specifics verbatim.
#
# Fail-open: any failure → empty stdout → standard compaction. Pair with
# postcompact-archive.sh, which files each summary after the fact.

input=$(cat 2>/dev/null || true)
trigger=$(printf '%s' "$input" | python3 -c "import json,sys
try: print(json.load(sys.stdin).get('trigger','auto'))
except Exception: print('auto')" 2>/dev/null || echo auto)

cat <<EOF
Preserve VERBATIM, do not paraphrase (quote, don't summarize):
- all numbers, file paths, versions, script/service/branch names, session ids / shas;
- verification results as "command → output → conclusion" (evidence, not the claim "verified");
- open tasks and their status (including what is WAITING on a human decision and why);
- verbatim wording of any rules/instructions the user gave this session;
- root causes of bugs found (the causal mechanism, not just the symptom and fix).
Compaction trigger: $trigger. If an analytical conclusion isn't yet written to a file, keep it in full.
EOF
exit 0
