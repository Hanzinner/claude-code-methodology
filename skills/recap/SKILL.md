---
name: recap
description: Re-read the current session and save what is worth remembering to long-term memory, before context is compacted or lost. Use when the user says "/recap", "save context", "save what we did", "before we lose this", or before a manual /compact.
---

# recap

Deliberate memory commit. The native `/compact` is lossy **by design**: it compresses the transcript for conversational continuity, not to preserve what matters (new rules, decisions, background that surfaced mid-session). `/recap` runs a deliberate pass **before** compaction, or any time something worth keeping surfaced. It reads the dialogue since the last compaction boundary, finds what is worth remembering, writes it to the right place, and reports what was saved.

## How to run

1. Pull the dialogue since the last compaction boundary:
   ```bash
   python3 "${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/scripts/recap_extract.py"
   ```
   `$CLAUDE_METHODOLOGY_DIR` is set by the installer (settings.json env). The script picks this session's transcript by `$CLAUDE_CODE_SESSION_ID`; if it warns that it fell back to the newest file, check that the dialogue is really yours.

2. Work out whose session this is: from the working directory (an agent folder, e.g. `agents/<name>/`) plus that agent's briefing if it has one. This decides WHERE to save (step 4). If this is the main/coordinator session (working directory is the workspace root), everything goes to global memory.

3. Read the output and decide what is worth saving. Catch anything that could matter in a future conversation:

   - **People:** preferences, habits, relationships, what they said, what they think
   - **The user personally:** positions, where they changed their mind, likes and dislikes
   - **Household / situational context:** where they live, what changed, schedule, plans
   - **Plans and intentions:** even informal ones ("I want to try X someday", "thinking about Y")
   - **Financial markers:** budgets, goals, constraints
   - **Relationships:** who they trust, who influences decisions, where the friction is
   - **Project context:** who said what, non-obvious dependencies, blockers
   - **Technical environment:** configs, hosts, where things live, new tools (never secrets or passwords: those do not go into memory files)
   - **Decisions:** what was decided, why, which alternatives were rejected
   - **Feedback about agent behavior:** what worked, what did not, what to do differently

4. Decide WHERE to save (swarm storage principle):
   - **Narrow working details of one agent** (tickets, debugging, domain specifics, working patterns) go to **that agent's folder** (its own knowledge file, log, todo). Not to global memory.
   - **Shared things: facts about the user, the swarm, decisions that affect other agents** go to **global** `memory/` (memory files + episodic log).
   - Rule: *work details in the agent folder, decisions and cross-dependencies in global.* Check `memory/MEMORY.md` first. Do not duplicate; update the existing entry instead of spawning a parallel one.
   - For each new memory: its own file in `memory/` with frontmatter (`name`, `description`, `metadata.type` = user/feedback/project/reference), a one-line pointer in `MEMORY.md` under the right section, and `[[name]]` wikilinks to related memories.

5. Episodic log:
   - **Global** `memory/episodic/YYYY-MM.md` stays THIN: 2-3 sentences about the session, key decisions, cross-agent items, things about the user. No narrow working details.
   - **Agent-specific details** (ticket breakdowns, debugging chronicle) go to the agent's own log, if it keeps one.
   ```
   ## YYYY-MM-DD
   [2-3 sentences: what the session was about, key decisions, open loops]
   ```

6. Update open loops (capture is not recall): append this session's unfinished tasks and pending decisions to the agent's todo / open-loops file (what, where it stopped, next step). Saving a pending item is capture; the next session only acts on it if it sits somewhere that is read at the start. This is the main defense against "wrote it down, never acted on it".

7. Report what was saved: a short list, file name + one line each, and where (global vs agent folder).

## What NOT to save

- Anything derivable from the codebase (file paths, function names, architecture)
- Git history or who-changed-what
- Debugging recipes: the fix is in the code, the commit has the context
- Ephemeral task state: use a todo list for that

## Anti-patterns

- Don't paraphrase the same fact into three files for redundancy. Memory is an index, not a database.
- Don't save your own intentions ("I'll be careful about X"). Those are not memories, they are promises without a mechanism.
- Don't summarize what the agent did: the user can read the diff. Memory is for context the diff does not carry.
