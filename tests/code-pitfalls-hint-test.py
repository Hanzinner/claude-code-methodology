#!/usr/bin/env python3
"""code-pitfalls-hint: headings by file type / command, text in quotes and heredocs is not a command, dedup per
session × hour, the standard's version, swap-live for a live script, decision records + ARCHITECTURE.md, and the
silent issue-first journal (only write TARGETS in a project count). CP=<path> tests another copy.
Sandbox: temp HOME, workspace and install dir; no config file."""
import glob, json, os, random, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
CP = os.path.realpath(os.environ.get("CP", os.path.join(HERE, "..", "hooks", "code-pitfalls-hint.py")))
T = tempfile.mkdtemp(prefix="cph-test-")
WS, C = f"{T}/ws", f"{T}/c"
PIT = f"{C}/code-pitfalls"
for d in (f"{T}/home/.claude/task-taken", PIT, f"{C}/scripts", f"{WS}/decisions", f"{WS}/Project-A/app", f"{WS}-wt/Dev/Project-A/app"):
    os.makedirs(d, exist_ok=True)
for topic, h in (("python", "Own file named like a stdlib module"), ("verification", "Green test, broken prod"),
                 ("git", "git add a b c: one bad path adds nothing"), ("vm", "ssh without -F"), ("shell", "set -e in a subshell"),
                 ("web", "Mobile width"), ("hooks", "A hook without +x"), ("concurrency", "Write without a lock"),
                 ("services", "A network change: rollback first, reboot, read the log")):
    open(f"{PIT}/{topic}.md", "w").write(f"# {topic}\n\n### {h}\nbody\n")
open(f"{WS}/CODING-STANDARD.md", "w").write("# Coding standard\n\n**Version: 7** (2026-11).\n")
open(f"{WS}/WEB-playbook.md", "w").write("# web\n")
open(f"{C}/scripts/live.sh", "w").write("#!/bin/sh\n")
open(f"{WS}/decisions/0003-a-cache.md", "w").write("# 0003 Project-A keeps its cache on disk\n\n**Status:** current\n")
open(f"{WS}/decisions/0002-old.md", "w").write("# 0002 Project-A used redis\n\n**Status:** replaced by #3\n")
open(f"{WS}/decisions/0000-template.md", "w").write("# 0000 template Project-A live.sh\n")
open(f"{WS}/Project-A/ARCHITECTURE.md", "w").write("# A\n")
ENV = {**os.environ, "HOME": f"{T}/home", "CLAUDE_METHODOLOGY_CONF": f"{T}/none.conf", "CCM_CLAUDE_DIR": C,
       "CCM_WORKSPACE": WS, "CODE_PITFALLS_DIR": PIT, "CPH_ISSUE_LOG": f"{T}/issue.log",
       "CPH_TASK_STATE": f"{T}/home/.claude/task-taken"}
P = F = 0
TAG = f"{random.randrange(16**4):04x}"


def ok(name, cond, out=""):
    global P, F
    if cond: P += 1
    else: F += 1; print("FAIL:", name, "::", str(out)[:400])


N = [0]


def run(tool, ti, sid=None, cwd=""):
    """→ additionalContext ('' when silent). A fresh session id per call unless given (dedup is per session)."""
    N[0] += 1
    sid = sid or f"{TAG}{N[0]:04d}-test"
    ev = {"session_id": sid, "tool_name": tool, "tool_input": ti, "cwd": cwd}
    r = subprocess.run([sys.executable, CP], input=json.dumps(ev), capture_output=True, text=True, env=ENV)
    if r.returncode:
        print(r.stderr[-400:])
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""


def log():
    try:
        return open(f"{T}/issue.log").read()
    except OSError:
        return ""


