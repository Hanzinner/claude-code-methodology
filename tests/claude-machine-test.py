#!/usr/bin/env python3
"""claude_machine: wraps `claude -p`, logs usage, returns only the answer text. Uses a FAKE claude binary (no network,
no real claude). CM=<path> tests another copy."""
import json, os, stat, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
CM = os.environ.get("CM", os.path.join(HERE, "..", "scripts", "claude_machine.py"))
T = tempfile.mkdtemp(prefix="cm-test-")
LOG = os.path.join(T, "usage.jsonl")
ARGS = os.path.join(T, "args.txt")
FAKE = os.path.join(T, "fakeclaude")
open(FAKE, "w").write('''#!/usr/bin/env python3
import json, os, sys
open(os.environ["FAKE_ARGS"], "w").write(" ".join(sys.argv[1:]) + "\\n" + sys.stdin.read())
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "plain":
    print("not json at all"); sys.exit(3)
res = {"type": "result", "result": "the answer", "is_error": mode == "err",
       "modelUsage": {} if mode == "nousage" else {"m1": {"inputTokens": 5, "outputTokens": 7, "cacheReadInputTokens": 1, "cacheCreationInputTokens": 2, "costUSD": 0.01}}}
print(json.dumps([{"type": "system"}, res]))
''')
os.chmod(FAKE, 0o755)
ENV = {**os.environ, "HOME": T, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CLAUDE_BIN": FAKE, "MACHINE_USAGE": LOG, "FAKE_ARGS": ARGS, "HANZ_TEST": "1"}
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def run(*a, mode="ok", stdin="in"):
    r = subprocess.run([sys.executable, CM, *a], input=stdin, capture_output=True, text=True, env={**ENV, "FAKE_MODE": mode})
    return r


r = run("tagA", "-p", "--output-format", "text", "hello")
ok("1 stdout is only the answer text", r.stdout == "the answer\n" and r.returncode == 0, (r.stdout, r.stderr))
a = open(ARGS).read()
ok("2 adds --no-session-persistence and json output, drops the caller's --output-format", "--no-session-persistence --output-format json" in a and "text" not in a.split("\n")[0], a)
ok("3 stdin is passed through", a.split("\n", 1)[1].strip() == "in", a)
rec = [json.loads(l) for l in open(LOG)]
ok("4 one usage line with tag, model and tokens", len(rec) == 1 and rec[0]["tag"] == "tagA" and rec[0]["model"] == "m1" and rec[0]["i"] == 5 and rec[0]["o"] == 7 and rec[0]["usd"] == 0.01, rec)
r = run("tagB", "-p", "x", mode="err")
ok("5 is_error answer -> rc 1", r.returncode == 1, r.returncode)
r = run("tagC", "-p", "x", mode="nousage")
ok("6 no modelUsage -> warning on stderr, no new log line", "no modelUsage" in r.stderr and sum(1 for _ in open(LOG)) == 2, r.stderr)
r = run("tagD", "-p", "x", mode="plain")
ok("7 non-JSON output is passed through with claude's rc", r.stdout.strip() == "not json at all" and r.returncode == 3, (r.stdout, r.returncode))
r = run("tagE", "x")
ok("8 missing -p -> usage, rc 2", r.returncode == 2 and "usage" in r.stderr, r.stderr)
r = run()
ok("9 no arguments -> rc 2", r.returncode == 2, r.stderr)
print(f"claude-machine: {P} pass, {F} fail")
sys.exit(1 if F else 0)
