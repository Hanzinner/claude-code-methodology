#!/usr/bin/env python3
"""mistakes-format-gate: off-format / header entries are denied on Edit, hinted after Bash.
Runs against the repo copy; MG=<path> tests an installed one. Sandbox only: HOME and the journal are temp."""
import contextlib, io, json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.realpath(__file__))
MG = os.environ.get("MG", os.path.join(HERE, "..", "hooks", "mistakes-format-gate.py"))
T = tempfile.mkdtemp(prefix="mg-test-")
J = f"{T}/MISTAKES.md"
home = f"{T}/h"; os.makedirs(f"{home}/.claude/agent-identity")
open(f"{home}/.claude/agent-identity/sidA", "w").write("/x/Agents/Ops-agent")
ENV = {**os.environ, "HOME": home, "CCM_MISTAKES": J, "CLAUDE_METHODOLOGY_CONF": "/nonexistent"}
today = time.strftime("%Y-%m-%d")
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def write(txt): open(J, "w").write(txt)


def hook(payload):
    r = subprocess.run([sys.executable, MG], input=json.dumps(payload), capture_output=True, text=True, env=ENV)
    return r.stdout + (f"[rc {r.returncode}] {r.stderr}" if r.returncode else "")


def bash(cmd=f"python3 - <<'EOF'\np='MISTAKES.md'\nEOF", sid="sidA"):
    return hook({"hook_event_name": "PostToolUse", "session_id": sid, "tool_name": "Bash", "tool_input": {"command": cmd}})


def edit(old_s, new_s):
    return hook({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                 "tool_input": {"file_path": J, "old_string": old_s, "new_string": new_s}})


good = f"## {today} · Ops-agent · fine\n**What happened:** x\n**Status:** OPEN\n"
bad = f"## {today} · Ops-agent · no status\n**What happened:** x\n"
foreign = f"## {today} · Other-agent · someone else's, no status\n**What happened:** x\n"
write("# MISTAKES\n\n" + bad); o = bash()
ok("1 own entry without Status via Bash → hint", "no **Status:**" in o and "PostToolUse" in o, o)
write("# MISTAKES\n\n" + good); o = bash()
ok("2 own entry on format → silent", o == "", o)
write("# MISTAKES\n\n" + foreign + good); o = bash()
ok("3 someone else's bad entry → not mine", o == "", o)
write("# MISTAKES\n\n" + bad); o = bash(cmd="ls -la")
ok("4 command not touching the journal → silent", o == "", o)
write("# MISTAKES\n\n## 2026-01-01 · Ops-agent · old, no status\n**What happened:** x\n"); o = bash()
ok("5 entry older than 7 days → silent", o == "", o)
HEAD = "# MISTAKES\n\n| class | example: grep -E '^## 20' |\n\n## Entry format\ntemplate\n\n"
write(HEAD + "## 2026-01-01 · A · old\n**Status:** OPEN\n")
o = edit("| class |", good + "| class |"); ok("6 Edit puts an entry into the header → deny", '"deny"' in o and "header" in o, o)
o = edit("## 2026-01-01", good + "## 2026-01-01"); ok("6b Edit puts it after the anchor → allowed", o == "", o)
write(good + HEAD); o = bash(); ok("6c Bash left an entry in the header → hint", "header" in o, o)
write(HEAD.replace("## Entry format", "## Something else") + good); o = edit("template", "template2"); ok("6d no anchor → no judgement", o == "", o)
write(HEAD); o = edit("template\n", "template\n\n" + f"## {today} · X · gist\n**Статус:** OPEN\n")
ok("7 Ukrainian status line accepted", o == "", o)
o = edit("template\n", "template\n\n## 12.11.2026 · X · gist\n**Status:** OPEN\n")
ok("8 off-format heading → deny with template", '"deny"' in o and "YYYY-MM-DD" in o, o)
print(f"mistakes-format-gate: {P} pass, {F} fail"); sys.exit(1 if F else 0)
