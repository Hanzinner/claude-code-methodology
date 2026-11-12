#!/usr/bin/env python3
"""work-guard: a Stop gate "don't stop with open tasks" in a sandbox (temp HOME, no config file, CCM_* env into the temp dir).
Runs the repo copy; WG=<path> tests another one. Fixtures only in the temp dir; no real inbox/alarm is touched."""
import datetime as _d, json, os, shutil as _sh, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.realpath(__file__))
WG = os.environ.get("WG", os.path.join(HERE, "..", "hooks", "work-guard.py"))
root = tempfile.mkdtemp(prefix="wg-test-")
MODE = f"{root}/mode"
home = f"{root}/home"; agent_dir = f"{root}/Agents/TestAgent"
os.makedirs(f"{home}/.claude/agent-identity"); os.makedirs(f"{home}/.claude/inbox-wait"); os.makedirs(agent_dir)
sid = "test-sid"
open(f"{home}/.claude/agent-identity/{sid}", "w").write(agent_dir)
INBOX = os.path.join(agent_dir, "inbox.md")
TODO = os.path.join(agent_dir, "agent-TODO.md")
HTODO = os.path.join(agent_dir, "human-TODO.md")
TP = f"{root}/t.jsonl"
GUARD = f"{root}/guard-agents.txt"
POSTLOG = f"{root}/posts.log"; POST = f"{root}/post.sh"
KEEP_MODE = False
LANG = ""


def setf(p, s): open(p, "w").write(s)
setf(POST, f'#!/bin/bash\necho "$1 | $2" >> {POSTLOG}\n'); os.chmod(POST, 0o755)


def env():
    return {**os.environ, "HOME": home, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_WORK_GUARD_AGENTS": GUARD,
            "CCM_ALARM_MODE_DIR": MODE, "CCM_HUMAN_NAME": "Sam", "CCM_INFRA_AGENT": "Infra", "WORK_GUARD_POST": POST,
            "CCM_LANG_EXTRA": LANG}


def exec_(sid_=sid):
    return subprocess.run([sys.executable, WG], input=json.dumps({"session_id": sid_, "transcript_path": TP}),
                          capture_output=True, text=True, env=env())


def run():
    if not KEEP_MODE: _sh.rmtree(MODE, ignore_errors=True)    # phrases of earlier cases must not carry a mode over
    return "BLOCK" if '"decision"' in exec_().stdout else "PASS"


