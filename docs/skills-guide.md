# Skills guide

Skills are how you give the agent named, reusable workflows it can invoke on demand.

## What a skill is

A folder under `skills/` containing a `SKILL.md` file:

```
skills/my-skill/
└── SKILL.md
```

`SKILL.md` has frontmatter and a body:

```markdown
---
name: my-skill
description: One sentence on what the skill does and when to invoke it. The trigger phrasing matters — be specific.
---

# my-skill

[Body — step-by-step instructions for the agent.]
```

When the user invokes the skill (typing `/my-skill` or saying something the `description` matches), the agent loads `SKILL.md` body and follows it as a sub-procedure for the next reply.

## When to write a skill

If you find yourself:
- Telling the agent the same multi-step workflow more than twice
- Wanting a clean invocation handle (`/recap` vs. "go back and save what we just talked about")
- Documenting anti-patterns and edge cases for one specific task
- Coordinating multiple users / sessions on the same procedure

Then write a skill.

If the procedure runs **every** time, that's a `CLAUDE.md` rule, not a skill. If it runs once and never again, do it inline. Skills are the middle ground: invoked on demand, structured enough to be worth documenting.

## Anatomy of a good skill body

The skills in this repo follow a common structure:

```markdown
# <name>

[One-paragraph statement of what the skill does and the principle it embodies.]

## How to invoke

[What the user types, what arguments the skill takes.]

## Step 1 — [first thing]
[Short reasoning + concrete action.]

## Step 2 — [second thing]
...

## Anti-patterns
- [What NOT to do, with a one-line reason.]

## When NOT to use
- [Cases where the skill is the wrong tool.]
```

The anti-patterns section is the most useful part of a skill. The agent will reach for the skill in the wrong situation unless you tell it explicitly when not to.

## Frontmatter

| Field | Required | Purpose |
|-------|----------|---------|
| `name` | yes | What the user types (lowercase, kebab-case) |
| `description` | yes | One sentence the agent uses to decide whether to fire the skill on a natural-language request |

The `description` is doing work — the agent reads it and decides "does this user request match?" A vague description ("does various things") will either fire too often or never. A specific description ("invoked when the user says X, Y, or Z") is decisive.

## How invocation works

Two paths:

1. **Explicit slash** — user types `/my-skill [args]`. The agent loads the skill body and follows it.
2. **Natural language match** — user says something the `description` describes. The agent decides to invoke the skill (and tells the user that's what it's doing).

For natural-language matching to work, your `description` should include the *trigger phrases the user is likely to say*, not just an abstract summary of the skill.

Bad description: "A code review workflow."

Good description: "Review the current branch for bugs. Invoked when the user says 'review my code', 'check this branch', 'find issues in the diff', '/review', or asks for a sanity check on changes before pushing."

## Arguments

Skills can accept arguments via the slash invocation: `/my-skill arg1 arg2`. The skill body should document what the args mean. If a required arg is missing, the skill should ask for it — not guess.

## Composition

Skills can shell out to scripts in `scripts/`, read files in `memory/`, and invoke other skills. Treat the skill body as you would a function — it can call other things, but it returns one outcome to the user.

## Anti-patterns

- **Vague descriptions.** Be specific about when to fire. If the description matches everything, the skill fires for nothing useful.
- **Bloated bodies.** A skill with 30 steps and 12 sub-conditions becomes its own form of cognitive overload. If it's that complex, it's probably 2-3 skills.
- **Skills that duplicate hooks.** If the procedure should happen automatically, not on demand, it belongs in a hook.
- **Skills that duplicate CLAUDE.md.** If the procedure should always apply, it belongs in the operating core.
- **Output skills.** If a skill ends with "now produce a 5-paragraph report" but the report shape varies wildly by context, the skill is doing too much.

## Examples in this repo

- [`skills/recap`](../skills/recap/SKILL.md) — re-read session, save memorable parts
- [`skills/register-as`](../skills/register-as/SKILL.md) — self-register in the cross-agent registry
- [`skills/call-agent`](../skills/call-agent/SKILL.md) — dial another registered agent
- [`skills/audit`](../skills/audit/SKILL.md) — sweep the prompt corpus for problems
- [`skills/grill`](../skills/grill/SKILL.md) — brutalist stress-test of a plan or position
- [`skills/pulse`](../skills/pulse/SKILL.md) — multi-source recency snapshot

Read several before writing your own — the patterns repeat: clear invocation, step-by-step body, explicit anti-patterns, explicit "when not to use".
