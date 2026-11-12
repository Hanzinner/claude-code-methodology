#!/usr/bin/env bash
# UserPromptSubmit — work-order detector. Failure it answers: "wrote the methodology, never set up CI" — an order
# for work dissolved into the conversation and nobody put it in the queue.
# ONLY coordinator sessions: the agent identity (~/.claude/agent-identity/<session_id>, written by the identity
# watchman) must match CCM_COORDINATOR_PATTERN. A prompt from the human with an imperative order for an
# artifact ("set up CI", "add a retry to the uploader") → inject "FIRST action: a line in the queue".
# Noise control: the imperative must open the sentence (after "please", "now", "I want you to", …) and the sentence
# must not be a question (no "?"). Log: ~/.claude/order-hits.log
# Config: CCM_COORDINATOR_PATTERN — NEW key, default "HQ|Coordinator|Orchestrator"; "*" = every session, even without
# an identity file. CCM_LANG_EXTRA ("uk" adds the Ukrainian verbs). Set it in methodology.conf or the environment.
input=$(cat)
sid=$(printf '%s' "$input" | grep -oP '"session_id"\s*:\s*"\K[^"]+' | head -1)
[ -n "$sid" ] || exit 0
eval "$(python3 "$(dirname "$(readlink -f "$0")")/../lib/ccm_conf.py" --shell)"
LIB="$(dirname "$(readlink -f "$0")")/../lib"
pattern="${CCM_COORDINATOR_PATTERN:-}"
[ -n "$pattern" ] || pattern=$(python3 - "$LIB" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import ccm_conf
f = ccm_conf.conf_file()
print((ccm_conf._parse(f).get("CCM_COORDINATOR_PATTERN") if f else "") or "HQ|Coordinator|Orchestrator")
PY
)
ident=""
[ -f "$HOME/.claude/agent-identity/$sid" ] && ident=$(cat "$HOME/.claude/agent-identity/$sid")
if [ "$pattern" != "*" ]; then
    printf '%s' "$ident" | grep -qE "$pattern" || exit 0
fi
export HOOK_INPUT="$input" CCM_LANG_EXTRA
hit=$(python3 - <<'PY'
import json, os, re
d = json.loads(os.environ["HOOK_INPUT"])
p = d.get("prompt", "") or ""
EN = (r"^\s*(?:(?:please|ok|okay|also|and|now|then|so|next|first|let's|let us|go ahead and|i want you to|i need you to|we need to|you need to|you should|we should)[,\s]+)*"
      r"(?:set up|setup|make(?! sure| sense| a note)|create|build|add|implement|deploy|configure|fix|refactor|write|introduce|wire up|ship|roll out|rework|rebuild|install|enable|migrate)\b\s+\S+")
UK = (r"\b(зроби|введи|заведи|розгорни|постав|збудуй|налаштуй|запили|додай|давай зробимо|перероби|полагодь|виправ)\b\s+\S+"
      if "uk" in os.environ.get("CCM_LANG_EXTRA", "") else None)
for sent in re.split(r"[.!\n]", p):
    if "?" in sent:
        continue
    if re.search(EN, sent, re.I) or (UK and re.search(UK, sent, re.I)):
        print("HIT"); break
PY
)
[ "$hit" = "HIT" ] || exit 0
mkdir -p "$HOME/.claude"
echo "$(date '+%F %T') [$sid] order-hint" >> "$HOME/.claude/order-hits.log"
echo "📌 [order?] This looks like an order for WORK. FIRST action: a line in the queue (roadmap / the agent's TODO / the executor's inbox), THEN the answer. An order without a line dissolves at the next context compaction."
exit 0
