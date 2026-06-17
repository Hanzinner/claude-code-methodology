#!/usr/bin/env bash
# Call a registered agent: resumes their session, asks a question, returns
# the response. The target agent sees a "[from agent: <caller>]" prefix so
# they know who is calling.
#
# Usage: call_agent.sh <name> "<prompt>"
#
# Expensive — each call is a fresh resume, which means a cache miss on the
# target's context. Use for delegated knowledge ("ask the security agent
# what they think"), not chit-chat.

set -euo pipefail

CLAUDE_DIR="${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}"
REGISTRY="$CLAUDE_DIR/agent-registry.json"

if [[ $# -ne 2 ]]; then
  echo "usage: call_agent.sh <agent-name> \"<prompt>\"" >&2
  exit 2
fi

target="$1"
prompt="$2"

if [[ ! -f "$REGISTRY" ]]; then
  echo "registry not found: $REGISTRY" >&2
  echo "register at least one agent first via /register-as <name>" >&2
  exit 1
fi

# Reverse lookup: caller name by current CLAUDE_CODE_SESSION_ID
caller=$(python3 -c "
import json, os
reg = json.load(open('$REGISTRY'))
my_sid = os.environ.get('CLAUDE_CODE_SESSION_ID','')
for name, e in reg.items():
    if e.get('sid') == my_sid:
        print(name); break
else:
    print(f'unregistered:{my_sid[:8]}' if my_sid else 'human-or-script')
")

# Lookup target sid + cwd
read -r sid cwd < <(python3 -c "
import json, sys
reg = json.load(open('$REGISTRY'))
e = reg.get('$target')
if not e:
    print('agent not registered: $target', file=sys.stderr)
    print('known:', ', '.join(reg.keys()) or '(none)', file=sys.stderr)
    sys.exit(3)
print(e['sid'], e.get('cwd', '.'))
")

full_prompt="[from agent: $caller] $prompt"

cd "$cwd"
claude -p "$full_prompt" \
  --resume "$sid" \
  --exclude-dynamic-system-prompt-sections \
  --output-format text 2>/dev/null
