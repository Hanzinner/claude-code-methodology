---
name: fix-findings
description: Turn a reviewer's findings into verified fixes - reproduce before fixing, fix the class not the instance, pin every behavioural change, and disposition what you do not fix. Environment-invariant - the caller supplies the commands and says whether it commits. Used by /quality-loop, or directly when the user says "fix the findings", "fix the review findings", "close the findings", "/fix-findings".
---

# Fix findings

How a finding becomes a verified fix. This file is the same text wherever it runs; **it never says which
commands to use, whether you may commit, or what a stack is.** Those are the caller's, declared in the
environment block it hands you:

| field | what it means for you |
|---|---|
| `test_command: <cmd>` | the only runner you use to prove a repro fails and a fix passes. Never substitute another - a bare runner can break collection in ways the project's own does not. |
| `lint_command` / `typecheck_command` | the static gates a fix must leave clean. |
| `gate: <path>` \| `gate: none` | when a path is given, every finding closes through it (artifacts below) and `done` must exit 0 before you call anything fixed. |
| `worktree: yours` \| `worktree: read-only` | whether you may edit at all. Read-only means you produce patches and dispositions, never writes. |
| `commit: caller` \| `commit: yours <convention>` | who records the work. If the caller commits, stop at a verified fix and hand back the ledger. |
| `stack: prepared` \| `stack: none` | whether a running system is available to reproduce against. With `none`, a repro is a failing test, not a live trigger, and you say so in the disposition. |

Everything below is invariant: it is what makes a fix trustworthy, not how this machine runs it.

## 0. How to run it here

- **Language.** Everything the user reads - the ledger summary, dispositions, questions - is in the
  user's language. Finding fields and trailers keep their English names
  (`Fixed:`, `Accepted:`, `P2`, `pin_verified`).
- **Proof of a run.** Every `test_command` / `lint_command` / `typecheck_command` run goes through
  `python3 "${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/scripts/proof_report.py" run --sid "$CLAUDE_CODE_SESSION_ID" -- '<command>'`
  (or the `/verify` skill), so `proof-guard` sees exit codes, not words. "Done" without such a run
  after your last edit is blocked by `proof-guard` (when that hook is on). If you run as a different
  OS user than the one who owns the worktree, export `PYTHONDONTWRITEBYTECODE=1` before any Python
  you start yourself (a `__pycache__` the owner cannot delete breaks `git worktree remove`).
- **Base branch** is the repo's default branch (main or master):
  `B=$(git rev-parse -q --verify main >/dev/null && echo main || echo master)`;
  `BASE=$(git merge-base "$B" HEAD)`. Diffs use three dots, `"$B"...HEAD` - two dots show commits
  merged into the base after you branched as your own deletions.
- **Subagents** (the simplification pass below) get `model:` stated explicitly, named to the user in
  one line.

---

## Over-engineering is not ugliness - it manufactures the bugs

**Every line you add is a line that can be wrong.** Complexity is not a style problem that costs
readability; it is the mechanism that produces the next defect. Simpler code has fewer bugs because
there is less of it to be wrong.

This is not a slogan - it is the measured pattern in this loop's own history:

- One branch spent **five consecutive iterations** fixing races in deletion-and-caching logic. Locks,
  compare-and-swap, ordering guards, a new shape each round. The races were real. **They existed
  only because the code had a TTL and a cache that nobody needed.** Deleting both removed every race
  at once and shrank the diff. Five rounds of correct fixes to code that should not have existed.
- A "fix" that added a reset helper **doubled every span export in production** - the added
  machinery was itself the defect, and reverting it in full was the fix.

So, every time you are about to add something:

- **Prefer removing the possibility of the bug over guarding against it.** One write instead of
  check-then-write. An unconditional path instead of a predicate with a fallback. No lock instead of
  a correct lock. No cache instead of a correctly-invalidated cache.
- **A guard against an impossible state is a future bug**, because it will be maintained, tested and
  reasoned about forever.
