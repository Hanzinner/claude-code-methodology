# The setup against the published sources

A review of this setup's development method (see [`dev-methodology.md`](dev-methodology.md), [`project-work.md`](project-work.md)) against established practice (DORA, Google SRE, Continuous Delivery, Fowler, ADR) and against 2025-26 agent-team frameworks. As of 2026-11-02.

How it was made: two separate searches by subagents, one for theory (20+ years of practice), one for what others built on agents in 2025-26. The first theory report came back written from memory; it was sent back and returned with a mark next to every source: opened and confirmed / replaced / dropped. Only what passed is below. Sources the agents did not open are listed at the end.

Where a claim has no source, it is this setup's own observation and is marked so.

## 1. Summary

- **The load-bearing parts held up.** Flow without sprints, a releaser working from a clean copy, stands promoting the same build, QA who is not the author, failing test first, a mistakes journal, a template instead of prose: each has an established name and sources that say the same.
- **Three things the sources would call mistakes:** agent branches living days (norm: hours); a cheat panel guarded only by a flag on a stand (norm: the code is absent from the production build); the decision journal as one file (norm: one record per decision).
- **New, and aimed at our recurring failures:** tasks as data with dependencies, not text; "passed" set by a script, not by the agent; no task number, no start; a limit on concurrent tasks per agent.
- **The most serious finding:** about 70 long-lived named sessions is rare. The common model is short runs: task, agent, result, session closed. Not a verdict, but a separate discussion (section 5).

## 2. What held up

| Ours | Industry name | What the source says | Where in this repo |
|---|---|---|---|
| Queue without sprints; epic, story; priority in bands | **Kanban** (flow) | Kanban Guide; DORA "small batches": sprints are not needed for speed | [`dev-methodology.md`](dev-methodology.md) (Delivery practices 2-3, "What we don't do"); `scripts/stats_projects.py` reads epics and stories from `ROADMAP.md` |
| Only the human orders epics | Product Owner orders the backlog | Scrum Guide: the backlog is the single source of work, ordered by one person | [`dev-methodology.md`](dev-methodology.md) (Roles: human) |
| "Done when" is a check that runs | **Acceptance criteria** in executable form | Fowler, Given-When-Then | [`project-work.md`](project-work.md) (stories with a runnable "Done when") |
| Releaser: clean copy in a separate folder, separate user, all checks, only green reaches the main line | **Merge queue / deployment pipeline**, "build once", hermetic builds | GitHub merge queue, GitLab merge trains, Continuous Delivery (Humble/Farley); Google SRE "Release engineering": approval, build and deploy rights are **separated**, which is a direct basis for the separate user | `scripts/releaser.py`, `scripts/setup-releaser.sh` (`releaser` user, commands from `release.toml` run only after a root `approve`) |
| Test, Dev, Prod: the same build byte for byte; Prod only with the human's permission | **Environment promotion** + approval gate | GitHub Environments: required reviewers, a run cannot be approved by whoever triggered it | stand names and rules in [`project-work.md`](project-work.md) (stand names template); the human-permission file is not in this repo as a mechanism |
| Vulnerability and secret scanning in the gate | DevSecOps | DORA pervasive security | `bin/secret-scan`, `scripts/public_gate.sh` |
| QA checks the live product as a user, without reading code | **Black-box / exploratory testing** | Fowler "Practical test pyramid" (with the warning: keep e2e tests to a minimum, they are slow and flaky) | [`project-work.md`](project-work.md) (QA) |
| A bug gets a failing test first | Regression test first | Fowler; Google eng-practices (checked by someone other than the author) | [`coding-standard.md`](coding-standard.md) |
| "Done" only with the output of a run; a gate blocks words | **Claim-vs-evidence gate / verification gates**, now a named practice for agent teams | InfoQ 2026-06 on AI writing code faster than people can verify it; dev.to; a study of 20,574 sessions: a false "tests passed" accounts for 22.6% of mismatches | `hooks/proof-guard.py` (a detector, not a block), `hooks/status-guard.py`, `scripts/story_status.py`; see [`measurement-and-proof.md`](measurement-and-proof.md) |
| Review by another model for critical changes | Independent reviewer | Sonar 2026: an LLM judge changes 7-17% of verdicts on repeat, so **model review complements tests, it does not replace them** | `scripts/cross-review.sh` |
| `MISTAKES.md`: root, fix, mechanism | **Blameless postmortem** | Google SRE: a postmortem without a follow-up action is no different from no postmortem. Our "second case of a class means an automatic gate" is stricter than the norm (own observation) | [`mistakes-journal.md`](mistakes-journal.md), `hooks/mistakes-format-gate.py`, `scripts/mistakes_review.sh` |
| Knowledge moves by script and a project start command, not prose | **Golden path / scaffolding** | Spotify Golden Paths; CNCF platforms whitepaper | `scripts/new_project.sh` |
| One repository per project | Polyrepo | An acceptable choice, no universal answer | [`project-work.md`](project-work.md) (two project types) |

