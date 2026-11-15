#!/usr/bin/env python3
"""Inbound queue test: real Update/Application objects, a stand-in Telegram and handle_message, a temp dir.
No network. Last line: `mobile-bot queue: N pass, M fail`."""
import asyncio, json, os, pathlib, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sandbox as sb
import bot
from telegram import Update
from types import SimpleNamespace as NS

bot.INQ_BACKOFF = (0, 0); bot._rate_log.clear()
Q = bot.TG_INQ; D = sb.D
app = bot.Application.builder().token("1:AAtest").build()
said = []
async def snd(cid, text, **k): said.append(text)
async def act(*a, **k): pass
class FakeBot:
    send_message = staticmethod(snd); send_chat_action = staticmethod(act)
fake = FakeBot()
def upd(n, text="m", uid=42, extra=None):
    m = {"message_id": n, "date": 1790000000, "chat": {"id": uid, "type": "private"}, "from": {"id": uid, "is_bot": False, "first_name": "H"}, "text": f"{text}{n}"}
    m.update(extra or {})
    return Update.de_json({"update_id": n, "message": m}, app.bot)
ctx = NS(bot=fake)
class A:      # the app for the worker: the bot is a stand-in
    bot = fake
fails = {"n": 0}
order = []
async def fake_handle(update, context):
    t = update.message.text
    if t.startswith("boom") and fails["n"] < fails.get("limit", 99):
        fails["n"] += 1
        raise bot.ClaudeFailed("network")
    order.append(t)
bot.handle_message = fake_handle
bot.CallbackContext = NS(from_update=lambda u, a: ctx)
res = []
def ok(name, c): c = bool(c); res.append(c); print(("PASS" if c else "FAIL"), name)
async def drain():
    while bot._inq_pending():
        await bot._inq_process_one(A, bot._inq_pending()[0])
async def stale_btn(d):
    import telegram.ext as te
    async def ans(*a): pass
    try:
        await bot._drop_stale(NS(message=None, callback_query=NS(data="revert:a", answer=ans, message=NS(date=d))), None); return False
    except te.ApplicationHandlerStop: return True
