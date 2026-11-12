#!/usr/bin/env python3
"""trash-guard: growth of the trash is attributed to the session whose command made it; the shout goes only to the
culprit and only over the limit; ownerless junk -> a board line once a day; --clean deletes only what lay > N days.
Everything in a sandbox (own trash, own state, temp HOME, no config file except a generated one for the NEW keys).
Runs the repo copy; TG=<path> tests another one."""
import json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.realpath(__file__))
TG = os.environ.get("TG", os.path.join(HERE, "..", "hooks", "trash-guard.py"))
R = tempfile.mkdtemp(prefix="tg-"); TR = f"{R}/Trash"; HOME = f"{R}/home"; ST = f"{HOME}/.claude/trash-guard"; BOARD = f"{R}/board.md"
os.makedirs(TR); os.makedirs(f"{HOME}/.claude/agent-identity")
for sid, a in (("sidA", "Scraper-agent"), ("sidB", "Web-agent")):
    open(f"{HOME}/.claude/agent-identity/{sid}", "w").write(f"/x/Agents/{a}")
CONF = f"{R}/methodology.conf"          # new keys (limit, board) come from the config file; default keys from env
open(CONF, "w").write(f"CCM_TRASH_LIMIT_GB=0.002\nCCM_TRASH_BOARD={BOARD}\n")   # limit ~2 MB
ENV = {**os.environ, "HOME": HOME, "CLAUDE_METHODOLOGY_CONF": CONF, "CCM_TRASH_DIR": TR, "CCM_TRASH_DAYS": "14",
       # names the live original reads (so the same test can be pointed at it)
       "TRASH_DIR": TR, "TRASH_STATE": ST, "TRASH_BOARD": BOARD, "TRASH_LIMIT_GB": "0.002", "HANZ_TEST": "1"}
P = F = 0
def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])
def run(mode, sid=None):
    r = subprocess.run([sys.executable, TG, mode], input=json.dumps({"session_id": sid, "tool_name": "Bash"}) if sid else "",
                       capture_output=True, text=True, env=ENV)
    return r.stdout
def junk(name, kb):
    os.makedirs(f"{TR}/{name}"); open(f"{TR}/{name}/blob", "wb").write(os.urandom(kb * 1024))
def state(): return json.load(open(f"{ST}/state.json"))

junk("old.thing", 100); time.sleep(1.2)
run("--measure")
ok("measure: state written, total ~100 KB, under the limit", 90_000 < state()["total"] < 200_000 and state()["complete"], state())

# session A: a command that made 3 profiles (the mv is inside a script - the hook never sees the command text)
run("--pre", "sidA"); time.sleep(0.1)
for i in range(3): junk(f"prof.Ab{i}", 900)
out = run("--post", "sidA")
led = [json.loads(l) for l in open(f"{ST}/ledger.jsonl")]
ok("growth attributed to session A (3 names, agent from identity)", len(led) == 1 and led[0]["sid"] == "sidA" and led[0]["agent"] == "Scraper-agent"
   and sorted(led[0]["names"]) == ["prof.Ab0", "prof.Ab1", "prof.Ab2"], led)
ok("old stuff in the trash is attributed to nobody", "old.thing" not in led[0]["names"])


run("--measure")
ok("after the measure the trash is over the limit", state()["total"] > 2 * 1024 * 1024, state()["total"])

# session B put nothing in -> silence for it; session A gets a shout with size and name group
run("--pre", "sidB"); ok("another session without growth - silent", run("--post", "sidB") == "")
run("--pre", "sidA"); out = run("--post", "sidA")
ok("culprit gets a shout into the context", "additionalContext" in out and "TRASH" in out and "THIS IS YOU" in out, out)
ok("the shout has the item count and top name groups", "3 items" in out and "prof.* x3" in out, out)
run("--pre", "sidA"); ok("a repeat within 10 min - silent", run("--post", "sidA") == "")
ok("no board line yet: the culprit is known and the hour has not passed", not os.path.exists(BOARD))

# the culprit ignores it for an hour -> a board line with the agent name, once a day
s = state(); s["over_since"] = int(time.time()) - 4000; json.dump(s, open(f"{ST}/state.json", "w"))
o1 = run("--measure"); o2 = run("--measure")
b = open(BOARD).read() if os.path.exists(BOARD) else ""
ok("an hour over the limit -> a board line with the culprit agent", "Scraper-agent" in b and "🟥" in b and "Trash" in b, b)
ok("a second measure the same day does not duplicate the line", b.count("Trash") == 1 and "board" in o1 and "board" not in o2, (o1, o2))

