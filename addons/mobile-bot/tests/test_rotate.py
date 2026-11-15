#!/usr/bin/env python3
"""Session rotation test: a stand-in `claude` on PATH, temp folders. Never touches a real session or summary.
Last line: `mobile-bot rotate: N pass, M fail`."""
import asyncio, json, os, pathlib, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
d0 = pathlib.Path(tempfile.mkdtemp()); fake = d0 / "bin"; fake.mkdir()
(fake / "claude").write_text(f"""#!/usr/bin/env python3
import json, sys
open("{d0}/calls", "a").write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({{"result": "summary " * 60}} if "moving to a new session" in sys.argv[2] else {{"result": "ok", "session_id": "NEW"}}))
""")
(fake / "claude").chmod(0o755); os.environ["PATH"] = f"{fake}:{os.environ['PATH']}"
import _sandbox as sb
import bot
d = sb.D
bot.SESSION_FILE = d / "session.txt"; bot.SESSIONS_DIR = d; bot.HANDOFF_DIR = d / "h"; bot.HANDOFF_DIR.mkdir(); bot.HANDOFF_NEXT = bot.HANDOFF_DIR / "next.md"
res = []
def ok(n, c): res.append(bool(c)); print("PASS" if c else "FAIL", n)
def sess(sid, tokens):
    (d / f"{sid}.jsonl").write_text(json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 3, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": tokens}}}) + "\n")
def calls(): return [json.loads(x) for x in (d0 / "calls").read_text().splitlines()]
async def main():
    bot.save_sid("SMALL"); sess("SMALL", 150_000); await bot.maybe_rotate_session()
    ok("150k - left alone", bot.load_sid() == "SMALL" and not bot.HANDOFF_NEXT.exists())
    bot.save_sid("BIG"); sess("BIG", 689_000); await bot.maybe_rotate_session()
    ok("690k - a summary is written and the session closed", bot.load_sid() is None and "summary" in bot.HANDOFF_NEXT.read_text())
    ok("the archive copy is 0600", any(p.name != "next.md" and oct(p.stat().st_mode)[-3:] == "600" for p in bot.HANDOFF_DIR.iterdir()))
    ok("the summary uses the same flags as a normal call (cache)", calls()[-1][2:] == bot.claude_cmd("x", "BIG", bot.load_settings())[3:])
    r, sid = await bot.run_claude("hello")
    ok("the new session got the summary in the prompt, no --resume", "summary" in calls()[-1][1] and "--resume" not in calls()[-1] and sid == "NEW")
    ok("next.md is removed after the hand-over", not bot.HANDOFF_NEXT.exists() and bot.load_sid() == "NEW")
    bot.save_sid("BIG2"); sess("BIG2", 300_000); await bot.maybe_rotate_session(); bot.SESSION_FILE.unlink(missing_ok=True); bot.HANDOFF_NEXT.unlink(missing_ok=True)
    await bot.run_claude("clean")
    ok("/reset: a new session without the summary", "summary" not in calls()[-1][1])
    shutil.rmtree(bot.HANDOFF_DIR); bot.save_sid("BIG3"); sess("BIG3", 300_000); await bot.maybe_rotate_session()
    ok("the summaries folder is created by itself", bot.HANDOFF_NEXT.exists())
    bot.ROTATE_TOKENS = 0; bot.save_sid("BIG4"); sess("BIG4", 900_000); n = len(calls()); await bot.maybe_rotate_session()
    ok("ROTATE_TOKENS=0 switches rotation off", bot.load_sid() == "BIG4" and len(calls()) == n)
    ok("no session file -> 0 tokens (never rotates blind)", bot.session_tokens("nope") == 0)
    n_ = sum(res); print(f"mobile-bot rotate: {n_} pass, {len(res) - n_} fail"); sys.exit(0 if all(res) else 1)
asyncio.run(main())
