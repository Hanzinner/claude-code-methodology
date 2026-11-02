# From rule to mechanism: the gate ladder

A written rule does not stop a mistake. It was written, it was in the always-loaded instructions, and the
same mistake happened again — across agents, for weeks. What stops a mistake is a mechanism, and
mechanisms come in three strengths:

| Rung | What it is | What it does |
|---|---|---|
| **1. Note** | A rule in a file | Nothing, on its own. It works only while someone remembers it. |
| **2. Detector** | A hook that notices and says so | Makes the mistake visible — a flag, a hint on the next turn, a log line. |
| **3. Structural impossibility** | A gate or a design with no path to the mistake | The mistake can't happen, or can't pass silently. |

Everything below is a rule that was moved up this ladder, after the rule alone failed. The trigger for this
round: in two days the operator corrected agents about **30 times**, and the most expensive corrections were
not about code — they were about the **order of steps**. The steps were already written down. None of four
agents followed them.

> **On results:** the effect of these mechanisms is being measured against that baseline. It isn't claimed
> here until it is measured — see [`measurement-and-proof.md`](measurement-and-proof.md) for why.

## 1. The change cycle

For any change to code, a script, a rule or an installation:

| Step | What | What it cost when skipped |
|---|---|---|
| **0. Look how it's done** | Before the first command on a new technology: search how people deploy it and its known issues; read your own playbook **in full** (not by grep); check what the swarm already has. Put a `source: …` line in the report. | 40 attempts in 40 minutes on an OS the tool doesn't support — a search answered it in one minute. The right disk image was in the playbook, "read" by grep. |
| **1. Requirement → where it's checked** | Every requirement maps to a `file:line` where it runs, and how it's verified. No line → no run. | Two requirements sat in the briefing but not in the layer that acted — an hour of wrong behavior before anyone noticed. |
| **2. Reference data before live** | A threshold/filter/rule runs first on reference or synthetic data with edge cases (window boundary, overfull set, empty field, known negatives). Live comes after. | A detection rule "proven" on three clean environments; other models then found ~20 bugs; 13 hours to actually done. |
| **3. Independent review** | Not the author. At minimum a fresh subagent that didn't see the code being written; for anything critical — **a different model**, given the step-1 table and the "why" log so it doesn't advise reverting fixes already paid for. | Self-review found 5 defects. Other models found ~20 more. The overlap between models was close to zero. |
| **4. Done = proof** | "Done / works / proven" only together with the output of a run through the production path, in the same message. Anything handed to a human (a script, a shortcut, instructions) — the agent ran it at least once itself. | A script for the operator went through three versions; the operator caught each one. A hook was dead for 33 days. |
| **Stop rule** | Three failed attempts in a row → stop, go to step 0. Not a fourth attempt. | |

Scale: a one-line fix needs steps 0 and 4. The rest need all of them — ceremony matches risk.

**This package went through the cycle it describes.** Running the installer the way a user would (step 4)
found 4 defects the files alone didn't show: the installer copied no Python hooks at all, the settings
template registered none of the hardening hooks, commands broke on a path with a space, and one new hook
crashed when `~/.claude` didn't exist yet. Two passes by a different model (step 3) then found 7 more — the
worst a **command injection** that had lived in the installer since its first version (a project path with
an apostrophe ran an arbitrary command), plus a redirect that made any `.htm` or upper-case `.PDF` file
permanently unreadable to the agent. Overlap between what the author found and what the reviewers found:
**zero.** All 11 are fixed, each with a run that shows it.

**Moved up the ladder:**
- Step 0 → [`hooks/stuck-detector.py`](../hooks/stuck-detector.py): three failed Bash calls in a row inject "stop, look it up" (rung 2).
- Step 3 → [`scripts/cross-review.sh`](../scripts/cross-review.sh): a fresh `claude -p` with another model, read-only tools, reviewing a diff against the requirements (rung 2, as a tool). Lesson from building it: `--allowedTools` only *adds* permissions — the first "read-only" run wrote into live logs. Only `--tools` restricts.
- Step 4 → [`hooks/proof-guard.py`](../hooks/proof-guard.py): a completion claim after code edits with no successful run gets flagged (rung 2). In the private setup it now blocks the end of the turn: after a week of calibration it fired 3 times in 423 turns with code edits, all three correct. Detector first, measure false positives, then block.

## 2. Lessons in front of the hand, not in a postmortem

Postmortems record lessons; nobody re-reads them at the moment they matter. So technical lessons live in
one place per technology — [`code-pitfalls/`](../code-pitfalls/) — and
[`hooks/code-pitfalls-hint.py`](../hooks/code-pitfalls-hint.py) shows the matching **headings** right before
an agent edits code of that kind. The top repeats were unglamorous: a signal taken for proof, `pkill -f`
killing its own shell, a shared file written without a lock, `sleep` racing an event. The private set this
comes from held ~220 such lessons (November 2026); the folder here is a seed.

