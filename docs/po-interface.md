# What reaches the human

For every agent, before it asks the human anything or reports to them. The human is the product owner, not a
developer, and several agents write to them; most of what agents want to say is not for them.

## 1. Is it for the human at all? Both must be "yes"

1. Is it **taste, product, priority, or something that can't be undone** (what it should do or look like, which
   piece comes next, publishing, money, the human's own machine, anything outside)? How to build it is technical:
   not for the human.
2. **If the human decided the opposite of what you would do, would anything change?** No → you are asking out of
   habit. Decide yourself.

Never for the human: technical choices, internal quality, "is this ok?" / "shall I continue?" (the answer is yes),
progress reports. The technical body of a report goes to the project lead's inbox and into git, not to the human.
Default: silence.

## 2. Where to put what passes

| What | Where | How it reaches the human |
|---|---|---|
| 🟥 **Blocker:** the work stands until the human does X | the blocker register only: `scripts/blocker_add.sh <project> "<what exactly>" "<who clears it>" "<check command \| manual>"` (`<project>` is a `Project-*` folder; outside any project give your own agent name: it goes to the shared `<workspace>/BLOCKERS.md`) | by itself: before the human's next message you get a "waiting for you" line (when the set of blockers changes, or every 4 h) and put it first in your reply; cleared by itself when the check passes, and the story moves on |
| 🟦 **Direction:** a choice of path or look, but you keep working on other things meanwhile | one line in your `human-TODO.md` | only counted in that line, once a day; the human pulls the details (section 3) |
| 👁 **Look with your eyes:** a check only the human can make (visual, hardware, "do I like it") | one line in your `human-TODO.md`, marked 👁 | the same; batched for when the human is at the machine |
| 📦 **Shipped** | nowhere: it is in git and the release log | the human asks "what's new" and you answer from `git log` |

- **Blocker or direction?** Ask "do I keep working without this answer?" Yes → direction. No → blocker. Check your
  own queue before calling anything a blocker.
- **A direction ripens:** once you have nothing else to do on that path, it is a blocker. Register it with
  `blocker_add.sh`; a line in `human-TODO.md` saying "waiting for the human" without a register number is not a
  blocker.
- **One line, plain words:** what to decide or look at, and the choices. A choice of look: a picture "now /
  proposed", not CSS numbers.
- **Write a check whenever one exists** (a file appears, a line is in a config, a URL answers): then nobody has to
  remember to clear it. `manual` only when no command can see it; the human clears it with
  `scripts/blockers.py clear <project> B<n> "<how>"`.

## 3. When the human asks

| The human says | You answer with |
|---|---|
| "what's waiting for me" / "what's on fire" | `scripts/blockers.py list` (open blockers with days waiting), then the 🟦/👁 lines from the agents' `human-TODO.md`. No blockers is normal and the most common answer. |
| "give me decisions" | blockers first, then directions, one line each with the choice |
| "let me click" / "let me look" | the 👁 lines as one batch, with links; only when the human is at the machine |
| "what's new" / "report" | shipped work from `git log`, in plain words, no internal plumbing |

The human chooses the mode; don't push a lane they didn't ask for.
