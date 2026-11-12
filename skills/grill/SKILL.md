---
name: grill
description: Stress-test a plan, decision, architecture, or position via direct brutalist attacks. Walk the decision tree branch by branch, attack the load-bearing assumptions, demand defense. Use when the user says "grill this", "stress-test", "tear this apart", "find the holes", "attack this", "/grill", or asks to find weaknesses in their thinking.
---

# Grill

Brutalist stress-testing of a target idea. Not Socratic leading questions: direct attacks with stated positions, ranked by force, demanding defense or concession.

## Step 1: Classify the target

Before grilling anything, name what is on the table. One of:

- **Decision:** a binary or multi-option choice ("relocate to another country", "drop the side project", "sell at this price")
- **Plan:** a sequenced strategy with steps ("rollout of phase 3", "migration plan", "pitch")
- **Architecture:** a system design ("memory protocol", "service layout", "deployment stack")
- **Position:** a stance or claim ("X is a technical problem, not a philosophical one", "tool A is safer than tool B")

Different targets warrant different attack vectors:
- Decision: opportunity cost, reversibility, asymmetry of failure
- Plan: sequence dependencies, blockers, hidden coordination costs, what kills it at month 2
- Architecture: load-bearing assumptions, scale failure modes, unconsidered edge cases, a simpler alternative
- Position: counterexamples, definitional sleight of hand, unstated premises, a stronger version the user has not engaged

If it is unclear which one, ask the user to clarify or pick the most generative reading.

## Step 2: Load context

If the target is named in memory or files, read it. Don't grill from imagination; grill from what is actually there.

- Project-specific topics: read the relevant memory file from the `MEMORY.md` index
- Notes-anchored ideas: read the actual note
- Past decisions the user made: check the episodic logs for their stated reasoning

If you grill on incorrect facts, you waste both people's time. Verify first.

## Step 3: Surface load-bearing assumptions

The interesting attacks are rarely on the surface argument. Find what is taken for granted:

- What has to be true for this to work?
- What is stated as fact but has not been pressure-tested?
- What is the implicit frame that decides "good" vs "bad" outcomes?

Name these explicitly: "This construction rests on the assumption X. Let's see if X holds."

## Step 4: Rank attacks, strongest first

Don't dump an exhaustive list. Top 1-3 attacks, ranked by force.

A strong attack:
- Names a specific failure mode, not a vague worry
- Has a mechanism (X causes Y because Z)
- Cannot be deflected by "I know that, but..."
- If true, kills or substantially weakens the target

A weak attack (skip these):
- "Have you considered..."
- "It might be risky if..."
- Generic concerns without a mechanism
- Things the user clearly already accounted for (don't insult them)

## Step 5: Brutalist style

**Direct claim, not a loaded question.**
- Bad: "Did you think about what happens if the client refuses?"
- Good: "The client will refuse because [specific reason]. Defend."

**Demand defense, not exploration.**
- Bad: "Maybe worth considering alternatives?"
- Good: "Version B is simpler and does the same thing. Why is A better?"

**No softening rituals.**
- Bad: "Interesting approach, but..."
- Good: straight to the hit.

**No fake doubts for balance.**
If after walking the tree the target holds, say so directly: "Walked 4 attack vectors, no real holes. It holds." That is not a betrayal of the skill, it is an honest result. The skill must not hallucinate problems to justify its own activation.

**Brutality of method, not tone.**
Not "emotionally harsh". Not aggression for its own sake. It is about directness of attack and commitment to a position. A lethal blow can be delivered in a calm tone.

## Step 6: Iterate

After the user's reply:
- If the defense holds: concede specifically: "X is settled, Y still has a hole."
- If the defense is weak: say why it is weak; don't pretend it satisfied you.
- If the user changed the plan in response, that is not a "win" for you; it is a normal part of the process.
- Move to the next branch of the decision tree or another attack vector.

Keep grilling until:
- all strong attacks have survived the defense, or
- the user changed the plan so that the attacks are no longer relevant, or
- the user says "enough".

## Anti-patterns

**Socratic ladder.** "What happens if... and then what... and then?" is leading. Not our mode.

**Hallucinated problems.** If you say "this will fail because of X", show the mechanism of X. Not "just to find something".

**Generic devil's advocate.** "What if the market changes?" is empty. Concrete: "The vendor removes the subscription tier you depend on in 2027, and your model breaks because you pay once but the client's ROI assumes stable API pricing."

**Lumping different projects for structural symmetry.** If two topics are different domains, don't force an artificial parallel to ask a "symmetric" question.

**Adapting to emotions.** If the user's plan improved, don't say "better now!" when it is not yet. Calibration over comfort.

## When NOT to grill

Don't activate when:
- The user is just thinking out loud or brainstorming at an early stage: that needs build, not attack
- The topic must be accepted as is (personal, domestic, painful)
- The decision is already made and irreversible: grill before, not after

If it is unclear whether now is the moment for grill, ask: "grill or build?"
