---
name: quality-loop
description: Run a project's quality pipeline until clean - tests -> lint -> typecheck -> dual review (/code-review + the deep-code-reviewer subagent on opus) -> fix every finding with artifact gating -> repeat. Project-agnostic - discovers the repo's own commands (release.toml first). This is the AUTOFIX loop; use /code-review alone for a report. Use when the user says "run the quality loop", "loop until clean", "get this branch clean", "/quality-loop".
---

# Quality loop

Loop until the branch is clean. **This skill fixes** - that is the only difference from
`/code-review`.

## 0. How to run it here

- **Language.** Everything the user reads - progress lines, the final report, questions - is in the
  user's language. Ledger, commit trailers and finding fields keep their
  English names (`Fixed:`, `Rejected:`, `P1`, `pin_verified`).
- **Proof of a run.** Every test / lint / typecheck command in Steps 1-3 and every live run in 3b goes
  through the run recorder, so `proof-guard` sees the exit codes, not your words:
  ```bash
  python3 "${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/scripts/proof_report.py" run --sid "$CLAUDE_CODE_SESSION_ID" -- '<command>'
  ```
  Or hand the check to the `/verify` skill (a Sonnet subagent that does the same wrapping). Saying
  "done" / "clean" without such a run after your last edit is blocked by `proof-guard` (when that
  hook is on).
- **Worktree hygiene.** If you run as a different OS user than the one who owns the tree, export
  `PYTHONDONTWRITEBYTECODE=1` before any Python you start yourself (a `__pycache__` the owner cannot
  delete breaks `git worktree remove` - `code-pitfalls/git.md`), and restore mutation backups with
  `cp`, never `git checkout --`/`stash`.
- **Models.** Every subagent this loop starts gets `model:` stated explicitly and named to the user
  in one line ("starting deep-code-reviewer on opus").
- **Base branch** is the repo's default branch (main or master):
  `B=$(git rev-parse -q --verify main >/dev/null && echo main || echo master)`. The baseline is the
  merge base, `git merge-base "$B" HEAD`; every diff uses three dots, `"$B"...HEAD`. Two dots
  compare two snapshots and show commits merged into the base after you branched as your own
  deletions.

## Caller instructions override everything here

Constraints in the invocation - "do not commit", "review only", "only touch these files", "stop
after one pass" - **win over every default below.** Name the constraints you picked up at the start
and again wherever one changed what you did. If a constraint makes a done-criterion unreachable,
**stop and report the gap** rather than reaching it by ignoring the constraint.

## You are pre-authorized. Do not stop to ask.

Reading, editing, running tests, running the review, committing, pushing to a PR you own, and
starting the next iteration are **part of the task**, not separate actions needing permission.

This is the most common way this loop fails: not by looping too long, but by stopping after
iteration 1 with "Want me to fix these?" when told to loop until clean.

**Never end a turn with:** "Want me to...?" / "Shall I...?" / "Say the word" / "Ready to commit" /
"Waiting for your go-ahead" / "What next - A, B or C?". If you are about to write one, you have
found the next action - **take it.**

**When there are options, decide.** Pick, justify in one line, continue. **Park out-of-scope items**
(tickets, PR titles, follow-up features) in a Deferred list; they never block.

### The only legal reasons to stop

1. **Zero findings** - a full pass completed clean
2. **A caller constraint blocks the next step** - stop there, report the gap
3. **The repeat-rejection tripwire fired** (below)
4. **An irreversible action outside scope** - a deploy, anything touching production, a force-push
5. **Hard blocked** - missing credential, expired auth, a service that will not start
6. **Anything that would speak as the user** - a PR/issue comment, reply or review under their
   account. Draft it; never post it.
7. **Opening a pull request** - always the user's call. Being authorized to commit is not
   authorization to publish. If the branch has no PR, **never create one.**
8. **A product, policy or consent decision** - not a correctness question; state it and continue
9. **The requirement itself is in question** (below)
10. **A redesign failed**

**Uncertainty is not on that list.** Investigate, decide, record it, keep going.

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

## The loop state file

