# hooks

Shell and Python hooks run by the Claude Code harness. Those that read other files resolve the install path via `$CLAUDE_METHODOLOGY_DIR` (set by `install.sh`), falling back to `~/.claude`; state and logs go under `~/.claude/`.

| File | Event | Action |
|------|-------|--------|
| `auto-extract-docs.sh` | PreToolUse on `Read` | If file is `.pdf`/`.html`, run extraction and redirect agent to the `.txt` output. PDFs >10 MB get a manual-run message instead. |
| `check-prompt-gap.sh` | UserPromptSubmit | Prepend `[now: <ts> \| gap since previous: <delta>]`. |
| `memory-curation-check.sh` | SessionStart | Run `scripts/curate_memory.py` at most weekly. Silent if clean; injects findings if not. |

## Hardening hooks

These turn a discipline-dependent rule into a mechanical gate. Each exists because a rule that relied on the agent *remembering* something failed in practice. See [`docs/measurement-and-proof.md`](../docs/measurement-and-proof.md) for the "rule → mechanism" reasoning.

| File | Event | Action |
|------|-------|--------|
| `memory-write-gate.py` | PreToolUse on `Write`/`Edit` | A memory file must carry `source:` + `verified:` frontmatter, or the write is blocked. Stops a guess hardening into a "fact". **Deliberately fail-CLOSED, and opt-in:** not wired in `settings.template.json` — add it yourself (unwrapped), and add `source:`/`verified:` to your memory frontmatter first, or it blocks your own `/recap`. |
| `precompact-instructions.sh` | PreCompact | Rewrites the *compaction* instructions — appends "quote the load-bearing specifics verbatim" to the tail of the compaction prompt, where it's most influential. The forgetting filter is an instruction, not a law. |
| `postcompact-archive.sh` | PostCompact | Files the full compaction summary to `~/.claude/compaction-log/` — the summary outlives the session. |
| `permission-denied-hint.sh` | PermissionDenied | Injects "stop, don't hop channels — your model of what's allowed is wrong" + a nudge to capture the correction that often follows a denial. |
| `reply-guard.py` | Stop | Detects a fabricated user turn ("User: …" outside a code block) in the last assistant message; logs + flags it. A detector, not a preventer. |
| `stop-dispatch.sh` | Stop | One Stop slot, several isolated consumers (fail-open); register more branches here. A branch's stdout is discarded, so branches report through files. A branch that must *block* Stop needs its own stdout passed through — give that to one branch only. |
| `hook-safe.sh` | wrapper | Wraps any hook: fail-open + timeout + a central error log, so a broken hook can't silently block input. (Don't wrap the fail-CLOSED gate above.) |
| `stuck-detector.py` | PostToolUse + PostToolUseFailure on `Bash` | 3 failed Bash calls in a row → "stop, look up how it's done". Written rule never followed; the hook is. |
| `proof-guard.py` | Stop | A completion claim after code edits with no successful run → log + flag file. Calibrate with `--calibrate`. |
| `surface-flags.sh` | UserPromptSubmit | The reader for the files above: shows the proof-guard and reply-guard flags once, and new lines of `~/.claude/hook-errors.log`. Without it those detectors write into files nobody opens. |
| `code-pitfalls-hint.py` | PreToolUse on `Edit`/`Write`/`Bash` | Shows headings of `code-pitfalls/<topic>.md` before the agent edits that kind of code (by extension; lock/thread code → `concurrency.md`). Bash commands: `git` → `git.md`, `ssh`/`qemu` → `vm.md`, `adb` → `android.md`. |
| `selfkill-gate.py` | PreToolUse on `Bash` | Denies `pkill -f` (it matches the agent's own shell) and detached "wait alarms" the harness can't see. |
| `sysfile-gate.py` | PreToolUse on `Bash` | Denies destructive commands on `/dev`, `/boot`, `/proc`, `/sys` and critical `/etc` files (an `rm -f /dev/null` once broke git and ssh for everyone). |
| `trash-guard.py` | PreToolUse / PostToolUse on `Bash` | "Delete" means move to `CCM_TRASH_DIR`; warns whoever grows the trash past `CCM_TRASH_LIMIT_GB`. Cleanup only with `--enable-cleanup`. |
| `mistakes-format-gate.py` | PreToolUse on `Write`/`Edit`, PostToolUse on `Bash` | Keeps the mistakes journal machine-readable: every new entry has the dated heading and a `**Status:**`. |
| `fable-gate.py` | PreToolUse on `Agent`/`Workflow` | A subagent must name its model; models listed in `CCM_FORBIDDEN_SUBAGENT_MODELS` are denied. |
| `websearch-to-tavily.sh` | PreToolUse on `WebSearch` | Steers search to the rotating search MCP (`mcp/search_mcp.py`); built-in WebSearch only when every provider is on cooldown. |
| `input-guard.py` | PostToolUse on any tool | Makes text appended to the agent's input that the human didn't write visible (tagged reminders, instructions inside fetched files). |
| `source-hint.py` | PostToolUse on web search | A query about law (visa, tax, residency) → "state eligibility only from an official page you opened" + the official addresses found. |
| `order-capture-hint.sh` | UserPromptSubmit | In coordinator sessions (`CCM_COORDINATOR_PATTERN`): an order for work → "put it in the queue now". Needs agent identity (layer 2). |
| `pause-guard.py` | Stop (via stop-dispatch) | Blocks a reply that ends with "shall we stop for today?" / "get some rest". The human decides when to stop. |
| `abbr-guard.py` | Stop (via stop-dispatch) | Flags abbreviations used without expansion; terms in `CCM_GLOSSARY` count as known. |
| `source-guard.py` | Stop (via stop-dispatch) | Flags a fact about the world (money, law, eligibility) stated without a primary source. |
| `strawman-guard.py` | Stop (via stop-dispatch) | Flags restating the human's position in a weaker form and assertions about them nobody gave. |
| `link-guard.py` | Stop (via stop-dispatch) | Flags paths to existing files written as plain text instead of clickable links. |
| `draft-guard.py` | Stop (via stop-dispatch) | An English draft written in the human's name with filler → "check it against the drafting guide" (`CCM_DRAFTING_GUIDE`). |
| `cost-guard.py` | Stop (via stop-dispatch) | One line when a turn ate an unusual share of quota, so the agent notices waste. Silent until `CCM_COST_UNITS_PER_PCT` is set. |

## Layer 2 — several agents

Hooks of the swarm (named agents, one folder each, talking through `inbox.md` files). All are wired in `settings.template.json` (the Stop ones inside `stop-dispatch.sh`). Most are silent unless the session has an agent identity (`~/.claude/agent-identity/<session_id>`, written by `briefing-watchman.sh`); two are OFF until a `methodology.conf` key ("several agents" section) names the agents.

**Inboxes**

| File | Event | Action |
|------|-------|--------|
| `foreign-inbox-gate.py` | PreToolUse on `Bash`/`Write`/`Edit` | Denies any write to an `<agents dir>/**/inbox.md` (foreign or your own) that bypasses `inbox_post.sh` / `inbox_done.sh`: `Edit`/`Write`, `>`/`>>`, `tee`, `sed -i`, interpreter writes. Also denies those two scripts called with the text in single quotes (an apostrophe breaks the letter). Code that takes the inbox lock is allowed. |
| `inbox-delta-hint.py` | PostToolUse on any tool | A new `- [ ]` item arrived in the agent's own "## New" mid-turn -> a hint (first line only, max 3) on the next tool call. Throttled (`INBOX_DELTA_THROTTLE`, default 60 s). Hint only. |
| `inbox-wait-timeout.py` | PreToolUse on `Bash` | A bare background call of `inbox_wait.sh <agent> [--until/--max ...]` gets `timeout` 55 min added (`INBOX_WAIT_TIMEOUT_MS`) via an "allow" with updated input. Glued or foreground calls are left alone. |

**Watchman and identity**

| File | Event | Action |
|------|-------|--------|
| `briefing-watchman.sh` | UserPromptSubmit | Per prompt of an agent session: delivers deferred letters (`inbox-pending/`); resolves and stores the agent's identity; creates a missing `inbox.md` and TODO files; re-injects `briefing.md` when its content hash changed; lists open inbox items every prompt (flags old and malformed ones); with a `.watchlist` file in the agent's folder shows the delta of those shared files; optional dead-man line (`CCM_SUPERVISOR_HEARTBEAT`, off when empty). Hint only, fail-open. Supersedes the old `multi-agent/` port. |
| `agent-status.py` | PostToolUse on any tool + Stop (detector branch) | Writes `~/.claude/agent-status/<agent>.json`: `WORKING` after a tool call, `DONE` at Stop, `ASK` (with the text) if the last reply holds `ASK: <question>`. A dashboard reads the file; nothing is shown to the agent. |

**Alarms and reminders**

| File | Event | Action |
|------|-------|--------|
| `remind-hint.sh` | UserPromptSubmit | The human asks to be reminded ("remind me in an hour") -> tells the agent to use `scripts/remind.py` instead of promising. Ukrainian phrases too when `CCM_LANG_EXTRA` has `uk`. Hint only. |
| `remind-guard.py` | Stop (via stop-dispatch, detector) | The agent promised a reminder in its reply but did not run `remind.py` in that turn (or the run failed) -> flag shown once on the next prompt. Ignores quotes, code, negations, questions. A detector, not a block. `--calibrate [days]`. |

**Guards**

| File | Event | Action |
|------|-------|--------|
| `work-guard.py` | Stop (via stop-dispatch, **blocking**) | An agent may not stop with an unprocessed inbox item, with open runnable TODO items and no `STATE:` line, or without a live `inbox_wait.sh` alarm. Also demands a recap at 700k tokens of context. Max 12 blocks in a row, then lets go. Per-agent alarm mode `off`/`once`/`auto`/`always` in `CCM_ALARM_MODE_DIR`. **OFF until `CCM_WORK_GUARD_AGENTS`** (a file, one agent per line) is set; only listed agents are touched. |
| `status-guard.py` | Stop (via stop-dispatch, **blocking** + flag) | A coordinator that states a story's state ("done", "not started") or tells the human "waiting on you" without running `story_status.py` / `blockers.py` / `git log` in the same turn -> blocked once per stop. "Waiting for X" with no blocker number `B<n>` -> flag on the next prompt. **OFF until `CCM_STATUS_GUARD_AGENTS`** (comma-separated) is set. |

See `docs/hooks-guide.md` for writing your own.
