#!/usr/bin/env python3
"""fable-gate: Agent/Workflow without an explicit model or on a forbidden one -> deny. FG=<path> tests another copy.
Sandbox: temp HOME, no config file; forbidden list comes from CCM_FORBIDDEN_SUBAGENT_MODELS."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
FG = os.environ.get("FG", os.path.join(HERE, "..", "hooks", "fable-gate.py"))
ENV = {**os.environ, "HOME": tempfile.mkdtemp(prefix="fg-test-"), "CLAUDE_METHODOLOGY_CONF": "/nonexistent",
       "CCM_FORBIDDEN_SUBAGENT_MODELS": "fable", "HANZ_TEST": "1"}
P = F = 0


def g(tool, inp, env=ENV):
    r = subprocess.run([sys.executable, FG], input=json.dumps({"session_id": "s", "tool_name": tool, "tool_input": inp}),
                       capture_output=True, text=True, env=env)
    return "deny" if '"deny"' in r.stdout else ("pass" if r.returncode == 0 and not r.stdout else "ERR " + r.stderr[-200:])


for n, tool, inp, want in (
    ("Agent without model", "Agent", {"prompt": "x", "description": "d"}, "deny"),
    ("Agent model fable", "Agent", {"prompt": "x", "model": "fable"}, "deny"),
    ("Agent model sonnet", "Agent", {"prompt": "x", "model": "sonnet"}, "pass"),
    ("Agent model opus", "Agent", {"prompt": "x", "model": "opus"}, "pass"),
    ("Workflow: agent() without model", "Workflow", {"script": "export const meta={name:'a'}\nawait agent('x', {label:'r'})"}, "deny"),
    ("Workflow: model: 'fable'", "Workflow", {"script": "await agent('x', {model: 'fable'})"}, "deny"),
    ("Workflow: model: 'sonnet'", "Workflow", {"script": "await agent('x', {model: 'sonnet', label:'r'})"}, "pass"),
    ("Workflow named, no script", "Workflow", {"name": "review"}, "pass"),
    ("Bash is not touched", "Bash", {"command": "echo fable"}, "pass"),
):
    got = g(tool, inp)
    if got == want: P += 1
    else: F += 1; print(f"FAIL: {n}: {got} (want {want})")
got = g("Agent", {"prompt": "x"}, {**ENV, "CCM_FORBIDDEN_SUBAGENT_MODELS": ""})
if got == "pass": P += 1
else: F += 1; print("FAIL: empty forbidden list must switch the gate off:", got)
r = subprocess.run([sys.executable, FG], input="", capture_output=True, text=True, env=ENV)
if r.returncode == 0 and not r.stdout: P += 1
else: F += 1; print("FAIL: empty stdin")
print(f"fable-gate: {P} pass, {F} fail"); raise SystemExit(1 if F else 0)
