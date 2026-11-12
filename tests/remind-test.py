#!/usr/bin/env python3
"""remind: set -> at its time a letter in the addressee's inbox (a stub mail script in a sandbox agents dir); downtime ->
a "late" note; the mail script refuses -> retry; cancel; bad time/addressee -> refusal. RM=<path> tests another copy.
Sandbox: temp HOME, no config file, CCM_* env into the temp dir; no network, nothing outside the temp dir."""
import json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.realpath(__file__))
RM = os.environ.get("RM", os.path.join(HERE, "..", "scripts", "remind.py"))
R = tempfile.mkdtemp(prefix="rm-test-"); AG = f"{R}/Agents"; D = f"{R}/state"
os.makedirs(f"{AG}/Tester"); INBOX = f"{AG}/Tester/inbox.md"
open(f"{AG}/Tester/briefing.md", "w").write("# t\n"); open(INBOX, "w").write("# inbox\n\n## New\n\n## Done\n")
# stub for inbox_post.sh: put the text under "## New" (the real one is tested with its own group)
POSTSTUB = f"{R}/post.sh"
open(POSTSTUB, "w").write(f"""#!/usr/bin/env python3
import sys
p = "{AG}/" + sys.argv[1] + "/inbox.md"
t = open(p, encoding="utf-8").read().replace("## New\\n", "## New\\n\\n- [ ] " + sys.argv[2] + "\\n", 1)
open(p, "w", encoding="utf-8").write(t)
""")
os.chmod(POSTSTUB, 0o755)
T0 = int(time.mktime((2026, 10, 7, 10, 0, 0, 0, 0, -1)))
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def run(*a, at=T0, **env):
    base = {**os.environ, "HOME": R, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_AGENTS_DIR": AG, "REMIND_DIR": D,
            "REMIND_NOW": str(at), "REMIND_POST": POSTSTUB, "REMIND_RESOLVE": f"{R}/no-such-resolver"}
    r = subprocess.run([sys.executable, RM, *a], capture_output=True, text=True, env={**base, **env})
    return r.returncode, r.stdout + r.stderr


def files(sub=""): return sorted(f for f in os.listdir(f"{D}/{sub}") if f.endswith(".json")) if os.path.isdir(f"{D}/{sub}") else []
def inbox(): return open(INBOX, encoding="utf-8").read()


rc, o = run("Tester", "15m", "check the deploy")
ok("set at 15m -> rc 0, a file with due = +900 s", rc == 0 and len(files()) == 1 and json.load(open(f"{D}/{files()[0]}"))["due"] == T0 + 900, o)
ok("reply: when, in how long, id", "07.10 10:15" in o and "in 15 min" in o and "--cancel" in o, o)
rc, _ = run("--fire", at=T0 + 600)
ok("5 min before the time --fire sends nothing", rc == 0 and "check the deploy" not in inbox() and len(files()) == 1)
rc, _ = run("--fire", at=T0 + 930)
ok("the time has come -> a letter under \"New\", the file in done/", rc == 0 and "⏰ **Reminder**" in inbox() and "check the deploy" in inbox()
   and not files() and len(files("done")) == 1, inbox())
ok("an on-time letter has no \"late\"", "late by" not in inbox())
run("--fire", at=T0 + 990)
ok("a second --fire doesn't duplicate the letter", inbox().count("check the deploy") == 1)

rc, o = run("Tester", "18:30", "call"); d1 = json.load(open(f"{D}/{files()[0]}"))["due"]
ok("HH:MM ahead -> today", time.strftime("%d %H:%M", time.localtime(d1)) == "07 18:30", o)
rc, o = run("Tester", "09:00", "morning"); d2 = max(json.load(open(f"{D}/{f}"))["due"] for f in files())
ok("HH:MM already past -> tomorrow", time.strftime("%d %H:%M", time.localtime(d2)) == "08 09:00", o)
rc, o = run("Tester", "1h30m", "compound"); ok("1h30m -> +5400 s", rc == 0 and any(json.load(open(f"{D}/{f}"))["due"] == T0 + 5400 for f in files()), o)
rc, o = run("--list", "Tester")
ok("--list: three reminders ordered by time", rc == 0 and o.index("compound") < o.index("call") < o.index("morning"), o)
rid = [json.load(open(f"{D}/{f}")) for f in files() if "morning" in open(f"{D}/{f}").read()][0]["id"]
rc, o = run("--cancel", rid); ok("--cancel removes; it is gone from the list", rc == 0 and "morning" not in run("--list")[1], o)
ok("--cancel of a missing id -> rc 4", run("--cancel", "zzzzz")[0] == 4)

