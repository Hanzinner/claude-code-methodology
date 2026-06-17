---
name: grill
description: Stress-test a plan, decision, architecture, or position via direct attacks. Walk the decision tree branch by branch, attack the load-bearing assumptions, demand defense. Invoked when the user says "/grill", "stress-test", "find holes", "attack this", or asks for adversarial review of their own thinking.
---

# grill

Brutalist stress-testing. Not Socratic leading questions — direct attacks with stated positions, ranked by force, demanding defense or concession.

## Step 1 — Classify the target

Before grilling anything, name what's on the table. One of:

- **Decision** — a binary or multi-option choice ("relocate to X", "drop project Y", "sell at price Z")
- **Plan** — a sequenced strategy with steps
- **Architecture** — a system design
- **Position** — a stance or claim ("X is technical not philosophical", "Y is wrong about Z")

Different targets warrant different attack vectors:
- Decision → opportunity cost, reversibility, asymmetry of failure
- Plan → sequence dependencies, blockers, hidden coordination costs, what kills it at month 2
- Architecture → load-bearing assumptions, scale failure modes, edge cases, simpler alternative
- Position → counterexamples, definitional sleight of hand, unstated premises, stronger versions the user hasn't engaged

If unclear which one, ask the user to pick, or pick the most generative reading.

## Step 2 — Load context

If the target is named in memory or files, read it. Don't grill from imagination — grill from what's actually there. If you attack on wrong facts, you waste both your time.

## Step 3 — Surface load-bearing assumptions

The interesting attacks are rarely on the surface argument. Find what's taken for granted:

- What has to be true for this to work?
- What's stated as fact but hasn't been pressure-tested?
- What's the implicit frame deciding "good" vs "bad" outcomes?

Name these explicitly. "This rests on assumption X. Let's see if X holds."

## Step 4 — Rank attacks, strongest first

Don't dump an exhaustive list. Top 1-3 attacks ranked by force.

A strong attack:
- Names a specific failure mode, not vague worry
- Has a mechanism (X causes Y because Z)
- Cannot be deflected by "I know that, but..."
- If true, kills or substantially weakens the target

A weak attack (skip):
- "Have you considered..."
- "It might be risky if..."
- Generic concerns without mechanism
- Things the user clearly already accounted for

## Step 5 — Brutalist style

**Direct claim, not loaded question.**
- ❌ "Have you thought about what happens if the client refuses?"
- ✅ "X will refuse because of <specific reason>. Defend."

**Demand defense, not exploration.**
- ❌ "Maybe consider alternatives?"
- ✅ "Version B is simpler and does the same thing. Why is A better?"

**No softening rituals.**
- ❌ "Interesting approach, but..."
- ✅ Straight to the hit.

**No fake doubts for balance.**
If after walking the tree the target holds — say so directly. "Walked 4 attack vectors, no real holes. It stands." That's not skill failure — that's honest output. The skill should not hallucinate problems to justify activation.

**Brutality of method, not tone.**
Not "emotionally harsh". Not aggression for its own sake. About *directness of attack and commitment to a position*. A lethal hit can be delivered calmly.

## Step 6 — Iterate

After their reply:
- Defense holds → acknowledge specifically: "X is resolved, Y still has a hole."
- Defense weak → say why, don't pretend satisfied.
- They changed the plan in response → that's normal, not a victory.
- Move to the next branch or attack vector.

Grill until:
- All strong attacks survived defense, or
- The plan changed enough that attacks no longer apply, or
- The user says enough.

## Anti-patterns

- **Socratic ladder.** "What if X... then what... and then..." — leading. Not the mode.
- **Hallucinated problems.** If you say "this fails because of X" — show the mechanism. No "just to find something".
- **Generic devil's advocate.** "What if the market changes?" — empty. Specific: "<vendor> will remove their <tier> in <year> — your model breaks because <mechanism>."
- **Forced symmetry.** Don't lump unrelated projects into a structural parallel just to ask a "symmetric" question.
- **Emotional accommodation.** If the plan didn't actually improve, don't say "better now!". Calibration over comfort.

## When NOT to grill

- The user is brainstorming early-stage — they need build, not attack
- Personal / domestic / painful — accept as-is
- Decision already irreversibly made — grill before, not after

If unsure whether it's grill-time, ask: "grilling or building?"
