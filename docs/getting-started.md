# Getting started — after the install

What to do once `./install.sh` has finished and `./check-install.py` says "0 missing or broken".
For a person, not for the agent. Each step says what you do and what you will see.

## 1. The first day

1. **Restart Claude Code.** A running session doesn't pick up new hooks.
2. **`~/.claude/CLAUDE.md` is the rule set your agent works by.** The installing agent told you what is in
   it; add or change anything there whenever you like. An update never overwrites your edits (you get
   `CLAUDE.md.new` next to it).
3. **Check `~/.claude/methodology.conf`.** The installer asked for your name, working folder and time zone;
   the hints agents read use them ("ask <your name>"). Change a line and it applies on the next prompt.
4. **Optional accounts** — web search (Tavily/Exa), offsite backup, the phone bot: [`accounts.md`](accounts.md)
   lists where to sign up, what is free and which file each key goes into. Nothing else depends on them.
5. **Work as usual.** Section 2 says what changed and why.

## 2. What your agent can do now, and why

Each line: the problem you would otherwise have, what changed, how to use it.

- **It remembers you between chats.** Plain Claude Code starts every new chat from zero. Now say "remember
  that I …" and it is written to memory (`~/.claude/memory/`, the folder Claude Code's own memory is pointed at) and known in every
  later chat.
- **Long work doesn't get lost.** When a chat gets very long, Claude Code compresses it and the details are
  gone. Type **`/recap`** before that happens: what is worth keeping goes to memory first. Keep one long chat
  per topic rather than a new chat each time: the working context of a task lives in its chat.
- **It can't say "done" without checking.** An agent will happily say "fixed" without running anything. Now,
  after it edits code, it can't finish the reply with "done" until it has run something that shows the result.
- **It won't break the machine.** Commands that have killed sessions or a whole system before (`pkill -f`,
  deleting system files) are refused.
- **It knows how long you were away.** Every message you send carries the time and the gap since your last
  one, so it doesn't pick up mid-sentence a thing you left three days ago.
- **It writes so you can follow.** An abbreviation it didn't explain, a price or a law without a source, a
  reply that just restates your view back to you: the next reply gets a reminder to fix it.
- **It stops going in circles.** Three failed commands in a row: it is told to stop and look the thing up.
- **It learns from its mistakes.** A mistake it made and fixed goes into a journal (the `CCM_MISTAKES` line of
  `methodology.conf`); three of the same kind mean a mechanism is needed, not a louder rule. Lessons about a
  kind of code (`~/.claude/code-pitfalls/`) are shown to it before it edits that kind of code again.
- **It doesn't send you to rest.** No "shall we stop for today?" at the end of a reply.

**Commands for when you need them:**

- **`/grill`** — before an important decision: it looks for the holes in your plan instead of praising it.
- **`/dossier`** — before a meeting or a deal: it researches a company or a person and tests what you believe
  about them, including looking for evidence against it.
- **`/pulse`** — what people have been saying about a topic lately (Reddit, Hacker News, the web).
- **`/audit`** — once a month or so: months of rules and notes pile up, some contradict each other, some are
  out of date. It finds them.
- **`/edit`** — break a video down by scenes and editing choices.
- **`/verify`** (or "check it with a subagent") — after your agent changed code: a cheaper model runs the tests, and
  the agent may say "done" only with that proof. Running tests no longer eats the quota of the expensive model.
- **`/update`** (or just "update the system") — gets the new version, tells you in plain words what is new, installs it
  and checks it.

## 3. If something gets in your way

| You see | What it is | To change it |
|---|---|---|
| `[now: … \| gap since previous: …]` at the top of your messages | the time line above | — |
| A refused command | a gate: that command caused real damage before | intended |
| It won't say "done" after a code edit | proof-guard | `PROOF_GUARD_BLOCK=0` in `methodology.conf` makes it a hint |
| A hint about an abbreviation, a source, restating your view | checks on the finished reply; they flag, nothing is blocked | add terms you know to `CCM_GLOSSARY` |
| A line "hook failures since the last prompt" | a mechanism crashed; nothing was blocked, the error is in `~/.claude/hook-errors.log` | read the log line |

To turn one mechanism off: remove its line from `~/.claude/settings.json` (hooks) or from
`~/.claude/hooks/stop-dispatch.sh` (the checks on finished replies). An update puts our lines back, so
keep a note, or leave the line and empty its list in `methodology.conf` where it has one.

## 4. More than one agent

