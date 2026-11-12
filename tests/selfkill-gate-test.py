#!/usr/bin/env python3
"""selfkill-gate: pkill -f denied, pgrep -f hinted, remote pkill denied, detached alarm scripts denied (when configured).
Runs the repo copy; SG=<path> tests another one. Sandbox only: HOME is a temp dir, no config file."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SG = os.environ.get("SG", os.path.join(HERE, "..", "hooks", "selfkill-gate.py"))
T = tempfile.mkdtemp(prefix="sg-test-")
CONF = f"{T}/methodology.conf"          # CCM_ALARM_SCRIPTS is a new key: it is read from the config file
open(CONF, "w").write("CCM_ALARM_SCRIPTS=wait-alarm.sh\n")
ENV = {**os.environ, "HOME": T, "CLAUDE_METHODOLOGY_CONF": CONF, "HANZ_TEST": "1"}
P = F = 0


def sg(cmd):
    r = subprocess.run([sys.executable, SG], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
                       capture_output=True, text=True, env=ENV)
    t = r.stdout.strip()
    if not t:
        return ""
    h = json.loads(t)["hookSpecificOutput"]
    return h.get("permissionDecision", "") + "|" + h.get("additionalContext", "") + h.get("permissionDecisionReason", "")


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


o = sg("until ! pgrep -f foo.py; do sleep 1; done"); ok("1 until ! pgrep -f -> hint, not deny", o.startswith("|") and "pgrep -x" in o, o)
o = sg("pgrep -f '[f]oo.py'"); ok("2 pgrep -f with a character class -> silent", o == "", o)
o = sg("pgrep -x python3"); ok("3 pgrep -x -> silent", o == "", o)
o = sg("pkill -f foo"); ok("4 pkill -f -> deny", o.startswith("deny"), o)
o = sg("ssh box 'pkill -f docker'"); ok("5 remote pkill -f -> deny", o.startswith("deny") and "remote" in o, o)
o = sg("ssh box \"pkill -f '[d]ocker pull'\""); ok("5b remote with a character class -> silent", o == "", o)
o = sg("cat <<'E'\npkill -f foo\nE"); ok("6 pkill -f inside a heredoc -> silent", o == "", o)
o = sg("ls -la"); ok("7 unrelated command -> silent", o == "", o)
o = sg("wait-alarm.sh X & disown"); ok("16 alarm & disown -> deny", o.startswith("deny"), o)
o = sg("nohup /opt/bin/wait-alarm.sh X >/dev/null 2>&1"); ok("16b nohup alarm -> deny", o.startswith("deny"), o)
o = sg("wait-alarm.sh X 2>&1 | tail -3"); ok("16c 2>&1 is not a background -> pass", o == "", o)
o = sg("cd /x && wait-alarm.sh X"); ok("16d && is not a background -> pass", o == "", o)
o = sg("grep wait-alarm /tmp/log &"); ok("16e other command with the word -> pass", o == "", o)
o = sg("mail.sh X 'gate: wait-alarm.sh with & disown - deny'"); ok("16f words in a quoted message -> pass", o == "", o)
o = sg("cat <<E\nwait-alarm.sh & disown\nE"); ok("16g heredoc -> pass", o == "", o)
open(CONF, "w").write("CCM_ALARM_SCRIPTS=\n")
o = sg("wait-alarm.sh X & disown"); ok("17 no alarm scripts configured -> rule off", o == "", o)
print(f"selfkill-gate: {P} pass, {F} fail"); raise SystemExit(1 if F else 0)
