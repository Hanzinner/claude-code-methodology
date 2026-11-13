#!/usr/bin/env python3
"""supervisor.py engine: red/green, a letter to the OWNER through a stub inbox_post (dedup: not again while the copy sits in
"New" and not within 6 h), a broken check goes to the infra agent only, silence after downtime (grace), the human flag for
severity "human" + the recovery flag, summary.json / heartbeat, restart through a stub systemctl, hooks kind, paused project,
disabled check, --init, --dry-run. SUP=<path> tests another copy. Sandbox only: temp HOME, no config file, CCM_* env into the
temp dir, a stub systemctl first in PATH; no network, nothing outside the temp dir."""
import json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.realpath(__file__))
SUP = os.environ.get("SUP", os.path.join(HERE, "..", "scripts", "supervisor.py"))
R = tempfile.mkdtemp(prefix="sup-test-"); AG = f"{R}/Agents"; ST = f"{R}/state"; BIN = f"{R}/bin"; SESS = f"{R}/sessions"; FL = f"{R}/flags"
for a in ("Owner", "Infra", "Second"):
    os.makedirs(f"{AG}/{a}"); open(f"{AG}/{a}/inbox.md", "w").write("# inbox\n\n## New\n\n## Done\n")
os.makedirs(BIN); os.makedirs(SESS)
POST = f"{R}/post.py"
open(POST, "w").write(f"""#!/usr/bin/env python3
import sys
p = "{AG}/" + sys.argv[1] + "/inbox.md"
t = open(p, encoding="utf-8").read().replace("## New\\n", "## New\\n\\n" + sys.argv[2] + "\\n", 1)
open(p, "w", encoding="utf-8").write(t)
""")
os.chmod(POST, 0o755)
# stub systemctl: "show" -> NRestarts 0; "is-active" -> dead; "restart" -> creates the file the check waits for
open(f"{BIN}/systemctl", "w").write(f"""#!/bin/sh
case "$1" in
  show) echo 0 ;;
  is-active) exit 3 ;;
  restart) echo "$2" >> {R}/restarts.log; touch {R}/svc-up ;;
esac
""")
os.chmod(f"{BIN}/systemctl", 0o755)
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:400])


def env(**kw):
    e = {**os.environ, "HOME": R, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_AGENTS_DIR": AG, "CCM_CLAUDE_DIR": R,
         "CCM_HUMAN_NAME": "Tester", "SUPERVISOR_POST": POST, "SUPERVISOR_SESSIONS": SESS, "SUPERVISOR_FLAGS": FL,
         "SUPERVISOR_HUMAN_RECHECK_S": "0", "SUPERVISOR_RECHECK_S": "0", "SUPERVISOR_FLAP_S": "0", "PATH": f"{BIN}:{os.environ['PATH']}"}
    for k in ("CCM_INFRA_AGENT", "CCM_SUPERVISOR_HEARTBEAT", "CCM_SUPERVISOR_PAUSED"):
        e.pop(k, None)
    e.update(kw)
    return e


def run(checks, state=ST, *args, **kw):
    os.makedirs(state, exist_ok=True)
    cf = f"{state}/checks.json"
    json.dump({"checks": checks}, open(cf, "w"))
    r = subprocess.run([sys.executable, SUP, "--checks", cf, "--state", state, *args], capture_output=True, text=True, env=env(**kw))
    return r.returncode, r.stdout + r.stderr


def inbox(a): return open(f"{AG}/{a}/inbox.md", encoding="utf-8").read()
def clear(a): open(f"{AG}/{a}/inbox.md", "w").write("# inbox\n\n## New\n\n## Done\n")
def summary(state=ST): return json.load(open(f"{state}/summary.json"))
def red(name="Red thing", **kw): return {"name": name, "kind": "cmd", "cmd": "echo broke; exit 1", "owner": "Owner", **kw}


# 1. green check: nothing red, summary + heartbeat written, no letters
rc, o = run([{"name": "Fine", "kind": "cmd", "cmd": "true", "owner": "Owner"}])
ok("1 green: rc 0, no problems in summary.json", rc == 0 and summary()["problems"] == [] and summary()["checks"] == 1, o)
ok("1b heartbeat is an epoch", abs(int(open(f"{ST}/heartbeat").read()) - time.time()) < 60)
ok("1c no letter", "Supervisor" not in inbox("Owner"))

