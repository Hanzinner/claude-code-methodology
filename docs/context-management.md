# Context management: keeping a months-long agent chat alive

Some agents run as a **single session for months**, not a fresh chat per task. That buys continuity —
the agent remembers the arc of the work — but the context grows without bound, and three things go wrong:

- **Auto-compaction loses detail.** Old turns collapse into a summary; the specifics are no longer in
  working memory.
- **Every turn gets more expensive.** The tail is re-read on each step.
- **The chat gets fragile.** Heavy attachments (base64 images, CSV dumps) do **not** get compressed by
  compaction and permanently wedge the session — `prompt too long` even *after* compacting. Real case:
  one chat reached 60 MB and looped on `too long` until the attachments were surgically removed.

The through-line: **reliability comes from a mechanism, not from remembering a rule.** In a long chat, a
written instruction sinks below the fold; a hook still runs.

## Hygiene, in layers

No single layer is enough — each one leaks on its own (compaction sinks, a protocol gets forgotten). So
they stack.

1. **Recap before every compaction.** Harvest what matters into files *before* the transcript is
   compressed — a deliberate pass where a human (or the agent) decides what's worth keeping, not a blind
   auto-harvest. Knowledge lives in files; the chat is ephemeral working memory. (This is the `/recap`
   skill in this repo.)
2. **Storage principle.** Knowledge goes in files, not in chat history. Narrow facts in the agent's own
   folder, shared facts in a common place. The chat is a desk, not an archive.
3. **A "living briefing" hook.** A `UserPromptSubmit` hook compares the SHA-256 of the agent's briefing
   against a per-session marker and injects the fresh version when it changes — removing the manual
   "re-read your briefing" step. It reacts to *content*, not mtime (a `git` checkout that touches the
   file must not trigger it).
   > **The story that made this a rule:** the first version keyed off the session's working directory,
   > and the operator never starts sessions from an agent's folder — so the hook **never fired once for a
   > month**, while a status line claimed it was live. The doc described a dead mechanism as alive.
   > **Lesson, wider than this hook: mark something "live" only with proof it executed** (a marker, a log,
   > an injection seen in a real session). Verifying that the code looks right is not verifying that it ran.
4. **A tool-output trimmer (cron).** A daily job trims old `bash`/`grep`/`read` outputs — those outside a
   recent window (~150 messages) — from large (>5 MB) inactive session files, replacing them with a
   placeholder and moving the cut text to a side file for full rollback. Scoped to *large* sessions only,
   so the payoff tracks the cost. Non-obvious gotcha: the harness stores each tool output **twice** (once
   in the content block, once in a sibling field); the second copy is usually bigger — you have to cut both.
5. **Attachment excision.** A one-time rescue when a chat is already wedged: strip base64 images / CSV
   dumps out of the transcript, structure-preserving, with a backup.
6. **Open-loops (recall, not just capture).** Files *store* pending work, but storing is not remembering
   to act. The agent keeps an explicit open-loops list and raises it when the operator returns — otherwise
   parked work silently falls out of the active window.
7. **Inbox watcher (recall + channel).** The same hook watches an `inbox.md` and injects **only the
   unprocessed `- [ ]` items from the `## New` section, every turn until they're closed** — never the whole
   file (the processed archive only grows), never a one-shot "on change" (which loses anything filed while
   the agent was elsewhere). An empty inbox means silence.
8. **Shared-file delta (`.watchlist`).** For agents that coordinate through shared repo files: the hook
   keeps a snapshot per session and shows only the diff against it — **not `git diff HEAD`**, because agents
   *commit* their changes, so a diff against HEAD is blind. A full dump is impossible anyway (one shared
   backlog file was 71 KB).

> **Delivery without freshness is industrialized staleness.** A *working* delivery layer *raises* the cost
> of stale docs: before, an agent might not read the briefing; now the stale line lands in context
> guaranteed, every turn. "Don't write state into files — write where to look it up" only became mandatory
> *after* the channel came alive.

## Hybrid lifecycle

One long chat plus hygiene holds for **3–4 months**. When even that hits the ceiling (~3–4M tokens), the
answer is a **rare, planned reset** — a fresh chat — not a reflexive restart on every bout of bloat.
Because recap discipline means the harvest is already done, the reset is safe: knowledge is in files, and
the old session goes to an archive you can still `grep`.

## Relay at reset

For an infrastructure agent with unfinished work, don't run two in parallel (they'd step on each other's
machine and git state). Harvest state into files, and a **fresh agent picks it up** — both the new work and
the loose ends. The state lives on disk (scripts, notes), not in the chat.

## The meta-principle

Don't optimize for *tolerating* an expensive, fragile chat. Ask *why* it's expensive and fragile, and
replace the mechanism: a hook costs milliseconds against a tail re-read on every turn. Each layer alone
leaks; layered and mechanized, they hold.

For the multi-agent side of this — delivery between agents, coordination, and the failures that shaped it —
see [`multi-agent.md`](multi-agent.md).
