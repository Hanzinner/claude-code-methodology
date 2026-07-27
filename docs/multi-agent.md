# Multi-agent: running a swarm of long-lived Claude Code sessions

A single operator running ~28 named agents — each a separate long-lived session with its own folder,
briefing, and scope. Some write code in parallel branches of one repo; others handle narrow domains.

Everything below is failure-driven. Each mechanism exists because something broke, and every number
here is measured, not estimated. The most useful part is probably [What we got wrong](#what-we-got-wrong) —
the mistakes cost more than the design.

## Why split at all

Splitting one agent into many is not free. It buys parallel work and smaller contexts; it costs a
**coordination tax** — and by default, the human pays that tax personally.

> The trigger for this entire writeup was the operator saying: *"I can barely keep track of what one
> agent is doing — and now there are three?"*

Split when a domain has its own vocabulary, its own sources of truth, and work that would otherwise
starve behind unrelated tasks. Not to "organize things".

## Failure modes and what addresses them

| Component | Failure mode it addresses |
|---|---|
| `agent-identity` (name → agent) | The hook keyed off `cwd`, but the operator never starts sessions from an agent's folder. **The whole delivery layer was dead for a month and nobody noticed.** |
| `inbox.md` + persistent ping | A file nobody is told to read is not a channel. Items sat unread for days; the human hand-carried messages instead. |
| `.watchlist` (delta of shared files) | Coder agents talk through shared repo files and **commit** them. The addressee never learns he was written to. |
| Cron as release runner | Any *agent* runner must be woken by the human — the message-bus problem just moves one step up. |
| "State lives in git, not in docs" | A briefing that described *current state* was **wrong within half a day** — and the hook then delivered that lie on every single turn. |
| `MISTAKES.md` + weekly pattern review | One mistake is chance; three identical ones are a design hole. You cannot see repeats if postmortems are scattered across chats that get compacted tomorrow. |
| `flock` on every shared file write | Agents, crons and helpers all did read-modify-write on the same files. Three collisions in one day. |

## 1. Delivery: a channel nobody reads is not a channel

Three layers, in the order they must exist:

1. **Identity.** The session must know *which* agent it is. Keying this off `cwd` looked obvious and
   was wrong: the operator works from the repo root, always. Now the agent's **name in the opening
   message** resolves to its folder (`~/.claude/agent-identity/<session_id>`), with a deliberately
   narrow match — the prompt must essentially *be* the name, so that "ask the network agent about X"
   mid-work doesn't hijack the session.
2. **Inbox.** Cross-agent messages land in `inbox.md`. The hook injects **only unprocessed items**
   from the `## New` section — never the whole file, never the processed archive (which only grows).
   Critically, it pings **every turn while items hang**, not once on change: a one-shot notification
   loses anything filed while the agent was elsewhere.
3. **Shared-file deltas.** Coder agents coordinate through shared repo files. Since they **commit**
   those changes, `git diff HEAD` shows nothing — so the hook keeps a **snapshot** per session and
   shows only the diff against it. Full dumps are impossible anyway: the shared backlog file is 71 KB.

**The trap we walked into:** the same hook injected an outdated briefing on every turn.
**Delivery without freshness is industrialized staleness.** Fixing delivery *raises* the cost of
stale docs — it guarantees the lie reaches the context.

## 2. Mechanism beats agreement

The rule "never run git as root, always as the owning user" existed for months, written down,
in the always-loaded instruction file. Then an agent ran a history-rewriting command in the main
repo: **808 commits → 125**, whole directories gone from history. Recovered from a backup taken
20 minutes earlier; nothing lost.

The chain: repo owned by user `A`, every agent runs as `root` → clone fails on ownership → `cd` into
the non-existent clone fails → **no `set -euo pipefail`** → the destructive command runs *in the
current directory*, i.e. the main repo.

The tempting fix is a guard hook that blocks and scolds. The operator's reaction reframed it:
*"this root/user thing has been showing up forever, since git existed here"*. That is not an
incident — it is a **structural gap**, and the rule demanded that every agent remember a workaround,
forever, on every command.

> A rule that requires everyone to remember it forever is not a rule. It's a deferred outage.
> The agent didn't "forget" — statistically, someone was bound to not remember.

So: don't guard the gap, **remove it**. A transparent `git` wrapper redirects to the owning user
inside the repo. Nobody has to remember anything; ownership is simply always correct.

The guard hook still exists, but only for what a wrapper can't fix: **destructive git in the main
repo is blocked outright, even for the right user** — correct ownership doesn't stop you shooting
someone else's tree.

## 3. The human must not be the message bus

Two agents deadlocked for 2+ hours: both claimed the same release number, both then politely
yielded and waited for each other. One wrote "waiting for X" **in its own chat** — so that message
did not exist for anyone else. The human unstuck them by pasting a screenshot from one chat to another.

Notably, the automatic gate was *right* to refuse every forceful exit (stealing the lock, overwriting
shared artifacts). **The system had no legal way out of the deadlock from the inside** — only through
a human.

What we concluded:

- **Version numbers must not be a resource.** The collision existed only because the number is
  claimed *early* (written into a source file while work is in progress). Assign it **at release
  time, from tags**, and an entire class of collisions disappears — one patch, no protocol change.
- **The releaser must be a cron, not an agent.** This is the key point: an *agent* releaser has to
  be woken by the human — the bus problem moves up a level rather than going away. A scheduler
  wakes itself. Humans are out of the loop **by construction**, not by agreement.
- **Preconditions come first.** A pull-based release over a dirty main branch is worse than the
  disease: a nightly snapshot cron was committing whatever lay on disk, so **one agent's unverified
  experiment shipped inside another agent's release**. Fix "main = intentional state" *before*
  centralizing releases, or you get one throat instead of three and the same illness.
- **Don't block on another agent.** Write to the channel and keep working. A deadlock requires
  *both* sides to freeze. If waiting is unavoidable, the waiting state goes **in the channel**, not
  in your own chat.
- **Locks need a TTL and a takeover rule.** Without them, the polite agent deadlocks and the
  impolite one wins. A lock that sat for two hours after its owner changed their mind is not
  coordination.

## 4. Don't write state into documents

A briefing said "network agent — research phase, next up: ARP" and "design agent — idle".
Reality, half a day later: the network code was in the kernel, and the design agent had shipped a
tagged release. The doc had a **date on it** and was still wrong — dates mark suspicion, they don't
create freshness, and readers believe prose.

**The test, applied to every line:**

> *Can this become false without anyone editing this file?*
>
> **Yes** → it's **state** (who's busy, current version, "next batch is X", branch status).
> It does not belong in the doc — link to where it actually lives.
> **No** → it's **durable** (role, boundaries, rules, the *why* behind decisions, lessons). Write it.

