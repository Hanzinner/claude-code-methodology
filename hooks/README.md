# hooks

Shell hooks run by the Claude Code harness. All resolve their install path via `$CLAUDE_METHODOLOGY_DIR` (set by `install.sh`), falling back to `~/.claude`.

| File | Event | Action |
|------|-------|--------|
| `auto-extract-docs.sh` | PreToolUse on `Read` | If file is `.pdf`/`.html`, run extraction and redirect agent to the `.txt` output. PDFs >10 MB get a manual-run message instead. |
| `check-prompt-gap.sh` | UserPromptSubmit | Prepend `[now: <ts> \| gap since previous: <delta>]`. |
| `memory-curation-check.sh` | SessionStart | Run `scripts/curate_memory.py` at most weekly. Silent if clean; injects findings if not. |

## Hardening hooks

These turn a discipline-dependent rule into a mechanical gate. Each exists because a rule that relied on the agent *remembering* something failed in practice. See [`docs/measurement-and-proof.md`](../docs/measurement-and-proof.md) for the "rule → mechanism" reasoning.

| File | Event | Action |
|------|-------|--------|
| `memory-write-gate.py` | PreToolUse on `Write`/`Edit` | A memory file must carry `source:` + `verified:` frontmatter, or the write is blocked. Stops a guess hardening into a "fact". **Deliberately fail-CLOSED.** |
| `precompact-instructions.sh` | PreCompact | Rewrites the *compaction* instructions — appends "quote the load-bearing specifics verbatim" to the tail of the compaction prompt, where it's most influential. The forgetting filter is an instruction, not a law. |
| `postcompact-archive.sh` | PostCompact | Files the full compaction summary to `~/.claude/compaction-log/` — the summary outlives the session. |
| `permission-denied-hint.sh` | PermissionDenied | Injects "stop, don't hop channels — your model of what's allowed is wrong" + a nudge to capture the correction that often follows a denial. |
| `reply-guard.py` | Stop | Detects a fabricated user turn ("User: …" outside a code block) in the last assistant message; logs + flags it. A detector, not a preventer. |
| `stop-dispatch.sh` | Stop | One Stop slot, several isolated consumers (fail-open); register more branches here. |
| `hook-safe.sh` | wrapper | Wraps any hook: fail-open + timeout + a central error log, so a broken hook can't silently block input. (Don't wrap the fail-CLOSED gate above.) |

See `docs/hooks-guide.md` for writing your own.
