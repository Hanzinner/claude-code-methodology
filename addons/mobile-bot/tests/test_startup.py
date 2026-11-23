#!/usr/bin/env python3
"""Startup on a slow or flood-limited Telegram: the real bot.main() against a fake Telegram on a loopback. getMe first
times out, then answers 429, then works; setMyCommands and deleteWebhook answer 429 once. The bot must not exit, must
wait at least retry_after before the next call after a 429, and must reach getUpdates. Also the restart policy of the
systemd unit template. Last line: `mobile-bot startup: N pass, M fail`."""
import json, os, signal, subprocess, sys, threading, time, http.server
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sandbox as sb
D = sb.D
import bot
res = []
def ok(n, c): res.append(bool(c)); print("PASS" if c else "FAIL", n)

ok("timeouts fit a slow network: connect >= 10 s, read >= 60 s",
   getattr(bot, "TG_CONNECT_TIMEOUT", 0) >= 10 and getattr(bot, "TG_READ_TIMEOUT", 0) >= 60)

# what each method answers, call by call; the last entry repeats. ("slow", s) = answer only after s seconds,
# longer than the read timeout the bot gets below -> a real httpx timeout -> PTB TimedOut.
SCRIPT = {"getMe": [("slow", 2.5), ("429", 2), "ok"], "setMyCommands": [("429", 1), "ok"],
          "deleteWebhook": [("429", 1), "ok"]}
ME = {"id": 1, "is_bot": True, "first_name": "t", "username": "t_bot"}
calls, lock = [], threading.Lock()


class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        method = self.path.rsplit("/", 1)[-1]
        with lock:
            n = sum(1 for m, _ in calls if m == method)
            calls.append((method, time.monotonic()))
        steps = SCRIPT.get(method, ["ok"])
        step = steps[min(n, len(steps) - 1)]
        code, out = 200, {"ok": True, "result": ME if method == "getMe" else ([] if method == "getUpdates" else True)}
        if isinstance(step, tuple) and step[0] == "slow":
            time.sleep(step[1])
        elif isinstance(step, tuple) and step[0] == "429":
            code, out = 429, {"ok": False, "error_code": 429, "description": f"Too Many Requests: retry after {step[1]}",
                              "parameters": {"retry_after": step[1]}}
        if method == "getUpdates":
            time.sleep(0.3)   # a long poll that returns nothing; without a pause the bot would spin on it
        b = json.dumps(out).encode()
        try:
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        except OSError:   # the bot gave up on the slow answer and closed the connection
            pass

    def log_message(self, *a): pass


def times(method):
    with lock:
        return [t for m, t in calls if m == method]


if not hasattr(bot, "TG_API_URL"):
    # a copy without the hook would talk to the real api.telegram.org: do not start it
    ok("bot.py has TG_API_URL (the fake Telegram can be put in front of it)", False)
else:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    run = ("import sys; sys.path.insert(0, %r); import bot\n"
           "bot.TG_API_URL = 'http://127.0.0.1:%d/bot'\n"
           "bot.TG_CONNECT_TIMEOUT = 1; bot.TG_READ_TIMEOUT = 1; bot.STARTUP_BACKOFF = (0.5, 2)\n"
           "bot.main()\n") % (str(sb.BOT_DIR), srv.server_port)
    errlog = open(D / "bot-stderr.log", "w+")
    p = subprocess.Popen([sys.executable, "-c", run], env=dict(os.environ), stdout=errlog, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and not times("getUpdates") and p.poll() is None:
            time.sleep(0.2)
        time.sleep(0.5)
        alive = p.poll() is None
        ok("startup through timeout + 429s: the bot is still running (rc=%s)" % p.returncode, alive)
        ok("...and reached getUpdates (polling started)", bool(times("getUpdates")))
        g = times("getMe")
        ok("getMe: 3 calls (timeout, 429, ok), got %d" % len(g), len(g) == 3)
        if len(g) >= 3:
            ok("after the timeout: a pause before the next getMe, not an instant retry (%.2f s)" % (g[1] - g[0]),
               g[1] - g[0] >= 1.4)   # 1 s read timeout + 0.5 s back-off
            ok("after 429 retry_after=2: the next getMe >= 2 s later (%.2f s)" % (g[2] - g[1]), g[2] - g[1] >= 2)
        for m in ("setMyCommands", "deleteWebhook"):
            t = times(m)
            ok("%s: 429 retry_after=1 waited out (%s)" % (m, ", ".join("%.2f" % (b - a) for a, b in zip(t, t[1:]))),
               len(t) >= 2 and t[1] - t[0] >= 1)
    finally:
        if p.poll() is None:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(15)
            except subprocess.TimeoutExpired:
                p.kill(); p.wait()
        srv.shutdown()
    errlog.seek(0); log_text = errlog.read(); errlog.close()
    ok("the log says why it waits ('next try in')", "next try in" in log_text)
    if not all(res):
        print("--- bot output (tail) ---"); print(log_text[-3000:])

# A Telegram-side outage of about an hour (429s and hanging calls, the way a Bot API outage looked from a real install),
# on a fake clock: asyncio.sleep advances it instead of waiting. The startup retry must stay up the whole hour, never
# call before a 429's retry_after has passed, cap its back-off, and go on as soon as Telegram answers again.
import asyncio
from telegram.error import BadRequest, RetryAfter, TimedOut
clock = [0.0]
real_sleep = asyncio.sleep
async def fake_sleep(s, *a, **k):
    clock[0] += s
    await real_sleep(0)
OUTAGE = 3600
seen = []   # (time of the call, the earliest time it was allowed)
allowed = [0.0]
async def flaky():
    t = clock[0]; seen.append((t, allowed[0]))
    if t >= OUTAGE:
        return "ok"
    if (len(seen) // 3) % 2 == 0:              # three 429s in a row, then three hanging calls, and so on
        ra = 30 if len(seen) % 2 else 120
        allowed[0] = t + ra
        raise RetryAfter(ra)
    clock[0] += bot.TG_READ_TIMEOUT              # a call that hangs until the read timeout
    allowed[0] = clock[0]
    raise TimedOut()
async def bad():
    raise BadRequest("chat not found")
asyncio.sleep = fake_sleep
try:
    got = asyncio.run(bot._tg_retry(flaky, "outage test"))
    try:
        asyncio.run(bot._tg_retry(bad, "bad request")); bad_raised = False
    except BadRequest:
        bad_raised = True
finally:
    asyncio.sleep = real_sleep
pauses = [b[0] - a[0] for a, b in zip(seen, seen[1:])]
ok("an hour of 429s and hangs: still waiting, then resumes (%d calls, back on Telegram at %.0f s)" % (len(seen), clock[0]),
   got == "ok" and seen[-1][0] >= OUTAGE)
early = [(t, a) for t, a in seen if t < a]
ok("...never a call before a 429's retry_after has passed (%d early)" % len(early), not early)
ok("...back-off capped: no gap over %d s plus a read timeout, and few calls (%d)" % (bot.STARTUP_BACKOFF[1], len(seen)),
   max(pauses) <= bot.STARTUP_BACKOFF[1] + bot.TG_READ_TIMEOUT + 1 and len(seen) < 200)
ok("...resumes within one back-off of the recovery (%.0f s after)" % (seen[-1][0] - OUTAGE),
   seen[-1][0] - OUTAGE <= bot.STARTUP_BACKOFF[1] + bot.TG_READ_TIMEOUT + 121)
ok("a non-transient error (BadRequest) is raised at once, not waited on", bad_raised)

# the systemd unit: a crash must not restart faster than RestartSec, and the start limit sits in [Unit]
units, sec = {}, None
for line in (sb.BOT_DIR / "systemd" / "claude-mobile-bot.service.template").read_text().splitlines():
    line = line.strip()
    if line.startswith("[") and line.endswith("]"):
        sec = line[1:-1]; units.setdefault(sec, {})
    elif "=" in line and not line.startswith("#") and sec:
        k, v = line.split("=", 1); units[sec][k.strip()] = v.strip()
svc, unit = units.get("Service", {}), units.get("Unit", {})
rs = int(svc.get("RestartSec", "0") or 0)
ok("unit: RestartSec between 60 and 300 (got %s)" % rs, 60 <= rs <= 300)
ok("unit: StartLimitIntervalSec and StartLimitBurst in [Unit], not [Service]",
   "StartLimitIntervalSec" in unit and "StartLimitBurst" in unit and not {"StartLimitIntervalSec", "StartLimitBurst"} & set(svc))
if rs and "StartLimitIntervalSec" in unit and "StartLimitBurst" in unit:
    iv, burst = int(unit["StartLimitIntervalSec"]), int(unit["StartLimitBurst"])
    # restarts RestartSec apart fit iv // rs + 1 times into the interval: fewer than the burst = systemd never gives up
    # on its own restarts, the limit only stops something faster than RestartSec
    ok("unit: restarts RestartSec apart never use up the burst (%d starts per %d s < %d)" % (iv // rs + 1, iv, burst),
       iv // rs + 1 < burst)
ok("unit: Restart=on-failure kept", svc.get("Restart") == "on-failure")

n_ = sum(res); print(f"mobile-bot startup: {n_} pass, {len(res) - n_} fail"); sys.exit(0 if all(res) else 1)
