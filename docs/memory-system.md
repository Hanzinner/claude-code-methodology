# Memory system

How long-term context persists across sessions, why it's structured the way it is, and how to work with it.

## The shape

```
memory/
├── MEMORY.md           # trigger index — always in context
├── README.md
├── episodic/
│   └── YYYY-MM.md     # one file per month, written by /recap
├── user_<name>.md     # facts about a person
├── feedback_<x>.md    # behavioral guidance
├── project_<x>.md     # current state of an active project
└── reference_<x>.md   # pointer to an external system
```

`MEMORY.md` is **always loaded** into the agent's context (it's referenced from `CLAUDE.md`). Everything else is **lazy-loaded** — read only when a trigger matches.

This split matters. If you dump every memory into one always-loaded file, the context window fills with stale facts on irrelevant topics, every conversation. The trigger index keeps the always-loaded surface small and routes to the relevant detail on demand.

## The trigger index

`MEMORY.md` reads as a list of "when topic X comes up → read file Y". Example:

```markdown
## People
- **Jane (CTO)** — decides on infra → [project_jane.md](project_jane.md)

## Active projects
- **Acme migration** (Phase 2, cutover next month) → [project_acme.md](project_acme.md)

## Feedback
- **Don't summarize at end of reply** → [feedback_no_trailing_summary.md](feedback_no_trailing_summary.md)
```

The agent scans this on every turn. When the user mentions Jane, Acme, or the agent considers writing a trailing summary, it opens the relevant file before continuing.

Rules for the index:
- One line per pointer
- Under ~150 characters per line
- Pointers grouped by category (people / projects / feedback / reference / etc)
- No memory content lives here — only pointers

## The four types

| Type | What goes in | Triggered by |
|------|--------------|--------------|
| **user** | Who the user is — role, expertise, working style, preferences | Most conversations; usually pre-loaded via `MEMORY.md`'s top section |
| **feedback** | Behavioral guidance — corrections AND confirmations of what worked | The agent considers an action the feedback covers |
| **project** | Current state of an active project — who, why, when, blockers | The project is named or its scope is touched |
| **reference** | Pointer to an external system and what it's for | The external system is mentioned, or the topic it covers comes up |

The four types aren't enforced by the system — they're a taxonomy that has stood up over a year of real use. Add others if your work needs them. Don't fragment further than necessary (don't split "feedback" into "communication-feedback" / "code-feedback" / etc — one type, organized by topic).

## Frontmatter

Every memory file starts with:

```markdown
---
name: short-kebab-case-slug
description: one-line summary — used to decide relevance later, so be specific
metadata:
  type: user | feedback | project | reference
---
```

The `name` slug is the wikilink target — other files reference this one with `[[short-kebab-case-slug]]`. Keep slugs stable; rewriting them requires updating every linker.

The `description` is what the agent reads when deciding whether to open the file. A good description is specific ("how Jane wants weekly status emails phrased") not generic ("info about Jane"). The agent decides "is this relevant?" from this one line, so make the line decisive.

## The Why and How-to-apply convention

For `feedback` and `project` types, body structure:

```
[Rule or fact]

**Why:** [the reason — often a past incident or constraint]

**How to apply:** [when/where this kicks in]
```

The Why exists so future-you can judge edge cases. Without it, the rule becomes dogma — followed even when the original reason no longer applies. With it, you can say "the constraint that motivated this rule has gone away — kill the rule".

## What NOT to put in memory

The most common waste:

| Bad memory | Why | Where it should live |
|------------|-----|----------------------|
| "The auth handler is in `src/auth/handler.go`" | Derivable from `grep` / `Read` | The codebase |
| "Bob renamed the `User` model to `Account` in commit abc123" | Git history | `git log` |
| "When test X fails, the fix is to set FOO=bar" | The fix is in the code; the commit explains why | Commit message |
| "We're working on the migration today" | Ephemeral session state | A todo list |
| "Be brutal in code review" | Already in CLAUDE.md | nowhere new |

If the user explicitly asks you to save one of these, push back: ask what was *surprising* or *non-obvious* about it. That's the part worth keeping.

## Wikilinks

Use `[[name]]` inside memory bodies to connect related entries. The link target is the other file's frontmatter slug, not the filename. Examples:

```markdown
This pattern matters when the user is in [[think-first-mode]] —
[[feedback-no-manufactured-disagreement]] applies in that mode too.
```

Link liberally. A `[[name]]` that doesn't resolve yet marks something worth writing later — `curate_memory.py` will flag it as a follow-up.

## Episodic log

`episodic/YYYY-MM.md` is the timeline. One entry per session, written by `/recap`:

```markdown
## YYYY-MM-DD
1-3 sentences on what the session was about. Key decisions made. Open loops carried forward.
```

This is the answer to "when did we do X?" Read it when the user references prior-conversation work.

The episodic log is not the same as the per-topic files. The per-topic files hold **current state**; the episodic log holds **how we got here**. Both are useful, neither replaces the other.

## /recap

The skill that commits memory at the end of a session. Workflow:

1. Pull the post-compaction transcript via `scripts/recap_extract.py`
2. Scan for things worth remembering (preferences, decisions, project state, behavioral feedback)
3. Check `MEMORY.md` — don't duplicate; update existing entries instead
4. Write or update memory files
5. Append a 1-3 line entry to `episodic/YYYY-MM.md`
6. Report what was saved — short list

The recap is **what makes the memory grow on its own**. Without it, memory is just a static seed — you'd have to write all of it by hand.

## Curation

`scripts/curate_memory.py` runs weekly (via the `memory-curation-check` hook) and reports:

- **Orphans** — files in `memory/` not linked from `MEMORY.md`
- **Broken links** — pointers in `MEMORY.md` to files that don't exist
- **Unresolved wikilinks** — `[[name]]` where `name` isn't a known memory slug

It doesn't auto-fix. It surfaces. You decide whether to consolidate, delete, or write the missing target.

## Practical rules of thumb

- **One topic, one file.** Don't fragment a topic into 5 files because each got its own session. Consolidate.
- **One file, one topic.** Don't pile unrelated facts into one file because they happened the same day. Split.
- **Trigger granularity matters.** If the trigger is too broad ("project work"), the agent reads it on every turn — defeats the lazy-loading. If too narrow, the trigger rarely fires. Aim for "user mentions topic X by name".
- **Stale > nothing.** A slightly stale memory is more useful than no memory. Trust point-in-time, verify when acting.
- **The Why is the most rotted part.** Why-lines age fastest because the original constraint shifts. Reread them periodically.