Priority of fixes: **remove the duplicate > generate it from source > warn about age > rely on memory.**

The same logic answers "how do I know if another agent finished?":

> **Check the source, don't quote someone's todo.** Work is material — a hook was written means the
> code changed; `grep` proves it in a second. Between "done" and "written down" there is always a
> window, and in that window files lie.

We explicitly **rejected** claim-first ("announce that you started, then do it"): it doesn't remove
the window, it moves it (the claim also has to be written in time), it's state-in-a-file again, and
a claim without a TTL is just a lock — which had already cost two hours that same day.

## 5. Inbox is a mailbox, not a desk

An empty inbox is the **normal** state, not an achievement.

Arrived → read → either do it now (if trivial) or **move it into your own todo and close the inbox
item**. Work lives in the todo. Two reasons:

- Hanging items get pinged **every turn** — a big task parked in the inbox eats context forever.
- **The move is a verification point.** You re-check whether it's still true instead of copying
  blindly. An item that sat for a week is a snapshot that may have rotted.

## What we got wrong

The postmortem log (`MISTAKES.md`) exists so repeats become visible; a weekly cron asks for a
**pattern** review, not a list. Two patterns surfaced on day one:

**Pattern 1 — "announced a result you never verified": 5 cases, 3 different agents, one day.**

| Announced | Actually | Verification would have cost |
|---|---|---|
| hook "LIVE" for a month | never executed **once** | listing the marker dir — it was empty |
| "causality confirmed" (twice in a day) | was measuring other agents' test processes | the A/B the same agent ran *later* |
| "the test rig is flaky" — written as **fact**, advising others not to dig | a broken shared socket | actually looking (someone else did) |
| "the script ran → task moved" | heading didn't match; the task vanished | reading the file after writing |
| "the watchlist is done" | built on the same variable that made the hook dead | asking *why* the existing code was dead |

A cheap signal — "the code looks right", "it went green", "the command didn't fail" — was taken as
proof. **In a swarm this is more expensive than solo:** a solo agent just re-runs. Here, one
unproven claim traveled through three agents and landed in a shipped release tag.

The mechanism is **proof next to the claim**: not "done", but "done, evidence: `<command/tag/log>`".
Anything without evidence is a hypothesis and must be labelled one. Still culture, not a gate —
which is exactly why it's logged as open.

**Pattern 2 — "shared things have no owner": 5 resources, rotting for a long time.**
Shared test socket · the main working tree · the git index (cron vs agents) · git itself as a domain ·
the inbox files. The sharpest formulation came from one of the coder agents auditing himself:

> *Strictness switched on depending on whose thing it was* — I bisected my own code, but wrote off
> the shared rig as "flaky", because re-running was free.

Fixes: an explicit **owner** per shared resource; `flock` for every writer; and making "just re-run
it" **not free** (an instability counter), because as long as it is free, a shared bug lives for years.

Honest note: while writing *this very section*, two attempts to edit the postmortem file failed with
"file changed since read" — another agent was writing concurrently. The pattern demonstrated itself
mid-description. The write finally went through under a lock.

## What this costs

- Cross-agent "dial" (one agent invoking another live) was tried and **rejected**: always a cache
  miss, several percent of quota per call. Files plus hooks do the same job in milliseconds.
- Every mechanism here is a hook, a file convention, or a cron — deliberately. Anything that needs
  an agent to be awake needs a human to wake it.
- The single most valuable habit is unglamorous: **prove that the mechanism ran**, don't verify that
  the code looks correct. One month of a dead hook was the tuition.
