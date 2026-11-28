# claude-code-methodology

Configuration files, hooks, scripts, and slash skills for Claude Code.

One person's setup, generalized over months of daily use. The mechanisms (hooks, memory layout, gates) are portable; `CLAUDE.md` is the rule set the agent works by; after the install the agent tells you what is in it and asks what you want to add.

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
- [`docs/accounts.md`](docs/accounts.md) — the outside accounts (all optional except Claude Code): where to sign up, what is free, which file each key goes into.
- [`docs/getting-started.md`](docs/getting-started.md) — after the install: the first day, day-to-day use, what the mechanisms will do in front of you, and how to add more agents.

**Going deeper** (long sessions, verification, self-correction):
- [`docs/mistakes-journal.md`](docs/mistakes-journal.md) — one file for postmortems, so three of the same mistake become a mechanism instead of a habit.
- [`docs/coding-standard.md`](docs/coding-standard.md) — the working standard every agent that writes code follows: a one-screen core (each rule marked with what guards it — a mechanism, an audit, or nobody) plus a reference by activity.
- [`code-pitfalls/`](code-pitfalls/README.md) — 342 technical lessons already paid for, in 11 files by technology (shell, python, git, web, hooks, verification, concurrency, services, VM, Windows, Android); a hook shows the matching headings before an edit.
- [`docs/hall-of-shame-docs.md`](docs/hall-of-shame-docs.md) — a real bad case kept as a model of what not to do: a document written for its author.

**Running a swarm** (many agents — a separate discipline; skip these if you run one agent):
- [`docs/dev-methodology.md`](docs/dev-methodology.md) — starting a project: what to ask the human, the command, positions to propose, what the lead does first.
- [`docs/project-work.md`](docs/project-work.md) — the standard for agents working in a project team: the path of a task, stories with a runnable "done when", stands, releases, blockers as records with a check.
- [`docs/po-interface.md`](docs/po-interface.md) — how ~30 technical reports a day reach a human who isn't a developer: a two-question filter, three lanes, and a pull mode.
- [`docs/web-playbook.md`](docs/web-playbook.md) — how agents build sites: "done" means seen at phone width, only proven state on a status panel, deploying under live users.

## Install

```bash
git clone https://github.com/Hanzinner/claude-code-methodology
cd claude-code-methodology
./install.sh
```

`install.sh` detects `claude`, asks for scope (user `~/.claude/` or project `<dir>/.claude/`), copies `hooks/`, `scripts/`, `skills/`, `agents/` (one subagent), `code-pitfalls/` (your own lessons are kept), `CLAUDE.md`, `memory-template/`, generates `settings.json` with hook paths, offers system deps and the mobile-bot addon. Existing files are backed up to `*.bak-<timestamp>`.

You can hand the repo to your own agent and say "install this": it runs `./install.sh` like a person would.

**Asking an agent to install it.** Paste this into Claude Code (any folder):

> Install https://github.com/Hanzinner/claude-code-methodology for me. Clone it into ~/claude-code-methodology
> (or `git pull` there if it exists), read its README, then run `./install.sh --user` (it takes defaults when
> nobody answers; that is fine). Then run `./check-install.py --user` and show me its full output.
> It is not installed until that check ends with "0 missing or broken"; if anything is missing, fix it and
> run the check again. Do not delete or move anything in ~/.claude yourself. Tell me which of my existing
> files the installer backed up or kept (`*.bak-*`, `CLAUDE.md.new`). Then read docs/accounts.md and tell me,
> one line each, which optional accounts I might want (web search, offsite backup, phone bot): where to sign up
> and which file the key goes into. Never ask me for a key in the chat. If I already had my own
> ~/.claude/CLAUDE.md, the installer keeps it and leaves your rules next to it (CLAUDE.md.new, CLAUDE.md.changes):
> merge them into mine as it says — keep everything of mine, add what is missing, ask me one line about each rule
> that contradicts mine. Then tell me in a few short lines what rules are now in ~/.claude/CLAUDE.md and ask whether I want to add anything; if I do, add it there.
> Then read docs/getting-started.md (sections 2, 4, 5) and tell me what the system now does for me. Assume I have
> never heard of any of it: for each thing, first the problem it removes, in my words, then what it does, then how
> I use it; a tool's name only after that. The same for the optional accounts: what I would get from each, not
> just its name. Short, no file paths unless I ask. Finally tell me to restart Claude Code.