# 2. red check -> a letter to the owner, summary lists it
rc, o = run([red()])
ok("2 red: summary.json problems + severity", summary()["problems"] == ["Red thing"] and summary()["details"][0]["severity"] == "infra", summary())
ok("2b the owner got ONE letter naming the check", inbox("Owner").count("«Red thing» is failing") == 1 and "broke" in inbox("Owner"), inbox("Owner"))
ok("2c a non-owner got nothing", "Supervisor" not in inbox("Infra"))

# 3. the same alarm again: not while the copy still sits in New, and not within 6 h even after it was processed
run([red()])
ok("3 no duplicate while the letter is unprocessed", inbox("Owner").count("is failing") == 1)
clear("Owner")
run([red()])
ok("3b no repeat within 6 h of the last alarm", "is failing" not in inbox("Owner"), inbox("Owner"))
st = json.load(open(f"{ST}/state.json")); st["Red thing"]["last_alert"] -= 7 * 3600; json.dump(st, open(f"{ST}/state.json", "w"))
run([red()])
ok("3c after 6 h it is sent again", inbox("Owner").count("is failing") == 1)

# 4. no owner -> no letter anywhere, still in summary
clear("Owner")
rc, o = run([red("No owner", owner="")], state=f"{R}/s4")
ok("4 no owner: no letter, but in summary", "Supervisor" not in inbox("Owner") + inbox("Infra") and summary(f"{R}/s4")["problems"] == ["No owner"], o)

# 5. several owners
rc, o = run([red("Two owners", owner=["Owner", "Second"])], state=f"{R}/s5")
ok("5 a list of owners: both are told", "Two owners" in inbox("Owner") and "Two owners" in inbox("Second"))
clear("Owner"); clear("Second")

# 6. a BROKEN check (rc 127 / rc 3 / traceback) -> not "the object is down": the infra agent only, no restart, flagged as broken
rc, o = run([{"name": "Bad probe", "kind": "cmd", "cmd": "no-such-command-xyz", "owner": "Owner", "severity": "human"}], state=f"{R}/s6", CCM_INFRA_AGENT="Infra")
ok("6 broken check: listed as broken, not as a problem", summary(f"{R}/s6")["broken_checks"] == ["Bad probe"] and summary(f"{R}/s6")["problems"] == [], summary(f"{R}/s6"))
ok("6b the infra agent got CHECK BROKEN; the owner did not", "CHECK BROKEN" in inbox("Infra") and "Supervisor" not in inbox("Owner"), inbox("Infra"))
ok("6c a report line marks it as broken (gear), not failed", "⚙ Bad probe" in o, o)
clear("Infra")
rc, o = run([{"name": "Unknown", "kind": "cmd", "cmd": "exit 3", "owner": "Owner"}], state=f"{R}/s6b")
ok("6d rc 3 (UNKNOWN) = broken check, letter to the owner when no infra agent is set", "CHECK BROKEN" in inbox("Owner"), inbox("Owner"))
clear("Owner")

# 7. silence after downtime: the supervisor's own gap between runs > 20 min -> age checks stay quiet; others do not
old = f"{R}/old.txt"; open(old, "w").write("x"); os.utime(old, (time.time() - 7200,) * 2)
fresh_chk = {"name": "Stale file", "kind": "fresh", "path": old, "max_age_min": 30, "owner": "Owner"}
s7 = f"{R}/s7"; os.makedirs(s7); open(f"{s7}/heartbeat", "w").write(str(int(time.time() - 3 * 3600)))   # last ran 3 h ago
rc, o = run([fresh_chk, red("Not an age check", owner="Second")], state=s7)
ok("7 after downtime: the age check is quiet (listed as after_downtime), no letter", summary(s7)["after_downtime"] == ["Stale file"] and "Stale file" not in inbox("Owner"), o)
ok("7b a non-age check is NOT silenced by downtime", "Not an age check" in inbox("Second"), inbox("Second"))
ok("7c the report says it is waiting", "⏳ Stale file" in o, o)
clear("Second")
rc, o = run([fresh_chk], state=s7)    # the next run, the gap is gone, grace (the check's own 30 min) still counts from the resume
ok("7d still quiet inside the grace window", summary(s7)["after_downtime"] == ["Stale file"])
st = json.load(open(f"{s7}/state.json")); st["__meta"]["resumed_at"] -= 3600; json.dump(st, open(f"{s7}/state.json", "w"))
rc, o = run([fresh_chk], state=s7)
ok("7e after the grace window the stale file is red and the owner is told", "Stale file" in summary(s7)["problems"] and "Stale file" in inbox("Owner"), o)
clear("Owner")
s7b = f"{R}/s7b"; os.makedirs(s7b); open(f"{s7b}/heartbeat", "w").write(str(int(time.time() - 600)))   # ran 10 min ago: no downtime
rc, o = run([fresh_chk], state=s7b)
ok("7f no downtime -> the same stale file is red at once", "Stale file" in summary(s7b)["problems"], o)
clear("Owner")

