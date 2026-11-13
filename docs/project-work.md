# Work in a project

Version: as of 2026-11 (shared with [coding-standard.md](coding-standard.md)).

**Audience: project teams**: lead agent, executors, QA, design, ops in a project with a roadmap, stands and releases. Rules about the code itself (reliability, tests, "done = a run", pitfalls, git for everyone, shared mechanisms) are in [coding-standard.md](coding-standard.md), and they apply here too.

Section numbers are shared with coding-standard: "§D-A", "§1", "§2.6–2.8", "§4.6" point here. If a brief or an old document disagrees with this file, this file wins. The reasoning is in [dev-methodology.md](dev-methodology.md).

---

## CORE: the path of a task (one screen)

Next to each rule, who guards it: ⚙ mechanism · 📊 audit (catches only what is in brackets) · ✋ nobody, only you.

**Roles:** the **operator** is Product Owner (goal, order of epics, accepts visuals/hardware) · the **project lead agent** is the only one who talks to the operator about the project; writes stories, hands out work, accepts · **executors** · **QA** (none: the lead launches a one-off verifier, §D-A) · **shared services**: the mechanisms dev agent (code of shared mechanisms), the infra agent (server), the git agent, the librarian agent (freshness of docs, registry, measurements). Communication is only through `scripts/inbox_post.sh <agent-name>` ⚙.

1. **Idea → lead → story.** A story has a **"Done when"** (a check that runs) in the project's `ROADMAP.md`, with a **size and priority**. The order of epics is the operator's. **Blocks the operator's work → 95, ahead of everything** ✋ (an audit sees only a letter tagged 🖐/9x that has sat in the inbox over a day). (§1)
2. **Lead → executor** by letter. The executor **does not block on others**: write it and keep working ✋. (§D-A)
3. **The executor works the cycle** [coding-standard §2.1](coding-standard.md): look at how it is done → requirements → reference data → code and tests (a test from "Done when"; a bug gets a failing test first) → **3 failures: stop** ⚙.
4. **Handing in: "done" only with a run in this turn** ⚙. Critical: **review by another model** ✋. ([coding-standard §3, §0](coding-standard.md))
5. **Verification on the live system by NOT the author**, along the user's path. The verifier has a veto, not the right to accept ✋. (§D-A, §3-P)
6. **A release is "reached the user"**, not "built". Deploy by script, full file set, with a version comparison ✋. (§2.6, §2.8)
7. **To the operator:** bad news first, "you wanted → now → but", what to poke at; no tech talk ✋. (§3-P)
8. **Afterwards:** you broke something, so write it into the [mistakes journal](mistakes-journal.md) ⚙. **Same class a second time: an automatic gate in the project** ✋ (an audit only counts whether the project has at least one gate). The product has a **`selftest`/`health`** 📊 (an audit checks presence only). ([coding-standard §4, §2.4a](coding-standard.md))

**Nobody guards the ✋ items. They hold only on you, and this is where a multi-agent setup breaks most often.**

---

# REFERENCE: open the section when you do the thing

## D-A. Team and process
### Roles
| Role | Who | What it does |
|---|---|---|
| **Product Owner** | the operator | sets the goal, decides the order of epics, accepts what the setup cannot verify itself (visuals, hardware, "do I like it") |
| **Project lead (HQ)** | one lead agent per project | the only one who talks to the operator about the project; writes the roadmap, cuts stories, sets priorities, hands out tasks, accepts handover |
| **Executors** | dev / front / design / DB / mobile / network / web / judge agents of the project | do the stories in their own files |
| **QA** | the project's QA agent; **no QA: the lead launches a one-off verifier** (below) | runs the live system along the user's path; has a **stop-cock, not the right to accept**: a veto stops, no veto means go (otherwise QA becomes the bottleneck) |
| **Shared services** (one set for the whole setup) | the mechanisms dev agent (code of mechanisms), the infra agent (server, services, network), the git agent (git), the librarian agent (freshness of docs, registry, measurements) | serve all projects, do not write products |

Communication is by letters in the inbox only (`scripts/inbox_post.sh`). State lives in git and the queue, not in retellings.