**What it never touches:** your chats and session history (`~/.claude/projects/`, `history.jsonl`),
`~/.claude.json`, your own commands, agents and MCP servers (in `agents/` it writes only its own `deep-code-reviewer.md`, after backing up your edited copy of it, if any). It writes only its own folders and merges
`settings.json`. This is tested on a clean machine: fingerprints of those files before and after two
installs and a run of every hook are compared.

**What runs on a schedule, and the one thing that goes online:** the installer adds one marked block to your
crontab (supervisor, reminders, quota, reports, stats, a daily copy of your chats; `--no-cron` skips it, `--prune-cron`
removes blocks of deleted installs). The chat copy goes to `~/.claude-backups/<date>/` at 03:10 (unchanged files
share disk space) and deletes nothing unless you pass `--enable-cleanup`; a daily auto-commit of your working folder
is `--with-git-snapshot`. One job uses the network: `scripts/quota_status.py` reads your Claude Code login
(`~/.claude/.credentials.json`, read only, never refreshed) and asks Anthropic's usage endpoint how much of your
plan is used, at most once every 5 minutes. Jobs that run a model and spend your quota (daily memory
consolidation, correction stats) are off unless you pass `--with-consolidation`.

Want it for one project only: say `--project <path>` instead of `--user`; the agents' working folder (agent
folders, mistakes journal) then goes to `~/claude-workspace/<project name>`, outside your repo (`--workspace <path>`
to choose another place). The optional extras (system
packages for PDF/HTML extraction, the Telegram bot) are off by default; ask the agent for them separately.

**Updating** as new layers land: `git pull && ./install.sh` again. Your memory, your own code lessons, your
permissions, env, model and your own hooks in `settings.json` are kept (only the hook entries that point
into the installed `hooks/` are replaced). If you edited `CLAUDE.md`, it is kept and the new version is
written next to it as `CLAUDE.md.new`. Every replaced file is also backed up as `*.bak-<timestamp>`.

**Platforms:** Linux, macOS and Windows (bash + Python 3.9 or newer). The mechanisms also call `timeout` and
`crontab`, and `flock` / `setsid` where they exist (without them: `gtimeout` or perl's alarm, a mkdir lock, a reader
started without setsid). On a stock macOS (/bin/bash 3.2, BSD `grep`, `sed`, `stat`, `date`) the scripts take the
portable branch of `lib/ccm_compat.sh` and keep to bash 3.2 syntax (`tests/bash3-compat-test.py` checks it); macOS 13
or newer is needed for `readlink -f`. Recommended all the same: `brew install bash coreutils` - `install.sh` then starts
the hooks and the scheduled `.sh` jobs through Homebrew's bash by its full path. `install.sh` and `check-install.py`
name each missing command and what stops without it.