Instructions usually survive compaction; accumulated state does not, and that is what makes
iteration 8 re-argue a point settled in iteration 2.

The state lives next to the gate's findings, **outside the tree and outside `.git/`** (a file
inside the tree shows up in the diff, and one written by a different OS user than the tree's owner
breaks `git worktree remove`). The gate prints the path, keyed by the git toplevel, and creates its
folder:

```bash
G="${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/skills/quality-loop/gate.py"
STATE=$(python3 "$G" state-path)    # ~/.claude/quality-loop/<sha1 of the git toplevel>/state.md
```

Read it at the start of every iteration, rewrite it at the end. Keep it short - decisions, not
narrative: iteration number, diff baseline, a ledger of finding -> fix -> pin, a **Rejected** table
(do not re-litigate), Deferred items, and constraints in force. **If the file is missing you are on
iteration 1** - never infer prior state from the conversation.

## Step 0. Discover this project's commands, then sync

Do not assume `make test`. Find the real ones. **A project that has a `release.toml` defines its
gate there first** (`test = "..."`, run from the project root, as the releaser does; projects made
by `scripts/new_project.sh` have one; the project is either its own repo or a folder of a larger
repo, so walk up from the cwd):

```bash
R=$(pwd); while [ "$R" != / ] && [ ! -f "$R/release.toml" ]; do R=$(dirname "$R"); done
[ -f "$R/release.toml" ] && grep -E '^(test|tests) *=' "$R/release.toml"
cat Makefile justfile package.json pyproject.toml 2>/dev/null | grep -iE "test|lint|format|typecheck|check" | head -20
ls .github/workflows/ 2>/dev/null && grep -hE "run:" .github/workflows/*.y*ml | head -20
```

`release.toml` is the authoritative gate where it exists; CI and the build files fill in lint /
format / typecheck it does not name. Record the commands in the state file.

Then bring the branch up to date with its base `"$B"` (merge, not rebase - rebasing rewrites
SHAs, which force-pushes and orphans inline review threads). Refuse to merge into a dirty tree.

## Steps 1-3. Tests, lint/format, typecheck

Run the discovered commands, each wrapped in `proof_report.py run` (section 0) or via `/verify`.
**Read the summary lines and report counts** - never just the exit code. Distinguish new failures
from pre-existing by running the same command on the base (a checkout of
`$(git merge-base "$B" HEAD)`).

## Step 3b. Actually run it - MANDATORY

**Passing tests is not evidence the thing works.** Tests mock the boundaries, and the boundaries are
where defects live. Skipping this does not save time; it moves the discovery to a moment when it
costs more.

**Every loop must exercise the change for real** - start the service, run the CLI, drive the
endpoint, execute the job with real inputs. Whatever "running it" means in this project, do that,
against realistic data. This is not delegated to the reviewer. The live run goes through
`proof_report.py run` as well.

Discover how, if you do not know: the README's quickstart, a `docker-compose.yml`, a `dev`/`serve`
target, or how CI's integration job invokes it.

Observe more than the exit code: the output, the logs (grep for errors, retries, timeouts), and the
persisted state - the expected change present **and** nothing unrelated mutated.

**When:** at least once per loop on the first behaviour-changing iteration, and **always** on the
final one. A loop that declares done without a live pass has not finished.

**Legal skips**, each named in the report: the environment genuinely cannot be started here; the diff
has no runtime path (docs, comments, pure rename); running it would touch production. "Tests are
green" and "the reviewer will do it" are not on that list. **Not-run is a blocking condition.**

Use fictional data for anything fabricated, and tear down only what this loop started.

## Step 4. Dual review - `/code-review` + `deep-code-reviewer`

Start both in parallel, in the same turn:

- **`/code-review`** (the built-in skill) on the branch diff `"$B"...HEAD`.
- **`deep-code-reviewer`** via the `Agent` tool: `subagent_type: "deep-code-reviewer"`,
  **`model: "opus"`** stated explicitly. If that subagent type
  is not offered, use `subagent_type: "general-purpose"`, `model: "opus"` and open the prompt with
  "Read ~/.claude/agents/deep-code-reviewer.md (<project>/.claude/agents/ for a project install) and follow it." Tell the user the model in one line.

