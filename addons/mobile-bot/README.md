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
├── .env.template                  # copy to .env, fill
├── bot.py                         # full working bot
├── systemd/
│   └── claude-mobile-bot.service.template
├── hooks/
│   ├── mobile-restrict.sh         # PreToolUse, allowlist writes
│   └── mobile-audit.sh            # PostToolUse, log + git commit
└── scripts/
    ├── osm-nearby.sh              # OSM Overpass nearby search
    └── osm_nearby.py              # (called by osm-nearby.sh)
```

## Setup

1. Create a Telegram bot via @BotFather, save the token.
2. Get your user ID from @userinfobot.
3. Copy `.env.template` → `.env`, fill `TELEGRAM_BOT_TOKEN` and
   `ALLOWED_TG_USERS`. The rest have sensible defaults (see the comments).
4. Install dependencies:
   ```bash
   pip install python-telegram-bot
   # optional, for the richer inputs:
   pip install faster-whisper          # voice / video transcription
   sudo apt-get install ffmpeg         # frame extraction
   pip install yt-dlp                  # social video download
   ```
   The bot degrades gracefully — without the optionals, text/photo/document
   still work; voice and video just report that the tool is unavailable.
5. Wire the hooks in `settings.json` (they are no-ops unless `CLAUDE_MOBILE_BOT=1`,
   which `bot.py` sets when it spawns Claude):
   ```json
   {
     "hooks": {
       "PreToolUse": [
         { "matcher": "Write|Edit",
           "hooks": [{ "type": "command",
             "command": "__CLAUDE_DIR__/mobile-bot/hooks/mobile-restrict.sh" }] }
       ],
       "PostToolUse": [
         { "matcher": "Write|Edit",
           "hooks": [{ "type": "command",
             "command": "__CLAUDE_DIR__/mobile-bot/hooks/mobile-audit.sh" }] }
       ]
     }
   }
   ```
6. Run:
   ```bash
   set -a; source .env; set +a
   python bot.py
   ```
   Or install the systemd unit template for auto-start.
7. In Telegram, send any message → the bot prompts you to set a PIN via
   `/setpin` (6-digit on-screen keypad). After that you're live.

## Security posture

The bot spawns Claude with a **constrained tool set**: Read/Grep/Glob/WebFetch/
WebSearch, Edit/Write (restricted to `.md` under the project via the hook), and
a **read-only Bash allowlist** (ls, cat, grep, git log, jq, …). Destructive
Bash (rm/dd/chmod/chown/mv) is never allowed. So even a hijacked Telegram
account can mostly *read*, not *run*.

Defense layers:
1. Telegram user-ID allowlist (`ALLOWED_TG_USERS`)
2. 6-digit PIN, scrypt-hashed, required after restart / 30-min inactivity
3. Lockout: 3 wrong PINs → 15-min lockout, logged to the audit file
4. `mobile-restrict.sh` blocks writes outside the allowlist and to secret-shaped files
5. `mobile-audit.sh` logs every write + auto-commits for one-tap `/revert`
6. Multi-tier rate limit (3/30s, 8/min, 20/15min, 60/hr), liftable with `/unlimit`
7. `[SEND: ...]` file sends are confined to the project dir and refuse secrets/.git

Not bank-grade. Good enough that casual snooping won't compromise the host.
Don't expose the token publicly.

## Commands

`/model` `/effort` `/settings` `/usage` (subscription quota) · `/session`
`/reset` · `/setpin` `/lock` · `/loc` `/clearloc` · `/unlimit` `/relimit` ·
`/revert` (undo the last file change) · `/whoami`.

## Special markers

The agent embeds these in its reply; the bot extracts and acts on them, then
strips them before display:
- `[SEND: /path/to/file]` — bot reads from disk, sends as a Telegram document/photo
- `[LOC: lat,lng,name]` — bot sends an interactive location pin
