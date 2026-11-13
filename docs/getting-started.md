# Getting started — after the install

What to do once `./install.sh` has finished and `./check-install.py` says "0 missing or broken".
For a person, not for the agent. Each step says what you do and what you will see.

## 1. The first day

1. **Restart Claude Code.** A running session doesn't pick up new hooks.
2. **Read `~/.claude/CLAUDE.md` and rewrite the "personal taste" sections** (communication, output, rule 12)
   to how you want to be talked to. The rest are mechanisms; leave them. An update never overwrites your
   edits (you get `CLAUDE.md.new` next to it).
3. **Check `~/.claude/methodology.conf`.** The installer asked for your name, working folder and time zone;
   the hints agents read use them ("ask <your name>"). Change a line and it applies on the next prompt.
4. **Work as usual.** You will start seeing the mechanisms — see "What you will notice" below.

## 2. Day to day with one agent

- **One long chat per topic, not a new chat each time.** Memory and the rules carry over between chats,
  but the working context of a task lives in its chat. Before the chat gets compacted (`/compact`, or
  Claude Code does it itself when the context fills), run **`/recap`**: it saves what is worth keeping to
  memory. After a compaction, details are gone; `/recap` is how they survive.
- **"Remember that …"** — the agent writes a memory file and a line in `memory/MEMORY.md` (the index).
  Memory is checked weekly for broken links and orphans (you see a line only if something is wrong).
- **The agent made a mistake and fixed it** → it writes an entry in the mistakes journal (where: the
  `CCM_MISTAKES` line of `methodology.conf`; a template is `swarm-template/MISTAKES.md`). Three of the
  same kind = a mechanism to build, not a louder rule.
- **Code lessons** in `~/.claude/code-pitfalls/` are shown to the agent (headings only) before it edits
  that kind of code. When it steps on a new one, it appends it there.
- **Slash commands:** `/recap`, `/audit` (contradictions and stale facts in your rules and memory),
  `/grill` (stress-test a plan), `/pulse` (what people say about a topic lately), `/dossier` (research a
  company or person against a hypothesis), `/edit` (break down a video).

## 3. What you will notice (the mechanisms working)

| You see | What it is | If it bothers you |
|---|---|---|
| `[now: … \| gap since previous: …]` at the top of your messages to the agent | the agent knows the time and how long you were away | — |
| The agent refuses `pkill -f`, `rm` on system files | gates: those commands killed agent sessions and a machine before | intended |
| "Done" is refused until it runs the code | proof-guard: a claim of "fixed" after editing code needs a run in the same turn | intended |
| The reply doesn't end with "shall we stop for today?" | pause-guard blocks that ending | remove the Stop branch (below) |
| A hint to expand an abbreviation, to give a source for a price or a law, not to restate your view | detectors on the finished reply; they flag, the hint comes on the next turn | add terms you know to `CCM_GLOSSARY` |
| "3 failed commands in a row — stop and look it up" | stuck-detector | — |
| A line "hook failures since the last prompt" | a mechanism crashed; it failed open (nothing was blocked), the error is in `~/.claude/hook-errors.log` | read the log line |

To turn one mechanism off: remove its line from `~/.claude/settings.json` (hooks) or from
`~/.claude/hooks/stop-dispatch.sh` (the checks on finished replies). An update puts our lines back, so
keep a note, or leave the line and empty its list in `methodology.conf` where it has one.

## 4. More than one agent

Several named agents, each in its own chat with its own folder, talking through inboxes. The installer has
already put the shared files into your working folder (`CCM_WORKSPACE`): `AGENTS.md` (the registry),
`MISTAKES.md` (one mistakes journal for all agents), `LIBRARY.md` (the catalog of mechanisms) and
`Agents/_example-agent/` (the template). Files you already had are not touched.

1. **Create an agent:** in any chat, type **`/register-as <Name>`** (letters, digits, `-`, `_`). It copies the
   template to `Agents/<Name>/` (briefing, inbox, the agent's own todo, your todo for it) and adds a row to
   `AGENTS.md`. Running it again for the same name changes nothing.
2. **Say what it owns.** After the first real conversation the agent fills `briefing.md`: its role in one line,
   what it owns, what it doesn't touch, where its tasks come from. Check the registry row. Ownership is the part
   that matters: two agents owning one file is how work gets lost.
3. **Open it:** start a new chat whose **first message is just the agent's name** (`Docs`, `docs-agent`, `Docs v2`
   all work). From then on that chat is that agent: on every message it is shown its briefing again when the
   briefing has changed, and the letters in its inbox that are still open. You never paste a briefing by hand.
   Want to call it by another word? Put it on a line in `Agents/<Name>/.aliases`.
4. **Agents talk by letter, not through you:** `scripts/inbox_post.sh <Name> "<text>"` (a lock, and a check
   that the letter landed); the receiver does it or moves it to its todo and closes the item with
   `scripts/inbox_done.sh`. Writing into someone else's `inbox.md` by hand is refused by a gate. A letter that
   arrives while an agent is mid-task is shown to it after the current tool call. You only get what needs you:
   taste, product, priority, anything irreversible — one line in that agent's `human-TODO.md`. How reports are
   filtered for a human: [`po-interface.md`](po-interface.md).
5. **Reminders:** "remind me at 18:30 to …" → the agent runs `scripts/remind.py`, and at that time a letter lands
   in its inbox (a cron line checks every minute). The agent sees it on your next message in that chat, or at
   once if it left an alarm running (`scripts/inbox_wait.sh`, see the work gate below). An agent that promises
   "I'll get back to it" without setting a reminder is flagged.
6. **Optional gates** (off until you name agents at the end of `methodology.conf`, section "several agents"):
   `CCM_WORK_GUARD_AGENTS` (a file, one agent name per line) — these agents can't end a reply while their inbox
   has unprocessed letters, or while their todo has open items and the reply doesn't say `STATE: waiting for …`;
   they also leave an alarm running, so a new letter wakes the chat without you;
   `CCM_STATUS_GUARD_AGENTS` — these agents can't tell you "story X is done / waiting for you" without running
   the status command first.
7. **When a project needs a team** (a lead agent, developers, QA): `scripts/new_project.sh --own-repo <Name>` (a code project
   with its own git repo) or `--no-code <Name>` (a folder in the shared one) creates the project files (roadmap,
   blockers, release settings) and the agents `<Name>-HQ` (the lead) and `<Name>-Dev`; [`project-work.md`](project-work.md) is the standard the team follows,
   [`dev-methodology.md`](dev-methodology.md) is how the team is set up. The release queue (a separate system
   user merges into the main branch only after the tests pass) and the git wrapper (blocks history-destroying
   commands in the shared folder) need root and are installed only on request:
   `./install.sh --with-releaser`, `./install.sh --with-git-guard`.

## 5. Keeping it up to date

`cd ~/claude-code-methodology && git pull && ./install.sh` — then `./check-install.py --user`.
Your memory, lessons, permissions, model, own hooks and `CLAUDE.md` edits are kept; anything replaced is
backed up next to itself as `*.bak-<time>` (skills under `~/.claude/.methodology-installed/backups/`, so
Claude Code doesn't load a copy as a second skill). Chats and history are never touched.
Nothing that deletes files runs unless you enabled it (`--enable-cleanup`).