### How agents work together
- **Do not block on another agent:** write into the channel and keep working. A wait you cannot avoid goes into the addressee's inbox, not your chat. A lock/claim only with a TTL and a takeover rule. Design test: "does it take a living being to make this move?": yes means a cron, not an agent. Cost: two agents politely waited for each other for 2+ hours; the operator untangled it by hand.
- **Stuck: go to the lead, not the operator.** A technical, organizational, git or infra choice is not taken to the operator; the lead brings **one ready decision**, not a menu. A classifier block is a tool refusal: first a legal workaround in your own zone and a grep of memory for a permission already given.
- **Only what passes a test reaches the operator:** taste / product / priority / irreversible **and** "if they decided the opposite, would something change?". The rest is the lead's inbox and git. 🟥 blocker only when the agent really cannot go on; otherwise 🟦 direction ([docs/po-interface.md](po-interface.md)).
- **Every idea or task from the operator goes into the queue at once** with a size and a zone; the reply has one line, "where I put it". If you write "on purpose / for now / simplification" in code, put a line in the queue in the same motion. If you simplify an explicit operator limit, say aloud what drops out. Cost: a task lost for 12 days; complaints sat for 30 versions.
- **Exchange format between components** (fields, label values, messages) is written down both at the sender and at the reader. A format change goes first as a letter to the reader. One feature on two surfaces is one task on two.
- **Taking a duty off a role or mechanism:** list all its duties and assign each a new owner; removing a mechanic: `grep` the instructions + the catalog/tools list. Cost: releases were taken from an agent and the CHANGELOG duty silently went to nobody.
- **Refuting your own statement:** mark the old record "REFUTED → see", write a new one in the same channel; do not rewrite quietly. Cost: a wrong `pkill` tip lived in notes and was used.

### If the project has no QA agent
**The lead, not the executor,** verifies: it launches a **one-off verifier**, a fresh subagent with no context of how the code was written. Give it only: the story, "Done when", the address/command of the live system and the user's role ("you are a user who needs to…"). Do not give it the code or the executor's report. The subagent inherits permissions and env of its parent. Launch it with the agent tool (an agent type with the needed tool set) or `claude -p --tools "…"` (exactly `--tools`; `--allowedTools` only ADDS); no tokens in env.

**The verifier needs Bash to walk the user's path, and Bash means it CAN write** (a bought class: a reviewer with Bash littered live logs). So it walks only through the user's entrance (page, bot, `health`/`selftest` command), does not touch live data and logs; a run that changes data goes on a copy or after a backup. A code reviewer needs no Bash, only `--tools "Read,Grep,Glob"`. The verifier walks the user's path on the live system and gives every finding with reproduction steps. The lead returns findings to the executor. This is not a twin of an agent: a one-off run that dies after its report.

**When to add a standing QA agent:** when one-off verifications exceed ~5 a week, or the operator finds by hand a second time what the verification missed.

### Where tests come from
Tests are not written by the author "as it feels". They come from four sources, each with its own author:
1. **"Done when" of a story → acceptance test.** The lead writes "Done when" as a check (command, scenario); the executor turns it into a test **before** the code or together with it. No test for "Done when": the story is not handed in.
2. **Every bug → a failing test first, then the fix** (repro-first). Not reproduced by a test means the bug is not found, and the fix does not count. The test stays forever.
3. **Same class of mistake a second time → a gate** on the whole class ([coding-standard §4.1](coding-standard.md)), not a test for one case.
4. **A QA/verifier finding → a test in `tests/`**, so the next run catches it automatically.
Tests live in the project's `tests/` and are run by the deploy or CI (§2.7), not only by the author by hand.

---

## 1. Before work: where the task comes from and what it is

**1.1 A task lives in the project queue, not in a head.** Every project with code has `ROADMAP.md`:
- **Epic**: a big goal · **Story**: a piece the user will feel · **Task**: small work (no ID).
- IDs: epic `E1…`, story `E1.S1…` (assigned by the lead). The near part is written down to stories, the far part is just epic names. False precision is worse than "details later".
- **Every story has "Done when"**: a verifiable proof that runs (test, command, tag, operator acceptance), not a tick.
- **The order of epics belongs only to the operator.** The lead orders stories inside the current epic.
- **Blockers are records with a check, not words** (`BLOCKERS.md` in the project; resolving a blocker moves the story to "in progress"). In the private setup: a `blocker_add.sh` tool does this. See [dev-methodology.md](dev-methodology.md).

