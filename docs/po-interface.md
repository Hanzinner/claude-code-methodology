# Agent reports vs. the human: what reaches the operator, and what doesn't

Problem: a swarm of agents writes ~30 technical reports a day. The human (product owner, not a developer)
has no capacity to read them, and fears missing the important one through fatigue.

Root cause: a report does **two jobs that got glued together**.

1. **Engineering record** — for other agents, for the future, for the mistakes journal. Must be technical. Correct as is.
2. **Operator awareness** — must be flat, filtered, product and decisions only.

The agent writes (1) and sends it as (2). The fix is to **split them**. Technical body goes to the project
lead agent's inbox and to git. The human gets three lanes, below. Portable: nothing here is specific to one project.

## Routing rule

- **Report body (technical) → lead agent's inbox + a git commit.** Not addressed to the human. It lives there.
- **The human receives only the three lanes below.** Everything else the lead agent resolves. **Default = silence.**

## Hard filter: is this for the human at all (both must be "yes")

1. Is it **taste / product / priority / irreversible**? (what it should DO or look like; which epic is next; publishing, money, the human's own machine, anything external.) Versus **technical** (how to build it) — technical never goes up; it is the agent's or lead's call.
2. **If the human decided the opposite of the agent's default, would anything in the world change?** No → it's a habit of asking. The lead cuts it.

The lead agent is **not a pass-through; it is a killer of fake questions.** Assume most "ask the human"
items are reflex, and cut them. The only legitimate reasons to surface: a product/consent decision · an
irreversible or external action · a real block only the human can lift. A loop fails when it stops to ask
where it should have decided.

## The three lanes

1. **Shipped** (FYI, scan or skip) — flat lines taken from **commit subjects** (agents already write them without jargon — a briefing rule). Assembled by a script, zero manual work. Internal plumbing (output mirroring, refactors, gates) is not listed: no product meaning.
2. **Needs a decision** — taste/product/priority, only the human can say. Each as one flat line plus what to choose. Source: each agent's "for the human" todo file, passed through the filter by the lead (stale items and habit items cut). **Split in two — do not mix them, or you rebuild false urgency:**
   - **Blocker** — the agent is actually stuck without it, nothing else in its queue. Rare. Only this is urgent.
   - **Direction** — picks a path or look, but the agent works on something else meanwhile. Common. **Not urgent — waits for the human's convenience.**
   - **Test:** "does the agent keep going without this decision?" Yes → direction. No → blocker. The lead must check the agent's todo/activity **before** calling anything a blocker, not by eye. (Failure, 2026-08: two directions were presented as blockers; the human caught it.)
3. **Look with your eyes** (visual / hardware checks only the human can confirm) — batched for when the human is at the machine. Doesn't block, but only they can confirm.

## Pull mode: the human pulls by mood, the panel doesn't push

The human arrives in some state and names a mode; the lead serves the matching lane. Pull under current capacity, not push.

| Human says | Served |
|---|---|
| "give me decisions" | Decisions lane — blockers first, then directions. Works from anywhere (mockups/URLs). |
| "let me click" | Look-with-eyes lane, as a batch. Needs the human **at the test stand** — don't serve it otherwise. |
| "report / what's up" | Shipped digest, flat. |
| "what's on fire" | Blockers only. Empty is normal, and the most common answer. |

Reason: the human works by mood and drive, not by schedule. Heavy work (decisions) is taken when there is
capacity; light work (clicking) when there isn't. The lead does not decide for them which mode they are in.

## Don't let a direction rot: auto-promotion

The trap of "important, not urgent" is that it **rots**: left long enough, it suddenly becomes urgent.
So: **direction → blocker automatically** when the owning agent has no other work left on that path (a
direction with no way around it is already a blocker). This removes the fear of "I postponed it and forgot":
the system promotes it when it ripens, not the human's memory. *(Mechanism: a gate on the board — an item moves direction → blocker if the owner's queue on that path is empty.)*

## Why not a plain Eisenhower matrix (important × urgent)

Considered. It doesn't fit as is: the "important" axis **does not route** here. An important technical
item — a data-loss fix on a full disk, maximally important and urgent — is still not the human's. The
primary axis is **whose call it is** (human: taste/product/priority/irreversible; swarm: technical);
urgency is secondary and applies only to what is already the human's. Two things were taken from Eisenhower:
the strategic quadrant (direction) and the "don't let it rot" rule (auto-promotion).

## What does not reach the human

Technical choices · internal quality/plumbing · "is this ok?" / "continue?" (default: yes) · progress · anything that fails the filter above.

## Mechanics (cheap)

- **Shipped:** a script over `git log` subjects. Plain language is already enforced by the briefing.
- **Decisions / look-with-eyes:** a server aggregates the agents' "for the human" todo files into blocker / direction / look lanes, with the auto-promotion above.
- **Lead digest:** the lead agent folds the three lanes into one stream/board. The human reads only that.
- **Briefing rule** (sent to every agent): "report body → lead/git; to the human only through the hard filter, one flat line in the 'for the human' todo file (decision / check)."

## What this gives

30 reports a day → **1 digest + 2–3 real questions.** The human doesn't miss the important item through
fatigue: decisions and checks are lifted to the top and don't drown; the technical part was never meant to reach them.

Related: [`multi-agent.md`](multi-agent.md) · [`mission-control.md`](mission-control.md) · [`dev-methodology.md`](dev-methodology.md)
