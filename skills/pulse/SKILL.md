---
name: pulse
description: Multi-source recency research. Synthesizes what people have been saying about a topic over the last N days (Reddit + Hacker News + web). Use when the user says "pulse on [topic]", "what are people saying about [X]", "what's going on with [X]", "/pulse", "take the pulse of", "monitoring [topic]", or asks for the current conversation or trends on a topic. Not for a one-off lookup; it is a recency/sentiment snapshot.
---

# Pulse: multi-source recency snapshot

A "what is happening now" cut on a topic from 3 sources: Reddit (consumer sentiment), Hacker News (technical/builder view), web (mainstream coverage). No authentication, no MCP needed.

## Step 1: Forcing intake (3 questions, one at a time)

### Q1: Topic, specifically

What are we monitoring? 1-2 sentences. **Specific.** "AI" is refused. "Pricing changes of a vendor's team plan" is fine. "Competitors in the documentation-agent niche" is fine.

If the user says "AI in general", push back once: "narrow it: adoption, capability, regulation, prices, a specific product?" If they do not narrow it, continue with the caveat "vague topic, surface-level only".

### Q2: Angle

What matters most:
1. **Trend:** what is accelerating or slowing
2. **Sentiment:** how people feel
3. **Problems:** pains and complaints
4. **Opportunities:** gaps and unmet needs
5. **Comparison:** how it looks against alternatives

Default: trend.

### Q3: Window

How many days back: 7 / 14 / 30 / 60 / 90. Default 30.

**Stop:** after Q3 we start. No batching.

## Step 2: Collect (3 sources)

### Reddit
```bash
curl -s "https://www.reddit.com/search.json?q=<URL-encoded-topic>&sort=top&t=<window>" -A "Mozilla/5.0"
curl -s "https://www.reddit.com/search.json?q=<URL-encoded-topic>&sort=new&t=<window>" -A "Mozilla/5.0"
```
`t=` accepts `hour|day|week|month|year|all`. For 7d/14d use `week`, for 30d `month`, for 60-90d also `month` (Reddit offers nothing finer).

For the top 3-5 posts, fetch the comments: `<post-permalink>.json?limit=top`.

### Hacker News (Algolia API)
```bash
# Stories in the window
curl -s "https://hn.algolia.com/api/v1/search?query=<topic>&numericFilters=created_at_i><unix-timestamp>&tags=story"
# Comments in the window
curl -s "https://hn.algolia.com/api/v1/search?query=<topic>&numericFilters=created_at_i><unix-timestamp>&tags=comment"
```
Timestamp = `date -d "<N> days ago" +%s` on Linux.

### Web
Your web search tool (if the repo's search MCP is installed: `mcp__search__search`), focused on trusted publishers (tech press plus topic-specific outlets). For the top 3 results, fetch the page body.

**Rate limit:** 1 query/sec per source. Sequential within a source.

**Retry:** on failure wait 3s, retry once, log it. 3 failures in a row on one source: skip that source with a note.

## Step 3: Synthesis

Look for:
1. **Consensus signals:** points where 3+ sources agree (highest confidence)
2. **Controversy signals:** where they diverge (who says what)
3. **Pain points:** repeated complaints (especially Reddit + web)
4. **Excitement:** repeated enthusiasm (especially HN)
5. **Emerging:** present in `sort=new`, absent in `sort=top`: new
6. **Gaps:** what you would expect to see but do not

For each, **cite URLs**. Training knowledge does not count as a finding.

## Step 4: Output

A markdown file at `/tmp/pulse_<topic-slug>_<YYYY-MM-DD>.md` + paste into the chat:

```markdown
# [TOPIC]: Pulse (last [N] days)
*Angle: [angle] | Session: [date]*

## TL;DR
[2-3 sentences]

## Reddit
### Top posts
- **[title]** (r/sub, [score]/[comments]): [1 line]. [URL]

### What Reddit says
[narrative paragraph]

## Hacker News
### Notable
- **[title]** ([points]/[comments]): [1 line]. [URL]

### What HN says
[narrative; note the technical/builder bias]

## Web
### Sources
- **[title]** ([publication]): [takeaway]. [URL]

### What the web says
[narrative]

## Cross-platform
[Consensus / controversy / emerging: top 3-5 patterns with URLs]

## Takeaways
- [3-5 bullets for the user's angle from Q2]

---
*Audit: queries=N, sources=M, cited=K*
```

## Anti-patterns

- Don't start without a committed Q1 (vague topic means a vague briefing)
- Don't batch intake: one question at a time
- Don't fabricate when a source is down: mark it explicitly, "Reddit skipped, 3 fails"
- Don't cite training knowledge as sources
- Don't parallelize page fetches: sequential

## When NOT to use

- A one-off quick lookup: just use web search
- An academic topic (peer-reviewed literature): not this skill's case
- A question about a historical event: that is not recency, it needs a different approach
- The topic is already in memory: read memory first