## 3. Where we deviated, and it was a mistake

1. **Agent branches lived days.** DORA: in trunk-based development a branch lives "no more than a few hours", merges at least daily, at most three active branches; branches of days and weeks are named as worse practice. In a pilot project the agents sat on their branches for days. Agent tasks are short, so it hurts less, but the rule "hours, not days" had to be written down. Now written: [`project-work.md`](project-work.md) ("A branch lives hours, not days"). The dashboard measurement of branch age is marked there as ordered; `scripts/repo_stale.py` is the nearest thing in this repo.
2. **A cheat panel for the human's own stand guarded only by a flag.** Fowler allows such toggles "for automated tests and maybe manual exploration"; OWASP classes active debug code as security misconfiguration (CWE-489). Correct: the panel's code is **absent** from the production build, and a test on Prod checks that those addresses do not exist. Now written: stand names in [`project-work.md`](project-work.md) (`sandbox-<person>`). No mechanism in this repo enforces it.
3. **The decision journal as one file.** The ADR norm (Architecture Decision Record, Nygard): each record is a separate numbered file, numbers are not reused, a replaced record is marked "superseded". There is no direct source saying one large file does harm; this is a deviation from the norm, not a proven damage. Fixed: [`swarm-template/decisions/`](../swarm-template/decisions/README.md).

One correction to ourselves: an earlier claim that "acceptance is the Product Owner's decision under Scrum" is **not in the Scrum Guide**. The split "QA has a veto but does not accept; the customer accepts" is our own choice. Logical, not canon.

## 4. New: what we lacked and what it would cure

Ordered by how much of our pain each closes. "Here" is checked against this repo.

| # | Practice | Who does it | What it cures | Here |
|---|---|---|---|---|
| 1 | **Tasks as data, not text.** A tracker with a dependency graph; the agent receives only unblocked tasks; status is computed | Beads (`bd ready`), Anthropic `feature_list.json`, Claude Code agent teams | A task gets lost; the roadmap turns into a diary (own observation) | Partial: stories are lines in `ROADMAP.md`, state is computed by `scripts/story_status.py`, blockers are records (`scripts/blockers.py`). No dependency graph. |
| 2 | **"Passed" is set by a script after test steps, not by the agent.** Every feature starts as "not passed" | Anthropic long-running harness; a `TaskCompleted` hook (exit code 2 = refuse) | "Everything is done" turns out untrue | Not in this repo. `hooks/proof-guard.py` only flags a claim with no successful run. |
| 3 | **Issue-first as compulsion:** no task in the tracker, the agent does not start | Copilot coding agent, claude-code-action, OpenHands; a `TaskCreated` hook | A task gets lost | Partial: `scripts/take_task.sh` records the task number; the hook reading it is a detector/journal for now, not a block. |
| 4 | **A separate "ready for acceptance" status; "accepted" can only be set by a human account** (a mechanism, not a rule) | Analogues: GitHub "someone other than the pusher must approve", "no approving your own run"; a discussion that an AI approval does not count | "Everything is done" turns out untrue | Not in this repo as a status. Acceptance is a rule in [`project-work.md`](project-work.md). |
| 5 | **A limit on concurrent tasks (WIP limit)** per agent and per stage | Kanban Guide: without it Kanban is just a list | Tasks started and forgotten | Not in this repo. |
| 6 | **Branches in hours, at most 3 active** | DORA | Merge conflicts, stale branches | Written in [`project-work.md`](project-work.md); measured by nothing yet. |
| 7 | **Decisions as separate files with a status** | Fowler, Nygard (ADR) | The one-file journal | [`swarm-template/decisions/`](../swarm-template/decisions/README.md) |
| 8 | **Finding the culprit in a red batch** (split the batch in half until the offending change is found) | Gas Town Refinery | A releaser with several changes in one run | Not in this repo. |
| 9 | **The four DORA metrics** from releaser data: deploy frequency; lead time from commit to prod; share of deploys needing intervention; time to restore | DORA four keys | An answer to "how are we doing" as a number, without rituals | Not in this repo. `scripts/releaser.py` keeps a log, the metrics are not computed from it. |
| 10 | One-step rollback with practice; health on prod; automatic dependency updates; CODEOWNERS (a file of code owners that calls the reviewer automatically); changelog and semantic versions | SRE, GitHub | Hygiene | Partial: `bin/swap-live` and `bin/git-guard` exist; the rest is not in this repo. |

On naming stands: "a stand for me with freedom to act" is in industry a **sandbox / review app**; the "Dev/Show" stand where a stakeholder looks is **UAT** (User Acceptance Testing) or a demo. Naming stands in the established way keeps agents from confusing them; the stand names in [`project-work.md`](project-work.md) follow this.

