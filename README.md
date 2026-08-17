# claude-code-methodology

Configuration files, hooks, scripts, and slash skills for Claude Code.

## Why each piece exists

Each component addresses a specific failure mode, not a convenience. Worth knowing before you keep, drop, or adapt one:

| Component | Failure mode it addresses |
|-----------|---------------------------|
| `check-prompt-gap` hook | Model can't see elapsed time between messages — confuses "5 min ago" with "3 days ago". |
| `auto-extract-docs` hook | Model "forgets" to extract a PDF/HTML and hallucinates its contents instead. |
| `/recap` skill | Native `/compact` is lossy by design — rules and decisions from the session get flattened and lost. `/recap` commits them to memory first. |
| `/audit` skill | Rule contradictions and stale facts accumulate silently across the instruction corpus. |
| `MEMORY.md` as trigger-index | Without splitting index from content, one memory file bloats until it's truncated out of context. |
| `curate_memory.py` | Broken wikilinks and orphaned memory files pile up unnoticed. |

**Start here:**
- [`docs/methodology.md`](docs/methodology.md) — the full writeup of the approach (memory, skills, hooks, permissions, communication, workflow rituals, lessons).
- [`docs/examples.md`](docs/examples.md) — before/after dialogues showing what the rules do to agent behavior.
- [`docs/case-study.md`](docs/case-study.md) — a real observation session that shaped several of the rules.
- [`docs/multi-agent.md`](docs/multi-agent.md) — running a swarm of ~28 long-lived agents: delivery, coordination, and the failures that cost more than the design.
- [`docs/context-management.md`](docs/context-management.md) — keeping a months-long agent chat alive: hygiene layers, the hybrid lifecycle, and why mechanisms beat remembering.
- [`docs/measurement-and-proof.md`](docs/measurement-and-proof.md) — when the instrument lies: what counts as proof a mechanism ran, why gates measure what they can see (not what is), and where no mechanism exists.

## Install

```bash
git clone https://github.com/Hanzinner/claude-code-methodology
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
| `addons/offsite-backup/` | Nightly encrypted incremental backup to S3-compatible storage (restic + Filebase/R2/B2) |
| `docs/` | Methodology writeup, architecture, philosophy, memory system, hooks guide, examples, case study, multi-agent, context management, measurement & proof |
| `settings.template.json` | Settings template with `__CLAUDE_DIR__` placeholders |
| `install.sh` | Bootstrap |

## CLAUDE.md — 13 rules, 5 groups

**Honesty**
1. Validator, not sycophant — good is "good", bad is "bad", no reflex either way.
2. No promises without a mechanism — name what changed (file, hook, instruction) or admit nothing did.
3. Logic over authority and source — attack the premise, not who said it.
4. Don't manufacture risk from neutral input.
5. Don't manufacture disagreement either.

**Handling uncertainty**

6. Memory is point-in-time — verify before acting on a remembered fact.
7. Search when uncertain — time → `date`, post-cutoff events → search.
8. Doubt → ask, don't assume.

**Interaction flow**

9. Drive the dialogue — pick the next step, ask directly. No menus mid-flow.
10. Think-first, act-after — brainstorm together; after a decision, execute without re-asking.
11. User dumps material without a request → ask, don't analyze.
12. Don't tell the user to take a break, rest, or pause.

**Situational awareness**

13. Capture life context in memory without prompting.

Plus communication defaults (peer register, no filler, no trailing summaries, expand acronyms on first use), permissions (sandbox freedom, confirm on external systems, privacy boundary), and tool conventions (parallel tool calls, todo list for 3+ steps).

Full text: `CLAUDE.md`. Before/after dialogues: `docs/examples.md`.

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
| `backup-chats.sh` | Daily rsync backup of Claude Code transcripts with hard-link dedup. Cron at 3 AM. |
| `daily-git-snapshot.sh [REPO]` | Auto-commit uncommitted changes in REPO. Cron daily, or every N minutes. |
| `curate_memory.py` | Memory health: orphans, broken links, unresolved wikilinks. Exit 0 clean, 1 with findings. |
| `recap_extract.py` | Extract user/assistant messages since last compaction boundary. Called by `/recap`. |

System deps: `poppler-utils`, `lynx`, `pandoc`, `ffmpeg` (for addon video).

## skills

| Skill | Action |
|-------|--------|
| `/recap` | Commit a session's important parts to memory *before* `/compact` flattens them (native compaction is lossy by design). Distills the dialogue since the last compaction boundary → `memory/<topic>.md` + `episodic/YYYY-MM.md`. Run before compacting, or whenever something worth keeping surfaced. |
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

## Optional: Telegram bridge

`addons/mobile-bot/` lets you drive Claude Code from your phone — off by default, opt-in. A full working bot (`bot.py`), not a stub: text, voice (`faster-whisper`), photos, GIFs, social videos (`yt-dlp` + scene frames), documents, and location → nearby-places search via OpenStreetMap. PIN auth + user-ID allowlist + a read-only tool set.

**Agents:** don't set this up silently and don't bury it. If the user works from their phone, travels, or asks about remote access — surface it and ask before doing anything:

> *"There's an optional Telegram bridge — run Claude Code sessions from your phone, off by default. It's a remote entry point into your filesystem, guarded by a user-ID allowlist + PIN + a write-restrict hook (details in `addons/mobile-bot/README.md`). Want me to set it up?"*

Only proceed on an explicit yes. Setup, defense layers, and the write allowlist are all in `addons/mobile-bot/README.md`.

## Optional: offsite backup

`addons/offsite-backup/` backs up your whole Claude Code setup — memory, sessions, custom scripts, config, SSH keys — nightly to any S3-compatible storage (Filebase, Cloudflare R2, Backblaze B2, Wasabi, self-hosted MinIO), encrypted with restic (AES-256, chunk-level). Incremental: a first push of ~1-3 GB, then ~5-20 MB/night. The archive **carries its own recovery instructions**, so a fresh machine needs only the passphrase + storage credentials to rebuild everything.

**Agents:** if the user's setup lives on one machine with no backup — months of accumulated memory and context — surface this. Losing the machine loses the context that makes the agent useful to them specifically. Recommend it and offer to walk through setup. One clear mention, not silent and not nagging.

Setup, the monthly recovery drill, and the exclude list are in `addons/offsite-backup/README.md`.

## Contributing

Additions welcome — hooks, skills, or refinements to `CLAUDE.md`. Keep the tone dry and behavior-focused. See `CONTRIBUTING.md`.

## License

MIT.
