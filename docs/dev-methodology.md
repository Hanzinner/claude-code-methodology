# Starting a project

For the agent asked to start a new project ("start a project X", "set up a team for X"). The team's day-to-day
rules are in [project-work.md](project-work.md), the rules for code in [coding-standard.md](coding-standard.md).
Do the steps in order; do not bootstrap by hand.

## 1. Ask the human, in one message

- What is it, for whom, and what does a first version that counts as "done" look like?
- Is it code (a site, a bot, a game, a service, a tool) or not (documents, research)?
- For code: is it a site, a game or a tool? (It sets the stands: web test/uat/prod, game dev-build/playtest,
  tool test/prod.)

Do not ask how many agents; you propose positions in step 3.

## 2. Create it

- Code: `scripts/new_project.sh --own-repo --profile web|game|tool <Name>` — a project with code always gets
  its own repo (and the release queue, if it was installed with `./install.sh --with-releaser`).
- No code: `scripts/new_project.sh --no-code <Name>` — a folder in the shared workspace.
- A contribution to someone else's open-source project: `--no-code` plus a clone of the upstream for the code; the release is a pull request the author accepts (project-work 4.7).

It creates the project folder, `release.toml`, `ROADMAP.md`, `BLOCKERS.md`, the first commit (own repo) and the
agents `<Name>-HQ` (the lead) and `<Name>-Dev` with briefing, inbox and to-do. Extra agent names after `<Name>`
are created too. Exit: 0 ok · 2 usage · 3 already exists · 4 a step failed (it names the step; what was created
stays). If the script does not fit the case, tell the human; no workaround by hand.

## 3. Propose the positions; the human decides

Write a list, one line per position: the role and why this project needs it (roles: [project-work.md](project-work.md),
section D-A):

- **Lead (HQ)** — always; the only one who talks to the human about this project.
- **Dev** — always for code.
- **QA** — once there are users or money; without it the lead runs one-off verifiers (project-work D-A).
- **Design** — if there is an interface people look at.
- **Specialists** as the product needs: front end, security, ops, mobile, data. Four roles are a floor, not a
  template: a site that takes money needed eight.

The human picks. Create each chosen agent with `/register-as <Name>-<Role>`. Shared services (mechanisms dev,
infra, git, librarian) are one per setup, not per project: connect to them; if one is missing, say so to the
human, don't create it yourself.

## 4. Hand over to the lead

Write to `<Name>-HQ` (`scripts/inbox_post.sh`) what the human said in step 1, and that its first steps are:

1. Fill its briefing and each agent's: role in one line, what it owns, what it doesn't touch.
2. `release.toml`: put the gate command in `test` (it runs before every release; empty = the project shows
   red). The release queue runs it only after `sudo scripts/releaser.py approve <Name>`: root only, so give the
   human that exact line to run.
3. CI and tests first, before features: without them tests rot (project-work 2.7).
4. `ROADMAP.md`: epics and stories, each with a Definition of Done that is a proof (a test, a command, a tag, the
   human's acceptance); size and priority on every item (project-work 1.1–1.2). Near work in detail, far work
   as a named epic only.
5. Each agent puts `PROJECT-WORK.md` and `CODING-STANDARD.md` on a line of its `.watchlist`, so it sees their
   changes.

Then tell the human in two lines: the project exists, who is in the team, and that from now on they talk about
it to `<Name>-HQ` (a new chat whose first message is `<Name>-HQ`).
