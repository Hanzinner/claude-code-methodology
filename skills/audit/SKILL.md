---
name: audit
description: Audit the agent's prompt corpus (global CLAUDE.md, memory files, skill definitions, agent briefings) for contradictions, persona drift, cognitive overload, semantic ambiguity, orphaned references, and stale facts. Use when the user says "/audit", "check memory", "find contradictions", "audit the rules", "clean up the ruleset", or asks for a sweep of behavioral instructions.
---

# Audit

Discovery and reporting of issues in the agent's prompt/instruction corpus. Does **not** auto-fix. It proposes concrete fixes; the user decides.

## What to read

Required:
- `~/.claude/CLAUDE.md` (global rules) and the project `CLAUDE.md` if there is one
- `memory/MEMORY.md` (index) and all `memory/*.md` files
- `~/.claude/skills/*/SKILL.md` (all skill definitions)

If the user scoped it:
- Agent briefings (`briefing.md` in agent folders)
- A specific sub-corpus the user named

## What to look for: 6 categories

### 1. Contradictions
Two instructions that cannot both be followed. Examples:
- "never ask permission for bash" + "before strong changes, ask"
- "answer brutally" + "soften corrections"
- One file says X for project Z, another says not-X

Be concrete: quote A from file1:line, quote B from file2:line, explain the conflict.

### 2. Persona drift
The agent is described differently in different files. Examples:
- "don't give advice" in CLAUDE.md vs "offer options" in a skill
- Peer-level register in one place, "assistant" framing in another

### 3. Cognitive overload
Instructions with too many conditions or branches to follow reliably. Examples:
- A rule with 5+ nested "if X then Y, except Z, except W..."
- A skill with 12 steps where the first 6 are preconditions
- Anything that can be simplified without changing behavior

### 4. Semantic ambiguity
Instructions that can be read several ways. Examples:
- "brief" (how many sentences?)
- "loyal" (to what?)
- "should verify" (who, when, how)

Flag only where the ambiguity could actually produce different behavior. No nitpicking.

### 5. Orphaned references
Pointers to files, projects or people that do not exist:
- a `[[name]]` wikilink to a missing file
- a memory trigger "when topic X, read Y.md" where Y.md is gone
- a mention of a project that is marked archived elsewhere

### 6. Stale facts
Date-sensitive facts that may have aged:
- "current role", "current project": cross-check with the episodic log
- model or tool versions
- "this week", "by end of month" without an absolute date
- an active project flagged "CLOSED" elsewhere

## Output format

```markdown
# Audit report: YYYY-MM-DD

## Summary
[1-2 sentences: overall corpus health + the most critical issue]

## Critical (actively breaking behavior)
### [category] [short title]
- **File A** (line range): "quote"
- **File B** (line range): "quote"
- **Issue:** [one sentence]
- **Suggested fix:** [one sentence]

## Medium (worth fixing when there is time)
[same shape]

## Low (cosmetic, does not block)
[same shape]

## Stats
- Files reviewed: N
- Found: critical X, medium Y, low Z
```

## Anti-patterns

- **Don't auto-fix.** Report only. The user decides what to change.
- **No nitpicking.** "Comma in the wrong place" is not an audit issue. Only things that affect behavior.
- **Don't invent contradictions.** If two rules are compatible, say so plainly. Hallucinated problems are waste (same anti-pattern as in `/grill`).
- **Don't duplicate issues.** If one root cause produces 5 symptoms, group them.
- **Don't report on fresh edits.** If a file changed in the last 24 hours, the user most likely knows what is in it.

## When NOT to audit

- Right after a big corpus overhaul: let the dust settle
- Mid-feature work: it distracts
- Nothing changed since the last audit: nothing new to find
