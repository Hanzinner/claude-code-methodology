# mobile-bot

Telegram bridge to Claude Code. Optional addon. Off by default.

Drive a Claude Code session from your phone: text, voice, photos, GIFs, social
videos, documents, and location — each turned into something the agent can act
on. `bot.py` is the full working implementation, not a stub.

## What it does

A long-running Python process that:
- Listens for messages on your Telegram bot account
- Authorizes senders by Telegram user-ID allowlist **and** a 6-digit PIN
- For each message, runs `claude -p "<prompt>" --resume <session-id>` in your
  project directory and returns the output
- Keeps one persistent session so context carries across messages

Input handling, all implemented:
- **Text** → prompt, with markdown rendered to Telegram HTML
- **Voice / audio** → transcribed locally with faster-whisper (no API)
- **Photos** → saved and handed to the agent to Read
- **GIF / animation** → 3 keyframes extracted via ffmpeg
- **Social video** (TikTok / Reels / Shorts / X) → yt-dlp pulls the video,
  ffmpeg extracts scene frames, whisper transcribes the audio
- **Documents** (.md/.txt/.pdf/.csv/.json/.yaml/.log/.html, ≤10 MB) → saved for Read
- **Location** → sticky for 2h, drives OSM Overpass nearby search
- **Forwarded messages** → source preamble preserved

The agent can send things back by embedding markers in its reply (see
**Special markers** below): files from the project dir, and interactive
Telegram location pins.

## Files

```
addons/mobile-bot/
├── README.md
├── .env.template                  # the secrets file template (-> <CCM_SECRETS_DIR>/mobile-bot.env)
├── bot.py                         # the bot
├── setup-mobile-bot.sh            # system side: unit, root helpers, sudoers, outbox spool (--dry-run, --uninstall)
├── supervisor-checks.json         # supervisor entries merged on --with-mobile-bot
├── systemd/claude-mobile-bot.service.template
├── hooks/                         # mobile-restrict.sh (fail-closed PreToolUse), mobile_restrict.py (the rules), mobile-audit.sh
├── helpers/                       # root helpers, installed by setup --with-swarm:
│   ├── ccm-bot-inbox.template     #   a letter from the bot into an agent's inbox (+ optional tab waker)
│   └── ccm-bot-blocker.template   #   clear a project blocker by the human's word
├── scripts/
│   ├── osm-nearby.sh, osm_nearby.py   # OSM Overpass nearby search
│   ├── tg_reply.sh                    # an agent answers the human in the bot chat
│   └── mobile_gate_check.sh           # supervisor check: the safety gate really blocks
└── tests/                         # test_restrict, test_core, test_queue, test_rotate, test_topics, test_helpers
```

## Secrets - everything in CCM_SECRETS_DIR

Default `~/.config/claude-secrets/` (the `CCM_SECRETS_DIR` setting). Never inside the workspace (usually a git repo).

| file | content | written by |
|---|---|---|
| `mobile-bot.env` | `TELEGRAM_BOT_TOKEN`, `ALLOWED_TG_USERS` | you / `setup-mobile-bot.sh` (from `.env.template`, 0600) |
| `mobile-bot-auth.json` | the scrypt-hashed PIN, lockout state | the bot, on `/setpin` |

An older install kept the PIN file in `~/.claude/secrets/`: it is still read from there (one warning in the log) and the
next write moves it. The gate treats `CCM_SECRETS_DIR` as a secret zone. The bot never prints a value; the child
`claude` process runs without the token.

## Setup

1. Create a Telegram bot via @BotFather, save the token. Get your user ID from @userinfobot.
2. Put both into `<CCM_SECRETS_DIR>/mobile-bot.env` (see `.env.template`). **An empty `ALLOWED_TG_USERS` = the bot
   refuses to start.**
3. Dependencies:
   ```bash
   pip install python-telegram-bot
   pip install faster-whisper          # optional: voice / video transcription
   sudo apt-get install ffmpeg         # optional: frame extraction
   pip install yt-dlp                  # optional: social video download
   ```
   Without the optionals text/photo/document still work; voice and video report that the tool is unavailable.
4. The bot passes its hooks with `--settings` on every call, so the gate can't be forgotten in settings.json.
5. Run by hand: `python3 bot.py` (the secrets file is read automatically), or install the service:
   ```bash
   sudo ./setup-mobile-bot.sh --dry-run --user <bot user> --workdir <project dir> --allow-paths <project dir>/notes
   sudo ./setup-mobile-bot.sh          --user <bot user> --workdir <project dir> --allow-paths <project dir>/notes
   ```
   (`install.sh --with-mobile-bot` copies this folder and calls the setup script.) `--uninstall` removes the unit, the root
   helpers and the sudoers file; it keeps the secrets, the PIN file, the spool and the state.
6. In Telegram, send any message -> the bot prompts you to set a PIN via `/setpin` (6-digit on-screen keypad).
   A PIN can be switched off with `"require_pin": false` in `<state dir>/settings.json`; anything else = required.

## What the bot does beyond one message = one `claude -p`