# session B put small stuff into an already overfull trash -> not the culprit
run("--pre", "sidB"); junk("tiny.note", 20); run("--post", "sidB"); run("--measure")
run("--pre", "sidB"); ok("small stuff (<10% of the limit) in an overfull trash - silent", run("--post", "sidB") == "")

# grew outside sessions (cron, someone else's script): ownerless > half -> board line "no culprit visible"
for f in os.listdir(ST):
    if f.startswith("board-"): os.remove(f"{ST}/{f}")
os.remove(BOARD)
for i in range(8): junk(f"cache-{i}", 900)
run("--measure"); b = open(BOARD).read() if os.path.exists(BOARD) else ""
ok("ownerless junk -> no culprit visible + name group", "no culprit visible" in b and "cache-* x8" in b, b)

# the junk was removed -> the ledger forgets it, the shout stops
import shutil
for i in range(3): shutil.rmtree(f"{TR}/prof.Ab{i}")
run("--measure"); os.remove(f"{ST}/shout-sidA")
ok("the ledger forgot what is no longer in the trash", "prof." not in open(f"{ST}/ledger.jsonl").read())
run("--pre", "sidA"); ok("session A removed its own - no more shouting (though the trash is over the limit because of others)", run("--post", "sidA") == "")

# small things: empty stdin, another tool, no start mark - silent and no crash
r = subprocess.run([sys.executable, TG, "--post"], input="", capture_output=True, text=True, env=ENV)
ok("empty stdin -> rc 0, silent", r.returncode == 0 and r.stdout == "", (r.returncode, r.stderr[-200:]))
r = subprocess.run([sys.executable, TG, "--post"], input=json.dumps({"session_id": "sidZ", "tool_name": "Bash"}), capture_output=True, text=True, env=ENV)
ok("a session without a start mark attributes nothing", r.returncode == 0 and r.stdout == "")
# -- auto-clean: older than N days by time spent IN the trash
T2 = f"{R}/h/u/.Trash"; os.makedirs(T2); E2 = {**ENV, "TRASH_DIR": T2, "CCM_TRASH_DIR": T2}
def cl(*a, **e):
    e = {**e, **({"CCM_TRASH_DAYS": e["TRASH_KEEP_DAYS"]} if "TRASH_KEEP_DAYS" in e else {}), **({"CCM_TRASH_DIR": e["TRASH_DIR"]} if "TRASH_DIR" in e else {})}
    r = subprocess.run([sys.executable, TG, "--clean", *a], capture_output=True, text=True, env={**E2, **e}); return r.returncode, r.stdout + r.stderr
os.makedirs(f"{T2}/fresh.dir"); open(f"{T2}/fresh.dir/f", "w").write("x"); open(f"{T2}/fresh.txt", "w").write("x")
os.utime(f"{T2}/fresh.txt", (1, 1))                      # "old" by mtime, but put into the trash just now
rc, o = cl(); ok("freshly put (even with an old mtime) is not touched", rc == 0 and sorted(os.listdir(T2)) == ["fresh.dir", "fresh.txt"] and "deleted 0" in o, o)
rc, o = cl("--dry", TRASH_KEEP_DAYS="0"); ok("--dry: counts, deletes nothing", rc == 0 and "would delete 2" in o and len(os.listdir(T2)) == 2, o)
rc, o = cl(TRASH_KEEP_DAYS="0"); ok("older than the limit -> deleted, logged in clean.log", rc == 0 and os.listdir(T2) == [] and "DELETED fresh.dir" in open(f"{ST}/clean.log").read(), o)
NT = f"{R}/h/u/notrash"; os.makedirs(NT); open(f"{NT}/keep", "w").write("x")
rc, o = cl(TRASH_DIR=NT, TRASH_KEEP_DAYS="0"); ok("folder not named .Trash -> rc 2, touches nothing", rc == 2 and os.listdir(NT) == ["keep"], o)
os.symlink(NT, f"{R}/h/u/x"); os.makedirs(f"{R}/h/u/x2"); os.symlink(NT, f"{R}/h/u/x2/.Trash")
rc, o = cl(TRASH_DIR=f"{R}/h/u/x2/.Trash", TRASH_KEEP_DAYS="0"); ok("a trash that is a symlink to another folder -> rc 2", rc == 2 and os.listdir(NT) == ["keep"], o)
os.symlink(f"{NT}/keep", f"{T2}/link"); rc, o = cl(TRASH_KEEP_DAYS="0")
ok("symlink in the trash: the link goes, the target stays", os.listdir(T2) == [] and os.path.exists(f"{NT}/keep"), o)
print(f"trash-guard: {P} pass, {F} fail"); raise SystemExit(1 if F else 0)