# 8. severity human: a flag for every LIVE session (pid alive), none for dead ones; recovery flag on green
json.dump({"pid": os.getpid(), "sessionId": "sess-live"}, open(f"{SESS}/1.json", "w"))
json.dump({"pid": 2 ** 22 + 12345, "sessionId": "sess-dead"}, open(f"{SESS}/2.json", "w"))
flip = f"{R}/flip"; open(flip, "w").write("")
chk8 = {"name": "Human thing", "kind": "cmd", "cmd": f"test ! -e {flip}", "owner": "Owner", "severity": "human"}
s8 = f"{R}/s8"
rc, o = run([chk8], state=s8)
ok("8 severity human: flag for the live session, text names the check", os.path.isfile(f"{FL}/sess-live") and "Human thing" in open(f"{FL}/sess-live").read(), o)
ok("8b no flag for the dead session", not os.path.exists(f"{FL}/sess-dead"))
ok("8c the flag text is finished English addressed to the agent", "[supervisor]" in open(f"{FL}/sess-live").read() and "Tester" in open(f"{FL}/sess-live").read())
os.remove(flip); os.remove(f"{FL}/sess-live")
rc, o = run([chk8], state=s8)
ok("8d recovery: a 'works again' flag", os.path.isfile(f"{FL}/sess-live") and "works again" in open(f"{FL}/sess-live").read(), o)
os.remove(f"{FL}/sess-live"); clear("Owner")
rc, o = run([red("Infra thing", severity="infra")], state=f"{R}/s8b")
ok("8e severity infra: a letter but no flag", not os.path.exists(f"{FL}/sess-live"))
clear("Owner")

# 9. restart through the stub systemctl: the service check goes green after `restart`
up = f"{R}/svc-up"
if os.path.exists(up): os.remove(up)
rc, o = run([{"name": "Svc", "kind": "cmd", "cmd": f"test -e {up}", "service": "my-svc", "owner": "Owner"}], state=f"{R}/s9")
ok("9 a failing service is restarted and the check is green after", open(f"{R}/restarts.log").read().strip() == "my-svc" and summary(f"{R}/s9")["problems"] == [] and "cured" in o, o)
os.remove(up); os.remove(f"{R}/restarts.log")
rc, o = run([{"name": "Svc2", "kind": "cmd", "cmd": "false", "service": "my-svc", "owner": "Owner", "restart_only_if_dead": True}], state=f"{R}/s9c")
ok("9b a service that never recovers ends red and the owner is told", "Svc2" in summary(f"{R}/s9c")["problems"] and "Svc2" in inbox("Owner"), o)
clear("Owner")

# 10. --dry-run: nothing is posted, no restart
rc, o = run([red("Dry")], f"{R}/s10", "--dry-run")
ok("10 dry-run: red in summary, no letter", summary(f"{R}/s10")["problems"] == ["Dry"] and "Supervisor" not in inbox("Owner"), o)

# 11. disabled / only_if_exists / paused project
paused = f"{R}/paused.txt"; open(paused, "w").write("# comment\nProjX\n")
rc, o = run([red("Off", enabled=False), red("Gated", only_if_exists=f"{R}/nothing-here"), red("Paused", project="ProjX"), red("Live", project="ProjY", owner="Second")],
            state=f"{R}/s11", CCM_SUPERVISOR_PAUSED=paused)
ok("11 disabled, gated and paused-project checks are not red; the live one is", summary(f"{R}/s11")["problems"] == ["Live"], summary(f"{R}/s11"))
ok("11b paused/disabled checks send nothing", "Off" not in inbox("Owner") and "Paused" not in inbox("Owner"))
clear("Second")

