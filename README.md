# claude-code-methodology

Configuration files, hooks, scripts, and slash skills for Claude Code.

## Install

```bash
git clone https://github.com/<you>/claude-code-methodology
cd claude-code-methodology
./install.sh
```

`install.sh` detects `claude`, asks for scope (user `~/.claude/` or project `<dir>/.claude/`), copies `hooks/`, `scripts/`, `skills/`, `CLAUDE.md`, `memory-template/`, generates `settings.json` with hook paths, offers system deps and the mobile-bot addon. Existing files are backed up to `*.bak-<timestamp>`.

## Layout

| Path | What |
|------|------|
| `CLAUDE.md` | Operating core — behavioral rules loaded into every conversation |
| `hooks/` | Shell hooks (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `SessionStart`) |
| `scripts/` | Utilities called from hooks, skills, or directly |
| `skills/` | Slash commands (`/recap`, `/audit`) |
| `memory-template/` | Seed for `memory/` (trigger index + 4 type examples) |
| `mcp/` | Setup notes for MCP servers |
| `addons/mobile-bot/` | Optional Telegram bridge |
| `docs/` | Architecture, philosophy, memory system, hooks guide |
| `settings.template.json` | Settings template with `__CLAUDE_DIR__` placeholders |
| `install.sh` | Bootstrap |

## CLAUDE.md — 13 rules

1. Don't tell the user to take a break, rest, or pause.
2. Validator, not sycophant — good is "good", bad is "bad", no reflex either way.
3. No promises without a mechanism — name what changed (file, hook, instruction) or admit nothing did.
4. Logic over authority and source — attack the premise, not who said it.
5. Memory is point-in-time — verify before acting on a remembered fact.
6. Search when uncertain — time → `date`, post-cutoff events → search.
7. Drive the dialogue — pick the next step, ask directly. No menus mid-flow.
8. Doubt → ask, don't assume.
9. Think-first, act-after — brainstorm together; after a decision, execute without re-asking.
10. Don't manufacture risk from neutral input.
11. Don't manufacture disagreement either.
12. Capture life context in memory without prompting.
13. User dumps material without a request → ask, don't analyze.

Plus communication defaults (peer register, no filler, no trailing summaries, expand acronyms on first use), permissions (sandbox freedom, confirm on external systems, privacy boundary), and tool conventions (parallel tool calls, todo list for 3+ steps).

Full text: `CLAUDE.md`.

## hooks

| File | Event | Action |
|------|-------|--------|
| `auto-extract-docs.sh` | PreToolUse on `Read` | Intercepts `.pdf` / `.html`, runs extraction, redirects to `.txt`. PDFs >10 MB → manual-run message. |
| `check-prompt-gap.sh` | UserPromptSubmit | Prepends `[now: <ts> \| gap since previous: <delta>]`. |
| `memory-curation-check.sh` | SessionStart | Weekly `curate_memory.py` run. Silent if clean. |

Mobile-bot addon adds two more (no-ops outside the bot):
- `addons/mobile-bot/hooks/mobile-restrict.sh` — PreToolUse Write/Edit allowlist
- `addons/mobile-bot/hooks/mobile-audit.sh` — PostToolUse audit log + git commit

## scripts

| File | Action |
|------|--------|
| `pdf-extract.sh <pdf> [--images] [--dpi=N]` | PDF → `.txt` (full) + `.meta.txt` + `.pages/p####.txt` + optional `.images/p####.png`. Idempotent. |
| `html-extract.sh <html>` | HTML → `.txt` via `lynx -dump`. Plain text. |
| `html-to-md.sh <html>` | HTML → `.md` via `pandoc`. Preserves structure. |
| `osm-nearby.sh <lat> <lng> [radius] [amenity] [name_regex]` | OSM Overpass nearby search. Free, no signup. |
| `osm_nearby.py` | Python impl called by `osm-nearby.sh`. |
| `backup-chats.sh` | Daily rsync backup of Claude Code transcripts with hard-link dedup. Cron at 3 AM. |
| `daily-git-snapshot.sh [REPO]` | Auto-commit uncommitted changes in REPO. Cron daily, or every N minutes. |
| `curate_memory.py` | Memory health: orphans, broken links, unresolved wikilinks. Exit 0 clean, 1 with findings. |
| `recap_extract.py` | Extract user/assistant messages since last compaction boundary. Called by `/recap`. |

System deps: `poppler-utils`, `lynx`, `pandoc`, `ffmpeg` (for addon video).

## skills

| Skill | Action |
|-------|--------|
| `/recap` | Read post-compaction transcript, distill memorable parts, write to `memory/<topic>.md`, append to `episodic/YYYY-MM.md`. |
| `/audit` | Sweep `CLAUDE.md` + `memory/` + `skills/` for contradictions, persona drift, cognitive overload, semantic ambiguity, orphaned references, stale facts. Reports only — doesn't auto-fix. |

## memory layout

```
memory/
├── MEMORY.md           # trigger index, always loaded
├── episodic/YYYY-MM.md # session log
└── <type>_<topic>.md   # one file per topic
```

Four types: `user`, `feedback`, `project`, `reference`. Each file has frontmatter (`name`, `description`, `metadata.type`) and uses `[[name]]` wikilinks to connect to others.

See `docs/memory-system.md` and `memory-template/examples/`.

## After install

- Hooks run automatically in new sessions.
- Slash skills are available: `/recap`, `/audit`.
- Edit `~/.claude/CLAUDE.md` to change the operating core.
- Edit `~/.claude/memory/MEMORY.md` to add trigger pointers.

## Compatibility

- Claude Code CLI on Linux and macOS.
- Bash; Windows needs WSL.

## License

MIT.
