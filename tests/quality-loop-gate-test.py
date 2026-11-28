#!/usr/bin/env python3
"""quality-loop gate.py: a finding is done only with every artifact; pin_verified in prose or with verdict=FAIL is
refused; --concurrency also needs interleavings; trailer refuses an incomplete finding; the store and state-path sit
under HOME/.claude/quality-loop/<sha1 of the git toplevel>/, never in the tree; outside a git repo it refuses.
GATE=<path> tests another copy. Sandbox: temp HOME and a temp git repo; nothing outside the temp dir."""
import hashlib, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
GATE = os.environ.get("GATE", os.path.join(HERE, "..", "skills", "quality-loop", "gate.py"))
R = tempfile.mkdtemp(prefix="qlgate-test-")
HOME, REPO, BARE = f"{R}/home", f"{R}/repo", f"{R}/not-a-repo"
for d in (HOME, REPO, BARE): os.makedirs(d)
subprocess.run(["git", "init", "-q", REPO], check=True)
TOP = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=REPO, capture_output=True, text=True).stdout.strip()
LOOP = os.path.join(HOME, ".claude", "quality-loop", hashlib.sha1(TOP.encode()).hexdigest())
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def run(*a, cwd=REPO):
    env = {**os.environ, "HOME": HOME, "USERPROFILE": HOME, "PYTHONDONTWRITEBYTECODE": "1",
           "GIT_CEILING_DIRECTORIES": R}
    r = subprocess.run([sys.executable, GATE, *a], cwd=cwd, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


ALL = {"repro": "FAILED test_x: expected 1 got 2", "class": "off-by-one on range end",
       "siblings": "range_a: same fix | range_b: clean", "fix": "use <= at x.py:10",
       "pin_verified": "expected=1 observed=1 verdict=PASS", "regression": "42 passed, 0 failed"}

try:
    rc, out = run("start", "F1", "off by one in range")
    ok("1 start: lists the six required artifacts", rc == 0 and all(a in out for a in ALL), out)
    ok("2 the record lives under HOME/.claude/quality-loop/<sha1>/findings", os.path.isfile(f"{LOOP}/findings/F1.json"))
    ok("3 nothing written into the tree", sorted(os.listdir(REPO)) == [".git"], os.listdir(REPO))

    rc, out = run("done", "F1")
    ok("4 done with nothing recorded -> rc 1 and names the gaps", rc == 1 and "siblings" in out and "repro" in out, out)
    rc, out = run("trailer", "F1")
    ok("5 trailer of an incomplete finding is refused", rc != 0 and "refusing" in out, out)

    rc, out = run("record", "F1", "pin_verified", "mutation-verified, works")
    ok("6 pin_verified in prose is rejected", rc != 0 and "REJECTED" in out, out)
    rc, out = run("record", "F1", "pin_verified", "expected=1 observed=2 verdict = FAIL")
    ok("7 pin_verified with verdict=FAIL is rejected", rc != 0 and "verdict=FAIL" in out, out)
    rc, out = run("record", "F1", "interleavings", "a then b")
    ok("8 interleavings unknown without --concurrency", rc != 0 and "unknown artifact" in out, out)

    for k, v in ALL.items():
        rc, out = run("record", "F1", k, v)
        ok(f"9 record {k}", rc == 0, out)
    rc, out = run("done", "F1")
    ok("10 done with every artifact -> rc 0", rc == 0 and "complete" in out, out)
    rc, out = run("trailer", "F1")
    ok("11 trailer carries class, siblings, verified-by, regression",
       rc == 0 and "Class: off-by-one" in out and "Siblings-checked: range_a" in out
       and "Verified-by: expected=1 observed=1 verdict=PASS" in out and "Regression: 42 passed" in out, out)

    rc, out = run("start", "F2", "race on purge", "--concurrency")
    ok("12 --concurrency asks for interleavings before the fix", rc == 0 and "interleavings" in out and "BEFORE" in out, out)
    for k, v in ALL.items(): run("record", "F2", k, v)
    rc, out = run("done", "F2")
    ok("13 concurrency finding without interleavings is not done", rc == 1 and "interleavings" in out, out)
    run("record", "F2", "interleavings", "A:read B:write A:write -> lost update")
    rc, out = run("done", "F2")
    ok("14 with interleavings it is done", rc == 0, out)
    rc, out = run("trailer", "F2")
    ok("15 concurrency trailer has Interleavings", "Interleavings: A:read" in out, out)

    rc, out = run("list")
    ok("16 list shows F1 and F2 as DONE", rc == 0 and out.count("DONE") == 2, out)

    rc, out = run("state-path")
    ok("17 state-path = <loop dir>/state.md, folder created, outside the tree",
       rc == 0 and out.strip() == os.path.join(LOOP, "state.md") and os.path.isdir(LOOP)
       and not out.strip().startswith(TOP), out)

    rc, out = run("done", "F9")
    ok("18 an unknown finding is refused with the start hint", rc != 0 and "gate.py start F9" in out, out)
    rc, out = run("state-path", cwd=BARE)
    ok("19 outside a git repo -> refused", rc != 0 and "not inside a git repository" in out, out)
finally:
    shutil.rmtree(R, ignore_errors=True)

print(f"quality-loop-gate: {P} pass, {F} fail")
sys.exit(1 if F else 0)
