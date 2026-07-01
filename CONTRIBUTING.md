# Contributing

Additions and refinements welcome. Read `CLAUDE.md` and `docs/philosophy.md` first — that's the spine everything hangs off of.

## What fits

- **New hooks** for lifecycle events not yet covered.
- **New skills** (folder in `skills/`) with a clear `SKILL.md` following the same shape as `recap` and `audit`.
- **New scripts** utilities that hooks or skills genuinely need.
- **New docs** — deeper how-tos, examples, integration guides.
- **Rules** — additions or refinements to `CLAUDE.md`, with a `Why` in the PR description.

## What doesn't fit

- Personal setup files (your own memory content, project files, credentials).
- Vendor-specific integrations that only work for one deployment.
- Features that duplicate what Claude Code already ships.
- Anything that requires paid third-party services without a free tier or clearly-marked opt-in.

## Style

- Dry documentation. Tables over prose. No pitch language ("elegant", "powerful", "revolutionary").
- Rules and skills lead with the rule, then `Why:`, then `How to apply:` where structure fits.
- Bash scripts: `set -euo pipefail`, header comment with usage, idempotent when possible, `chmod +x`.
- Python scripts: no external deps if avoidable (stdlib only). Header docstring with usage.
- No emojis in code or docs unless the file already uses them.
- Line count budget: if a doc is over ~150 lines, split it.

## Testing

- Shell scripts: pass `shellcheck` (CI runs it on PR).
- Hooks: include a manual simulation example in the PR description, e.g.:
  ```bash
  echo '{"tool_name":"Read","tool_input":{"file_path":"/tmp/test.pdf"}}' | ./hooks/your-hook.sh
  ```
- Skills: no automated test — include a sample invocation and expected agent behavior in the PR.

## PR checklist

- [ ] Change explained in one paragraph. Why, not just what.
- [ ] Added file listed in the relevant README (root `README.md` + subdir README).
- [ ] Existing behavior not silently broken.
- [ ] No secrets, credentials, personal file paths (`/home/<your-name>/...` should be `$HOME/...` or `$CLAUDE_METHODOLOGY_DIR`).
- [ ] Shellcheck passes locally: `shellcheck path/to/your-script.sh`.

## Discussion first

For significant changes (new rule in `CLAUDE.md`, new lifecycle hook pattern, restructure of memory format), open an issue first with the proposal. Small additions and fixes can go straight to PR.
