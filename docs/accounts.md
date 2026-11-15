# Accounts — what to sign up for, and where each key goes

For the person installing, and for the agent doing it for them: the agent reads this, tells the person
**only the rows they still need**, and names the file each key goes into. **Keys never go into the chat** —
the person puts them into the file themselves; the agent only says which file.

Prices and free tiers below were checked on 2026-11-15 on each provider's own pricing page; they change.

| Account | Needed? | What you get from it |
|---|---|---|
| Claude Code (Anthropic) | **required** | the agent itself |
| Tavily | optional — web search | 1000 searches a month free, no card |
| Exa | optional — second search provider | $10 of credits a month free + a one-time $10 bonus, no card |
| S3-compatible storage (Backblaze B2, Cloudflare R2, …) | optional — offsite backup addon | B2: first 10 GB free |
| Telegram bot | optional — mobile bot addon | free |

Without any optional account everything else works: search falls back to Claude Code's built-in `WebSearch`,
nothing is backed up off the machine, there is no phone access.

## Claude Code

Sign up at https://claude.com/claude-code and install the CLI. Nothing to copy: log in once with `claude`.
Check: `claude --version`. The quota monitor (`scripts/quota_status.py`) reads this login, read only.

## Tavily and Exa — web search

1. Sign up: https://tavily.com and/or https://exa.ai. One is enough; both give rotation (when Tavily's month
   runs out, the same query goes to Exa).
2. Copy the **API key** from the provider's dashboard.
3. **Easiest: paste the key when `./install.sh` asks for it** (input is hidden). The installer writes it to
   `search.env` and, if the `claude` CLI is there, registers the server — steps 3 and 4 done. To add a key
   later by hand, put it into `search.env` in your secrets folder (`CCM_SECRETS_DIR` in
   `~/.claude/methodology.conf`, default `~/.config/claude-secrets/`), mode 600:
   ```
   TAVILY_API_KEY=tvly-...
   EXA_API_KEY=...
   ```
4. Register the server once: `claude mcp add --scope user search -- python3 ~/.claude/mcp/search_mcp.py`
5. Check: `claude mcp list` shows `search: ✓ Connected`; restart Claude Code.

Until the server is registered, the built-in `WebSearch` keeps working (details in [`mcp/README.md`](../mcp/README.md)).

## S3-compatible storage — offsite backup

1. Sign up with any S3-compatible provider. Backblaze B2: https://www.backblaze.com/cloud-storage
2. Create a **private bucket** and an **application key** limited to that bucket. Copy: bucket name, key ID
   (access key), application key (secret key), the S3 endpoint URL shown on the bucket page.
3. Put them into `~/.claude/secrets/s3-credentials.json` (mode 600):
   `{"accessKey": "...", "secretKey": "...", "bucket": "...", "endpoint": "https://..."}`
4. Make a random passphrase, keep it in a password manager, and put it into
   `~/.claude/secrets/backup-passphrase.txt` (mode 600). Losing it means losing the archive.
5. Set up and check: [`addons/offsite-backup/README.md`](../addons/offsite-backup/README.md)
   (`restic init`, first backup, `restic snapshots` lists it).

## Telegram — mobile bot

1. In Telegram, talk to **@BotFather** → `/newbot` → copy the **bot token**.
2. Talk to **@userinfobot** → copy **your numeric user ID**.
3. Put both into `~/.claude/mobile-bot/.env` (copy of `.env.template`, mode 600):
   `TELEGRAM_BOT_TOKEN=...` and `ALLOWED_TG_USERS=<your id>`. An empty list lets anyone who finds the bot
   reach the PIN prompt.
4. Start it and check: [`addons/mobile-bot/README.md`](../addons/mobile-bot/README.md). The first message to
   the bot asks you to set a PIN with `/setpin`; after that it answers.

## For the agent doing the install

`./install.sh` and `./check-install.py` end with the accounts that are still missing, one line each, with a
link into this file. Pass that to the person in one short list:
- which optional accounts above they might want, one line each with the link and what it's for;
- for each one they say yes to: the exact file and the line to put in it, and that they do it themselves;
- then run the row's check yourself and report the result.

Never ask for a key in the chat, never echo a secrets file, never write a key into the workspace.
