# claude-code-methodology

Configuration files, hooks, scripts, and slash skills for Claude Code.

One person's setup, generalized over months of daily use. The mechanisms (hooks, memory layout, gates) are portable; the communication and output rules are personal taste — `CLAUDE.md` marks which is which. Take the pieces that fit; rewrite the rest.

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

**Start here** (a single agent — most readers):
- [`docs/methodology.md`](docs/methodology.md) — the full writeup of the approach (memory, skills, hooks, permissions, communication, workflow rituals, lessons).
- [`docs/examples.md`](docs/examples.md) — before/after dialogues showing what the rules do to agent behavior.
- [`docs/case-study.md`](docs/case-study.md) — a real observation session that shaped several of the rules.

**Going deeper** (long sessions, verification, self-correction):
- [`docs/context-management.md`](docs/context-management.md) — keeping a months-long agent chat alive: hygiene layers, the hybrid lifecycle, and why mechanisms beat remembering.
- [`docs/measurement-and-proof.md`](docs/measurement-and-proof.md) — when the instrument lies: what counts as proof a mechanism ran, why gates measure what they can see (not what is), and where no mechanism exists.
- [`docs/mistakes-journal.md`](docs/mistakes-journal.md) — one file for postmortems, so three of the same mistake become a mechanism instead of a habit.
- [`docs/coding-standard.md`](docs/coding-standard.md) — the working standard every agent that writes code follows: a one-screen core (each rule marked with what guards it — a mechanism, an audit, or nobody) plus a reference by activity.
- [`code-pitfalls/`](code-pitfalls/README.md) — 268 technical lessons already paid for, in 11 files by technology (shell, python, git, web, hooks, verification, concurrency, services, VM, Windows, Android); a hook shows the matching headings before an edit.
- [`docs/hall-of-shame-docs.md`](docs/hall-of-shame-docs.md), [`docs/hall-of-shame-ops.md`](docs/hall-of-shame-ops.md) — two real bad cases kept as models of what not to do: a document written for its author, and a network change declared "done" before the human's own path was checked.
- [`docs/docx-playbook.md`](docs/docx-playbook.md) — generating Word documents with python-docx without the silent layout traps; render to an image before handing over.
- [`docs/rule-to-mechanism.md`](docs/rule-to-mechanism.md) — the gate ladder (note → detector → structural impossibility): the change cycle, independent review by another model, a supervisor that checks the work, and why written rules alone didn't hold.

**Running a swarm** (many agents — a separate discipline; skip these if you run one agent):
- [`docs/multi-agent.md`](docs/multi-agent.md) — running a swarm of ~80 long-lived agents: delivery, coordination, and the failures that cost more than the design.
- [`docs/dev-methodology.md`](docs/dev-methodology.md) — the delivery layer: roles, roadmap + Definition of Done, quality gates, and bootstrap — a product team when the team is agents.
- [`docs/project-work.md`](docs/project-work.md) — the standard for agents working in a project team: the path of a task, stories with a runnable "done when", stands, releases, blockers as records with a check.
- [`docs/po-interface.md`](docs/po-interface.md) — how ~30 technical reports a day reach a human who isn't a developer: a two-question filter, three lanes, and a pull mode.
- [`docs/mission-control.md`](docs/mission-control.md) — a web panel that steers live agents by appending to a file channel they tail: cheap push over cold-start, everything counted from outside.

## Install

```bash
git clone https://github.com/Hanzinner/claude-code-methodology
cd claude-code-methodology
./install.sh
```

`install.sh` detects `claude`, asks for scope (user `~/.claude/` or project `<dir>/.claude/`), copies `hooks/`, `scripts/`, `skills/`, `code-pitfalls/` (your own lessons are kept), `CLAUDE.md`, `memory-template/`, generates `settings.json` with hook paths, offers system deps and the mobile-bot addon. Existing files are backed up to `*.bak-<timestamp>`.

You can hand the repo to your own agent and say "install this": it runs `./install.sh` like a person would.

**Asking an agent to install it.** Paste this into Claude Code (any folder):

