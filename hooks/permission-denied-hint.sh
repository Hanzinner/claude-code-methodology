#!/usr/bin/env bash
# PermissionDenied hook — two jobs in one shot:
#  A) a stop-signal against channel-hopping after a block. A denial means your
#     model of what's allowed is wrong; the reflex to try adjacent channels /
#     workarounds usually makes it worse. Stop, rethink, or ask.
#  B) a capture trigger: the moment of a denial is a high-probability point for
#     valuable feedback (a correction often immediately follows a refusal), so
#     nudge the agent to save it if the next human turn corrects the behavior.
#
# Contract: stdin carries tool_name/tool_input/reason; the reply goes in
# hookSpecificOutput.additionalContext. Run it under hook-safe.sh (fail-open).

input=$(cat)
tool=$(printf '%s' "$input" | python3 -c "import json,sys
try: print(json.load(sys.stdin).get('tool_name','the tool'))
except Exception: print('the tool')" 2>/dev/null || echo "the tool")

python3 - "$tool" <<'EOF'
import json, sys
tool = sys.argv[1]
ctx = (f"You were just denied on {tool}. That's a signal your model of what's allowed is "
       "WRONG — don't hunt for workarounds or adjacent channels. Stop, rethink, or ask.\n"
       "📝 A denial often precedes a rule: if the next human turn corrects your behavior, "
       "that's a candidate for feedback-memory — save it.")
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionDenied",
                                         "additionalContext": ctx}}, ensure_ascii=False))
EOF