- **If the fix is bigger than the bug it closes, it is the wrong fix.**
- **"Delete this" is a valid finding and usually the best one.** The strongest outcome of an
  iteration is a smaller diff than it started with.

When a reviewer proposes an abstraction, a wrapper, a config knob or a strategy, the default answer
is **no** unless it is load-bearing today. Speculative generality is how a 500-line change becomes
2000 lines of surface for the next round to find defects in.

---

## Step 5. Fix every finding

### P3 is parked, not fixed - hard rule

A P3 goes in the ledger as `Deferred: [P3] ...` and you move on. Fix one only when it is one line at
one site. Never block an iteration on a P3, never block convergence on one, never spend a review
round on one. Measured across 338 loop commits: mechanical P3-grade work - comment trims, test
shrinks, prompt re-wording, "subsumed" pin deletions - produced 7 Criticals and 4 P1s and removed
nothing a user could see.


**First, reconcile every fresh finding against the ledger** (`state.md` plus the `Fixed:` / `Rejected:` / `Deferred:` trailers in `git log $(git merge-base "$B" HEAD)..HEAD`). The reviewers are blind to prior rounds by design, so this matching is yours alone:

- **Matches a Rejected row** -> the repeat-rejection tripwire below. Never a fresh investigation, never a silent second rejection.
- **Matches a Deferred row** -> stays deferred; note it as still open, do not re-report it as new.
- **Matches a Fixed row** -> the reviewer found a regression or a vacuous pin. Confirm the pin still exists and fails without the fix; a deleted or never-working pin is a new, serious finding.
- **No match** -> genuinely new; continue below.

Then work the merged report top-down by severity. For each finding: real bug, real rule violation, or false positive? Decide explicitly. Rejecting one is fine; silently dropping it is not - say which you rejected and why.

### Verify the worst case before you fix anything

**Severity is a claim, and it is the claim most often wrong.** Before fixing, reconstruct what actually happens if the finding is left alone:

- **What breaks** - concretely, in terms a user or an operator would notice.
- **What must happen to trigger it** - the full precondition chain, not just the code path.
- **How often that realistically occurs.**
- **Blast radius** - data loss? user-visible wrong output? an internal counter off by one? recoverable by a one-line update?

A finding whose trigger is *"two admins press the same button inside a 50ms window while a once-a-day cron holds a database call"* and whose impact is *"one counter off by one, document still reachable, fixable with a single-row update"* is **P2 at most, usually P3.** It is technically data corruption and that does not make it urgent.

**Security is the exception - never apply the probability discount to it.** Every exploit path looks improbable as an accident; an attacker searches for exactly that path. An externally-reachable issue (unauthenticated access, user input reaching a dangerous sink, injection, SSRF, tenant isolation failure, secret exposure) is **P1 on impact alone**. But scope it to the external surface: a finding that needs an already-trusted teammate to act maliciously is **not a security finding** - we do not model insiders as attackers.

**"The process could die here" is one design finding, not many.** Do not guard every instruction; name the transactional boundary that removes the class - write nothing until the end and commit atomically, or make the write idempotent. P2 unless the interruption loses data a user notices.

**If the verified worst case does not justify the fix, do not fix it - `accept` it.** That is a fourth disposition alongside fixed / rejected / deferred:

```
Accepted:
- [reviewer said P1, verified P3] orphaned finding on tombstoned issue (repositories/x.py:88)
  trigger: two admins inside a 50ms window during the daily merge pass
  probability: negligible - not a rate a real system reaches
  impact: one issue's count off by one; document still reachable by direct link
  recovery: single-row update
  reason: cost of the fix exceeds the verified worst case
```

An accepted finding is **not** a silent drop. It goes in the commit trailer, in the loop state file, in the PR body, and it is stated to the user in the report every time. Re-raising it in a later iteration is answered by pointing at that record - **never by re-fixing it.**

Fixing a finding whose worst case you never checked is how a branch spends multiple iterations on a race that cannot fire.

### The gate: artifacts, not intentions