- **Inbound queue on disk.** Every message is written to disk first, one worker handles them strictly in order, the file is
  removed only after success. The rate limit holds a message back (it does not drop it); a restart loses nothing; a failed
  attempt is retried 3 times and then the human is told. A retried message carries a note that the earlier attempt may have
  partly run.
- **Replies that cannot be sent** are retried, then kept in the outbox and sent when Telegram is back; long replies are cut on
  line boundaries and each piece is converted to HTML separately (never inside a tag).
- **Session rotation.** A session above `MOBILE_BOT_ROTATE_TOKENS` (default 200000, 0 = off) writes a summary right after
  a reply (warm cache); the next message starts a new session seeded with it. Summaries live in `MOBILE_BOT_HANDOFF_DIR`
  (0700) - the gist of private conversations, keep it out of git. `/reset` starts clean, without a summary.
- **Plain error texts** for login / quota / network / lost-session failures instead of a raw traceback.

## Swarm integration (optional, `--with-swarm`)

For installs that run several named agents (see `swarm-template/`). Off unless the agents dir exists and the root helper
is installed (or `MOBILE_BOT_SWARM=1`).

- `/to <agent> <text>` (or a reply to an agent's message, text or voice or photo or document) -> a letter in that agent's
  inbox. The agent answers with `scripts/tg_reply.sh <agent> <<'EOF' ... EOF`; the bot sends it with a "from <agent>"
  header, and your reply to it goes to the same agent again.
- A Telegram group with topics: one topic per agent; write in a topic = a letter; the answer comes to the same topic.
  Add the bot to a forum group as admin ("Manage topics"); it records the group when you add it.
- `B2 yes` (`Proj B2 yes`) clears a blocker in the register (`scripts/blockers.py`).
- `/wake <agent>` wakes an agent's live tab - only with `setup-mobile-bot.sh --with-wake` (a short Haiku call each time =
  your quota).
- Why root helpers: the inboxes and the blocker register belong to another account, and the bot must not hold a general
  write path into them. The helpers take only an agent NAME / a project and a number, validate them, force the signature,
  refuse secret-looking text and over-long letters. The gate allows exactly one write form:
  `cat <file> | sudo -n ccm-bot-inbox <agent>` with the file inside `CLAUDE_MOBILE_BOT_ALLOW_PATHS`.

## Security posture

The bot spawns Claude with a **constrained tool set**: Read/Grep/Glob/WebFetch/
WebSearch, Edit/Write (restricted by the hook to paths in
`CLAUDE_MOBILE_BOT_ALLOW_PATHS`; empty = no writes), and a **read-only Bash
allowlist** (ls, cat, grep, git log, …). So even a hijacked Telegram account can
mostly *read*, not *run*.

That list is the first layer, not the boundary. A `Bash(x:*)` rule allows every
form of `x`: in an isolated test `sed -i` and `sort -o` ran under their prefix
rules, and the bot's `acceptEdits` mode lets `>` and `; touch` write into the
working dir. The boundary is `hooks/mobile_restrict.py`, itself an allowlist: no
shell metacharacters outside quotes except the pipe, every pipe segment starts
with an allowed tool, no reads of secret zones. Our first version listed forbidden
metacharacters instead; review bypassed it with a newline, then `<(...)`, `||` and
`$VAR`, then glob characters hiding a path. `tests/test_restrict.py` keeps those
cases. One honest limit: secret zones are a list of known names, so run the bot as
its own user with a narrow working dir rather than trusting the list alone. The child process also runs
without the bot's token in its environment and without project-level settings,
which carry "always allow" grants collected in working sessions.

Defense layers:
1. Telegram user-ID allowlist (`ALLOWED_TG_USERS`)
2. 6-digit PIN, scrypt-hashed, required after restart / 30-min inactivity (can be switched off explicitly)
3. Lockout: 3 wrong PINs → 15-min lockout, logged to the audit file
4. `mobile-restrict.sh` (fail-closed) blocks writes outside the allowlist and to secret-shaped files, reads of secret zones, and anything in Bash but allowlisted read-only tools
5. `mobile-audit.sh` logs every Write/Edit + auto-commits the file (new files too) for one-tap `/revert`
6. Multi-tier rate limit (3/30s, 8/min, 20/15min, 60/hr), liftable with `/unlimit`
7. `[SEND: ...]` file sends are confined to the project dir and refuse secrets/.git

Not bank-grade. Good enough that casual snooping won't compromise the host.
Don't expose the token publicly.

## Commands

`/model` `/effort` `/settings` `/usage` (subscription quota) · `/session`
`/reset` · `/setpin` `/lock` · `/loc` `/clearloc` · `/unlimit` `/relimit` ·
`/revert` (undo the last file change) · `/whoami` · with the swarm: `/to` `/wake`.

## Special markers

The agent embeds these in its reply; the bot extracts and acts on them, then
strips them before display:
- `[SEND: /path/to/file]` — bot reads from disk, sends as a Telegram document/photo
- `[LOC: lat,lng,name]` — bot sends an interactive location pin