On **Windows**, run `./install.sh` in Git Bash (Git for Windows; Claude Code on Windows runs its hooks there too).
There `python3` is often the Microsoft Store stub, so the installer takes the first working one of `python3`,
`python`, `py -3`, writes it into the hook commands, and puts a `python3` that runs it into `<install dir>/lib/pyshim/`
(the hooks and the agent's Bash commands find it first). Paths are written as `C:/...`, which both Git Bash and Python
read. Windows has no cron: the installer prints the scheduled jobs as `schtasks` commands; `./install.sh --user
--schedule-windows` registers them in Task Scheduler as `ccm-<job>` tasks (each runs a small script in
`<install dir>/schedule/` through Git Bash, without a window), and `./install.sh --schedule-windows --uninstall`
removes every `ccm-*` task.
WSL (`wsl --install`, then everything inside it) is the Linux route and needs none of this.

**What it sets up today, and what not yet** (as of 2026-11; the goal is the whole private setup with one command, built layer by layer):

| Layer | Installed by `install.sh` today | In the repo, set up by hand | Not in the repo yet |
|---|---|---|---|
| One agent | `CLAUDE.md`, 30 hooks and gates, scripts and `bin/` tools (linked into `~/.local/bin`), 13 skills, 1 subagent (`deep-code-reviewer`), memory template, code lessons, `methodology.conf` (your name, folder, time zone), a marked block in your crontab; a quick check at the end (seconds: every file in place, the supervisor green); `--verify-all` also runs every installed test; the web-search server (asks for Tavily/Exa keys, registers itself) | — | Telegram alerts from the input guard; cleanup of the trash folder is off unless `--enable-cleanup` |
| A swarm of agents | 9 more hooks (briefing watchman: an agent recognised by its name in the first message, briefing re-shown when it changes, unread letters every turn; inbox gate; reminders), inbox tools, `/register-as <Name>`, blocker register and story status, project bootstrap (`new_project.sh`), the shared files from `swarm-template/` copied into your workspace. Off until you list agents in `methodology.conf`: the two Stop gates (open work, unproven status). Only with a flag: the releaser (`--with-releaser`, root) and the git wrapper (`--with-git-guard`) | — | — |
| Upkeep | a supervisor every 15 min with 20 checks (are the hooks, the watchman, reminders, the release queue, the chat copy still doing their job; is an agent stuck on an API error), quota and a daily token report as files, the weekly mistakes-journal review, catalog and broken-link checks, a git history of the mechanisms' own code, a public-repo gate, stats as plain JSON in `~/.claude/stats/`. Findings go to `~/.claude/supervisor/summary.json`, and to an agent's inbox only if you name one in `methodology.conf` | — | — |
| Add-ons, one flag each | `--with-mobile-bot` (Telegram bridge to Claude Code: PIN, an allowlist of users, a gate on what it may run), `--with-offsite-backup` (encrypted restic backup to B2 or S3; nothing is ever deleted from it unless you say so), `--with-agent-browser` (a headless browser agents drive; fetches its engine with npm), `--with-net-change` (change the machine's network with an automatic roll-back unless you confirm), `--with-dashboard` (read-only status page of the agents on 127.0.0.1:8765), `--with-session-hygiene` (long chats slow down and bloat: trims old tool outputs from large inactive chats, never the conversation, and only when last night's chat copy is newer), `--with-reader` (read the agents' documents in a browser, phone included; 127.0.0.1:8001 unless you open it to the network; interface in Ukrainian). Parts that need root are done by each add-on's `setup-*.sh`; without root the installer prints the `sudo` line. Accounts they need: [`docs/accounts.md`](docs/accounts.md) | — | — |

## Layout

| Path | What |
|------|------|
| `CLAUDE.md` | Operating core — behavioral rules loaded into every conversation |
| `hooks/` | Shell/Python hooks on `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PreCompact`, `PostCompact`, `PermissionDenied`, `Stop` |
| `scripts/` | Utilities called from hooks, skills, or directly |
| `skills/` | Slash commands (`/recap`, `/audit`, `/register-as`, `/grill`, `/pulse`, `/dossier`, `/edit`, `/update`, `/verify`, `/quality-loop`, `/fix-findings`, `/decision-log`, `/tldr`) |
| `agents/` | Subagent definitions: `deep-code-reviewer` (read-only reviewer on opus; half of the dual review in `/quality-loop`) |
| `memory-template/` | Seed for `memory/` (trigger index + 4 type examples) |
| `swarm-template/` | Empty shared files for a swarm: mistakes journal with the classes that repeated, agent registry, mechanism catalog, one agent's folder |
| `code-pitfalls/` | Technical lessons already paid for, one file per technology — shown to the agent before it edits that kind of code |
| `mcp/` | Setup notes for MCP servers |
| `addons/mobile-bot/` | Optional Telegram bridge |
| `addons/offsite-backup/` | Nightly encrypted incremental backup to S3-compatible storage (restic + Filebase/R2/B2) |
| `addons/agent-browser/` | Headless browser the agents drive (`br`, `br-ask`) with saved recipes |
| `addons/net-change/` | Network change with snapshot and automatic roll-back unless confirmed |
| `addons/dashboard/` | Read-only local status page of the agents |
| `addons/reader/` | A reader in the browser for the documents agents hand to a human (`--with-reader`) |
| `addons/session-hygiene/` | Trims old tool outputs from large inactive chats, on top of the nightly chat copy (`--with-session-hygiene`) |
| `docs/` | Getting started, accounts, memory system, hooks guide, coding standard, project work, and the rest of the rules |
| `settings.template.json` | Settings template with `__CLAUDE_DIR__` placeholders |
| `install.sh` | Bootstrap |

## CLAUDE.md

The rules every chat works by: [`CLAUDE.md`](CLAUDE.md) (honesty, uncertainty, interaction flow, work that outlives a chat,
permissions, memory, output). The installing agent tells the person what is in it; they are not repeated here.

## hooks

| File | Event | Action |
|------|-------|--------|
| `auto-extract-docs.sh` | PreToolUse on `Read` | Intercepts `.pdf` / `.html`, runs extraction, redirects to `.txt`. PDFs >10 MB → manual-run message. |
| `check-prompt-gap.sh` | UserPromptSubmit | Prepends `[now: <ts> \| gap since previous: <delta>]`. |
| `memory-curation-check.sh` | SessionStart | Weekly `curate_memory.py` run. Silent if clean. |

Plus the hardening layer — gates that block a command (`selfkill-gate`, `sysfile-gate`, `fable-gate`, `memory-write-gate` opt-in, `mistakes-format-gate`), detectors on the finished reply that flag and hint on the next turn (`abbr-guard`, `source-guard`, `strawman-guard`, `link-guard`, `draft-guard`, `cost-guard`, `reply-guard`), Stop gates that keep a reply from ending (`pause-guard`, `proof-guard`: "done" after a code edit with nothing run; `work-guard` and `status-guard` for the agents you list), and helpers around them (`hook-safe` wrapper, `stop-dispatch`, `surface-flags`, `stuck-detector`, `code-pitfalls-hint`, `input-guard`, `source-hint`, `trash-guard`, `order-capture-hint`, compaction steering). One line each, with the event: [`hooks/README.md`](hooks/README.md).

Mobile-bot addon adds two more (no-ops outside the bot):
- `addons/mobile-bot/hooks/mobile-restrict.sh` — PreToolUse Write/Edit allowlist
- `addons/mobile-bot/hooks/mobile-audit.sh` — PostToolUse audit log + git commit

## scripts

| File | Action |
|------|--------|
| `pdf-extract.sh <pdf> [--images] [--dpi=N]` | PDF → `.txt` (full) + `.meta.txt` + `.pages/p####.txt` + optional `.images/p####.png`. Idempotent. |
| `html-extract.sh <html>` | HTML → `.txt` via `lynx -dump`. Plain text. |
| `backup-chats.sh` | Daily rsync copy of Claude Code transcripts with hard-link dedup. Scheduled by `install.sh` (03:10); deletes nothing unless `--enable-cleanup`. |
| `daily-git-snapshot.sh [REPO]` | Auto-commit uncommitted changes in REPO. Scheduled only with `install.sh --with-git-snapshot`. |
| `curate_memory.py` | Memory health: orphans, broken links, unresolved wikilinks. Exit 0 clean, 1 with findings. |
| `recap_extract.py` | Extract user/assistant messages since last compaction boundary. Called by `/recap`. |
| `proof_report.py run --sid <id> -- <cmd>` | Run a check and append its exit code to the session's report, which `hooks/proof-guard.py` counts as a run. Used by `/verify`. |
| `verify_prompt.py --note … <changed paths>` | The task for the checking subagent: the project gate from `release.toml`, the changed files, every command through `proof_report.py`. Used by `/verify`. |
| `cross-review.sh --git <range>` | Independent review of a diff by a different model (fresh `claude -p`, read-only tools). See `docs/coding-standard.md` §2.1. |

System deps: `poppler-utils`, `lynx`, `pandoc`, `ffmpeg` (for addon video).

## skills

| Skill | Action |
|-------|--------|
| `/recap` | Commit a session's important parts to memory *before* `/compact` flattens them (native compaction is lossy by design). Distills the dialogue since the last compaction boundary → `memory/<topic>.md` + `episodic/YYYY-MM.md`. Run before compacting, or whenever something worth keeping surfaced. |
| `/verify` | Check your change with a subagent on sonnet: it runs the project gate and the tests of the changed files through `proof_report.py`; proof-guard counts the subagent as a run only by that report (exit codes, not words). |
| `/audit` | Sweep `CLAUDE.md` + `memory/` + `skills/` for contradictions, persona drift, cognitive overload, semantic ambiguity, orphaned references, stale facts. Reports only — doesn't auto-fix. |

## memory layout

```
memory/
├── MEMORY.md           # trigger index, always loaded
├── episodic/YYYY-MM.md # session log
└── <type>_<topic>.md   # one file per topic
```

Four types: `user`, `feedback`, `project`, `reference`. Each file has frontmatter (`name`, `description`, `metadata.type`) and uses `[[name]]` wikilinks to connect to others.

See `memory-template/README.md` and `memory-template/examples/`.

## After install

- Hooks run automatically in new sessions.
- Slash skills are available: `/recap`, `/audit`, `/register-as`, `/grill`, `/pulse`, `/dossier`, `/edit`, `/update`, `/verify`, `/quality-loop`, `/fix-findings`, `/decision-log`, `/tldr`.
- Edit `~/.claude/CLAUDE.md` to change the operating core.
- Edit `~/.claude/memory/MEMORY.md` to add trigger pointers.

## Compatibility

- Claude Code CLI on Linux, macOS and Windows.
- Bash; on Windows, Git Bash (or WSL).

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
