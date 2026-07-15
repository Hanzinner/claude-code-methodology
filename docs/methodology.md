# Methodology

Patterns from ~three months of daily Claude Code use. Not doctrine — mechanisms that work, reasons why, mistakes to avoid.

Take individual pieces, adapt to your own workflow. Don't copy the whole thing wholesale.

## 1. Memory architecture

### MEMORY.md is a trigger index, not a store

`MEMORY.md` is a small file (under ~200 lines) shaped as **"when topic X comes up → read file Y.md"**. Not content, an index.

```markdown
- **AWS deployment / infra** → [reference_aws.md](reference_aws.md)
- **Current active projects** → [project_state.md](project_state.md)
```

**Why:** `MEMORY.md` loads into every conversation. If a topic doesn't come up, detail files never load. Context isn't eaten unnecessarily. When a topic surfaces, the agent opens the specific file and has depth.

**Anti-pattern:** dumping everything into `MEMORY.md` → file grows → early lines fall off → agent sees half the index.

### File types

- **`user_*`** — facts about the user (role, situation, preferences)
- **`feedback_*`** — behavioral rules born from specific cases ("don't do X because Y happened")
- **`project_*`** — state of specific projects, decisions, stakeholders
- **`reference_*`** — pointers to external systems (where, how to connect)
- **`episodic/YYYY-MM.md`** — session log (what was done when)

The split helps semantically. "What did we discuss last week?" → episodic. "What are the rules about X?" → feedback. "State of project Y?" → project.

### Point-in-time discipline

Memory is a **snapshot, not live state**. A file written two weeks ago may be stale (project cancelled, person left, decision reversed).

Rule: before making a claim based on memory, **verify** via grep / read / search. Especially for date-sensitive facts, configurations, versions.

Anti-pattern: "memory says X → confidently assert X to user" → turns out X changed → trust erosion.

### Memory vs plan vs tasks (scope)

- **Memory** — persists between sessions, useful for future conversations
- **Plan** — approach agreement in the current session before implementation
- **Tasks** — discrete steps in the current session, progress tracking

Don't confuse them. Ephemeral state (a TODO in the current task) doesn't belong in memory.

## 2. Skills

### When to make one

Worth creating when:
1. **Recurring methodology** — you repeat the same procedure (company research, pipeline debug, code review) ≥3 times/month
2. **Has clear anti-patterns** — known mistakes to avoid; a prompt in your head won't remember them
3. **Needs forcing intake** — questions that must be asked *before* execution to avoid wasted work
4. **Has a clear output format** — structure worth standardizing

Not worth it when:
- One-shot task
- Method varies per case (skill = overengineering)
- It's just "find X" — bash/search is enough

### SKILL.md shape

Frontmatter:
```yaml
---
name: skill-name
description: One paragraph — what it does + explicit trigger phrases for invocation. The more specific the description, the more accurately the agent invokes it.
---
```

Body:
1. **Step 1 — Forcing intake** (optional) — questions to ask before execution
2. **Steps 2-N — Workflow** — exact procedure
3. **Output format** — what the result looks like
4. **Anti-patterns** — what NOT to do
5. **When NOT to use** — boundaries

### Composable skills for distinct cognitive moves

Instead of one monolithic "assistant" — separate skills for separate tasks:
- `/grill` — stress-test a plan / decision (attack assumptions)
- `/audit` — check instruction corpus for contradictions / drift
- `/recap` — commit a session's important parts to memory before `/compact` flattens them
- `/pulse` — multi-source recency snapshot on a topic

The agent sees all skill descriptions and picks the right one. User says "stress-test this plan" → triggers `/grill` without an explicit call.

## 3. Hooks

### Hooks beat behavioral rules

A rule in `CLAUDE.md` can be "forgotten" mid-long-session. A hook is a bash script that **guaranteed runs** on an event (UserPromptSubmit, SessionStart, etc). It's a mechanism, not an intention.

