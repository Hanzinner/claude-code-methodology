# Architecture

## Layers

```
CLAUDE.md         Behavioral rules loaded into every conversation.
hooks/            Shell/Python scripts run by the harness at lifecycle events.
scripts/          Utilities called from hooks, skills, or directly.
skills/           Slash commands (/recap, /audit).
memory/           Per-topic markdown files + MEMORY.md trigger index.
code-pitfalls/    Per-technology lessons, shown (headings only) before a matching edit.
mcp/              MCP server config (Tavily, etc).
multi-agent/      Two hand-made examples not installed yet (session trimming, tool redirect).
swarm-template/   Shared files for several agents: registry, mistakes journal, catalog, one agent folder.
addons/           Optional extensions (mobile-bot, offsite-backup).
```

## Flow per turn

1. User message → `UserPromptSubmit` hooks prepend `[now: <ts> | gap: <since-last>]` and any flags left by last turn's detectors.
2. Agent loads `CLAUDE.md` (always in context) + `MEMORY.md` (trigger index).
3. If the message matches a trigger in `MEMORY.md`, agent reads the linked memory file.
4. Agent uses tools. `PreToolUse` hooks can block or redirect (e.g. PDF read → extract first → read `.txt`) or add context (lessons before an edit). `PostToolUse`/`PostToolUseFailure` count failures in a row.
5. Agent replies. `Stop` hooks check the finished reply and leave flags for step 1 of the next turn.

## Lifecycle hook map

| Event | When | This repo uses it for |
|-------|------|-----------------------|
| `SessionStart` | New session | Weekly memory health check |
| `UserPromptSubmit` | Each user message | Prepend timestamp + gap; surface detector flags and hook errors |
| `PreToolUse` | Before tool call | PDF/HTML auto-extract; lessons before an edit; mobile-bot write allowlist |
| `PostToolUse` | After tool call | Stuck-detector reset; mobile-bot audit log + git commit |
| `PostToolUseFailure` | After a failed tool call | Stuck-detector (3 failed Bash calls in a row → stop and look it up) |
| `PreCompact` / `PostCompact` | Around compaction | Steer what the summary keeps; archive the summary |
| `PermissionDenied` | A tool call was denied | "Don't hop channels" hint |
| `Stop` | Reply finished | Dispatcher → reply-guard, proof-guard |

Hooks read JSON from stdin and answer with JSON on stdout (a deny decision, extra context) or exit 2 to block where the event allows it. Exit codes and output: [hooks-guide.md](hooks-guide.md).

## Where to add things

| Adding... | Goes in |
|-----------|---------|
| A rule that should always apply | `CLAUDE.md` |
| Enforcement that can't depend on agent memory | `hooks/` |
| A reusable utility | `scripts/` |
| A multi-step workflow invoked on demand | `skills/` |
| A fact about the user / project / external system | `memory/` |
| A fact about the codebase | nowhere — read the code |
