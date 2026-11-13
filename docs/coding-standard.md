# Coding standard

**Version: 1** (2026-11). An agent confirms it in its briefing with the line `Standard: v1 read <date>`; when the version grows, it reads the new entries under "Changelog" at the bottom and updates the line (`scripts/standard_version.py` shows who is behind).

**Audience: anyone who writes code, a script, a hook, a site or a detection rule.** One file for yourself or a shared mechanism, no difference. These are rules about the code itself and about proving it works.

Working inside a project team (lead agent, stories, stands, releases)? Also read [project-work.md](project-work.md). Section numbers are shared between the two files: "§2.6", "§D-A" point to project-work, "§2.3b", "§3" point here.

Three things this standard is built on:
1. A repeated mistake becomes an automatic gate (§4.1).
2. Verification on the live system is done by someone other than the author (§3).
3. The product checks itself with a command (§2.4a).

If a brief, a CLAUDE.md or an old document disagrees with this file, this file wins.

---

## CORE: read every time (one screen)

Next to each rule, who guards it: ⚙ mechanism (block or hint, see §5) · 📊 audit · ✋ nobody, only you.

1. **Look at how it is done and what already exists** ✋ before the first command: the tools list, the catalog, [code-pitfalls/](../code-pitfalls/README.md), a web search. **3 failures in a row: stop and search** ⚙ (`hooks/stuck-detector.py`). (§2.1, §2.2)
2. **Operator requirements verbatim.** Unclear: one question, not an assumption ✋. (§2.5)
3. **Project code lives in the project directory, shared mechanisms in one scripts directory, secrets never in the repo** (the repo is under an auto-commit cron) ✋. (§2.3)
4. **An error is not swallowed** (no "empty" in place of a failure) ✋. **The irreversible step goes last, after a dry run** ✋. A shell chain that contains an irreversible step needs `set -euo pipefail` + `trap ERR` ✋. (§2.3b, §2.3c)
5. **A test sits next to the change and can be rerun. A test never writes to live state** (`TEST_MODE=1`) ⚙. (§2.4)
6. **"Done" only with a run in this turn** ⚙ (`hooks/proof-guard.py`: edited code and ran nothing, the turn does not end). A check states how much it checked; zero means the check is broken ✋. Critical changes (§0): **review by a different model**, `scripts/cross-review.sh` ✋. (§3, §0)
7. **Deletion is `mv` to a trash directory, not `rm`** ✋. (§2.3b)
8. **Afterwards:** you broke something, so write it into the mistakes journal ([docs/mistakes-journal.md](mistakes-journal.md)) ⚙ (format). **Same class of mistake a second time: automatic gate** ✋. New mechanism: entry in the catalog ⚙ + a watchdog check ✋. (§4)

**Nobody guards the ✋ items. They hold only on you, and this is where a multi-agent setup breaks most often.** The "standard version read" line in an agent's brief is audited 📊 (for coding agents; paused projects are excluded).

---

# REFERENCE: open the section when you do the thing

## 0. Scale: ceremony matches risk
| Change | Required |
|---|---|
| **Small** (a line, a config value, a typo) | §2.1 step 0 (does it exist already, how is it done) + §3 proof of a run |
| **Ordinary** (feature, script, fix) | everything except review by another model (a fresh subagent is enough) |
| **Critical:** shared mechanisms (hooks, gates, `settings.json`), security (access, secrets, permissions, outbound network), detection rules for a client environment, code that acts on real accounts or devices or **changes data or decisions** of the operator or a client (labels, deletion, bans, age), scripts and instructions for the operator's own hands | everything, **review by another model is mandatory** |

> Site appearance (buttons, layout) is an **ordinary** change: screenshot + scenario run, no cross-model review. Reason: 25 visible tweaks in one day on a scraping project, each a 5-20 minute fix.
> **Infra** (system config, cron, services) and **shared mechanisms** (hooks, scripts on PATH) have no roadmap and no commit trailers. The queue is the owner's TODO; rules are in §2.9. Project types (git flow / auto-snapshot): [project-work.md §2.6](project-work.md).

---

## 2. While working