**Every finding is tracked by `gate.py`. A finding you cannot close in the gate is not fixed**, regardless of what the tests say or how confident you feel.

```bash
G="${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/skills/quality-loop/gate.py"   # store: ~/.claude/quality-loop/<sha1 of toplevel>/findings/
python3 "$G" start F1 "<one-line description>" [--concurrency]
python3 "$G" record F1 <artifact> "<value>"
python3 "$G" done F1        # exits 1 and lists what is missing
python3 "$G" trailer F1     # emits the commit trailer block
```

Required artifacts: `repro`, `class`, `siblings`, `fix`, `pin_verified`, `regression` - plus `interleavings` when you passed `--concurrency`.

This exists because the prose version of these steps got skipped nearly every time. One race condition once consumed **five consecutive iterations producing six net lines**, because each round fixed the instance in front of it and let the next reviewer find the adjacent window. The gate makes that visible: an empty `siblings` is a blocked commit, not a silent omission.

**Pass `--concurrency` for any ordering, locking, or race finding.** It additionally requires an interleaving table, and you must write it **before** the fix. If you cannot enumerate the orderings, you do not understand the bug yet - do not write a fix.

**`record` takes observed output, not narration.** `repro` holds the actual FAIL output from before the fix and `pin_verified` the structured PASS line after it (`expected=<v> observed=<v> verdict=PASS`; a `verdict=FAIL` line is rejected by the gate on purpose - it means the fix does not work), never the sentence "mutation-verified". A claim without its output is the thing that seeds the next reviewer with a wrong premise and costs a full iteration to disprove.

We have no commit hook that checks trailers: `proof-guard` guards that a run happened, `gate.py` guards the per-finding artifacts - use `gate.py trailer` to generate the trailer lines rather than writing them by hand.

### The per-finding loop - do this yourself, cheaply

**Never re-run the dual review to check whether a fix worked.** That is a multi-minute `/code-review` + `deep-code-reviewer` (opus) pass, and it is a discovery tool, not a verification tool. Verifying your own fix is faster, more thorough and free: you can run the exact tests that would break it in seconds, and you know what you changed. Reserve the heavyweight reviewers for finding things you did not think to look for.

For **each** finding, run this loop to convergence before touching the next one:

**1. Reproduce it first - this is also how you verify the finding is real.**

Write the test that fails *because the defect exists*, before changing any production code.

```bash
<test_command> <covering test file>::<new test>    # must FAIL
```

If you cannot make it fail, **the finding is not real** - reject it and record that you tried to reproduce it and could not. That is the strongest possible rejection evidence, and it costs a minute.

This single act does three jobs: it verifies the finding, it becomes the Step 5b pin, and it defines when the fix is done. There is no separate "verify the pin fails without the fix" step - you just watched it fail.

**2. Fix until that test passes.** The reviewer's suggested fix is a *hypothesis, not a prescription* - both reviewers are read-only and never executed anything, so a suggestion can be right about the defect and wrong about the fix, usually because it does not hold under the project's test doubles or a mock they never saw. If the suggestion does not pass the test, discard it and write your own; note the divergence.

**3. Prove you broke nothing.** Run the covering file, the neighbouring tests, and **every prior iteration's pin**:

```bash
<test_command> <covering test file> <neighbouring test files>    # read the summary line, not the exit code
```

Prior pins are unit tests and cost seconds. A fix that quietly breaks an earlier pinned fix is this loop's most expensive failure, because the next reviewer sees a new defect with no history.

**4. Attack your own fix with cases the reviewer did not mention.** The reviewer named one instance; you are fixing a class. Ask what *else* is in that class:

- the same bug in a sibling call site, branch, or provider
- the boundary either side of the one they cited - empty, null, one element, a huge one
- the inverse path - does the fix hold on the error branch, not just the happy one?
- the test double: does this behave the same under the project's fakes/mocks as in production?

Add cases for whatever you find. **This is the step that stops one finding becoming three iterations** - the sibling instances get caught now, by you, instead of by a fresh reviewer two iterations later reporting them as new defects.

