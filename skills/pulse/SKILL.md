---
name: pulse
description: Multi-source recency snapshot — synthesize what people are saying about a topic in the last N days (Reddit + Hacker News + general web). Invoked when the user says "/pulse", "what's the buzz on X", "take the pulse on Y", "what's people saying about Z right now".
---

# pulse

Recency-weighted multi-source synthesis. Not a one-shot search — a snapshot of *current conversation and sentiment* on a topic, drawn from sources that surface community signal (Reddit, HN) plus general web for breaking news.

## How to invoke

User passes a topic. Optional: time window (default last 30 days).

Examples:
- `/pulse Rust async runtimes`
- `/pulse Claude model lineup, last 7 days`
- `/pulse what's going on with project X`

## Step 1 — Frame the question

A vague topic produces vague pulse. Tighten:
- What kind of signal? (sentiment? new tools? controversies? rollouts?)
- What time window? (default 30 days unless specified)
- What community would have it? (general web vs. dev forums vs. industry-specific)

If the user's prompt is one word, ask for a sharper framing before searching.

## Step 2 — Multi-source sweep

Run searches in parallel across at least three modalities:

1. **Reddit / forums** — community sentiment, complaints, "anyone else seeing X"
2. **Hacker News** — technical discussion, new tools, deep critique
3. **General web** (search engine) — news, blog posts, official releases

Use whatever tools are available — MCP search servers (Tavily, etc.), `WebSearch`, or `curl` against specific endpoints. Don't rely on one source.

## Step 3 — Synthesize, don't paste

Bad output: a list of links with one-line summaries.
Good output: a paragraph that says **what people are converging on, what they're splitting on, and what's new this window.**

Structure:

```
# Pulse: <topic> (last N days)

## Consensus
[1-2 sentences on what everyone agrees on right now]

## Splits
[1-2 sentences on the disagreement axis]

## New
[1-3 bullets on what's emerged this window — releases, controversies, tool launches]

## Sources
[5-10 links, weighted by signal not recency alone]
```

## Step 4 — Calibrate confidence

If three sources agree, say so. If you only found one strong signal, say so — don't extrapolate. If the window has nothing surprising, say "quiet week, nothing notable beyond X" — silence is data.

## Anti-patterns

- **Link dump.** A list of 20 URLs is not a pulse. The synthesis is the product.
- **Sample of one.** "One Reddit thread said X" → not a pulse, an anecdote.
- **Sentiment hallucination.** If you can't cite the source for a sentiment claim, don't make the claim.
- **Stale framing.** "Recent" means within the user's window, not "this year". Filter.

## When NOT to use

- One-shot factual lookup ("what year did X launch?") — that's `WebSearch`, not pulse.
- Deep research on a single source ("read this paper") — that's `dossier` or direct fetch.
- Topics with no public conversation (internal corporate state, personal projects) — pulse needs a community.