**2.1 Change cycle** ([dev-methodology.md](dev-methodology.md) has the cases and costs)
| Step | What to do | What stays visible |
|---|---|---|
| **0. Look at how it is done** | Before the first command on a new technology: web search (how it is deployed, on which OS, known issues) + your own playbook in full + whether the setup already has it (the tools list, the catalog) + pitfalls ([code-pitfalls/](../code-pitfalls/README.md)). Non-trivial subsystem: read 1-2 proven open-source implementations and adapt. Two sources disagree: do not pick whom to believe, measure with one command | a `source: …` line in the report |
| **1. Requirements → where they are verified** | Every operator/brief requirement → `file:line` where it works and what verifies it. **No line, no run.** Only for tasks with several requirements; a single hand-fix is one requirement, proof of a run is enough | table in the report/review |
| **2. Reference data before live** | First reference/synthetic data with edge cases (limits, empty, overflow, negatives from operator feedback), then live | run output on the reference data |
| **3. Review by not-the-author** | A fresh subagent with no context of how the code was written. **Critical: `scripts/cross-review.sh` (a different model)**, passing the table from step 1 and the "why so" log | a file in the cross-reviews directory |
| **4. Done = proof** | see §3 | |
| **Stop rule** | 3 failures in a row: stop, go to step 0 (search), no 4th attempt | |

**How to review so that it catches things** ([dev-methodology.md](dev-methodology.md)):
- The reviewer did not see how the code was written, and you do **not** tell it where to look or "what is minor".
- A finding counts only with a reproduction (a failing test **before** the fix).
- The fix is a **class, not an instance** (neighbours, boundaries, the inverse branch).
- Write down what was rejected, so it is not relitigated.
- A large diff is a suspicion, not a merit.
- Severity is a claim until checked: test the worst case first; a fix costlier than the bug means `accept`.
- The loop is pre-authorized: a tiny stop-list, everything else it decides without asking.

**Changing a model, prompt, thresholds, judge/classifier rules** is a separate mode: [project-work.md §2.1a](project-work.md).

**2.2 Pitfalls.** Before you edit code, the hint hook (`hooks/code-pitfalls-hint.py`) shows the headings of the pitfalls for that technology. If one resembles your case, open the entry in full. Technologies: shell · python · web · services · windows · vm · git · hooks · android · concurrency · verification.

**2.2a Debugging and diagnosis.**
- **First confirm the test bench is real:** your artifact is what runs (not a checkpoint, not an old image), the observation channel (log, serial) is set up first, and you check in the operator's environment. Cost: 3 days of wrong conclusions, tests booted from a hypervisor checkpoint.
- **Measure first, then fix.** "It is the ceiling / impossible" only with proof; suspect your own bug first. Cost: a modem "ceiling" was a bug three times in one night; a noise map built in 2 s refuted 7 hours of guesses.
- **Before naming a cause: what else explains this symptom, and why is it not that?** Separate controlled evidence from coincidence in time. Do not widen evidence beyond what it covers.
- **"Flaky" is not a diagnosis.** After a fix every new red is a new cause. Instability is measured by an instrument (`runs_to_green`), not by an agent's word. Cost: five causes under one "flake"; the fifth was the OS dropping every 7th click.
- **Validate with the real code against the real artifact**, not your own reimplementation or port. Cost: a bug hid for 4 versions because the Python port was correct.

**2.3 Stack and location of code.**
- Project code lives in the project directory. Shared mechanisms live in one scripts directory owned by the mechanisms dev agent. Not in `/tmp`, not in a home directory for project work.
- Sites: the web playbook. Standard library `http.server`, one HTML file. Service, reverse proxy, address: a message to the infra agent.
- There are no secrets in the repo (it is under an auto-commit cron). They live in a config directory outside the repo.
- A new dependency or framework needs a reason in the commit or ADR ([project-work.md §4.3](project-work.md)).