# 12. hooks kind: a hook file missing -> red; present and executable -> green; a branch of stop-dispatch without its file -> red
hd = f"{R}/hooks"; os.makedirs(hd)
open(f"{hd}/good.sh", "w").write("#!/bin/sh\n"); os.chmod(f"{hd}/good.sh", 0o755)
sets = f"{R}/settings.json"
json.dump({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": f'"{hd}/good.sh"'}, {"type": "command", "command": f'"{hd}/gone.sh"'}]}]}}, open(sets, "w"))
rc, o = run([{"name": "Hooks", "kind": "hooks", "owner": "Owner"}], state=f"{R}/s12", SUPERVISOR_SETTINGS=sets)
ok("12 a missing hook file is red and named", summary(f"{R}/s12")["problems"] == ["Hooks"] and "missing gone.sh" in o, o)
json.dump({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": f'"{hd}/good.sh"'}]}]}}, open(sets, "w"))
rc, o = run([{"name": "Hooks", "kind": "hooks"}], state=f"{R}/s12b", SUPERVISOR_SETTINGS=sets)
ok("12b all hooks present -> green", summary(f"{R}/s12b")["problems"] == [], o)
os.chmod(f"{hd}/good.sh", 0o644)
rc, o = run([{"name": "Hooks", "kind": "hooks"}], state=f"{R}/s12c", SUPERVISOR_SETTINGS=sets)
ok("12c a hook called directly without +x is red", "no +x good.sh" in o, o)
open(f"{hd}/stop-dispatch.sh", "w").write("#!/bin/sh\nBLOCKING=(alpha)\nDETECTORS=(beta gamma)\n"); os.chmod(f"{hd}/stop-dispatch.sh", 0o755)
open(f"{hd}/alpha.py", "w").write("import os\n"); open(f"{hd}/beta.py", "w").write("import os\n")
json.dump({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": f'"{hd}/stop-dispatch.sh"'}]}]}}, open(sets, "w"))
rc, o = run([{"name": "Hooks", "kind": "hooks"}], state=f"{R}/s12d", SUPERVISOR_SETTINGS=sets)
ok("12d a dispatcher branch with no file (gamma) is red, the present ones are not", "dispatch branch gamma" in o and "branch alpha" not in o and "branch beta" not in o, o)

# 13. heartbeat key: the supervisor also writes CCM_SUPERVISOR_HEARTBEAT (what the watchman reads)
hb = f"{R}/hb/pulse"
rc, o = run([{"name": "Fine", "kind": "cmd", "cmd": "true"}], state=f"{R}/s13", CCM_SUPERVISOR_HEARTBEAT=hb)
ok("13 CCM_SUPERVISOR_HEARTBEAT gets the epoch", os.path.isfile(hb) and abs(int(open(hb).read()) - time.time()) < 60, o)

# 14. a registry that cannot be read -> rc 2 with a message, not a traceback and not a silent green
bad = f"{R}/s14"; os.makedirs(bad); open(f"{bad}/checks.json", "w").write("{not json")
r = subprocess.run([sys.executable, SUP, "--checks", f"{bad}/checks.json", "--state", bad], capture_output=True, text=True, env=env())
ok("14 unreadable registry: rc 2 + message", r.returncode == 2 and "cannot read the registry" in r.stderr and "Traceback" not in r.stderr, r.stderr)

# 15. --init renders the placeholders and does not overwrite
tpl = f"{R}/tpl.json"; open(tpl, "w").write('{"checks": [{"name": "x", "kind": "cmd", "cmd": "python3 \\"__CLAUDE_DIR__/scripts/a.py\\"", "path": "__HOME__/x"}]}')
dst = f"{R}/s15/checks.json"
r = subprocess.run([sys.executable, SUP, "--init", tpl, "--checks", dst, "--state", f"{R}/s15"], capture_output=True, text=True, env=env())
j = json.load(open(dst)) if os.path.isfile(dst) else {}
ok("15 --init: placeholders replaced", j and R in j["checks"][0]["cmd"] and j["checks"][0]["path"] == f"{R}/x" and "__" not in json.dumps(j), r.stdout + r.stderr)
open(dst, "w").write('{"checks": []}')
r = subprocess.run([sys.executable, SUP, "--init", tpl, "--checks", dst, "--state", f"{R}/s15"], capture_output=True, text=True, env=env())
ok("15b --init leaves an existing registry alone", open(dst).read() == '{"checks": []}', r.stdout)

# 16. the shipped template is valid and every cmd points to a script that exists in this repo
tp = os.path.join(HERE, "..", "config", "supervisor-checks.template.json")
if os.path.isfile(tp) and "SUP" not in os.environ:
    t = json.load(open(tp))["checks"]
    import re
    missing = [m for c in t for m in re.findall(r'__CLAUDE_DIR__/scripts/([\w.-]+)', c.get("cmd", "")) if not os.path.isfile(os.path.join(HERE, "..", "scripts", m))]
    ok("16 the registry template: valid JSON, every script it names exists", t and not missing, missing)
    ok("16b every template check has name, kind, owner field", all({"name", "kind", "owner"} <= set(c) for c in t))

print(f"supervisor: {P} pass, {F} fail")
sys.exit(1 if F else 0)
