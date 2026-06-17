# Hooks

Hooks are shell commands the Claude Code harness executes at specific lifecycle points. They are the **architectural** enforcement layer: anything you can't trust the agent to remember consistently belongs here.

All hooks resolve their install location via `$CLAUDE_METHODOLOGY_DIR` (set by `install.sh` in `settings.json`), falling back to `~/.claude`.

| Hook | Lifecycle event | What it does |
|------|-----------------|--------------|
| `auto-extract-docs.sh` | PreToolUse on `Read` | Intercepts Read calls on `.pdf` / `.html` files. Auto-runs the extraction script if needed, blocks the Read, and redirects the agent to the `.txt` output. PDFs >10 MB get a "run manually" message instead of auto-extraction. |
| `check-prompt-gap.sh` | UserPromptSubmit | Prepends `[now: <timestamp> | gap since previous: ...]` to every user message. Lets the agent reason about temporal context (immediate follow-up vs. days later). |
| `memory-curation-check.sh` | SessionStart | Runs `scripts/curate_memory.py` at most weekly. Silent if memory is clean; injects a findings report into session context if issues are detected. |

## Adding your own

A hook is just a script that reads JSON from stdin and writes JSON to stdout (or text to stderr). See [Claude Code hook docs](https://docs.anthropic.com/claude-code/hooks).

To wire a new hook in, edit `settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "/path/to/your-hook.sh" }]
      }
    ]
  }
}
```

Matchers: `Read`, `Write`, `Edit`, `Bash`, `WebSearch`, etc. — or `*` for all tools.

## Hook exit codes

- `0` — pass through, tool call proceeds normally
- `2` — block the tool call; stderr is shown to the agent (use this to redirect or instruct)
- other non-zero — error, surfaced to the agent

## Debug

Hooks run silently. To see what a hook is doing:

```bash
echo '{"tool_name":"Read","tool_input":{"file_path":"/tmp/test.pdf"}}' | ./hooks/auto-extract-docs.sh
```

Or add logging inside the hook:

```bash
echo "$(date): hook fired on $file_path" >> /tmp/hook-debug.log
```