async def main():
    bot._inq_init()
    bot._check_rate_limit = lambda uid: (True, "")
    for n in [3, 1, 2] + list(range(4, 18)):     # 17 of them, out of arrival order
        await bot.enqueue_message(upd(n), ctx)
    ok("17 fast ones - all on disk", len(bot._inq_pending()) == 17)
    await drain()
    ok("all handled in order", order == [f"m{i}" for i in range(1, 18)])
    await bot.enqueue_message(upd(5), ctx)
    ok("a repeated delivery of the same update does not duplicate", not bot._inq_pending())
    order.clear(); await bot.enqueue_message(upd(20), ctx); bot._inq_init(); await drain()
    ok("after a restart the letter is not lost", order == ["m20"])
    r = []
    async def rt(x, **k): r.append(x)
    u = NS(effective_user=NS(id=1, full_name="x"), message=NS(reply_text=rt), update_id=30)
    await bot.enqueue_message(u, ctx)
    ok("a stranger does not get into the queue", not bot._inq_pending() and "not authorized" in r[0])
    order.clear(); said.clear(); fails.update(n=0, limit=1)
    await bot.enqueue_message(upd(40, "boom"), ctx); await bot.enqueue_message(upd(41), ctx); await drain()
    ok("a temporary failure: retry, order kept", order == ["boom40", "m41"] and "retry by myself" in said[0])
    order.clear(); said.clear(); fails.update(n=0, limit=99)
    await bot.enqueue_message(upd(50, "boom"), ctx); await bot.enqueue_message(upd(51), ctx); await drain()
    ok("3 failures: into bad/, the human told, the queue goes on", (Q/"bad"/f"{50:012d}.json").exists() and order == ["m51"] and any("Not handled" in x and "boom50" in x for x in said))
    order.clear(); (Q/f"{60:012d}.json").write_text("{bad"); await bot.enqueue_message(upd(61), ctx)
    t = asyncio.create_task(bot._inq_worker(A)); await asyncio.sleep(0.3); t.cancel(); await asyncio.gather(t, return_exceptions=True)
    ok("a broken file goes to bad/, the rest passed", (Q/"bad"/f"{60:012d}.json").exists() and order == ["m61"])
    async def slow(u, c): await asyncio.sleep(10)
    bot.handle_message = slow
    await bot.enqueue_message(upd(70), ctx); p = bot._inq_pending()[0]
    t = asyncio.create_task(bot._inq_process_one(A, p)); await asyncio.sleep(0.1); t.cancel(); await asyncio.gather(t, return_exceptions=True)
    ok("a bot stop: the letter stays, the attempt is not counted", json.loads(p.read_text())["attempts"] == 0)
    bot.handle_message = fake_handle; order.clear(); await drain()
    said.clear(); seq = iter([(False, "x"), (True, "")]); bot._check_rate_limit = lambda uid: next(seq)
    sl = asyncio.sleep; bot.asyncio.sleep = lambda s: sl(0)
    order.clear(); await bot.enqueue_message(upd(80), ctx); await drain(); bot.asyncio.sleep = sl
    ok("the limit holds a message back, does not drop it", order == ["m80"] and any("Message limit" in x for x in said))
    r.clear(); bot.INQ_MAX = 1; bot._check_rate_limit = lambda uid: (True, "")
    await bot.enqueue_message(upd(90), ctx)
    m = upd(91)
    u = NS(effective_user=m.effective_user, effective_chat=m.effective_chat, message=NS(reply_text=rt), update_id=91)
    await bot.enqueue_message(u, ctx)
    ok("a full queue says so directly", any("not accepted" in x for x in r) and len(bot._inq_pending()) == 1)
    await drain(); bot.INQ_MAX = 200
    u = upd(100, extra={"reply_to_message": {"message_id": 7, "date": 1790000000, "chat": {"id": 42, "type": "private"}, "text": "t"}, "photo": [{"file_id": "F", "file_unique_id": "U", "width": 1, "height": 1}], "caption": "c"})
    back = Update.de_json(json.loads(json.dumps(u.to_dict(), ensure_ascii=False)), app.bot)
    ok("reply and photo survive the disk", back.message.reply_to_message.message_id == 7 and back.message.photo[0].file_id == "F" and back.message.caption == "c")
    from telegram.error import TimedOut
    calls = []
    async def rt2(x, **k):
        calls.append(x)
        if len(calls) == 1: raise TimedOut()
    sl2 = asyncio.sleep; bot.asyncio.sleep = lambda s: sl2(0)
    await bot._reply_chunk(NS(message=NS(reply_text=rt2)), "text")
    ok("a send failure: the piece is retried, no exception upward", len(calls) == 2)
    async def rt3(x, **k): raise TimedOut()
    await bot._reply_chunk(NS(message=NS(reply_text=rt3)), "text"); bot.asyncio.sleep = sl2
    ok("Telegram is down: the exception does not reach the queue", True)
    async def killed(u, c): raise bot.ClaudeKilled("rc143")
    bot.handle_message = killed; bot.asyncio.sleep = lambda s: sl2(0)
    await bot.enqueue_message(upd(110), ctx); p = bot._inq_pending()[0]
    await bot._inq_process_one(A, p)
    ok("TERM: the attempt is not counted", json.loads(p.read_text())["attempts"] == 0)
    for _ in range(6):
        if p.exists(): await bot._inq_process_one(A, p)
    bot.asyncio.sleep = sl2; bot.handle_message = fake_handle
    ok("TERM without end: stops in bad/", (Q/"bad"/p.name).exists())
    await bot.enqueue_message(upd(120), ctx)
    ok("queue file 0600, folder 0700", oct(bot._inq_pending()[0].stat().st_mode)[-3:] == "600" and oct(Q.stat().st_mode)[-3:] == "700")
    await drain()
    import datetime as dt, telegram.ext as te
    old_d = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)
    async def stale(txt, d):
        try:
            await bot._drop_stale(NS(message=NS(text=txt, date=d, entities=[NS(type="bot_command", offset=0)] if txt.startswith("/") else []), callback_query=None), None); return False
        except te.ApplicationHandlerStop: return True
    ok("an old /reset is dropped; /to, a fresh one and plain text are not",
       await stale("/reset", old_d) and not await stale("/to A x", old_d) and not await stale("/reset", dt.datetime.now(dt.timezone.utc)) and not await stale("text", old_d))
    ok("an old button is dropped", await stale_btn(old_d))
    async def rt4(x, **k): raise TimedOut()
    ok("a confirmation after an action does not raise", await bot._reply_after_effect(NS(reply_text=rt4), "x") is None)
    seen = []
    async def h(u, c):
        seen.append(bot._inq_retry)
        if len(seen) == 1: raise bot.ClaudeFailed("x")
    bot.handle_message = h; await bot.enqueue_message(upd(130), ctx); await drain(); bot.handle_message = fake_handle
    ok("a retry knows it is a retry", seen == [False, True])
    bot._BOT_START = 0
    ok("an old menu pressed now works", not await stale_btn(old_d))
    src = open(os.path.join(str(sb.BOT_DIR), "bot.py")).read()
    ok("the /to handler goes through the queue", 'CommandHandler("to", enqueue_message)' in src)
    TO = r"/to(@\w+)?(\s|$)"
    ok("/today is not confused with /to", not bot.re.match(TO, "/today") and bot.re.match(TO, "/to A x"))
    ed = Update.de_json({"update_id": 200, "edited_message": {"message_id": 1, "date": 1790000000, "edit_date": 1790000001, "chat": {"id": 42, "type": "private"}, "from": {"id": 42, "is_bot": False, "first_name": "H"}, "text": "/to A x"}}, app.bot)
    await bot.enqueue_message(ed, ctx)
    ok("an edited /to is not queued", not bot._inq_pending())
    O = bot.TG_OUTBOX; O.mkdir(parents=True, exist_ok=True); [x.unlink() for x in O.glob("*.json")]; bot.asyncio.sleep = lambda s: sl2(0)
    await bot._reply_chunk(NS(message=NS(reply_text=rt3)), "important reply"); bot.asyncio.sleep = sl2
    got = list(O.glob("*.json"))
    ok("Telegram is down: the reply is kept on disk", len(got) == 1 and "important" in got[0].read_text())
    sent = []
    async def fsend(uid, x, **k): sent.append(x); return NS(message_id=5)
    await bot._outbox_flush(NS(send_message=fsend))
    ok("the outbox delivers it; the reply is not bound to an agent", "important" in sent[0] and bot._map_load() == {})
    said.clear(); bot._check_rate_limit = lambda uid: (False, "x"); told = []
    async def n(b, c, t): told.append(t)
    real_n, real_s = bot._inq_notify, bot.asyncio.sleep
    bot._inq_notify = n
    calls_rl = {"n": 0}
    def rl(uid):
        calls_rl["n"] += 1
        return (calls_rl["n"] > 3, "x")
    bot._check_rate_limit = rl; bot.asyncio.sleep = lambda s: sl2(0); bot._inq_rate_told = False
    await bot._inq_wait_rate(fake, 42, 42)
    ok("the limit tells the human once per wait", len(told) == 1)
    bot._inq_notify, bot.asyncio.sleep = real_n, real_s
    n_ = sum(res); print(f"mobile-bot queue: {n_} pass, {len(res) - n_} fail"); sys.exit(0 if all(res) else 1)
asyncio.run(main())
