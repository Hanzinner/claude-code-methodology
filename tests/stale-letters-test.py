#!/usr/bin/env python3
"""stale_letters: my urgent letter, unread in a live addressee's "New" past MIN_AGE → one "wake it" line; read, not
urgent, too young, too old, no tab, someone else's → silent. Plus the chain: inbox_post.sh writes the send log,
inbox_wait.sh calls stale_letters on a link with no letters.
SL=<path> tests another stale_letters.py; IP / IW another inbox_post.sh / inbox_wait.sh. Sandbox only."""
import atexit, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.join(HERE, "..")
SL = os.environ.get("SL", os.path.join(REPO, "scripts", "stale_letters.py"))
IP = os.environ.get("IP", os.path.join(REPO, "scripts", "inbox_post.sh"))
IW = os.environ.get("IW", os.path.join(REPO, "scripts", "inbox_wait.sh"))
T = tempfile.mkdtemp(prefix="stale-test-")
atexit.register(shutil.rmtree, T, True)
AG, LOG, HOME = f"{T}/Agents", f"{T}/sent.log", f"{T}/home"
for a in ("Lead", "Dev", "Design", "Sleepy"):
    os.makedirs(f"{AG}/{a}")
os.makedirs(f"{AG}/Team/Nested")                     # an agent one level deeper (project sub-folder)
os.makedirs(f"{HOME}/.claude/agent-identity")
open(f"{HOME}/.claude/agent-identity/sid-lead", "w").write(f"{AG}/Lead\n")
# fake agent_tab: a live tab for every agent except Sleepy
TAB = f"{T}/tab.py"
open(TAB, "w").write("import json, sys\na = sys.argv[1]\n"
                     "print(json.dumps([] if a == 'Sleepy' else [{'name': a + '-tab', 'status': 'idle', 'pid': 1, 'sessionId': 'x'}]))\n")
ENV = {**os.environ, "HOME": HOME, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_TEST": "1", "CCM_AGENTS_DIR": AG,
       "CCM_LANG_EXTRA": "", "STALE_SENT_LOG": LOG, "STALE_AGENT_TAB": f"{sys.executable} {TAB}", "INBOX_LISTEN": "0"}
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:400])


def inbox(agent, new, done="", hdr="## New"):
    open(f"{AG}/{agent}/inbox.md", "w").write(f"# {agent}\n\n{hdr}\n\n{new}\n\n## Processed\n\n{done}\n")


def log(*rows):
    """rows: (minutes ago, sender, addressee, first line)"""
    # +30 s: "N minutes ago" reads as N min, not N-1 after rounding
    open(LOG, "w").write("".join(f"{int(time.time() - m * 60 - 30)}\t{s}\t{to}\t{h}\n" for m, s, to, h in rows))


def stale(me="Lead", **env):
    r = subprocess.run([sys.executable, SL, me], capture_output=True, text=True, env={**ENV, **env}, timeout=30)
    return r.stdout + (f"[rc {r.returncode}] {r.stderr}" if r.returncode else "")