**1.2 Prioritization: size and priority on every queue item.**
- **Size** `XS · S · M · L · XL`: how much work.
- **Priority** `0-100` in bands: **90+** critical/now · **70+** high · **40+** normal · **10+** low · **0+** someday. Band first, then a number inside it, so there are no ties.
- **How to set priority:** the lead goes top to bottom; the first rule that fires gives the band:
  1. **Order of epics is the operator's.** The lead orders stories only inside the current epic; "maybe another epic matters more" is a line to the operator, not unilateral.
  2. **🖐 Blocks the operator's work** (broken or awkward in hand: site, buttons, bot, phone, report) → **95**, before everything. The executor finishes the current STEP (not the task) and switches.
  3. **Unblocks another agent**, someone is standing and waiting → **90+**. Cost: 5.5 hours on a handover the addressee did not see.
  4. **Irreversible or dated** (deadline, data that will vanish, a window that closes) → **70+**.
  5. **A small XS that opens something** (removes a blocker, gives proof, removes a manual step of the operator) → do it at once, no queue.
  6. **The rest by value for "Done when" of the current epic** → 40-69; does not lead to it → 10-39 or 0-9.
- **A sender's tag is a proposal:** the receiver reprioritizes against its own queue by the same criteria.
- **Do not:** keep a list of "live priorities" in a brief; it goes stale in days. Order lives in the project queue.
- Conversational work with no queue (chat, research): the tag is optional.

**1.3 The inbox is transit.** Arrived → read → done at once, or moved into your own queue with a tag and the item closed (`scripts/inbox_done.sh`). Write to others only through `scripts/inbox_post.sh <agent-name>` (a gate does not let you write by hand). If a letter arrives in the middle of long work, reread "New" before the next step.

---

## 2. While working (beyond [coding-standard §2](coding-standard.md))

**2.1a Changing a model, prompt, thresholds, judge/classifier rules** is a separate mode. Cost: 10+ judge versions as patches in a day, live AUC 0.41, worse than a coin.
1. Measure on a **held-out set** the rule has not seen.
2. Change the live version ≤1 time a day, and only if better in **both** directions.
3. A rule from one example does not go live.
4. Before an A/B, print the final prompt and check it holds no test answer (a handle, a label); this is a "trial mode".
5. Measure **noise** first: ≥2 runs of the same thing. An effect inside noise is not an effect.
6. Run a new model/judge first **in shadow** on labeled data; recalibrate thresholds before switching.
7. A rule = statement + ≥2 examples + a counterexample, written after viewing **raw data from both sides**, not the model's texts.
8. Measure against the **current baseline** (the rule in force, manual work), not against an ideal.
9. An LLM product is evaluated by fixed dimensions with a threshold. The critical dimension (hallucinations) has a **veto**. The set must contain traps and "not in the docs" cases; write down what the set does not cover.

**A model's output is untrusted input:** keys (handle, id, path) only from your own data; the verdict from the last line of a fixed format; a model that reads foreign text gets a minimum of tools (`--tools Read --strict-mcp-config`).