**2.3b Reliable code: for everything we write** (classes from the mistakes journal, each with ≥3 cases).
- **An error is not swallowed.** A reader/parser/instrument that fails makes noise (log, rc≠0); it does not return "empty" or a default. Forbidden: `catch{}` around a whole block, `2>/dev/null` on anything important, `| tail -1` as proof, `set -e` without `trap ERR`. "Could not read" is not "empty"; "unknown" is not "no". Cost: a BOM broke a JSON file, the reader saw "empty", a bot removed likes from the wrong account; 10+ cases of this class.
- **The irreversible action goes last:** dry run first (list of targets), validation, review with PASS. A protection layer is removed only after PASS. Cost: a PIN removed before review, 30 minutes of hole in prod.
- **Writes to data/state:** tmp → check → atomic replace. Backup before overwriting. Read the result after writing. After a bulk command look at the result (`git status`, contents), not at rc (6+ cases).
- **Several entrances to one harm: one point of control** (one gate function, one source of state, one stream reader), not N checks by agreement. Controlling state has one source of truth; mirrors are derived only. A process that drives a device runs as exactly one instance.
- **Anything that can repeat** (retry, repair, restart, API pull) is idempotent. Incremental pulls use overlapping windows + dedup. Cost: fallback + repair gave 10× the mails; windows placed end to end lost job postings.
- **Wait for an event with a deadline, not a fixed pause.** `sleep` against an event of variable duration is a race by construction. The wait marker must be something that could not have been in the log before (class with 6+ cases).
- **Clean up and kill only your own** (tree/agent tag, unique resource names). Before advising "kill X" ask "whose processes will this kill?". If you killed a process with external state (lock, tmp), clean up what it held. A script with `flock` starts children with the lock fd closed.
- **Root-owned files in the corpus or shared directories:** `chown` to the working user, not 0600. Cost: git snapshots silently failed.
- **Structural edit of text by script:** anchor at the start of line (`^## …`, `re.M`) + `assert count==1` + reread the result. A mass `sed` over the corpus: review each replacement.
- **Architecture:** a floor that never falls plus the best available layer on top; no path is load-bearing. An abstraction with one implementation is a guess, prove it with a second while cheap. Refactor when there is a reason.
- **Long jobs:** a warning "doing X, ~N min", in the background with progress checks.
- **Deletion:** `mv` to the trash directory, not `rm`. Trash lives 14 days, then a cleaner removes it; anything needed longer does not go in trash. Exception: temporary things the script itself created in this run (`mktemp -d` under `/var/tmp` or `~/.cache`, not `/tmp`, which is RAM-backed). It cleans them up itself with `trap … EXIT` and does not put them in trash. Reason: 1602 browser profiles = 32 GB in trash in one day.

**2.3c A shell chain with something irreversible further on** (mv, rm, git, write to shared) runs only with `set -euo pipefail` + `trap ERR` that logs where it fell (§2.3b). A failed `cd` otherwise does not break the chain and the next command runs in the wrong place.

**2.4 Tests: where the change is.** (For project code and shared mechanisms. Infra scripts that can only be checked on the live system: positive + negative run in the cron environment + a watchdog check.) New code and the area around a refactor; do not backfill stable code. A test is a file next to the code and is rerun (`tests/`). If you broke someone else's test, you do not hand in. A hook/gate is accepted with the same command that is in `settings.json` (via `hooks/hook-safe.sh`) and by running your own typical commands through it.
- **A test never writes to live state** (logs, state, inbox, HOME, live data directories). The test wrapper sets `TEST_MODE=1` (⚙ the inbox tool and the messaging bridge then do not write to the live side). Otherwise isolate with variables (`HOME=`, `*_STATE=`). Check whether a function the test calls writes to a file itself. Cost: a deploy test wrote into a live status file; test frames landed in the live CLIP directory.
- **Run the rare branch at least once with a faked trigger** (error, "with payload", non-default answers, target hardware configuration). An empty run does not test the branch. Appending to an old script: read the tail for an `exit` above your insert. Cost: an `install.sh` dead for 3 months.
- **Real records from prod** (telemetry, dumps, live events) are stored and rerun offline as regression. Test the code that is in prod. Test detection on the table where the target events actually are.
- **Corrupted data is not passed off as correct:** integrity is checked at the level the user receives (checksum). Corrupted means refusal, not garbage. For "quietly wrong", suspect your test first.
- Where tests in a project come from (acceptance from "Done when", failing-on-bug, gate on a class, QA finding): [project-work.md §D-A](project-work.md).

**2.4a The product checks itself.** Every service/bot/site/OS has a machine-readable `/health` or `--selftest` command that says "works / not + why". Proof (§3) and the watchdog run it. Text instead of a screenshot is 50-100× cheaper. Without it the agent either trusts its own word or burns screenshots. **Command contract for an agent:** deterministic `[ok]`/`[err]`; an unknown command or argument gives `[err]`, never a quiet `[ok]`; the name matches the behaviour; health answers in any state. Cost: an outside agent lost 40-50 minutes of 120 on an `[ok]` that did nothing.

