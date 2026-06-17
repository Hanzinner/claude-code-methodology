# skills

Slash commands. Each folder has a `SKILL.md` with frontmatter (`name`, `description`) and a body the agent follows when the skill is invoked.

| Skill | Action |
|-------|--------|
| `recap` | Re-read the current session, save what's worth remembering to `memory/`. Uses `scripts/recap_extract.py`. |
| `audit` | Sweep `CLAUDE.md` + `memory/` + `skills/` for contradictions, persona drift, orphaned references, stale facts. Reports, doesn't auto-fix. |

## Adding your own

```
skills/<name>/SKILL.md
```

Frontmatter:

```markdown
---
name: <name>
description: One sentence the agent uses to decide whether to fire on a natural-language request. Be specific about triggers.
---

# <name>

[Step-by-step body — what the agent does when invoked.]
```

Invocation: `/<name>` or natural language matching `description`.
