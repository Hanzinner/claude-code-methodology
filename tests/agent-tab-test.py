#!/usr/bin/env python3
"""agent_tab.py in a sandbox: identity -> session -> live pid. AT=<path> tests another copy."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
AT = os.environ.get("AT", os.path.join(HERE, "..", "scripts", "agent_tab.py"))
T = tempfile.mkdtemp(prefix="at-test-")
for d in ("ident", "sess", "Agents/Foo-Dev", "Agents/New-HQ", "Agents/Grp/Deep-agent"):
    os.makedirs(f"{T}/{d}")
me = os.getpid()
try:
    start = open(f"/proc/{me}/stat").read().rsplit(")", 1)[1].split()[19]
except OSError:
    start = "0"          # no /proc: the pid-exists check is used instead


def sess(fn, **k):
    json.dump(k, open(f"{T}/sess/{fn}.json", "w"))


open(f"{T}/ident/sid-a", "w").write(f"{T}/Agents/Foo-Dev\n")
open(f"{T}/ident/sid-old", "w").write("/x/Agents/Old-HQ\n")
open(f"{T}/ident/sid-deep", "w").write(f"{T}/Agents/Grp/Deep-agent\n")
open(f"{T}/Agents/New-HQ/.aliases", "w").write("# was\nOld-HQ\n")
sess("1", pid=me, procStart=start, sessionId="sid-a", name="tab-2e", status="idle")
sess("2", pid=me, procStart="1", sessionId="sid-a", name="tab-dead", status="idle")        # a reused pid
sess("3", pid=me, procStart=start, sessionId="sid-old", name="tab-7f", status="busy")
sess("4", pid=me, procStart=start, sessionId="sid-deep", name="tab-9c", status="idle")
env = {**os.environ, "HOME": T, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_AGENTS_DIR": f"{T}/Agents",
       "AGENT_TAB_IDENT": f"{T}/ident", "AGENT_TAB_SESSIONS": f"{T}/sess", "AGENT_TAB_AGENTS": f"{T}/Agents"}
P = F = 0


def run(*a):
    r = subprocess.run([sys.executable, AT, *a], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout.strip()


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print(f"FAIL: {n} {o}")


have_proc = os.path.isdir("/proc")
rc, o = run("Foo-Dev"); ok("1 one live tab by identity -> name and idle, the dead pid is dropped", (rc, o) == (0, "tab-2e\tidle"), (rc, o))
rc, o = run("foo-dev"); ok("2 a name in any case", rc == 0 and o.startswith("tab-2e"), o)
rc, o = run("New-HQ"); ok("3 an old identity via .aliases -> found, busy", (rc, o) == (0, "tab-7f\tbusy"), (rc, o))
rc, o = run("Nobody"); ok("4 none -> rc 1, \"no live tab\"", (rc, o) == (1, "no live tab"), (rc, o))
rc, o = run("Foo-Dev", "--json"); ok("5 --json", rc == 0 and json.loads(o)[0]["name"] == "tab-2e", o)
rc, o = run("Deep-agent"); ok("6 an agent in a group folder", (rc, o) == (0, "tab-9c\tidle"), (rc, o))
rc, o = run(); ok("7 no argument -> rc 2", rc == 2, o)
print(f"agent-tab: {P} pass, {F} fail"); sys.exit(1 if F else 0)