# the machine was off: both overdue go on the first --fire with a note
rc, _ = run("--fire", at=T0 + 3 * 86400)
ok("after downtime: both letters went, with \"late by\"", rc == 0 and "compound" in inbox() and "call" in inbox() and inbox().count("late by") == 2 and not files(), inbox())

# the mail script refuses -> the file stays, goes next time
bad = f"{R}/bad.sh"; open(bad, "w").write("#!/bin/bash\necho busy >&2; exit 7\n"); os.chmod(bad, 0o755)
run("Tester", "10m", "because of a breakdown")
rc, _ = run("--fire", at=T0 + 700, REMIND_POST=bad)
ok("the letter did not go -> rc 1, the reminder stays, RETRY in the log", rc == 1 and len(files()) == 1 and "RETRY" in open(f"{D}/remind.log").read())
rc, _ = run("--fire", at=T0 + 760)
ok("next minute with a working mail script -> delivered", rc == 0 and "because of a breakdown" in inbox() and not files())
run("Tester", "10m", "dead addressee")
rc, _ = run("--fire", at=T0 + 600 + 90000, REMIND_POST=bad)
ok("the machine was off a day + ONE refusal -> not giving up (the day counts from the first failure)", len(files()) == 1 and not files("failed"))
rc, _ = run("--fire", at=T0 + 600 + 90000 + 3600, REMIND_POST=bad); ok("an hour of failures -> still waiting", len(files()) == 1)
rc, _ = run("--fire", at=T0 + 600 + 90000 + 86500, REMIND_POST=bad)
ok("a day of failures -> failed/, not looping forever", len(files("failed")) == 1 and not files())
open(f"{D}/zz.json", "w").write("{}"); open(f"{D}/aa.json", "w").write("[]"); run("Tester", "5m", "after the broken ones")
rc, o = run("--fire", at=T0 + 400)
ok("broken files in the dir don't stop the rest; they go to failed/ themselves", rc == 0 and "after the broken ones" in inbox() and not files() and "BROKEN" in open(f"{D}/remind.log").read(), o)

for args, why in ((("Tester", "sometime", "x"), "a bad time"), (("Tester", "10", "x"), "a bare number without a unit"), (("Tester", "2020-01-01 10:00", "x"), "a time in the past"),
                  (("Nobody-Agent", "5m", "x"), "no such addressee"), (("Tester", "5m"), "no text"), (("--oops",), "an unknown option")):
    n0 = len(files()); rc, o = run(*args)
    ok(f"{why} -> rc 2, nothing set", rc == 2 and len(files()) == n0, o)

# addressee lookup inline: "<name>-agent" folder, case-insensitive, nested group
os.makedirs(f"{AG}/Team/Helper-agent"); open(f"{AG}/Team/Helper-agent/inbox.md", "w").write("# inbox\n\n## New\n\n## Done\n")
rc, o = run("helper", "5m", "nested"); ok("addressee 'helper' finds Team/Helper-agent (case, -agent, group)", rc == 0 and len(files()) == 1, o)
# the install's own HOME default dir (no REMIND_DIR): ~/.claude/reminders
rc, o = run("Tester", "5m", "default dir", REMIND_DIR=""); ok("default state dir is ~/.claude/reminders", rc == 0 and len(os.listdir(f"{R}/.claude/reminders")) == 1, o)
print(f"remind: {P} pass, {F} fail"); raise SystemExit(1 if F else 0)
