# Case study: seeing without understanding

An observation from a real session — building the `/edit` skill for video breakdown work. The user showed a fan-edit about the September 1973 Chilean coup, scored to a Víctor Jara song. The agent failed both identifications.

Documenting because it captures a boundary that recurs across culturally-specific visual work: the agent sees the pixels, but doesn't recognize what they are.

## The phenomenon

Both parties look at the same pixels. See different things.

**Agent reads:** "man in glasses at the window of an official-looking building, military vehicle in the courtyard, overlay text 'They Shall Not Pass'." Classification: Western documentary about Latin American politics.

**User reads:** "that's Allende at the window of La Moneda on September 11, 1973 — Hawker Hunter jets are about to bomb the palace, and the audio track is his final radio address." Classification: fan-edit about the coup.

Same frame. Two different events in each head.

## The mechanism

Visual recognition works in layers:

| Layer | What it is | Agent capability |
|-------|------------|------------------|
| 1 | Low-level perception (colors, shapes, contours) | ✅ |
| 2 | Basic categorization (person, building, aircraft) | ✅ |
| 3 | Type / class (Hawker Hunter jet, colonial-era architecture, presidential palace) | partial ✅ |
| 4 | Specific identification (Salvador Allende at La Moneda, September 11 1973) | ❌ without context |
| 5 | Cultural-narrative meaning (fan-edit genre pairing the protest song of an artist killed by the regime with the footage of that regime taking power) | ❌ |

Layers 1-3 are OK because they're densely represented in image-text training pairs. Layers 4-5 fail because:

- The agent is trained predominantly on English-language text.
- It "knows" about the coup from text descriptions, not from frames tagged `santiago_coup_1973_lamoneda.jpg`.
- The **text → event** link is strong. The **image → event** link is weak.
- In culturally-specific domains (Latin American history, non-English regional cinema, Eastern European archives, etc), this amplifies.

## Why "a bigger model won't fix this"

Natural hypothesis: more parameters → better vision. Wrong.

Layers 4-5 don't scale with model capacity. They scale with the presence of the right image-text pairs in training. If the internet has 1000 texts describing "Allende final address 1973" and 10 frames of that moment with captions — the model learns the fact from text, not from image.

You can know WHAT an event is without being able to recognize it in pixels. That's not an intelligence deficit — it's a multimodal-data deficit on specific references.

## Predicted exposure in other domains

The same mechanism should show up on:

- **Archival footage from any region underdocumented in English** — Eastern European history, post-colonial African politics, Latin American upheavals, South and Southeast Asian archives
- **Frames from specific films** — especially regional cinema (Iranian new wave, Bengali arthouse, Soviet post-thaw, Filipino golden-age)
- **Regional meme / TikTok visual language** — the agent can decode Anglosphere memes; other language-communities' visual jokes are opaque
- **Architectural styles of peripheral regions** — Soviet brutalism vs Brazilian brutalism vs Japanese metabolism — layer 3 blurs
- **Uniforms / emblems of specific units or eras**
- **Fonts and print styles** (revolutionary posters of any tradition, pre-Latin-script typography)
- **Gesture / body language** — largely a dead zone

## Beyond the visual

The phenomenon isn't unique to vision. It's a general **transfer of training-data cultural asymmetry** onto any modality.

Example from the same session: the user said "Manifiesto" — the agent parsed it as a generic political declaration. User: that's a specific Víctor Jara song, released posthumously after the coup, one of the tracks the fan-edit uses.

Another example: user said "Kaya" — agent parsed as the Bob Marley album. User: no, that's Ahmet Kaya, Kurdish-Turkish singer who died in exile after being persecuted for a song.

Same default-to-English-dominated-reference failure in text as in image.

So this is **not a visual problem, but a culturally-dominant-training problem** — just acutely visible on visual tasks because in text there's a chance to clarify with more words, and a frame can't be clarified without external context.

## What to do about it (agent side)

1. **Context-first protocol on visual analysis.** Before any breakdown, ask: "what is this? when? who made it? what are we looking for?" Baked into the `/edit` skill as forcing intake.

2. **Calibrated humility on culturally-dense topics.** If the topic touches history, cinema, or subculture from a region not centered in English-language sources — the agent should explicitly acknowledge "my defaults may fail here" and ask rather than assert.

3. **User as interpretive interface.** For niche domains, "user sees + agent reads + we assemble" beats "agent does it alone". Not a betrayal of autonomy — a normal division of labor where one has better vision and the other has better semantic coverage.

## Open question

Can this be fixed by **runtime context injection** — preload a corpus of region-tagged visual references with captions before the session? Technically yes, RAG over vision. Value — no. The user brings live context faster than you can maintain a still-incomplete index.

Alternative: domain-specific fine-tune. Expensive. Not economical for one user.

Third alternative: live with the limitation and use the context-first protocol. Current bet.

## Why this belongs in a methodology repo

Two things.

**One:** it's a concrete example of the "know your agent's limits" principle from `methodology.md` §5. Not abstract "AI has limitations" — a specific mechanism (multimodal training asymmetry), a specific class of failure (cultural-narrative meaning), a specific mitigation (context-first protocol).

**Two:** it's an example of how a *user* discovers this. Not from a benchmark, not from a paper — from watching the agent fail on their own domain. The corrective feedback loop only works if the user is paying enough attention to notice, and the operating core is honest enough to admit the failure instead of confabulating around it.

That failure-visibility-plus-honest-response loop is what the rules in `CLAUDE.md` are actually protecting.

---

**Trigger:** analyzing ~78 frames of a fan-edit
**Related concepts:** context-first visual protocol, multimodal training asymmetry, calibrated humility on culturally-dense topics
