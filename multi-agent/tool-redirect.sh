#!/usr/bin/env bash
# PreToolUse hook — a declarative "tool policy": deny one tool and, in the
# denial reason, TELL the agent which tool to use instead. The agent reads the
# permissionDecisionReason and retries with the right tool on its own — no
# briefing edits, no per-agent rules. One hook redirects the whole fleet.
#
# This example redirects WebSearch -> a Tavily MCP search (better results, and
# it doesn't burn WebSearch limits). The pattern generalizes to any tool policy:
# swap the matcher and the reason text.
#
# Wire it in settings.json:
#   "PreToolUse": [
#     { "matcher": "WebSearch",
#       "hooks": [{ "type": "command", "command": ".../tool-redirect.sh", "timeout": 5 }] }
#   ]

cat >/dev/null   # stdin not needed — the decision is unconditional

cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"WebSearch is disabled by tool policy: use the Tavily MCP instead — run the same query through mcp__tavily__tavily_search (find it via ToolSearch with the keyword 'tavily' if it isn't loaded yet). Tavily is more accurate and doesn't consume WebSearch limits. If the tavily server is genuinely unavailable in this session (headless/cron), say so honestly in your reply — do NOT look for a workaround."}}
EOF
