# Writing hooks

## What hooks are

Commands (shell or Python scripts) the Claude Code harness executes at lifecycle events. Use them to enforce behavior the agent can't be trusted to remember consistently.

Memory triggers are reactive (agent reads them only if it knows to look). Hooks are non-reactive (always fire).

## Lifecycle events

Every hook gets the common fields on stdin (`session_id`, `transcript_path`, `cwd`, `hook_event_name`, …) plus the event's own. The ones this repo uses:

| Event | Extra payload | Typical use (here) |
|-------|---------------|-------------|
| `SessionStart` | how the session started | Inject context, run periodic checks (memory health) |
| `UserPromptSubmit` | `prompt` | Annotate the user message (time gap), surface flags left by other hooks |
| `PreToolUse` | `tool_name`, `tool_input` | Block or redirect a tool call (PDF → extract first); inject lessons before an edit |
| `PostToolUse` | `tool_name`, `tool_input`, the tool's result | Log, audit, count (stuck-detector resets on success) |
| `PostToolUseFailure` | `tool_name`, `tool_input`, `error` | Count consecutive failures (stuck-detector) |
| `PreCompact` / `PostCompact` | `trigger`, … | Steer what compaction keeps; archive the summary |
| `PermissionDenied` | `tool_name`, … | Tell the agent to stop hopping channels |
| `Stop` | `last_assistant_message`, … | Check the finished reply (reply-guard, proof-guard) |

There are more events (`SessionEnd`, `SubagentStop`, `Notification`, …) — see the [hooks reference](https://code.claude.com/docs/en/hooks).

## Exit codes and output

| Code | Behavior |
|------|----------|
| `0` | Success. Stdout that is JSON is parsed (decisions, `additionalContext`); plain stdout reaches the model only for `UserPromptSubmit` and `SessionStart`. |
| `2` | Block, where the event can block. For `PreToolUse` the call is denied and stderr goes to the model. What exit 2 does depends on the event: on `UserPromptSubmit` it drops the prompt; on `PostToolUse` the tool has already run. |
| other non-zero | Non-blocking error. The action proceeds; the transcript shows the first stderr line; the model is not told. A crashing hook fails silently from the agent's point of view — hence `hook-safe.sh` and its error log. |

Prefer JSON on stdout over exit codes: `permissionDecision: "deny"` with a reason (PreToolUse), `additionalContext` to add text to the model's context. The hooks in this repo do that.

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

Matchers: tool name (`Read`, `Write`, `Edit`, `Bash`), MCP tool (`mcp__name__tool`), or `*`. All matching hooks run **in parallel** — don't rely on order between them. Need an order, or several consumers on one event? Use one dispatcher script (see `hooks/stop-dispatch.sh`).

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
