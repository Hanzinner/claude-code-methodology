#!/usr/bin/env python3
"""rename_session: appends a custom-title record to a session .jsonl. RS=<path> tests another copy. HOME is a temp dir."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
RS = os.environ.get("RS", os.path.join(HERE, "..", "scripts", "rename_session.py"))
T = tempfile.mkdtemp(prefix="rs-test-")
ENV = {**os.environ, "HOME": T, "CLAUDE_METHODOLOGY_CONF": "/nonexistent"}
PD = os.path.join(T, ".claude", "projects", "proj")
os.makedirs(PD)
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


A, B = "aaaaaaaa-1111-2222-3333-444444444444", "bbbbbbbb-1111-2222-3333-444444444444"
for sid, title in ((A, "Fix the parser"), (B, "Write the docs")):
    with open(os.path.join(PD, sid + ".jsonl"), "w") as f:
        f.write(json.dumps({"type": "ai-title", "aiTitle": title, "sessionId": sid}) + "\n")
        f.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
open(os.path.join(PD, "notes.jsonl"), "w").write("{}\n")   # not a session file name: ignored


def run(*a):
    r = subprocess.run([sys.executable, RS, *a], capture_output=True, text=True, env=ENV)
    return r.returncode, r.stdout + r.stderr


rc, o = run("--list")
ok("1 --list shows both sessions, ignores other .jsonl", rc == 0 and "Sessions (2)" in o and "Fix the parser" in o, o)
rc, o = run("parser", "Parser rework")
ok("2 rename by title substring succeeds", rc == 0 and "Parser rework" in o, o)
last = json.loads(open(os.path.join(PD, A + ".jsonl")).read().splitlines()[-1])
ok("3 a custom-title record was appended", last["type"] == "custom-title" and last["customTitle"] == "Parser rework" and last["sessionId"] == A, last)
rc, o = run("--list", "rework")
ok("4 --list now finds it by the custom title, marked with a star", "★" in o and "Sessions (1)" in o, o)
rc, o = run("-", "x")
ok("5 ambiguous selector -> rc 2", rc == 2 and "ambiguous" in o, o)
rc, o = run("zzz-nothing", "x")
ok("6 no match -> rc 2", rc == 2 and "no session matches" in o, o)
rc, o = run("bbbbbbbb", "  ")
ok("7 empty title -> rc 2", rc == 2 and "empty title" in o, o)
rc, o = run("bbbbbbbb", "Docs by id")
ok("8 rename by UUID prefix", rc == 0, o)
rc, o = run("--help")
ok("9 --help prints usage, rc 0", rc == 0 and "Usage" in o, o)
print(f"rename-session: {P} pass, {F} fail")
sys.exit(1 if F else 0)