> Install https://github.com/Hanzinner/claude-code-methodology for me. Clone it into ~/claude-code-methodology
> (or `git pull` there if it exists), read its README, then run `./install.sh --user` (it takes defaults when
> nobody answers; that is fine). Then run `./check-install.py --user` and show me its full output.
> It is not installed until that check ends with "0 missing or broken"; if anything is missing, fix it and
> run the check again. Do not delete or move anything in ~/.claude yourself. Tell me which of my existing
> files the installer backed up or kept (`*.bak-*`, `CLAUDE.md.new`), then tell me to restart Claude Code.

**What it never touches:** your chats and session history (`~/.claude/projects/`, `history.jsonl`),
`~/.claude.json`, your own commands, agents and MCP servers. It writes only its own folders and merges
`settings.json`. This is tested on a clean machine: fingerprints of those files before and after two
installs and a run of every hook are compared.

Want it for one project only: say `--project <path>` instead of `--user`. The optional extras (system
packages for PDF/HTML extraction, the Telegram bot) are off by default; ask the agent for them separately.

**Updating** as new layers land: `git pull && ./install.sh` again. Your memory, your own code lessons, your
permissions, env, model and your own hooks in `settings.json` are kept (only the hook entries that point
into the installed `hooks/` are replaced). If you edited `CLAUDE.md`, it is kept and the new version is
written next to it as `CLAUDE.md.new`. Every replaced file is also backed up as `*.bak-<timestamp>`.

**Platforms:** Linux and macOS (bash + python3). On **Windows, use WSL** (`wsl --install`, then install
Claude Code and this repo inside it). Native Windows is not supported yet: the hooks are bash and python
scripts, and Claude Code on Windows runs PowerShell unless Git Bash is installed.

**What it sets up today, and what not yet** (as of 2026-11; the goal is the whole private setup with one command, built layer by layer):

| Layer | Installed by `install.sh` today | In the repo, set up by hand | Not in the repo yet |
|---|---|---|---|
| One agent | `CLAUDE.md`, 14 hooks, scripts, `/recap` `/audit`, memory template, code lessons | mobile bot (offered by the installer), offsite backup (`addons/offsite-backup/`) | most of the private guards on replies (about 30 more) |
| A swarm of agents | — | `multi-agent/` (inbox writer, briefing watchman, git wrapper, session hygiene), `swarm-template/` (journal, registry, catalog, agent folder) | project bootstrap, releaser, blocker register |
| Upkeep | — | — | watchdog over all mechanisms, nightly reconciliations, the panel |

## Layout

| Path | What |
|------|------|
| `CLAUDE.md` | Operating core — behavioral rules loaded into every conversation |
| `hooks/` | Shell/Python hooks on `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PreCompact`, `PostCompact`, `PermissionDenied`, `Stop` |
| `scripts/` | Utilities called from hooks, skills, or directly |
| `skills/` | Slash commands (`/recap`, `/audit`) |
| `memory-template/` | Seed for `memory/` (trigger index + 4 type examples) |
| `swarm-template/` | Empty shared files for a swarm: mistakes journal with the classes that repeated, agent registry, mechanism catalog, one agent's folder |
| `code-pitfalls/` | Technical lessons already paid for, one file per technology — shown to the agent before it edits that kind of code |
| `mcp/` | Setup notes for MCP servers |
| `addons/mobile-bot/` | Optional Telegram bridge |
| `addons/offsite-backup/` | Nightly encrypted incremental backup to S3-compatible storage (restic + Filebase/R2/B2) |
| `docs/` | Methodology writeup, architecture, philosophy, memory system, hooks guide, examples, case study, multi-agent, context management, measurement & proof, mistakes journal, mission control, dev methodology, rule to mechanism |
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

Plus eleven **hardening hooks** (memory-write gate — opt-in, pre/post-compact steering, permission-denied hint, reply-guard, stop-dispatch, a fail-open `hook-safe` wrapper, the change-cycle detectors: stuck-detector, proof-guard, code-pitfalls-hint, and `surface-flags`, which shows the detectors' flags and hook errors on the next prompt) that turn discipline-dependent rules into mechanical gates — see [`hooks/README.md`](hooks/README.md#hardening-hooks).

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
| `cross-review.sh --git <range>` | Independent review of a diff by a different model (fresh `claude -p`, read-only tools). See `docs/rule-to-mechanism.md`. |

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