def msg(t): setf(TP, json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": t}]}}) + "\n")
def jl(o): return json.dumps(o, ensure_ascii=False) + "\n"
def logtail(): return open(f"{home}/.claude/work-guard.log").read().splitlines()[-1]


setf(GUARD, "TestAgent\n")
res = []
setf(INBOX, "# inbox\n\n## New\n\n- [ ] letter\n\n## Done\n"); setf(TODO, "- [ ] task A\n- [ ] ⏳ waiting for Sam\n")
msg("done"); res.append(("1 inbox has a new item", run(), "BLOCK"))
setf(INBOX, "# inbox\n\n## New\n\n## Done\n- [ ] old one under Done\n")
msg("did a step"); res.append(("2 TODO open, no STATE", run(), "BLOCK"))
msg("did it\n\nSTATE: waiting for the end of the meeting 12:27"); res.append(("3 STATE without an alarm", run(), "BLOCK"))
p = subprocess.Popen(["sleep", "60"]); setf(f"{home}/.claude/inbox-wait/TestAgent", str(p.pid))
res.append(("4 STATE + a live alarm", run(), "PASS"))
p.kill(); p.wait(); res.append(("5 the alarm died", run(), "BLOCK"))
setf(TODO, "- [x] done\n- [ ] ⏳ waiting for Sam\n"); msg("all"); res.append(("6 empty queue, no alarm", run(), "BLOCK"))
p2 = subprocess.Popen(["sleep", "60"]); setf(f"{home}/.claude/inbox-wait/TestAgent", str(p2.pid)); msg("all\n\nSTATE: queue empty")
res.append(("6b empty queue + alarm", run(), "PASS")); p2.kill(); p2.wait()
setf(GUARD, "Other\n"); setf(TODO, "- [ ] A\n"); msg("x"); res.append(("7 agent not in the list", run(), "PASS"))
setf(GUARD, ""); res.append(("7b empty guard file -> guard off", run(), "PASS"))
os.remove(GUARD); res.append(("7c no guard file -> guard off", run(), "PASS"))
setf(GUARD, "TestAgent\n"); msg("step")
seq = "".join("B" if run() == "BLOCK" else "P" for _ in range(14)); res.append(("8 loop: 12 blocks, then a pass", seq[:13], "BBBBBBBBBBBBP"))
# context: a big context -> one recap demand, then the usual rules again
setf(TODO, "- [x] done\n")
p3 = subprocess.Popen(["sleep", "60"]); setf(f"{home}/.claude/inbox-wait/TestAgent", str(p3.pid))
def usage_line(n): return jl({"type": "assistant", "message": {"usage": {"input_tokens": 10, "cache_read_input_tokens": n}, "content": [{"type": "text", "text": "x\n\nSTATE: queue empty"}]}})
setf(TP, usage_line(750000)); res.append(("9 context 750k -> recap", run(), "BLOCK")); res.append(("10 same context -> no repeat", run(), "PASS"))
run(); res.append(("10b after the recap -> '/compact' line for the human", str(os.path.exists(HTODO) and open(HTODO).read().count("/compact")), "1"))
run(); res.append(("10c no duplicate", str(open(HTODO).read().count("/compact")), "1"))
setf(TP, usage_line(100000)); res.append(("11 after the compaction", run(), "PASS"))
setf(TP, usage_line(750000)); res.append(("12 750k again -> recap again", run(), "BLOCK")); p3.kill(); p3.wait()
res.append(("12b the '/compact' line carries the sid", str(f"[{sid[:8]}]" in open(HTODO).read()), "True"))
setf(TP, usage_line(100000)); run()
res.append(("12c after the compaction this session's '/compact' line is closed", str("- [ ] type" not in open(HTODO).read()), "True"))

# ghost: the old branch after /compact is not blocked, the live one is as usual
def row(uuid, parent, typ="assistant", text="step", usage=None, model="claude-opus-5-5", **kw):
    m = {"model": model, "content": [{"type": "text", "text": text}]}
    if usage is not None: m["usage"] = {"input_tokens": 10, "cache_read_input_tokens": usage}
    return json.dumps({"type": typ, "uuid": uuid, "parentUuid": parent, "message": m, **kw}, ensure_ascii=False)
def transcript(tail_rows):
    head = [row("o1", None, usage=690000), row("o2", "o1", usage=700000),
            json.dumps({"type": "system", "subtype": "compact_boundary", "uuid": "cb", "parentUuid": None}),
            row("n1", "cb", typ="user", text="summary"), row("n2", "n1", usage=100000)]
    setf(TP, "\n".join(head + tail_rows) + "\n")
setf(TODO, "- [ ] task A\n"); setf(INBOX, "# inbox\n\n## New\n\n## Done\n")
for f in os.listdir(f"{home}/.claude/inbox-wait"): os.remove(f"{home}/.claude/inbox-wait/{f}")
try: os.remove(f"{home}/.claude/work-guard/recap-{sid}")
except OSError: pass
transcript([row("g1", "o2", text="ghost works", usage=705000)])
res.append(("13 the last turn is a ghost (branch before the compaction) -> not blocked", run(), "PASS"))
res.append(("13b ghost logged", str("GHOST" in logtail()), "True"))
transcript([row("g1", "o2", text="ghost", usage=705000), row("n3", "n2", text="live, no STATE", usage=110000)])
res.append(("14 last turn of the live branch, TODO open -> block", run(), "BLOCK"))
res.append(("14b context from the live branch (110k), not the ghost (705k) -> no recap demand", str("recap" not in logtail()), "True"))
transcript([row("n3", "n2", text="x", usage=720000), row("n4", "n3", text="You've hit your limit", usage=0, model="<synthetic>")])
run(); run()
res.append(("15 a synthetic row (usage 0) doesn't reset the recap -> exactly one demand",
            str(sum("demanding a recap" in l for l in open(f"{home}/.claude/work-guard.log").read().splitlines()[-4:])), "1"))

# an alarm process whose marker vanished in a race is still an alarm
setf(TODO, "- [x] done\n"); setf(TP, row("z1", None, text="x\n\nSTATE: waiting for a letter", usage=100000) + "\n")
fake = f"{root}/inbox_wait.sh"; setf(fake, "#!/bin/bash\nsleep 60\n"); os.chmod(fake, 0o755)
p6 = subprocess.Popen(["bash", fake, "TestAgent", "--until", "14:00"])
res.append(("17 no marker, process 'inbox_wait.sh TestAgent' alive -> not blocked", run(), "PASS"))
p6.kill(); p6.wait()
p7 = subprocess.Popen(["bash", fake, "OtherAgent"])
res.append(("17b another agent's alarm doesn't count -> block", run(), "BLOCK")); p7.kill(); p7.wait()

# memory pressure: the harness stopped the background task -> no alarm demanded, a letter to the infra agent once
human = jl({"type": "user", "uuid": "h1", "message": {"role": "user", "content": "keep going"}})
asst = jl({"type": "assistant", "uuid": "a1", "message": {"model": "claude-opus-5-5", "content": [{"type": "text", "text": "stopped\n\nSTATE: queue empty"}]}})
def notif(text, uuid="n1"):
    return jl({"type": "user", "uuid": uuid, "origin": {"kind": "task-notification", "producer": "session-task"},
               "message": {"role": "user", "content": f"<task-notification>\n<status>killed</status>\n<summary>{text}</summary>\n</task-notification>"}})
REAP = "Background command stopped because the system is running low on memory. Do not start it again on your own"
setf(INBOX, "# inbox\n\n## New\n\n## Done\n"); setf(TODO, "- [x] done\n")
setf(TP, human + notif(REAP) + asst)
res.append(("18 low memory, no alarm -> not blocked", run(), "PASS"))
res.append(("18b a letter to the infra agent went out", str(open(POSTLOG).read().count("Infra | work-guard")), "1"))
run(); res.append(("18c the same notification again -> no duplicate letter", str(open(POSTLOG).read().count("Infra")), "1"))
setf(TP, human + notif("Background command completed (exit code 0)") + asst)
res.append(("18d an ordinary task completion without an alarm -> block as before", run(), "BLOCK"))
setf(TP, human + notif(REAP) + asst + jl({"type": "user", "uuid": "h2", "message": {"role": "user", "content": "what's up"}}) + asst)
res.append(("18e the human wrote after the stop -> the alarm is mandatory again", run(), "BLOCK"))
tr = jl({"type": "user", "uuid": "t1", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "<task-notification> " + REAP}]}})
setf(TP, human + tr + asst)
res.append(("18f the same phrase in a tool output (grep) is not a notification -> block", run(), "BLOCK"))
setf(TODO, "- [ ] task\n"); setf(TP, human + notif(REAP, "n2") + jl({"type": "assistant", "uuid": "a2", "message": {"model": "claude-opus-5-5", "content": [{"type": "text", "text": "step"}]}}))
r_ = exec_()
res.append(("18g open TODO without STATE -> block, but it doesn't tell to start an alarm", str('"decision"' in r_.stdout and "do NOT start the alarm" in r_.stdout and "run_in_background" not in r_.stdout), "True"))
_sh.rmtree(f"{home}/.claude/work-guard", ignore_errors=True)
setf(TODO, "- [x] done\n")
_o = os.environ.get("CCM_INFRA_AGENT")
n_posts = open(POSTLOG).read().count("Infra")

