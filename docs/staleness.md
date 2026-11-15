# Decision record: documents must not hold state that can change on its own

Status: accepted. Context: a swarm of long-lived agents, where briefings and inboxes are injected into context by hooks.
Short version of the same argument lives in [`multi-agent.md`](multi-agent.md); this is the full reasoning.

## The question

Agent X reads a problem A in an inbox or todo file. Agent Y has already removed or changed it. X works from
information that was false at the moment it was read. What are the options? Second, linked question: how do
inbox and todo split, so agents do not live inside the inbox?

## Evidence

A developer agent's briefing, written in the morning, was checked against git the same day:

| Briefing said | Reality |
|---|---|
| "Next batch: the ARP module" | ARP and DNS modules were already in the kernel tree |
| "Networking: research phase" | the network stack was written and merged |
| "Design: asleep" | a release tag had shipped, and that agent had held the lock |

The briefing went stale within half a day. A date next to the claim does not help: it marks suspicion, it does
not make the text fresh, and the reader believes the text anyway.

## The finding that matters

Until then the briefing hook had been broken, so briefings were often not read at all. Once delivery was fixed,
the stale briefing landed in context on every turn, guaranteed. Delivery does not tell truth from lie; it carries
whatever is in the file.

> Delivery without freshness is industrialized staleness.

This is not an argument against delivery. It means freshness stops being optional once delivery works.

## Root cause

The document duplicates state that lives elsewhere. "Networking is in the research phase" is not knowledge about
the swarm; it is a snapshot of code, branches, tags and a changelog. Any duplicate of state drifts. Here it took
half a day.

Rule: a document does not describe what can be computed from the source. Instead of "networking is in research,
next batch is ARP", write "branch state: `git log --oneline <branch> -5`; what shipped: top of the changelog".
The file says where to look, not what you will see.

Test for every line:

> Can this become false without anyone editing this file?

- Yes: it is **volatile** (who is busy, current version, latest tag, "next batch is X", task status). It does not
  belong in the file. Link to the source.
- No: it is **durable** (role, scope, boundaries with neighbours, rules, the reasoning behind decisions, lessons).
  Write it.

One real briefing mixed both: its decision rationale and boundaries were durable and valuable, while its
"live priorities" went stale in the same file within hours.

## Options considered

1. **Do not duplicate state.** Strip volatile lines, keep pointers to git, tags, changelog, queue. Kills the class,
   not the instance. Chosen first.
2. **Generate, do not write.** If a state summary is needed, a script or cron builds it from git. Generated
   text is regenerated, so it does not rot. (A branch-state summary is about ten lines of script.)
3. **Transient inbox.** See below. The longer an item sits, the likelier it is already false.
4. **Show age at display time.** The hook marks an item as "hanging N days". Cheap, but only a suspicion signal,
   not freshness. In this repo `hooks/briefing-watchman.sh` marks inbox items older than 2 days.
5. **Invalidation broadcast** ("Y changed state, notify everyone who referenced it"). Rejected: it requires knowing
   who referenced what, which is expensive and brittle. Option 1 makes it unnecessary.

Priority: remove the duplicate > generate it > warn about age > rely on memory.

## Inbox versus todo

The inbox is a mailbox, not a desk. An empty inbox is the normal state, not an achievement.

Flow: item arrives, agent reads it, then either does it at once (small) or moves it to its own todo and closes the
inbox item. Work lives in the todo.

- **Verification point.** The move inbox to todo is where the agent checks whether the item is still true. An item
  that has sat in the inbox for a month is a snapshot of someone else's message.
- **Context cost.** The hook pings unprocessed items on every prompt. A large task living in the inbox for a week
  burns context on each turn. In the todo it is not re-pinged; it resurfaces when the human returns to the agent.
- **Closing safely.** Clearing an inbox with a bare edit is a read-modify-write without a lock and loses letters
  that arrived in parallel. Use `scripts/inbox_done.sh` (closes an item under the same lock as delivery).

The author of this rule broke it the same day: the archivist agent processed seven items directly in the inbox
instead of moving them to its todo, and they hung there.

## Status of another agent's work: check the source

Asked "did agent Z do Y?", look at the result (code, file, tag, `git log`), not at Z's todo or inbox. Between
"done" and "written down" there is always a window, and in that window the file lies. Concrete case: an agent told
the human a task was not done yet; it had been done, just not recorded. Work is material: if a hook was written,
a `grep` proves it in a second.

## Rejected: claim-first

Proposal: announce "I started X" before working, so others do not duplicate.

Rejected because it does not remove the window, it moves it (the claim must also be written in time); it is state
in a file again, so it rots; and a claim without a TTL is a lock, which had already cost two hours of deadlock that
day. Exception: long work with a real risk of duplicate effort. Then the claim is mandatory with a TTL and a
takeover rule: `scripts/claim.sh` (acquire/check/release, expiry built in, expired claims are free).

## What shipped, and what did not

- Rule "volatile state is not written into files, only a pointer to the source; the inbox is transit": not in this
  repo's `CLAUDE.md` as a numbered rule. It is described here and in `docs/multi-agent.md`. Copy it into your own
  `CLAUDE.md` if you want it always loaded.
- Inbox tooling: `scripts/inbox_post.sh`, `scripts/inbox_done.sh`, `hooks/briefing-watchman.sh` (per-turn ping,
  age mark after 2 days) are in this repo.
- TTL claims: `scripts/claim.sh` is in this repo.
- Generated branch-state summary: not in this repo.

## Honest limit

None of this keeps documents true forever. It shrinks the surface for lies: the less volatile content in files,
the less can rot. The rest is discipline, and discipline lost to mechanisms every time we measured it. Hence the
order: remove the duplicate, generate, remind, and only last rely on memory.
