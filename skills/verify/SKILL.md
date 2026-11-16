---
name: verify
description: Check your own change with a subagent on a cheaper model (sonnet) - it runs the project gate (release.toml -> test) and the tests of the changed files through proof_report.py, which writes the report proof-guard counts, and returns a short summary. Use when you finished a code change and want proof before saying "done", or when the user says "/verify", "check it with a subagent", "run the tests in a subagent".
---

# verify - check it with a subagent

Why: running tests and reading their output eats the context and the quota of an expensive model. A subagent on sonnet
does it cheaper. proof-guard counts it as a run **only** with the report file `proof_report.py` writes
(`~/.claude/proof-reports/<session id>.jsonl`, or `CCM_PROOF_REPORTS_DIR` in `methodology.conf`): exit codes, not words.

## Steps

1. Build the task (in Bash, where `$CLAUDE_CODE_SESSION_ID` is set):
   ```bash
   python3 "${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/scripts/verify_prompt.py" --note "<what changed and what should work, one line>" <changed files or the project folder>
   ```
   The project gate comes from the nearest `release.toml` up from each path (its `test` command).
2. Call `Agent` with **`model: "sonnet"`** set explicitly (without it the subagent runs on your model),
   `subagent_type: "general-purpose"`, `prompt` = the output of step 1, word for word.
3. Read the summary. `SUMMARY: all rc 0` -> you may say "done" with that proof (proof-guard lets it through: the report
   is newer than your last edit). `RED` -> fix it yourself and run the skill again. The session's report:
   `python3 "${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/scripts/proof_report.py" show`.

## When not to

- Decisions, the talk with the human, edits agreed in the chat stay with you; the subagent only checks.
- One to three short commands (one test that takes seconds): run them yourself, the subagent costs more.
- You edited code after the check: the report is now older than the edit and proof-guard does not count it. Run it again.
