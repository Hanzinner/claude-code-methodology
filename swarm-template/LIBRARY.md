# LIBRARY — catalog of shared mechanisms and system documents

> Two failures this prevents: "done but not documented" (someone rebuilds it) and "documented but not done"
> (someone trusts it). **Rule:** you create a shared document or mechanism (hook, cron job, script, skill,
> service) → add its line here in the same turn; rename or delete → fix the line.
> A nightly check should compare this file with the disk, the hook config and the crontab, and send the
> differences to whoever owns this file. (The repo doesn't ship that check; until you build one, check by hand.)

**Line format (machine-readable):** `- <code> [<name>](<path>) — <what it does> {tags}`
**Tags:** `{hook:<Event>}` · `{cron}` · `{tool}` · `{skill}` · `{systemd}` · `{doc}` · `{config}` · `{stale?}` · `{orphan}`

## I. System
- I.1 [CLAUDE.md](~/.claude/CLAUDE.md) — the rules every agent loads {doc}

## II. Mechanisms
- II.1 [hook-safe.sh](~/.claude/hooks/hook-safe.sh) — fail-open wrapper, timeout, central error log {tool}

## III. Projects
