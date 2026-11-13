# scripts

Utilities called from hooks or directly. All idempotent. Paths are set per script through env vars named in each header (`CLAUDE_MEMORY_DIR`, `CLAUDE_PROJECT_TRANSCRIPT_DIR`, `BACKUP_DIR`, …); defaults live under `~/.claude`.

## Document extraction

| Script | Action |
|--------|--------|
| `pdf-extract.sh <pdf> [--images] [--dpi=N]` | PDF → `.txt` (full) + `.meta.txt` + `.pages/p####.txt` + optional `.images/p####.png`. |
| `html-extract.sh <html>` | HTML → `.txt` via `lynx -dump` (plain text). |
| `html-to-md.sh <html>` | HTML → `.md` via `pandoc` (GFM, preserves structure). |

System deps: `poppler-utils`, `lynx`, `pandoc`.

## Memory & persistence

| Script | Action |
|--------|--------|
| `backup-chats.sh` | Daily rsync backup of Claude Code transcripts with hard-link dedup. Cron at 3 AM. |
| `daily-git-snapshot.sh [REPO]` | Auto-commit uncommitted changes in REPO. Cron at 4 AM, or every N minutes. |
| `curate_memory.py` | Memory health (orphans, broken links, unresolved wikilinks). Exit 0 if clean, 1 with findings. |
| `recap_extract.py` | Dump user/assistant messages since the last compaction boundary. Used by `/recap`. |
| `claude_machine.py` | Run `claude -p` from a script without saving a session, with cost accounting. |
| `episodic_append.sh` | The one way to add to the "when did we do X" log: under a lock, so two agents don't swallow each other's entries. |
| `extract_scenes.sh` | Scene-change frames from a video (URL via yt-dlp, or a file); used by `/edit`. |
| `rename_session.py` | Set a custom title on a Claude Code session. |
| `transcript_tail.py` | The transcript lines of the last turn, without reading the whole file (Stop checks share it). |
| `ai-studio-to-md` | Convert Google AI Studio JSON exports to Markdown. |

## Layer 2 — several agents

Scripts of the swarm. Agent names are folder names under `CCM_AGENTS_DIR`; project folders match `CCM_PROJECTS_GLOB` (default `Project-*`). Settings are in the "several agents" section of `methodology.conf`.

### Inboxes

| Script | Action |
|--------|--------|
| `inbox_post.sh <agent> <text>` | The only write path into an inbox: under a lock, inserted right after "## New", no duplicates, checked from disk after the write. Text may come on stdin. Busy inbox -> the letter waits in `inbox-pending/` (delivered by the watchman). After delivery runs `agent_listening.py`. |
| `inbox_done.sh <agent> <substring> [entry]` | Closes an item in your own inbox under the same lock: moves it from "## New" to "## Processed". Refuses when the substring matches several different items. |
| `inbox_resolve.sh <agent\|path>` | Prints the addressee's `inbox.md`: path, folder `<name>`, `<name>-agent`, or an alias from `.aliases`. Ambiguous -> exit 2 with candidates. |
| `inbox_lib.sh` | Shared helpers (section names, lock). Sourced by the three above, never run. |
| `inbox_wait.sh <agent> [--until HH:MM] [--max S]` | The agent's alarm clock: started in the background, exits when a new item lands in "## New", at `--until`, or after 55 min (the ceiling). The exit wakes the same tab. Mode per agent in `CCM_ALARM_MODE_DIR`: `off`/`once`/`auto`/`always`. |
| `agent_listening.py <agent>` | After a delivery: one warning line if the addressee has no live alarm and has been idle for more than 5 min. Always exit 0. |
| `agent_tab.py <agent> [--json]` | The live tab of an agent for `SendMessage`: name and `idle`/`busy`; exit 1 when none. |

### Alarms and reminders

| Script | Action |
|--------|--------|
| `remind.py <agent> <when> <text>` | A reminder as a letter in the agent's inbox (`15m`, `2h`, `18:30`, a date). `--list`, `--cancel <id>`, `--fire` (cron, every minute; the installer adds the line). Survives reboots; late ones are marked. |
| `claim.sh acquire\|check\|release <key>` | The one lock for the swarm, always with a TTL (default 30 min) and an owner, so a dead process cannot deadlock the rest. Needs `flock`. |