Reconcile both reports into one ranked list yourself: dedupe by site and defect, keep the higher
severity only when its evidence holds, note which reviewer raised what. Do not re-review the code
inline yourself; the reviewers own discovery.

**Never steer the reviewers.** The brief is the diff and the scope, nothing else. Never tell a
reviewer the stop condition, the iteration count, or that findings cost time. You are measuring the
code with them; telling the instrument what reading you want makes the reading worthless.

## Step 5. Fix every finding

### P3 is parked, not fixed - hard rule

A P3 goes in the ledger as `Deferred: [P3] ...` and you move on. Fix one only when it is one line at
one site. Never block an iteration on a P3, never block convergence on one, never spend a review
round on one. Measured across 338 loop commits: mechanical P3-grade work - comment trims, test
shrinks, prompt re-wording, "subsumed" pin deletions - produced 7 Criticals and 4 P1s and removed
nothing a user could see.

### The per-finding loop - do this yourself, cheaply

**Never re-run the dual review to check whether a fix worked.** That is a multi-minute pass and it
is a discovery tool, not a verification tool.

1. **Reproduce first.** Write the test that fails *because the defect exists*, before touching
   production code. **If you cannot make it fail, the finding is not real** - reject it and record
   that you tried. This single act verifies the finding, becomes the pin, and defines "done".
2. **Fix until it passes.** A reviewer's suggested fix is a **hypothesis, not a prescription** - it
   can be right about the defect and wrong about the fix, usually because it does not hold under the
   test doubles. If it does not pass, discard it and write your own.
3. **Prove you broke nothing** - the covering file, its neighbours, and **every prior iteration's pin**.
4. **Attack your own fix with cases the reviewer did not mention.** They named one instance; you are
   fixing a **class**: the sibling call site, the opposite branch, the error path, the boundary
   either side, the same pattern behind another provider. **This is the step that stops one finding
   becoming three iterations.**
5. Only now is it fixed.

### Verify the worst case before fixing

Reconstruct what happens if the finding is left alone: what breaks, the full trigger chain, the
realistic frequency, the blast radius and recovery. **If the verified worst case does not justify the
fix, `accept` it** - a fourth disposition beside fixed/rejected/deferred, recorded in the commit
trailer, the state file and the report, and **never re-fixed** on a later pass.

Security on the external attack surface is never accepted on improbability grounds.

### A rejection needs the same evidence as a finding

"Out of scope", "already guarded upstream", "not in this diff" are checkable claims. Check them
(`git diff --stat "$B"...HEAD`, `findReferences` if LSP tools are present - else Grep for callers,
actually reading the guard) before writing them down. A rejection a later reviewer disproves costs a
full iteration.

### The diff budget

Growth is fine when a fix needs the lines; a 500-line change walking out at 2000 is not. Record the
baseline (`git diff --shortstat "$B"...HEAD`) and re-check each iteration. Over ~25% growth:
**justify every added block individually or delete it.** Regression pins are exempt - count them
separately.

Ask per fix: **is this fix bigger than the bug it closes?**

### The gate - artifacts, not intentions

```bash
G="${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/skills/quality-loop/gate.py"
python3 "$G" start F1 "<description>" [--concurrency]
python3 "$G" record F1 <artifact> "<value>"
python3 "$G" done F1        # exits 1 and lists what is missing
python3 "$G" trailer F1     # emits the commit trailer block
```

The gate keeps its records in `~/.claude/quality-loop/<sha1 of the git toplevel>/findings/`, never
inside `.git/`.

Artifacts: `repro`, `class`, `siblings`, `fix`, `pin_verified`, `regression` (+ `interleavings` for
ordering bugs, written **before** the fix). `pin_verified` must be
`expected=<v> observed=<v> verdict=PASS` - **prose is rejected**. A printed 2 where you expected 1 is
a FAIL, not an explanation.

This exists because the prose version of these steps gets skipped. An empty `siblings` means you
fixed the instance, not the class.

## Step 5a. When patching keeps failing, question the code, then redesign