# "turn off the alarm" from the human / a .no-alarm flag -> no alarm demanded until the end of the day
nowz = _d.datetime.now(_d.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
oldz = (_d.datetime.now(_d.timezone.utc) - _d.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
def hu(t, ts=nowz, u="h"): return jl({"type": "user", "uuid": u, "timestamp": ts, "message": {"role": "user", "content": t}})
A = jl({"type": "assistant", "uuid": "a9", "message": {"model": "claude-opus-5-5", "content": [{"type": "text", "text": "ok\n\nSTATE: queue empty"}]}})
setf(INBOX, "# inbox\n\n## New\n\n## Done\n"); setf(TODO, "- [x] done\n")
setf(TP, hu("turn off the alarm for now, we talk directly") + A)
res.append(("19 'turn off the alarm' today -> not blocked", run(), "PASS"))
setf(TP, hu("turn off the alarm", u="h1") + A + hu("ok, start the alarm again", u="h2") + A)
res.append(("19b then 'start the alarm' -> demanded again", run(), "BLOCK"))
setf(TP, hu("stop the alarms please") + A)
res.append(("19g 'stop the alarms please' -> not blocked", run(), "PASS"))
setf(TP, hu("no alarm today", ts=oldz) + A)
res.append(("19c an order from two days ago -> demanded", run(), "BLOCK"))
setf(TP, hu("what about the alarm?") + A)
res.append(("19d a mere mention of the alarm -> demanded", run(), "BLOCK"))
setf(TP, hu("keep working") + A); setf(os.path.join(agent_dir, ".no-alarm"), "")
res.append(("19e a .no-alarm flag today -> not blocked", run(), "PASS"))
os.utime(os.path.join(agent_dir, ".no-alarm"), (time.time() - 2 * 86400, time.time() - 2 * 86400))
res.append(("19f yesterday's flag -> demanded", run(), "BLOCK"))
os.remove(os.path.join(agent_dir, ".no-alarm"))
setf(TODO, "- [ ] task\n"); setf(TP, hu("turn off the alarm") + jl({"type": "assistant", "uuid": "a8", "message": {"model": "m", "content": [{"type": "text", "text": "step"}]}}))
r_ = exec_()
res.append(("19h open TODO without STATE -> block, 'do NOT start the alarm'", str("do NOT start the alarm" in r_.stdout and "run_in_background" not in r_.stdout), "True"))
setf(TODO, "- [x] done\n")

# alarm modes: off · once · auto (default) · always
KEEP_MODE = True
def mode(m):
    _sh.rmtree(MODE, ignore_errors=True)
    if m: os.makedirs(MODE); setf(f"{MODE}/TestAgent", m + "\n"); os.utime(f"{MODE}/TestAgent", (time.time(), time.time()))
setf(INBOX, "# inbox\n\n## New\n\n## Done\n"); setf(TODO, "- [x] done\n"); old = time.time() - 7200
os.utime(INBOX, (old, old)); setf(TP, A)
mode("off");    res.append(("21 mode off, no alarm -> not blocked", run(), "PASS"))
mode("always"); res.append(("21b always, inbox quiet for 2 h -> block", run(), "BLOCK"))
mode(None);     res.append(("21c auto (no file), inbox quiet 2 h, no human messages -> not blocked", run(), "PASS"))
mode("once");   res.append(("21d once, quiet 2 h -> block", run(), "BLOCK"))
mode(None); os.utime(INBOX, None); res.append(("21e auto, inbox just changed -> block", run(), "BLOCK"))
mode(None); os.utime(INBOX, (old, old)); setf(TP, hu("set a permanent alarm") + A)
r21f = run(); m21 = open(f"{MODE}/TestAgent").read().strip() if os.path.exists(f"{MODE}/TestAgent") else "-"
res.append(("21f 'set a permanent alarm' -> mode always and block", f"{r21f}/{m21}", "BLOCK/always"))
mode(None); setf(TP, hu("turn off the alarm", ts=oldz) + A)
run(); res.append(("21g an old (2 days) 'turn off the alarm' doesn't change the mode", str(not os.path.exists(f"{MODE}/TestAgent")), "True"))
mode(None); setf(TP, hu("make it a one-shot alarm") + A); run()
res.append(("21h 'one-shot alarm' -> mode once", open(f"{MODE}/TestAgent").read().strip() if os.path.exists(f"{MODE}/TestAgent") else "-", "once"))
KEEP_MODE = False
os.utime(INBOX, None)

# Ukrainian phrases only with CCM_LANG_EXTRA=uk
LANG = ""
setf(TODO, "- [ ] task\n"); msg("step\n\nСТАН: waiting")
res.append(("22 Ukrainian 'СТАН:' without the uk list -> not a STATE line -> block", run(), "BLOCK"))
LANG = "uk"
res.append(("22b with uk: the 'СТАН:' line is accepted, but no alarm -> still block (alarm)", run(), "BLOCK"))
p8 = subprocess.Popen(["sleep", "60"]); setf(f"{home}/.claude/inbox-wait/TestAgent", str(p8.pid))
res.append(("22c with uk: 'СТАН:' + live alarm -> pass", run(), "PASS"))
LANG = ""
res.append(("22d without uk: the same -> block", run(), "BLOCK")); p8.kill(); p8.wait()
LANG = "uk"
setf(TODO, "- [x] done\n"); setf(TP, hu("вимкни будильник") + A); os.remove(f"{home}/.claude/inbox-wait/TestAgent")
res.append(("22e uk: 'вимкни будильник' -> not blocked", run(), "PASS"))
LANG = ""
res.append(("22f without uk: the same words don't switch it off -> block", run(), "BLOCK"))

# a renamed folder: the guard file holds the old name from .aliases -> the guard acts
import uuid as _u
sid_a = "alias-" + _u.uuid4().hex[:6]; open(f"{home}/.claude/agent-identity/{sid_a}", "w").write(agent_dir)
setf(os.path.join(agent_dir, ".aliases"), "# old\nOldName\n"); setf(GUARD, "OldName\n"); setf(TODO, "- [ ] A\n"); setf(TP, A.replace("STATE: queue empty", "x"))
r = exec_(sid_a)
res.append(("20 the old name from .aliases is in the guard file -> the guard acts", "BLOCK" if '"decision"' in r.stdout else "PASS", "BLOCK"))

P = F = 0
for name, got, want in res:
    if got == want: P += 1
    else: F += 1; print(f"FAIL: {name}: got {got}, want {want}")
print(f"work-guard: {P} pass, {F} fail"); raise SystemExit(1 if F else 0)
