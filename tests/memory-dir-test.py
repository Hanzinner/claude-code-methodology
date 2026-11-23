#!/usr/bin/env python3
"""The memory folder is ONE folder: the one Claude Code's own auto memory uses (autoMemoryDirectory in settings.json).
lib/ccm_conf.py derives CCM_MEMORY_DIR from it (settings.local.json first, ~/ expanded, overrides CCM_MEMORY_DIR >
CLAUDE_MEMORY_DIR > the setting > <claude dir>/memory), the episodic log follows it, and memory-write-gate guards
exactly that folder. Sandbox: a temp install dir (copies of lib/ and hooks/), temp HOME, no config file.
Last line: memory-dir-test: N pass, M fail."""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
# realpath: lib/ccm_conf.py finds the install dir through realpath(__file__); a macOS temp dir is /var/folders/...,
# a link to /private/var/folders/... - the unresolved name never equalled what the script printed
T = os.path.realpath(tempfile.mkdtemp(prefix="memory-dir-test-"))
C = f"{T}/c"                     # the install dir
os.makedirs(f"{T}/home")
for sub in ("lib", "hooks"):
    shutil.copytree(os.path.join(ROOT, sub), f"{C}/{sub}")
BASE = {k: v for k, v in os.environ.items() if k not in ("CCM_MEMORY_DIR", "CLAUDE_MEMORY_DIR", "CCM_EPISODIC_DIR",
                                                          "CCM_CLAUDE_DIR", "CLAUDE_METHODOLOGY_DIR")}
BASE.update({"HOME": f"{T}/home", "CLAUDE_METHODOLOGY_CONF": f"{T}/none.conf", "CCM_TEST": "1"})
P = F = 0


def ok(name, cond, detail=""):
    global P, F
    if cond: P += 1
    else: F += 1; print("FAIL:", name, str(detail)[:300])


def conf(key, **env):
    r = subprocess.run([sys.executable, f"{C}/lib/ccm_conf.py", key], capture_output=True, text=True, timeout=20,
                       env={**BASE, **env})
    return r.stdout.strip()


def settings(name, value):
    p = f"{C}/{name}"
    if value is None:
        if os.path.exists(p): os.remove(p)
    else:
        json.dump({"autoMemoryDirectory": value, "env": {}}, open(p, "w"))


def gate(path, content="no frontmatter\n", **env):
    ev = {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}
    r = subprocess.run([sys.executable, f"{C}/hooks/memory-write-gate.py"], input=json.dumps(ev), capture_output=True,
                       text=True, timeout=20, env={**BASE, **env})
    return "deny" in r.stdout


ok("1 no setting -> <claude dir>/memory", conf("CCM_MEMORY_DIR") == f"{C}/memory", conf("CCM_MEMORY_DIR"))
ok("2 the episodic log follows the memory folder", conf("CCM_EPISODIC_DIR") == f"{C}/memory/episodic")
settings("settings.json", f"{T}/mem-a")
ok("3 autoMemoryDirectory in settings.json -> that folder", conf("CCM_MEMORY_DIR") == f"{T}/mem-a")
ok("3b ... and the episodic log goes there too", conf("CCM_EPISODIC_DIR") == f"{T}/mem-a/episodic")
settings("settings.json", "~/notes/mem/")
ok("4 '~/' is expanded against HOME, a trailing slash dropped", conf("CCM_MEMORY_DIR") == f"{T}/home/notes/mem",
   conf("CCM_MEMORY_DIR"))
settings("settings.local.json", f"{T}/mem-local")
ok("5 settings.local.json beats settings.json (as in Claude Code)", conf("CCM_MEMORY_DIR") == f"{T}/mem-local")
ok("6 CLAUDE_MEMORY_DIR (the older name) beats the setting", conf("CCM_MEMORY_DIR", CLAUDE_MEMORY_DIR=f"{T}/old") == f"{T}/old")
ok("7 CCM_MEMORY_DIR beats everything", conf("CCM_MEMORY_DIR", CCM_MEMORY_DIR=f"{T}/x", CLAUDE_MEMORY_DIR=f"{T}/old") == f"{T}/x")
settings("settings.local.json", None)
open(f"{C}/settings.json", "w").write("{not json")
ok("8 a broken settings.json -> the fallback, not a crash", conf("CCM_MEMORY_DIR") == f"{C}/memory", conf("CCM_MEMORY_DIR"))

# memory-write-gate guards the folder Claude really writes to
settings("settings.json", f"{T}/mem-a")
os.makedirs(f"{T}/mem-a", exist_ok=True); os.makedirs(f"{C}/memory", exist_ok=True)
ok("9 a memory file without provenance in the autoMemoryDirectory folder -> denied", gate(f"{T}/mem-a/fact.md"))
good = "---\nname: x\nsource: chat 2026-11-16\nverified: yes\n---\nbody\n"
ok("10 ... with source:/verified: -> allowed", not gate(f"{T}/mem-a/fact.md", good))
ok("11 the old default folder is not memory any more -> not guarded", not gate(f"{C}/memory/fact.md"))
ok("12 the index MEMORY.md stays exempt", not gate(f"{T}/mem-a/MEMORY.md"))

shutil.rmtree(T, ignore_errors=True)
print(f"memory-dir-test: {P} pass, {F} fail")
sys.exit(1 if F else 0)
