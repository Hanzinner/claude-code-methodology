# memory-template

Seed for `memory/` during install. After install, edit the copies in `~/.claude/memory/`, not these.

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
---
```

For `feedback` and `project`, body leads with the rule/fact, then `**Why:**` and `**How to apply:**` lines.

## Wikilinks

`[[name]]` resolves to another file's `name:` slug. Unresolved links are caught by `scripts/curate_memory.py`.

## What not to save

- Code patterns / file paths — derivable from the repo
- Git history — `git log` is authoritative
- Debug fixes — the fix is in the code
- Ephemeral task state — use a todo list
