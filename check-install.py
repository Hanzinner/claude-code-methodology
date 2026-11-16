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
check(os.path.isfile(f"{target}/CLAUDE.md"), "CLAUDE.md", "run ./install.sh")
check(not os.path.isfile(f"{target}/CLAUDE.md.new"), "CLAUDE.md: our rules merged into yours",
      f"merge pending: keep everything in {target}/CLAUDE.md, add what it lacks from CLAUDE.md.changes, ask the user about "
      f"each contradiction, then: mv {target}/CLAUDE.md.new {target}/.methodology-installed/CLAUDE.md.base")
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
print(f"  Telegram bot: {'installed' if os.path.exists(target + '/mobile-bot/bot.py') else 'not installed'}")
for tool, why in (("pdftotext", "PDF extraction"), ("pandoc", "HTML to markdown"), ("lynx", "HTML to text")):
    found = any(os.access(os.path.join(p, tool), os.X_OK) for p in os.environ.get("PATH", "").split(":"))
    print(f"  {tool} ({why}): {'found' if found else 'not found'}")

# Accounts: print ONLY what is missing — one line per section of docs/accounts.md, with the same anchor.
def _conf(key):
    try:
        return subprocess.run([sys.executable, f"{target}/lib/ccm_conf.py", key], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except Exception:
        return ""


def _has(cmd):
    return any(os.access(os.path.join(p, cmd), os.X_OK) for p in os.environ.get("PATH", "").split(":"))


def _keys(path, names):
    try:
        txt = open(path, encoding="utf-8").read()
    except OSError:
        return False
    return any(l.split("=", 1)[0].strip() in names and l.split("=", 1)[1].strip()
               for l in txt.splitlines() if "=" in l and not l.lstrip().startswith("#"))


secrets = _conf("CCM_SECRETS_DIR") or os.path.expanduser("~/.config/claude-secrets")
DOC = os.path.join(REPO, "docs", "accounts.md")
todo = []
if not _has("claude"):
    todo.append(f"Claude Code: the claude CLI is not on PATH -> {DOC}#claude-code")
senv = os.path.join(secrets, "search.env")
if not _keys(senv, ("TAVILY_API_KEY", "EXA_API_KEY")):
    todo.append(f"web search: no keys in {senv} -> {DOC}#tavily-and-exa--web-search")
else:
    try:
        cj = json.load(open(os.path.expanduser("~/.claude.json")))
    except Exception:
        cj = {}
    if "search" not in (cj.get("mcpServers") or {}) and not any(
            "search" in ((v or {}).get("mcpServers") or {}) for v in (cj.get("projects") or {}).values() if isinstance(v, dict)):
        todo.append(f"web search: keys are there but the server is not registered: claude mcp add --scope user search "
                    f"-- python3 {target}/mcp/search_mcp.py -> {DOC}#tavily-and-exa--web-search")
if os.path.exists(f"{target}/scripts/backup/backup-restic.sh") and not any(
        os.path.exists(os.path.join(secrets, f)) for f in ("restic.env", "s3-credentials.json")):
    todo.append(f"offsite backup: installed, no storage keys in {secrets} -> {DOC}#s3-compatible-storage--offsite-backup")
if os.path.exists(f"{target}/mobile-bot/bot.py") and not os.path.exists(os.path.join(secrets, "mobile-bot.env")):
    todo.append(f"mobile bot: installed, no {secrets}/mobile-bot.env -> {DOC}#telegram--mobile-bot")
if os.path.isfile(f"{target}/addons/session-hygiene/session-hygiene.py"):
    try:
        r = subprocess.run([sys.executable, f"{target}/scripts/cron_state_check.py", "session_hygiene", "36"],
                           capture_output=True, text=True, timeout=15)
        why = (r.stdout or r.stderr).strip().splitlines()[-1:] or ["?"]
        print(f"  session-hygiene add-on: {'never ran yet (it waits for the nightly chat backup)' if r.returncode == 3 else why[0]}")
    except Exception as e:
        print(f"  session-hygiene add-on: state unknown ({str(e)[:80]})")
rcheck = f"{target}/addons/reader/reader-check.py"
if os.path.isfile(rcheck):
    try:
        r = subprocess.run([sys.executable, rcheck], capture_output=True, text=True, timeout=15)
        rc, why = r.returncode, (r.stdout or r.stderr).strip()
    except Exception as e:
        rc, why = 1, str(e)[:160]
    print(f"  reader add-on: {why}")   # the "Optional" block: not counted as broken (--no-cron installs do not start it)
if todo:
    print("\nAccounts still to set up (optional; each line points to the how-to):")
    for t in todo:
        print("  -", t)

print(f"\n{ok} ok, {len(bad)} missing or broken")
for b in bad:
    print("  -", b)
sys.exit(1 if bad else 0)
