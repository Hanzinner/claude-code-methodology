#!/usr/bin/env bash
# PreToolUse hook — when the agent runs under the mobile bot (env var
# CLAUDE_MOBILE_BOT=1 set by bot.py), restrict Write/Edit to a configured
# allowlist of paths. Outside the bot context, this hook is a no-op.
#
# Configure CLAUDE_MOBILE_BOT_ALLOW_PATHS in .env as a colon-separated list,
# e.g.  /home/you/notes:/home/you/scratch

set -euo pipefail

# No-op outside the mobile bot context
[[ "${CLAUDE_MOBILE_BOT:-}" == "1" ]] || exit 0

input=$(cat)
tool=$(printf '%s' "$input" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_name',''))")
case "$tool" in Write|Edit) ;; *) exit 0 ;; esac

target=$(printf '%s' "$input" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))")
[[ -n "$target" ]] || exit 0

# Resolve to absolute path
target_abs=$(realpath -m "$target")

# Hard blocks regardless of allowlist
for blocked in /etc /root /home/*/.ssh /home/*/.gnupg; do
  if [[ "$target_abs" == "$blocked"* ]]; then
    echo "BLOCKED by mobile-bot: writes to $blocked are not allowed from mobile" >&2
    exit 2
  fi
done
case "$(basename "$target_abs")" in
  .env|.env.*|credentials*|*.key|*.pem)
    echo "BLOCKED by mobile-bot: secret-shaped file ($(basename "$target_abs"))" >&2
    exit 2 ;;
esac

# Allowlist check
IFS=':' read -ra ALLOW <<< "${CLAUDE_MOBILE_BOT_ALLOW_PATHS:-}"
for prefix in "${ALLOW[@]}"; do
  [[ -z "$prefix" ]] && continue
  prefix_abs=$(realpath -m "$prefix")
  if [[ "$target_abs" == "$prefix_abs"/* || "$target_abs" == "$prefix_abs" ]]; then
    exit 0
  fi
done

echo "BLOCKED by mobile-bot: $target_abs is outside CLAUDE_MOBILE_BOT_ALLOW_PATHS" >&2
echo "Allowed: ${CLAUDE_MOBILE_BOT_ALLOW_PATHS:-(none)}" >&2
exit 2
