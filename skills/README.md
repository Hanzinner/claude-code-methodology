# skills

Slash commands. Each folder has a `SKILL.md` with frontmatter (`name`, `description`) and a body the agent follows when the skill is invoked.

| Skill | Action |
|-------|--------|
| `recap` | Re-read the current session, save what's worth remembering to `memory/`. Uses `scripts/recap_extract.py`. |
| `audit` | Sweep `CLAUDE.md` + `memory/` + `skills/` for contradictions, persona drift, orphaned references, stale facts. Reports, doesn't auto-fix. |
| `dossier` | Hypothesis-tested research on a company/person/org; at least 30% of searches try to disprove the hypothesis. |
| `edit` | Video edit analysis: scene keyframes + per-frame log + narrative. Uses `scripts/extract_scenes.sh`. |
| `grill` | Brutalist stress-test of a plan, decision, architecture or position. |
| `pulse` | Recency snapshot of a topic from Reddit + Hacker News + web. |
| `update` | Update the installed system from its repo: say in plain words what is new, install the same way, merge `CLAUDE.md`, check. |
| `register-as` | Register the current chat as a named agent: copies the agent template into `Agents/<Name>/`, adds a row to `AGENTS.md`, records the session identity for the briefing watchman. |

## Adding your own

Worth a skill when you repeat the same procedure (research, a review, a debugging routine) a few times a month, it
has known mistakes to avoid, it needs questions asked before starting, or its result has a shape worth fixing. Not
worth it for a one-off task, a method that changes every time, or "find X" (a search does that).

A good body, in order: questions to ask before starting (if any), the steps, what the result looks like, what not
to do, when not to use it.

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
