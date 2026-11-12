#!/usr/bin/env python3
"""pause-guard: a pause offer in the final paragraph blocks, elsewhere only flags; quotes/code/negations stay silent.
Runs the repo copy; PG=<path> tests another one. Sandbox: temp HOME, no config file, CCM_LANG_EXTRA set per case."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
PG = os.environ.get("PG", os.path.join(HERE, "..", "hooks", "pause-guard.py"))
T = tempfile.mkdtemp(prefix="pg-test-")
P = F = 0
n = 0


def ok(name, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", name, str(o)[:300])


def run(text, lang="", active=False):
    global n
    n += 1
    home = f"{T}/h{n}"; os.makedirs(home)
    tp = f"{home}/t.jsonl"
    with open(tp, "w") as f:
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}) + "\n")
    env = {**os.environ, "HOME": home, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_LANG_EXTRA": lang,
           "CCM_HUMAN_NAME": "Sam"}
    inp = {"session_id": "sidA", "transcript_path": tp, "stop_hook_active": active}
    r = subprocess.run([sys.executable, PG], input=json.dumps(inp), capture_output=True, text=True, env=env)
    fl = f"{home}/.claude/pause-guard-flags/sidA"
    flag = open(fl).read() if os.path.exists(fl) else ""
    return r.stdout, flag, r.returncode


BLOCKS = ["Done, tests pass.\n\nShall we call it a day?",
          "Refactor is in.\n\nWant to pick this up tomorrow?",
          "All merged.\n\nYou should take a break, you've been at it for hours.",
          "Fixed.\n\nThat's enough for today.",
          "Fixed.\n\nShall we stop here for today?",
          "Looks good.\n\nGet some rest!",
          "Okay.\n\nGood stopping point, I think.",
          "Done.\n\nTake care of yourself.",
          "Done.\n\nWe could continue tomorrow with fresh eyes.",
          "Done.\n\nGo get some sleep, it can wait until the morning."]
for i, t in enumerate(BLOCKS):
    o, fl, rc = run(t)
    ok(f"block {i}: {t[-40:]!r}", '"decision": "block"' in o and "Sam" in o and rc == 0, o)

SILENT = ["Migrated the table. The nightly job will pick this up tomorrow at 03:00 UTC.",
          "Use `shall we call it a day` as a test string.\n\nNext: wire the hook.",
          "> Shall we call it a day?\n\nThat quote is from the transcript; the fix is below.",
          "There is no need to call it a day, the remaining step is short.\n\nRunning it now.",
          "The retry loop will take a break of 5 seconds between attempts.",
          "Break statements exit the loop early.\n\nNext I'll add the test.",
          "```\nlet's call it a day\n```\n\nThe snippet above is what the log contained.",
          "I'll continue with the schema next.\n\nStep two is the index.",
          "He said \"good stopping point\" in the review.\n\nI changed the parser."]
for i, t in enumerate(SILENT):
    o, fl, rc = run(t)
    ok(f"silent {i}: {t[:40]!r}", o == "" and fl == "" and rc == 0, (o, fl))

o, fl, _ = run("Let's call it a day here, we covered a lot.\n\nNext: run the suite and paste the output.")
ok("offer outside the final paragraph → flag, no block", o == "" and "pause-guard" in fl, (o, fl))
o, fl, _ = run("Done.\n\nShall we call it a day?", active=True)
ok("stop_hook_active → flag only", o == "" and "Sam decides" in fl, (o, fl))
o, fl, _ = run("Done.\n\nНа сьогодні досить?", lang="")
ok("Ukrainian phrase with lang off → silent", o == "" and fl == "", (o, fl))
o, fl, _ = run("Готово.\n\nНа сьогодні досить?", lang="uk")
ok("Ukrainian phrase with uk on → block", '"decision": "block"' in o, o)
o, fl, _ = run("Готово.\n\nНе варто відпочивати зараз, лишився один крок.", lang="uk")
ok("Ukrainian negated → silent", o == "", o)
r = subprocess.run([sys.executable, PG], input="not json", capture_output=True, text=True,
                   env={**os.environ, "HOME": T, "CLAUDE_METHODOLOGY_CONF": "/nonexistent"})
ok("garbage stdin → rc 1 with a trace, no block output", r.returncode == 1 and r.stdout == "", r)
print(f"pause-guard: {P} pass, {F} fail"); sys.exit(1 if F else 0)
