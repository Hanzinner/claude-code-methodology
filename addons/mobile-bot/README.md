# mobile-bot

Telegram bridge to Claude Code. Optional addon. Off by default.

## What it does

A long-running Python process that:
- Listens for messages on your Telegram bot account
- Authenticates senders via Telegram user-ID allowlist + PIN
- For each message, spawns `claude -p "<prompt>" --resume <session-id>` and returns the output
- Supports text out of the box; extend for voice (`faster-whisper`), photos / GIFs / documents, videos (`yt-dlp` + scene frames), location (sticky 2h, drives `osm-nearby.sh`)

## Files

```
addons/mobile-bot/
├── README.md
├── .env.template                  # copy to .env, fill
├── bot.py.stub                    # minimal reference (text-only)
├── systemd/
│   └── claude-mobile-bot.service.template
├── hooks/
│   ├── mobile-restrict.sh         # PreToolUse, allowlist writes
│   └── mobile-audit.sh            # PostToolUse, log + git commit
└── scripts/
    ├── osm-nearby.sh              # OSM Overpass nearby search
    └── osm_nearby.py              # (called by osm-nearby.sh)
```

The `scripts/osm-nearby.sh` is called from the bot when the user shares a location (sticky for 2h). It queries OSM Overpass for nearby amenities (restaurants, pharmacies, etc). Free, no signup.

`bot.py.stub` is text-only. Voice/video/location features are documented above but not implemented in the stub.

## Setup

1. Create a Telegram bot via @BotFather, save the token.
2. Get your user ID from @userinfobot.
3. Copy `.env.template` → `.env`, fill:
   - `TELEGRAM_BOT_TOKEN`
   - `ALLOWED_USER_IDS` (comma-separated)
   - `MOBILE_BOT_PIN` (4-8 digits)
   - `CLAUDE_SESSION_ID` (start a session, copy its SID here)
   - `CLAUDE_CWD` (directory the session runs in)
   - `CLAUDE_MOBILE_BOT_ALLOW_PATHS` (colon-separated dirs the bot can write to)
4. `pip install python-telegram-bot python-dotenv`
   System deps for voice/video: `ffmpeg`, `yt-dlp`.
5. Wire hooks in `settings.json`:
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
   Hooks are no-ops unless `CLAUDE_MOBILE_BOT=1`, which `bot.py` sets when spawning Claude.
6. Run: `python bot.py.stub` (or `bot.py` after extending), or use the systemd template.

## Defense layers

1. Telegram user-ID allowlist
2. PIN required after restart / inactivity
3. `mobile-restrict.sh` blocks writes outside allowlist
4. `mobile-audit.sh` logs every write + auto-commits for revert
5. Rate limit (configurable, in your `bot.py`)

Not bank-grade. Good enough that casual snooping won't compromise the host. Don't expose publicly.

## Special markers

Agent replies the bot understands:
- `[SEND: /path/to/file]` — bot reads from disk, sends as Telegram document
- `[LOC: lat,lng,name]` — bot sends interactive location pin