## 3. A catalog against two kinds of lie

A swarm accumulates mechanisms faster than anyone remembers them, and two lies follow:
**"done but not documented"** (someone rebuilds it) and **"documented but not done"** (someone trusts it).
The fix is one hierarchical catalog of every mechanism and system document — one machine-readable line per
file, with tags for what it is (`hook:<event>`, `cron`, `tool`, `stale?`, `orphan`…) — plus a nightly check
that every listed path exists, every script in the hook config and crontab has a line, and a line's hook tags
match what the script is really subscribed to. Findings go to the catalog's owner as one letter; no findings,
no letter. This check was itself "documented but not done" for a while: the catalog promised it, an audit of
this very article caught the claim, and only then was it built. Two helpers make it hold: a
broken-link sweep, and a rule that renaming a document goes through a tool that rewrites references (a gate,
rung 3). The first version was reported "tested" — and passed **0 of 5** acceptance checks.

## 4. A supervisor that checks the work, not the process

A restart policy already existed. A bot still lay dead for a month — `active`, with hundreds of restarts —
while the watcher "successfully" watched nothing. So the supervisor checks that each mechanism **does its
job** (writes its data, answers, moves its log), not that a process is alive:
1. a failed check → restart → check again;
2. **3 restarts in an hour → stop restarting, escalate** — a restart loop is a symptom, not a fix;
3. escalation goes to the owning agent; only a human-actionable item reaches the operator, as one line;
4. **dead-man switch:** the supervisor and the delivery hook watch each other — if either stops writing its
   heartbeat, the other says so.

First real test: three restarts healed a service; the fourth attempt stopped and escalated, as designed.

## 5. Nightly memory review — read-only, on purpose

Shared memory rots: contradictions, stale dates, duplicates, broken links. A nightly job hands it to a fresh
model that may **only read** and writes a report. It never edits. The memory's checksum is taken before and
after — any change is an alarm. Auto-fixing memory is exactly how a wrong guess becomes a shared "fact" for
every agent (memory poisoning), so the fix step stays with an owner who reads the report.

## 6. The mistakes journal, with a class index

The [journal](mistakes-journal.md) got an index at the top: each **class** of mistake, how many times it
occurred, and which mechanism now covers it. Examples of classes: "done without a run" (20+ times, 8+ agents),
"a command that killed itself" (8+), "a shared file without a lock" (7+), "self-review by the same model",
and a new one — **"silent death"**: something broke and nothing shouted (a watcher guarding emptiness, a
script dying before its log line, a hook without `+x`, a service "up" but writing no data). A gate enforces
the entry-header format, and a weekly review looks for repeats. A repeat is a work order for a mechanism.

## 7. Splitting an agent at the seam

One infrastructure agent became two, and the criterion is a question, not a topic: **"can this be tested in
a sandbox?"** Yes → the *dev* agent (hooks, scripts, tools). No → the *infra* agent (the live system:
schedules, services, network, backups, secrets) — including code whose correctness *is* the live system's
state. Two rules keep the seam clean: **one author per shared file**, and an explicit incident seam — infra
patches the live system, dev fixes the cause with a test, infra closes the incident.

## 8. How a project lead sets priorities

A priority scale says how to *write* a priority; this says how to *decide* it. Walk the rules top-down; the
first that fires gives the band:
1. **Epic order belongs to the human.** The lead orders stories inside the current epic; doubts about epic
   order go to the human as a one-line choice.
2. **Unblocks another agent → 90+.** Someone waiting costs more than anything of your own. (One handoff landed
   where the recipient couldn't see it: 5.5 hours lost.)
3. **Broken in the human's hands** (a tool they use daily) **→ 90+**, before anything new.
4. **Irreversible or dated** (a deadline, data about to disappear, a closing window) **→ 70+.**
5. **An extra-small task that unlocks something** → do it now, no queue.
6. **The rest** by value to the current epic's Definition of Done.

The order lives **in the queue**, not in the lead's briefing — a "current priorities" list in a briefing was
stale within days. And agent boundaries are drawn **by question, not by topic**: "who answers *this kind of
question*?" survives new topics; "who owns *this topic*?" doesn't.

## 9. Small lessons that bought a lot

- **Gates block themselves.** A new gate denied the very commands needed to repair it. Run your own repair
  path through a gate before shipping it.
- **A lost file can be rebuilt from the session log.** The transcript holds the last full write plus every
  edit after it; replaying them reproduced the file exactly — checked byte-for-byte on 7 files.
- **Audit freshness in parallel, read-only.** Five read-only auditors swept ~240 documents for stale claims
  in one pass; none could change anything, so none could make it worse.
- **"Live" only with proof it ran.** Still the most repeated lesson, and still the cheapest to check.