**5. Only now is it fixed.** Record it and move to the next finding.

### A rejection or deferral needs the same evidence as a finding

"Out of scope", "already guarded upstream", "that file is not in this diff" are all **checkable claims**, and a wrong one costs an entire iteration when the next reviewer disproves it. Check before writing it down:

- "not in this diff" -> `git diff --stat "$B"...HEAD`
- "no caller does that" -> `LSP findReferences` if LSP tools are present; else Grep for callers
- "already handled upstream" -> open the guard and read it

A rejection you cannot evidence is not a rejection; it is a finding you have not investigated yet.

### The diff budget

Growing the PR is fine when a fix genuinely needs the lines. What is **not** fine is a 500-LOC PR walking out of this loop at 2000 LOC. That happens every time, it is the single most common failure of this loop, and it is caused by fixes that are more elaborate than the bug they close.

Record the baseline before the first iteration and re-check it every time round:

```bash
git diff --shortstat "$B"...HEAD    # baseline at loop start, and after each iteration
```

| Loop growth over baseline | What it means |
|---|---|
| Shrinking, or roughly flat | Healthy. Findings are being fixed by deleting and simplifying. |
| Up to ~20% | Normal. Real fixes cost real lines. |
| **Over ~25%** | **Stop and justify every added block individually.** State, per addition, which finding forced it and why nothing smaller would do. If you cannot, delete it. |

Regression-pin tests from Step 5b are exempt - count them separately. Everything else is in scope.

Judge each fix by proportionality: **is this fix bigger than the bug it closes?** A one-line off-by-one does not need a new helper class. A missing None check does not need a validation layer.

The four things that actually inflate a diff - hunt them on every iteration:
- **Over-engineering a simple fix.** New abstraction, wrapper, config knob, or strategy where three lines would do. This is the big one.
- **Bloated diff.** Churn that is not the fix - reformatting untouched code, drive-by renames, reordering imports in files you did not otherwise change.
- **Overcomplicated architecture.** A new layer, manager, or indirection introduced to satisfy a finding that a local edit would have satisfied.
- **Comment and docstring bloat.** Explaining the fix in five lines of comment. The reason goes in the commit message; one or two lines max in the source.

**Scope discipline:** if a finding suggests a new capability or a nice-to-have improvement, **report it as a suggestion, do not implement it.** Fixing bugs is in scope; expanding the feature is not.

While fixing, don't reintroduce what the reviewer just flagged:
- No function over ~50 LOC; extract, or state why it can't split
- No comment bloat - default is no comment; one or two lines when the *why* is non-obvious
- No context bloat - for any `prompts/` change, tool description, or JSON-schema `description`, work out how often that text is sent and quantify it ("~600 tokens on every communication turn")

## Step 5a0. Before redesigning, ask whether the code should exist

Two triggers, either one is enough:

- **Two consecutive rounds found a defect in your own fix** (the consecutive detector), or
- **One file has been edited more than ~6 times across the loop** (the churn detector). Sustained grinding on one surface is the same failure spread thin - it never trips the consecutive test because the rounds are not adjacent.

**Do not go straight to redesign.** Redesign assumes the component should exist. Ask the cheaper question first:

1. **What feature does this code serve?** Name it in one line.
2. **If that feature were deleted, would the whole defect class disappear?**
3. **What is actually lost by not having it?**

This is not hypothetical. One branch spent five rounds fixing races in deletion-and-caching logic - locks, compare-and-swap, ordering guards, a fresh shape each round. The races were real. They existed **only because the code had a TTL and a cache that nobody needed.** Deleting both removed every race at once, and shrank the diff. Five rounds of correct fixes to code that should not have been there.

Races, lock ordering and cache-invalidation defects are the strongest signal here: **before you design a correct lock, ask why there is contention at all.** Two writers exist because two code paths write; often one of them is a feature nobody asked for.

If deleting it is plausible, **stop and ask** - do not delete a product feature on your own authority. Return:

