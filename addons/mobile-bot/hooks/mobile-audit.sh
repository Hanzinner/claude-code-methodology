#!/usr/bin/env bash
# PostToolUse hook — when the agent runs under the mobile bot, log every
# Write/Edit to a JSONL audit log and (optionally) git-commit the change
# so it can be reverted.
#
# Outside the mobile bot context, this hook is a no-op.

set -euo pipefail

[[ "${CLAUDE_MOBILE_BOT:-}" == "1" ]] || exit 0

LOG="${MOBILE_BOT_AUDIT_LOG:-$HOME/.claude/mobile-bot-audit.jsonl}"   # same default as bot.py

input=$(cat)
tool=$(printf '%s' "$input" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_name',''))")
case "$tool" in Write|Edit) ;; *) exit 0 ;; esac

target=$(printf '%s' "$input" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))")
[[ -n "$target" ]] || exit 0

# Append audit line. Values go in through the environment, never spliced into the
# code: a file name with an apostrophe would otherwise break (or inject into) it.
# An unwritable log is reported but does NOT skip the commit below — the commit is
# what makes /revert possible.
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
AUDIT_TOOL="$tool" AUDIT_FILE="$target" AUDIT_LOG="$LOG" python3 -c "
import json, os, time
entry = {
    'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    'tool': os.environ['AUDIT_TOOL'],
    'file': os.environ['AUDIT_FILE'],
    'session': os.environ.get('CLAUDE_CODE_SESSION_ID', ''),
}
with open(os.environ['AUDIT_LOG'], 'a') as f:
    f.write(json.dumps(entry) + '\\n')
" 2>/dev/null || echo "audit log not writable: $LOG" >&2

# If target is inside a git repo, auto-commit for easy revert
if target_dir=$(dirname "$target"); cd "$target_dir" 2>/dev/null && git rev-parse --git-dir >/dev/null 2>&1; then
  # status, not diff-index: diff-index is blind to a NEW (untracked) file, so Write of a
  # new file was never committed and /revert had nothing to undo.
  if [[ -n "$(git status --porcelain -- "$target" 2>/dev/null)" ]]; then
    git add "$target" 2>/dev/null && \
      git commit -m "mobile-bot: $(basename "$target")" --quiet 2>/dev/null || true
  fi
fi

exit 0
