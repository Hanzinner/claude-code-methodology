---
name: decision-log
description: Record every judgement call made without asking the user - options considered, option chosen, cost to flip - into a per-session decisions file, surface it verbatim in the final message, and apply the user's overrides when they quote entries back. Decisions that change the product or something the user already saw are not logged-and-applied - they are named to the user before building. Invoke at the start of a task with judgement calls, to re-emit the log, or to process overrides; also when the user says "decision log", "show the decision log", "what did you decide on your own", "/decision-log".
---

# Decision log

A judgement call flagged in prose mid-session is buried the moment the next tool result scrolls it away. It counts only when it is in the log.

## What is a judgement call

Any point where two or more reasonable options existed and you picked one without asking: an ambiguous instruction you interpreted, a scope you cut or expanded, a default you chose, a pattern you followed over another, an error you decided to swallow or raise, a thing you deliberately did not do, an item you deferred. Not: what the user specified explicitly, and not mechanical choices (formatting, import order).

## What is NOT logged-and-applied

A decision that changes the product, or changes anything the user has already seen or approved, is not yours to apply and log afterwards. It is named to the user in chat as one line **before** building: "decisions I am making myself: ...". A product change to something the user already praised goes in only with their "yes" on that exact point. The log covers the rest: technical, scope and default calls.

## The file

`decisions.md` in the session scratchpad directory that the system prompt names. Fall back to `/tmp/claude-decisions-<branch>.md`. Never inside the repo. Append at the moment you decide, not at the end from memory - the end-of-session reconstruction is exactly the thing that loses entries.

One entry per call, this shape and no longer:

```
### D3 - <the decision in one line>
- Chose: <option> - <one clause of why>
- Also: <option A> (<why not, one clause>); <option B> (<why not>)
- Flip cost: trivial | moderate | rework
- Where: <path:line, or "scope" / "process">
- Status: auto-applied
```

Subagents make calls too. Every Task prompt you write asks the subagent to end its report with its own entries in this shape; you merge them in under their own IDs.

## The final message

The last message of the task carries the log **inline, verbatim** - a link alone gets ignored. Render it as one table row per entry, in the user's language:

| ID | Decision | Chose | Also considered | Cost to flip |

Then exactly one line: `Quote a row and name the option you want instead.` No commentary on the entries; the table is the commentary.

If there were no judgement calls, say `No decisions were made without you this session.` - the absence is information too. In a turn with no task (pure conversation) omit that line.

## Overrides

When the user quotes entries back with a different option:

1. For each quoted ID: implement the flip, run the tests that cover the change, set `Status: overridden -> <option>` in the file.
2. If the flip invalidates a later entry, re-open that entry and say so before touching it.
3. Re-emit only the changed rows, plus any entry the flip re-opened.

A quoted row with no option means "explain this one" - answer in two sentences, do not change anything.

## Never

- Batch the log at the end from memory.
- Summarise entries in the final message instead of printing the rows.
- Treat "I mentioned it in the message where I did it" as logged.
