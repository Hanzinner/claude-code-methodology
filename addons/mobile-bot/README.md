# mobile-bot addon

Telegram bridge to Claude Code. Drive your agent from your phone — type a question, get a reply; send voice, get transcribed-and-answered; send a screenshot, get analyzed; send a location, get nearby places.

**This is an optional add-on.** Most users won't want their agent reachable from the internet. If you do, this is the pattern.

## What it does

The bot is a long-running Python process that:
- Listens for messages from your Telegram bot account
- Authenticates the sender via PIN (single user / allowlist)
- For each message, spawns a `claude -p "<prompt>" --resume <session-id>` subprocess
- Returns the response to Telegram as text
- Handles voice (via `faster-whisper`), photos / GIFs / documents (via Claude vision), videos (yt-dlp + scene frames + transcript), location (sticky for 2 hours, drives OSM-nearby queries via the `osm-nearby.sh` script)

## Security model

Five defense layers:

1. **Telegram allowlist** — only configured user IDs can message the bot at all
2. **PIN gate** — first message after restart / inactivity requires a PIN entered via inline keypad
3. **Write restriction hook** — when the bot is the one driving Claude, the `mobile-restrict.sh` hook blocks writes outside an explicit allowlist of paths
4. **Rate limit** — configurable per-tier message/minute caps; commands `/unlimit` / `/relimit` to escalate during heavy sessions
5. **Audit log** — every write while in mobile mode is appended to a JSONL log + auto-committed to git so `/revert` can roll back

This is **not bank-grade security**. It is "good enough that a stolen phone or a casual snoop won't compromise the host". For anything stronger, don't expose the agent over a public messenger.

## Files in this addon

```
addons/mobile-bot/
├── README.md                          # this file
├── .env.template                      # secrets — copy to .env and fill
├── bot.py.stub                        # minimal reference impl (PIN + text)
├── systemd/
│   └── claude-mobile-bot.service.template
└── hooks/
    ├── mobile-restrict.sh             # PreToolUse — only allow writes inside CLAUDE_MOBILE_BOT_ALLOW_PATHS
    └── mobile-audit.sh                # PostToolUse — log + git commit every edit
```

The `bot.py.stub` is a minimal working example showing the auth + bridge pattern. For a full-featured implementation (voice, video, location, file send), use the reference at TODO — this stub is meant as a starting point you'd extend for your own needs.

## Setup

1. **Create a Telegram bot** via [@BotFather](https://t.me/BotFather). Save the token.
2. **Get your Telegram user ID** via [@userinfobot](https://t.me/userinfobot).
3. **Copy `.env.template` → `.env`** and fill:
   - `TELEGRAM_BOT_TOKEN`
   - `ALLOWED_USER_IDS` (comma-separated, your ID for single-user)
   - `MOBILE_BOT_PIN` (4-8 digits)
   - `CLAUDE_SESSION_ID` (start a Claude Code session, `/register-as mobile` so we can find it later, then put the SID here)
4. **Install Python deps:**
   ```bash
   pip install python-telegram-bot faster-whisper python-dotenv
   ```
   System deps if you want voice/video: `ffmpeg`, `yt-dlp`.
5. **Wire the hooks** by adding to your `settings.json`:
   ```json
   {
     "hooks": {
       "PreToolUse": [
         { "matcher": "Write|Edit",
           "hooks": [{ "type": "command", "command": "__CLAUDE_DIR__/mobile-bot/hooks/mobile-restrict.sh" }] }
       ],
       "PostToolUse": [
         { "matcher": "Write|Edit",
           "hooks": [{ "type": "command", "command": "__CLAUDE_DIR__/mobile-bot/hooks/mobile-audit.sh" }] }
       ]
     }
   }
   ```
   (These hooks only enforce when `CLAUDE_MOBILE_BOT=1` is set — the bot sets this env var when it spawns Claude, so they're no-ops in your regular terminal use.)
6. **Run it:**
   ```bash
   python bot.py
   ```
   Or set up the systemd service from `systemd/claude-mobile-bot.service.template` for auto-start at boot.

## Usage

Send `/start` to your bot from your phone. Enter the PIN via the inline keypad. After auth, send any text — the bot relays it to your Claude session and returns the response.

Special markers in agent replies the bot understands:
- `[SEND: /path/to/file]` — bot reads the file from your machine and sends it to you as a Telegram document
- `[LOC: lat,lng,name]` — bot sends an interactive Telegram location pin

Commands:
- `/start` — re-init / re-auth
- `/clear` — clear sticky location
- `/unlimit` — bypass rate limit for the current session (use sparingly)
- `/relimit` — restore default rate limit

## Anti-patterns

- **Don't expose the bot publicly.** Allowlist-only. If a stranger can DM your bot, they can DM your agent.
- **Don't store the PIN in plain text on a shared machine.** Use a secrets manager or env var.
- **Don't grant the bot more filesystem reach than it needs.** `CLAUDE_MOBILE_BOT_ALLOW_PATHS` should be the minimum set of directories the agent might write to from the phone.
- **Don't run on the bot's session a critical production-write task.** The PIN protects from casual access; the audit log catches mistakes. Neither prevents catastrophe.

## Tradeoffs

This is convenient. It is also an attack surface. You're choosing:
- ✓ Drive the agent from anywhere
- ✓ Voice / camera / location inputs your terminal can't give
- ✗ Another long-running internet-facing service to maintain
- ✗ Telegram is a third party — they see message metadata at minimum
- ✗ Bot token leak = stranger talks to your agent

For most projects, this is overkill. For long-running agent setups where you'd benefit from off-keyboard access, it's worth the setup.
