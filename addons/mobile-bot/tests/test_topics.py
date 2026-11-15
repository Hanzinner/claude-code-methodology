#!/usr/bin/env python3
"""Agent topics + agent replies test: a stand-in Telegram, temp spools. Never touches a real group/outbox/inbox.
Last line: `mobile-bot topics: N pass, M fail`."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sandbox as sb
import bot
from telegram import Update
from telegram.ext import ApplicationHandlerStop
from types import SimpleNamespace as NS
d = sb.D
bot.SETTINGS_FILE.write_text(json.dumps({"require_pin": False}))   # the PIN has its own case below
bot._check_rate_limit = lambda uid: (True, "")   # the limit has its own case
bot.TG_OUTBOX.mkdir(parents=True, exist_ok=True)
G = -1004375918529; bot.GROUP_FILE.parent.mkdir(parents=True, exist_ok=True); bot.GROUP_FILE.write_text(json.dumps({"chat_id": G}))
app = bot.Application.builder().token("1:AAtest").build()
letters, sent, created, replies = [], [], [], []
async def deliver(a, t): letters.append((a, t)); return "ok"
bot._deliver_to_agent = deliver
async def reply_after(msg, text, **k): replies.append(text); return None
bot._reply_after_effect = reply_after
class Bot:
    async def create_forum_topic(self, chat, name): created.append(name); return NS(message_thread_id=100 + len(created))
    async def send_message(self, chat, text, **k): sent.append((chat, k.get("message_thread_id"), text)); return NS(message_id=7, chat_id=chat)
fake = Bot(); ctx = NS(bot=fake)
res = []
def ok(n, c): res.append(bool(c)); print("PASS" if c else "FAIL", n)
def gmsg(uid=42, text="hello", thread=None, extra=None, chat=G):
    m = {"message_id": 5, "date": 1790000000, "chat": {"id": chat, "type": "supergroup", "is_forum": True}, "from": {"id": uid, "is_bot": False, "first_name": "H"}, "text": text}
    if thread: m.update(message_thread_id=thread, is_topic_message=True)
    m.update(extra or {})
    return Update.de_json({"update_id": 1, "message": m}, app.bot)
async def route(u):
    try: await bot._drop_stale(u, ctx); return False
    except ApplicationHandlerStop: return True
OUT = bot.TG_OUTBOX
async def main():
    ok("the group does not go into the Claude chat", await route(gmsg()))
    ok("the general topic: a hint, no letter", not letters and "general topic" in replies[-1])
    await route(gmsg(text="/new alpha"))
    ok("/new creates the agent's topic", created == ["Alpha"] and bot._topics() == {"Alpha": 101})
    await route(gmsg(text="look at the offer", thread=101))
    ok("a letter in a topic -> this agent's inbox", letters[-1] == ("Alpha", "look at the offer"))
    await route(gmsg(text="", thread=None, extra={"text": None, "forum_topic_created": {"name": "beta", "icon_color": 1}, "message_thread_id": 300, "is_topic_message": True}))
    ok("a topic created by the human with an agent's name is bound", bot._topics().get("Beta-agent") == 300)
    await route(gmsg(text="/to Alpha test", thread=None))
    ok("/to in the general topic: topic + letter", letters[-1] == ("Alpha", "test") and bot._topics().get("Alpha") == 101)
    n = len(letters); await route(gmsg(uid=111, text="break in", thread=101))
    ok("a stranger in the group is ignored", len(letters) == n)
    ok("another group does not overwrite ours", await route(gmsg(chat=-100999, text="x")) and bot._group_id() == G)
    (OUT / "1_1.json").write_text(json.dumps({"agent": "Alpha", "text": "here is the answer"}))
    await bot._outbox_flush(fake)
    ok("the agent's answer went into its topic", sent[-1][0] == G and sent[-1][1] == 101 and "here is the answer" in sent[-1][2])
    (OUT / "2_2.json").write_text(json.dumps({"agent": "New-topic", "text": "first"}))
    await bot._outbox_flush(fake)
    ok("an agent without a topic: the topic is created, the answer goes there", "New-topic" in created and sent[-1][1] == bot._topics()["New-topic"])
    (OUT / "3_3.json").write_text(json.dumps({"self": True, "agent": "bot", "text": "own"}))
    await bot._outbox_flush(fake)
    ok("the bot's own reply goes to the private chat, not the group", sent[-1][0] == 42 and sent[-1][1] is None)
    bot.GROUP_FILE.unlink(); (OUT / "4_4.json").write_text(json.dumps({"agent": "Alpha", "text": "no group"}))
    await bot._outbox_flush(fake)
    ok("no group: the answer goes to the private chat with a header", sent[-1][0] == 42 and "from Alpha" in sent[-1][2])
    bot.GROUP_FILE.write_text(json.dumps({"chat_id": G}))
    ok("the queue does not take group.json/topics.json for letters", not bot._inq_pending())
    bot.GROUP_FILE.unlink()
    stranger = Update.de_json({"update_id": 9, "my_chat_member": {"chat": {"id": -100777, "type": "supergroup", "is_forum": True}, "from": {"id": 111, "is_bot": False, "first_name": "X"}, "date": 1790000000,
        "old_chat_member": {"user": {"id": 1, "is_bot": True, "first_name": "b"}, "status": "left"}, "new_chat_member": {"user": {"id": 1, "is_bot": True, "first_name": "b"}, "status": "member"}}}, app.bot)
    await route(stranger)
    ok("a stranger's group does not become ours", bot._group_id() is None)
    bot.GROUP_FILE.write_text(json.dumps({"chat_id": G}))
    import telegram.error as te
    class DeadBot(Bot):
        async def send_message(self, chat, text, **k):
            if k.get("message_thread_id") == 101: raise te.BadRequest("Message thread not found")
            return await super().send_message(chat, text, **k)
    db = DeadBot(); await bot._topic_set("Alpha", 101)
    (OUT / "5_5.json").write_text(json.dumps({"agent": "Alpha", "text": "do not get lost"}))
    await bot._outbox_flush(db)
    ok("a dead topic: the letter is not in sent, the topic is removed", (OUT / "5_5.json").exists() and bot._topics().get("Alpha") != 101)
    await bot._outbox_flush(db)
    ok("the next attempt arrived (a new topic)", not (OUT / "5_5.json").exists() and "do not get lost" in sent[-1][2])
    class SlowBot(Bot):
        async def create_forum_topic(self, chat, name):
            await asyncio.sleep(0.05); return await super().create_forum_topic(chat, name)
    sb_ = SlowBot(); before = len(created)
    await asyncio.gather(bot._topic_for(sb_, "A1"), bot._topic_for(sb_, "B1"), bot._topic_for(sb_, "A1"))
    tp = bot._topics(); ok("parallel topics: both saved, no duplicate", "A1" in tp and "B1" in tp and len(created) - before == 2)
    await route(gmsg(text="/to Gear Picker look at the laptop"))
    ok("/to \"Gear Picker\" (a name with a space) in the group - the text is whole", letters[-1] == ("Gear Picker", "look at the laptop"))
    await route(gmsg(text="", extra={"text": None, "forum_topic_created": {"name": "Id", "icon_color": 1}, "message_thread_id": 400, "is_topic_message": True}))
    ok("an inexact topic name is not bound", 400 not in bot._topics().values())
    real_rl = bot._check_rate_limit; bot._check_rate_limit = lambda uid: (False, "x"); n = len(letters)
    for _ in range(5): await route(gmsg(text="spam", thread=300))
    bot._check_rate_limit = real_rl
    ok("the limit works in the group too", len(letters) == n)
    woke = []
    async def fake_wake(update, text=None):
        m = bot.WAKE_RE.fullmatch((text or update.message.text or "").strip())
        if m: woke.append(m.group(1)); return True
        return False
    real_wake = bot._wake_word; bot._wake_word = fake_wake; n = len(letters)
    await route(gmsg(text="wake", thread=300))
    await route(gmsg(text="/wake Bid-HQ"))
    bot._wake_word = real_wake
    ok("\"wake\" in a topic = that agent, /wake in the general topic = the named one; no letter", woke == ["Beta-agent", "Bid-HQ"] and len(letters) == n)
    real = bot.is_unlocked; bot.is_unlocked = lambda: False; n = len(letters)
    await route(gmsg(text="secret", thread=300)); bot.is_unlocked = real
    ok("PIN locked: no letter goes from a topic", len(letters) == n and "PIN" in replies[-1])
    # name resolution and the blocker word
    ok("agent name: case and -agent do not matter", bot._resolve_agent("BETA")[0] == "Beta-agent" and bot._resolve_agent("alp")[0] == "Alpha")
    ok("a free-form 'wake me at 7' is not a wake of an agent", not await real_wake(NS(message=NS(text="wake me at 7")), "wake me at 7"))
    ok("blocker words: 'B2 yes' matches, the Ukrainian word only with CCM_LANG_EXTRA=uk; (a leading word is checked as a project later)", bot.BLOCKER_RE.fullmatch("B2 yes") and not bot.BLOCKER_RE.fullmatch("b12 \u0442\u0430\u043a.") and bot.BLOCKER_RE.fullmatch("Option B2 yes") is not None)
    n_ = sum(res); print(f"mobile-bot topics: {n_} pass, {len(res) - n_} fail"); sys.exit(0 if all(res) else 1)
asyncio.run(main())
