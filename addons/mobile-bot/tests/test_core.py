#!/usr/bin/env python3
"""Core behaviour of bot.py: PIN switch, message cutting, error texts, secrets locations, fail-closed start,
the Telegram API mocked on a loopback server (no network). Last line: `mobile-bot core: N pass, M fail`."""
import asyncio, json, os, pathlib, subprocess, sys, threading, http.server
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sandbox as sb
D = sb.D
(D / "secrets").mkdir(exist_ok=True)
(D / "secrets" / "mobile-bot-auth.json").write_text("{}")
import bot
res = []
def ok(n, c): res.append(bool(c)); print("PASS" if c else "FAIL", n)

# PIN: required unless EXPLICITLY switched off
bot.SETTINGS_FILE.write_text(json.dumps({"model": "sonnet"}))
ok("PIN required by default", bot.pin_required() and not bot.is_unlocked())
bot.SETTINGS_FILE.write_text("{garbled")
ok("garbled settings -> PIN still required (fail-closed)", bot.pin_required())
bot.SETTINGS_FILE.write_text(json.dumps({"require_pin": "false"}))
ok("only the JSON false switches it off (a string does not)", bot.pin_required())
bot.SETTINGS_FILE.write_text(json.dumps({"require_pin": False}))
ok("require_pin=false -> unlocked", not bot.pin_required() and bot.is_unlocked())
bot.SETTINGS_FILE.unlink()

# md_chunks: never cuts inside a tag, counts UTF-16, drops empty text
ok("md_chunks: empty text -> no pieces", bot.md_chunks("  \n ") == [])
big = "\n".join(f"line {i} " + "x" * 80 for i in range(200))
ch = bot.md_chunks(big)
ok("md_chunks: pieces <= 3500 and nothing lost", all(len(c) <= 3500 for c in ch) and "\n".join(ch) == big)
emo = "😀" * 3000
ok("md_chunks: an emoji line is cut by UTF-16 (<= 3500 units)", all(len(c.encode('utf-16-le')) // 2 <= 3500 for c in bot.md_chunks(emo)) and "".join(bot.md_chunks(emo)) == emo)
ok("md_chunks: every piece converts to valid-looking HTML (no cut tag)", all(bot.md_to_tg_html(c).count("<b>") == bot.md_to_tg_html(c).count("</b>") for c in bot.md_chunks("**bold** text\n" * 600)))

# error texts
h = bot.humanize_claude_error(1, "Error: 401 Unauthorized")
ok("humanize: login error", "Authorization" in h and "rc=1" in h)
ok("humanize: SIGTERM without stderr = a restart, not a crash", "restarted" in bot.humanize_claude_error(143, ""))
ok("humanize: quota", "Limit" in bot.humanize_claude_error(1, "429 rate limit"))
ok("humanize: lost session", "/reset" in bot.humanize_claude_error(1, "No conversation found"))
ok("humanize: unknown keeps the raw tail", "weird thing" in bot.humanize_claude_error(1, "weird thing"))

# the child never sees the bot's secrets
os.environ["TELEGRAM_BOT_TOKEN"] = "1:SECRET"; os.environ["SOME_API_KEY"] = "k"
env = bot.child_env(X="1")
ok("child_env drops the token and *_API_KEY", "TELEGRAM_BOT_TOKEN" not in env and "SOME_API_KEY" not in env and env["X"] == "1")
ok("the httpx logger is quiet (its URLs carry the token)", bot.logging.getLogger("httpx").level >= 30)

# PIN file lives in CCM_SECRETS_DIR; the old path is a fallback with one warning
ok("PIN file default = CCM_SECRETS_DIR/mobile-bot-auth.json", bot._auth_file() == D / "secrets" / "mobile-bot-auth.json")
(D / "secrets" / "mobile-bot-auth.json").unlink()
old = D / "home" / ".claude" / "secrets"; old.mkdir(parents=True); (old / "mobile-bot-auth.json").write_text("{}")
os.environ["HOME"] = str(D / "home")
import io; buf = io.StringIO(); hnd = bot.logging.StreamHandler(buf); bot.log.addHandler(hnd)
bot.logging.disable(bot.logging.NOTSET); bot.log.propagate = False; bot.log.setLevel(30)
fb = bot._auth_file(); bot.log.removeHandler(hnd); bot.logging.disable(bot.logging.CRITICAL)
ok("old PIN path still read, with a one-line warning", fb == old / "mobile-bot-auth.json" and "move it to" in buf.getvalue() and buf.getvalue().count("\n") == 1)
bot.AUTH_FILE = fb; bot.set_pin("123456")
ok("the next write goes to the new path", (D / "secrets" / "mobile-bot-auth.json").exists() and bot.AUTH_FILE == D / "secrets" / "mobile-bot-auth.json")
ok("PIN file is 0600 and holds no plain PIN", oct(bot.AUTH_FILE.stat().st_mode)[-3:] == "600" and "123456" not in bot.AUTH_FILE.read_text() and bot.verify_pin("123456"))

# the token/allowlist come from CCM_SECRETS_DIR/mobile-bot.env when the environment lacks them (parsed, not sourced)
(D / "secrets" / "mobile-bot.env").write_text("TELEGRAM_BOT_TOKEN=9:fromfile\nALLOWED_TG_USERS=7,8\nBAD=$(touch %s/pwned)\n" % D)
sub = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import bot; print(bot.TOKEN, sorted(bot.ALLOWED))" % str(sb.BOT_DIR)],
                     env={k: v for k, v in os.environ.items() if k not in ("TELEGRAM_BOT_TOKEN", "ALLOWED_TG_USERS")}, capture_output=True, text=True)
ok("secrets file: token + allowlist read, a $(...) value is not executed", sub.stdout.strip() == "9:fromfile [7, 8]" and not (D / "pwned").exists())

sub = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import bot; print(bool(bot.BLOCKER_RE.fullmatch('B2 \u0442\u0430\u043a')))" % str(sb.BOT_DIR)],
                     env={**os.environ, "CCM_LANG_EXTRA": "uk"}, capture_output=True, text=True)
