# How to write memory here

For the agent saving a memory. The installer copies this folder to `~/.claude/memory/` once; edit the copies
there. Shared memory is for what every chat needs: a correction or lesson about one named agent's own work goes
into that agent's `briefing.md`, not here.

## Layout

```
memory/
├── MEMORY.md           # trigger index, always loaded
├── examples/           # one example per type
└── episodic/           # one file per month (YYYY-MM.md), created on first recap
```

## Types

| Type | Saved when | Purpose |
|------|------------|---------|
| `user` | You learn something about who the user is | Tailor responses |
| `feedback` | User corrects you, or confirms a non-obvious approach worked | Don't make them say it twice |
| `project` | You learn current state of an active project | Informed suggestions in context |
| `reference` | You learn about an external system | Know where to look |

## Frontmatter

```markdown
---
name: short-kebab-case-slug
description: one-line summary used to decide relevance
metadata:
  type: user | feedback | project | reference
  source: where the fact came from      # needed only if you enable memory-write-gate
  verified: yes | inferred | unverified # ditto — a guess is honestly "inferred"
---
```

For `feedback` and `project`, body leads with the rule/fact, then `**Why:**` (the reason, often the incident) and
`**How to apply:**` (when it kicks in) lines. Without the why, a rule turns into dogma: months later nobody can tell
whether it still applies.

Then add one line to `MEMORY.md` under the right heading: `- **topic** → [file.md](file.md)`, under ~150 chars.

## Wikilinks

`[[name]]` resolves to another file's `name:` slug (or its file name without `.md`). Unresolved links are caught by `scripts/curate_memory.py`.

## Episodic log

`episodic/YYYY-MM.md`, one entry per session (`/recap` writes it): `## YYYY-MM-DD` and 1-3 sentences — key
decisions, open loops. Topic files hold the current state; the log holds how you got there.

## What not to save

- Code patterns / file paths — derivable from the repo
- Git history — `git log` is authoritative
- Debug fixes — the fix is in the code
- Ephemeral task state — use a todo list
