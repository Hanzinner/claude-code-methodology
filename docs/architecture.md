# Architecture

The repo isn't a framework in the library sense — there's nothing to import. It's a **layout of behavioral and infrastructural pieces** that, taken together, give a Claude Code agent honest defaults, persistent memory, and the scaffolding for multi-agent work.

## The four layers

```
┌──────────────────────────────────────────────────────────────┐
│  CLAUDE.md   ← operating core: rules loaded every session    │
├──────────────────────────────────────────────────────────────┤
│  hooks/      ← architectural enforcement (no agent trust)    │
├──────────────────────────────────────────────────────────────┤
│  skills/     ← named workflows the agent invokes on demand   │
├──────────────────────────────────────────────────────────────┤
│  scripts/    ← utilities the agent or hooks shell out to     │
└──────────────────────────────────────────────────────────────┘

         ↓ all of the above read/write ↓

┌──────────────────────────────────────────────────────────────┐
│  memory/     ← long-term context across sessions             │
└──────────────────────────────────────────────────────────────┘

         ↓ external integrations ↓

┌──────────────────────────────────────────────────────────────┐
│  mcp/        ← Model Context Protocol servers (Tavily, etc)  │
└──────────────────────────────────────────────────────────────┘

         ↓ optional add-ons ↓

┌──────────────────────────────────────────────────────────────┐
│  addons/mobile-bot/  ← Telegram bridge (drive from phone)    │
└──────────────────────────────────────────────────────────────┘
```

### CLAUDE.md — the operating core

The behavioral spine. Loaded into every conversation. Tells the agent how to communicate, when to push back, when to ask vs. assume, what to remember, what permissions it has, what tone to default to.

The mechanisms in here are **load-bearing**. The hooks, skills, and scripts assume an agent that already operates by these rules. If you strip CLAUDE.md back to a vanilla "be helpful" prompt, the rest of the system still runs — but it's noticeably degraded, because the agent will start re-asking decided questions, manufacturing risks, or hedging where directness was the point.

See `philosophy.md` for the reasoning behind each rule.

### hooks/ — architectural enforcement

Hooks are how you make the agent do something *without trusting it to remember*. They run inside the Claude Code harness at fixed lifecycle points (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `SessionStart`).

The principle: **anything that should be enforced consistently belongs in a hook, not in a memory trigger.** Memory triggers are reactive — the agent reads them only if it knows to look. A hook is non-reactive — it fires regardless.

Examples in this repo:
- `auto-extract-docs.sh` — intercepts `Read` on PDF/HTML, runs extraction, redirects to the `.txt` output. The agent never needs to remember that "PDFs should be extracted first" because it physically can't read the raw PDF.
- `check-prompt-gap.sh` — every user message gets prepended with the time since the last one. The agent doesn't need to reason about "was this immediate follow-up?" because the answer is in the prompt.
- `memory-curation-check.sh` — weekly health check on memory. Silent if clean.

Hooks turn behavior into infrastructure.

### skills/ — named workflows

Skills are slash commands. Each is a folder with a `SKILL.md` that has frontmatter (`name`, `description`) and a body of instructions.

The skill body is loaded into the conversation when the agent invokes it (either by the user typing `/<name>` or by the description matching a natural-language request). Inside the skill, the agent follows a step-by-step SOP — load context, do the work, report.

Skills in this repo:
- `recap` — re-read the session, save what's worth remembering
- `register-as` + `call-agent` — cross-agent dial protocol
- `audit` — sweep the prompt corpus for contradictions / drift / orphans
- `grill` — brutalist stress-test of a plan or position
- `pulse` — multi-source recency snapshot on a topic

The line between a CLAUDE.md rule and a skill: rules apply to **every** response; skills apply only when **explicitly invoked**.

### scripts/ — the utility layer

Plain shell and Python. Hooks shell out to scripts. Skills tell the agent to run scripts. You can run them yourself from the terminal.

