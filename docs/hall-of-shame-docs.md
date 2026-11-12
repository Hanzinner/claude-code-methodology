# Hall of shame: doc slop

The worst sin in writing for a swarm: **writing a document for yourself (or another AI), not for the
person who will use it.** Filling it with explanations of your own decisions, self-description and
decoration, and handing it over as a working document. Read this before handing any document to a human.
Bought on one bad day: an agent wrote a knowledge-base "standard"; the human went through it line by line;
about 95% was slop.

For drafting messages to people, the same gate applies sentence by sentence. A sentence that fails is
deleted, not rewritten prettier.

## The one test, for every line

**What does the person DO with this? What breaks if the line is removed?**

No answer — the line does not exist. Not "improve", not "shorten": **delete**. If more than half remains
after the pass, you were writing for yourself. The reader needs an action, not your justification.

## The model of what NOT to do (a real case, invented topic here)

The case was a standard for naming and structuring detection-query documents in a knowledge base. The
shape of each bad line is kept; the topic is replaced by a neutral one — a standard for runbook pages.

| Written | Why it is slop |
|---|---|
| "standard structure" | there is one standard, nothing to compare to; a template inflated into "The Standard" |
| "like a room number, but readable" | decorative analogy so the text sounds clever |
| "(from the runbook taxonomy)" | invented authority — no such taxonomy exists |
| "DISK-FULL, CERT-EXPIRED... " eight domains in one row | examples and entities that don't exist yet; speculation ahead of need |
| "the page reads itself" | empty aphorism |
| "Tool-first, foolproof. This is the doc that goes in the wiki" | self-description of the document; the reader is already in the wiki |
| "to teach the method / when the spreadsheet isn't available" | justification for the document's existence |
| "Don't scatter the procedure across pages", "page (C) is justified when…" | design diary: the author's architecture decisions inside a working document |
| "a hand-maintained date rots into a lie" | a writer's aphorism the executor can't act on |
| "git here / wiki version history" | author's infrastructure chatter, zero value to the user |
| "Use placeholders in drafts" | instruction to the author of a draft, not to the wiki's user |

Of the whole document the reader needed **three things**: the title format, the section order, and the
mapping from classification to section. The other ~90% was the author explaining to themselves why they
built it that way.

## Slop scaffolds — recognize and kill

1. **Dash-appositive** "X - explanation of X" as the spine of every sentence. The main tell of machine rhythm.
2. **A document about itself** — "this is the doc that…", "the page reads itself", "Doc A's job ends at…".
3. **Pseudo-aphorisms** — a neat one-liner for beauty, not information.
4. **Explaining the obvious** to a professional (an on-call engineer knows what a phishing-proxy attack is; no lecture).
5. **Speculative examples/domains/scenarios** that do not exist.
6. **Design diary** — justifying your own choices in the body of a working document.
7. **Bold sprinkles and parenthetical inserts** as seasoning.

## Mechanism

Before handing over: run every line through the test at the top. If you can't say in a second what the
person does with it, cut it. This is not style; it is the difference between "the document works" and
"slop you'd be ashamed of".

**Librarian agent:** on a repeat by another agent, mechanize (a pre-publish gate or a hook, built by the
mechanisms dev agent). Discipline will not hold it, because an agent does not hear itself: here the author
twice said "clean" without having re-read the text.

## Deeper: pass a standard by example, not by specification

By default an agent writes an abstract specification of the structure (that is how an AI organizes things).
A person opens a finished model and copies it. If a good example exists, a separate "standard essay" that
duplicates it is again writing for yourself. The document carries only what the example cannot say about
itself (the naming rule, the classification mapping) plus "copy this one". The example carries the rest.