o = run("Edit", {"file_path": "/x/tool.py", "new_string": "x = 1"})
ok("1 a .py edit -> python + verification headings", "Own file named like a stdlib" in o and "Green test" in o, o)
ok("1b the standard's version is shown", "Coding standard v7" in o, o)
o = run("Edit", {"file_path": "/x/tool.py", "new_string": "import threading"})
ok("2 new text spawns threads -> concurrency too", "Write without a lock" in o, o)
o = run("Bash", {"command": "cat > /tmp/letter.txt <<'EOF'\nplease ssh into the box and git push\nEOF"})
ok("3 ssh and git only inside a heredoc body -> silent", o == "", o)
o = run("Bash", {"command": "echo 'run ssh host' > /tmp/x"})
ok("4 ssh only inside quotes -> silent", o == "", o)
o = run("Bash", {"command": "bash -c \"ssh host uptime\""})
ok("5 ssh in the argument of bash -c IS a command -> vm", "ssh without -F" in o, o)
o = run("Bash", {"command": "cd /r && git add a b"})
ok("6 git -> git lessons", "one bad path adds nothing" in o, o)
sid = f"{TAG}dd01-test"
o1 = run("Bash", {"command": "git status"}, sid); o2 = run("Bash", {"command": "git log"}, sid)
ok("7 the same topic twice in one session and hour -> shown once", "one bad path" in o1 and o2 == "", o2)
o = run("Edit", {"file_path": f"{PIT}/python.md", "new_string": "### new"})
ok("8 editing the pitfalls themselves -> silent", o == "", o)
o = run("Edit", {"file_path": "/x/page.html", "new_string": "<p>"})
ok("9 a web file -> web lessons + the web playbook", "Mobile width" in o and "WEB-playbook.md" in o, o)
o = run("Edit", {"file_path": f"{C}/scripts/live.sh", "new_string": "echo"})
ok("10 an edit of a LIVE script -> swap-live hint", "swap-live" in o and "live.sh.new" in o, o)
o = run("Write", {"file_path": f"{C}/scripts/live.sh.new", "content": "echo"})
ok("11 writing the .new copy -> no swap-live hint", "swap-live" not in o, o)
o = run("Edit", {"file_path": f"{WS}/Project-A/app/main.py", "new_string": "x"})
ok("12 a project edit -> the current decision record + ARCHITECTURE.md",
   "0003-a-cache.md" in o and "ARCHITECTURE.md" in o, o)
ok("12b a replaced decision and the template are not shown", "0002-old" not in o and "0000-template" not in o, o)
ok("13 a project edit -> one issue-first line, 'no task'", log().count("\n") == 1 and "\tProject-A\tno task\t" in log(), log())
sid = f"{TAG}task-test"
open(f"{T}/home/.claude/task-taken/{sid}", "w").write("Project-A S5\n")
run("Edit", {"file_path": f"{WS}/Project-A/app/main.py", "new_string": "x"}, sid)
ok("14 a task taken in that project -> 'task S5'", "\tProject-A\ttask S5\t" in log(), log())
n = log().count("\n")
run("Edit", {"file_path": f"{WS}/Project-A/README.md", "new_string": "x"})
run("Edit", {"file_path": f"{WS}/Project-A/tests/test_a.py", "new_string": "x"})
run("Edit", {"file_path": "/x/tool.py", "new_string": "x"})
ok("15 .md, tests/ and files outside projects -> no journal line", log().count("\n") == n, log())
run("Bash", {"command": "python3 - <<'EOF'\nimport json; json.load(open('Project-A/data/graph.json'))\nEOF"}, cwd=WS)
ok("16 a Bash that only READS a project file -> no journal line", log().count("\n") == n, log())
run("Bash", {"command": "sed -i 's/a/b/' Project-A/app/main.py"}, cwd=WS)
ok("17 sed -i on a project file (relative, cwd = workspace) -> a journal line via Bash",
   log().count("\n") == n + 1 and log().rstrip().endswith("\tBash"), log())
