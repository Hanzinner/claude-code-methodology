# Memory system

## Layout

```
memory/
├── MEMORY.md           # trigger index — always in context
├── README.md
├── episodic/
│   └── YYYY-MM.md
├── user_<x>.md
├── feedback_<x>.md
├── project_<x>.md
└── reference_<x>.md
```

`MEMORY.md` is always loaded. Other files are lazy-loaded — only when a trigger matches.

## Trigger index

`MEMORY.md` is a list of "topic X → file Y" pointers. One line per pointer, under ~150 chars. No memory content lives in `MEMORY.md`.

Example:
```markdown
## People
- **Jane (CTO)** — decides on infra → [project_jane.md](project_jane.md)

## Feedback
- **Don't summarize at end of reply** → [feedback_no_trailing_summary.md](feedback_no_trailing_summary.md)
```

## Four types

| Type | Content |
|------|---------|
| `user` | Who the user is — role, expertise, working style |
| `feedback` | Behavioral guidance (corrections and confirmations) |
| `project` | Current state of an active project |
| `reference` | Pointer to an external system and its purpose |

Add other types if needed. Don't fragment further than necessary.

## Frontmatter

```markdown
---
name: short-kebab-case-slug
description: one-line summary used to decide relevance later
metadata:
  type: user | feedback | project | reference
---
```

`name` is the wikilink target — `[[name]]` from other files resolves to this.

## Why + How to apply convention

For `feedback` and `project` types:

```
[rule or fact]

**Why:** [the reason — often a past incident or constraint]

**How to apply:** [when/where this kicks in]
```

`Why` lets you decide later whether the rule still applies. Without it, rules become dogma.

## What not to save

| Bad memory | Where it should live |
|------------|----------------------|
| File paths / architecture / function names | The codebase |
| Who-changed-what | `git log` |
| Debug fixes | Commit message |
| In-progress task state | A todo list |
| Rules already in CLAUDE.md | nowhere new |

## Episodic log

`episodic/YYYY-MM.md` — one entry per session, written manually or by a periodic recap:

```markdown
## YYYY-MM-DD
1-3 sentences. Key decisions. Open loops.
```

Per-topic files hold current state; the episodic log holds how you got there.

## Curation

`scripts/curate_memory.py` reports:
- Orphans (files not linked from `MEMORY.md`)
- Broken links (pointers to missing files)
- Unresolved wikilinks (`[[name]]` where `name` doesn't exist)

Runs weekly via the `memory-curation-check` hook. Reports only — doesn't auto-fix.