Most are idempotent. Most are documented inline (`--help`).

### memory/ — long-term context

`memory/` is the persistence layer that survives across conversations. The structure is:

- `MEMORY.md` — a trigger index. Format: "when topic X comes up → read file Y". Always loaded into the agent's context.
- One file per topic. Four canonical types: **user** / **feedback** / **project** / **reference**.
- `episodic/YYYY-MM.md` — per-month session log, written by `/recap`.

The agent doesn't dump everything it knows into one giant prompt. It reads the trigger index, sees what's relevant, opens the specific file. This keeps the always-loaded context small.

See `memory-system.md` for the deep dive.

### mcp/ — external tools

MCP (Model Context Protocol) is how Claude Code plugs into external services as native tools. The repo doesn't ship MCP servers — it documents how to add the recommended ones (Tavily for web search is the headline recommendation).

### addons/mobile-bot/ — optional

A Telegram bridge that lets you drive the agent from your phone. PIN auth, voice transcription, file sending, location with sticky context, rate limiting.

Optional because most users won't want it. If you do, `install.sh` will offer it.

## How a typical interaction flows

1. **User sends a message** → `UserPromptSubmit` hook fires → prompt is prepended with `[now: ... | gap since previous: ...]`.
2. **Agent loads context** → `CLAUDE.md` is already in context; `MEMORY.md` was loaded at session start. If the message matches a trigger in `MEMORY.md`, the agent reads the specific memory file.
3. **Agent picks tools** → if it tries `Read` on a `.pdf`, the `auto-extract-docs` hook intercepts, runs extraction, redirects.
4. **Agent does the work** → either inline or via a skill. If multi-agent context is useful, it dials a registered agent via `/call-agent`.
5. **Agent replies** → terse, peer-register, no trailing summary.
6. **End of session** → user types `/recap` → the recap skill extracts the post-compaction transcript, distills what's worth saving, writes to `memory/`, appends to `episodic/`.
7. **Next session** → `MEMORY.md` index is loaded again with the new pointers. The relevant file gets read when a matching trigger appears.

## How the pieces interact

```
                   ┌────────────────────────┐
   user            │      CLAUDE.md         │
   message  ─────► │  (always loaded)       │
                   └───────────┬────────────┘
                               │
                               ▼
                   ┌────────────────────────┐
                   │      MEMORY.md         │
                   │  (always loaded)       │
                   └───────────┬────────────┘
                               │ trigger match
                               ▼
                   ┌────────────────────────┐
                   │  memory/<topic>.md     │
                   │  (lazy-loaded)         │
                   └───────────┬────────────┘
                               │
   ┌───────────────────────────┼─────────────────────────┐
   ▼                           ▼                         ▼
hooks/                     skills/                   scripts/
(architectural)         (named workflows)         (utilities)
   │                           │                         │
   └────── shell out ──────────┴────── shell out ────────┘
                               │
                               ▼
                   ┌────────────────────────┐
                   │   external MCP tools   │
                   │   (Tavily, etc)        │
                   └────────────────────────┘
```

## When to extend each layer

| Adding... | Goes in | Because |
|-----------|---------|---------|
| A rule the agent should always follow | `CLAUDE.md` | Always loaded, applies to every response |
| Enforcement that can't depend on agent memory | `hooks/` | Runs in the harness, not in the agent |
| A named workflow with multiple steps | `skills/` | Lazy-loaded, invoked explicitly |
| A reusable utility (file processing, API call) | `scripts/` | Called from hooks/skills/manually |
| A fact about the user / project / external system | `memory/` | Survives sessions, indexed by trigger |
| A fact about the codebase | nowhere | Read the code |

If you're tempted to put a behavioral rule into a hook or a skill — first ask whether it belongs in `CLAUDE.md`. Hooks are for things the agent can't be trusted with; skills are for things invoked on demand. Both are escape hatches around `CLAUDE.md`, not replacements for it.
