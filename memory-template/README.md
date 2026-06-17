# Memory template

This directory is **copied to `$CLAUDE_METHODOLOGY_DIR/memory/`** during install if no memory exists there. After install, edit those files (not these) — these are the seed.

## Layout

```
memory/
├── MEMORY.md           # the trigger index (always loaded into context)
├── README.md           # this file
├── examples/           # sanitized examples of each memory type
│   ├── user_example.md
│   ├── feedback_example.md
│   ├── project_example.md
│   └── reference_example.md
└── episodic/           # per-month session logs
    └── YYYY-MM.md
```

## The four types

| Type | When to save | What it's for |
|------|--------------|---------------|
| **user** | You learn something about who the user is — role, preferences, expertise level, working style | Tailor responses to them specifically |
| **feedback** | The user corrects you, or confirms a non-obvious approach worked | Don't make the user give the same guidance twice |
| **project** | You learn current state of an active project — who's doing what, why, deadlines | Make informed suggestions in that project's context |
| **reference** | You learn about an external system and its purpose (dashboard, ticketing system, doc location) | Know where to look for current info |

## Frontmatter convention

Every memory file starts with:

```markdown
---
name: short-kebab-case-slug
description: one-line summary — used to decide relevance later, so be specific
metadata:
  type: user | feedback | project | reference
---
```

For `feedback` and `project` types, the body should lead with the rule/fact, then `**Why:**` and `**How to apply:**` lines. Knowing *why* lets future-you judge edge cases instead of blindly following the rule.

## Linking

Use `[[name]]` to link to other memories. The `name` is the other file's frontmatter slug, not the filename. Link liberally — a `[[name]]` that doesn't resolve yet marks something worth writing later.

## What NOT to save

- Code patterns / architecture / file paths — derivable from the repo
- Git history — `git log` is authoritative
- Debugging recipes — the fix is in the code
- In-progress task state — use a todo list
- Anything already in `CLAUDE.md`

If the user explicitly asks you to save these things anyway, ask what was *surprising* or *non-obvious* about it — that's the part worth keeping.

## Curation

`scripts/curate_memory.py` checks for orphans, broken links, and unresolved wikilinks. It runs weekly via the `memory-curation-check` hook.
