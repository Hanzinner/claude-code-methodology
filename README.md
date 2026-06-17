# claude-code-methodology

A working **operating system for Claude Code**: honest behavioral defaults, a memory architecture that survives across sessions, hooks that enforce hygiene the agent can't be trusted to remember, slash-skills for recurring workflows, and a cross-agent dial that lets one chat call another.

This is not a tutorial. It's the real setup, packaged so a new user can clone and run.

## What's inside

| Layer | What it does |
|-------|--------------|
| **`CLAUDE.md`** | The operating core. Behavioral rules the agent loads every conversation — validator-not-sycophant, no-promises-without-mechanism, logic-over-source, point-in-time memory, neutral-until-proven-risky. |
| **`hooks/`** | PreToolUse / PostToolUse / UserPromptSubmit / SessionStart hooks. Architecturally enforce things the agent would otherwise forget: auto-extract PDF/HTML before reading, inject time-since-last-message into every prompt, audit memory health on session start. |
| **`scripts/`** | Reusable utilities the agent calls: document extraction (PDF/HTML → text), location lookup (OSM Overpass), cross-agent dial (resume someone else's session and ask them a question), chat backup, daily git snapshot, recap extraction. |
| **`skills/`** | Slash commands: `/recap` (save important context to memory), `/audit` (find contradictions in the rulebook), `/grill` (stress-test a plan), `/pulse` (multi-source recency snapshot), `/dossier` (hypothesis-tested research), `/call-agent` + `/register-as` (cross-agent dial). |
| **`memory-template/`** | The memory layout: `MEMORY.md` as a trigger index, files-per-topic, frontmatter convention, four memory types (user / feedback / project / reference). Comes with sanitized examples. |
| **`mcp/`** | Guide for hooking up MCP servers (Tavily for web search, optional GitHub / Notion / Perplexity). |
| **`addons/mobile-bot/`** | **Optional.** Telegram bridge to Claude Code on your machine — PIN auth, voice transcription, file sending, location with sticky context, rate limiting. Drop in if you want to drive the agent from your phone. |
| **`docs/`** | Architecture overview, philosophy behind the choices, deep-dives on memory / agents / hooks / skills. |

## Install

```bash
git clone https://github.com/<you>/claude-code-methodology
cd claude-code-methodology
./install.sh
```

`install.sh` will:
- detect your Claude Code install
- ask whether to install at user scope (`~/.claude/`) or project scope (`./.claude/`)
- copy hooks, scripts, and skills into the right places
- generate a `settings.json` with the hook paths wired up
- offer to install Python dependencies for the optional pieces (faster-whisper for voice, ffmpeg for video, etc.)
- offer to install the mobile-bot addon (skipped by default)

After install, start a new Claude Code session and the operating core is live. Customize `CLAUDE.md` to your voice.

## Philosophy in one paragraph

Most "AI assistant" defaults optimize for the user feeling helped. This setup optimizes for the user actually being helped — which means the agent has to be willing to disagree, to ask before assuming, to not invent risks where none exist, and to remember things across conversations without becoming a yes-machine. The mechanisms in `CLAUDE.md` are load-bearing; the hooks and skills are scaffolding around them.

See [`docs/philosophy.md`](docs/philosophy.md) for the long version.

## Compatibility

- **Claude Code** (CLI): primary target. Tested on Linux and macOS.
- **Claude Agent SDK**: most of `CLAUDE.md`, the skill format, and the memory layout transfer directly. Hooks need adaptation to SDK lifecycle.
- Windows is not tested — most scripts assume bash. WSL works.

## Adapt, don't adopt

This is one person's working setup, generalized. The mechanisms (validator, point-in-time memory, neutral-until-proven-risky, architectural enforcement via hooks) survive any domain. The surface (tone, language, what gets logged) is yours to set. Read `docs/philosophy.md` and `docs/architecture.md`, then prune and rewrite.

## License

MIT — see [`LICENSE`](LICENSE).