When one chat holds your work, a renovation and a course at once, it mixes them up. An agent is a separate
helper for one area: its own chat, folder, notes and to-do list; it knows only its area.

**Why not just a separate chat per topic?** That is where most people start, and it breaks in these places. The
first one matters most: every correction you make in a plain chat lands in the one memory all chats share, so over
months that memory fills with narrow, outdated lessons. An agent keeps its lessons in its own briefing.

| With plain separate chats | With agents |
|---|---|
| You correct a chat ("don't do X here"), and the lesson goes into the one shared memory every chat reads. It piles up, goes stale, and a lesson from one topic gets in the way of another. | The lesson goes into that agent's own `briefing.md`: it applies exactly where it belongs, the agent is shown it again whenever it changes, and the shared memory stays short. |
| A long chat gets compressed and forgets what it was for; a new chat knows nothing. You explain the role again. | The role, what it owns and its rules live in its `briefing.md`. Open any new chat with the agent's name and it is that agent again; when the briefing changes, it is shown the new one. |
| You are the messenger: you copy what one chat found into another. | Agents write letters to each other's inboxes and act on them without you. |
| What each chat still has to do lives in your head. | Each agent keeps its own to-do list and goes through it; open items don't vanish when the chat is compressed. |
| Questions for you are scattered over a dozen chats. | Each agent keeps one file of what only you can decide (`human-TODO.md`); everything else it decides itself. |
| Two chats edit the same file and overwrite each other. | Each file has one owner agent, written in the registry; others send the owner a letter. |
| A chat does nothing until you type in it. | An agent with an alarm wakes up on a new letter or a reminder by itself. |

So one chat is fine for one thing at a time. Agents pay off once you have several areas running in parallel,
or one big area (a project with a lead, developers and testing) that is too much for one chat.

The installer has
already put the shared files into your working folder (`CCM_WORKSPACE`): `AGENTS.md` (the registry),
`MISTAKES.md` (one mistakes journal for all agents), `LIBRARY.md` (the catalog of mechanisms),
`CODING-STANDARD.md` (the rules for agents that write code) and `Agents/_example-agent/` (the template). Files you already had are not touched.

1. **Create an agent:** in any chat, type **`/register-as <Name>`** (letters, digits, `-`, `_`). It copies the
   template to `Agents/<Name>/` (briefing, inbox, the agent's own todo, your todo for it) and adds a row to
   `AGENTS.md`. Running it again for the same name changes nothing.
2. **Say what it owns.** After the first real conversation the agent fills `briefing.md`: its role in one line,
   what it owns, what it doesn't touch, where its tasks come from. Check the registry row. Ownership is the part
   that matters: two agents owning one file is how work gets lost. An agent that writes code also reads
   `CODING-STANDARD.md` and confirms it in its briefing (`Standard: v<N> read <date>`); with the file listed in its
   `.watchlist`, it is shown what changed whenever the standard gets a new version.
3. **Open it:** start a new chat whose **first message is just the agent's name** (`Docs`, `docs-agent`, `Docs v2`
   all work). From then on that chat is that agent: on every message it is shown its briefing again when the
   briefing has changed, and the letters in its inbox that are still open. You never paste a briefing by hand.
   Want to call it by another word? Put it on a line in `Agents/<Name>/.aliases`.
   One agent = one chat. Don't start a second session of the same agent in the background to "listen": it acts
   where you can't see it, and the chat you talk to stays silent.
   A briefing holds what stays true (role, ownership, rules). Anything that changes on its own (who is busy, what
   version, what is next) goes to git, a log or a queue, and the briefing only says where to look: written state
   goes stale within hours, and the watchman keeps delivering it.
4. **Agents pass work to each other, not through you.** Without this you are the messenger: you copy what one
   agent said into another agent's chat. Now each agent has an inbox. Any agent (or you) drops a letter there:
   `scripts/inbox_post.sh <Name> "<text>"`. The receiver sees open letters on every message it gets, and one that
   arrives while it is mid-task right after its current step; it does the thing, or moves it to its to-do list,
   and closes the letter (`scripts/inbox_done.sh`). Writing into someone else's inbox by hand is refused, so a
   letter can't get garbled or lost. You can give an agent a task the same way without opening its chat.
