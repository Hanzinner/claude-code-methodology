#!/usr/bin/env python3
"""mobile-bot — Telegram bridge to Claude Code on a VM.

Architecture:
- The bot keeps one persistent session (sid stored in session.txt)
- Each message from a whitelisted user -> claude -p --resume <sid>
- The reply is sent back to Telegram
- Memory + skills + tools are available (Claude runs in the project dir)
"""
import os, sys, json, re, shlex, html, time, hmac, hashlib, shutil, secrets as pysecrets, asyncio, logging, pathlib
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (Application, ApplicationHandlerStop, CallbackContext, TypeHandler,
                          MessageHandler, CommandHandler, CallbackQueryHandler, filters)
from telegram.error import BadRequest, TelegramError, NetworkError, RetryAfter

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("mobile-bot")
# httpx logs every request with its URL, and the URL carries the bot token (.../bot<TOKEN>/getUpdates every
# 10 s): only failures go to the log.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Optional: the methodology's settings loader (<install dir>/lib/ccm_conf.py, one level above this add-on).
# Without it the bot runs on environment variables alone.
for _rel in ("..", os.path.join("..", "..")):   # installed: <install dir>/mobile-bot/bot.py; in the repo: addons/mobile-bot/bot.py
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), _rel, "lib"))
try:
    from ccm_conf import conf as _ccm_conf
except Exception:
    _ccm_conf = None


def _conf(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if v in (None, "") and _ccm_conf:
        try:
            v = _ccm_conf(key)
        except Exception:
            v = None
    return v if v not in (None, "") else default


def _load_secrets_file() -> None:
    """TELEGRAM_BOT_TOKEN / ALLOWED_TG_USERS come from the environment (systemd EnvironmentFile) or, when
    the bot is started by hand, from <CCM_SECRETS_DIR>/mobile-bot.env. The file is parsed, never sourced,
    and the environment wins."""
    d = _conf("CCM_SECRETS_DIR", os.path.join(os.path.expanduser("~"), ".config", "claude-secrets"))
    try:
        lines = open(os.path.join(d, "mobile-bot.env"), encoding="utf-8").read().splitlines()
    except OSError:
        return
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        try:
            v = " ".join(shlex.split(v, comments=True))
        except ValueError:
            v = v.strip()
        os.environ.setdefault(k, v)


_load_secrets_file()
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED = {int(x) for x in os.environ.get("ALLOWED_TG_USERS","").split(",") if x.strip()}
# Directory Claude runs in — the project root you want reachable from your phone.
CLAUDE_CWD = os.environ.get("CLAUDE_BOT_CWD") or os.getcwd()
# Bot's own state (session id + settings). Override with MOBILE_BOT_STATE_DIR.
_STATE_DIR = pathlib.Path(os.environ.get("MOBILE_BOT_STATE_DIR") or os.path.join(CLAUDE_CWD, ".claude", "mobile-bot"))
_STATE_DIR.mkdir(parents=True, exist_ok=True)
SESSION_FILE = _STATE_DIR / "session.txt"
SETTINGS_FILE = _STATE_DIR / "settings.json"

# ── Swarm integration (optional: letters to agents, replies from agents, blockers, topics) ──
# On when MOBILE_BOT_SWARM=1, or - by default - when the agents dir exists and the root helper is installed
# (addons/mobile-bot/setup-mobile-bot.sh --with-swarm). Off = a plain phone-to-Claude bridge.
AGENTS_DIR = pathlib.Path(os.environ.get("MOBILE_BOT_AGENTS_DIR") or _conf("CCM_AGENTS_DIR") or "/nonexistent-agents-dir")
# The helpers run as root through sudo: the agents' inboxes and the blocker register belong to another user,
# and the bot must not hold a general write path into them. Empty MOBILE_BOT_SUDO = call them directly.
SUDO = shlex.split(os.environ.get("MOBILE_BOT_SUDO", "sudo -n"))
INBOX_WRAPPER = os.environ.get("MOBILE_BOT_INBOX_WRAPPER") or "/usr/local/sbin/ccm-bot-inbox"
BLOCKER_WRAPPER = os.environ.get("MOBILE_BOT_BLOCKER_WRAPPER") or "/usr/local/sbin/ccm-bot-blocker"
INBOX_CMD = SUDO + [INBOX_WRAPPER]
BLOCKER_CMD = SUDO + [BLOCKER_WRAPPER]
_sw = os.environ.get("MOBILE_BOT_SWARM", "")
SWARM_ON = (_sw == "1") if _sw in ("0", "1") else (AGENTS_DIR.is_dir() and os.path.exists(INBOX_WRAPPER))
# The project a bare "B2 yes" refers to (empty = the project word is required).
BLOCKER_PROJECT = os.environ.get("MOBILE_BOT_BLOCKER_PROJECT", "")
# Agents answer through tg_reply.sh: a JSON file dropped here, picked up by the bot every ~5 s.
TG_OUTBOX = pathlib.Path(os.environ.get("CCM_TG_OUTBOX") or _conf("CCM_TG_OUTBOX") or "/var/spool/ccm-tg-outbox")
AGENT_MSG_MAP = TG_OUTBOX / "map.json"
# Photos/documents from a reply to an agent: outside git, the agent reads them by path.
TG_MEDIA = pathlib.Path(os.environ.get("MOBILE_BOT_MEDIA_DIR") or _STATE_DIR / "media")
# Inbound queue and the agents' group live next to the bot's own state (owner-only).
TG_INQ = pathlib.Path(os.environ.get("MOBILE_BOT_INQ_DIR") or _STATE_DIR / "inq")
GROUP_FILE = pathlib.Path(os.environ.get("MOBILE_BOT_GROUP_DIR") or _STATE_DIR / "group") / "group.json"
TOPICS_FILE = GROUP_FILE.with_name("topics.json")     # {agent: message_thread_id}
# Path to the OSM nearby-search helper (ships with this addon).
OSM_SCRIPT = os.environ.get("OSM_NEARBY_SCRIPT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "osm-nearby.sh")
MAX_TG_MSG = 4000  # Telegram limit is 4096; leave headroom

MODELS = ["opus", "sonnet", "haiku"]
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
# Per-model effort capability (matches VS Code Anthropic extension behavior).
# Haiku is a smaller model — doesn't use large thinking budgets effectively.
MODEL_EFFORTS = {
    "opus": EFFORTS,
    "sonnet": EFFORTS,
    "haiku": ["low", "medium"],
}
DEFAULT_SETTINGS = {"model": "sonnet", "effort": "medium"}


# ──────────────────────────────────────────────────────────────────────────
# AUTH (PIN-based, 30 min session)
# ──────────────────────────────────────────────────────────────────────────

def _secrets_dir() -> str:
    return _conf("CCM_SECRETS_DIR", os.path.join(os.path.expanduser("~"), ".config", "claude-secrets"))


def _auth_file() -> pathlib.Path:
    """The scrypt-hashed PIN lives in CCM_SECRETS_DIR/mobile-bot-auth.json. An older install kept it in
    ~/.claude/secrets/: it is still read from there (one warning), and the next /setpin writes the new path."""
    if os.environ.get("MOBILE_BOT_AUTH_FILE"):
        return pathlib.Path(os.environ["MOBILE_BOT_AUTH_FILE"])
    new = pathlib.Path(_secrets_dir()) / "mobile-bot-auth.json"
    old = pathlib.Path(os.path.expanduser("~/.claude/secrets/mobile-bot-auth.json"))
    if not new.exists() and old.exists():
        log.warning("PIN file read from the old path %s - move it to %s", old, new)
        return old
    return new


AUTH_FILE = _auth_file()
PIN_LENGTH = 6
SESSION_TIMEOUT = 30 * 60      # 30 minutes
MAX_FAILURES = 3
LOCKOUT_DURATION = 15 * 60     # 15 minutes after MAX_FAILURES

# In-memory state (per user_id):
_pin_buffers: dict[int, str] = {}      # during entry
_setup_buffers: dict[int, dict] = {}   # during setup (stage: 'first'/'confirm', first_pin: '...')
_pending_after_auth: dict[int, dict] = {}   # uid -> {update, context, ts} — message that arrived while locked


def _hash_pin(pin: str, salt: bytes) -> str:
    return hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()


def load_auth() -> dict:
    if AUTH_FILE.exists():
        try:
            return json.loads(AUTH_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            log.warning("auth file corrupted")
    return {}


def save_auth(d: dict) -> None:
    global AUTH_FILE
    if not os.environ.get("MOBILE_BOT_AUTH_FILE") and AUTH_FILE != pathlib.Path(_secrets_dir()) / "mobile-bot-auth.json":
        AUTH_FILE = pathlib.Path(_secrets_dir()) / "mobile-bot-auth.json"   # migrate from the old path on the first write
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(d))
    try:
        os.chmod(AUTH_FILE, 0o600)
    except OSError:
        pass


def pin_is_set() -> bool:
    auth = load_auth()
    return bool(auth.get("pin_hash"))


def verify_pin(pin: str) -> bool:
    auth = load_auth()
    if not auth.get("pin_hash"):
        return False
    salt = bytes.fromhex(auth["salt"])
    expected = auth["pin_hash"]
    actual = _hash_pin(pin, salt)
    return hmac.compare_digest(expected, actual)


def set_pin(pin: str) -> None:
    salt = pysecrets.token_bytes(16)
    auth = load_auth()
    auth["pin_hash"] = _hash_pin(pin, salt)
    auth["salt"] = salt.hex()
    auth["last_unlock"] = time.time()
    auth["fail_count"] = 0
    auth.pop("lockout_until", None)
    save_auth(auth)


def pin_required() -> bool:
    """The PIN is off only by an explicit `"require_pin": false` in settings.json. A missing or garbled
    field means the PIN is required (fail-closed)."""
    return load_settings().get("require_pin", True) is not False


def is_unlocked() -> bool:
    if not pin_required():
        return True
    auth = load_auth()
    # Lockout forces is_unlocked -> False even if last_unlock is fresh
    if auth.get("lockout_until", 0) > time.time():
        return False
    last = auth.get("last_unlock", 0)
    return (time.time() - last) <= SESSION_TIMEOUT


def is_locked_out() -> tuple[bool, int]:
    auth = load_auth()
    until = auth.get("lockout_until", 0)
    remaining = int(until - time.time())
    return (remaining > 0, max(0, remaining))


def touch_activity() -> None:
    auth = load_auth()
    auth["last_unlock"] = time.time()
    save_auth(auth)


def record_failure() -> tuple[int, bool]:
    """Return (fail_count, is_now_locked_out)."""
    auth = load_auth()
    fc = auth.get("fail_count", 0) + 1
    auth["fail_count"] = fc
    locked = False
    if fc >= MAX_FAILURES:
        auth["lockout_until"] = time.time() + LOCKOUT_DURATION
        auth["fail_count"] = 0
        locked = True
    save_auth(auth)
    # security log
    try:
        with open(os.environ.get("MOBILE_BOT_AUDIT_LOG") or os.path.expanduser("~/.claude/mobile-bot-audit.jsonl"), "a") as f:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "event": "pin_failure",
                "fail_count": fc,
                "lockout_triggered": locked,
            }) + "\n")
    except Exception:
        pass
    return (fc, locked)


def reset_failures() -> None:
    auth = load_auth()
    auth["fail_count"] = 0
    auth.pop("lockout_until", None)
    save_auth(auth)


# ──────────────────────────────────────────────────────────────────────────
# PIN keypad UI
# ──────────────────────────────────────────────────────────────────────────

