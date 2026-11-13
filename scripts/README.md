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
| `standard_version.py current\|hint\|lag` | Compares the coding standard's version with the `Standard: vN read` line in an agent's briefing; `hint` prints the changelog entries it missed. Called by `briefing-watchman.sh` when an agent's `.watchlist` has `CODING-STANDARD.md`. |
| `setup-git-guard.sh` | Symlinks `bin/git-guard` as `git` into `~/.local/bin` (or `--system`); `--rc-file` adds a PATH block, `--uninstall`, `--dry-run`. **Only with `install.sh --with-git-guard`.** |

## Layer 3 — upkeep and supervision

Watchers, catalogs, reports and statistics. Who gets a letter when something breaks is set in the "upkeep and supervision" section of `methodology.conf` (`CCM_INFRA_AGENT`, `CCM_MISTAKES_KEEPER`, ...); an empty value = no letter, the finding stays in a log or a JSON file. Unless a row says otherwise, a script only reads and reports (letters go through `inbox_post.sh`). "cron" = a line `install.sh` writes into the crontab (not with `--no-cron`); "supervisor" = an entry in `config/supervisor-checks.template.json`.

### Supervisor

| Script | Action |
|--------|--------|
| `supervisor.py [--checks F] [--state DIR] [--dry-run] [--only NAME] [--init TEMPLATE]` | Runs a registry of functional checks (`http`, `tcp`, `cmd`, `fresh`, `journal`, `hooks`, `system`). Red check -> a letter to its `owner` (the same alarm not again for 6 h); severity `human` also puts a one-line flag into every live session. A check that cannot measure (rc 3, 126, 127, a traceback) is reported once to `CCM_INFRA_AGENT`, not as an outage. Stays quiet after machine downtime. Writes `summary.json` and `heartbeat` in its state dir. Restarts a systemd unit only for a check that names a `service` (none in the template). Cron every 15 min. |
| `config/supervisor-checks.template.json` | The check list. `supervisor.py --init <file>` copies it to `<state>/checks.json`; `__CLAUDE_DIR__` and `__HOME__` are filled in on read. Entries whose file does not exist yet are skipped (`only_if_exists`). |
| `checks_lint.py [--checks FILE]` | Lints the registry: a `fresh` check on a `*.log` file needs a `fresh_ok` reason (a log is written on failures too). rc 1 lists offenders, rc 3 when the registry is unreadable. Supervisor. |
| `watchman_alive_check.py` | Chats written to within 20 min -> the briefing watchman must have run within 90 min (its `heartbeat` file). Skipped until that file exists. Supervisor. |
| `hook_timeouts_check.py` | Red when `hook-errors.log` holds more than 3 `[TIMEOUT` lines from the last hour. Supervisor. |
| `reminders_stuck_check.py` | Red when a `remind.py` reminder is overdue by more than 10 min (the per-minute `--fire` cron does not deliver). Supervisor. |
| `releaser_check.py` | Red when a `*.ready` marker has waited more than 15 min; green when the releaser is not installed. Supervisor. |
| `api_silence_check.py` | Red when, within 20 min, a session shows a synthetic API/OAuth/rate-limit error right after a human message: the model was never called, so no Stop gate can see it. Supervisor, severity `human`. |
| `tab_stuck_check.py` | An agent's tab whose last reply is a synthetic service error, older than 10 min, with no live alarm. Needs `CCM_WORK_GUARD_AGENTS` (empty = off). Writes one line per case into the agent's `human-TODO.md` (the one place it changes anything). Supervisor. |
| `presence_check.py` | Is the human at the machine: a fresh prompt (< 15 min), else the idle time printed by `CCM_PRESENCE_CMD`. rc 0 present, 1 away, 2 unknown (fail-closed). For things that push messages. Manual; the template entry is disabled. |
| `cron_state_check.py <name> <max_hours>` | Red when a job run by `catchup-run` has a `.fail` file or its last success is older than `max_hours`; machine downtime (from `journalctl --list-boots`) is subtracted. Supervisor: the template entry `example_job` is disabled, copy it per job. |
| `chat_backup_check.sh` | The last `backup-chats.sh` line in the log is a success, not older than 26 h, and today's folder holds a `.jsonl`. Manual: neither cron nor the template runs it (it expects the backup cron line to log to `~/.claude/logs/chat-backup.log`). |

### Mistakes journal and catalogs

| Script | Action |
|--------|--------|
| `mistakes_review.sh` | Counts OPEN entries in the mistakes journal and sends one letter to `CCM_MISTAKES_KEEPER` ("look for repeats"). No OPEN = silent; no keeper = a log line only. Cron weekly (Sun 12:35); supervisor checks its log. |
| `mistakes_review_catchup.sh` | Runs the review when its log is older than 7 days (the machine was off). Cron `@reboot` after 300 s. |
| `library_check.py [--dry]` | Checks `LIBRARY.md` against reality: paths exist, every script in hooks and crontab has a line, `{hook:Event}` tags match `settings.json`, no duplicate numbers, new scripts without a mention. One letter to `CCM_LIBRARY_KEEPER` (plus one to the author of an unmentioned script); `--dry` only prints. Cron daily 12:52. |
| `swarm_tools_check.sh` | A script in `scripts/` or an executable in `bin/` not named in `SWARM-TOOLS.md` -> one letter to `CCM_SWARM_TOOLS_OWNER` (empty = log only; the same list is not posted twice). No catalog = exit 0. Cron daily 12:50. |
| `broken_links.py [--all]` | Sweep of broken `](...md)` links over the workspace's markdown, with a "moved to" candidate. `CCM_BROKEN_LINKS_SKIP` skips folders. Read-only. Manual. |
| `stats_orphan_docs.py [--dry]` | Documents in an agent's folder named in neither its briefing nor its `*TODO*.md` -> one letter to that agent (at most every few days; paused agents skipped). Writes `orphan-docs.json`. Cron hourly at :45; supervisor checks the file's age. |

