#!/usr/bin/env python3
"""Check an installation against this repo, item by item. The repo is the list of what must be there.

  ./check-install.py --user            # checks ~/.claude
  ./check-install.py --project DIR     # checks DIR/.claude

Checks: every hook, script, skill and code-lessons file from the repo is installed (hooks and scripts
executable); CLAUDE.md and memory are there; settings.json is valid JSON and every hook command it
registers exists and runs to exit 0 on a sample event. Prints one line per item and a total.
Exit 0 only if nothing is missing or broken. Optional extras (Telegram bot, system packages) are
reported, not required.
"""
import json, os, shlex, subprocess, sys

REPO = os.path.dirname(os.path.realpath(__file__))


def usage():
    print(__doc__.strip().split("\n\n")[1]); sys.exit(2)


args = sys.argv[1:]
if args[:1] == ["--user"]:
    target = os.path.expanduser("~/.claude")
elif args[:1] == ["--project"] and len(args) == 2:
    target = os.path.join(os.path.abspath(args[1]), ".claude")
else:
    usage()

ok, bad = 0, []


def check(cond, what, fix=""):
    global ok
    if cond:
        ok += 1
    else:
        bad.append(what + (f" — {fix}" if fix else ""))
    print(f"{'ok  ' if cond else 'MISS'} {what}")


def files(sub, exts):
    d = os.path.join(REPO, sub)
    return sorted(f for f in os.listdir(d) if f.endswith(exts) and os.path.isfile(os.path.join(d, f)))


print(f"Checking {target} against {REPO}\n")
check(os.path.isfile(f"{target}/CLAUDE.md") or os.path.isfile(f"{target}/CLAUDE.md.new"), "CLAUDE.md", "run ./install.sh")
for f in files("hooks", (".sh", ".py")):
    p = f"{target}/hooks/{f}"
    check(os.path.isfile(p) and os.access(p, os.X_OK), f"hooks/{f}", "missing or not executable: run ./install.sh")
for f in files("scripts", (".sh", ".py")):
    p = f"{target}/scripts/{f}"
    check(os.path.isfile(p) and os.access(p, os.X_OK), f"scripts/{f}", "missing or not executable: run ./install.sh")
for d in sorted(os.listdir(f"{REPO}/skills")):
    if os.path.isdir(f"{REPO}/skills/{d}"):
        check(os.path.isfile(f"{target}/skills/{d}/SKILL.md"), f"skills/{d}", "run ./install.sh")
for f in files("code-pitfalls", (".md",)):
    check(os.path.isfile(f"{target}/code-pitfalls/{f}"), f"code-pitfalls/{f}", "run ./install.sh")
for f in files("lib", (".py",)):
    check(os.path.isfile(f"{target}/lib/{f}"), f"lib/{f}", "run ./install.sh")
for f in files("mcp", (".py",)):
    check(os.path.isfile(f"{target}/mcp/{f}"), f"mcp/{f}", "run ./install.sh")
for sub in ("bin", "tests"):
    for f in files(sub, ("",)):
        p = f"{target}/{sub}/{f}"
        check(os.path.isfile(p) and os.access(p, os.X_OK), f"{sub}/{f}", "missing or not executable: run ./install.sh")
check(os.path.isfile(f"{target}/methodology.conf"), "methodology.conf", "run ./install.sh")
check(os.path.isfile(f"{target}/memory/MEMORY.md"), "memory/MEMORY.md", "run ./install.sh")

settings = f"{target}/settings.json"
try:
    s = json.load(open(settings))
    check(True, "settings.json is valid JSON")
except Exception as e:
    s = None
    check(False, "settings.json is valid JSON", f"{e}; run ./install.sh")

if s is not None:
    tmpl = json.load(open(f"{REPO}/settings.template.json"))
    def hook_id(cmd):
        """script name + its own args: 'trash-guard.py --post' and 'input-guard.py --post' are different hooks"""
        t = shlex.split(cmd)
        i = max((k for k, w in enumerate(t) if w.endswith((".py", ".sh"))), default=len(t) - 1)
        return " ".join([t[i].rsplit("/", 1)[-1], *t[i + 1:]])
    want = {(ev, hook_id(h["command"]))
            for ev, gs in tmpl["hooks"].items() for g in gs for h in g["hooks"]}
    have = {}
    for ev, gs in (s.get("hooks") or {}).items():
        for g in gs:
            for h in g.get("hooks", []):
                have[(ev, hook_id(h["command"]))] = h["command"]
    sample = {"session_id": "check-install", "transcript_path": "/nonexistent", "cwd": os.getcwd(),
              "tool_name": "Read", "tool_input": {"file_path": "x.txt", "command": "ls"},
              "prompt": "hi", "trigger": "manual", "error": "Exit code 2"}
    for ev, name in sorted(want):
        cmd = have.get((ev, name))
        if not cmd:
            check(False, f"settings.json: {ev} → {name} registered", "run ./install.sh")
            continue
        r = subprocess.run(cmd, shell=True, input=json.dumps({**sample, "hook_event_name": ev}),
                           capture_output=True, text=True, timeout=60)
        check(r.returncode == 0, f"settings.json: {ev} → {name} runs",
              f"exit {r.returncode}: {(r.stderr or r.stdout).strip()[:160]}")

print("\nOptional (not required):")
print(f"  Telegram bot: {'installed' if os.path.isdir(target + '/mobile-bot') else 'not installed'}")
for tool, why in (("pdftotext", "PDF extraction"), ("pandoc", "HTML to markdown"), ("lynx", "HTML to text")):
    found = any(os.access(os.path.join(p, tool), os.X_OK) for p in os.environ.get("PATH", "").split(":"))
    print(f"  {tool} ({why}): {'found' if found else 'not found'}")

print(f"\n{ok} ok, {len(bad)} missing or broken")
for b in bad:
    print("  -", b)
sys.exit(1 if bad else 0)