L1 = "- [ ] [2026-01-01] Lead · 🖐 the build is red, fix first"
inbox("Dev", L1); log((30, "Lead", "Dev", L1))
o = stale()
ok("1 urgent, unread 30 min, tab alive → a line naming the tab", "Dev" in o and 'to="Dev-tab"' in o and "30 min" in o, o)
inbox("Dev", "", done=L1.replace("[ ]", "[x]"))
ok("2 the same letter already moved to Processed → silent", stale() == "", stale())
L2 = "- [ ] [2026-01-01] Lead · please look at the layout when free"
inbox("Dev", L2); log((30, "Lead", "Dev", L2))
ok("3 not urgent → silent", stale() == "", stale())
inbox("Dev", L1); log((3, "Lead", "Dev", L1))
ok("4 younger than MIN_AGE (10 min) → silent", stale() == "", stale())
log((25 * 60, "Lead", "Dev", L1))
ok("5 older than a day → silent", stale() == "", stale())
L3 = "- [ ] [2026-01-01] Lead · 🖐 wake up"
inbox("Sleepy", L3); log((30, "Lead", "Sleepy", L3))
ok("6 no live tab → silent", stale() == "", stale())
log((30, "Design", "Dev", L1))
ok("7 someone else's letter → silent", stale() == "", stale())
L4 = "- [ ] [2026-01-01] Lead · release blocker `M·90`"
inbox("Design", L4); log((40, "Lead", "Design", L4), (35, "Lead", "Design", L4))
o = stale()
ok("8 priority M·90 counts as urgent; the same letter twice → one line", o.count("📮") == 1 and "Design" in o, o)
L5 = "- [ ] [2026-01-01] Lead · URGENT: the stand is down"
inbox("Dev", L5, hdr="## Нові"); log((20, "Lead", "Dev", L5))
ok("9 URGENT, inbox with the old Ukrainian '## Нові' header → a line", "Dev" in stale(), stale())
L6 = "- [ ] [2026-01-01] Lead · ТЕРМІНОВО: стенд лежить"
inbox("Dev", L6); log((20, "Lead", "Dev", L6))
ok("10 Ukrainian ТЕРМІНОВО without CCM_LANG_EXTRA=uk → silent", stale() == "", stale())
ok("11 the same with CCM_LANG_EXTRA=uk → a line", "Dev" in stale(CCM_LANG_EXTRA="uk"), stale(CCM_LANG_EXTRA="uk"))
open(f"{AG}/Team/Nested/inbox.md", "w").write(f"# N\n\n## New\n\n{L1}\n\n## Processed\n")
log((30, "Lead", "Nested", L1))
ok("12 an addressee one folder deeper is found", 'to="Nested-tab"' in stale(), stale())
os.remove(LOG)
ok("13 no send log → silent, rc 0", stale() == "", stale())
open(LOG, "w").write("garbage line\nnot-a-number\tLead\tDev\t🖐 x\n")
ok("14 a broken send log → silent, rc 0", stale() == "", stale())
r = subprocess.run([sys.executable, SL], capture_output=True, text=True, env=ENV)
ok("15 no agent given → usage, rc 2", r.returncode == 2 and "stale_letters" in r.stdout, r.stdout + r.stderr)

# --- the chain: inbox_post.sh writes the send log ----------------------------------------------------------------------
inbox("Dev", "_(empty)_")
r = subprocess.run(["bash", IP, "Dev", "🖐 the build is red\nsecond line of the letter"], capture_output=True, text=True,
                   env={**ENV, "INBOX_SENT_LOG": f"{T}/chain.log", "CLAUDE_CODE_SESSION_ID": "sid-lead"})
row = open(f"{T}/chain.log").read().rstrip("\n").split("\t") if os.path.isfile(f"{T}/chain.log") else []
ok("16 inbox_post.sh logs one line: epoch, sender (from the identity), addressee, the letter's first line only",
   len(row) == 4 and row[1] == "Lead" and row[2] == "Dev" and row[3].endswith("🖐 the build is red")
   and open(f"{T}/chain.log").read().count("\n") == 1, (r.stderr, row))
subprocess.run(["bash", IP, "Dev", "a plain letter"], capture_output=True, text=True, env=ENV)
ok("17 under CCM_TEST without INBOX_SENT_LOG nothing is written to ~/.claude/inbox-sent.log",
   not os.path.exists(f"{HOME}/.claude/inbox-sent.log"))

# --- the chain: inbox_wait.sh calls stale_letters on a link with no letters --------------------------------------------
inbox("Lead", "")
wenv = {**ENV, "STALE_SENT_LOG": f"{T}/chain.log", "STALE_MIN_AGE": "0", "INBOX_WAIT_POLL": "1",
        "ALARM_MODE_DIR": f"{T}/mode", "WORK_GUARD_AGENTS": f"{T}/none"}
r = subprocess.run(["bash", IW, "Lead", "--max", "1"], capture_output=True, text=True, env=wenv, timeout=60)
ok("18 inbox_wait.sh, --max with no letters → the stale line before the 'no letters' line",
   "your urgent letter to Dev" in r.stdout and 'to="Dev-tab"' in r.stdout and "no letters" in r.stdout
   and r.stdout.index("📮") < r.stdout.index("⌛"), r.stdout + r.stderr)
r = subprocess.run(["bash", IW, "Lead", "--max", "30"], capture_output=True, text=True,
                   env={**wenv, "INBOX_WAIT_CEIL": "1"}, timeout=60)
ok("19 inbox_wait.sh, the ceiling exit → the stale line too", "your urgent letter to Dev" in r.stdout
   and "served its link" in r.stdout, r.stdout + r.stderr)
print(f"stale-letters: {P} pass, {F} fail")
sys.exit(1 if F else 0)