def _make_pin_keypad(action: str) -> InlineKeyboardMarkup:
    """action in {'auth', 'setup1', 'setup2'} — distinguishes the stage in the callback."""
    rows = [
        [InlineKeyboardButton(d, callback_data=f"pin:{action}:{d}") for d in "123"],
        [InlineKeyboardButton(d, callback_data=f"pin:{action}:{d}") for d in "456"],
        [InlineKeyboardButton(d, callback_data=f"pin:{action}:{d}") for d in "789"],
        [
            InlineKeyboardButton("⌫", callback_data=f"pin:{action}:back"),
            InlineKeyboardButton("0", callback_data=f"pin:{action}:0"),
            InlineKeyboardButton("✕", callback_data=f"pin:{action}:clear"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def _pin_mask(filled: int) -> str:
    return "●" * filled + "○" * (PIN_LENGTH - filled)


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return {**DEFAULT_SETTINGS, **json.loads(SETTINGS_FILE.read_text())}
        except (json.JSONDecodeError, OSError):
            log.warning("settings corrupted — using defaults")
    return DEFAULT_SETTINGS.copy()


def save_settings(s: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(s, indent=2))


def md_chunks(text: str, limit: int = 3500) -> list[str]:
    """Markdown -> pieces of at most `limit`, cut on line boundaries. Cutting READY HTML by characters is not
    allowed: the cut lands inside a tag (<b -> BadRequest) and the fallback sends garbage. So the raw text is
    cut and every piece is turned into HTML on its own; the 3500 headroom covers growth from escape/href."""
    if not text.strip():
        return []   # only [LOC]/[SEND] and no text: an empty message is a BadRequest and breaks the loop before the location/file
    u16 = lambda x: len(x.encode("utf-16-le")) // 2   # Telegram counts the limit in UTF-16: an emoji is 2
    parts, cur = [], ""
    for line in text.split("\n"):
        while u16(line) > limit:
            if cur:
                parts.append(cur); cur = ""
            n, cut = 0, 0
            for ch in line:
                n += 2 if ord(ch) > 0xFFFF else 1
                if n > limit:
                    break
                cut += 1
            parts.append(line[:cut]); line = line[cut:]
        if cur and u16(cur) + 1 + u16(line) > limit:
            parts.append(cur); cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts


def md_to_tg_html(text: str) -> str:
    """Convert Claude's markdown output → Telegram-compatible HTML.

    Telegram HTML subset: <b>, <i>, <u>, <s>, <code>, <pre>, <a>, <blockquote>.
    No <ul>/<ol>/<li>/<h1>/<br> — fall back to plain text formatting.
    """
    # 1) Pull out code blocks and inline code BEFORE escaping, swap in placeholders
    placeholders = {}
    counter = [0]

    def stash(tag_open, content, tag_close):
        idx = counter[0]; counter[0] += 1
        key = f"\x00PH{idx}\x00"
        placeholders[key] = tag_open + html.escape(content, quote=False) + tag_close
        return key

    # Triple-backtick code block (with or without a language hint)
    text = re.sub(
        r"```(\w*)\n?(.*?)```",
        lambda m: stash("<pre>", m.group(2).rstrip("\n"), "</pre>"),
        text, flags=re.DOTALL,
    )
    # Inline `code`
    text = re.sub(
        r"`([^`\n]+)`",
        lambda m: stash("<code>", m.group(1), "</code>"),
        text,
    )

    # 2) Escape HTML for the rest of the text
    text = html.escape(text, quote=False)

    # 3) Markdown links [text](url) — first, so they don't clash with bold/italic
    def link_sub(m):
        link_text = m.group(1)
        url = m.group(2)
        # url was already HTML-escaped with the rest of the text in step 2; unescape
        # first, or "&" becomes "&amp;amp;" and the link breaks. quote=True for href.
        return f'<a href="{html.escape(html.unescape(url), quote=True)}">{link_text}</a>'
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link_sub, text)

    # 4) Bold **text**
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", text)
    # Bold __text__
    text = re.sub(r"__([^_\n]+)__", r"<b>\1</b>", text)

    # 5) Italic *text* (singleton, not **)
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<i>\1</i>", text)
    # Italic _text_
    text = re.sub(r"(?<![_\w])_([^_\n]+)_(?![_\w])", r"<i>\1</i>", text)

    # 6) Headings ##/### -> bold (Telegram has no headings)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # 7) Leave bullet lists as plain text (- or *) — renders fine
    # Numbered lists (1. 2. 3.) are fine too

    # 8) Restore code placeholders
    for key, value in placeholders.items():
        text = text.replace(key, value)

    return text


def load_sid() -> str | None:
    if SESSION_FILE.exists():
        v = SESSION_FILE.read_text().strip()
        return v or None
    return None


def save_sid(sid: str) -> None:
    SESSION_FILE.write_text(sid)


# The child must not see the bot's own secrets: a reply is one `echo $TOKEN` away otherwise.
_CHILD_ENV_DROP = {"TELEGRAM_BOT_TOKEN", "ALLOWED_TG_USERS"}


def child_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in _CHILD_ENV_DROP and not re.search(r"(TOKEN|SECRET|PASSWORD|API_KEY)$", k)
           or k in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")}
    env.update(extra)
    return env


# The gate is passed by the bot itself on every call, so it can't be forgotten in settings.json
# and doesn't depend on the install scope. Paths are quoted: the install dir may contain spaces.
_HOOKS = pathlib.Path(__file__).resolve().parent / "hooks"
sys.path.insert(0, str(_HOOKS))
from mobile_restrict import refuse_send   # one definition of "secret" for the gate and [SEND:]
MOBILE_SETTINGS = json.dumps({"hooks": {
    "PreToolUse": [{"matcher": "Bash|Read|Grep|Glob|Write|Edit|MultiEdit|NotebookEdit",
                    "hooks": [{"type": "command", "command": shlex.quote(str(_HOOKS / "mobile-restrict.sh"))}]}],
    "PostToolUse": [{"matcher": "Write|Edit",
                     "hooks": [{"type": "command", "command": shlex.quote(str(_HOOKS / "mobile-audit.sh"))}]}],
}})


# ── Session rotation ──────────────────────────────────────────────────────────────────────────────
# One session that lives for months grows to hundreds of thousands of tokens: every message after a pause
# (the cache has expired) re-reads all of it at full price, and the model "thinks" long before the first word.
# The auto-compact sits near the window's ceiling and never fired. So: a session over ROTATE_TOKENS writes a
# summary right after a reply (the cache is still warm), and the next message starts a new session seeded
# with that summary. 0 = never rotate.
ROTATE_TOKENS = int(os.environ.get("MOBILE_BOT_ROTATE_TOKENS") or 200_000)
# Claude Code keeps a session as <home>/.claude/projects/<working dir with every non-alphanumeric as "-">/<sid>.jsonl
SESSIONS_DIR = pathlib.Path(os.environ.get("MOBILE_BOT_SESSIONS_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(CLAUDE_CWD))))
# Outside any git repo on purpose: this is the gist of private conversations.
HANDOFF_DIR = pathlib.Path(os.environ.get("MOBILE_BOT_HANDOFF_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "mobile-handoff"))
HANDOFF_NEXT = HANDOFF_DIR / "next.md"
HUMAN = _conf("CCM_HUMAN_NAME", "the user")
HANDOFF_PROMPT = (
    "This conversation is moving to a new session because it has grown too large. Write a summary for your "
    f"next self, who will continue the conversation with {HUMAN} in Telegram: what was discussed and decided; "
    "what is still open (with dates); what they asked you to do or not to do in this chat; important facts "
    "from the last weeks that are not in your memory files. The gist only, no preamble, up to 700 words, "
    "markdown. Do not call any tools - just the text of the summary.")


def session_tokens(sid: str) -> int:
    """Context size = the input of the last model call in the session (read from its file). No data -> 0."""
    f = SESSIONS_DIR / f"{sid}.jsonl"
    try:
        with open(f, "rb") as fh:
            fh.seek(max(0, f.stat().st_size - 400_000))
            lines = fh.read().decode(errors="replace").splitlines()
    except OSError:
        return 0
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        u = (d.get("message") or {}).get("usage") if isinstance(d, dict) and d.get("type") == "assistant" else None
        if u:
            return u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
    return 0


async def maybe_rotate_session() -> None:
    sid = load_sid()
    if not ROTATE_TOKENS or not sid or (n := session_tokens(sid)) < ROTATE_TOKENS:
        return
    log.info("rotate: session %s = %dk tokens, writing a summary", sid[:8], n // 1000)
    settings = load_settings()
    proc = await asyncio.create_subprocess_exec(
        *claude_cmd(HANDOFF_PROMPT, sid, settings),
        cwd=CLAUDE_CWD, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=child_env(CLAUDE_CODE_ENTRYPOINT="claude-vscode", CLAUDE_MOBILE_BOT="1", **_gate_env()))
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=300)
        text = json.loads(out.decode()).get("result", "") if proc.returncode == 0 else ""
    except asyncio.CancelledError:
        proc.kill()
        raise
    except asyncio.TimeoutError:
        proc.kill(); text = ""
    except (ValueError, AttributeError):
        text = ""
    if len(text.strip()) < 200:   # no summary: leave the session alone, try again after the next reply
        log.warning("rotate: no summary produced (rc=%s), keeping the session", proc.returncode)
        return
    body = f"# Summary of session {sid[:8]} ({time.strftime('%Y-%m-%d %H:%M')}, {n // 1000}k tokens)\n\n{text.strip()}\n"
    HANDOFF_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    targets = [HANDOFF_DIR / f"{time.strftime('%Y%m%d-%H%M')}-{sid[:8]}.md"]
    if load_sid() == sid:   # /reset during the summary: the human wants a clean session - archive only
        targets.append(HANDOFF_NEXT)
    for path in targets:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(body)
    if HANDOFF_NEXT in targets:
        SESSION_FILE.unlink(missing_ok=True)
    log.info("rotate: done, the next message starts a new session with the summary (%d chars)", len(text))


def humanize_claude_error(rc: int, stderr: str) -> str:
    """Turns a technical `claude -p` failure into a plain explanation, classified by stderr patterns.
    Returns MARKDOWN (not HTML): md_to_tg_html() runs after it and escapes raw tags. The raw stderr tail
    stays at the end for diagnosis."""
    s = (stderr or "").lower()
    tail = (stderr or "").strip()[:400]

    def msg(head: str) -> str:
        out = f"{head}\n\n_tech: rc={rc}_"
        if tail:
            out += f"\n```\n{tail}\n```"
        return out

    # 0. The claude process was killed by a signal (143 = SIGTERM on a bot restart, 137 = SIGKILL/OOM):
    #    an outside stop, not a crash of claude - do not alarm.
    if rc in (143, 137) and not tail:
        return ("🔄 **I was just restarted, or the server ran out of memory** - your request was cut off "
                "halfway. Just send it again.")
    # 1. Login expired (most often after a token refresh)
    if any(k in s for k in ("invalid api key", "authentication", "unauthorized", "401",
                            "please run /login", "oauth", "credentials", "not logged in",
                            "no auth", "token has expired", "expired")):
        return msg("🔑 **Authorization problem** - the Claude login expired or was not synced. "
                   "Log in again on the server (`claude` -> `/login`).")
    # 2. Limit / quota / overload
    if any(k in s for k in ("rate limit", "429", "usage limit", "quota", "overloaded",
                            "529", "too many requests", "capacity")):
        return msg("📊 **Limit or overload** - the quota is used up or Anthropic is overloaded. "
                   "Wait a little and try again.")
    # 3. Broken or lost session id (resume of a session that does not exist)
    if any(k in s for k in ("no conversation found", "session not found", "no session",
                            "could not find session", "invalid session")):
        return msg("🧵 **The session broke** - the saved session id was not found. "
                   "Send /reset to start a new conversation (the old memory stays in the files).")
    # 4. Network / DNS / connection
    if any(k in s for k in ("network", "connection", "dns", "timeout", "timed out",
                            "econnrefused", "getaddrinfo", "unreachable", "ssl")):
        return msg("🌐 **The network is shaky** - could not reach Anthropic. "
                   "Most likely temporary, try again in a minute.")
    # 5. Not recognised: say so honestly and give the raw tail
    return msg("❌ **Claude failed for an unknown reason.** This is what it said:")


class ClaudeFailed(Exception):
    """Claude did not answer (network, login, limit). The text is for the human; the letter stays in the queue for a retry."""


class ClaudeKilled(ClaudeFailed):
    """Claude was killed by TERM - usually a restart of the bot itself, the letter is not to blame."""


# Attempt flag of a queued letter: there is one worker, so a plain variable. Claude may have died after acting.
_inq_retry = False
RETRY_NOTE = ("[The previous attempt at this message was cut off and may have been carried out partly. "
              "First check what is already done; do not duplicate letters to agents or file writes.]\n\n")


def claude_cmd(prompt: str, sid: str | None, settings: dict) -> list[str]:
    """One set of flags for a normal call and for the rotation summary: other tools or another system
    prompt = another cache prefix, and the summary would not hit the warm cache."""
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--exclude-dynamic-system-prompt-sections",
        "--permission-mode", "acceptEdits",
        # User settings only. Project/local settings carry the "always allow" grants collected
        # in working sessions (`--allowedTools` adds to them, it doesn't replace them).
        "--setting-sources", "user",
        "--settings", MOBILE_SETTINGS,   # the gate: hooks/mobile_restrict.py
        # This list is the first layer, not the boundary: a "Bash(x:*)" prefix rule allows every
        # form of x (`sed -i` and `sort -o` ran under theirs), so tools with a write or exec
        # mode are left out (sed, awk, find, fd -x, rg --pre) and the gate does the rest.
        "--allowedTools",
        "Read", "Grep", "Glob", "WebFetch", "WebSearch", "Edit", "Write",
        "Bash(ls:*)", "Bash(grep:*)", "Bash(cat:*)",
        "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(sort:*)", "Bash(uniq:*)",
        "Bash(du:*)", "Bash(df:*)", "Bash(stat:*)", "Bash(file:*)",
        "Bash(which:*)", "Bash(echo:*)", "Bash(tree:*)",
        "Bash(date:*)", "Bash(pwd)", "Bash(whoami)",
        "Bash(git log:*)", "Bash(git status)", "Bash(git diff:*)", "Bash(git show:*)",
        # OSM Overpass nearby search - for location-based queries
        f"Bash({OSM_SCRIPT}:*)",
    ]
    if SWARM_ON:   # a letter to an agent: only this wrapper (the canonical inbox_post.sh runs under it)
        cmd.append("Bash(" + " ".join(INBOX_CMD) + ":*)")
    cmd += [
        "--disallowedTools", "NotebookEdit", "Task",
        "--model", settings["model"],
        "--effort", settings["effort"],
    ]
    if sid:
        cmd += ["--resume", sid]
    return cmd


def _gate_env() -> dict:
    """What the gate hook needs to know about the swarm wrapper (empty = letters to agents are refused)."""
    return {"CLAUDE_MOBILE_BOT_INBOX_WRAPPER": INBOX_WRAPPER if SWARM_ON else ""}


async def run_claude(prompt: str) -> tuple[str, str | None]:
    """Runs claude -p, returns (reply text, new session_id). Raises ClaudeFailed on a crash."""
    if _inq_retry:
        prompt = RETRY_NOTE + prompt
    sid = load_sid()
    handoff = HANDOFF_NEXT.read_text() if sid is None and HANDOFF_NEXT.exists() else ""
    if handoff:
        prompt = ("[The previous session grew too large and was closed. Its summary is below - continue from it; "
                  f"do not tell {HUMAN} about the rotation unless asked.]\n\n" + handoff + "\n\n---\n\n" + prompt)
    # Threat model: whoever took over the Telegram account CAN write the allowed text files and send letters
    # to agents (that is the capability asked for); they CANNOT read secrets outside the working dir, run
    # arbitrary commands, or write code/hooks/settings. The boundary is the gate hook (an allowlist) +
    # --setting-sources user + child_env() without the bot token. The allowlist is the first layer, not the only one.
    settings = load_settings()
    cmd = claude_cmd(prompt, sid, settings)

    log.info("calling claude (sid=%s model=%s effort=%s)",
             sid[:8] if sid else "new", settings["model"], settings["effort"])
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=CLAUDE_CWD,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=child_env(CLAUDE_CODE_ENTRYPOINT="claude-vscode",
                      CLAUDE_MOBILE_BOT="1", **_gate_env()),  # activates the gate
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.CancelledError:
        proc.kill()      # the bot is stopping: do not leave claude finishing unattended
        raise
    except asyncio.TimeoutError:
        proc.kill()
        return ("⏱ **Claude thought for over 5 minutes and I stopped it.** The task is too big or it hung - "
                "split it into smaller parts or try again.", None)

    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace")
        log.error("claude rc=%s stderr=%s", proc.returncode, stderr_text[:500])
        raise (ClaudeKilled if proc.returncode in (143, -15) else ClaudeFailed)(humanize_claude_error(proc.returncode, stderr_text))

    try:
        data = json.loads(stdout.decode())
    except json.JSONDecodeError as e:
        log.error("json decode fail: %s raw=%s", e, stdout.decode(errors="replace")[:500])
        return ("❓ **Claude answered, but I did not understand the format of the answer.** "
                "Most likely a one-off glitch - try again.", None)

    # JSON comes as a single object or a list of events - handle both
    result_text = None
    new_sid = None

    if isinstance(data, dict):
        result_text = data.get("result") or data.get("text") or ""
        new_sid = data.get("session_id")
    elif isinstance(data, list):
        for ev in data:
            if isinstance(ev, dict) and ev.get("type") == "result":
                result_text = ev.get("result", "")
                new_sid = ev.get("session_id")
                break

    # /reset during the reply (commands do not wait in the queue): do not resurrect a session that was reset
    if new_sid and new_sid != sid and load_sid() == sid:
        save_sid(new_sid)
        log.info("session updated: %s", new_sid[:8])
        if handoff:
            HANDOFF_NEXT.unlink(missing_ok=True)   # the summary is in the new session; the archive copy stays

    return (result_text or "(empty reply)", new_sid)


async def _require_pin_or_prompt(update: Update, context=None) -> bool:
    """Returns True if authorized, else shows PIN prompt and returns False.
    If context is passed — stores the pending message to retry after unlock."""
    uid = update.effective_user.id
    if not pin_required():
        return True
    # Setup needed?
    if not pin_is_set():
        await update.message.reply_text(
            "🔐 PIN not set yet. Tap /setpin to set " + str(PIN_LENGTH) + " digits.",
        )
        return False
    # Locked out?
    locked, remaining = is_locked_out()
    if locked:
        await update.message.reply_text(
            f"⛔ Locked out after wrong PINs. <b>{remaining // 60} min</b> left.",
            parse_mode=ParseMode.HTML,
        )
        return False
    # Session expired?
    if not is_unlocked():
        _pin_buffers[uid] = ""
        # Store the pending message — auto-process after unlock, no need to retype
        if context is not None:
            _pending_after_auth[uid] = {"update": update, "context": context, "ts": time.time()}
        await update.message.reply_text(
            f"🔒 Session locked. Enter PIN:\n\n<code>{_pin_mask(0)}</code>\n\n"
            "<i>Your message is saved — I'll process it after unlock.</i>",
            reply_markup=_make_pin_keypad("auth"),
            parse_mode=ParseMode.HTML,
        )
        return False
    return True


UPLOAD_DIR = pathlib.Path(os.environ.get("MOBILE_BOT_UPLOAD_DIR") or "/tmp/mobile-bot-uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Location is sticky for 2h — once shared, the bot remembers it for later queries.
# In-memory (sensitive); on restart the bot forgets — share again.
LOCATION_TTL = 2 * 60 * 60
_user_locations: dict[int, dict] = {}  # uid -> {lat, lng, ts}


def _get_user_location(uid: int) -> dict | None:
    """Returns a valid stored location (not expired) or None."""
    entry = _user_locations.get(uid)
    if not entry:
        return None
    if time.time() - entry["ts"] > LOCATION_TTL:
        _user_locations.pop(uid, None)
        return None
    return entry


def _set_user_location(uid: int, lat: float, lng: float) -> None:
    _user_locations[uid] = {"lat": lat, "lng": lng, "ts": time.time()}


def _clear_user_location(uid: int) -> bool:
    return _user_locations.pop(uid, None) is not None

# Rate limit: multi-tier rolling window. The first tier exceeded blocks all.
# (max_messages, window_seconds, label)
RATE_LIMIT_TIERS = [
    (3, 30, "30 sec"),       # anti-spam: 3 per 30 sec
    (8, 60, "1 min"),        # burst small: 8 per min
    (20, 15 * 60, "15 min"), # burst medium: 20 per 15 min
    (60, 60 * 60, "hour"),   # drain: 60 per hour
]
_rate_log: dict[int, list[float]] = {}
_rate_bypass: dict[int, float] = {}   # uid -> ts until which bypass applies


def _check_rate_limit(uid: int) -> tuple[bool, str]:
    """Returns (allowed, reason_if_blocked)."""
    now = time.time()
    if _rate_bypass.get(uid, 0) > now:
        return (True, "")
    log = _rate_log.setdefault(uid, [])
    longest_window = max(w for _, w, _ in RATE_LIMIT_TIERS)
    cutoff = now - longest_window
    while log and log[0] < cutoff:
        log.pop(0)
    # check each tier
    for limit, window, label in RATE_LIMIT_TIERS:
        in_window = sum(1 for t in log if t >= now - window)
        if in_window >= limit:
            return (False, f"⛔ Limit of <b>{limit}</b> messages / {label} reached. "
                           "Wait, or /unlimit (with PIN) to lift it temporarily.")
    log.append(now)
    return (True, "")


URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _wrap_url_only(text: str) -> str:
    """If the text is just a URL (with minimal framing) — wrap it in an explicit fetch instruction."""
    stripped = text.strip()
    urls = URL_RE.findall(stripped)
    # text without the URLs
    rest = URL_RE.sub("", stripped).strip()
    if urls and len(rest) < 10:  # only a URL and a few chars
        return (
            f"The user sent a link: {urls[0]}\n"
            "WebFetch it and summarize briefly — the main idea and why it might matter."
        )
    return text


def _format_forward_context(msg) -> str:
    """If the message is forwarded — returns a preamble with the source."""
    if not msg.forward_origin:
        return ""
    origin = msg.forward_origin
    src = ""
    try:
        # Telegram MessageOrigin types
        t = origin.type
        if t == "user" and hasattr(origin, "sender_user"):
            u = origin.sender_user
            src = f"{u.full_name}" + (f" (@{u.username})" if u.username else "")
        elif t == "hidden_user" and hasattr(origin, "sender_user_name"):
            src = origin.sender_user_name
        elif t == "chat" and hasattr(origin, "sender_chat"):
            src = origin.sender_chat.title or "(chat)"
        elif t == "channel" and hasattr(origin, "chat"):
            src = origin.chat.title or "(channel)"
    except Exception:
        pass
    return f"[FORWARDED from: {src or '(unknown)'}]\n"


async def _download_photo(msg, context) -> pathlib.Path | None:
    """Downloads the largest version of the photo to /tmp."""
    if not msg.photo:
        return None
    largest = msg.photo[-1]  # last = biggest resolution
    file = await context.bot.get_file(largest.file_id)
    ext = ".jpg"
    name = f"{int(time.time()*1000)}_{pysecrets.token_hex(4)}{ext}"
    path = UPLOAD_DIR / name
    await file.download_to_drive(str(path))
    return path


# Document types we accept as attachments
ALLOWED_DOC_EXT = {".md", ".txt", ".pdf", ".csv", ".json", ".yaml", ".yml", ".log", ".html"}
MAX_DOC_SIZE = 10 * 1024 * 1024  # 10 MB


async def _download_animation(msg, context) -> pathlib.Path | None:
    """Telegram GIF (animation = mp4) -> downloads + extracts 3 keyframes."""
    if not msg.animation:
        return None
    anim = msg.animation
    file = await context.bot.get_file(anim.file_id)
    base = f"{int(time.time()*1000)}_{pysecrets.token_hex(3)}_gif"
    path = UPLOAD_DIR / f"{base}.mp4"
    await file.download_to_drive(str(path))
    return path


async def _extract_animation_frames(video_path: pathlib.Path) -> list[pathlib.Path]:
    """3 frames from a gif/animation via ffmpeg."""
    frames_dir = video_path.parent / f"{video_path.stem}_frames"
    frames_dir.mkdir(exist_ok=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", "select='not(mod(n,5))',scale=720:-1",
            "-vsync", "vfr",
            "-frames:v", "3",
            str(frames_dir / "f_%02d.jpg"),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)
        return sorted(frames_dir.glob("f_*.jpg"))
    except Exception as e:
        log.warning("animation frame extract failed: %s", e)
        return []


async def _download_document(msg, context) -> pathlib.Path | None:
    """Downloads a document attachment if its type and size are allowed."""
    if not msg.document:
        return None
    doc = msg.document
    fname = doc.file_name or "document"
    ext = pathlib.Path(fname).suffix.lower()
    if ext not in ALLOWED_DOC_EXT:
        log.info("rejected doc with ext %s", ext)
        return None
    if doc.file_size and doc.file_size > MAX_DOC_SIZE:
        log.info("rejected doc size %s", doc.file_size)
        return None
    file = await context.bot.get_file(doc.file_id)
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", fname)[:80]
    name = f"{int(time.time()*1000)}_{pysecrets.token_hex(4)}_{safe_name}"
    path = UPLOAD_DIR / name
    await file.download_to_drive(str(path))
    return path


# Voice → transcription via faster-whisper (local, no API).
# The model is lazy — loaded on the first voice message.
_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            log.info("loading whisper model 'base'…")
            _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            log.info("whisper model loaded")
        except Exception as e:
            log.error("whisper unavailable: %s", e)
            return None
    return _whisper_model


SOCIAL_VIDEO_RE = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*"
    r"(?:tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com|"
    r"instagram\.com|youtube\.com/shorts|youtu\.be|"
    r"twitter\.com|x\.com)"
    r"/\S+",
    re.IGNORECASE,
)


async def _extract_social_video(url: str) -> dict:
    """Downloads a TikTok/Reels/Shorts video -> metadata + frames + audio transcript."""
    workdir = UPLOAD_DIR / f"video_{int(time.time()*1000)}_{pysecrets.token_hex(3)}"
    workdir.mkdir(parents=True, exist_ok=True)
    out_template = str(workdir / "%(id)s.%(ext)s")

    # yt-dlp: video as mp4, moderate quality (360p-720p) to stay fast
    cmd = [
        "yt-dlp", "--no-playlist", "--quiet", "--no-warnings",
        "--write-info-json",
        "--format", "best[ext=mp4][height<=720]/best[ext=mp4]/best",
        "--max-filesize", "100M",
        "-o", out_template,
        url,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            return {"error": f"yt-dlp rc={proc.returncode}: {stderr.decode()[:300]}"}
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return {"error": "timeout (>120s)"}

    info_files = list(workdir.glob("*.info.json"))
    video_files = [f for f in workdir.iterdir() if f.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
    if not info_files:
        return {"error": "no metadata extracted"}
    if not video_files:
        return {"error": "no video file extracted"}

    try:
        info = json.loads(info_files[0].read_text())
    except Exception as e:
        return {"error": f"info parse failed: {e}"}

    video_path = video_files[0]
    duration = float(info.get("duration") or 0)

    # 1. Audio extraction for whisper
    audio_path = workdir / "audio.mp3"
    try:
        audio_proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(video_path), "-vn",
            "-acodec", "libmp3lame", "-ar", "16000", "-b:a", "64k",
            str(audio_path),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(audio_proc.communicate(), timeout=60)
    except Exception as e:
        log.warning("audio extract failed: %s", e)

    # 2. Frames: scene detection (scene changes) + fallback uniform sampling
    frames_dir = workdir / "frames"
    frames_dir.mkdir(exist_ok=True)
    n_frames_target = 3 if duration < 15 else (6 if duration < 60 else 10)
    try:
        # Scene detection: threshold 0.25, capped to n_frames via -frames:v
        frame_proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", "select='gt(scene,0.25)',scale=720:-1",
            "-vsync", "vfr",
            "-frames:v", str(n_frames_target),
            str(frames_dir / "frame_%03d.jpg"),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(frame_proc.communicate(), timeout=60)
        extracted = sorted(frames_dir.glob("frame_*.jpg"))
        # Fallback: if scene detection yielded no frames — uniform sampling
        if len(extracted) < 2 and duration > 0:
            for f in extracted:
                f.unlink()
            fps = max(n_frames_target / duration, 0.1)
            fb_proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", str(video_path),
                "-vf", f"fps={fps:.4f},scale=720:-1",
                "-frames:v", str(n_frames_target),
                str(frames_dir / "frame_%03d.jpg"),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(fb_proc.communicate(), timeout=60)
            extracted = sorted(frames_dir.glob("frame_*.jpg"))
    except Exception as e:
        log.warning("frame extract failed: %s", e)
        extracted = []

    # 3. Whisper transcription
    transcript = ""
    if audio_path.exists():
        model = _get_whisper()
        if model is not None:
            try:
                def do_transcribe():
                    segments, _info = model.transcribe(str(audio_path), language=None, beam_size=1)
                    return " ".join(s.text.strip() for s in segments).strip()
                transcript = await asyncio.to_thread(do_transcribe)
            except Exception as e:
                log.warning("video transcript failed: %s", e)

    # Cleanup: video and audio are large — delete them. Keep frames and info for the agent.
    try:
        video_path.unlink()
    except OSError:
        pass
    try:
        if audio_path.exists():
            audio_path.unlink()
    except OSError:
        pass

    return {
        "title": info.get("title", "") or (info.get("description", "") or "")[:100],
        "uploader": info.get("uploader") or info.get("channel") or info.get("uploader_id", ""),
        "duration": int(duration),
        "view_count": info.get("view_count", 0),
        "like_count": info.get("like_count", 0),
        "description": (info.get("description", "") or "")[:500],
        "transcript": transcript,
        "frames": [str(p) for p in extracted],
        "url": url,
    }


def _format_video_preamble(info: dict) -> str:
    if "error" in info:
        return f"[Could not download video: {info['error']}]"
    lines = ["[Social-media video]"]
    if info.get("uploader"):
        lines.append(f"Author: @{info['uploader']}")
    if info.get("title"):
        lines.append(f"Title/caption: {info['title']}")
    if info.get("description") and info["description"] != info.get("title", ""):
        lines.append(f"Description: {info['description']}")
    if info.get("duration"):
        lines.append(f"Duration: {info['duration']}s")
    stats = []
    if info.get("view_count"):
        stats.append(f"{info['view_count']:,} views")
    if info.get("like_count"):
        stats.append(f"{info['like_count']:,} likes")
    if stats:
        lines.append("Stats: " + ", ".join(stats))
    if info.get("transcript"):
        lines.append(f"\nAudio transcript:\n{info['transcript']}")
    else:
        lines.append("(audio has no speech or whisper failed)")
    if info.get("frames"):
        lines.append(
            f"\nVideo frames ({len(info['frames'])}, scene-detected / "
            "evenly sampled). READ each via the Read tool "
            "to see what's on screen:"
        )
        for fpath in info["frames"]:
            lines.append(f"  {fpath}")
    return "\n".join(lines)


async def _transcribe_voice(msg, context) -> str | None:
    """Downloads voice/audio and transcribes it locally via faster-whisper."""
    src = msg.voice or msg.audio
    if not src:
        return None
    model = _get_whisper()
    if model is None:
        return "(could not load whisper model — voice not transcribed)"
    file = await context.bot.get_file(src.file_id)
    path = UPLOAD_DIR / f"{int(time.time()*1000)}_voice.ogg"
    await file.download_to_drive(str(path))
    # transcribe (CPU-bound) — in a thread so the event loop is not blocked
    def do_transcribe():
        segments, info = model.transcribe(str(path), language=None, beam_size=1)
        return " ".join(seg.text.strip() for seg in segments).strip()
    transcript = await asyncio.to_thread(do_transcribe)
    try:
        path.unlink()
    except OSError:
        pass
    return transcript or "(empty transcript)"


# ── Reply helpers: the answer is already produced, so a send failure is healed here ──────────────

def _outbox_save_answer(chunk: str) -> None:
    TG_OUTBOX.mkdir(parents=True, exist_ok=True)
    f = TG_OUTBOX / f"{time.time_ns()}_{os.getpid()}.json"
    tmp = f.with_name("." + f.name + ".tmp")
    tmp.write_text(json.dumps({"self": True, "agent": "bot", "text": chunk}, ensure_ascii=False))
    os.replace(tmp, f)


def _retry_seconds(e: RetryAfter) -> float:
    ra = e.retry_after      # int or timedelta - depends on the PTB settings
    return ra.total_seconds() if hasattr(ra, "total_seconds") else float(ra)


async def _reply_after_effect(msg, text: str, **kw):
    """A confirmation AFTER an action is done (letter delivered, blocker cleared). A failure here must not go
    to the queue, or it would repeat the action itself. -> Message or None."""
    try:
        return await msg.reply_text(text, **kw)
    except TelegramError as e:
        log.warning("confirmation did not arrive (%s): %s", e, text[:80])
        return None


async def _reply_chunk(update: Update, chunk: str) -> None:
    """One piece of the reply. Claude has already worked: a send failure is healed here, or the queue would
    run Claude again (duplicate letters and quota). Not delivered in ~1.5 min -> the disk outbox."""
    for pause in (5, 30, 60, None):
        try:
            try:
                await update.message.reply_text(md_to_tg_html(chunk), parse_mode=ParseMode.HTML,
                                                disable_web_page_preview=True)
            except BadRequest as e:
                log.warning("HTML parse failed (%s) - fallback to plain text", e)
                await update.message.reply_text(chunk)
            return
        except TelegramError as e:
            if pause is None:   # Telegram is down for longer: the disk outbox, _outbox_loop delivers it
                log.error("reply did not arrive (%d chars): %s -> outbox", len(chunk), e)
                _outbox_save_answer(chunk)
                return
            log.warning("send failed (%s), retry in %d s", e, pause)
            await asyncio.sleep(_retry_seconds(e) if isinstance(e, RetryAfter) else pause)


async def handle_message(update: Update, context):
    user = update.effective_user
    if user.id not in ALLOWED:
        log.warning("unauthorized: id=%s name=%s", user.id, user.full_name)
        await update.message.reply_text(f"🚫 not authorized. your id: {user.id}")
        return

    if not await _require_pin_or_prompt(update, context):
        return

    # The rate limit is not checked here: the inbound queue holds a message back (it does not drop it),
    # see _inq_wait_rate.
    if SWARM_ON:
        if re.match(r"/to(@\w+)?(\s|$)", (update.message.text or "")):
            await cmd_to(update, context)
            return
        if await _reply_to_agent(update, context) or await _blocker_word(update) or await _wake_word(update):
            return

    msg = update.message
    chat_id = update.effective_chat.id

    # Collect message content (text + caption + forwarded preamble + photo/doc + voice)
    forward_preamble = _format_forward_context(msg)
    text_body = msg.text or msg.caption or ""

    photo_path = None
    if msg.photo:
        photo_path = await _download_photo(msg, context)

    doc_path = None
    extra_photo_path = None
    animation_frames = []   # before the document branch: a GIF sent as a file adds to it
    if msg.document:
        fname = msg.document.file_name or ""
        ext = pathlib.Path(fname).suffix.lower()
        mime = (msg.document.mime_type or "").lower()
        # Document-as-image: gif -> frames, others -> as photo
        if ext == ".gif" or mime == "image/gif":
            file = await context.bot.get_file(msg.document.file_id)
            gif_path = UPLOAD_DIR / f"{int(time.time()*1000)}_{pysecrets.token_hex(3)}_doc.gif"
            await file.download_to_drive(str(gif_path))
            extra_frames = await _extract_animation_frames(gif_path)
            if extra_frames:
                animation_frames.extend(extra_frames)
        elif ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"} or mime.startswith("image/"):
            file = await context.bot.get_file(msg.document.file_id)
            extra_photo_path = UPLOAD_DIR / f"{int(time.time()*1000)}_{pysecrets.token_hex(3)}{ext or '.img'}"
            await file.download_to_drive(str(extra_photo_path))
        else:
            doc_path = await _download_document(msg, context)
            if doc_path is None:
                await msg.reply_text(
                    "❌ Document rejected. Allowed: " + ", ".join(sorted(ALLOWED_DOC_EXT)) +
                    f", or image (.jpg/.png/.gif/.webp) (up to {MAX_DOC_SIZE // 1024 // 1024} MB)"
                )
                return

    voice_transcript = None
    if msg.voice or msg.audio:
        await context.bot.send_chat_action(chat_id, ChatAction.RECORD_VOICE)
        voice_transcript = await _transcribe_voice(msg, context)

    if msg.animation:
        await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
        anim_path = await _download_animation(msg, context)
        if anim_path:
            animation_frames.extend(await _extract_animation_frames(anim_path))

    # Social video (TikTok/Reels/Shorts/X video) — detect in text, process max 1 URL
    social_preamble = None
    social_url_to_strip = None
    if text_body:
        m = SOCIAL_VIDEO_RE.search(text_body)
        if m:
            social_url_to_strip = m.group(0)
            await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
            log.info("processing social video: %s", social_url_to_strip)
            info = await _extract_social_video(social_url_to_strip)
            social_preamble = _format_video_preamble(info)

    # If this is a location-only message — store sticky, reply with ack
    if msg.location and not (msg.text or msg.caption):
        lat, lng = msg.location.latitude, msg.location.longitude
        _set_user_location(user.id, lat, lng)
        await msg.reply_text(
            f"📍 Location saved ({lat:.5f}, {lng:.5f}).\n"
            f"I'll remember it for {LOCATION_TTL // 3600}h. All your queries will use "
            "these coordinates for 'nearby' search. /clearloc to forget."
        )
        return

    # If location arrived together with text — update sticky.
    if msg.location:
        _set_user_location(user.id, msg.location.latitude, msg.location.longitude)

    # Pull location from sticky storage (current or previously saved)
    location_preamble = None
    stored = _get_user_location(user.id)
    if stored:
        lat, lng = stored["lat"], stored["lng"]
        location_preamble = (
            f"[User location: {lat:.5f}, {lng:.5f}]   Maps: https://www.google.com/maps?q={lat},{lng}\n\n"
            "OSM nearby search (REQUIRED for any 'nearby'/'close by'/brand queries):\n"
            f"  bash {OSM_SCRIPT} {lat} {lng} <radius_km> <amenity> [name_regex]\n\n"
            "Parameters:\n"
            "  • radius_km: default 3, brands — 5-10\n"
            "  • amenity: restaurant, fast_food, cafe, bar, pub, food_court, ice_cream, "
            "pharmacy, atm, bank, fuel, hospital, school\n"
            "  • name_regex (optional): case-insensitive Python regex to filter by name. "
            "If your area uses a non-Latin script, try both: 'McDonald|<local spelling>'.\n\n"
            "CRITICAL — how to search:\n"
            "  • Shawarma/fast food/diners/KFC = fast_food (NOT restaurant)\n"
            "  • Cafes with pastries = cafe\n"
            "  • Sit-down restaurants = restaurant\n"
            "  • To find a CUISINE — try amenity in order: "
            "restaurant, fast_food, cafe, food_court. Otherwise you'll miss a whole class.\n"
            "  • To find a BRAND — use name_regex + radius 5-10km. "
            "If not in one amenity — try them all.\n\n"
            "IF NOT IN OSM:\n"
            "  • Don't invent. Say 'Not in OpenStreetMap (searched <pattern> within Xkm in "
            "restaurant/fast_food/cafe). You can check via a Google Maps URL — paste it "
            "in your browser: https://www.google.com/maps/search/<query>/@<lat>,<lng>,15z'\n\n"
            "REPLY STYLE:\n"
            "  • Brief: name + distance + 1 line of substance. NO phones/hours/addresses in the summary.\n"
            "  • Details — only when the user explicitly asks.\n"
            "  • If you found a brand — give distance and whether the site has a menu. No marketing fluff.\n\n"
            "INTERACTIVE LOCATIONS:\n"
            "  • For the top 1-3 picks add a marker to the reply: [LOC: lat,lng,name]\n"
            "  • Example: [LOC: 50.4555,30.6172,Some Diner]\n"
            "  • The bot extracts the marker and sends a real Telegram location (interactive pin, "
            "opens with a tap in Google Maps).\n"
            "  • Don't write the marker visibly — put it in the reply, the bot strips it before display.\n"
            "  • Max 3 LOC markers (the bot drops extras).\n\n"
            "Do NOT use WebSearch for 'what's nearby' — those are blog listicles. "
            "OSM = coordinates + distances. WebSearch/WebFetch — only menus and reviews."
        )

    parts = []
    # Always add the instruction about sending files back to Telegram
    parts.append(
        "[REPLY CAPABILITIES — invisible markers in the text, the bot extracts and handles them]\n"
        "  • Send a file to the user: insert a marker [SEND: /full/absolute/path/to/file]\n"
        f"    — only files inside {CLAUDE_CWD}/, up to 50 MB\n"
        "    — photos (.jpg/.png/...) up to 10MB are sent as a photo with preview, others as a document\n"
        "    — max 5 files per reply\n"
        "    — NO secrets, NO credentials, NO .git, NO /etc — the bot blocks these\n"
        "  • Send a location: [LOC: lat,lng,name] (max 3)\n"
        "  • Don't show markers to the user in your explanation — just put them in the reply text, "
        "the bot strips them before display.\n"
    )
    if SWARM_ON:
        _ap = [p for p in os.environ.get("CLAUDE_MOBILE_BOT_ALLOW_PATHS", "").split(":") if p]
        if _ap:
            parts.append(
                "[WRITING - allowed by the human]\n"
                f"  • Text files: Write/Edit only inside {', '.join(_ap)} (not secrets, not .git, not hooks/settings, "
                "not an inbox.md - the gate blocks them).\n"
                f"  • A letter to an agent (its inbox): TWO steps. 1) Write the text of the letter to {_ap[0]}/bot-outbox/<name>.md. "
                f"2) Bash in exactly this form: cat <that file> | {' '.join(INBOX_CMD)} <Agent>\n"
                f"    - <Agent> = the exact folder name in {AGENTS_DIR}/. Not sure - ls it first.\n"
                f"    - the signature \"from {HUMAN} (Telegram bot)\" and the date are added automatically, do not write them.\n"
                "    - editing an inbox.md directly is forbidden: it loses letters under parallel writes.\n"
                "    - after sending, tell the human briefly whom it went to.\n")
    if forward_preamble:
        parts.append(forward_preamble.rstrip())
    if location_preamble:
        parts.append(location_preamble)
    if photo_path:
        parts.append(f"[The user attached an image: {photo_path}]")
        parts.append("Read it via the Read tool to see what's there.")
    if extra_photo_path:
        parts.append(f"[The user attached an image (as a document): {extra_photo_path}]")
        parts.append("Read it via the Read tool to see what's there.")
    if doc_path:
        parts.append(f"[The user attached a document: {doc_path}]")
        parts.append("Read it via the Read tool.")
    if voice_transcript:
        parts.append(f"[Voice message, transcribed]: {voice_transcript}")
    if animation_frames:
        parts.append(f"[GIF/animation — {len(animation_frames)} frames]")
        for f in animation_frames:
            parts.append(f"  {f}")
        parts.append("Read the frames via the Read tool to see what's in the gif/animation.")
    if social_preamble:
        parts.append(social_preamble)
    if text_body:
        # If the text had a social URL — strip it to avoid duplication
        if social_url_to_strip:
            text_body = text_body.replace(social_url_to_strip, "").strip()
        if text_body:
            text_body = _wrap_url_only(text_body)
            parts.append(text_body)
    text = "\n\n".join(parts).strip() or "(empty message)"

    log.info("msg from %s: %s", user.id, text[:100])
    touch_activity()

    # show that we're working
    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

    # keep "typing" alive while claude thinks (can take a while)
    async def keep_typing():
        while True:
            await asyncio.sleep(4)
            try:
                await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
            except Exception:
                pass   # a one-off network glitch must not switch the indicator off until the end of the reply

    typing_task = asyncio.create_task(keep_typing())
    try:
        reply, _ = await run_claude(text)
    finally:
        typing_task.cancel()

    # Extract [SEND: <path>] markers for sending files from the VM
    SEND_RE = re.compile(r"\[SEND:\s*([^\]]+)\]")
    SEND_ROOT = pathlib.Path(CLAUDE_CWD).resolve()
    MAX_SEND_BYTES = 50 * 1024 * 1024  # Telegram bot limit ~50MB
    files_to_send: list[pathlib.Path] = []
    for m in SEND_RE.finditer(reply):
        raw_path = m.group(1).strip().strip("'\"")
        try:
            p = pathlib.Path(raw_path).resolve()
        except Exception:
            continue
        if not p.is_file():
            log.warning("SEND skipped (not file): %s", p)
            continue
        if not p.is_relative_to(SEND_ROOT):   # not startswith: /x/cwd-backup is not inside /x/cwd
            log.warning("SEND skipped (outside root): %s", p)
            continue
        if refuse_send(p):
            log.warning("SEND skipped (sensitive): %s", p)
            continue
        if p.stat().st_size > MAX_SEND_BYTES:
            log.warning("SEND skipped (>50MB): %s", p)
            continue
        files_to_send.append(p)
    reply = SEND_RE.sub("", reply).strip()
    # dedup
    seen_files = set()
    unique_files = []
    for p in files_to_send:
        if p in seen_files:
            continue
        seen_files.add(p)
        unique_files.append(p)
    files_to_send = unique_files[:5]  # max 5

    # Extract coordinates from three sources and send as real Telegram locations:
    # 1. [LOC: lat,lng,name] marker (if the agent used it explicitly)
    # 2. Google Maps URL with ?q=lat,lng (the agent often writes these)
    # 3. Google Maps URL with @lat,lng in place links
    loc_re = re.compile(r"\[LOC:\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)(?:\s*,\s*([^\]]+))?\]")
    gmaps_re = re.compile(
        r"https?://(?:www\.)?(?:google\.com/maps|maps\.google\.com)[^\s\)\]]*?"
        r"(?:[?&]q=|@)(-?\d+\.\d+)[,%2C]\s*(-?\d+\.\d+)",
        re.IGNORECASE,
    )

    locations_to_send = []
    for m in loc_re.finditer(reply):
        try:
            lat, lng = float(m.group(1)), float(m.group(2))
            name = (m.group(3) or "").strip()
            locations_to_send.append((lat, lng, name))
        except ValueError:
            continue
    reply = loc_re.sub("", reply)

    for m in gmaps_re.finditer(reply):
        try:
            lat, lng = float(m.group(1)), float(m.group(2))
            locations_to_send.append((lat, lng, ""))
        except ValueError:
            continue
    reply = reply.strip()

    # Dedupe by coordinates (5 decimals = ~1.1m precision)
    seen = set()
    unique_locs = []
    for lat, lng, name in locations_to_send:
        key = (round(lat, 5), round(lng, 5))
        if key in seen:
            continue
        seen.add(key)
        unique_locs.append((lat, lng, name))

    # Telegram limit 4096: cut the markdown on line boundaries, each piece -> HTML on its own (see md_chunks).
    for chunk in md_chunks(reply):
        await _reply_chunk(update, chunk)

    # Send interactive locations after the main reply (max 3 to avoid spam)
    for lat, lng, name in unique_locs[:3]:
        try:
            await context.bot.send_location(chat_id, latitude=lat, longitude=lng)
            if name:
                await update.message.reply_text(f"📍 {name}")
        except Exception as e:
            log.warning("send_location failed for %s,%s: %s", lat, lng, e)

    # Send files from the VM (if the agent added [SEND: ...] markers)
    PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    for path in files_to_send:
        try:
            ext = path.suffix.lower()
            with open(path, "rb") as f:
                if ext in PHOTO_EXTS and path.stat().st_size <= 10 * 1024 * 1024:
                    await context.bot.send_photo(chat_id, photo=f, caption=path.name)
                else:
                    await context.bot.send_document(chat_id, document=f, filename=path.name)
        except Exception as e:
            log.warning("send file failed for %s: %s", path, e)
            try:
                await update.message.reply_text(f"❌ Couldn't send {path.name}: {e}")
            except Exception:
                pass


async def cmd_whoami(update: Update, context):
    u = update.effective_user
    await update.message.reply_text(
        f"tg user_id: {u.id}\nchat_id: {update.effective_chat.id}\nname: {u.full_name}"
    )


async def _require_unlock_for_cmd(update: Update) -> bool:
    """Check the session is unlocked — else show a PIN prompt and return False."""
    if not pin_is_set():
        await update.message.reply_text("Set a PIN first: /setpin")
        return False
    locked, remaining = is_locked_out()
    if locked:
        await update.message.reply_text(
            f"⛔ Locked out for {remaining // 60} min.",
        )
        return False
    if not is_unlocked():
        _pin_buffers[update.effective_user.id] = ""
        await update.message.reply_text(
            f"🔒 Enter PIN:\n\n<code>{_pin_mask(0)}</code>",
            reply_markup=_make_pin_keypad("auth"),
            parse_mode=ParseMode.HTML,
        )
        return False
    return True


async def cmd_reset(update: Update, context):
    if update.effective_user.id not in ALLOWED:
        return
    if not await _require_unlock_for_cmd(update):
        return
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
    HANDOFF_NEXT.unlink(missing_ok=True)   # a clean session - without the summary of the previous one
    await update.message.reply_text("🔄 Mobile session reset. The next message starts a new one.")


async def cmd_session(update: Update, context):
    if update.effective_user.id not in ALLOWED:
        return
    if not await _require_unlock_for_cmd(update):
        return
    sid = load_sid()
    await update.message.reply_text(f"current mobile sid: {sid or '(none — created on first message)'}")


def _make_model_keyboard(current: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        ("✅ " if m == current else "") + m.title(),
        callback_data=f"set_model:{m}"
    )] for m in MODELS]
    return InlineKeyboardMarkup(rows)


def _make_effort_keyboard(current: str, model: str) -> InlineKeyboardMarkup:
    available = MODEL_EFFORTS.get(model, EFFORTS)
    rows = [[InlineKeyboardButton(
        ("✅ " if e == current else "") + e,
        callback_data=f"set_effort:{e}"
    )] for e in available]
    return InlineKeyboardMarkup(rows)


async def cmd_model(update: Update, context):
    if update.effective_user.id not in ALLOWED:
        return
    if not await _require_unlock_for_cmd(update):
        return
    s = load_settings()
    await update.message.reply_text(
        f"Current model: <b>{s['model']}</b>\n\nChoose a model:",
        reply_markup=_make_model_keyboard(s["model"]),
        parse_mode=ParseMode.HTML,
    )


async def cmd_effort(update: Update, context):
    if update.effective_user.id not in ALLOWED:
        return
    if not await _require_unlock_for_cmd(update):
        return
    s = load_settings()
    available = MODEL_EFFORTS.get(s["model"], EFFORTS)
    note = ""
    if s["model"] == "haiku":
        note = "\n\n<i>Haiku supports only low/medium — smaller model.</i>"
    await update.message.reply_text(
        f"Current effort: <b>{s['effort']}</b> (model: <code>{s['model']}</code>)\n\n"
        f"low/medium — fast, cheap\nhigh/xhigh/max — slower, deeper thinking"
        f"{note}",
        reply_markup=_make_effort_keyboard(s["effort"], s["model"]),
        parse_mode=ParseMode.HTML,
    )


async def cmd_settings(update: Update, context):
    if update.effective_user.id not in ALLOWED:
        return
    if not await _require_unlock_for_cmd(update):
        return
    s = load_settings()
    sid = load_sid()
    await update.message.reply_text(
        f"<b>Current settings:</b>\n"
        f"• Model: <code>{s['model']}</code>\n"
        f"• Effort: <code>{s['effort']}</code>\n"
        f"• Session: <code>{sid[:8] if sid else 'none'}</code>\n\n"
        "Commands: /model /effort /reset",
        parse_mode=ParseMode.HTML,
    )


_edit_counter = 0


async def _safe_edit(q, *args, **kwargs):
    """edit_message_text that always updates the UI.

    Telegram raises 'message not modified' if the new text is byte-identical to
    the previous one. That made back/clear on an empty buffer look like the bot
    hung — the message text didn't change and the edit silently failed.

    We append an invisible zero-width-space counter — invisible on screen, but
    the bytes differ, so the edit always goes through.
    """
    global _edit_counter
    _edit_counter = (_edit_counter + 1) % 8
    suffix = "​" * (_edit_counter + 1)  # 1-8 ZWSP, cyclic

    # text may be the first positional arg or the 'text' kwarg
    if args:
        new_args = (args[0] + suffix,) + args[1:]
        try:
            await q.edit_message_text(*new_args, **kwargs)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
    elif "text" in kwargs:
        new_kwargs = dict(kwargs)
        new_kwargs["text"] = kwargs["text"] + suffix
        try:
            await q.edit_message_text(**new_kwargs)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
    else:
        try:
            await q.edit_message_text(*args, **kwargs)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise


async def _handle_pin_tap(q, action: str, key: str) -> None:
    """Handles a digit/back/clear tap on the PIN keypad."""
    uid = q.from_user.id

    # Locked out check (for auth flow)
    if action == "auth":
        locked, remaining = is_locked_out()
        if locked:
            await q.answer()
            await _safe_edit(q, text=f"⛔ Locked out. {remaining // 60} min left.")
            return

    buf_before = _pin_buffers.get(uid, "")
    buf = buf_before

    # ✕ (clear) — if empty, closes the menu. If digits present, erases all.
    if key == "clear":
        if buf_before == "":
            _pin_buffers.pop(uid, None)
            _setup_buffers.pop(uid, None)
            _pending_after_auth.pop(uid, None)
            await q.answer("menu closed")
            await _safe_edit(q, text="❌ Entry cancelled.")
            return
        buf = ""
    elif key == "back":
        buf = buf[:-1]
    elif key.isdigit() and len(buf) < PIN_LENGTH:
        buf += key
    _pin_buffers[uid] = buf

    # If buf didn't change (back on empty, digit on full PIN) — no-op with a toast.
    if buf == buf_before:
        if key == "back":
            await q.answer("already empty", show_alert=False)
        elif key.isdigit():
            await q.answer(f"already {PIN_LENGTH} digits", show_alert=False)
        else:
            await q.answer()
        return

    # Default ack for all code paths below (edit message)
    await q.answer()

    # Setup flow stage 1: collect the first PIN
    if action == "setup1":
        # Check state: if no longer "first", this is a stale menu from an old message
        if _setup_buffers.get(uid, {}).get("stage") != "first":
            await _safe_edit(q, "ℹ️ This menu is stale. Start again via /setpin")
            return
        if len(buf) >= PIN_LENGTH:
            _setup_buffers[uid] = {"stage": "confirm", "first_pin": buf}
            _pin_buffers[uid] = ""
            await _safe_edit(q, 
                f"🔁 Confirm the PIN again:\n\n<code>{_pin_mask(0)}</code>",
                reply_markup=_make_pin_keypad("setup2"),
                parse_mode=ParseMode.HTML,
            )
            return
        await _safe_edit(q, 
            f"🔐 Set a PIN ({PIN_LENGTH} digits):\n\n<code>{_pin_mask(len(buf))}</code>",
            reply_markup=_make_pin_keypad("setup1"),
            parse_mode=ParseMode.HTML,
        )
        return

    # Setup flow stage 2: confirmation
    if action == "setup2":
        # Check setup state is "confirm" (i.e. the first PIN was entered)
        if _setup_buffers.get(uid, {}).get("stage") != "confirm":
            await _safe_edit(q, "ℹ️ This menu is stale. Start again via /setpin")
            return
        if len(buf) >= PIN_LENGTH:
            first = _setup_buffers.get(uid, {}).get("first_pin", "")
            if buf == first:
                set_pin(buf)
                _pin_buffers.pop(uid, None)
                _setup_buffers.pop(uid, None)
                await _safe_edit(q, 
                    "✅ PIN set. Session active for 30 min from the last message."
                )
            else:
                _pin_buffers[uid] = ""
                _setup_buffers.pop(uid, None)
                await _safe_edit(q, 
                    "❌ PINs didn't match. Start again via /setpin"
                )
            return
        await _safe_edit(q, 
            f"🔁 Confirm the PIN:\n\n<code>{_pin_mask(len(buf))}</code>",
            reply_markup=_make_pin_keypad("setup2"),
            parse_mode=ParseMode.HTML,
        )
        return

    # Change PIN flow stage 0: verify current before changing
    if action == "changepin":
        # Check we're in the "verify_current" stage (launched via /setpin)
        if _setup_buffers.get(uid, {}).get("stage") != "verify_current":
            await _safe_edit(q, "ℹ️ This menu is stale. Start again via /setpin")
            return
        if len(buf) >= PIN_LENGTH:
            if verify_pin(buf):
                # OK — move to the first stage of setting a new one
                reset_failures()
                _pin_buffers[uid] = ""
                _setup_buffers[uid] = {"stage": "first"}
                await _safe_edit(q, 
                    "✅ Current PIN correct.\n\n"
                    f"🔐 Set a new PIN ({PIN_LENGTH} digits):\n\n<code>{_pin_mask(0)}</code>",
                    reply_markup=_make_pin_keypad("setup1"),
                    parse_mode=ParseMode.HTML,
                )
            else:
                _pin_buffers[uid] = ""
                fc, locked = record_failure()
                if locked:
                    await _safe_edit(q, 
                        f"⛔ Locked out for {LOCKOUT_DURATION // 60} min ({MAX_FAILURES} wrong)."
                    )
                else:
                    await _safe_edit(q, 
                        f"❌ Wrong PIN ({fc}/{MAX_FAILURES}). PIN change cancelled.\n\n"
                        "Try again via /setpin",
                    )
            return
        await _safe_edit(q, 
            f"🔑 Enter current PIN:\n\n<code>{_pin_mask(len(buf))}</code>",
            reply_markup=_make_pin_keypad("changepin"),
            parse_mode=ParseMode.HTML,
        )
        return

    # Auth flow: unlock
    if action == "auth":
        if len(buf) >= PIN_LENGTH:
            if verify_pin(buf):
                reset_failures()
                touch_activity()
                _pin_buffers.pop(uid, None)
                # If there's a pending message — process it now
                pending = _pending_after_auth.pop(uid, None)
                if pending and time.time() - pending["ts"] < 10 * 60:
                    await _safe_edit(q, "✅ Unlocked. Processing your previous message…")
                    try:
                        try:
                            await handle_message(pending["update"], pending["context"])
                        except ClaudeFailed as e:   # no queue here: the human must see the failure
                            await _inq_notify(context.bot, pending["update"].effective_chat.id, str(e))
                    except Exception as e:
                        log.exception("re-handle after auth failed: %s", e)
                else:
                    _pending_after_auth.pop(uid, None)
                    await _safe_edit(q, "✅ Unlocked. Go ahead.")
            else:
                _pin_buffers[uid] = ""
                fc, locked = record_failure()
                if locked:
                    _pending_after_auth.pop(uid, None)
                    await _safe_edit(q,
                        f"⛔ Locked out for {LOCKOUT_DURATION // 60} min ({MAX_FAILURES} wrong)."
                    )
                else:
                    await _safe_edit(q,
                        f"❌ Wrong PIN ({fc}/{MAX_FAILURES}). Try again:\n\n<code>{_pin_mask(0)}</code>",
                        reply_markup=_make_pin_keypad("auth"),
                        parse_mode=ParseMode.HTML,
                    )
            return
        await _safe_edit(q,
            f"🔒 Enter PIN:\n\n<code>{_pin_mask(len(buf))}</code>",
            reply_markup=_make_pin_keypad("auth"),
            parse_mode=ParseMode.HTML,
        )


async def on_callback(update: Update, context):
    q = update.callback_query
    if q.from_user.id not in ALLOWED:
        await q.answer()
        return
    if not q.data or ":" not in q.data:
        await q.answer()
        return

    if q.data.startswith("topic:") and SWARM_ON:
        if not is_unlocked():
            await q.answer("🔒 Unlock with the PIN first"); return
        agent = q.data.split(":", 1)[1]
        th = await _topic_for(context.bot, agent) if agent in _agent_names() else None
        await q.answer()
        await q.message.reply_text(f"👉 {agent}: {_topic_link(th)}" if th else "❌ The topic was not created.")
        return

    # PIN callbacks: format "pin:<action>:<key>" — the handler calls q.answer itself
    # (with an optional toast for no-op cases), to avoid duplicating.
    if q.data.startswith("pin:"):
        _, action, key = q.data.split(":", 2)
        await _handle_pin_tap(q, action, key)
        return

    # for non-pin callbacks (revert, set_model, etc.) — ack here
    await q.answer()

    # Revert callback: format "revert:<commit_hash>"
    if q.data.startswith("revert:"):
        if not is_unlocked():
            await _safe_edit(q, "🔒 Session locked — revert not allowed.")
            return
        commit = q.data.split(":", 1)[1]
        proc = await asyncio.create_subprocess_exec(
            "git", "revert", "--no-edit", commit,
            cwd=CLAUDE_CWD,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            await _safe_edit(q, 
                f"✅ Revert <code>{commit}</code> succeeded. Files restored.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await _safe_edit(q, 
                f"❌ Revert failed:\n<pre>{html.escape(stderr.decode()[:500])}</pre>",
                parse_mode=ParseMode.HTML,
            )
        return

    kind, value = q.data.split(":", 1)
    s = load_settings()
    if kind == "set_model" and value in MODELS:
        s["model"] = value
        # If current effort is incompatible with the new model — auto-fallback to medium
        available = MODEL_EFFORTS.get(value, EFFORTS)
        if s["effort"] not in available:
            old_effort = s["effort"]
            s["effort"] = "medium"
            save_settings(s)
            await _safe_edit(q, 
                f"✅ Model: <b>{value}</b>\n"
                f"⚠ Effort changed from <code>{old_effort}</code> to <code>medium</code> "
                f"(not supported on {value})",
                parse_mode=ParseMode.HTML,
            )
        else:
            save_settings(s)
            await _safe_edit(q, 
                f"✅ Model: <b>{value}</b>",
                parse_mode=ParseMode.HTML,
            )
    elif kind == "set_effort" and value in EFFORTS:
        # Check compatibility with the current model
        available = MODEL_EFFORTS.get(s["model"], EFFORTS)
        if value not in available:
            await _safe_edit(q, 
                f"❌ Effort <code>{value}</code> not supported on model <b>{s['model']}</b>",
                parse_mode=ParseMode.HTML,
            )
            return
        s["effort"] = value
        save_settings(s)
        await _safe_edit(q, 
            f"✅ Effort: <b>{value}</b>",
            parse_mode=ParseMode.HTML,
        )


async def cmd_setpin(update: Update, context):
    uid = update.effective_user.id
    if uid not in ALLOWED:
        return
    # If a PIN is already set — ALWAYS require the current one, regardless of unlocked state.
    # Changing the PIN is a privileged, sudo-style operation.
    if pin_is_set():
        locked, remaining = is_locked_out()
        if locked:
            await update.message.reply_text(
                f"⛔ Locked out for {remaining // 60} min after wrong PINs. /setpin unavailable.",
            )
            return
        _pin_buffers[uid] = ""
        _setup_buffers[uid] = {"stage": "verify_current"}
        await update.message.reply_text(
            "🔑 Enter the current PIN to change it:\n\n"
            f"<code>{_pin_mask(0)}</code>",
            reply_markup=_make_pin_keypad("changepin"),
            parse_mode=ParseMode.HTML,
        )
        return
    # First-time setup — no PIN yet, allow without verification.
    _pin_buffers[uid] = ""
    _setup_buffers[uid] = {"stage": "first"}
    await update.message.reply_text(
        "🔐 Set a PIN ({} digits):\n\n<code>{}</code>".format(PIN_LENGTH, _pin_mask(0)),
        reply_markup=_make_pin_keypad("setup1"),
        parse_mode=ParseMode.HTML,
    )


async def cmd_usage(update: Update, context):
    uid = update.effective_user.id
    if uid not in ALLOWED:
        return
    if not await _require_unlock_for_cmd(update):
        return
    # CLI /usage doesn't show the real quota via --print. Instead we do a
    # minimal "ping" dial (Haiku, low effort, 1-token prompt) and pull the
    # rate_limit_event from the JSON response — the real status is there.
    await update.message.reply_text("⏳ checking quota…")
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", ".",
        "--model", "haiku",
        "--effort", "low",
        "--output-format", "json",
        "--exclude-dynamic-system-prompt-sections",
        "--setting-sources", "user",
        "--settings", MOBILE_SETTINGS,
        cwd=CLAUDE_CWD,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=child_env(CLAUDE_CODE_ENTRYPOINT="claude-vscode", CLAUDE_MOBILE_BOT="1"),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        await update.message.reply_text("⏱ quota check timeout")
        return
    try:
        data = json.loads(stdout.decode())
    except json.JSONDecodeError:
        await update.message.reply_text(f"❌ couldn't parse: {stderr.decode()[:300]}")
        return

    rate_event = None
    total_cost = None
    if isinstance(data, list):
        for ev in data:
            if isinstance(ev, dict):
                if ev.get("type") == "rate_limit_event":
                    rate_event = ev.get("rate_limit_info", {})
                if ev.get("type") == "result":
                    total_cost = ev.get("total_cost_usd")
    elif isinstance(data, dict):
        rate_event = data.get("rate_limit_info")
        total_cost = data.get("total_cost_usd")

    if not rate_event:
        await update.message.reply_text("ℹ️ no rate_limit_event returned. Subscription active, no exact %.")
        return

    status = rate_event.get("status", "?")
    resets_at = rate_event.get("resetsAt", 0)
    rl_type = rate_event.get("rateLimitType", "?")
    overage_status = rate_event.get("overageStatus", "?")
    reset_str = "?"
    if resets_at:
        reset_str = time.strftime("%H:%M %d.%m", time.localtime(resets_at))

    cost_line = f"\n• Reference cost of this check dial: <code>${total_cost:.4f}</code>" if total_cost else ""

    await update.message.reply_text(
        f"📊 <b>Anthropic quota</b>\n\n"
        f"• Status: <code>{status}</code>\n"
        f"• Window type: <code>{rl_type}</code>\n"
        f"• Reset: <code>{reset_str}</code>\n"
        f"• Overage: <code>{overage_status}</code>"
        f"{cost_line}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_loc(update: Update, context):
    uid = update.effective_user.id
    if uid not in ALLOWED:
        return
    if not await _require_unlock_for_cmd(update):
        return
    stored = _get_user_location(uid)
    if not stored:
        await update.message.reply_text(
            "🚫 No location saved. Share via 📎 → Location."
        )
        return
    age_min = int((time.time() - stored["ts"]) / 60)
    remaining_min = int((LOCATION_TTL - (time.time() - stored["ts"])) / 60)
    lat, lng = stored["lat"], stored["lng"]
    await update.message.reply_text(
        f"📍 Saved location: {lat:.5f}, {lng:.5f}\n"
        f"   Saved {age_min} min ago. {remaining_min} min left.\n"
        f"   🗺 https://www.google.com/maps?q={lat},{lng}\n\n"
        "Commands: /clearloc — forget"
    )


async def cmd_clearloc(update: Update, context):
    uid = update.effective_user.id
    if uid not in ALLOWED:
        return
    if not await _require_unlock_for_cmd(update):
        return
    if _clear_user_location(uid):
        await update.message.reply_text("🗑 Location forgotten.")
    else:
        await update.message.reply_text("ℹ️ There was no location anyway.")


async def cmd_lock(update: Update, context):
    uid = update.effective_user.id
    if uid not in ALLOWED:
        return
    if not pin_is_set():
        await update.message.reply_text("No PIN set — nothing to lock. /setpin")
        return
    # Force lock: clear last_unlock
    auth = load_auth()
    auth["last_unlock"] = 0
    save_auth(auth)
    await update.message.reply_text("🔒 Locked. The next message will require a PIN.")


async def cmd_unlimit(update: Update, context):
    """Temporarily lift the rate limit. PIN-protected (requires unlock).
    Arg: duration in minutes (default 30, max 120)."""
    uid = update.effective_user.id
    if uid not in ALLOWED:
        return
    if not await _require_unlock_for_cmd(update):
        return
    minutes = 30
    if context.args and context.args[0].isdigit():
        minutes = max(1, min(120, int(context.args[0])))
    _rate_bypass[uid] = time.time() + minutes * 60
    until = time.strftime("%H:%M", time.localtime(_rate_bypass[uid]))
    await update.message.reply_text(
        f"🚀 Rate limit lifted for <b>{minutes} min</b> (until {until}). "
        "Watch your subscription quota.\n\n"
        "Cancel earlier: /relimit",
        parse_mode=ParseMode.HTML,
    )


async def cmd_relimit(update: Update, context):
    """Restore the rate limit early."""
    uid = update.effective_user.id
    if uid not in ALLOWED:
        return
    if not await _require_unlock_for_cmd(update):
        return
    _rate_bypass.pop(uid, None)
    await update.message.reply_text("🔒 Rate limit restored.")


async def cmd_revert(update: Update, context):
    """Show the last 5 mobile-bot changes with revert buttons."""
    uid = update.effective_user.id
    if uid not in ALLOWED:
        return
    if not await _require_unlock_for_cmd(update):
        return
    proc = await asyncio.create_subprocess_exec(
        "git", "log", "--oneline", "--grep=mobile-bot", "-n", "5",
        cwd=CLAUDE_CWD,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    lines = [l for l in stdout.decode().strip().split("\n") if l]
    if not lines:
        await update.message.reply_text("ℹ️ No mobile-bot changes recorded yet.")
        return
    # Inline keyboard with revert options
    rows = []
    for line in lines:
        hash_part = line.split()[0]
        # short: hash + first ~40 chars of the message
        label = (line[:60] + "…") if len(line) > 60 else line
        rows.append([InlineKeyboardButton(f"↩ {label}", callback_data=f"revert:{hash_part}")])
    await update.message.reply_text(
        "<b>Recent mobile-bot changes.</b> Tap the one to undo:",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode=ParseMode.HTML,
    )


async def cmd_start(update: Update, context):
    if update.effective_user.id not in ALLOWED:
        await update.message.reply_text(f"🚫 not authorized. your id: {update.effective_user.id}")
        return
    await update.message.reply_text(
        "👋 mobile-bot ready.\n\n"
        "Just write what you need — I'll relay it to Claude on the VM.\n\n"
        "Commands:\n"
        "/session — show the current session\n"
        "/reset — reset the session (start fresh)\n"
        "/whoami — your tg id"
    )


# ── Letters to agents from the phone ──────────────────────────────────────────────────────────────
# There: /to <agent> <text>, or a reply to "📨 from <agent>" -> the root helper -> a letter in the inbox.
# Back: an agent calls scripts/tg_reply.sh <agent> -> a JSON file in TG_OUTBOX -> _outbox_loop sends it to the
# human and remembers message_id -> agent, so a reply goes to the same agent. An agent without an open tab
# reads it later - that is shown honestly ("asleep"); background twins are not started.
OUTBOX_NAME_RE = re.compile(r"^\d+_\d+\.json$")


def _agent_names() -> list[str]:
    names = []
    if not AGENTS_DIR.is_dir():
        return names
    for d in sorted(AGENTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith(("_", ".")):   # _deprecated/ is an archive, not an addressee
            continue
        if (d / "inbox.md").is_file():
            names.append(d.name)
        for sub in sorted(d.iterdir()):
            if sub.is_dir() and not sub.name.startswith(("_", ".")) and (sub / "inbox.md").is_file():
                names.append(sub.name)
    return names


def _resolve_agent(q: str) -> tuple[str | None, list[str]]:
    """A name typed on the phone -> the exact folder name. Case-insensitive, with/without "-agent", unique prefix."""
    names = _agent_names()
    norm = lambda x: re.sub(r"[-_ ]?agent$", "", x.lower())
    ql = q.lower()
    for test in (lambda n: n == q, lambda n: n.lower() == ql, lambda n: norm(n) == norm(q)):
        hit = [n for n in names if test(n)]
        if len(hit) == 1:
            return hit[0], []
    hit = [n for n in names if n.lower().startswith(ql)] or [n for n in names if ql in n.lower()]
    if len(hit) == 1:
        return hit[0], []
    return None, hit[:12]


def _map_load() -> dict:
    try:
        return json.loads(AGENT_MSG_MAP.read_text())
    except (OSError, ValueError):
        return {}


def _map_add(pairs: list[tuple[str, str]]) -> None:
    """pairs: ("<chat_id>:<message_id>", agent) - message_id is unique only within a chat."""
    m = _map_load()
    for key, agent in pairs:
        m[key] = agent
    if len(m) > 2000:
        m = dict(list(m.items())[-2000:])   # dict keeps insertion order -> keep the fresh ones
    tmp = AGENT_MSG_MAP.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False))
    os.replace(tmp, AGENT_MSG_MAP)


async def _deliver_to_agent(agent: str, text: str) -> str:
    """A letter into the agent's inbox. -> a report line for the human (HTML)."""
    proc = await asyncio.create_subprocess_exec(
        *INBOX_CMD, agent,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(text.encode()), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        log.warning("to-agent %s: timeout 30s", agent)
        return f"⏱ {html.escape(agent)}: the inbox did not answer within 30 s - the letter may not have arrived, send it again."
    out = out.decode(errors="replace").strip()
    if proc.returncode != 0:
        log.warning("to-agent %s rc=%s: %s", agent, proc.returncode, out[:300])
        return f"❌ {html.escape(agent)}: not delivered - {html.escape(out[-300:] or 'rc=' + str(proc.returncode))}"
    log.info("to-agent %s: delivered (%d chars)", agent, len(text))
    a = f"<b>{html.escape(agent)}</b>"
    if "DEFERRED" in out:
        return f"🟡 {a}: the letter is in the delivery queue (the inbox was busy), it will arrive by itself."
    wake = next((l for l in out.splitlines() if l.startswith("WAKE:")), "")   # the tab state comes from the waker, not a guess
    if "waking" in wake:
        return f"⏰ {a}: letter delivered. The tab was dozing - woken up, it will read it within a minute."
    if "no live tab" in wake:
        return f"📭 {a}: letter delivered, but there is no live tab - open it on the computer."
    if "busy" in wake:
        return f"✅ {a}: letter delivered, the tab is working right now - it will see it mid-turn."
    if "off" in wake:
        return f"✅ {a}: letter delivered (tabs are not woken automatically - it is read on the agent's next turn)."
    if "failed" in wake:
        return f"⚠️ {a}: letter delivered, but the waker failed - open the tab or /wake {html.escape(agent)}."
    return f"✅ {a} got the letter - the answer will come here."


WAKE_RE = re.compile(r"(?:/wake(?:@\w+)?|wake)\s+(.+)", re.I | re.S)


async def _wake_word(update: Update, text: str | None = None) -> bool:
    """"wake <agent>" / /wake <agent> - wake the agent's open tab. True = handled."""
    raw = (text if text is not None else update.message.text or "").strip()
    m = WAKE_RE.fullmatch(raw)
    if not m:
        if re.fullmatch(r"/wake(@\w+)?", raw):
            await _reply_after_effect(update.message, "Whom to wake? /wake <agent> (or just \"wake\" in the agent's topic).")
            return True
        return False
    name, body = _split_agent_text("/wake " + m.group(1).strip())   # "wake Bid-HQ, look at B3" -> Bid-HQ + text
    name = name.rstrip(",.:;!")
    explicit = raw.lower().startswith("/wake")
    # Free-form "wake ..." only with the exact name: "wake me at 7" must not become a letter to an agent
    agent = _resolve_exact(name) or (_resolve_agent(name)[0] if explicit and len(name) >= 3 else None)
    if not agent:
        if explicit:
            _, cands = _resolve_agent(name)
            await _reply_after_effect(update.message, f"❓ \"{name}\" - " + (("similar: " + ", ".join(cands)) if cands else "no such agent."))
            return True
        return False   # "wake me at 7" is not an agent: let it go as a normal message
    if body.strip():   # an errand in the same phrase - as a letter; the letter wakes the tab itself
        await _reply_after_effect(update.message, await _deliver_to_agent(agent, body.strip()), parse_mode=ParseMode.HTML)
        return True
    proc = await asyncio.create_subprocess_exec(*INBOX_CMD, "--wake", agent,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill(); out = b"timeout"
    out = out.decode(errors="replace").strip()
    texts = {"waking": f"⏰ {agent}: woken up, it will start in a minute.",
             "busy": f"✅ {agent} is working anyway.",
             "listening": f"✅ {agent} is listening to the inbox anyway.",
             "no live tab": f"📭 No live tab of {agent} - open it on the computer.",
             "off": f"ℹ️ Waking tabs is switched off on this install (setup-mobile-bot.sh --with-wake)."}
    reply = next((v for k, v in texts.items() if k in out), f"❌ {agent}: {out[-300:]}")
    log.info("wake %s: %s", agent, out[:120])
    await _reply_after_effect(update.message, reply)
    return True


async def cmd_to(update: Update, context):
    if update.effective_user.id not in ALLOWED or not SWARM_ON:
        return
    if not await _require_unlock_for_cmd(update):
        return
    name, body = _split_agent_text(update.message.text or "")
    parts = ["/to"] + [x for x in (name, body) if x]
    if len(parts) == 1 and _group_id():
        await _agents_buttons(update, context)
        return
    if len(parts) < 3:
        await update.message.reply_text(
            "A letter to an agent: <code>/to Agent text</code>\n"
            "The name is the agent's folder (case and \"-agent\" may be left out).\n"
            "The answer comes here; reply to it - and it goes to the same agent again (text or voice).",
            parse_mode=ParseMode.HTML)
        return
    agent, cands = _resolve_agent(parts[1])
    if not agent:
        tail = ("Similar: " + ", ".join(cands)) if cands else "No such agent."
        await update.message.reply_text(f"❓ \"{parts[1]}\" - {tail}")
        return
    m = await _reply_after_effect(update.message, await _deliver_to_agent(agent, parts[2]), parse_mode=ParseMode.HTML)
    if m:
        _map_add([(f"{m.chat_id}:{m.message_id}", agent)])   # a reply to the confirmation also goes to this agent


# "B2 yes" / "Proj B2 yes" - clear a project blocker (the blockers.py register). B is Latin.
_YES = "yes|так" if "uk" in _conf("CCM_LANG_EXTRA") else "yes"   # the Ukrainian "так" only with CCM_LANG_EXTRA=uk
BLOCKER_RE = re.compile(r"(?:([A-Za-z0-9-]{1,32})\s+)?[Bb](\d{1,4})\s+(?:" + _YES + r")[.!]?", re.I)


async def _blocker_word(update: Update) -> bool:
    """The clear-a-blocker command. True = handled. The reply is whatever the command printed."""
    m = BLOCKER_RE.fullmatch((update.message.text or "").strip())
    if not m:
        return False
    # A word before the number counts only if it is a real project (case-insensitive): "Option B2 yes" is a normal message.
    project = BLOCKER_PROJECT
    if m.group(1):
        pat = _conf("CCM_PROJECTS_GLOB", "Project-*")
        base = pathlib.Path(_conf("CCM_WORKSPACE", str(CLAUDE_CWD)))
        prefix = pat.split("*")[0]
        known = {d.name[len(prefix):].lower(): d.name[len(prefix):] for d in base.glob(pat) if d.is_dir()}
        project = known.get(m.group(1).lower().removeprefix(prefix.lower()))
        if not project:
            return False
    if not project:
        return False
    proc = await asyncio.create_subprocess_exec(
        *BLOCKER_CMD, project, f"B{int(m.group(2))}",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        await _reply_after_effect(update.message, "⏱ The command did not answer within 60 s - check whether the blocker is cleared.")
        return True
    text = out.decode(errors="replace").strip() or f"rc={proc.returncode}"
    log.info("blocker %s B%s: rc=%s", project, m.group(2), proc.returncode)
    await _reply_after_effect(update.message, text[-3500:])
    return True


async def _letter_from(msg, context, agent: str) -> str | None:
    """A message of the human -> the text of a letter to the agent: voice is transcribed, a photo/document goes
    to TG_MEDIA with its path in the letter. None = not passed on (the human was told why)."""
    text = msg.text or msg.caption or ""
    if msg.voice or msg.audio:
        await context.bot.send_chat_action(msg.chat_id, ChatAction.RECORD_VOICE)
        text = (await _transcribe_voice(msg, context) or "").strip()
        if text:
            text = "🎙 (voice, transcript) " + text
    # Photo/document: into TG_MEDIA, the path in the letter - the agent opens the file itself ("look at this screenshot").
    media = None
    if msg.photo:
        media = await _download_photo(msg, context)
    elif msg.document and (pathlib.Path(msg.document.file_name or "").suffix.lower() in
                           {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
                           or (msg.document.mime_type or "").lower().startswith("image/")):
        # A screenshot "without compression" arrives as a document - also an image (as in handle_message).
        if msg.document.file_size and msg.document.file_size > MAX_DOC_SIZE:
            await msg.reply_text(f"❌ The image is larger than {MAX_DOC_SIZE // 1024 // 1024} MB.")
            return None
        ext = pathlib.Path(msg.document.file_name or "").suffix.lower() or ".img"
        media = UPLOAD_DIR / f"{int(time.time()*1000)}_{pysecrets.token_hex(4)}{ext}"
        await (await context.bot.get_file(msg.document.file_id)).download_to_drive(str(media))
    elif msg.document:
        media = await _download_document(msg, context)
        if media is None:
            await msg.reply_text("❌ Document not accepted. Allowed: " + ", ".join(sorted(ALLOWED_DOC_EXT)) +
                                 f" or a photo (up to {MAX_DOC_SIZE // 1024 // 1024} MB).")
            return None
    elif msg.video or msg.animation or msg.video_note or msg.sticker:
        await msg.reply_text(f"To {agent} I pass text, voice, a photo or a document - not video or stickers.")
        return None
    if media:
        TG_MEDIA.mkdir(parents=True, exist_ok=True)
        TG_MEDIA.chmod(0o755)
        dst = TG_MEDIA / media.name
        await asyncio.to_thread(shutil.move, str(media), str(dst))
        dst.chmod(0o644)
        text = f"{text}\n📎 file from {HUMAN}: {dst}".strip()
    if not text.strip():
        await msg.reply_text(f"To {agent} I pass only text, voice, a photo or a document.")
        return None
    return text


# ── A group with one topic per agent ──────────────────────────────────────────────────────────────
# A topic = a chat with an agent: write in a topic -> a letter to its inbox; the agent's answer (tg_reply.sh)
# -> the same topic. The bot creates the topic at the first letter/answer, or the human creates a topic named
# after the agent. The group file lives in its own folder: in the queue folder any *.json would be taken by
# the worker for a letter (it once ate group.json).

def _group_id() -> int | None:
    try:
        return int(json.loads(GROUP_FILE.read_text())["chat_id"])
    except (OSError, ValueError, KeyError):
        return None


def _topics() -> dict:
    try:
        return json.loads(TOPICS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _topics_save(t: dict) -> None:
    TOPICS_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = TOPICS_FILE.with_name(".topics.tmp")
    tmp.write_text(json.dumps(t, ensure_ascii=False))
    os.replace(tmp, TOPICS_FILE)


_topics_lock = asyncio.Lock()   # the outbox and the group handlers create topics in parallel


async def _topic_for(bot, agent: str) -> int | None:
    """The agent's topic in the group; none - create it. No group / failed -> None (then the private chat is used)."""
    gid = _group_id()
    if gid is None:
        return None
    async with _topics_lock:
        if agent in (t := _topics()):
            return t[agent]
        try:
            topic = await bot.create_forum_topic(gid, agent[:128])
        except TelegramError as e:
            log.warning("topic for %s was not created: %s", agent, e)
            return None
        t = _topics()
        t[agent] = topic.message_thread_id
        _topics_save(t)
        return topic.message_thread_id


async def _topic_set(agent: str, thread: int | None) -> None:
    async with _topics_lock:
        t = _topics()
        if thread is None:
            t.pop(agent, None)
        else:
            t[agent] = thread
        _topics_save(t)


def _resolve_exact(name: str) -> str | None:
    """A topic name -> an agent only exactly (case and "-agent" do not matter): a topic "Ideas" must not stick to a random one."""
    norm = lambda x: re.sub(r"[-_ ]?agent$", "", x.strip().lower())
    hit = [n for n in _agent_names() if norm(n) == norm(name)]
    return hit[0] if len(hit) == 1 else None


def _split_agent_text(text: str) -> tuple[str, str]:
    """"/to Gear Picker look" -> ("Gear Picker", "look"): names with a space - by an exact match on 3-2 words."""
    exact = {n.lower(): n for n in _agent_names()}
    for k in (3, 2):
        p = text.split(None, k + 1)
        if len(p) >= k + 1 and " ".join(p[1:k + 1]).lower() in exact:
            return exact[" ".join(p[1:k + 1]).lower()], (p[k + 1] if len(p) == k + 2 else "")
    p = text.split(None, 2)
    return (p[1] if len(p) > 1 else ""), (p[2] if len(p) > 2 else "")


def _topic_link(thread: int) -> str:
    return f"https://t.me/c/{str(_group_id())[4:]}/{thread}"


async def _group_update(update: Update, context) -> None:
    """Everything from the group comes here, not into the Claude chat. Strangers are ignored silently."""
    msg, user = update.message, update.effective_user
    if not msg or not user or user.id not in ALLOWED:
        return
    if not is_unlocked():
        await _reply_after_effect(msg, "🔒 The bot is locked by the PIN - unlock it in the private chat with the bot.")
        return
    allowed, why = _check_rate_limit(user.id)   # the limit is shared with the private chat
    if not allowed:
        await _reply_after_effect(msg, why, parse_mode=ParseMode.HTML)
        return
    thread = msg.message_thread_id if msg.is_topic_message else None
    if msg.forum_topic_created:      # the human created a topic named after an agent
        agent = _resolve_exact(msg.forum_topic_created.name)
        if agent:
            await _topic_set(agent, thread)   # a second topic of the same agent - this one is now the current
            await _reply_after_effect(msg, f"✅ The topic is bound to {agent}. Write - the letter goes to its inbox.")
        else:
            _, cands = _resolve_agent(msg.forum_topic_created.name)
            await _reply_after_effect(msg, f"❓ The topic is not bound: there is exactly no agent \"{msg.forum_topic_created.name}\". Similar: {', '.join(cands) or '-'}")
        return
    t = _topics()
    if msg.forum_topic_edited or msg.forum_topic_closed or msg.forum_topic_reopened or not (msg.text or msg.caption or msg.photo or msg.document or msg.voice or msg.audio or msg.video or msg.sticker or msg.animation or msg.video_note):
        return
    agent = next((a for a, th in t.items() if th == thread), None) if thread else None
    raw = (msg.text or "").strip()
    if agent and re.fullmatch(r"(/wake(@\w+)?|wake)", raw, re.I):   # in an agent's topic the name is optional
        raw = f"wake {agent}"
    if WAKE_RE.fullmatch(raw) and await _wake_word(update, raw):
        return
    if agent:
        text = await _letter_from(msg, context, agent)
        if text is not None:
            await _reply_after_effect(msg, await _deliver_to_agent(agent, text), parse_mode=ParseMode.HTML)
        return
    # The general topic: /to Agent text or /new Agent - open a topic
    cmd = (msg.text or "").split(None, 1)[0].split("@")[0] if msg.text else ""
    name, body = _split_agent_text(msg.text or "")
    if cmd in ("/to", "/new") and name:
        agent, cands = _resolve_agent(name)
        if not agent:
            await _reply_after_effect(msg, f"❓ \"{name}\" - " + (("similar: " + ", ".join(cands)) if cands else "no such agent."))
            return
        th = await _topic_for(context.bot, agent)
        if th is None:
            await _reply_after_effect(msg, "❌ The topic was not created - does the bot have the \"Manage topics\" right?")
            return
        if cmd == "/to" and body:
            r = await _deliver_to_agent(agent, body)
            try:
                await context.bot.send_message(_group_id(), f"✉️ {html.escape(body[:300])}\n\n{r}", message_thread_id=th, parse_mode=ParseMode.HTML)
            except TelegramError as e:
                log.warning("group: the copy of the letter did not reach the topic: %s", e)
        await _reply_after_effect(msg, f"👉 Topic {agent}: {_topic_link(th)}")
        return
    await _reply_after_effect(msg, "This is the general topic. Write in an agent's topic or: /new <agent> - open a topic.")


async def _agents_buttons(update: Update, context) -> None:
    """/to without a name in the private chat - the agents as buttons: those with a topic already come first."""
    t = _topics()
    names = sorted(_agent_names(), key=lambda n: (n not in t, n.lower()))
    rows, row = [], []
    for n in names[:96]:
        btn = (InlineKeyboardButton(n, url=_topic_link(t[n])) if n in t and _group_id()
               else InlineKeyboardButton(n, callback_data=f"topic:{n}"[:64]))
        row.append(btn)
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    await update.message.reply_text("Whom to write to? A button opens the agent's topic in the group.", reply_markup=InlineKeyboardMarkup(rows))


async def _reply_to_agent(update: Update, context) -> bool:
    """A reply to an agent's message -> a letter to it. True = handled (do not go further)."""
    msg = update.message
    rt = msg.reply_to_message
    if not rt:
        return False
    agent = _map_load().get(f"{update.effective_chat.id}:{rt.message_id}")
    if not agent:
        return False
    text = await _letter_from(msg, context, agent)
    if text is None:
        return True
    m = await _reply_after_effect(msg, await _deliver_to_agent(agent, text), parse_mode=ParseMode.HTML)
    if m:
        _map_add([(f"{m.chat_id}:{m.message_id}", agent)])
    return True


def _transient(e: Exception) -> bool:
    """A temporary Telegram failure (network/timeout/flood) - retry. In PTB BadRequest is a subclass of
    NetworkError, so it is cut off explicitly: "chat not found" or broken HTML is not cured by a retry."""
    return isinstance(e, RetryAfter) or (isinstance(e, NetworkError) and not isinstance(e, BadRequest))


async def _outbox_flush(bot) -> None:
    for sub in ("sent", "bad"):
        (TG_OUTBOX / sub).mkdir(parents=True, exist_ok=True)   # without the folder os.replace fails -> the letter is sent again every tick
    for f in sorted(TG_OUTBOX.iterdir()):
        if not OUTBOX_NAME_RE.match(f.name):
            continue
        try:
            item = json.loads(f.read_text())
            agent, text = str(item["agent"]), str(item["text"])
        except (OSError, ValueError, KeyError) as e:
            log.warning("outbox: broken %s (%s) -> bad/", f.name, e)
            os.replace(f, TG_OUTBOX / "bad" / f.name)
            continue
        own = bool(item.get("self"))   # the bot's own reply that did not arrive in time: a reply to it is not for an agent
        head = "📨 <b>a reply that did not arrive earlier</b>\n\n" if own else f"📨 <b>from {html.escape(agent)}</b>\n\n"
        chunks = md_chunks(text)
        if not chunks:   # no visible text (tg_reply.sh and Python see "blank" differently) - not "sent"
            log.warning("outbox: %s - a letter without visible text -> bad/", f.name)
            os.replace(f, TG_OUTBOX / "bad" / f.name)
            continue
        # Progress lives in the file itself ("done" = how many pieces have gone): a network failure in the
        # middle of a long letter does not send it again from the first piece.
        done = set(item.get("done") or [])   # {"<uid>:<piece>"} - not a position: survives a change of ALLOWED
        sent = []
        thread = None if own or item.get("private") else await _topic_for(bot, agent)
        targets = [_group_id()] if thread else sorted(ALLOWED)   # the agent has a topic - there, else the private chat
        topic_dead = False
        if thread:
            head = ""
        try:
            for uid in targets:
                for i, chunk in enumerate(chunks):
                    if f"{uid}:{i}" in done:
                        continue
                    try:
                        try:
                            m = await bot.send_message(uid, (head if i == 0 else "") + md_to_tg_html(chunk),
                                                       parse_mode=ParseMode.HTML, disable_web_page_preview=True,
                                                       message_thread_id=thread)
                        except BadRequest as e:
                            log.warning("outbox HTML parse failed (%s) - plain", e)
                            m = await bot.send_message(uid, (f"📨 from {agent}\n\n" if head and i == 0 else "") + chunk,
                                                       message_thread_id=thread)
                        if not own:
                            sent.append((f"{uid}:{m.message_id}", agent))
                    except TelegramError as e:
                        if _transient(e):
                            raise             # temporary -> save the progress, retry in 5 s
                        if thread:            # the topic was deleted / the bot removed from the group: do not lose the reply
                            topic_dead = True
                            break
                        # permanent (Forbidden, chat not found...) - skip the piece, do not hold the queue
                        log.warning("outbox: %s -> uid=%s piece %d rejected for good (%s), skipping",
                                    agent, uid, i, e)
                    done.add(f"{uid}:{i}")
        except TelegramError:   # only a temporary failure gets here (_transient)
            _map_add(sent)
            item["done"] = sorted(done)
            tmp = f.with_name("." + f.name + ".tmp")
            tmp.write_text(json.dumps(item, ensure_ascii=False))
            os.replace(tmp, f)
            raise
        if topic_dead:
            log.warning("outbox: topic of %s is dead - removing it, the letter goes again (a new topic or the private chat)", agent)
            async with _topics_lock:     # erase only the topic that failed: the human may have bound a new one already
                t = _topics()
                if t.get(agent) == thread:
                    t.pop(agent); _topics_save(t)
            item["topic_fail"] = item.get("topic_fail", 0) + 1
            item["private"] = item["topic_fail"] >= 2
            item["done"] = []
            tmp = f.with_name("." + f.name + ".tmp")
            tmp.write_text(json.dumps(item, ensure_ascii=False)); os.replace(tmp, f)
            continue
        _map_add(sent)
        os.replace(f, TG_OUTBOX / "sent" / f.name)
        log.info("outbox: %s -> Telegram (%s)", agent, "own reply" if own else f"{len(sent)} msg")


async def _outbox_loop(app: Application) -> None:
    while True:
        pause = 5
        try:
            await _outbox_flush(app.bot)
        except RetryAfter as e:   # a flood limit on the whole bot: retrying before retry_after only extends the ban
            pause = max(5, _retry_seconds(e))
            log.warning("outbox: Telegram flood limit, waiting %.0f s", pause)
        except Exception:
            log.exception("outbox flush failed - retry in 5 s")
        await asyncio.sleep(pause)


# ── Inbound queue on disk ─────────────────────────────────────────────────────────────────────────
# Why messages used to be lost: the 3-per-30-s limit DROPPED a message (a batch of forwarded items), and the PTB
# queue lived in memory while drop_pending_updates threw everything away on every restart. Now: an update goes
# to disk at once -> one worker handles them strictly one by one -> the file is removed only after success. The
# limit holds a message back, it does not drop it. A crash between handling and the acknowledgement to Telegram
# does not duplicate: done/ remembers the update_id.
INQ_MAX = 200                    # a ceiling: a taken-over account cannot fill the disk; the quota is held by the worker's limit
INQ_ATTEMPTS = 3
INQ_BACKOFF = (60, 300)          # pause before the 2nd and 3rd attempts, s
INQ_DONE_DAYS = 7
_inq_wake = asyncio.Event()
_inq_rate_told = False


def _inq_write(path: pathlib.Path, item: dict) -> None:
    tmp = path.with_name("." + path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # the human's texts - owner only
    with os.fdopen(fd, "w") as f:
        json.dump(item, f, ensure_ascii=False)
    os.replace(tmp, path)


def _inq_pending() -> list[pathlib.Path]:
    return sorted(p for p in TG_INQ.glob("*.json") if re.fullmatch(r"\d+\.json", p.name))


def _inq_init() -> None:
    (TG_INQ / "done").mkdir(parents=True, exist_ok=True)
    (TG_INQ / "bad").mkdir(exist_ok=True)
    TG_INQ.chmod(0o700)
    cutoff = time.time() - INQ_DONE_DAYS * 86400   # only at start: the bot restarts often enough
    for p in (TG_INQ / "done").iterdir():
        if p.stat().st_mtime < cutoff:
            p.unlink()   # an empty marker created by this same code


async def enqueue_message(update: Update, context):
    """The entry: cut off strangers, put the rest on disk. No work here: an update must not be lost."""
    user = update.effective_user
    if update.message is None:      # an edited /to: CommandHandler lets those through too
        return
    if getattr(getattr(update, "effective_chat", None), "type", "private") != "private":
        return   # the group is handled by _drop_stale/_group_update
    if user.id not in ALLOWED:
        log.warning("unauthorized: id=%s name=%s", user.id, user.full_name)
        await update.message.reply_text(f"🚫 not authorized. your id: {user.id}")
        return
    name = f"{update.update_id:012d}.json"
    path = TG_INQ / name
    if path.exists() or (TG_INQ / "done" / name).exists() or (TG_INQ / "bad" / name).exists():
        log.info("inq: repeated update %s - skipping", update.update_id)
        return
    if len(_inq_pending()) >= INQ_MAX:
        await update.message.reply_text(f"⛔ The queue already holds {INQ_MAX} messages - this one was not accepted, send it later.")
        return
    try:
        _inq_write(path, {"update": update.to_dict(), "attempts": 0})
    except OSError as e:
        log.exception("inq: could not write %s", name)
        await update.message.reply_text(f"⛔ The message was not accepted, send it again: disk ({e.strerror}).")
        return
    _inq_wake.set()
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    except TelegramError:
        pass


async def _inq_notify(bot, chat_id, text: str) -> None:
    try:
        try:
            await bot.send_message(chat_id, md_to_tg_html(text), parse_mode=ParseMode.HTML)
        except BadRequest:
            await bot.send_message(chat_id, text)
    except TelegramError as e:
        log.warning("inq: could not tell the human (%s)", e)


async def _inq_wait_rate(bot, uid: int, chat_id: int) -> None:
    """The limit (quota protection from a taken-over account) holds the queue back. The human is told once per wait."""
    global _inq_rate_told
    while True:
        allowed, _ = _check_rate_limit(uid)
        if allowed:
            return
        if not _inq_rate_told:
            _inq_rate_told = True    # once per batch: the worker resets it when the queue is empty
            await _inq_notify(bot, chat_id, f"⏳ Message limit: the queue ({len(_inq_pending())}) will continue by itself, nothing is lost. /unlimit lifts it.")
        await asyncio.sleep(5)


async def _inq_process_one(app: Application, path: pathlib.Path) -> None:
    item = json.loads(path.read_text())
    update = Update.de_json(item["update"], app.bot)
    uid, chat_id = update.effective_user.id, update.effective_chat.id
    preview = (update.message.text or update.message.caption or "media")[:80] if update.message else "?"
    if not item["attempts"]:     # a retry of the same letter is not counted by the limit a second time
        await _inq_wait_rate(app.bot, uid, chat_id)
    global _inq_retry
    _inq_retry = item["attempts"] > 0 or item.get("kills", 0) > 0 or item.get("interrupted", False)
    item["attempts"] += 1
    _inq_write(path, item)       # before handling: a crash in the middle counts too, or a poisonous letter loops forever
    context = CallbackContext.from_update(update, app)
    try:
        try:
            await handle_message(update, context)
        finally:
            _inq_retry = False
    except asyncio.CancelledError:
        item["attempts"] -= 1    # a normal stop of the bot is not the letter's fault
        item["interrupted"] = True   # but Claude may already have done something
        _inq_write(path, item)
        raise
    except ClaudeKilled as e:
        item["kills"] = item.get("kills", 0) + 1
        if item["kills"] <= 5:   # beyond that it is no longer a restart but something systematic - the normal attempt count
            item["attempts"] -= 1
            _inq_write(path, item)
            log.warning("inq: Claude was killed by a signal, the letter stays (%s)", path.name)
            await asyncio.sleep(5)
            return
        await _inq_notify(app.bot, chat_id, f"{e}")
        os.replace(path, TG_INQ / "bad" / path.name)
        return
    except Exception as e:
        log.exception("inq: %s attempt %d/%d", path.name, item["attempts"], INQ_ATTEMPTS)
        why = str(e) if isinstance(e, ClaudeFailed) else "internal bot error"
        if item["attempts"] >= INQ_ATTEMPTS:
            os.replace(path, TG_INQ / "bad" / path.name)
            await _inq_notify(app.bot, chat_id, f"❌ Not handled after {INQ_ATTEMPTS} attempts, send it again: \"{preview}\"\n{why}")
        else:
            pause = INQ_BACKOFF[min(item["attempts"], len(INQ_BACKOFF)) - 1]
            if item["attempts"] == 1:
                await _inq_notify(app.bot, chat_id, f"{why}\n\n🔁 The message is queued, I will retry by myself in {pause // 60} min.")
            await asyncio.sleep(pause)
        return
    (TG_INQ / "done" / path.name).touch()
    path.unlink()
    try:   # after "done": a failure or a stop of the rotation does not repeat a reply already given
        await maybe_rotate_session()   # right after the reply: the cache is still warm
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("rotate: failure, keeping the session")


async def _inq_worker(app: Application) -> None:
    while True:
        pending = _inq_pending()
        if not pending:
            global _inq_rate_told
            _inq_rate_told = False
            _inq_wake.clear()
            try:
                await asyncio.wait_for(_inq_wake.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass
            continue
        try:
            await _inq_process_one(app, pending[0])
        except asyncio.CancelledError:
            raise
        except OSError:       # disk/permissions: the letter is intact, not in bad/; retry later
            log.exception("inq: disk error on %s, retry in 30 s", pending[0].name)
            await asyncio.sleep(30)
        except Exception:     # a broken queue file: into bad/, so it does not stop the rest
            log.exception("inq: could not read %s -> bad/", pending[0].name)
            try:
                os.replace(pending[0], TG_INQ / "bad" / pending[0].name)
            except OSError:      # the worker must not die silently while the entry still accepts letters
                log.exception("inq: could not move %s away", pending[0].name)
                await asyncio.sleep(30)


_BOT_START = time.time()


async def _drop_stale(update: Update, context) -> None:
    """After downtime Telegram delivers old things too. Messages go to the queue, but commands (a /reset from
    three hours ago) and buttons do not - except /to and /wake: those are letters, they must arrive."""
    ch = getattr(update, "effective_chat", None)
    if ch and ch.type != "private":   # the agents' group: remember it whatever update came
        log.info("group: update %s from chat %s (%s, type %s, topics=%s)", update.update_id, ch.id, ch.title, ch.type, ch.is_forum)
        if SWARM_ON:
            u = getattr(update, "effective_user", None)
            mcm = getattr(update, "my_chat_member", None)   # the bot was added: counts only if the human added it
            if ((u and u.id in ALLOWED) or (mcm and mcm.from_user.id in ALLOWED)) and _group_id() in (None, ch.id):
                GROUP_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                GROUP_FILE.write_text(json.dumps({"chat_id": ch.id, "title": ch.title, "is_forum": ch.is_forum}, ensure_ascii=False))
            if ch.id == _group_id() and getattr(update, "message", None):
                try:
                    await _group_update(update, context)
                except Exception:
                    log.exception("group: handling failed")
                    await _reply_after_effect(update.message, "❌ Not handled - send it again.")
        raise ApplicationHandlerStop   # the group is not the Claude chat
    m = update.message
    stale = lambda d: d and time.time() - d.timestamp() > 600
    q = update.callback_query
    # A button has no press time, so only one that arrived right after the start counts as old
    if q and q.message and stale(q.message.date) and time.time() - _BOT_START < 15:
        log.info("old button dropped: %s", q.data)
        await q.answer("Pressed before the bot restarted - open the menu again")
        raise ApplicationHandlerStop
    is_cmd = m and m.entities and m.entities[0].type == "bot_command" and m.entities[0].offset == 0
    if is_cmd and not re.match(r"/(to|wake)(@\w+)?(\s|$)", m.text) and stale(m.date):
        log.info("old command dropped: %s", m.text[:30])
        raise ApplicationHandlerStop


async def post_stop(app: Application) -> None:
    for key in ("inq_task", "outbox_task"):
        task = app.bot_data.get(key)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def post_init(app: Application) -> None:
    """Register commands in the Telegram UI (shown in the '/' menu)."""
    try:
        TG_OUTBOX.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("outbox %s is not usable (%s): replies that fail to send will not be kept", TG_OUTBOX, e)
    app.bot_data["outbox_task"] = asyncio.create_task(_outbox_loop(app))
    _inq_init()
    app.bot_data["inq_task"] = asyncio.create_task(_inq_worker(app))
    swarm_cmds = [
        BotCommand("to", "letter to an agent: /to Agent text"),
        BotCommand("wake", "wake an agent's tab: /wake Agent"),
    ] if SWARM_ON else []
    await app.bot.set_my_commands(swarm_cmds + [
        BotCommand("model", "choose model (opus/sonnet/haiku)"),
        BotCommand("effort", "effort level (low -> max)"),
        BotCommand("settings", "current settings"),
        BotCommand("usage", "current subscription quota %"),
        BotCommand("revert", "undo the last file change"),
        BotCommand("unlimit", "temporarily lift rate limit (N min)"),
        BotCommand("relimit", "restore rate limit"),
        BotCommand("loc", "show saved location"),
        BotCommand("clearloc", "forget saved location"),
        BotCommand("session", "current mobile session"),
        BotCommand("reset", "reset session"),
        BotCommand("setpin", "set/change PIN"),
        BotCommand("lock", "lock now"),
        BotCommand("whoami", "your Telegram id"),
    ])
    log.info("bot commands registered")


def main():
    if not TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set")
    if not ALLOWED:
        # An empty allowlist = a bot open to anyone. Not acceptable (the PIN is optional) -> do not start.
        log.error("ALLOWED_TG_USERS is empty - refusing to start (fail-closed)")
        raise SystemExit(1)
    log.info("starting bot, allowed users: %s, pin_required=%s, swarm=%s", ALLOWED, pin_required(), SWARM_ON)
    app = Application.builder().token(TOKEN).post_init(post_init).post_stop(post_stop).build()
    app.add_handler(TypeHandler(Update, _drop_stale), group=-1)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("session", cmd_session))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("effort", cmd_effort))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("setpin", cmd_setpin))
    app.add_handler(CommandHandler("lock", cmd_lock))
    app.add_handler(CommandHandler("usage", cmd_usage))
    app.add_handler(CommandHandler("revert", cmd_revert))
    app.add_handler(CommandHandler("unlimit", cmd_unlimit))
    app.add_handler(CommandHandler("relimit", cmd_relimit))
    app.add_handler(CommandHandler("loc", cmd_loc))
    app.add_handler(CommandHandler("clearloc", cmd_clearloc))
    if SWARM_ON:
        app.add_handler(CommandHandler("wake", enqueue_message))   # like /to: through the queue, then _wake_word
        app.add_handler(CommandHandler("to", enqueue_message))     # a letter also goes through the queue: not lost, does not block commands
    app.add_handler(CallbackQueryHandler(on_callback))
    # Catch text, photos, documents, voice, audio, gif/animation, forwarded, location
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Document.ALL |
         filters.VOICE | filters.AUDIO | filters.ANIMATION |
         filters.FORWARDED | filters.LOCATION)
        & ~filters.COMMAND & filters.UpdateType.MESSAGE,   # an edit is not a new message
        enqueue_message,
    ))
    app.run_polling(drop_pending_updates=False)   # the bot was down: the messages still arrive (Telegram keeps them 24 h)


if __name__ == "__main__":
    main()