### Hooks that pay off

**SessionStart — memory health check.** Script checks if memory files aren't stale, if `MEMORY.md` matches the file set. Silent on clean. Weekly cadence.

**UserPromptSubmit — time + gap detector.** Script injects into every user prompt:
```
[now: 2026-05-24 22:45 EDT | gap since previous user message: 3h 12m]
```
Gives the agent temporal awareness — otherwise it "doesn't know" what elapsed between messages (just sees the next line in the transcript).

Implementation: bash script in `~/.claude/scripts/`, parses `session_id` from stdin JSON, timestamp file per session, stdout injects into context.

**PreToolUse on Read for PDF/HTML — auto-extract.** Intercepts reads on `.pdf` / `.html`, runs extraction (`pdftotext`, `lynx`, `pandoc`), redirects the agent to read the `.txt` output instead. The agent never has to remember "extract first" — it physically can't read the raw file.

### Anti-pattern

A hook that frequently fails → blocks invocation. Keep scripts simple, fast-fail-and-continue (exit 0 by default, don't block prompts unless intentionally blocking with exit 2).

## 4. Permissions

### Blanket vs confirm — by blast radius

- **Local reversible ops** (Edit, Read, bash in sandbox) → allow blanket, don't ask
- **High blast radius** (`rm -rf`, drop DB, force push) → always confirm
- **Externally visible changes** (cloud docs, posts, emails) → describe → confirm → act

### Privacy boundary as explicit exclusion list

Instead of "the agent won't get into something" — **explicitly enumerate what NOT to integrate**:
- Email MCP? No — human channel, not agent proxy
- Calendar MCP? No
- Slack / Telegram MCP? No — confidential conversations

User passes relevant info manually. The boundary is an **architectural decision**, not ad-hoc.

### Destructive actions

Instead of `rm` — `mv` to `~/.Trash/`. Reversibility as default. Especially for the agent — it can pick the wrong file.

## 5. Communication

### Validator, not sycophant

- Good idea → "good". Bad → "bad". Real assessment.
- No "I'd be happy to", "Great point!", "You're absolutely right" as reflex.
- Calibration over comfort.

Anti-pattern (counter-overcorrection): deflating good moves to look "objective". If something is genuinely strong, say so directly.

### No empty promises

"I'll be more careful", "I'll remember", "I won't do that again" — **a lie unless a mechanism changed**. Replace with:
- Name the concrete file / skill / rule that changed
- Or honestly say "nothing changed, I just acknowledge the miss"

### Logic over source / authority

An argument is judged by internal consistency and evidence, not by source credentials. Source bias ≠ argument falsehood. When in doubt, attack the **premise**, not the source.

### Drive dialogue, not menus

Instead of "pick 1 of 3" — propose one concrete next step with a brief reason. User will say if wrong.

Exception: when there's real ambiguity in requirements — ask a specific question, don't dump options.

### Doubt → question, not assumption

Before acting on an assumption, **clarify**. Own assumption + action on it = always a mistake. Especially before writing to memory.

### Think-first signals

User says "thinking", "what if", "maybe", "considering" — this is **discussion**, not a request for action. Don't lurch into execution. Reach a decision together, then act.

Flip side: once a decision is made, act without re-asking on every step. Re-asking on an agreed action = blocker.

### Capture life context

Situational, role, environment details — capture and record **without prompting**. This shapes future decision context.

## 6. Workflow rituals

### /recap → /compact pattern

The native `/compact` is lossy **by design**: it summarizes the transcript to keep the conversation going, not to retain what matters. Rules, decisions, and background that emerged mid-session get flattened into a summary and are gone for good. `/recap` is the fix — a deliberate memory-commit of those parts *before* compaction runs.

Run it when context approaches the limit (visible on status indicator), **or any time important things surfaced in the chat that must outlive the session** — don't wait for the limit:
1. Run `/recap` — agent re-reads the session, writes important parts to memory + episodic
2. Then `/compact` — harness compresses into summary

**Not really a memory problem in practice.** Claude Code shows a status indicator (a filling circle) as context approaches the auto-compact threshold — a visible cue. So you don't have to *remember* to recap; you *react* to the warning before it fires. It's still a manual step — there's no session-end event to fully automate it — but the UI removes the "forgot it existed" failure. Recap when the circle is near full, or any time something worth keeping surfaced.

### /audit for drift control

Every couple of months — `/audit` sweeps `CLAUDE.md` + memory + skills for:
- Contradictions (rule conflicts with another)
- Persona drift (agent described differently in different files)
- Cognitive overload (rule with 5+ conditions)
- Orphaned references (pointers to missing files)
- Stale facts (project marked "active" but archived elsewhere)

User fixes after reviewing the report — the skill reports, doesn't auto-fix.

## 7. Trade-offs / lessons

### Write-only memory

Episodic log (session journal) is almost never read back automatically. Only when the user explicitly says "what did we do last week". Not a bug — a property: memory is loaded by trigger, episodic triggers are rare.

**Mitigation:** don't rely on episodic as activate-able context. It's history for the human, not operational context for the agent.

### Hallucinated problems when asked to find them

If you say "find holes in this plan" — the agent will find them, even when none exist. Confirmation bias of the request.

**Mitigation:**
1. Hypothesis instead of directive: "what would have to be true for this plan to fail in 6 months?"
2. Explicit escape hatch: "if there are no real problems, say so directly"
3. Split description and criticism into separate steps

(Baked into `/grill` as methodology.)

### Memory contradictions across files

Accumulate naturally — new rules overwrite old ones, but old ones stay in files. Without `/audit` every couple of months → drift.

## 8. Tried and rejected

**Email / Calendar / Slack / Telegram MCP** — privacy boundary. User passes manually.

**OSINT cron** — periodic briefs on general topics. Anti-pattern: "briefs for the sake of briefs". Proactivity only on real trigger.

**Weaker-model critic** (Haiku critiquing Sonnet/Opus) — weaker can't reliably critique on analytical tasks. Wrong use case.

**Vector search for personal memory** — flat files + wikilinks + grep is enough for the corpus size of one person. Vector = overengineering.

**Devil's advocate as automation** — generates hallucinated problems (see above). Better an explicit `/grill` with the right prompt.

**Watch on vault via inotifywait** — a static snapshot of the graph in memory is enough. Watch = overengineering.

**Post-session reflection hook** — Claude Code doesn't have a "session end" event. And there's no need — `/recap` covers it.

## 9. Known issues (WIP)

This is a living personal setup, not a shipped product. Open items being worked on:

- **Trash has no rotation yet.** `mv` to `~/.Trash/` instead of `rm` gives reversibility, but nothing prunes it — it grows unbounded until cleaned by hand. A TTL cleanup (e.g. cron `find ~/.Trash -mtime +30 -delete`) is planned, not built.
- **`/audit` is manual and report-only.** It surfaces rule drift and stale facts but doesn't auto-fix, and nothing schedules it. Between runs, drift accumulates. Cadence and optional auto-fix are open questions.

## 10. Anthropic docs worth reading

- Skills overview: <https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview>
- Hooks reference: <https://docs.claude.com/en/docs/claude-code/hooks>
- Settings: <https://docs.claude.com/en/docs/claude-code/settings>
- Memory (Claude Code): <https://docs.claude.com/en/docs/claude-code/memory>

Anthropic Academy has short courses on Claude Code Skills and Sub-agents (1-2 hours each, certificate). Useful for vocabulary and gap-check.

## Closing

This is a **snapshot of a system that took shape over ~three months of active use**. Not doctrine. Best used by taking individual patterns (memory as trigger index, `/audit` ritual, hook for time injection) and folding them in gradually. Don't dump-copy.