```
Requirement in question: TTL + cache on findings
Defects it caused: 5 rounds, N findings, all races between deletion and consolidation
If removed: every one of those disappears; diff shrinks by ~X lines
Cost of removal: findings are never auto-expired
Recommendation: remove
```

That is legal stop-reason 9. Only when the requirement is confirmed necessary does Step 5a apply.

## Step 5a. When patching keeps failing, redesign - do not patch again

Track, per iteration, whether a Critical or Warning came from **code this loop wrote in a previous iteration**.

**Two consecutive iterations finding a defect in the previous iteration's fix means the design is wrong, not the code.** Stop patching. One race once consumed five consecutive iterations - five different shapes of the same fifteen lines - and produced six net lines. Every round reasoned locally about the two lines in front of it and let the next reviewer find the adjacent window. A sixth patch would not have converged either.

**Do not stop the loop. Replace the component.**

### 1. Harvest the contract before deleting anything

The old code's guarantees are your spec, and they are already written down - in its pins and in the `Fixed:` entries of the commit log:

```bash
git log $(git merge-base "$B" HEAD)..HEAD --format='%B' | grep -A3 "Fixed:"
```

List every **behaviour** the component must still guarantee. Behaviour, not mechanism: "findings never outlive their user" is a behaviour; "the audit lock is acquired before the purge" is a mechanism, and mechanisms are what you are throwing away.

### 2. Delete the implementation and its implementation-coupled tests

**Delete, do not refactor.** Refactoring toward a new shape carries the old shape's assumptions with it - that is how the five-iteration loop happened in the first place.

Tests split in two, and getting this wrong costs you either the regression protection or the redesign:

- **Implementation-coupled pins** - asserting on internal ordering, an internal lock, a private helper, a specific call sequence. **Delete them with the code.** Keeping them anchors the rewrite to the design you just decided was wrong.
- **Behavioural pins** - asserting an outcome a user or caller can observe. **These survive**, rewritten against the new design. Every behaviour harvested in step 1 must end up pinned again.

### 3. Rebuild simpler

The replacement **must be smaller than what it replaced.** If it is not, it is not a redesign - it is the same design with new names, and it will produce the same defects. Say the before and after LOC explicitly.

Prefer removing the possibility of the bug over guarding against it: one write instead of a check-then-write, an unconditional path instead of a predicate with a fallback, no lock instead of a correct lock.

### 4. Re-pin every harvested behaviour, then force a whole-branch review

Each behaviour from step 1 gets a fresh pin against the new design, verified failing-then-passing as usual. Then set `scope=whole` - a redesign is never delta-reviewed; it is the largest change the loop can make.

### Bounds

- **One redesign per component.** If the replacement also produces defects, the loop has now failed at both patching and redesigning - that is stop-reason 10. Report the chain, the behaviours, and both designs.
- Record it in the commit as a `Redesign:` trailer naming the component, before/after LOC, behaviours harvested, and pins deleted vs rewritten.

## Step 5b. Pin every behavioral fix with a deterministic test

**This loop is itself a regression source.** Iteration 3's fix silently undoes iteration 1's, and nothing notices: the live test that caught the original bug is never re-run, and a fresh reviewer only ever sees the current diff, not the history of what was already fixed. Every iteration that ends without a pin makes the next one more dangerous. This is the single stupidest way for the loop to fail, and it is common.

**A finding is not "fixed" until a deterministic test fails without the fix and passes with it.** If you followed the per-finding loop in Step 5 you already have this - the reproduction test *is* the pin, and you watched it fail before you fixed anything. This section is about where it lives and what deserves one.

Deterministic means it runs under the caller's `test_command` on **every subsequent iteration**. A live signal, an LLM-graded assertion, or a scenario test is **not** a pin - they are slow, non-deterministic, and the loop does not re-run them. Pin in the suite the caller's `test_command` runs. Genuinely LLM-dependent behavior pins in whatever separate suite the project keeps for that; say in the report that this pin does not run in the loop's inner iterations, so it guards the branch but not the next fix.

### What gets a pin

