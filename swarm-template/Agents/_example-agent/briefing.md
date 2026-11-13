# <agent-name> — briefing

> Role in one line: what this agent is for.
> Read first: the files it can't work without (project roadmap, the standard).

## Owns
- Files and domains it is responsible for. Nobody else edits these without a letter first.

## Doesn't touch
- Shared mechanisms, other agents' files. A change there → a letter to the owner.

## How it works
- Where its tasks come from (its inbox, the project roadmap).
- Where it reports: technical detail → the project lead's inbox + a git commit; to the human only what
  passes the filter in `docs/po-interface.md`.

## Standard
- Writes code → `CODING-STANDARD.md` at the workspace root (read it whole once). In a project team → also `docs/project-work.md`.
- Standard: v0 read —
  (after reading, change to `Standard: v<N> read <date>`; put `CODING-STANDARD.md` on a line in this folder's
  `.watchlist` and you are shown only the changelog entries you missed when the version grows)

<!-- Self-healing: an instruction here didn't work as written and you found a working way → append a dated
     line at the bottom: what didn't work · why · the fix. Append, don't rewrite. -->
