#!/usr/bin/env python3
"""ai-studio-to-md: converts AI Studio exports to Markdown. AS=<path> tests another copy."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
AS = os.environ.get("AS", os.path.join(HERE, "..", "scripts", "ai-studio-to-md"))
T = tempfile.mkdtemp(prefix="as-test-")
ENV = {**os.environ, "HOME": T, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_HUMAN_NAME": "Dana"}
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


export = {"chunkedPrompt": {"chunks": [
    {"role": "user", "text": "What is 2+2?"},
    {"role": "model", "text": "Thinking...", "isThought": True},
    {"role": "model", "text": "It is 4."},
    {"role": "user", "inlineFile": {"mimeType": "image/png"}},
    {"role": "user", "driveDocument": {"name": "Plan.doc"}},
    {"role": "model", "text": "   "},
]}}
src = os.path.join(T, "chat1")
json.dump(export, open(src, "w"))
json.dump({"other": 1}, open(os.path.join(T, "plain.json"), "w"))
os.makedirs(os.path.join(T, "sub"))
json.dump(export, open(os.path.join(T, "sub", "chat2"), "w"))


def run(*a):
    r = subprocess.run([sys.executable, AS, *a], capture_output=True, text=True, env=ENV)
    return r.returncode, r.stdout + r.stderr


rc, o = run(src)
md = open(os.path.join(T, "chat1.md")).read()
ok("1 single file converts, rc 0", rc == 0 and "chat1.md" in o, o)
ok("2 user turn labelled with CCM_HUMAN_NAME, model with Gemini", "**Dana:** What is 2+2?" in md and "**Gemini:** It is 4." in md, md)
ok("3 thought chunk and empty chunk are dropped", "Thinking" not in md and md.count("**Gemini:**") == 1, md)
ok("4 attachments become placeholders", "[attached file: image/png]" in md and "[Google Drive: Plan.doc]" in md, md)
ok("5 no trailing separator", not md.rstrip().endswith("---"), md[-20:])
rc, o = run(T)
ok("6 folder mode converts both exports, skips the non-export json", rc == 0 and "Done: 2 file(s)." in o and os.path.exists(os.path.join(T, "sub", "chat2.md")) and not os.path.exists(os.path.join(T, "plain.md")), o)
E = tempfile.mkdtemp(prefix="as-empty-")
rc, o = run(E)
ok("7 folder without exports -> says so", "No files with chunkedPrompt found." in o, o)
rc, o = run(os.path.join(T, "nope"))
ok("8 missing path -> rc 2", rc == 2 and "does not exist" in o, o)
env2 = {k: v for k, v in ENV.items() if k != "CCM_HUMAN_NAME"}
subprocess.run([sys.executable, AS, src], env=env2, capture_output=True)
ok("9 default human name -> 'User' label", "**User:**" in open(os.path.join(T, "chat1.md")).read())
print(f"ai-studio-to-md: {P} pass, {F} fail")
sys.exit(1 if F else 0)