### Git and public repo

| Script | Action |
|--------|--------|
| `git_empty_objects_check.sh` | Zero-byte files in the workspace's `.git/objects` (a cut-off write). Does not repair; one letter to `CCM_GIT_KEEPER` per new set. Cron `@reboot` after 120 s; supervisor, severity `human`. |
| `git_snapshot_2fail_check.sh` | Red when the last two results in the `daily-git-snapshot.sh` log (`SNAP_LOG`) are both failures. Manual: neither cron nor the template runs it. |
| `mech_snapshot.sh` | Commits the code of the mechanisms (`scripts/*.sh`, `scripts/*.py`, `hooks/*`, `lib/*.py` by default) into a separate git (`~/.claude/mech.git`, outside the workspace repo). Whitelist only, a blocking pre-commit secret scan, a file that vanished leaves the index but stays in history. A secret or a broken whitelist -> letter to `CCM_MECH_OWNER`. Writes a git repo; deletes nothing. Cron every 10 min; supervisor checks its log. |
| `public_gate.sh <snapshot-dir> \| --selftest` | Gate before a public push; exit 1 forbids it. Checks tracked files and the whole history for Cyrillic, names from `CCM_PUBLIC_GATE_NAMES`, internal files (`CCM_PUBLIC_GATE_INTERNAL`) and secret formats; fewer than 5 files = a broken gate. Runs its own `--selftest` matrix first. `CCM_PUBLIC_GATE_CYRILLIC=1` (the default) fails the gate on any Cyrillic letter in a tracked file, `0` skips that check. Manual. |
| `public_gate_selftest.sh [--check]` | Runs the gate's self-test in a clean environment and logs the result; `--check` is the verdict (green and not older than 26 h). Cron daily 05:25; supervisor runs `--check`. |

### Quota and reports

| Script | Action |
|--------|--------|
| `quota_status.py [--json] [--out FILE] [--line AGENT] [--hours N]` | Session and weekly quota: the real numbers from the account's usage endpoint (read with the CLI's own token, never refreshed), else an estimate from transcripts. Does not call a model. Writes the status file. Cron every minute under `flock`. |
| `quota_real_check.sh` | Status file younger than 10 min, source `api`, real reading not older than 60 min; an expired login while nobody works = quiet. Supervisor. |
| `quota_log_line.py` | Appends one line per run (weekly %, session %, reset time) to `quota-weekly-history.log`. Cron hourly at :07. |
| `token_daily_report.py [--date D] [--print] [--force] [--after H]` | One day's token use and API-equivalent cost as `<date>.md`, `.json` and `latest.md`. Once per day; no model call. Cron hourly at :15 with `--after 8`; supervisor checks `latest.md`. |

### Statistics

All write into `STATS_DIR` (default `~/.claude/stats`).

| Script | Action |
|--------|--------|
| `stats_collect.py` | Working time, tokens, cost, agents and the human's messages (corrections, swearing) from the session logs -> `data.json`. No model call. Cron hourly at :35; supervisor checks the file. |
| `stats_adoption.py` | Whether the rules are used: per agent task-list tags, inbox age, stuck urgent items; the journal's recent entries and old OPEN ones -> `adoption.json`. One letter a day to `CCM_STATS_OWNER` when the journal has unsorted entries. Cron hourly at :40. |
| `stats_projects.py` | Epics and stories read from each project's `ROADMAP.md` -> `projects.json`. rc 1 if a roadmap cannot be parsed. Read-only. Cron every 15 min. |
| `stats_corrections.py [--days N] [--after H]` | Lifts the human's corrections out of the tabs and classes them with a cheap model (`haiku`, through `claude_machine.py`): **spends your quota**. Red = a class without a hand-set verdict, or a "mechanism" class that repeated after its `since`; one letter to `CCM_STATS_OWNER`. **Only with `install.sh --with-consolidation`** (cron hourly at :20, once a day after the set hour). |

### Memory

| Script | Action |
|--------|--------|
| `memory_consolidation.sh [--force]` | Nightly read-only report on the memory corpus from a fresh `claude -p` (`sonnet`, tools `Read,Grep,Glob`): **spends your quota**, once a day, when the human has been quiet 45 min, yesterday was missed, or it is 23:00. Memory is hashed before and after; a change is flagged. Report in `CCM_CONSOLIDATION_DIR`, one letter to `CCM_CONSOLIDATION_KEEPER`. **Only with `install.sh --with-consolidation`** (cron hourly at :20; the gate decides). |
| `prune_watchman_state.sh [--dry-run] [--yes]` | Deletes the briefing watchman's state markers older than `CCM_PRUNE_DAYS` (30). **Deletes, so off by default:** does nothing unless `CCM_PRUNE_WATCHMAN_STATE=1` or `--yes`; `--dry-run` lists. Manual: the installer writes no cron line for it (its header suggests `30 12 * * 0`). |

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
| `catchup-run <name> daily\|weekly\|monthly [--after HH] -- <cmd...>` | Cron with catch-up after downtime: run from cron every hour, it starts the command only when the current day / ISO week / month has no success yet and hour `--after` has come. Records `<name>.ok` / `<name>.fail` (read by `cron_state_check.py`), output goes to a log; rc 75 from the command = "not ready, try later". One run at a time (flock). Not scheduled by the installer: you add the cron line. |
