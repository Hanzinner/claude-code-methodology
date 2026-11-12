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

See `docs/hooks-guide.md` for writing your own.