**2.6 Git and release in a project** (git for everyone: `add` only your own, WIP, the wrapper, artifacts: [coding-standard §2.6-K](coding-standard.md)).
> **Two project types:** **with its own git flow** (branches, worktrees, CI, a release train; a web-shop project with worktrees + a queue of markers) and **under an auto-snapshot** (a cron commits the whole tree every ~10 minutes: scraping project, sites, most others). The operator's decision (2026-10): a separate repository for projects with live development, the rest in the top repo, and **one releaser for all**. Until built, the split below holds.
- **Project with its own git flow:** work in a branch/worktree; release through the release train with a version tag; a commit carries `Roadmap: E#.S#` (§3-P).
- **Project under an auto-snapshot:** no branches or trailers; the cron commits the tree itself. The link to the roadmap is a line in the project's `CHANGELOG.md` ("E#.S# — what changed", in plain language, **time only from `date`**) at the moment of the change. Closing a story is a separate agent commit with `Roadmap:`/`Proof:`. **A release is a deploy with a recorded version** (git hash in a log/version file), not a tag. A new project with its own git flow must ask the infra agent to add its path to the snapshot exclusion.
- **Several agents in one codebase → a file owner** (a `FILE-OWNERSHIP.md` in the project): editing someone else's file requires a letter to the owner first.
- **A release is "arrived", not "built":** the version tag is set only after the build reached where it is used. Cost: v0.173 "built and not deployed".
- **Share by construction, not by agreement:** own branch/tree; own signal file `.release-queue/<branch>.ready` with the exact SHA that was verified (the automaton merges exactly that); auto-merge in its own worktree, only fast-forward into master; a shared counter (version number) is assigned by one writer at the moment of release, not by an agent at start. Minutes pass between checking state and acting, so check at the moment of the action. Cost: two agents took v0.241, 2+ hours of clinch; an unverified WIP rode into someone else's release.
- **Last-known-good** version is frozen as a rollback point, especially under an auto-snapshot where there are no tags.
- **A branch lives hours, not days** (trunk-based per DORA: merge into main at least once a day, ≤3 active branches per project; branches of days and weeks are named bad practice). Finished a piece: a marker into the releaser queue the same day. A branch older than a day is red on the dashboard (measurement ordered). **Pull master into your branch daily and always before a marker into the queue.** The author resolves conflicts at their end, not the releaser; a marker only with green tests after the pull, so the releaser has a clean fast-forward. The releaser's clean copy is not cancelled by this: it checks what will ship, not what sits in the agent's directory.
- **A project under a releaser: everything reaches master only through the queue, documents too** (ROADMAP, BLOCKERS, release.toml, .md): edit in your branch/copy → commit → marker (`releaser.py ready`). There is no separate "small" path around the releaser: two paths into master mean again "passed on trust" and uncommitted changes in the master tree that the next ff will not take (seen: ROADMAP and release.toml edited directly in the master tree). The dashboard sees the ROADMAP after release; that takes minutes. **The one exception is launch:** the releaser cannot read the first `release.toml` with the gate command (it reads the toml from master), so the mechanisms dev agent puts it into master together with `releaser.py approve` and a log line. After that every toml change goes through the queue, and a new gate command needs approve again. In the private setup the releaser is a separate tool; the repo does not ship it.
- **Waking a team agent: the built-in `SendMessage`, the content by letter.** Write the assignment with `scripts/inbox_post.sh` (a record survives a dropped tab). If it prints "⚠ not listening" or it is urgent, use the built-in `SendMessage` tool into its live tab with one line, "you have a letter from X about Y". It wakes an idle tab on its own, no alarm clock. A tab name ≠ an agent name; limits and traps are in the tools list under "waking another agent".

**2.7 Quality gates.**
- **With its own git flow:** CI on every commit of a branch (build + tests + linter), built FIRST. A red CI on your commit is your 90+.
- **Under an auto-snapshot:** the gate is at **deploy**: the deploy script runs tests and does not deploy on red (CI on snapshots of half-finished work is noise).
- A language linter/formatter is a free second pair of eyes, everywhere.
- **Red under load means "not measured", not "red":** an overloaded machine fabricates failures (OS project CI: load ≥3 → `unmeasured`; cost: all branches "red" from the rig, not the code).

**2.8 Deploy and live users.**
- **Stand names (template for web services):** `test`: team and QA, anything goes · `uat`: acceptance by the customer and the operator, only what QA signed, byte for byte, agents do not touch data · `prod`: only with the operator's permission for a specific version · `sandbox-<person>`: a sandbox with a cheat panel that does not physically exist in the prod build (+ a test on prod that it is absent). Do not call a stand "dev" (in industry dev is a developer's machine). Profiles: **a game with no public release**: `dev build` (agent + QA) → `playtest` (the customer plays; accepted = the current version with a mark), no third stand; **a tool/script**: `test` → `prod`, acceptance = the first live run.
- **Deploy to another machine with the full set of files**, then compare the live version with the source (hash); a watchdog "live version ≠ source > 30 min". Cost: a deploy of `collect.py` without `config.py` crashed the collector and a session was lost.
- **Freeze for a demo/deadline:** a flag file with a window in the project; every agent checks it before a deploy/restart.
- **Live people are on the site:** tests on a copy with a mocked `fetch`, no real labels/data on live records; nothing jumps under the hand; a service restart in a quiet window (the web playbook).
- **Before a deploy:** diff the target machine against local and review every difference; deploy only by script, no manual service restart. Cost: someone else's edit shipped to a phone in a batch.
- **Dev ≠ prod:** you do not iterate live on prod; prove it in dev, and one verified batch goes to prod; the version is visible to the user (header, first output line).
- **Interface for live people:** a destructive action comes with an undo window or a trash; the interface hides, it does not destroy; a failed action is shown to the person with the reason, not silent.
- **Messages to people and alarms:** one message with a reason, not a stream; a separate "✅ recovered"; quiet hours; a deliberate pause ≠ a failure; a daily ceiling on questions to a person.
- **A network/infra change checks all of the person's paths:** the IDE, sites from the laptop, access from the LAN, the machine's internet; not one criterion. Cost: "done" by internet while the operator was left without the IDE. **And everything that depends on the old address:** `grep -r` the old IP through code and configs BEFORE it disappears. Cost: a battery watchdog went blind overnight. **"Done" only after a real restart** of the machine/service and a read log, not after a dry run. Cost: NAT on a laptop and the VM's DNS died after a reboot, 3 hours of the operator's time. The rollback plan is written BEFORE the change.
- **Before tearing down infrastructure** (VM, disk, service): a restore document: what was removed, what is left and where, the steps to bring it back.
- **Code that drives a device/account:** before each action check the screen state; an unclear state means "back", not an action in the dark ([code-pitfalls](../code-pitfalls/README.md), android).

