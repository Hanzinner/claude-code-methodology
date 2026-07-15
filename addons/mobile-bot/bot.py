#!/usr/bin/env python3
"""mobile-bot — Telegram bridge to Claude Code on a VM.

Architecture:
- The bot keeps one persistent session (sid stored in session.txt)
- Each message from a whitelisted user -> claude -p --resume <sid>
- The reply is sent back to Telegram
- Memory + skills + tools are available (Claude runs in the project dir)
"""
import os, json, re, html, time, hmac, hashlib, secrets as pysecrets, asyncio, logging, pathlib
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from telegram.error import BadRequest

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("mobile-bot")

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED = {int(x) for x in os.environ.get("ALLOWED_TG_USERS","").split(",") if x.strip()}
# Directory Claude runs in — the project root you want reachable from your phone.
CLAUDE_CWD = os.environ.get("CLAUDE_BOT_CWD") or os.getcwd()
# Bot's own state (session id + settings). Override with MOBILE_BOT_STATE_DIR.
_STATE_DIR = pathlib.Path(os.environ.get("MOBILE_BOT_STATE_DIR") or os.path.join(CLAUDE_CWD, ".claude", "mobile-bot"))
_STATE_DIR.mkdir(parents=True, exist_ok=True)
SESSION_FILE = _STATE_DIR / "session.txt"
SETTINGS_FILE = _STATE_DIR / "settings.json"
# Path to the OSM nearby-search helper (ships with this addon).
OSM_SCRIPT = os.environ.get("OSM_NEARBY_SCRIPT") or os.path.expanduser("~/.claude/scripts/osm-nearby.sh")
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

AUTH_FILE = pathlib.Path(os.environ.get("MOBILE_BOT_AUTH_FILE") or os.path.expanduser("~/.claude/secrets/mobile-bot-auth.json"))
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


def is_unlocked() -> bool:
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
        # url needs no escaping in href, but quote is mandatory
        return f'<a href="{html.escape(url, quote=True)}">{link_text}</a>'
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


async def run_claude(prompt: str) -> tuple[str, str | None]:
    """Runs claude -p, returns (reply text, new session_id)."""
    sid = load_sid()
    # Constrained mode: only safe tools plus a read-only Bash allowlist.
    # If someone hijacks Telegram, the most they can do is read, not run commands.
    settings = load_settings()
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--exclude-dynamic-system-prompt-sections",
        "--permission-mode", "acceptEdits",
        # Edit/Write are restricted (to .md under the project) via a hook.
        # Bash — allowlist of read-only utils. Destructive (rm/dd/chmod/chown/mv) is not listed.
        "--allowedTools",
        "Read", "Grep", "Glob", "WebFetch", "WebSearch", "Edit", "Write",
        "Bash(ls:*)", "Bash(find:*)", "Bash(grep:*)", "Bash(cat:*)",
        "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(sort:*)", "Bash(uniq:*)",
        "Bash(du:*)", "Bash(df:*)", "Bash(stat:*)", "Bash(file:*)",
        "Bash(which:*)", "Bash(echo:*)", "Bash(tree:*)", "Bash(awk:*)", "Bash(sed:*)",
        "Bash(date:*)", "Bash(pwd)", "Bash(whoami)",
        "Bash(git log:*)", "Bash(git status)", "Bash(git diff:*)", "Bash(git show:*)",
        "Bash(jq:*)", "Bash(rg:*)", "Bash(fd:*)",
        # OSM Overpass nearby search — for location-based queries
        f"Bash({OSM_SCRIPT}:*)",
        "--disallowedTools", "NotebookEdit", "Task",
        "--model", settings["model"],
        "--effort", settings["effort"],
    ]
    if sid:
        cmd += ["--resume", sid]

    log.info("calling claude (sid=%s model=%s effort=%s)",
             sid[:8] if sid else "new", settings["model"], settings["effort"])
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=CLAUDE_CWD,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            **os.environ,
            "CLAUDE_CODE_ENTRYPOINT": "claude-vscode",
            "CLAUDE_MOBILE_BOT": "1",  # activates the restriction hooks
        },
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        return ("⏱ timeout — claude did not respond within 5 min", None)

    if proc.returncode != 0:
        log.error("claude rc=%s stderr=%s", proc.returncode, stderr.decode()[:500])
        return (f"❌ claude crashed (rc={proc.returncode})\n{stderr.decode()[:500]}", None)

    try:
        data = json.loads(stdout.decode())
    except json.JSONDecodeError as e:
        return (f"❌ couldn't parse JSON: {e}\nraw: {stdout.decode()[:500]}", None)

    # JSON comes as a single object or a list of events — handle both
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

    if new_sid and new_sid != sid:
        save_sid(new_sid)
        log.info("session updated: %s", new_sid[:8])

    return (result_text or "(empty reply)", new_sid)


async def _require_pin_or_prompt(update: Update, context=None) -> bool:
    """Returns True if authorized, else shows PIN prompt and returns False.
    If context is passed — stores the pending message to retry after unlock."""
    uid = update.effective_user.id
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


UPLOAD_DIR = pathlib.Path("/tmp/mobile-bot-uploads")
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


async def handle_message(update: Update, context):
    user = update.effective_user
    if ALLOWED and user.id not in ALLOWED:
        log.warning("unauthorized: id=%s name=%s", user.id, user.full_name)
        await update.message.reply_text(f"🚫 not authorized. your id: {user.id}")
        return

    if not await _require_pin_or_prompt(update, context):
        return

    # Rate limit (guards against an attacker draining the quota)
    allowed, reason = _check_rate_limit(user.id)
    if not allowed:
        await update.message.reply_text(reason, parse_mode=ParseMode.HTML)
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

    animation_frames = []
    if msg.animation:
        await context.bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
        anim_path = await _download_animation(msg, context)
        if anim_path:
            animation_frames = await _extract_animation_frames(anim_path)

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
                return

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
        if not str(p).startswith(str(SEND_ROOT)):
            log.warning("SEND skipped (outside root): %s", p)
            continue
        if "/secrets/" in str(p) or "credentials" in p.name.lower() or "/.git/" in str(p):
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

    # Convert markdown to Telegram HTML
    formatted = md_to_tg_html(reply)

    # Telegram limit 4096 — split into chunks. HTML tags are short, so errors are rare.
    chunks = [formatted[i:i + MAX_TG_MSG] for i in range(0, len(formatted), MAX_TG_MSG)]
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except BadRequest as e:
            log.warning("HTML parse failed (%s) — fallback to plain text", e)
            raw = reply[chunks.index(chunk) * MAX_TG_MSG : (chunks.index(chunk) + 1) * MAX_TG_MSG]
            await update.message.reply_text(raw)

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
                        await handle_message(pending["update"], pending["context"])
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
        cwd=CLAUDE_CWD,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "claude-vscode"},
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


async def post_init(app: Application) -> None:
    """Register commands in the Telegram UI (shown in the '/' menu)."""
    await app.bot.set_my_commands([
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
    log.info("starting bot, allowed users: %s", ALLOWED)
    app = Application.builder().token(TOKEN).post_init(post_init).build()
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
    app.add_handler(CallbackQueryHandler(on_callback))
    # Catch text, photos, documents, voice, audio, gif/animation, forwarded, location
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Document.ALL |
         filters.VOICE | filters.AUDIO | filters.ANIMATION |
         filters.FORWARDED | filters.LOCATION)
        & ~filters.COMMAND,
        handle_message,
    ))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
