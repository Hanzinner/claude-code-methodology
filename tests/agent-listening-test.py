#!/usr/bin/env python3
"""agent_listening: the addressee listens (a live inbox_wait / a session active within QUIET min) -> silence; no -> a
"⚠ ... is not listening" line. AL=<path> tests another copy. Sandbox only."""
import os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.realpath(__file__))
AL = os.environ.get("AL", os.path.join(HERE, "..", "scripts", "agent_listening.py"))
R = tempfile.mkdtemp(prefix="al-")
for d in ("ident", "proj/p", "wait", "Agents/Live", "Agents/Dead", "Agents/Waits", "Agents/Ghost"): os.makedirs(f"{R}/{d}")
ENV = {**os.environ, "HOME": R, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "LISTEN_IDENT": f"{R}/ident", "LISTEN_ROOTS": f"{R}/proj",
       "LISTEN_WAIT": f"{R}/wait", "LISTEN_QUIET_MIN": "5", "AGENT_TAB_SESSIONS": f"{R}/none", "AGENT_TAB_IDENT": f"{R}/ident"}


def sess(sid, agent, age_s):
    # the mtime is deliberately "just now" (what a night hygiene job does) - only the timestamp INSIDE counts
    open(f"{R}/ident/{sid}", "w").write(f"{R}/Agents/{agent}")
    ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - age_s))
    open(f"{R}/proj/p/{sid}.jsonl", "w").write('{"type":"user","timestamp":"%s"}\n' % ts)


sess("s1", "Live", 60); sess("s2", "Dead", 7200); sess("s2old", "Dead", 90000); sess("s3", "Waits", 7200)
w = subprocess.Popen(["sleep", "30"]); open(f"{R}/wait/Waits", "w").write(str(w.pid))
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def run(a):
    r = subprocess.run([sys.executable, AL, a], capture_output=True, text=True, env=ENV)
    return r.returncode, r.stdout


rc, o = run(f"{R}/Agents/Live"); ok("a session was active a minute ago -> silence", rc == 0 and o == "", o)
rc, o = run(f"{R}/Agents/Dead/inbox.md"); ok("2 h of silence, no alarm -> \"not listening\", the freshest session's time", rc == 0 and "⚠ Dead is not listening" in o and "120 min ago" in o, o)
rc, o = run(f"{R}/Agents/Waits"); ok("a live inbox_wait -> silence though the session is silent for 2 h", o == "", o)
w.kill(); w.wait()
rc, o = run(f"{R}/Agents/Waits"); ok("the alarm died (dead pid) -> \"not listening\"", "⚠ Waits is not listening" in o, o)
rc, o = run(f"{R}/Agents/Ghost"); ok("no session of the agent at all -> says so", "no session of it found" in o, o)
# a ready tab name: agent_tab found one -> SendMessage to="..."; none -> "tell the human"
open(f"{R}/tab.sh", "w").write('#!/bin/sh\n[ "$1" = Dead ] && { printf "tab-2e\\tidle\\n"; exit 0; }\necho "no live tab"; exit 1\n')
os.chmod(f"{R}/tab.sh", 0o755); ENV["AGENT_TAB"] = f"{R}/tab.sh"
rc, o = run(f"{R}/Agents/Dead"); ok("a live tab -> a ready SendMessage to=\"tab-2e\"", 'SendMessage to="tab-2e"' in o, o)
rc, o = run(f"{R}/Agents/Ghost"); ok("no tab -> \"tell the human\", no SendMessage", "tell the human" in o and "SendMessage" not in o, o)
r = subprocess.run([sys.executable, AL], capture_output=True, text=True, env=ENV); ok("no argument -> silent, rc 0", r.returncode == 0 and r.stdout == "")
print(f"agent-listening: {P} pass, {F} fail"); sys.exit(1 if F else 0)
