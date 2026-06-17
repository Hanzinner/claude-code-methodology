# Hooks guide

Hooks are how you make the Claude Code harness enforce behavior the agent can't be trusted to remember.

## When to write a hook

If you've ever written a memory entry that starts with **"Always remember to..."** or **"Never do..."** — that's a hook in disguise. Memory triggers are reactive (the agent reads them only if it knows to look). Hooks are non-reactive (they fire whether the agent remembers or not).

A few canonical hook-shaped problems:

| Problem | Hook lifecycle |
|---------|----------------|
| "PDF reads should go through extraction first" | PreToolUse on Read |
| "After every code edit, run the linter" | PostToolUse on Edit/Write |
| "When the agent starts, tell it what time it is" | SessionStart |
| "Each user prompt should include time-since-last-message" | UserPromptSubmit |
| "Some commands should require explicit confirmation even in sandbox" | PreToolUse on Bash with pattern matching |
| "Log every change for an audit trail" | PostToolUse on Edit/Write |

If the rule is **conditional on agent judgment** ("be brief when the user is in a hurry"), that's a `CLAUDE.md` rule, not a hook. Hooks enforce things that are unconditional or have machine-checkable conditions.

## Anatomy of a hook

A hook is a script that:
1. Reads JSON from stdin (Claude Code tells you what's happening)
2. Optionally writes JSON to stdout (to modify the harness behavior)
3. Optionally writes text to stderr (the agent sees this)
4. Returns an exit code that tells the harness what to do

```bash
#!/usr/bin/env bash
# Read the hook input
input=$(cat)

# Parse it (Python is easier than jq for nested fields)
tool=$(echo "$input" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_name',''))")

# Decide what to do
if [[ "$tool" == "Write" && "$some_condition" ]]; then
    echo "stop and ask the user first" >&2
    exit 2
fi

# Otherwise let it through
exit 0
```

## The input JSON

The harness passes structured data on stdin. Shape depends on the lifecycle event:

**PreToolUse / PostToolUse:**
```json
{
  "tool_name": "Read",
  "tool_input": { "file_path": "/path/to/file" },
  "session_id": "..."
}
```

**UserPromptSubmit:**
```json
{
  "prompt": "the user's message",
  "session_id": "..."
}
```

**SessionStart:**
```json
{
  "session_id": "..."
}
```

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Pass through. Tool call proceeds normally. |
| `2` | Block the tool call. The stderr text is shown to the agent — use this to redirect ("read the .txt instead") or instruct ("ask the user first"). |
| other non-zero | Treated as an error; surfaced to the agent. |

For `SessionStart` and `UserPromptSubmit`, the typical pattern is:
- exit 0 with stdout text → prepended to the agent's context
- or exit 0 with a JSON envelope on stdout for more structured injection

## Wiring it up

In `settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [{ "type": "command", "command": "/path/to/your-hook.sh" }]
      }
    ]
  }
}
```

Matchers can be specific tools (`Read`, `Bash`, `Edit`, `Write`), MCP tools (`mcp__name__tool`), or `*` for all.

Multiple hooks on the same matcher run in order.

## Anti-patterns

- **Chatty hooks.** A hook that always prints "FYI: hook fired" pollutes the agent's context with noise. Hooks should be silent on the happy path.
- **Slow hooks.** Hooks run synchronously in the request path. A hook that takes 3 seconds adds 3 seconds to every tool call. Cache, throttle, or background heavy work.
- **Hooks that hide errors.** If your hook fails, fail loudly (exit non-zero with a clear message). A hook that silently lets bad state through is worse than no hook.
- **Hooks duplicating CLAUDE.md.** If the rule depends on context the agent has to evaluate, it's not a hook — it's a rule.

## Debugging

Hooks run silently. To watch what's happening, add a log line:

```bash
echo "$(date): $(jq -r .tool_name <<<"$input") on $(jq -r .tool_input.file_path <<<"$input")" \
  >> /tmp/hook-debug.log
```

Or simulate the hook from the terminal:

```bash
echo '{"tool_name":"Read","tool_input":{"file_path":"/tmp/test.pdf"}}' | ./hooks/auto-extract-docs.sh
```

The hook should behave the same when run manually as when fired by the harness — there's no extra context.

## Examples in this repo

- [`hooks/auto-extract-docs.sh`](../hooks/auto-extract-docs.sh) — PreToolUse on Read, intercepts PDF/HTML and redirects to extracted text
- [`hooks/check-prompt-gap.sh`](../hooks/check-prompt-gap.sh) — UserPromptSubmit, prepends `[now: ... | gap since previous: ...]`
- [`hooks/memory-curation-check.sh`](../hooks/memory-curation-check.sh) — SessionStart, runs a weekly memory health check and injects findings

These three are the load-bearing hooks. Add more as you find patterns the agent repeatedly drifts on.
