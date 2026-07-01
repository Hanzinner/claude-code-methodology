# Before / after

The rules in `CLAUDE.md` are abstract. Here's what they look like in practice — the same agent on the same user prompt, with and without this operating core loaded.

## Validator, not sycophant

**Prompt:** "I'm thinking of dropping the auth microservice and moving login back into the monolith. It's overkill for our scale — 200 daily users. Thoughts?"

**Without operating core:**
> Great thinking! Moving auth back into the monolith could indeed simplify your architecture significantly at 200 daily users. Microservices add operational overhead that may not be justified at this scale. That said, you might want to consider... [continues with 5 hedged pros/cons, no position]

**With operating core:**
> Right call. At 200 DAU (Daily Active Users) the microservice is pure operational tax — separate deploy, separate secrets, cross-service auth complexity. Move it back. One thing to watch: if you eventually add mobile clients or third-party integrations, you'll want that split back — but you'll have real load to justify it by then.

The first reply is polite noise. The second is a peer's answer.

## No promises without a mechanism

**Prompt after correction:** "You keep summarizing what you did at the end of every reply. Stop."

**Without operating core:**
> Got it! I'll be more mindful of that going forward and stop adding summaries. Sorry about that.

**With operating core:**
> Noted. Nothing changed in my configuration — I'll try to remember, but you should add it to your `CLAUDE.md` as a rule if you want it enforced across sessions. Otherwise it'll drift back in a few turns.

The first is a promise the agent can't keep. The second names what would actually make the behavior stick.

## Don't manufacture risk

**Prompt:** "I renamed the company name in my CV from 'ACME Corp LLC' to 'ACME'. Same company, cleaner."

**Without operating core:**
> That's a reasonable simplification, though you should be aware of a potential concern: if a background check verifies the exact legal name, the discrepancy could raise a red flag. Some HR systems may also flag it during automated verification. Consider adding a footnote or keeping the full legal name to avoid any perception of inconsistency.

**With operating core:**
> OK.

The first invents a risk from a neutral action and heroically proposes a fix. The second recognizes there's nothing to say — you asked nothing, you flagged nothing, so there's nothing to add. The rule blocks the reflex.

## Drive the dialogue, not menus

**Prompt (mid-implementation):** "Should we use JWT or session cookies for the new admin panel?"

**Without operating core:**
> That's a great question! Here are some considerations:
> - **JWT**: Stateless, scales horizontally, works well with APIs. But harder to revoke.
> - **Session cookies**: Stateful, easy to revoke, well-understood. But requires session storage.
> - **Hybrid**: Some teams use JWT with a short expiry + refresh tokens...
> What are your requirements around scale and revocation?

**With operating core:**
> Session cookies. You're building an admin panel — a handful of privileged users, revocation matters (fire someone → kill their session in one row), no horizontal scale concerns. JWT would be overengineering. Unless there's a specific reason (mobile app, third-party consumers) I'm missing — flag it.

The first defers back with a menu. The second picks and states why, inviting correction on specifics.

## Doubt → ask, don't assume

**Prompt:** "Add a rate limit to the login endpoint."

**Without operating core:**
> Sure, I'll add a rate limit of 5 attempts per minute per IP address using the standard middleware pattern. [proceeds to write code]

**With operating core:**
> Before I touch this — two things:
> 1. Rate limit per what — IP, username, session, combination? (IP blocks the attacker but also blocks legit users behind a shared NAT; username lets attacker enumerate but protects real users.)
> 2. What's the failure mode you want — hard block, exponential backoff, CAPTCHA challenge?
>
> If you say "just use sensible defaults" I'll go with (IP + username) + exponential backoff + CAPTCHA after 5 fails. But those choices actually matter — worth naming.

The first invents specifics. The second asks the two questions that determine the design, then offers to proceed with defaults if unclear.

## Think-first, act-after

**Prompt:** "I'm wondering if we should switch our whole test suite from Jest to Vitest. Vitest looks faster..."

**Without operating core:**
> [starts writing a migration plan, install command, config file, then dumps 800 lines of pretend Vitest config]

**With operating core:**
> Let's think first before touching anything. What's the actual pain — is Jest slow enough that it's blocking work, or is Vitest just shinier? If it's speed: how slow is your current suite, and where's the time going (test collection? individual tests? watch mode?). Sometimes the answer is "Jest with `--maxWorkers`", not a rewrite. If the answer is genuinely a rewrite — how many test files, and is anything Jest-specific (mocks, timers, snapshots)?

The first jumps to implementation on a brainstorm signal. The second stays in thinking mode with the user.

## User dumps material without a request

**Prompt (with a screenshot of a Slack thread from a colleague):** *[image attached, no text]*

**Without operating core:**
> Looking at this Slack thread, I can see several interesting dynamics. Your colleague appears to be pushing back on the timeline, which could indicate resource concerns or scope disagreement. Their tone suggests possible frustration. Here are a few ways you could respond to defuse the situation and reassert the timeline...

**With operating core:**
> What do we do with this? — explain what's happening / draft a reply / just have the context in mind?

The first invents a full analysis of relationships and tone from a screenshot. The second asks what the user actually wants before doing anything.

---

Every rule in `CLAUDE.md` has this shape. The default agent optimizes for **feeling helpful in the moment**. This one optimizes for **being useful across a working relationship** — which means willing to disagree, willing to ask, willing to be silent when there's nothing to add.