**2.5 Operator requirements verbatim.** Unclear: one question (in chat, or to the project lead through the inbox as the project does it), not an assumption. A complaint "looks odd": change only what was pointed at.

**2.6-K Git: for everyone in a shared tree** (releases, branches, worktrees, project types: [project-work.md §2.6](project-work.md)).
- **`git add` only your own files, explicitly. Not `-A`.** (The snapshot cron does `add -A` with an exclusion for one project and a check for someone else's merge. That is a mechanism, not a violation.)
- **Before a fix, check master:** `git log master -- <file>`; it may already be fixed. Cost: a mouse-click fix was done twice, the merge conflict kept HTTPS and 4 apps off the OS for 5+ weeks.
- **First line of a commit is plain language for the operator** (the dashboard shows it as "last thing done"); technical detail in the body.
- **Someone else's uncommitted WIP is not stashed, reset or cleaned.** Stop your operation and write the owner the exact list of "what and where". A destructive action for process tidiness is worse than the problem.
- **Destructive operations in the main repo are blocked by a git wrapper** on PATH (`bin/git-guard`, installed with `install.sh --with-git-guard`; protects against accidents, not against deliberate bypass: calling the real binary directly skips it, which is only done in a throwaway clone). It blocks `filter-repo` / `reset --hard` / `gc --prune` / `branch -D` / `push --force` / `clean -f` for everyone (exit 88), judged by **effect** after normalizing flags (synonyms such as `branch --delete --force`, `checkout -f`, `restore`, `switch -f`, `stash clear|drop`, `reflog expire`, `update-ref`, `worktree remove -f`, `filter-branch` are blocked too).
- **Build output does not go into git.** `.gitignore` does not act on already tracked files; you need `git rm --cached`. Cost: 1009 MB of `target/` in history blocked a public carve-out. Pitfalls: `code-pitfalls/git.md`; convention: the commit convention.

**2.9 Shared mechanisms (hooks, gates, background scripts)**
- **Change a live script/hook atomically:** write `.new` → `bash -n` / `ast.parse` → `chmod` to match the original → `mv`; then `ls -l` (permissions get lost, the hook is dead). Editing in place breaks a run in progress (bash reads the file as it goes; cost: a CI watcher script). In the private setup this is a `swap-live` tool: syntax check → permissions and owner from the live file → `mv` → check +x.
- **A test never writes to live state:** see §2.4 (applies to all).
- **A blocking mechanism is built in stages:** detector (log only) → calibration on history (share of false positives, threshold; **measure by volume, e.g. 300 turns with a code edit, not by calendar week**) → block. Choose fail-open or fail-closed explicitly and write down why. **Whatever forbids is fail-closed by default.**
- **Gate acceptance test: one fixture = one rule = one expected marker.** A fixture that triggers several rules tests none.
- **Gate acceptance matrix (mandatory):** (a) broken input / missing dependency → block, not allow; (b) bypass through a wrapper or chain (`-c "…"`, `$VAR`); (c) text ABOUT the rule or documentation with an example is not blocked; (d) the fix path that the deny message suggests is passable. Cost: without `jq` a hook exited 0, i.e. "allowed", for 4 generations; a memory gate blocked its own repair.
- **Ladder of strength:** note < detector < structural impossibility (API shape, one point of control). For each gate ask "can the way to make this mistake be removed?". Mechanism granularity = rule granularity (a rule about sessions is a hook, not a firewall; a firewall killed a deploy robot).
- **Every periodic mechanism writes a line on every tick and has `trap ERR`:** silence in the log means broken. Test a channel with a beacon carrying a unique token sent now. Cost: a release runner died silently every 5 minutes, log 0 bytes, the release stood still for 3 hours.
- **Accept a hook on the next turn** after editing `settings.json` (the harness rereads it asynchronously), and with the same command as in settings (via `hooks/hook-safe.sh`).
- **Tests run as root in `mktemp -d` (mode 700) + a script run as another user = "green" on an empty result:** `chown` the test directory to that user and check the result, not just rc.
- **One author per shared file:** `settings.json` belongs to the mechanisms dev agent; crontab/systemd/nginx/watchdog checks belong to the infra agent. **Exception, an outage:** you may patch someone else's shared script or cron yourself, only with a backup + a line in the mistakes journal + a message to the owner; the real fix is the owner's. A new background script = a message to the infra agent ("what, how often, how to check") + a watchdog check (§4.4).
- **"Wrote" ≠ "arrived".** There is no channel where a write to a file or log equals delivery. An alert channel is accepted by **delivery**: the test is that the message reached the addressee from a DIFFERENT session (or the human), not that "the file appeared". `|| log WARN` on a delivery is a defect. Cost: three channels in one day silently swallowed messages (a runner, a git snapshot, an alert about a secret).
- **An automaton that decides about someone else's work does not stay silent.** Message not delivered to the addressee: message the project lead "not delivered to <whom>", not a log line. Cost: a release runner did not find the directory (the agent's directory had a suffix), the agent thought for 8 hours the release was on its way.
- **The same failure for more than a day: message the lead.** A marker/task that fails every 5 minutes for weeks without an alarm from its author is silence (a release marker failed for weeks).
- **A finding about a secret goes straight to the domain owner** (the git agent), not through project leads. A secret's cost grows hourly. Cost: a message about a live private key in git lay in a project lead's inbox for three days.
- **A detector does not repair by itself; it calls the domain owner** when the choice of repair depends on what exactly broke. A wrong auto-repair of history is irreversible.
- **Code of shared mechanisms lives in its own git repo** with an automatic snapshot every 10 minutes (owner: the git agent).

