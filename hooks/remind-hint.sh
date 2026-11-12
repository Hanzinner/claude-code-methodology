#!/usr/bin/env bash
# UserPromptSubmit: the human asks to be reminded ("remind me in an hour...", "set a reminder for 18:30") -> a hint to the
# agent on HOW that is done: scripts/remind.py puts a letter into its inbox at the time. Without the hint the agent
# answers "I'll remind you" — and has no mechanism for it (a promise without a mechanism). Every session; the agent
# name comes from the session's identity (~/.claude/agent-identity/<sid>, written by briefing-watchman).
# English phrases always; Ukrainian ones when CCM_LANG_EXTRA contains "uk". Fail-open, silent when nothing matches.
eval "$(python3 "$(dirname "$(readlink -f "$0")")/../lib/ccm_conf.py" --shell 2>/dev/null)" || true
input=$(cat)
sid=$(printf '%s' "$input" | grep -oP '"session_id"\s*:\s*"\K[^"]+' | head -n1 || true)
export HOOK_INPUT="$input" CCM_LANG_EXTRA="${CCM_LANG_EXTRA:-}"
python3 - <<'PY' || exit 0
import json, os, re, sys
try: p = json.loads(os.environ["HOOK_INPUT"]).get("prompt", "") or ""
except ValueError: sys.exit(1)
pats = [r"\bremind me\b", r"\bremind (?:us|him|her|them|the agent)\b", r"\bset (?:me |us )?(?:a |an |the )?(?:reminder|timer)\b",
        r"\b(?:add|create|make|put) (?:me )?(?:a |an )?reminder\b", r"\breminders? (?:for|at|in|on)\b", r"\bping me (?:at|in|on|tomorrow)\b"]
if "uk" in os.environ.get("CCM_LANG_EXTRA", ""):
    pats.append(r"(?<!\w)(?:нагадай|нагадаєш|нагадати мені|нагадуй|постав\w*\s+(?:собі\s+)?нагадування|нагадування (?:на|через|о))(?!\w)")
sys.exit(0 if re.search("|".join(pats), p, re.I) else 1)
PY
ident=""
[ -n "$sid" ] && [ -f "$HOME/.claude/agent-identity/$sid" ] && ident=$(basename "$(cat "$HOME/.claude/agent-identity/$sid")")
[ -n "$ident" ] || ident="<your-agent-name>"
who="${CCM_HUMAN_NAME:-the user}"
dir="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
echo "⏰ [reminder] $who asks to be reminded. The mechanism: \`$dir/scripts/remind.py $ident <when> \"<what exactly, with context — you may not remember it later>\"\` — <when>: 15m · 2h · 3d · 18:30 · \"2026-10-09 10:00\". At that time a letter lands in your inbox. Don't say \"I'll remind you\" without running this command; in your reply give the time it printed. List: remind.py --list."
exit 0
