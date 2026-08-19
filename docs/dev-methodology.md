# Orchestrating development with a swarm of agents

A reusable way to build software with a swarm of AI agents — not a single project, but a **system** you
deploy onto any project with one command. This is the delivery layer that sits on top of the mechanisms in
[`multi-agent.md`](multi-agent.md): roles, roadmap, quality gates, and how a "product team" runs when the
team is agents.

## The thesis

In a human team, hygiene — tests, review, CI — costs **person-hours**, so startups cut it and debt piles
up. In an agent swarm the tedious part costs ~zero labor, so you can hold hygiene **better** than most
startups, not worse. The proof route is deliberate: invent the method on one project → prove it ports to a
small one → apply it where it makes money.

## Roles

Each agent is a separate session with its own briefing, raised by name. Roles come in two kinds — and the
split matters: without it, bootstrapping a new project would duplicate the shared services every time.

**Shared** — one instance for the whole swarm, serving every project. Bootstrap *connects* to them, it
doesn't recreate them:
- **Orchestrator** — takes "deploy the infrastructure", creates a new project's team, holds the
  cross-project picture. (It runs bootstrap, because the project's own HQ doesn't exist yet.)
- **Knowledge/archivist** — knowledge hygiene across the swarm: where things live, delivery into
  briefings, freshness. Does not author engineering content.
- **Git agent** — git practice across all repos (conventions, hooks, incident review).
- **Infra agent** — VM / CI tooling / hooks / the board, for every project. Builds mechanisms, not product.
- **Growth / PR** — the public image (shared, spans projects).
- **Secretary** — message routing between agents.

**Project-specific** — bootstrap makes a fresh instance per project:
- **Project HQ** — architecture, priorities, branch decisions. The **single interface to the human** for
  this project: it filters the stream and doesn't relay raw agent reports. Delegates; doesn't do the small
  work itself.
- **Dev** — implementation (tasks, bugs, release flow).
- **QA** — testing on user cases; findings → Dev.
- **Design** — visual / UX, if the product has an interface.
- **+ project-specific specialists** as needed.

**Human (not an agent):**
- **Product owner** — sets epic priority; accepts "done" on what the swarm can't self-verify (visual,
  hardware, business).

**How the swarm talks:**
- **inbox = an async channel** between agents — a cheap replacement for an expensive live "dial" (a
  `-p --resume` invocation costs dollars per call; an inbox line costs zero). Arrived → do it or move it to
  your own todo → close the inbox item. An empty inbox is normal.
- **git = shared memory and source of truth.** State is not relayed — you look at the code / log / tag.
- **A board** (a concept) — agent state + roadmap + queue, all **computed from git**. The portable thing is
  the board *concept*, not any one implementation (ours is the panel in [`mission-control.md`](mission-control.md)).

## Delivery practices

**1. Version control.** git + worktrees (branches don't block each other) + a release train (a release is
something deployed/built, with a version tag).

**2. Roadmap: Epic → Story → Task + a Definition of Done.** An **epic** is a big goal, a **story** a
user-facing slice, a **task** small work. **DoD = proof it runs** (a test / command / tag / human
acceptance), never a checkbox and never self-certification. Keep an honest horizon: near work broken into
stories/tasks, far work named as an epic with no detail — fake precision is worse than an honest "details
later".

**3. Task fields: size + priority** (for anything in the queue). Size `XS·S·M·L·XL`. Priority `0-100` in
**bands**, not false precision: 90-100 critical · 70-89 high · 40-69 normal · 10-39 low · 0-9 someday.
Conversational work (chat/research, not queued) is exempt.

**4. PM link: the roadmap is a live mirror of git.** A commit carries a `Roadmap: E#.S#` trailer; status is
**computed from git, never hand-maintained** (anti-staleness, below). A rollup script feeds the board.
"Done" only with proof: `Proof: tag:… | cmd:… | accepted:date`. Self-certification ("it works") doesn't count.

**5. Quality gates** (what most startups lack):
- **CI on every commit** — build + tests + linter → green/red, catching breakage at the moment it's
  introduced. Build it **first**; without it, tests rot.
- **Tests at three levels** — unit (one function), integration (a few together), e2e (the whole system as a
  user). Rule: **test where the change is** (the new code and around a refactor), don't backfill stable code.
- **Static analysis** — linter/formatter, free second eyes.
- **Independent review before merge**, with a *different* viewpoint (an author reviewing themselves is
  theater). Cheap in a swarm: a reviewer agent, or multi-agent review.
- **Coverage** — a fog map of what's lit by tests; later, once tests exist.

**6. Incident journal** — see [`mistakes-journal.md`](mistakes-journal.md). One mistake is chance; three
identical ones are a design hole to mechanize.

**7. ADR — architectural decisions written down.** "Decided X because Y", so a year later you know *why*
instead of re-deriving it.

**8. Reliability: mechanism > briefing > rules-file.** A rule that must hold gets mechanized (a hook / gate
/ script), not left to briefing discipline. A briefing is forgotten; a hook isn't.

**9. Anti-staleness.** A document doesn't describe what can be **computed**. Test each line: *"can this
become false without anyone editing this file?"* Yes → it's **state** (who's busy, current version, branch
status) → it lives in git / the queue, the file holds only a pointer. No → it's **durable** (roles, rules,
the spirit of decisions) → write it. A date doesn't save a stale line. Check another agent's status **in
the source**, don't quote their todo.

## What we don't do

**Sprints, story points, velocity, burndown, estimation rituals.** Those exist for *human* teams — to
estimate the unknown, sync ten people, report to a manager. A tireless agent swarm needs none of it; it's
pure overhead. Keep the connective tissue and the computed status; drop the planning ceremony.

## Bootstrap: "deploy the infrastructure for project X"

The **orchestrator** runs it (the project's HQ doesn't exist yet); the **infra agent** builds the
mechanism. One command → a project-specific team raised and **connected** to the shared services (which are
not recreated). It stamps:
1. **Structure** — folders for the project agents, the code, project docs.
2. **Project agents from templates** — HQ/Dev/QA/Design get a briefing skeleton (role, boundaries, how it
   works, a **link to this methodology** — shared, not a copy).
3. **A roadmap skeleton** — an empty roadmap (Epic/Story/DoD) + PM rollup + a board entry.
4. **Git convention + hooks** — commit-message format, the release train (inherited from the shared git agent).
5. **Quality-gate scaffold** — a CI skeleton for the project's stack, the incident log, the inbox protocol.
6. **Registration** of the new team in the swarm registry + **connection to the shared services** (so the
   archivist sees it, the git agent covers its repo, the board shows it).

## Portability: what changes, what doesn't

**Identical across projects:** the project-team template (HQ/Dev/QA/Design) + connection to shared
services, roadmap/DoD, size+priority fields, the PM-git link, the incident log, review, anti-staleness,
"mechanism > briefing", inbox communication. *(The shared services are not replicated — they're one set for
the whole swarm.)*

**Changes per project:** the test toolchain (`cargo test` → `pytest`/`jest`/…), the CI target, the set of
project-specific agents, whether Design/PR exist at all.

Domain specifics from the project where this was forged (a bare-metal OS: `no_std`, a framebuffer) do **not**
port — but the method does.
