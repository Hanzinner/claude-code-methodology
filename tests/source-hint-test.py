#!/usr/bin/env python3
"""source-hint: a legal query → hint with official addresses from the results; other query → silent; once per 30 min per session.
SH=<path> tests another copy. Sandbox: temp HOME, no config, CCM_LANG_EXTRA set per case."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SH = os.environ.get("SH", os.path.join(HERE, "..", "hooks", "source-hint.py"))
HOME = tempfile.mkdtemp(prefix="sh-test-"); P = F = 0
ENV = {**os.environ, "HOME": HOME, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_HUMAN_NAME": "Sam"}


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def run(sid, tool, query, resp, lang=""):
    r = subprocess.run([sys.executable, SH], input=json.dumps({"session_id": sid, "tool_name": tool, "tool_input": {"query": query}, "tool_response": resp}),
                       capture_output=True, text=True, env={**ENV, "CCM_LANG_EXTRA": lang})
    return r.stdout


RES = "1. IEC — https://www.canadavisa.com/iec.html\n2. Who can apply — https://www.canada.ca/en/immigration/iec/eligibility.html\n3. https://moving2canada.com/x"
o = run("s1", "mcp__search__search", "International Experience Canada eligible countries work holiday visa", RES)
ok("legal query + official address in the results → hint with it", "source-hint" in o and "https://www.canada.ca/en/immigration/iec/eligibility.html" in o
   and "canadavisa" not in o.split("Official in the results")[1] and "Sam" in o, o)
ok("address without the trailing \\n of the JSON string", "eligibility.html\\n" not in o and "eligibility.html." in o, o)
ok("repeat in the same session within 30 min → silent", run("s1", "mcp__search__search", "canada work permit quota", RES) == "")
o = run("s2", "WebSearch", "Portugal D8 visa requirements", "https://portugalhandbook.com/d8 https://reddit.com/r/x")
ok("no official pages → says so, names the sites found", "NO official pages" in o and "portugalhandbook.com" in o, o)
ok("not a legal query → silent", run("s3", "mcp__search__search", "python flock example", RES) == "")
ok("other tool → silent", run("s4", "WebFetch", "canada visa", RES) == "")
r = subprocess.run([sys.executable, SH], input="", capture_output=True, text=True, env=ENV)
ok("empty stdin → rc 0, silent", r.returncode == 0 and r.stdout == "")
ok("uk term with uk off → silent", run("s5", "WebSearch", "віза до Португалії", RES, lang="") == "")
ok("uk term with uk on → hint", "source-hint" in run("s6", "WebSearch", "віза до Португалії", RES, lang="uk"))
print(f"source-hint: {P} pass, {F} fail"); sys.exit(1 if F else 0)
