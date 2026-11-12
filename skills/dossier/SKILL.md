---
name: dossier
description: Hypothesis-tested research on a specific company, person, or organization; NOT a generic profile. Forces the user to state a hypothesis upfront so the research tests it instead of confirming it; at least 30% of the search budget goes to disconfirming evidence. Use when the user says "dossier on [X]", "research [company]", "background on [person]", "prep me for a meeting with [X]", "due diligence [X]", "what should I know about [X]", "/dossier", "competitor intel on [X]".
---

# Dossier: hypothesis-tested entity research

Not a generic Wikipedia summary. Every run forces the user to state a hypothesis and searches for evidence both FOR and AGAINST it, so the result is a verdict, not a confirmation.

## Step 1: Forcing intake (4 mandatory + 2 optional, one at a time)

### Q1: Subject identity
Who exactly? Exact name + a disambiguator: for a company, domain or LinkedIn page; for a person, LinkedIn URL or (company + role); for an NGO, EIN or country + name.

**Refuse ambiguous names.** "John Smith" means re-ask. "Anna from Acme Corp" is fine.

### Q2: Subject type
- person / company / NGO / government org / other

Different source matrices. Force a choice.

### Q3: Purpose
1. Sales meeting / pitch prep
2. Investment / acquisition diligence
3. Competitor intel
4. Hire / interview prep
5. Personal vetting
6. Journalism
7. Other (one line)

The research angle depends on this.

### Q4: Hypothesis (MANDATORY, the anchor)

What does the user ALREADY believe about this subject and want to verify or refute?

Examples:
- "the contact is avoiding me because their company is cutting its consulting budget"
- "the vendor team will make us the primary account by Q3"
- "this company resells someone else's documentation pipeline with no diff of its own"

If the user says "I have no hypothesis", push back once: "then guess. Commit to a position you will update later. Without a hypothesis a dossier is a generic profile."

If there is still none, fall back to "the most surprising thing I could find" and flag in the audit section that this is a fallback.

**This is the non-generic anchor. Skip it and you get a Wikipedia summary.**

### Q5: Depth
- Brief (~5 searches, no network/reputation passes)
- Decision-grade (~15 searches, full cycle)

### Q6: Sensitivities (optional, only for journalism / personal vetting)
What to exclude (medical, family, political)?

**Stop:** after Q5/Q6, commit and start. Do not re-open intake.

## Step 2: Source matrix (by Q2 type)

**Person:**
- LinkedIn (if blocked, fetch manually and note it)
- Personal site, GitHub (if tech), Scholar (if academic)
- News via your web search tool + page fetch
- Conference talks, podcasts

**Company:**
- Official site (about, leadership, news)
- SEC EDGAR (free API, US public companies): `curl -s "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<cik>&type=10-K&dateb=&owner=include&count=40" -A "Mozilla/5.0"`
- Crunchbase free tier
- GitHub (for tech orgs)
- LinkedIn company page

**NGO:**
- ProPublica Nonprofit Explorer (free, Form 990s): `curl -s "https://projects.propublica.org/nonprofits/api/v2/search.json?q=<name>"`
- Official site, news

**Government:**
- Official .gov sites, news, ProPublica

Web search: use your web search tool; if the repo's search MCP is installed, that is `mcp__search__search`.

## Step 3: Hypothesis-driven search

**Rule: at least 30% of the search budget goes to DISCONFIRMING queries.**

Classify every search:
- **Supporting:** confirms the hypothesis
- **Disconfirming:** could refute it

Example for the hypothesis "the contact is avoiding me because of cuts":
- Supporting: "<company> layoffs 2026", "<contact> consulting budget"
- Disconfirming: "<company> new hires 2026 security", "<contact> promotion announcement", "<vendor> team expansion"

Without at least 30% disconfirming queries this is confirmation bias, not research.

## Step 4: Timeline (12 months by default)

Reverse chronological:
- News (hires, departures, acquisitions, product launches)
- Funding / financial events (for companies)
- Controversies / legal events
- Public statements / strategy shifts

Every entry with a URL + tier (primary / secondary / tertiary).

## Step 5: Network + reputation

**Network:** investors, customers, partners (company); co-founders, advisors, board (person); funders, board (NGO). 5-10 entries ranked by relevance to the hypothesis.

**Reputation:** sentiment from news (last 12 months), Glassdoor for a company, peer mentions for a person. Tier accordingly. Caveat: reputation is noisy.

## Step 6: Red flags

Surface without sensationalizing:
- Litigation (court records are primary)
- Regulatory actions (primary)
- Key personnel exits (last 90 days)
- Financial signals (going-concern notes are primary)
- Sustained negative coverage (secondary)

Tier each one.

## Step 7: Conversation hooks (3-5)

Not generic. Tied to actual findings.

Bad: "Ask about the roadmap"
Good: "Mention their recent acquisition of X: it signals a move into vertical Y. Framing: 'Saw the [X] announcement. How does that change your roadmap for Y?'"

Each hook has:
- **Hook** (one sentence)
- **Finding** (URL + tier)
- **Framing** (verbatim what to say)

## Step 8: Output (markdown, not DOCX)

Save to `/tmp/dossier_<slug>_<YYYY-MM-DD>.md` and paste into the chat:

```markdown
# Dossier: [SUBJECT]
*Purpose: [Q3] | Depth: [Q5] | Date: [YYYY-MM-DD]*

## Executive summary
[1 paragraph: who + why they matter + VERDICT (SUPPORTED / PARTIALLY / DISPROVEN / INCONCLUSIVE) + 3 things to know]

## Identity facts
[table: founded/born, location, size/stage, current role, key affiliations, all sourced]

## Hypothesis test
**Hypothesis (verbatim):** [the user's, from Q4]

**Supporting evidence:**
- [bullet with hyperlink + tier]

**Disconfirming evidence:**
- [bullet with hyperlink + tier]

**Verdict:** [2-3 sentences with weighting]

## 12-month timeline
[reverse chronological with URLs + tiers]

## Network signals
[5-10 entries ranked by relevance]

## Reputation
[sentiment + noisy-data caveat]

## Red flags
[tiered, not editorialized]

## Conversation hooks
1. **[hook]**: [finding URL + tier]. *Framing:* "..."

## Audit
- Queries: N (supporting: X, disconfirming: Y), at least 30% disconfirming: yes/no
- Sources received: M, cited: K
- Per tier: primary X, secondary Y, tertiary Z
- Extra MCP tools used: [list or none]
- Fallback hypothesis: [yes/no]
```

## Anti-patterns

- No Q4 hypothesis: generic profile, failure
- Under 30% disconfirming: confirmation bias, failure
- Batching intake questions: does not work
- Accepting ambiguous names: disambiguation failure
- Generic hooks ("ask about the roadmap"): failure
- Sensationalizing red flags instead of tiering them
- Skipping the source tier on flags
- Fabricating coverage when LinkedIn is blocked
- A confirmation-biased verdict ("SUPPORTED" without engaging the disconfirming evidence)
- Including sensitive topics that were excluded in Q6

## When NOT to use

- The user wants a generic overview ("tell me about Microsoft"): that is a web search, not a dossier
- A subject with no public footprint: say so explicitly, do not fabricate
- The topic is already in memory (known clients, contacts): read memory first