5. **What needs you is in one place.** Without this, questions for you are scattered over a dozen chats. Each
   agent keeps a `human-TODO.md` in its folder: only what only you can decide (taste, product, priority,
   anything that can't be undone), one line each. The rest it decides and does itself. How agents filter what
   reaches you: [`po-interface.md`](po-interface.md).
6. **Reminders.** "Remind me at 18:30 to …" — the agent runs `scripts/remind.py`, and at that time a letter lands
   in its inbox. An agent that promises "I'll get back to it" without setting one is flagged.
7. **Agents that work without you prodding** (off until you name them at the end of `methodology.conf`, section
   "several agents"). Without this an agent with a full inbox just sits until you write to it.
   `CCM_WORK_GUARD_AGENTS` (a file, one agent name per line): these agents can't end a reply while letters are
   unprocessed or their to-do has open items (unless the reply says `STATE: waiting for …`), and they leave an
   alarm running (`scripts/inbox_wait.sh`), so a new letter wakes the chat by itself.
   `CCM_STATUS_GUARD_AGENTS`: these agents can't tell you "story X is done / waiting for you" without checking first.
8. **When a project needs a team** (a lead agent, developers, QA): `scripts/new_project.sh --own-repo <Name>` (a code project
   with its own git repo) or `--no-code <Name>` (a folder in the shared one) creates the project files (roadmap,
   blockers, release settings) and the agents `<Name>-HQ` (the lead) and `<Name>-Dev`; [`project-work.md`](project-work.md) is the standard the team follows,
   [`dev-methodology.md`](dev-methodology.md) is what the agent that starts a project does. The release queue (a separate system
   user merges into the main branch only after the tests pass) and the git wrapper (blocks history-destroying
   commands in the shared folder) need root and are installed only on request:
   `./install.sh --with-releaser`, `./install.sh --with-git-guard`.

## 5. What looks after the system (upkeep)

Runs from the crontab block the installer added; nothing to start by hand.

- **The supervisor** (every 15 min) runs 20 checks of whether the mechanisms still do their job: hooks present
  and not timing out, the watchman alive, reminders delivered, an agent not stuck on an API error. What is red
  is in `~/.claude/supervisor/summary.json`; the two that need you (an agent can't answer after your message; a cut-off
  write left empty objects in git) appear as one line at the top of your next message to any agent. After the machine was off,
  the "nothing updated for N minutes" checks stay quiet until they can be judged again.
- **Who fixes it:** by default nobody gets a letter — findings stay in files. Put an agent's name into the
  "upkeep and supervision" keys at the end of `methodology.conf` (`CCM_INFRA_AGENT`, `CCM_MISTAKES_KEEPER`,
  …) and that agent gets the finding in its inbox. The weekly mistakes-journal review, for example, tells its
  keeper which kind of mistake repeated three times and needs a mechanism.
- **Your quota:** `scripts/quota_status.py` shows how much of your plan is used (it asks Anthropic with your
  own login, read only); a daily token report is written to a file, not sent anywhere.
- **A copy of your chats:** every night at 03:10 the Claude Code transcripts are copied to
  `~/.claude-backups/<date>/` (unchanged files share disk space). Nothing is deleted unless you enabled cleanup,
  then copies older than a year. The supervisor turns red if the copy is older than a day.
  Want your working folder committed to git every night as well: `./install.sh --with-git-snapshot`.
- **History of the mechanisms' code:** every 10 minutes the installed hooks and scripts are committed into a
  separate git (`~/.claude/mech.git`), so "what changed in this gate since yesterday" has an answer.
- **Publishing a repo:** `scripts/public_gate.sh <dir>` refuses a push to anywhere public if the repo or any
  commit in its history has a secret, a name from `CCM_PUBLIC_GATE_NAMES`, an internal swarm file (inbox,
  briefing, mistakes journal) or Cyrillic text. The last two are defaults for a private swarm: for a repo that
  ships such files on purpose, set `CCM_PUBLIC_GATE_CYRILLIC=0` or narrow `CCM_PUBLIC_GATE_INTERNAL`.
- **Spends a model's quota, so off by default:** daily memory consolidation and correction stats —
  `./install.sh --with-consolidation`.

## 6. Keeping it up to date

Tell your agent **"update the system"** (`/update`): it pulls the new version, tells you what is new, installs it the
way you installed it and checks it. By hand: `cd ~/claude-code-methodology && git pull && ./install.sh`, then
`./check-install.py --user`.
Your memory, lessons, permissions, model, own hooks and `CLAUDE.md` edits are kept; anything replaced is
backed up next to itself as `*.bak-<time>` (skills under `~/.claude/.methodology-installed/backups/`, so
Claude Code doesn't load a copy as a second skill). Chats and history are never touched.
Nothing that deletes files runs unless you enabled it (`--enable-cleanup`).