### Blockers and stories

| Script | Action |
|--------|--------|
| `blockers.py` | Blockers as rows in `<project>/BLOCKERS.md`, each with a check command. `run` (cron every 15 min, installer adds it) runs only approved checks, clears blockers, flips story lines in `ROADMAP.md` and posts letters. Also `add`, `approve`, `clear`, `list [--json]`. A hand-edited command is not run until `approve`. |
| `blocker_add.sh` | Wrapper for `blockers.py add`: whoever hits the wall registers it; prints the number `B<n>`. |
| `story_status.py <project> <S-code>` | A story's state computed from the roadmap line, blockers, TODOs and inboxes, commits and code files. What `status-guard.py` wants run before a state report. |
| `take_task.sh <project> <story>` | "I take this story": writes it to `~/.claude/task-taken/<session id>`. For now a journal; nothing enforces it. |

### Projects and releases

| Script | Action |
|--------|--------|
| `new_project.sh (--own-repo [--profile web\|game\|tool] \| --no-code) <Name> [agent...]` | Starts a project: `release.toml`, `ROADMAP.md`, `BLOCKERS.md`, agent folders, first commit (own repo). Default agents `<Name>-HQ`, `<Name>-Dev`. |
| `releaser.py` | Release queue run by cron: per project a separate system user merges the oldest `.ready` marker into its own clone, runs the gate from `release.toml`, and on green fast-forwards `master`. Red -> `master` untouched, letter to the lead. Commands: `run`, `approve` (root), `ready <agent> "<what>"`, `status`. **Only with `install.sh --with-releaser`.** |
| `setup-releaser.sh` | System side of the above (root): the `releaser` user, state folders, optional sudoers line (`--sudo-cmd`), `/etc/cron.d/ccm-releaser` with `--cron` (releaser every 5 min, drift nightly, stale hourly). `--dry-run`. Run by `--with-releaser`. |
| `project_drift.py` | Nightly: red line for each project with code that lacks a parseable `release.toml`, a gate command, or a recent green release. Writes `drift.json`. Exit 1 when any is red. |
| `repo_stale.py` | Hourly: uncommitted files older than 24 h in a project's own repo -> one letter per day to its lead. Commits nothing. |
| `wt_deliver.sh <agent>` | Delivers an agent's worktree into `master`: merge master in, test, check file ownership against `<project>/OWNERS`, `--ff-only`, build. Refuses at every step without moving `master`. Settings in `<project>/deliver.conf`. |
| `standard_version.py current\|hint\|lag` | Compares the coding standard's version with the `Standard: vN read` line in an agent's briefing; `hint` prints the changelog entries it missed. Nothing in this repo calls it yet. |
| `setup-git-guard.sh` | Symlinks `bin/git-guard` as `git` into `~/.local/bin` (or `--system`); `--rc-file` adds a PATH block, `--uninstall`, `--dry-run`. **Only with `install.sh --with-git-guard`.** |

## cross-review.sh

Independent review by a **different** model: a fresh `claude -p` with `--tools "Read,Grep,Glob"` reviews a diff or files against an optional requirements table and a "why" log. Self-review by the same model found 5 defects where other models found ~20 more. Usage: `cross-review.sh --model sonnet --git HEAD~1..HEAD`.

## bin/ (linked into `~/.local/bin`)

| Tool | What it does |
|---|---|
| `creds` | Read credentials from the one store (`CCM_SECRETS_DIR`) instead of copying them next to the work. |
| `rename-ref` | Rename a `.md` file and rewrite every reference to it. |
| `secret-scan` | Find secrets in the added lines of a diff, or in whole files. |
| `swap-live` | Replace a live script or hook atomically with a checked copy, keeping its permissions. |
| `git-guard` | A `git` wrapper that blocks destructive verbs (`reset --hard`, `clean -f`, `branch -D`, `checkout -f`, history rewrites...) in the shared workspace repo, exit 88. Project repos of their own get the same, plus no direct moves of `master` when they sit under the release queue. With `CCM_GIT_GUARD_BLOCK_REMOTE=1` also blocks `remote add`/`set-url` and any push in the shared repo (off by default). **Only with `install.sh --with-git-guard`** (via `setup-git-guard.sh`). |
