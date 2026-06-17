---
name: audit
description: Audit the agent's prompt corpus (CLAUDE.md + memory + skill definitions) for contradictions, persona drift, cognitive overload, semantic ambiguity, orphaned references, and stale facts. Invoked when the user says "/audit", "check memory", "find contradictions", "rules audit".
---

# audit

Discovery and reporting of issues in the operating corpus. Does **not** auto-fix — proposes concrete fixes, the user decides.

## What to read

Required:
- `CLAUDE.md` (operating core)
- `memory/MEMORY.md` (index)
- `memory/*.md` (all memory files)
- `skills/*/SKILL.md` (all skill definitions)

Context-dependent (if the user scoped it):
- Subagent briefings
- A specific subcorpus the user named

## What to look for — 6 categories

### 1. Contradictions
Two instructions that can't both be followed. Examples:
- "never ask permission for bash" + "before strong changes, ask"
- "answer brutally" + "soften corrections"
- One file says X for project Z, another says ¬X

Concrete: cite A from file1:line, cite B from file2:line, explain the conflict.

### 2. Persona drift
The agent described differently across files. Examples:
- "don't give advice" in CLAUDE.md vs "offer options" in a skill
- Register: peer-level in one place, "assistant" framing in another

### 3. Cognitive overload
Instructions with too many conditions/branches for reliable execution. Examples:
- A rule with 5+ nested "if X then Y, except Z, except W..."
- A skill with 12 steps where the first 6 are preconditions
- Can be simplified without changing behavior

### 4. Semantic ambiguity
Instructions that can be read multiple ways. Examples:
- "brief" (how many sentences?)
- "loyal" (to what?)
- "should verify" (who, when, how)

Only flag where ambiguity could actually produce different behavior — not nitpicking.

### 5. Orphaned references
Pointers to files/projects/people that don't exist:
- `[[name]]` wikilink to a missing file
- Memory trigger "when topic X → read Y.md" and Y.md is gone
- Reference to a project marked archived elsewhere

### 6. Stale facts
Date-sensitive facts that may have aged:
- "current role", "current project" — cross-check with episodic log
- Model / tool versions
- "this week", "by end of month" without an absolute date
- Active project flagged "CLOSED" elsewhere

## Output format

```markdown
# Audit report — YYYY-MM-DD

## Summary
[1-2 sentences: overall corpus health + most critical issue]

## Critical (actively breaking behavior)
### [category] [short title]
- **File A** (line range): "quote"
- **File B** (line range): "quote"
- **Issue:** [one sentence]
- **Suggested fix:** [one sentence]

## Medium (worth fixing when time permits)
[same shape]

## Low (cosmetic, doesn't block)
[same shape]

## Stats
- Files reviewed: N
- Found: critical X, medium Y, low Z
```

## Anti-patterns

- **Don't auto-fix.** Report only. The user decides what to change.
- **No nitpicking.** "Comma in the wrong place" is not an audit issue. Only things that affect behavior.
- **Don't invent contradictions.** If two rules are compatible, say so directly. Hallucinated problems = waste.
- **Don't duplicate issues.** If one root cause produces 5 symptoms, group them.
- **Don't audit fresh changes.** If a file was updated in the last 24h, the user knows what's there.

## When NOT to audit

- Just after a big corpus overhaul — let the dust settle
- Mid-feature work — distracting
- No changes since the last audit — nothing new to find
