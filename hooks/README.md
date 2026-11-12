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

See `docs/hooks-guide.md` for writing your own.
