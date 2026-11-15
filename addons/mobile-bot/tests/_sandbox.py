"""Shared sandbox of the mobile-bot tests: everything in a temp dir, no network, no real Telegram, nothing outside it.
Import it BEFORE `bot`. MOBILE_BOT_DIR (env) points the tests at another copy of the bot folder (default: this repo's)."""
import os, pathlib, sys, tempfile

D = pathlib.Path(os.path.realpath(tempfile.mkdtemp(prefix="mobile-bot-test-")))
BOT_DIR = pathlib.Path(os.environ.get("MOBILE_BOT_DIR") or pathlib.Path(__file__).resolve().parent.parent)
AGENTS = D / "Agents"
for name in ("Alpha", "Beta-agent", "Gear Picker"):
    (AGENTS / name).mkdir(parents=True); (AGENTS / name / "inbox.md").write_text("## New\n")
os.environ.update(
    HOME=str(D / "home"), CLAUDE_METHODOLOGY_CONF="/nonexistent", CCM_SECRETS_DIR=str(D / "secrets"),
    CLAUDE_BOT_CWD=str(D / "work"), MOBILE_BOT_STATE_DIR=str(D / "state"), MOBILE_BOT_UPLOAD_DIR=str(D / "up"),
    MOBILE_BOT_AGENTS_DIR=str(AGENTS), MOBILE_BOT_SWARM="1", CCM_TG_OUTBOX=str(D / "outbox"),
    MOBILE_BOT_HANDOFF_DIR=str(D / "handoff"), MOBILE_BOT_SESSIONS_DIR=str(D / "sessions"),
    TELEGRAM_BOT_TOKEN="1:x", ALLOWED_TG_USERS="42", MOBILE_BOT_SUDO="", MOBILE_BOT_BLOCKER_PROJECT="Demo",
    HOME_TEST="1")
for sub in ("home", "work", "sessions", "outbox"):
    (D / sub).mkdir(exist_ok=True)
sys.path.insert(0, str(BOT_DIR))
import logging
logging.disable(logging.CRITICAL)