Triggers: **two consecutive iterations found a defect in your own fix**, or **one file edited more
than ~6 times** across the loop (slow grinding never trips the consecutive test).

**Ask the cheap question first:** **what does the user lose if this code is gone?** Answer with a
requirement, never a mechanism - "the re-open pass" makes deletion look free, "a new problem class
still reaches the index" shows what you are dropping. Then: **would deleting that requirement remove
the whole defect class?** Races and cache-invalidation defects usually mean a writer exists that
nobody asked for. Deleting a feature is the user's call - **stop and ask** (legal stop 9).

**When they approve, the cost of removal becomes an accepted finding, not a footnote.** Record it
with the same weight as any accepted risk - commit trailer, state file, PR body - because that
sentence is the thing a later reviewer files as a bug. Its three consumers: the redesign commit
states it as `dropped, accepted <date>` (the harvest list only covers behaviours you *keep*); the
next review is told to attack it; the PR body carries it verbatim as a row, never as prose, and no
summary sentence may contradict it. A "by design" or "tuning knob" label is the same record type -
a deferred finding, re-asked next time this path is touched.

Only if the requirement is confirmed necessary: **redesign, do not patch again.** Harvest the
behaviours the old code guaranteed (from its pins and the commit log), delete the implementation
**and its implementation-coupled tests** (behavioural tests survive, rewritten), rebuild **smaller**
than what it replaced, re-pin every harvested behaviour, and force a full review. One redesign per
component; a failed redesign is legal stop 10.

## Step 5b. Commit

One commit per iteration, **after** the pins verify - and after a `proof_report.py` run (or
`/verify`) newer than your last edit. Never `--amend`, never force-push.

The message body is the audit record - it is meant to be long, and it is the only home rejections
have:

```
<subject: what changed, not "quality loop iteration 3">

Fixed:
- [P1] <finding> (<file:line>)  pinned by <test>
Rejected:
- [P2] <finding> - <reason>, raised by <reviewer>
Accepted:
- <finding> - trigger <x>, impact <y>, recovery <z>; cost of fix exceeds worst case
Deferred:
- <item> - out of scope
Class: <the class of defect, not the instance>
Siblings-checked: <site: verdict | site: verdict>
Verified-by: expected=<v> observed=<v> verdict=PASS
Iteration: N | gates: <counts> | reviewers: code-review <n>, deep-code-reviewer <n>
```

Push only if a PR exists **and the authenticated user authored it** (`gh api user --jq .login` vs
`gh pr view --json author`). Never push to someone else's PR. No PR means commits stay local.

## Step 6. Loop

Rewrite the state file, then restart from Step 1. **Spawn a genuinely fresh review each iteration** -
never reuse the last report or hand the reviewer a summary of what you fixed.

**Repeat-rejection tripwire:** if a fresh reviewer re-raises something you rejected, you may not
silently reject it again.

- **Rejection backed by evidence** (a measurement, a traced path, a guard you read) -> **escalate,
  do not "fix".** Capitulating to a re-raise is how a *correct* rejection becomes a production defect.
- **Rejection that was reasoning only** -> investigate properly now, then fix or escalate.

Reachability rejections need the **deployment config**, not a code constant: "only one worker",
"unreachable in prod", "the queue serialises it" must come from Terraform / k8s manifests / the
service definition. A per-container concurrency setting says nothing about how many containers run.

## Done when

- The project's own test / lint / format / typecheck commands pass, with counts reported, each run
  recorded by `proof_report.py` (or `/verify`) after the last edit
- Neither `/code-review` nor `deep-code-reviewer` returns an unresolved P0 or P1
- **A round that returns only P3s is the last round** - park them as Deferred and stop; never fix them, never spawn another review for them
- Every finding was reproduced before being fixed, or rejected because it could not be
- Every fix was attacked with sibling cases before being marked fixed
- Every finding closed through `gate.py done`; every rejection and acceptance carries evidence
- The change was actually RUN this loop (Step 3b), or a legal skip reason is named
- Diff growth justified per-addition; no over-engineered fix or drive-by churn
- Nothing was added that is not load-bearing today
- No PR was created; no reviewer was told the stop condition; nothing was posted as the user
