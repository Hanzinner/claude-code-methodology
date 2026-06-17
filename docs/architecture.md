# Architecture

## Layers

```
CLAUDE.md         Behavioral rules loaded into every conversation.
hooks/            Shell scripts run by the harness at lifecycle events.
scripts/          Utilities called from hooks, skills, or directly.
skills/           Slash commands (/recap, /audit).
memory/           Per-topic markdown files + MEMORY.md trigger index.
mcp/              MCP server config (Tavily, etc).
addons/           Optional extensions (mobile-bot).
```

## Flow per turn

1. User message → `UserPromptSubmit` hook prepends `[now: <ts> | gap: <since-last>]`.
2. Agent loads `CLAUDE.md` (always in context) + `MEMORY.md` (trigger index).
3. If the message matches a trigger in `MEMORY.md`, agent reads the linked memory file.
4. Agent uses tools. `PreToolUse` hooks can block or redirect (e.g. PDF read → extract first → read `.txt`).
5. Agent replies.

## Lifecycle hook map

| Event | When | This repo uses it for |
|-------|------|-----------------------|
| `SessionStart` | New session | Weekly memory health check |
| `UserPromptSubmit` | Each user message | Prepend timestamp + gap |
| `PreToolUse` | Before tool call | PDF/HTML auto-extract; mobile-bot write allowlist |
| `PostToolUse` | After tool call | Mobile-bot audit log + git commit |

Hooks read JSON from stdin, exit 0 (pass) or 2 (block with stderr message to agent).

## Where to add things

| Adding... | Goes in |
|-----------|---------|
| A rule that should always apply | `CLAUDE.md` |
| Enforcement that can't depend on agent memory | `hooks/` |
| A reusable utility | `scripts/` |
| A multi-step workflow invoked on demand | `skills/` |
| A fact about the user / project / external system | `memory/` |
| A fact about the codebase | nowhere — read the code |
