#!/usr/bin/env python3
"""ai_studio_to_md: AI Studio JSON exports -> Markdown next to them. Thoughts skipped, attachments as placeholders, the human
labelled with CCM_HUMAN_NAME, non-exports left alone, a dotted name keeps its own .md. AS=<path> tests another copy. Temp dirs only."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
AS = os.environ.get("AS", os.path.join(HERE, "..", "scripts", "ai_studio_to_md.py"))
T = tempfile.mkdtemp(prefix="as-test-")
ENV = {**os.environ, "HOME": T, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_TEST": "1", "CCM_HUMAN_NAME": "Alex"}
D = os.path.join(T, "exports")
os.makedirs(os.path.join(D, "sub"))
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:400])


def export(path, chunks):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"runSettings": {"model": "x"}, "chunkedPrompt": {"chunks": chunks}}, f)


export(os.path.join(D, "Trip plan"), [
    {"role": "user", "text": "Plan a trip"},
    {"role": "model", "text": "secret reasoning", "isThought": True},
    {"role": "model", "text": "Day 1: walk."},
    {"role": "user", "inlineFile": {"mimeType": "image/png"}},
    {"role": "user", "driveDocument": {"id": "abc"}},
    {"role": "model", "text": "   "},
])
export(os.path.join(D, "sub", "chat v1.2"), [{"role": "user", "text": "first"}])
export(os.path.join(D, "sub", "chat v1.3"), [{"role": "user", "text": "second"}])
export(os.path.join(D, "notes.json"), [{"role": "tool", "text": "a tool line"}])
open(os.path.join(D, "plain.txt"), "w").write("just text, no export\n")
json.dump({"other": 1}, open(os.path.join(D, "other.json"), "w"))
open(os.path.join(D, "broken"), "w").write('{"chunkedPrompt": [')


def run(*a):
    r = subprocess.run([sys.executable, AS, *a], capture_output=True, text=True, env=ENV, cwd=T)
    return r.returncode, r.stdout + r.stderr


def md(*p):
    try:
        return open(os.path.join(D, *p), encoding="utf-8").read()
    except OSError:
        return None


rc, o = run(D)
ok("1 folder: rc 0, 4 exports converted (recursively)", rc == 0 and "Done: 4 file(s)." in o, o)
t = md("Trip plan.md") or ""
ok("2 dialogue with labels: the human by CCM_HUMAN_NAME, the model as Gemini, separators between turns",
   t.startswith("# Trip plan\n") and "**Alex:** Plan a trip" in t and "**Gemini:** Day 1: walk." in t and "\n---\n" in t, t)
ok("3 thoughts and empty text skipped, nothing trailing", "secret reasoning" not in t and not t.rstrip().endswith("---") and t.count("**Gemini:**") == 1, t)
ok("4 attachments become placeholders", "_[attached file: image/png]_" in t and "_[Google Drive: Google Drive document]_" in t, t)
ok("5 dotted names keep their own .md (no overwrite of one by the other)",
   "first" in (md("sub", "chat v1.2.md") or "") and "second" in (md("sub", "chat v1.3.md") or ""), os.listdir(os.path.join(D, "sub")))
ok("6 .json -> .md beside it, an unknown role is labelled by its name", "**tool:** a tool line" in (md("notes.md") or ""), md("notes.md"))
ok("7 not an export (text, other JSON, broken JSON) -> silent, no .md", md("plain.md") is None and md("other.md") is None
   and md("broken.md") is None and md("plain.txt.md") is None and md("broken.md") is None, os.listdir(D))
rc, o = run(os.path.join(D, "notes.json"))
ok("8 a single file -> rc 0, its .md", rc == 0 and "notes.json -> notes.md" in o, o)
empty = os.path.join(T, "empty"); os.makedirs(empty)
rc, o = run(empty)
ok("9 a folder without exports -> rc 0, says so, writes nothing", rc == 0 and "No files with chunkedPrompt found." in o and not os.listdir(empty), o)
rc, o = run(os.path.join(T, "nope"))
ok("10 a missing path -> rc 2", rc == 2 and "does not exist" in o, o)
ENV.pop("CCM_HUMAN_NAME")
rc, o = run(os.path.join(D, "sub", "chat v1.2"))
ok("11 no CCM_HUMAN_NAME -> the default label", rc == 0 and "**The user:** first" in (md("sub", "chat v1.2.md") or ""), md("sub", "chat v1.2.md"))

shutil.rmtree(T)
print(f"ai-studio-to-md: {P} pass, {F} fail")
sys.exit(1 if F else 0)
