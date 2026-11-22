#!/usr/bin/env python3
"""A freshly installed memory-template/ is clean: curate_memory.py reports nothing on it (the example entries in MEMORY.md
sit inside <!-- --> comments; README.md at the top of the memory folder is its "how to write memory here", not memory),
and memory-write-gate lets that README be edited. Real problems still show: a broken link outside a comment, an
unresolved [[name]] in a memory file, a README.md in a subfolder (gated). CM=, GATE= <path> test other copies.
Sandbox: temp memory folder, temp HOME, no config file. Last line: memory-template-curate: N pass, M fail."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
CM = os.environ.get("CM", os.path.join(ROOT, "scripts", "curate_memory.py"))
GATE = os.environ.get("GATE", os.path.join(ROOT, "hooks", "memory-write-gate.py"))
T = tempfile.mkdtemp(prefix="memory-template-curate-test-")
M = os.path.join(T, "memory")
os.makedirs(os.path.join(T, "home"))
shutil.copytree(os.path.join(ROOT, "memory-template"), M)
ENV = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_MEMORY_DIR", "CCM_EPISODIC_DIR", "CLAUDE_METHODOLOGY_DIR")}
ENV.update({"HOME": os.path.join(T, "home"), "CLAUDE_METHODOLOGY_CONF": os.path.join(T, "none.conf"), "CCM_TEST": "1",
            "CCM_MEMORY_DIR": M, "CLAUDE_MEMORY_DIR": M})
P = F = 0


def ok(name, cond, detail=""):
    global P, F
    if cond: P += 1
    else: F += 1; print("FAIL:", name, "::", str(detail)[:600])


def curate():
    r = subprocess.run([sys.executable, CM], capture_output=True, text=True, timeout=30, env=ENV)
    return r.returncode, r.stdout + r.stderr


def denied(path, content="no frontmatter\n"):
    ev = {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}
    r = subprocess.run([sys.executable, GATE], input=json.dumps(ev), capture_output=True, text=True, timeout=30, env=ENV)
    return '"deny"' in r.stdout


def add(name, text):
    with open(os.path.join(M, name), "w", encoding="utf-8") as f:
        f.write(text)


rc, out = curate()
ok("1 a fresh copy of memory-template/ -> 0 issues", rc == 0 and "issue" not in out, out)
ok("2 memory-write-gate: README.md at the top of the memory folder is not memory -> allowed",
   not denied(os.path.join(M, "README.md")))
os.makedirs(os.path.join(M, "people"))
ok("3 memory-write-gate: a README.md in a subfolder is gated -> denied", denied(os.path.join(M, "people", "README.md")))
ok("4 memory-write-gate: an ordinary memory file without provenance -> still denied", denied(os.path.join(M, "user_x.md")))

with open(os.path.join(M, "MEMORY.md"), "a", encoding="utf-8") as f:
    f.write("\n- **Real entry** -> [project_gone.md](project_gone.md)\n"
            "<!--\n- **Multi-line example** -> [project_hidden.md](project_hidden.md)\n-->\n"
            "<!-- - **Sam** -> [user_sam.md](user_sam.md) -->\n")
add("user_sam.md", "---\nname: user-sam\ndescription: d\nmetadata:\n  type: user\n---\nSee [[no-such-note]].\n"
                   "<!-- [[commented-out-note]] -->\n")
rc, out = curate()
ok("5 a broken link outside a comment -> still reported", rc == 1 and "broken link in MEMORY.md: project_gone.md" in out, out)
ok("6 a link inside a multi-line comment -> not reported", "project_hidden.md" not in out, out)
ok("7 a file linked only from inside a comment is an orphan", "orphan: user_sam.md" in out, out)
ok("8 an unresolved [[name]] in a memory file -> still reported; one inside a comment -> not",
   "unresolved wikilink in user_sam.md: [[no-such-note]]" in out and "commented-out-note" not in out, out)
ok("9 README.md is still not named (orphan / frontmatter / wikilink)", "README.md" not in out, out)

shutil.rmtree(T, ignore_errors=True)
print(f"memory-template-curate: {P} pass, {F} fail")
sys.exit(1 if F else 0)
