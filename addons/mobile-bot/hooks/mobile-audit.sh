#!/usr/bin/env bash
# PostToolUse hook — when the agent runs under the mobile bot, log every
# Write/Edit to a JSONL audit log and (optionally) git-commit the change
# so it can be reverted.
#
# Outside the mobile bot context, this hook is a no-op.

set -euo pipefail

[[ "${CLAUDE_MOBILE_BOT:-}" == "1" ]] || exit 0

LOG="${MOBILE_BOT_AUDIT_LOG:-/var/log/claude-mobile-bot-audit.jsonl}"
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
touch "$LOG" 2>/dev/null || { echo "audit log not writable: $LOG" >&2; exit 0; }

input=$(cat)
tool=$(printf '%s' "$input" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_name',''))")
case "$tool" in Write|Edit) ;; *) exit 0 ;; esac

target=$(printf '%s' "$input" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))")
[[ -n "$target" ]] || exit 0

# Append audit line
python3 -c "
import json, sys, os, time
entry = {
    'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    'tool': '$tool',
    'file': '$target',
    'session': os.environ.get('CLAUDE_CODE_SESSION_ID', ''),
}
with open('$LOG', 'a') as f:
    f.write(json.dumps(entry) + '\n')
"

# If target is inside a git repo, auto-commit for easy revert
if target_dir=$(dirname "$target"); cd "$target_dir" 2>/dev/null && git rev-parse --git-dir >/dev/null 2>&1; then
  if ! git diff-index --quiet HEAD -- "$target" 2>/dev/null; then
    git add "$target" 2>/dev/null && \
      git commit -m "mobile-bot: $(basename "$target")" --quiet 2>/dev/null || true
  fi
fi

exit 0