| Finding | Pin? |
|---|---|
| Anything **live testing or a break attempt** produced | **Always - highest priority.** It was found by poking a running stack, which the loop never repeats, so it is invisible from the next iteration onward. |
| Correctness: logic, None-handling, concurrency, resource leak, data integrity, contract break | Always |
| The original bug the branch was written to fix | Always |
| Rule violation with runtime behavior - UTC reaching the LLM, un-wrapped prompt interpolation, a missing ownership check | Yes. These are deterministically assertable; assert on the payload, not on prose. |
| Over-engineering, separation of concerns, comment/docstring bloat, naming, formatting | **No.** Nothing to regress, and a test here is exactly the bloat this loop is supposed to remove. |

### If a pin was not written reproduce-first

Occasionally a fix lands before its test - a trivial one-liner, or a fix made while chasing something else. Then you must verify the pin explicitly: stash the fix, confirm the test **FAILS**, restore, confirm it **PASSES**.

A test that passes either way is worse than no test: it is a false guarantee that will wave the same bug through on iteration 5.

### Pins do not count against the diff budget

Test LOC that locks in a verified fix is the one kind of growth this loop wants. Track it separately from production LOC so the Step 5 budget check never argues against pinning something real.

### Keep a ledger across iterations

Maintain, for the whole loop: **finding -> fix -> pinning test -> iteration found**. Before declaring done, run the full suite once more and confirm **every pin from every iteration still passes**. If an earlier pin broke, the loop regressed its own earlier work - that is a finding in its own right. Fix it, and keep looping.

---

## Step 5d. Simplification pass - only once correctness is clean

Run this when a review returns **zero correctness findings**, before declaring done. Not every iteration - it judges the *accumulated* diff, and running it mid-loop just churns code that is about to change again.

**Why a separate pass rather than more rules in the main review:** the reviewer already carries simplicity rules, and they still fire late - one function went 839 -> 1219 -> 828 -> 1232 -> 780 chars across four iterations because bloat was noticed three rounds after it landed. In a mixed review, simplicity findings compete with Criticals for attention and lose. One reviewer, one lens, on the final diff, catches it once.

Spawn `deep-code-reviewer` (`Agent`, `subagent_type: "deep-code-reviewer"`, `model: "opus"`; if that type is not offered - `general-purpose` + "Read ~/.claude/agents/deep-code-reviewer.md (<project>/.claude/agents/ for a project install) and follow it") with a **simplification-only** brief:

> Review the accumulated branch diff for simplicity and maintainability ONLY. Report no correctness findings - a separate pass owns those. Judge it on: what can be deleted, what is over-engineered, what is at the wrong altitude, what a new developer would struggle to read.

What it is looking for:

- **Deletion first.** Which hunks would the diff be better without? "Delete this" is the best possible finding.
- **Over-engineering** - single-use helpers, wrappers that only forward, speculative config, one-strategy strategy patterns, defensive checks against impossible states.
- **Altitude** - logic sitting at the wrong layer: a manager doing raw I/O, transport concerns leaking into domain code, narrow guidance injected into an always-on prompt.
- **Reuse** - reimplemented behaviour that an existing helper already covers.
- **Readability** - functions over ~50 LOC, nesting past 3, magic numbers, boolean flag args, spaghetti flow.
- **Comment and docstring bloat** - anything restating the code; regression history that belongs in a commit message.
- **Context bloat** - `prompts/` text and tool descriptions, quantified as tokens x send frequency.
- **Fix proportionality** - is any fix bigger than the bug it closed? That is the 5-iterations-for-6-net-lines shape.

**Findings go through the normal path** - `gate.py`, the per-finding loop, the commit trailers. A simplification finding is a finding; it does not get a shortcut just because it deletes code.

**Do not invoke the bundled `/simplify` here.** Its lenses are right but it *applies* fixes directly, bypassing the gate, the pins and the commit trailers. Run it standalone if you want a second opinion; never inside this loop.

If this pass produces changes, correctness must be re-confirmed - loop back to Step 1.
