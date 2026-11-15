#!/usr/bin/env bash
# PreCompact hook — NOT a reminder to the agent. This hook's stdout is returned
# as newCustomInstructions and appended to the TAIL of the compaction prompt
# ("Additional Instructions:", the most influential position) — i.e. it speaks to
# the process that decides what survives compaction. The default compaction is
# lossy by design; this steers it to keep the load-bearing specifics verbatim.
#
# Fail-open: any failure → empty stdout → standard compaction. Pair with
# postcompact-archive.sh, which files each summary after the fact.
# The summary also ends with a fixed-heading section of the agent's own mistakes in that segment — including the ones
# nobody noticed. The archived summaries (~/.claude/compaction-log/) are then one grep away for whoever reviews the
# mistakes journal: a mistake that happens three times is a hole in the construction, and you only see the three if
# they are written down somewhere other than a chat that is about to be compacted.

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

REQUIRED, as a separate section at the end of the summary, with exactly this heading (a script may read it — don't change it):
## Agent mistakes in this segment
One item per mistake of the AGENT in this segment — including ones the human didn't notice or mention
(a false "done", something broken, a duplicate, an unneeded action, a wrong conclusion, a forgotten task):
- what happened (fact) · root cause (the mechanism) · can it be mechanized (hook/gate/test/no — which) · written to the mistakes journal (yes/no)
Don't list the human's corrections as such — only the agent's mistakes. No mistakes — one line: none
EOF
exit 0
