# Skills

Slash commands. Each skill is a folder containing a `SKILL.md` file with frontmatter (`name`, `description`) and a body of instructions the agent follows when the skill is invoked.

| Skill | Purpose |
|-------|---------|
| `recap` | Re-read the current session and commit what's worth remembering to `memory/`. |
| `register-as` | Register the current session as a named agent in the shared registry. |
| `call-agent` | Dial a registered agent — resume their session, ask a question, get a one-shot answer. |
| `audit` | Sweep `CLAUDE.md` + memory + skills for contradictions, drift, orphans, stale facts. Report, don't fix. |
| `grill` | Brutalist stress-test of a plan/decision/architecture/position. Direct attacks, ranked by force. |
| `pulse` | Multi-source recency snapshot on a topic (Reddit + HN + web). Synthesis, not link dump. |

## How a skill works

Claude Code surfaces skills by reading the `SKILL.md` frontmatter:
- `name` — what the user types (`/recap`, `/grill`, ...)
- `description` — short trigger description shown when the agent considers invoking it

When the user invokes the skill (`/name` or natural language matching the description), the agent loads the `SKILL.md` body and follows it as a sub-instruction set for the next reply.

## Adding your own

```
skills/my-skill/
└── SKILL.md
```

`SKILL.md` template:

```markdown
---
name: my-skill
description: One sentence on what the skill does and when to invoke it. The trigger phrasing matters — be specific so the agent knows when to fire.
---

# my-skill

Body — step-by-step instructions for the agent. Treat it like an internal SOP.
```

After install, the skill is live in the next session.

## Why skills and not just `CLAUDE.md` rules

`CLAUDE.md` is always loaded — it's the spine. Skills are loaded on demand — they're the toolkit. Use a skill when:

- The procedure is multi-step but situational (not every conversation needs it)
- It has its own anti-patterns and edge cases worth documenting
- You want a clean invocation handle (`/grill` vs. having to describe what you want)
- Multiple users or sessions should converge on the same workflow

If a rule should apply to **every** response, it belongs in `CLAUDE.md`. If it applies only when explicitly invoked, it belongs here.
