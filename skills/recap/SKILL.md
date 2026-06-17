---
name: recap
description: Re-read the current session and save what's worth remembering to long-term memory. Invoked when the user says "/recap", "save context", "save what we did", "before we lose this".
---

# recap

Periodic memory commit. Reads the post-compaction transcript of the current session, finds things worth remembering, writes them to the right place in `memory/`, and reports what was saved.

## How to run

1. Pull the dialogue since the last compaction boundary:
   ```bash
   python3 "$CLAUDE_METHODOLOGY_DIR/scripts/recap_extract.py"
   ```
   (Falls back to `~/.claude/scripts/recap_extract.py` if the env var isn't set.)

2. Read the output and decide what's worth saving. Catch anything that could matter in a future conversation:

   - **People** — preferences, habits, relationships, what they said, what they think
   - **The user themselves** — positions, where they changed their mind, what they like/dislike
   - **Household / situational context** — where they live, what changed, schedule, plans
   - **Plans and intentions** — even informal ones ("I want to try X someday", "thinking about Y")
   - **Financial markers** — budgets, goals, constraints
   - **Relationships** — who they trust, who influences decisions, where the friction is
   - **Project context** — who said what, non-obvious dependencies, blockers
   - **Technical environment** — configs, IPs, where things live, new tools
   - **Decisions** — what was decided, why, what alternatives were rejected
   - **Feedback about agent behavior** — what worked, what didn't, what to do differently

3. Check `memory/MEMORY.md` for what's already there. Don't duplicate. Update existing entries instead of creating parallel ones.

4. For each new memory:
   - Write it to its own file in `memory/` with frontmatter (`name`, `description`, `metadata.type` = user/feedback/project/reference)
   - Add a one-line pointer to `MEMORY.md` under the right section
   - Use `[[name]]` wikilinks to connect related memories

5. Append an entry to `memory/episodic/YYYY-MM.md` (create if absent):
   ```
   ## YYYY-MM-DD
   [2-3 sentences: what the session was about, key decisions, open loops]
   ```

6. Report what was saved — short list, file names + one-line each.

## What NOT to save

- Anything derivable from the codebase (file paths, function names, architecture)
- Git history or who-changed-what
- Debugging recipes — the fix is in the code, the commit has the context
- Ephemeral task state — use a todo list for that

## Anti-patterns

- Don't paraphrase the same fact into three files for redundancy. Memory is an index, not a database.
- Don't save your own intentions ("I'll be careful about X") — those aren't memories, they're promises. See CLAUDE.md rule 3.
- Don't summarize what the agent did — the user can read the diff. Memory is for context the diff doesn't carry.
