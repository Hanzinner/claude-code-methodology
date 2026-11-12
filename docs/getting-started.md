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

Several named agents, each in its own chat with its own folder, talking through inboxes. This is layer 2;
**the installer does not set it up yet** — what follows is how to do it by hand today.

1. **Make the shared folder** (your `CCM_WORKSPACE`) and copy `swarm-template/` into it: the mistakes
   journal, the agent registry (`AGENTS.md`), the catalog of mechanisms (`LIBRARY.md`) and one example
   agent folder.
2. **Create an agent:** copy `Agents/_example-agent/` to `Agents/<Name>/` and fill `briefing.md`: what it
   owns, what it doesn't touch, where its tasks come from. Add a row to `AGENTS.md`. Ownership is the part
   that matters: two agents owning one file is how work gets lost.
3. **Start it:** open a new chat and make the first message *"You are <Name>. Read Agents/<Name>/briefing.md
   and work as that agent."* (Layer 2 adds a watchman that does this from the name alone and re-shows the
   briefing when it changes.)
4. **Agents talk by letter, not by you:** one agent writes to another with
   `multi-agent/inbox-post.sh <Name> "<text>"` (a lock and a check that the letter landed); the receiver
   reads its `inbox.md`, does it or moves it to its `agent-TODO.md`, and closes the item. You only get what
   needs you: taste, product, priority, anything irreversible — one line in that agent's `human-TODO.md`.
   How reports are filtered for a human: [`po-interface.md`](po-interface.md).
5. **When a project needs a team** (a lead agent, developers, QA): [`project-work.md`](project-work.md) is
   the standard they follow, [`dev-methodology.md`](dev-methodology.md) is how the team is set up.

## 5. Keeping it up to date

`cd ~/claude-code-methodology && git pull && ./install.sh` — then `./check-install.py --user`.
Your memory, lessons, permissions, model, own hooks and `CLAUDE.md` edits are kept; anything replaced is
backed up next to itself as `*.bak-<time>` (skills under `~/.claude/.methodology-installed/backups/`, so
Claude Code doesn't load a copy as a second skill). Chats and history are never touched.
Nothing that deletes files runs unless you enabled it (`--enable-cleanup`).
