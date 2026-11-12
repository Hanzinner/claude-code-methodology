# MISTAKES — the swarm's mistakes journal

> **Rule: you broke something and figured it out → write it here, at the top, now.** Any agent.
> Not a punishment, not a confession — **fuel for mechanisms.** One mistake is chance; three of the same
> kind are a hole in the construction that needs a mechanism. You only see the repeat if all mistakes
> live in one place, not in chats that get compacted tomorrow.
> **Write down what turned out fine by luck** (a backup saved it, the human caught it) — the most valuable kind.
> Don't write typos. The test: "could another agent trip on this?"
> A technical lesson (code, script, service, VM, git) also goes to `code-pitfalls/<technology>.md`:
> here is the story, there is the lesson an agent sees before it edits that kind of code.

## Before writing — is it a repeat?

Mistake looks like a row below → end your heading with `[class №N]`. These classes repeated across our
agents; the right-hand column is what guards each one in this repo.

| № | Class | Guard in this repo |
|---|---|---|
| 1 | "Done / works / proven" without a run (a signal is not proof; tested by another path than production) | `hooks/proof-guard.py` |
| 2 | A fact about the world without a primary source | none shipped |
| 3 | A command killed itself (`pkill -f` matches its own shell) | lesson in `code-pitfalls/shell.md` |
| 4 | A shared file written without a lock (inbox, log, git index) | `multi-agent/inbox-post.sh` |
| 5 | Wrong direction: started without looking at how it is done | `hooks/stuck-detector.py` |
| 6 | Self-review by the same model | `scripts/cross-review.sh` |
| 7 | Ignored a written mandatory file or an explicit constraint from the human | none |
| 8 | Strawman / risk invented on neutral input | none shipped |
| 9 | Fixed `sleep` against an event of variable length | lesson in `code-pitfalls/shell.md` |
| 10 | Silent death: something broke and nobody shouted (empty log, hook without +x) | `hooks/hook-safe.sh` + `hooks/surface-flags.sh` |
| 11 | An alert arrived, nobody acted | none |
| 12 | A test wrote into live state | `TEST_MODE=1` convention, `docs/coding-standard.md` §2.4 |
| 13 | A mechanism keyed on the text of a command, not on the action or identity | none |
| 14 | Slop in a text for a human | `docs/hall-of-shame-docs.md` |
| 15 | A mechanism didn't move to a new project (only the text "how we did it" did) | none shipped |
| 16 | Edited what is running right now (a script mid-run reads the changed file) | lesson in `code-pitfalls/shell.md` |

New class: add a row when the same kind shows up a second time. Don't keep counters here — they rot; count with `grep`.

## Entry format

```
## YYYY-MM-DD · <agent> · <gist in one line> [class №N]
**What happened:** the fact, no excuses.
**Why:** the root cause, not the symptom.
**Fix:** what you did — CONFIRMED by a run, not a hypothesis.
**Can it be made impossible:** yes/no + how (hook / wrapper / gate). Repeat of a class → name it.
**Status:** OPEN · ACCEPTED · MECHANIZED (<path of the mechanism>)
```

`OPEN` = a mechanism is possible and not built yet · `ACCEPTED` = discipline only, no mechanism will
come · `MECHANIZED` = closed by a mechanism; move the entry to `MISTAKES-archive.md`.

---
<!-- new entries go right below this line, newest first -->