ok("CCM_LANG_EXTRA=uk adds the Ukrainian confirmation word", sub.stdout.strip() == "True")

# an empty allowlist = the bot refuses to start
sub = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import bot; bot.main()" % str(sb.BOT_DIR)],
                     env={**os.environ, "ALLOWED_TG_USERS": ""}, capture_output=True, text=True)
ok("empty ALLOWED_TG_USERS: refuses to start (exit 1)", sub.returncode == 1)

# Telegram API on a loopback: a real PTB Bot talks to a local fake server
calls = []
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); body = self.rfile.read(n).decode()
        calls.append((self.path.rsplit("/", 1)[-1], body))
        out = {"ok": True, "result": {"message_id": 11, "date": 1, "chat": {"id": 42, "type": "private"}, "text": "x"}}
        b = json.dumps(out).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
async def api():
    from telegram import Bot
    from telegram.request import HTTPXRequest
    b = Bot("1:AAtest", base_url=f"http://127.0.0.1:{srv.server_port}/bot", request=HTTPXRequest())
    await b.initialize() if False else None
    bot.TG_OUTBOX.mkdir(parents=True, exist_ok=True)
    (bot.TG_OUTBOX / "9_9.json").write_text(json.dumps({"agent": "Alpha", "text": "**hi** there"}))
    await bot._outbox_flush(b)
    return b
asyncio.run(api()); srv.shutdown()
sends = [c for c in calls if c[0] == "sendMessage"]
ok("outbox through a mocked Telegram API: one sendMessage, HTML, to the allowed user", len(sends) == 1 and "42" in sends[0][1] and "HTML" in sends[0][1])
ok("...and the file moved to sent/", (bot.TG_OUTBOX / "sent" / "9_9.json").exists())
n_ = sum(res); print(f"mobile-bot core: {n_} pass, {len(res) - n_} fail"); sys.exit(0 if all(res) else 1)
