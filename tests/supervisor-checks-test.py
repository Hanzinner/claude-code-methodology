#!/usr/bin/env python3
"""The checks the supervisor runs (watchman_alive, cron_state, hook_timeouts, checks_lint, reminders_stuck, releaser,
tab_stuck, api_silence, presence): each has at least one red and one green case. SC=<dir with the check scripts> tests
another copy. Sandbox only: temp HOME, no config file, every path through env/CCM_* into the temp dir; no network."""
import json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.realpath(__file__))
SC = os.environ.get("SC", os.path.join(HERE, "..", "scripts"))
R = tempfile.mkdtemp(prefix="chk-test-")
NOW = int(time.time())
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:400])


def run(script, *args, **kw):
    e = {**os.environ, "HOME": R, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_HUMAN_NAME": "Tester"}
    for k in list(e):
        if k.startswith("CCM_") and k != "CCM_HUMAN_NAME":
            e.pop(k)
    e.update({k: str(v) for k, v in kw.items()})
    r = subprocess.run([sys.executable, os.path.join(SC, script), *map(str, args)], capture_output=True, text=True, env=e)
    return r.returncode, r.stdout + r.stderr


def touch(p, age_s=0, text="x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)
    os.utime(p, (NOW - age_s,) * 2)


def iso(t): return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


# ── watchman_alive_check
W, T = f"{R}/w/wm", f"{R}/w/proj"
touch(f"{T}/a/s.jsonl", 60); touch(f"{W}/heartbeat", 3 * 3600)
rc, o = run("watchman_alive_check.py", WATCHMAN_DIR=W, TRANSCRIPTS=T)
ok("watchman: chats alive, pulse 3 h old -> red", rc == 1 and "silent" in o, o)
touch(f"{W}/heartbeat", 120)
rc, o = run("watchman_alive_check.py", WATCHMAN_DIR=W, TRANSCRIPTS=T)
ok("watchman: chats alive, pulse 2 min old -> green", rc == 0, o)
touch(f"{T}/a/s.jsonl", 3 * 3600); touch(f"{W}/heartbeat", 3 * 3600)
rc, o = run("watchman_alive_check.py", WATCHMAN_DIR=W, TRANSCRIPTS=T)
ok("watchman: quiet chats + old pulse -> green (nothing to check)", rc == 0 and "quiet" in o, o)
os.remove(f"{W}/heartbeat")
rc, o = run("watchman_alive_check.py", WATCHMAN_DIR=W, TRANSCRIPTS=T)
ok("watchman: no pulse file -> rc 3 (could not measure)", rc == 3, o)

# ── cron_state_check
CS = f"{R}/cs"
def okfile(name, age_h): touch(f"{CS}/{name}.ok", 0, time.strftime("%Y-%m-%d %H:%M", time.localtime(NOW - age_h * 3600)) + " 2026-11-13\n")
okfile("fresh_job", 5); okfile("old_job", 50)
rc, o = run("cron_state_check.py", "fresh_job", 36, CCM_CRON_STATE=CS, CRON_STATE_BOOTS="/nonexistent")
ok("cron_state: success 5 h ago, limit 36 -> green", rc == 0, o)
rc, o = run("cron_state_check.py", "old_job", 36, CCM_CRON_STATE=CS, CRON_STATE_BOOTS="/nonexistent")
ok("cron_state: success 50 h ago, limit 36 -> red", rc == 1, o)
boots = [{"first_entry": (NOW - 100 * 3600) * 1e6, "last_entry": (NOW - 48 * 3600) * 1e6}, {"first_entry": (NOW - 10 * 3600) * 1e6, "last_entry": NOW * 1e6}]
json.dump(boots, open(f"{R}/boots.json", "w"))
rc, o = run("cron_state_check.py", "old_job", 36, CCM_CRON_STATE=CS, CRON_STATE_BOOTS=f"{R}/boots.json")
ok("cron_state: 38 of the 50 h the machine was off -> working age 12 h -> green", rc == 0 and "off 38 h" in o, o)
touch(f"{CS}/broke.fail", 0, "2026-11-13 10:00 rc=2 period 2026-11-13\n")
rc, o = run("cron_state_check.py", "broke", 36, CCM_CRON_STATE=CS)
ok("cron_state: a .fail file -> red with the failure text", rc == 1 and "rc=2" in o, o)
rc, o = run("cron_state_check.py", "never", 36, CCM_CRON_STATE=CS)
ok("cron_state: no .ok, no .fail -> rc 3", rc == 3, o)

# ── hook_timeouts_check
L = f"{R}/hook-errors.log"
def line(age_s, kind="TIMEOUT"):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(NOW - age_s)); ts = ts[:-2] + ":" + ts[-2:]
    return f"{ts} x.py failed (exit 124)" + (f" [TIMEOUT 20s]" if kind == "TIMEOUT" else " :: boom") + "\n"
open(L, "w").write("".join(line(60 * i) for i in range(1, 6)))
rc, o = run("hook_timeouts_check.py", HOOK_ERRORS_LOG=L)
ok("hook_timeouts: 5 timeouts in the hour -> red", rc == 1 and ": 5 " in o, o)
open(L, "w").write(line(60) + line(120) + line(3 * 3600) * 5 + line(30, "other") * 9)
rc, o = run("hook_timeouts_check.py", HOOK_ERRORS_LOG=L)
ok("hook_timeouts: 2 recent + old ones + non-timeout failures -> green", rc == 0 and ": 2 " in o, o)
rc, o = run("hook_timeouts_check.py", HOOK_ERRORS_LOG=f"{R}/no-such.log")
ok("hook_timeouts: no log -> green", rc == 0, o)

# ── checks_lint
def reg(cs): p = f"{R}/reg.json"; json.dump({"checks": cs}, open(p, "w")); return p
rc, o = run("checks_lint.py", "--checks", reg([{"name": "Restic log", "kind": "fresh", "path": "/x/restic.log", "max_age_min": 60}, {"name": "ok", "kind": "cmd"}]))
ok("checks_lint: fresh on a .log with no reason -> red, named", rc == 1 and "Restic log" in o, o)
rc, o = run("checks_lint.py", "--checks", reg([{"name": "Restic log", "kind": "fresh", "path": "/x/restic.log", "fresh_ok": "the log is only written on success"}, {"name": "f", "kind": "fresh", "path": "/x/state.json"}]))
ok("checks_lint: with fresh_ok, or fresh on a non-log -> green", rc == 0, o)
rc, o = run("checks_lint.py", "--checks", f"{R}/missing.json")
ok("checks_lint: unreadable registry -> rc 3", rc == 3, o)
rc, o = run("checks_lint.py", "--checks", reg([]))
ok("checks_lint: an empty registry is suspicious -> rc 3", rc == 3, o)

# ── reminders_stuck_check
RD = f"{R}/rem"
touch(f"{RD}/{NOW - 1200}-abc.json", 0, "{}")
rc, o = run("reminders_stuck_check.py", REMIND_DIR=RD)
ok("reminders: one overdue by 20 min -> red", rc == 1 and "overdue" in o, o)
os.remove(f"{RD}/{NOW - 1200}-abc.json"); touch(f"{RD}/{NOW + 600}-def.json", 0, "{}"); touch(f"{RD}/{NOW - 100}-ghi.json", 0, "{}"); touch(f"{RD}/remind.log", 0, "x")
rc, o = run("reminders_stuck_check.py", REMIND_DIR=RD)
ok("reminders: a future one, one 100 s late, a log file -> green", rc == 0, o)
rc, o = run("reminders_stuck_check.py", REMIND_DIR=f"{R}/no-dir")
ok("reminders: no dir -> green", rc == 0, o)

# ── releaser_check
RS = f"{R}/rel"
touch(f"{RS}/queue/Alpha/a.ready", 30 * 60); touch(f"{RS}/queue/Beta/b.ready", 60)
rc, o = run("releaser_check.py", RELEASER_STATE=RS)
ok("releaser: a marker waiting 30 min -> red, names the project, not the fresh one", rc == 1 and "Alpha" in o and "Beta" not in o, o)
os.remove(f"{RS}/queue/Alpha/a.ready")
rc, o = run("releaser_check.py", RELEASER_STATE=RS)
ok("releaser: only a fresh marker / empty queue -> green", rc == 0, o)
rc, o = run("releaser_check.py", RELEASER_STATE=f"{R}/no-rel")
ok("releaser: no queue dir (not installed) -> green", rc == 0 and "not installed" in o, o)

# ── api_silence_check
AP = f"{R}/api"
def tr(path, events): touch(path, 0, "\n".join(json.dumps(e) for e in events) + "\n")
human = lambda t, txt="are you alive?": {"type": "user", "timestamp": iso(t), "message": {"content": txt}}
synth = lambda t, txt="API Error: Can't reach the API server (EAI_AGAIN)": {"type": "assistant", "timestamp": iso(t), "message": {"model": "<synthetic>", "content": [{"type": "text", "text": txt}]}}
real = lambda t: {"type": "assistant", "timestamp": iso(t), "message": {"model": "claude", "content": [{"type": "text", "text": "hi"}]}}
toolres = lambda t: {"type": "user", "timestamp": iso(t), "message": {"content": [{"type": "tool_result", "content": "ok"}]}}
tr(f"{AP}/p/s1.jsonl", [human(NOW - 120), synth(NOW - 100)])
rc, o = run("api_silence_check.py", API_SILENCE_ROOTS=AP)
ok("api_silence: a human message answered by a synthetic API error -> red", rc == 1 and "EAI_AGAIN" in o and "are you alive" in o, o)
tr(f"{AP}/p/s1.jsonl", [human(NOW - 120), real(NOW - 110), synth(NOW - 100)])
rc, o = run("api_silence_check.py", API_SILENCE_ROOTS=AP)
ok("api_silence: the error follows a real model reply, not the human -> green", rc == 0, o)
tr(f"{AP}/p/s1.jsonl", [human(NOW - 120), toolres(NOW - 110), synth(NOW - 100)])
rc, o = run("api_silence_check.py", API_SILENCE_ROOTS=AP)
ok("api_silence: the error follows a tool result (the agent was working) -> green", rc == 0, o)
tr(f"{AP}/p/s1.jsonl", [human(NOW - 5000), synth(NOW - 4990)])
rc, o = run("api_silence_check.py", API_SILENCE_ROOTS=AP)
ok("api_silence: an old error outside the 20 min window -> green", rc == 0, o)
tr(f"{AP}/p/s1.jsonl", [human(NOW - 120), synth(NOW - 100, "Something unrelated")])
rc, o = run("api_silence_check.py", API_SILENCE_ROOTS=AP)
ok("api_silence: a synthetic line that is not a service error -> green", rc == 0, o)

# ── tab_stuck_check
TS = f"{R}/tab"; ID, PR, GF, WT, ST = f"{TS}/ident", f"{TS}/projects", f"{TS}/guard.txt", f"{TS}/wait", f"{TS}/state"
os.makedirs(f"{TS}/Agents/Alice"); os.makedirs(f"{TS}/Agents/Bob")
touch(GF, 0, "# guarded\nAlice\nBob\n")
touch(f"{ID}/sid-a", 0, f"{TS}/Agents/Alice\n"); touch(f"{ID}/sid-b", 0, f"{TS}/Agents/Bob\n")
tr(f"{PR}/p/sid-a.jsonl", [human(NOW - 4000, "go on"), real(NOW - 3900), synth(NOW - 3600)])   # Alice: stopped on an error an hour ago
tr(f"{PR}/p/sid-b.jsonl", [human(NOW - 4000, "go on"), synth(NOW - 3700), real(NOW - 3600)])   # Bob: the error was followed by a real reply
E = dict(TAB_STUCK_IDENT=ID, TAB_STUCK_ROOTS=PR, TAB_STUCK_AGENTS=GF, TAB_STUCK_WAIT=WT, TAB_STUCK_STATE=ST)
rc, o = run("tab_stuck_check.py", **E)
todo = f"{TS}/Agents/Alice/human-TODO.md"
ok("tab_stuck: Alice stopped on a service error, no alarm -> red, only Alice", rc == 1 and "Alice" in o and "Bob" not in o, o)
ok("tab_stuck: one line for the human in Alice's human-TODO", os.path.isfile(todo) and open(todo).read().count("Alice has stood") == 1 and "Tester" in open(todo).read(), os.path.isfile(todo) and open(todo).read())
ok("tab_stuck: Bob (error then a real reply) got no line", not os.path.exists(f"{TS}/Agents/Bob/human-TODO.md"))
rc, o = run("tab_stuck_check.py", **E)
ok("tab_stuck: still red on the next run, but the same stop is not written twice", rc == 1 and open(todo).read().count("has stood") == 1, o)
touch(f"{WT}/Alice", 0, str(os.getpid()))
rc, o = run("tab_stuck_check.py", **E)
ok("tab_stuck: Alice has a live alarm (inbox_wait) -> green", rc == 0, o)
rc, o = run("tab_stuck_check.py", **{**E, "TAB_STUCK_AGENTS": ""})
ok("tab_stuck: no guard file configured -> off, green", rc == 0 and "off" in o, o)
os.makedirs(f"{TS}/Agents/Cy"); touch(f"{TS}/Agents/Cy/Cy-Boss-TODO.md", 0, "")
touch(f"{ID}/sid-c", 0, f"{TS}/Agents/Cy\n"); touch(GF, 0, "Cy\n")
tr(f"{PR}/p/sid-c.jsonl", [human(NOW - 4000), synth(NOW - 3600, "Failed to authenticate: OAuth session expired")])
rc, o = run("tab_stuck_check.py", **E)
ok("tab_stuck: an existing <agent>-<Name>-TODO.md (old style) is used instead of a new file", rc == 1 and "Cy has stood" in open(f"{TS}/Agents/Cy/Cy-Boss-TODO.md").read() and not os.path.exists(f"{TS}/Agents/Cy/human-TODO.md"), o)

# ── presence_check
PD = f"{R}/pres/ts"
def pres(cmd="", **kw): return run("presence_check.py", PRESENCE_TS_DIR=PD, CCM_PRESENCE_CMD=cmd, **kw)
touch(f"{PD}/s1", 0, str(NOW - 60))
rc, o = pres()
ok("presence: a prompt a minute ago -> present (rc 0)", rc == 0 and o.startswith("present:prompt"), o)
touch(f"{PD}/s1", 0, str(NOW - 3600))
rc, o = pres()
ok("presence: old prompt, no desktop source -> away (rc 1)", rc == 1 and o.startswith("away:"), o)
touch(f"{PD}/machine/s2", 0, str(NOW - 10))
rc, o = pres()
ok("presence: a fresh stamp in the machine/ subfolder is not the human -> still away", rc == 1, o)
rc, o = pres("echo 3")
ok("presence: desktop idle 3 min -> present", rc == 0 and "desktop idle 3" in o, o)
rc, o = pres("echo .")
ok("presence: desktop idle '.' -> present", rc == 0, o)
rc, o = pres("echo 1:30")
ok("presence: desktop idle 1:30 -> away", rc == 1 and "idle 90" in o, o)
rc, o = pres("echo 2+01:23")
ok("presence: idle in days -> away", rc == 1, o)
rc, o = pres("false")
ok("presence: the source fails -> unknown, fail-closed (rc 2)", rc == 2 and o.startswith("unknown:"), o)
rc, o = pres("echo gibberish")
ok("presence: the source prints nonsense -> unknown", rc == 2, o)

print(f"supervisor-checks: {P} pass, {F} fail")
sys.exit(1 if F else 0)
