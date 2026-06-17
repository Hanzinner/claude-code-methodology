# Writing hooks

## What hooks are

Shell scripts the Claude Code harness executes at lifecycle events. Use them to enforce behavior the agent can't be trusted to remember consistently.

Memory triggers are reactive (agent reads them only if it knows to look). Hooks are non-reactive (always fire).

## Lifecycle events

| Event | Stdin payload | Typical use |
|-------|---------------|-------------|
| `SessionStart` | `{session_id}` | Inject context, run periodic checks |
| `UserPromptSubmit` | `{prompt, session_id}` | Modify or annotate the user message |
| `PreToolUse` | `{tool_name, tool_input, session_id}` | Block or redirect a tool call |
| `PostToolUse` | `{tool_name, tool_input, tool_response, session_id}` | Log, audit, post-process |

## Exit codes

| Code | Behavior |
|------|----------|
| `0` | Pass through. Tool proceeds. |
| `2` | Block. Stderr text is shown to the agent. |
| other non-zero | Error, surfaced to the agent. |

For `SessionStart` and `UserPromptSubmit`, stdout text is prepended to the agent's context.

## Minimal hook

```bash
#!/usr/bin/env bash
set -euo pipefail

input=$(cat)
tool=$(echo "$input" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_name',''))")

[[ "$tool" == "Write" ]] || exit 0

target=$(echo "$input" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))")

if [[ "$target" == *.lock ]]; then
    echo "BLOCKED: don't write .lock files" >&2
    exit 2
fi

exit 0
```

## Wiring

`settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [{ "type": "command", "command": "/abs/path/your-hook.sh" }]
      }
    ]
  }
}
```

Matchers: tool name (`Read`, `Write`, `Edit`, `Bash`), MCP tool (`mcp__name__tool`), or `*`. Multiple hooks on the same matcher run in order.

## Debugging

Simulate a hook:

```bash
echo '{"tool_name":"Read","tool_input":{"file_path":"/tmp/test.pdf"}}' | ./hooks/auto-extract-docs.sh
echo "exit: $?"
```

Or log:

```bash
echo "$(date): fired on $target" >> /tmp/hook-debug.log
```

## Constraints

- Hooks run synchronously in the request path. Slow hooks slow every tool call.
- Hooks should be silent on the happy path. Chatty hooks pollute the agent's context.
- If a rule depends on agent judgment, it's not a hook — it's a rule in `CLAUDE.md`.

## Examples in this repo

- `hooks/auto-extract-docs.sh` — PreToolUse on `Read`, intercepts PDF/HTML, redirects to extracted text
- `hooks/check-prompt-gap.sh` — UserPromptSubmit, prepends `[now: <ts> | gap: <since-last>]`
- `hooks/memory-curation-check.sh` — SessionStart, weekly memory health check
- `addons/mobile-bot/hooks/mobile-restrict.sh` — PreToolUse Write/Edit allowlist (mobile-only)
- `addons/mobile-bot/hooks/mobile-audit.sh` — PostToolUse audit log + git commit (mobile-only)