---

## 3. Handing in: "done"

**"Done / works / fixed / proven" exists only together with a run through the PROD path in THIS turn.** The output is visible in the turn's tool calls (transcript), or there is a link to a run report/log (background review, CI, runner). In the message itself, in words: what was run and with what result. To the operator, no raw output. Self-certification does not count.
- **Proof is only an artifact that nothing but the mechanism's own work could have produced** (a log line written by cron itself, a tag, a `grep` in the recipient's file). Not proof: `crontab -l`, the file existing, rc, `✓`, an `echo` line. Verify what you wrote after writing, by reading from disk, in the right section. Cost: a runner marked "LIVE" did not run under cron for 3 hours; "sent to three people": the mail did not exist.
- **"Proven" (property, threshold, rule)** only with a control test on a reference where the answer is known in advance. A live run alone does not prove correctness. Cost: a detection query shown as proof on 3 "clean" tenants → ~20 bugs, 13 hours.
- **Verification report:** "command → what it printed → expected / actual → `VERDICT: PASS | FAIL | PARTIAL`". PARTIAL only for environment limits. "Read the code, the logic is correct" is not a check.
- **"Works" always with a place:** on which stand, whether it has the same carrier, network, hardware as the user. A conclusion about a property the stand does not have proves nothing. Cost: "the OS reaches the internet" was true in an emulator only; the operator's hypervisor had no network; all the "greens" ran without a disk.
- **An instrument does not guess and proves what it sees.** No `or`/`else` defaults on verdict parameters (do not know: assert). An artifact is checked against source freshness: the instrument refuses to run tests on an image older than the code. Check a log's timestamps before concluding. "A contradicts B" only from one run with no outside actions. Cost: half a day on a "bug 2/2" in an image 263 hours older than the code.
- **A check states its scope.** A test/gate/reconciliation writes how many objects it checked ("N files") and, below a threshold N, shouts "I am broken" rather than "clean". Green on empty is not proof. Cost: a publication gate run as root read 0 files and allowed pushing a snapshot with 6073 lines of non-English text and 97 personal names.
- **Code/script:** the launch command + its output (not only `bash -n` / `py_compile` / `node --check`). **A script for cron or the watchdog: run it in the cron environment** (`env -i PATH=/usr/bin:/bin HOME=… …`), not from an interactive shell. Cost: two watchdog checks lied for 17 hours.
- **Site/UI:** screenshot of the default state + phone width + a scenario run of the buttons in a browser (the web playbook); describe in words what is on the screenshot. **A new address/link: check from the user's machine** (`curl` from the operator's laptop), not from the VM with `--resolve`. Cost: a dashboard card resolved to NXDOMAIN on the operator's side.
- **Whatever goes into the operator's hands** (script, shortcut, instruction): the agent ran it itself at least once; an instruction has full steps.
- **Any visual** (OS screenshot, image, UI): describe in words what is visible; "works" without a description does not count. Cost: a wallpaper called "Sky" in an OS screenshot was a swamp.
- **Visual/hardware that the setup cannot verify:** the proof comes from the operator, as a 👁 line in the agent's operator-TODO.
- Handing in a story inside a project (run by QA not the author, commit trailers, report to the operator from the user's angle, human docs): [project-work.md §3-P](project-work.md).

---

## 4. Afterwards

**4.1 You broke something: write it in the [mistakes journal](mistakes-journal.md).** On top, in the format from its header (`## YYYY-MM-DD · agent · gist [class №N]` + what happened · why · confirmed fix · can it be made impossible · status). Write also what passed by luck. A technical lesson goes also into `code-pitfalls/<technology>.md`.
**A gate is accepted only by showing that it fails:** plant a real violation → exit≠0, clean input → 0. "A gate that cannot fail is worse than none." Cost: an architecture gate said "0" four times in a day with 16 violations present. A shared instrument (tests, gates, rigs) has an **owner** who regularly asks "what does this instrument NOT see by construction?".
**Second appearance of the same class in your project: an automatic gate** in the project's `tests/` or gates, run at every handover; not a third note. Example: a stream gate was born when "read a byte and discarded it" appeared three times in a day; the rule was in the journal in the morning and broken by the same agent in the evening.

**4.2 An instruction did not work as written and you found a workaround:** leave a trace at the bottom of the same file (what · why · fix, date). Confirmed only.

**4.4 New mechanism/script/site:** an entry in the catalog (+ the tools list, if other agents use it) **+ a message to the infra agent asking for a watchdog check** with a positive **and negative** run. The watchdog must shout when the object is absent. Cost: a backup job "green" for 21 hours with a dead offsite copy; a messaging bot guarded emptiness for a month. Without the entry it "does not exist" for the setup; a nightly reconciler catches this. **The watchdog looks at the result, not at a sign of activity:** "fresh" means a file written only on success; a logger counts from ≥2 data lines, not from START/Running; remove test artifacts in the same turn. Cost: the same backup job "green" on an error log for 21 hours; a hook marked "LIVE" had 0 executions for a month.

**4.5 Do not write the changeable into docs** (state, version, "next step"); only a pointer to where to look (git, the queue). Write the stable (rules, "why so").

Architecture decisions (§4.3), human docs (§4.5a), "what we do not do" (§4.6), a new project (§4.7): [project-work.md](project-work.md).

---

## 5. Who guards (and what is missing)
| What | Mechanism | Level |
|---|---|---|
| Pitfalls before a code edit | `hooks/code-pitfalls-hint.py` | hint |
| 3 failures in a row | `hooks/stuck-detector.py` | hint |
| "Done" without proof | `hooks/proof-guard.py` | **block** for code since 2026-10 (calibration: 3 triggers in 423 turns with code edits over a week, all genuine). Claimed "done" after an edit and ran nothing: run it and show the output, or say plainly it is unverified and who will verify. Off-switch `PROOF_GUARD_BLOCK=0`. For shared docs it is a hint, next row |
| Claim "done" after an edit (>3 lines) to shared docs without `cross-review` | `hooks/proof-guard.py` (docs branch) | flag + hint (cleared only when EVERY changed shared doc passed a successful `scripts/cross-review.sh` after the edit; briefs: one review) |
| Writing into someone else's inbox by hand | `hooks/foreign-inbox-gate.py`; the sanctioned path is `scripts/inbox_post.sh` | block |
| Stopping with open work | `hooks/work-guard.py` (Stop; only for agents listed in `CCM_WORK_GUARD_AGENTS`, off when empty), fail-open on purpose: a Stop gate that fell must not lock an agent forever | block |
| Whether the standard is used | `scripts/standard_version.py` (which agents confirmed which version); in the private setup also a nightly adoption audit page | on demand |
| **"Done" only with a run proof / review for critical** | a gate for the review part is the next step | |

A rule nobody guards, agents do not follow (measured). A new item in this file is introduced together with a measurement of how it is used, with an introduction date and a removal condition.

## Changelog

- **v1** (2026-11) — first public version: the core path of a change, handing in with a run proof, who guards what.
