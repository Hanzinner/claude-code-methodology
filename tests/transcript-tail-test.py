#!/usr/bin/env python3
"""transcript_tail: last-turn extraction and live-branch detection on synthetic transcripts. TT=<path> tests another copy."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
TT = os.environ.get("TT", os.path.join(HERE, "..", "scripts", "transcript_tail.py"))
T = tempfile.mkdtemp(prefix="tt-test-")
ENV = {**os.environ, "HOME": T, "CLAUDE_METHODOLOGY_CONF": "/nonexistent"}
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def user(text, uid): return {"type": "user", "uuid": uid, "message": {"content": text}}
def tool_res(uid): return {"type": "user", "uuid": uid, "message": {"content": [{"type": "tool_result", "content": "x"}]}}
def asst(uid, parent): return {"type": "assistant", "uuid": uid, "parentUuid": parent, "message": {"content": [{"type": "text", "text": "a"}]}}


def write(name, recs):
    p = os.path.join(T, name)
    with open(p, "w") as f:
        for r in recs: f.write(json.dumps(r) + "\n")
    return p


def run(code, *args):
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import transcript_tail as t\n%s" % (os.path.dirname(TT), code), *args],
                       capture_output=True, text=True, env=ENV)
    return r.stdout + (f"[rc {r.returncode}] {r.stderr}" if r.returncode else "")


p = write("a.jsonl", [user("first", "1"), asst("2", "1"), user("second", "3"), tool_res("4"), asst("5", "4")])
o = run("import json\nprint(len([l for l in t.lines(sys.argv[1], t._is_human) if l]))", p)
ok("1 lines() starts at the LAST human message", o.strip() == "3", o)
ok("2 tool_result is not a human message", "second" in subprocess.run([sys.executable, TT, p], capture_output=True, text=True, env=ENV).stdout)
cli = subprocess.run([sys.executable, TT, p], capture_output=True, text=True, env=ENV)
ok("3 CLI prints the last turn only", len(cli.stdout.split()) and len([l for l in cli.stdout.splitlines() if l.strip()]) == 3 and "first" not in cli.stdout, cli.stdout)
p2 = write("b.jsonl", [asst("2", "1"), asst("3", "2")])
o = run("print(len([l for l in t.lines(sys.argv[1], lambda o: False) if l]))", p2)
ok("4 no human message -> the whole file", o.strip() == "2", o)
o = run("print(t.lines('/nonexistent/x.jsonl', lambda o: True))")
ok("5 missing file -> empty list, no crash", o.strip() == "[]", o)
# bigger than one 2 MB block: the last human message sits before 3 MB of filler
big = [user("old", "u0")] + [{"type": "assistant", "uuid": f"f{i}", "message": {"content": [{"type": "text", "text": "z" * 900}]}} for i in range(3500)]
p3 = write("c.jsonl", big)
ok("5b fixture is bigger than 2 MB", os.path.getsize(p3) > 2 * 1024 * 1024)
o = run("print(len([l for l in t.lines(sys.argv[1], t._is_human) if l]))", p3)
ok("6 last human message found across a block boundary", o.strip() == "3501", o)
# live_branch
boundary = {"type": "system", "subtype": "compact_boundary", "uuid": "B"}
live = [boundary, {"type": "user", "uuid": "L1", "parentUuid": "B", "message": {"content": "hi"}}, asst("L2", "L1")]
ghost = [asst("G1", "OLD")]
p4 = write("d.jsonl", [user("old", "OLD")] + live + ghost)
o = run("import json\nr = t.live_branch(sys.argv[1]); print(len(r['live']), r['last_is_ghost'])", p4)
ok("7 live_branch: ghost message after the boundary is detected", o.strip() == "2 True", o)
p5 = write("e.jsonl", [user("old", "OLD")] + live)
o = run("r = t.live_branch(sys.argv[1]); print(r['last_is_ghost'])", p5)
ok("8 live_branch: only the live branch -> no ghost", o.strip() == "False", o)
o = run("print(t.live_branch(sys.argv[1]))", p)
ok("9 live_branch: no compaction -> None", o.strip() == "None", o)
print(f"transcript-tail: {P} pass, {F} fail")
sys.exit(1 if F else 0)
