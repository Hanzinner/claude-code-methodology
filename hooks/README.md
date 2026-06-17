# hooks

Shell hooks run by the Claude Code harness. All resolve their install path via `$CLAUDE_METHODOLOGY_DIR` (set by `install.sh`), falling back to `~/.claude`.

| File | Event | Action |
|------|-------|--------|
| `auto-extract-docs.sh` | PreToolUse on `Read` | If file is `.pdf`/`.html`, run extraction and redirect agent to the `.txt` output. PDFs >10 MB get a manual-run message instead. |
| `check-prompt-gap.sh` | UserPromptSubmit | Prepend `[now: <ts> \| gap since previous: <delta>]`. |
| `memory-curation-check.sh` | SessionStart | Run `scripts/curate_memory.py` at most weekly. Silent if clean; injects findings if not. |

See `docs/hooks-guide.md` for writing your own.