## 5. Long sessions against short ones

No public example of a swarm of about 70 long-lived named sessions was found. The common model is different: task, an agent starts, does it, opens a merge request, the session dies (Copilot, claude-code-action, OpenHands, a Cursor experiment that restarts agents every cycle). Reasons given in the sources:

- a long session degrades: the further, the worse the answers (context rot);
- an error in one session raises the chance of an error in the next in the same repository (0.52 against 0.34, the 20,574-session study);
- short runs are cheaper and easier to verify.

Where long sessions exist (Gas Town: the "Mayor" is long-lived, workers are short), state lives **outside**, in git and the tracker, not in the session's memory. Part of this is true here: briefing, inbox, todo and journals live in files, which is why a context compaction does not kill the work for good (own observation; see [`context-management.md`](context-management.md)). Whether a role such as a project's dev agent should live for months or start per story and die is a real question, and it depends on how the human wants to work (tabs they do not want to multiply). Left open, not decided.

## 6. What we have that was not found elsewhere

- A blocker register that clears a blocker itself when its check passes and moves the story to "in progress" (`scripts/blockers.py`).
- A mistakes journal with classes and a link "class repeated, mechanism ordered" ([`mistakes-journal.md`](mistakes-journal.md)).
- Three stands with a QA signature and a file holding the human's permission for a specific version. The stands are described in [`project-work.md`](project-work.md); the permission file is not in this repo.
- Nightly audits: whether the standard is used, orphaned documents (`scripts/stats_adoption.py`, `scripts/stats_orphan_docs.py`, `scripts/project_drift.py`).
- A releaser under its own user, in a clean copy, run by cron (`scripts/releaser.py`). In the wider world a CI server does this; nobody was found showing the same on Claude Code. This is "not found", not "does not exist".

## 7. Order of work proposed at the time

By benefit per unit of work. Nothing starts without the human's yes.

1. Tasks as data + "passed" set by a script + a "waiting for acceptance" status that only a human can clear (rows 1, 2, 4 of the table): one mechanism, not three. Look at Beads before building our own: a ready tracker for agents, installed with one line in a briefing.
2. Issue-first as a hook: no task number, no code (row 3). Cheap, because it is a hook.
3. Fix the three deviations of section 3.
4. A WIP limit: first as a measurement on the dashboard (how many "in progress" per agent), then as a limit.
5. DORA metrics from the releaser, once the releaser runs on a first project.

Two notes without action: model review does not replace tests (Sonar); e2e tests in the gate should be few, or a five-minute releaser cycle will not hold.

## 8. Sources

**Theory:** Kanban Guide (kanban.university/kanban-guide) · Scrum Guide (scrumguides.org) · DORA: working-in-small-batches, trunk-based-development, pervasive-security, dora-metrics-four-keys (dora.dev) · Continuous Delivery patterns (continuousdelivery.com/implementing/patterns) · Google SRE: release-engineering, postmortem-culture (book and workbook), monitoring-distributed-systems (sre.google) · GitHub docs: merge queue, protected branches, environments, CODEOWNERS, Dependabot · GitLab merge trains · Fowler: GivenWhenThen, practical-test-pyramid, feature-toggles, ArchitectureDecisionRecord, BlueGreenDeployment, CanaryRelease · Nygard, "Documenting architecture decisions" (2011) · adr.github.io · Spotify Golden Paths · CNCF platforms whitepaper · Shape Up (basecamp.com/shapeup) · scrum.org, DoD vs acceptance criteria · Sonar 2026, "what happens when two AI agents review code" · OWASP Top 10 2025 A02 · writethedocs, docs-as-code · monorepo.tools.

**Practice:** Claude Code docs: agent-teams, best-practices, hooks-guide (code.claude.com) · Anthropic research: effective-harnesses-for-long-running-agents; building-c-compiler · GitHub Spec Kit (github.com/github/spec-kit) · BMAD-METHOD (github.com/bmad-code-org/bmad-method) · cc-sdd (github.com/gotalab/cc-sdd) · Beads (github.com/gastownhall/beads) · Gas Town (github.com/gastownhall/gastown) · ruflo (github.com/ruvnet/ruflo) · Cursor, "Scaling agents" (cursor.com/blog/scaling-agents) · claude-code-action (github.com/anthropics/claude-code-action) · Copilot coding agent (github.blog) · Devin Review (docs.devin.ai) · OpenHands resolver · AGENTS.md / Agentic AI Foundation (openai.com/index/agentic-ai-foundation) · the 20,574-session study (arxiv.org/html/2605.29442v1) · doc rot: allstacks.com, addyosmani.com/blog/agents-md.

**Not opened by the agents:** Claude Squad, SuperClaude, Devin playbooks, CrewAI/AutoGen for code; the body of Google's "Just say no to more e2e tests"; Atlassian WIP limits.
