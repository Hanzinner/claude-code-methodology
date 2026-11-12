#!/usr/bin/env python3
"""agent-status: PostToolUse -> WORKING; Stop -> DONE, or ASK with the question when the last reply has "ASK:";
no identity -> no file. AS=<path> tests another copy. Sandbox: temp HOME."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
AS = os.environ.get("AS", os.path.join(HERE, "..", "hooks", "agent-status.py"))
T = tempfile.mkdtemp(prefix="as-test-")
H = f"{T}/home"; os.makedirs(f"{H}/.claude/agent-identity")
open(f"{H}/.claude/agent-identity/s1", "w").write("/x/Agents/Alpha-Dev")
P = F = 0


def ok(name, cond, out=""):
    global P, F
    if cond: P += 1
    else: F += 1; print("FAIL:", name, str(out)[:300])


def run(sid, ev, text=None):
    tp = f"{T}/t.jsonl"
    with open(tp, "w") as f:
        f.write(json.dumps({"type": "user", "message": {"content": "go"}}) + "\n")
        if text is not None:
            f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}) + "\n")
    subprocess.run([sys.executable, AS], input=json.dumps({"session_id": sid, "hook_event_name": ev, "transcript_path": tp}),
                   capture_output=True, text=True, env={**os.environ, "HOME": H, "CLAUDE_METHODOLOGY_CONF": "/nonexistent"})
    p = f"{H}/.claude/agent-status/Alpha-Dev.json"
    return json.load(open(p)) if os.path.exists(p) else None


s = run("s1", "PostToolUse")
ok("1 PostToolUse -> WORKING", s and s["state"] == "WORKING" and s["agent"] == "Alpha-Dev" and s["updated"] > 0, s)
s = run("s1", "Stop", "All finished.")
ok("2 Stop, plain reply -> DONE", s and s["state"] == "DONE" and s["ask"] == "", s)
s = run("s1", "Stop", "Two options.\nASK: ship on friday or monday?\nthanks")
ok("3 Stop with ASK: -> ASK + question", s and s["state"] == "ASK" and s["ask"] == "ship on friday or monday?", s)
os.remove(f"{H}/.claude/agent-status/Alpha-Dev.json")
s = run("nobody", "PostToolUse")
ok("4 no identity -> no file (silent)", s is None and not os.path.exists(f"{H}/.claude/agent-status/nobody.json"), s)
s = run("s1", "UserPromptSubmit")
ok("5 other event -> nothing written", s is None, s)
print(f"agent-status: {P} pass, {F} fail"); raise SystemExit(1 if F else 0)