---

## 3-P. Handing in a story (beyond [coding-standard §3](coding-standard.md) "done = a run")
- **A story the user will feel passes a run by NOT the author, along the user's path, on the live system** (QA agent or a one-off verifier). The verifier has a veto, not the right to accept: found something, back; found nothing, goes. Code review looks at text, not behaviour. Cost: an OS project's gate was 28/28 green, the operator found 3 broken features in half an hour → a QA agent; an outside agent from scratch gave 16 findings, 11 closed.
- **A change the user will feel is handed in together with an updated line in the human docs** (user guide / CHANGELOG) and the technical doc, in the same commit/deploy.
- **A commit in a project with its own git flow** (the commit gate is **soft forever**, warning only: a block on commit is a deadlock in the middle of work; exceptions `auto:*`, releases, merges, `.md`-only commits) carries `Roadmap: E#.S#` in the body and, if it closes a story, `Proof: tag:…|cmd:…|operator:<date>`. Roadmap status is computed from git, not kept by hand.
- **To the operator, from the user's angle, bad first:** "you wanted … → now … → but …", an honest "asked and did not get", "did not ask for this, we did it ourselves", questions only he can judge, "known limits, not bugs", and a concrete route "what to poke at". No tech talk. Internal backend milestones are not sent for verification. Cost: an angle of "please check" gave ticks, while "you wanted" showed the wrong thing was built; a 30-version gap, the operator did not see fixes for his own complaints.

---

## 4. Afterwards (beyond [coding-standard §4](coding-standard.md))

**4.3 An architecture decision** ("chose X because Y"): one line in the project's ROADMAP/README/ARCHITECTURE, so a month later nobody reinvents what was done. **A log of attempts**: what was tried, what failed and why, honest and complete (HANDOFF), so another agent or model can pick it up.

**4.5a Documents for people** (user guide, instructions): after a batch of changes the lead rereads them **whole**, does not add layers. Cost: a user guide went from 131 to 60 lines after the operator's "pile of text". Style: [docs/hall-of-shame-docs.md](hall-of-shame-docs.md).

**4.6 What we do NOT do.** Sprints, story points, velocity, burndown, estimate rituals are ceremonies for teams of humans; for a swarm they are pure overhead. We take the task↔commit link + computed status + proof.

**4.7 A new project with code:** bootstrap per [dev-methodology.md](dev-methodology.md) part D: lead agent, ROADMAP skeleton, BLOCKERS, CI first, an entry in the catalog. In the private setup this is a `new_project.sh` script that creates release.toml, ROADMAP, BLOCKERS, the agents' directories, and the first commit; **a project with code (site, bot, game, service) always gets its own repo and a releaser from day one**; without its own repo only a project without code (documents, research). By hand we do not bootstrap; if the script does not fit, write to the methodology owner, no workaround. Cost: someone did the steps by hand and ended up in the monorepo without a releaser. The repo does not ship this script.

---

## 5. Who guards (project part; the rest: [coding-standard §5](coding-standard.md))
| What | Mechanism | Level |
|---|---|---|
| State of stories / "waiting on the operator" blockers | in the private setup: `blockers.py`, `story_status.py` feeding an operator-facing board | computed from files, hourly |
| Roadmaps of all projects for the operator | in the private setup: a dashboard reads every `ROADMAP.md` | every 15 minutes |
| 🖐 letter in the inbox over a day · gate on a class in the project · `selftest`/`health` | in the private setup: a nightly adoption audit | measurement |
| Commit with `Roadmap:`/`Proof:` in git-flow projects | commit-msg hook (soft) | warning |
