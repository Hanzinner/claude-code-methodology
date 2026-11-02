#!/usr/bin/env bash
# PreToolUse hook of the mobile bot: a thin FAIL-CLOSED wrapper around mobile_restrict.py,
# where the rules live. A gate that crashes or can't start must refuse, not allow: any
# non-zero exit from it becomes a block (exit 2). Outside the bot it is a no-op.
[[ "${CLAUDE_MOBILE_BOT:-}" == "1" ]] || exit 0
python3 "$(dirname "$(realpath "$0")")/mobile_restrict.py" && exit 0
echo "BLOCKED by mobile-bot: the gate refused this call or could not run" >&2
exit 2