run("Bash", {"command": f"echo x > {WS}-wt/Dev/Project-A/app/x.py"})
ok("18 a write in an agent's worktree of the project counts too", log().count("\n") == n + 2, log())
open(f"{WS}/PROJECT-WORK.md", "w").write("# project work\n")
o = run("Edit", {"file_path": f"{WS}/Project-A/app/main.py", "new_string": "x"})
ok("19 with PROJECT-WORK.md in the workspace, a project edit names it", "PROJECT-WORK.md" in o, o)
o = run("Edit", {"file_path": "/x/tool.py", "new_string": "x"})
ok("19b outside a project it doesn't", "PROJECT-WORK.md" not in o, o)
os.remove(f"{WS}/CODING-STANDARD.md")
o = run("Edit", {"file_path": "/x/tool.py", "new_string": "x"})
ok("20 no standard file -> no version line, the headings still come", "Coding standard" not in o and "Own file" in o, o)

# git reset --soft <branch> (a squash over a moved main reverted two commits merged meanwhile) -> merge-base hint
o = run("Bash", {"command": "cd /w && git reset -q --soft main && git commit -m x"})
ok("21 reset --soft main -> the merge-base hint", "git merge-base HEAD main" in o and "main...HEAD" in o, o)
for k, c in (("22", "git reset --soft $(git merge-base HEAD main)"), ("23", "git reset --soft HEAD~2"), ("24", "git reset --soft 4b5431d")):
    o = run("Bash", {"command": c}); ok(f"{k} {c} -> no hint", "merge-base HEAD" not in o, o)
s1 = f"{TAG}gr-test"; o1 = run("Bash", {"command": "git reset --soft main"}, sid=s1); o2 = run("Bash", {"command": "git reset --soft main"}, sid=s1)
ok("25 the same session and hour -> once", "merge-base" in o1 and "merge-base" not in o2, o2)

for m in glob.glob(f"/tmp/cph-{TAG}*"):
    os.remove(m)
# network / service changes -> services (the first heading of services.md); reading them, a backup copy FROM a config
# file, the words in quotes or a heredoc -> silent
SV = "A network change: rollback first"
for c in ("netplan apply", "sudo netplan try --timeout 60", "ip addr add 10.0.0.2/24 dev eth0", "ip -4 route del default",
          "ip link set eth0 down", "nmcli con modify eth0 ipv4.dns 1.1.1.1", "nmcli connection up eth0",
          "resolvectl dns eth0 1.1.1.1", "echo nameserver 1.1.1.1 > /etc/resolv.conf",
          "sed -i 's/a/b/' /etc/netplan/50-cloud-init.yaml", "tee /etc/network/interfaces < new", "cp new.yaml /etc/netplan/01.yaml",
          "ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf", "systemctl restart networking",
          "systemctl stop systemd-networkd", "sudo systemctl restart NetworkManager.service", "bash -c \"netplan apply\"",
          "cd /etc && ifdown eth0"):
    o = run("Bash", {"command": c})
    ok(f"26 a network change -> services: {c}", SV in o, o)
for c in ("ip a", "ip route show", "ip addr show dev eth0", "systemctl status networking", "systemctl restart nginx",
          "resolvectl status", "nmcli dev status", "cat /etc/resolv.conf", "cp /etc/resolv.conf /tmp/resolv.bak",
          "grep dns /etc/netplan/50.yaml", "echo 'then netplan apply' > /tmp/note",
          "cat > /tmp/plan.txt <<'EOF'\nnetplan apply\nsystemctl restart networking\nEOF"):
    o = run("Bash", {"command": c})
    ok(f"27 not a change -> no services: {c!r}", SV not in o, o)
o = run("Edit", {"file_path": "/etc/netplan/50-cloud-init.yaml", "new_string": "dhcp4: true"})
ok("28 editing a network config file -> services", SV in o, o)
o = run("Edit", {"file_path": "/x/app.service", "new_string": "[Service]"})
ok("28b a .service file still -> services", SV in o, o)

print(f"code-pitfalls-hint: {P} pass, {F} fail"); sys.exit(1 if F else 0)
