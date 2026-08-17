# The mistakes journal: turning repeats into mechanisms

One file. Every time an agent breaks something **and figures out why**, it writes the postmortem there —
immediately, while it's fresh. Not punishment, not confession: **fuel for mechanisms.**

The reasoning is in [`measurement-and-proof.md`](measurement-and-proof.md) and
[`multi-agent.md`](multi-agent.md); this is the practice and its template.

## Why one file

**One mistake is chance. Three identical ones are a design hole** — something that should be mechanized,
not re-remembered. You can only see the repeat if the postmortems sit in **one place**. Scattered across
chats that get compacted tomorrow, the pattern is invisible and the same mistake recurs for months.

So the value isn't the individual entry — it's the **pattern review**: periodically (a cron, or a human)
asks "what recurs?", and a recurring root cause becomes a work order for a gate/hook/wrapper.

## Entry format

```markdown
## <date> · <who> · <one-line what happened>

**What happened.** The fact, no excuses.
**Why.** The root cause — the mechanism, not the symptom.
**Fix.** Confirmed (it worked), not a hypothesis.
**Preventable?** A hook/gate/wrapper — or honestly "no, only attention".
**Status.** OPEN | MECHANIZED | ACCEPTED
```

Two rules that make it work:
- **Record the near-misses too** — the accident that *didn't* happen but could have (a backup saved you,
  a human caught it) is the most valuable entry, because it's a hole you haven't paid full price for yet.
- **"Preventable?" is the point.** If the answer keeps being "only attention" for the same class of
  mistake, that's the signal to build a mechanism — the honest admission is what triggers the fix.

## A worked example (generic)

```markdown
## 2026-05-12 · agent · claimed a hook was live; it had never run

**What happened.** Reported the guard hook as "installed and live" on the evidence of `crontab -l`
plus a file on disk. Under cron it had never once executed — an empty PATH made it fail silently.
**Why.** "Live" was proven from *configuration* (the entry exists) instead of *execution* (an artifact
only the hook's own run could produce). A recurring root: proof-by-config.
**Fix.** Confirmed by checking the hook's own output marker in a real cron run — it was empty, so the
claim was false; fixed the PATH and re-verified from the marker.
**Preventable?** Partly — a rule "prove execution, not config" is still discipline. A stronger gate would
require the marker before a component may be tagged live.
**Status.** ACCEPTED (culture) — escalate to a gate if it recurs.
```

The format is deliberately small so writing an entry is cheaper than not writing one. The discipline is
just: **the moment you understand a mistake, before you move on, write it down here.**
