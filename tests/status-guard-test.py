#!/usr/bin/env python3
"""status-guard: a coordinator states a story state / "waiting on you" without a source run in the turn -> BLOCK; with story_status
-> silent; "before prod" without B<n> -> flag; agent not in the list / list empty -> silent. SG=<path> tests another copy.
Sandbox: temp HOME, no config file, CCM_* env per case."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SG = os.environ.get("SG", os.path.join(HERE, "..", "hooks", "status-guard.py"))
T = tempfile.mkdtemp(prefix="sg-test-")
H = f"{T}/home"; os.makedirs(f"{H}/.claude/agent-identity")
open(f"{H}/.claude/agent-identity/s-hq", "w").write("/x/Agents/Alpha-HQ")
open(f"{H}/.claude/agent-identity/s-dev", "w").write("/x/Agents/Alpha-Dev")
P = F = 0
n = 0


def ok(name, cond, out=""):
    global P, F
    if cond: P += 1
    else: F += 1; print("FAIL:", name, str(out)[:300])


def run(sid, text, tools=(), active=False, agents="Alpha-HQ", lang=""):
    global n
    n += 1
    tp = f"{T}/t{n}.jsonl"
    rows = [{"type": "user", "message": {"role": "user", "content": "what about S68?"}}]
    for t in tools:
        rows.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": t}}]}})
        rows.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}})
    rows.append({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    open(tp, "w").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    env = {**os.environ, "HOME": H, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_STATUS_GUARD_AGENTS": agents,
           "CCM_LANG_EXTRA": lang, "CCM_HUMAN_NAME": "Sam"}
    r = subprocess.run([sys.executable, SG], input=json.dumps({"session_id": sid, "transcript_path": tp, "stop_hook_active": active}),
                       capture_output=True, text=True, env=env)
    return r.stdout


o = run("s-hq", "- S68 separate address for staff.\nCode not started: split address, own session.")
ok("1 'Code not started' under the S68 line, no source -> BLOCK", '"decision": "block"' in o and "not started" in o, o)
o = run("s-hq", "- S68 separate address.\nCode not started.", tools=["/x/scripts/story_status.py Alpha S68"])
ok("2 same after story_status -> silent", o == "", o)
o = run("s-hq", "- S68 separate address.\nCode not started.", tools=["grep -c '^- ⏳' Project-Alpha/ROADMAP.md; cat Agents/Alpha-HQ/agent-TODO.md"])
ok("3 roadmap and own TODO are not a source -> BLOCK", '"decision": "block"' in o, o)
o = run("s-hq", "Both agents are idle because everything is waiting on you.")
ok("4 'waiting on you' without blockers.py -> BLOCK", '"decision": "block"' in o, o)
o = run("s-hq", "Everything is waiting on you.", tools=["/x/scripts/blockers.py list Alpha"])
ok("4b after blockers.py -> silent", o == "", o)
o = run("s-hq", "S78 is done when the push arrives after a bid.")
ok("5 'done when ...' is a condition, not a state -> silent", o == "", o)
o = run("s-hq", "> Alpha-Dev: S68 done\nForwarded to QA.")
ok("6 a quoted message of someone else does not count -> silent", o == "", o)
o = run("s-hq", "Story S28 is closed.", active=True)
ok("7 stop_hook_active (already blocked once) -> no second block", '"decision"' not in o, o)
o = run("s-dev", "- S68 separate address.\nCode not started.")
ok("8 agent not in the list -> silent", o == "", o)
o = run("s-hq", "- S68 separate address.\nCode not started.", agents="")
ok("8b empty list = guard off -> silent", o == "", o)
o = run("s-hq", "Domain and server - in one go before prod.", tools=["git log --oneline -3"])
fl = f"{H}/.claude/status-guard-flags/s-hq"
ok("9 'before prod' without B<n> -> flag, not block", o == "" and os.path.exists(fl) and "before prod" in open(fl).read() and "blocker_add" in open(fl).read(), o)
os.remove(fl); run("s-hq", "Domain is B7, server is B8: before prod.")
ok("9b with blocker numbers -> no flag", not os.path.exists(fl))
o = run("s-hq", "- S68 окрема адреса.\nКод не почато.")
ok("10 Ukrainian phrase is ignored when uk is off -> silent", o == "", o)
o = run("s-hq", "- S68 окрема адреса.\nКод не почато.", lang="uk")
ok("10b ... and caught when CCM_LANG_EXTRA=uk -> BLOCK", '"decision": "block"' in o, o)
print(f"status-guard: {P} pass, {F} fail"); raise SystemExit(1 if F else 0)
