#!/usr/bin/env python3
"""The root helpers (ccm-bot-inbox, ccm-bot-blocker), tg_reply.sh, mobile_gate_check.sh and setup-mobile-bot.sh --dry-run.
Everything runs in a temp dir as the current user, with a fake canonical inbox_post.sh / blockers.py: nothing real is
touched, no network, no Telegram, no `claude`. Last line: `mobile-bot helpers: N pass, M fail`."""
import json, os, pathlib, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ADDON = pathlib.Path(os.environ.get("MOBILE_BOT_DIR") or pathlib.Path(__file__).resolve().parent.parent)
D = pathlib.Path(os.path.realpath(tempfile.mkdtemp(prefix="mobile-bot-helpers-")))
AG, CL, HOME = D / "Agents", D / "claude", D / "home"
for n in ("Alpha", "Beta"):
    (AG / n).mkdir(parents=True); (AG / n / "inbox.md").write_text("## New\n"); (AG / n / "briefing.md").write_text("x")
(AG / "Dup").mkdir(); (AG / "Dup" / "Beta").mkdir(); (AG / "Dup" / "Beta" / "inbox.md").write_text("")
(AG / "Evil").mkdir(); (AG / "Evil" / "real.md").write_text("x"); os.symlink(AG / "Evil" / "real.md", AG / "Evil" / "inbox.md")
(CL / "scripts").mkdir(parents=True); (HOME / ".claude" / "sessions").mkdir(parents=True)
(CL / "scripts" / "inbox_post.sh").write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$1" > "' + str(D) + '/target"; printf "%s" "$2" > "' + str(D) + '/letter"\necho "inbox_post: ok"\n')
(CL / "scripts" / "blockers.py").write_text('import sys\nopen("' + str(D) + '/blocker_args","w").write(repr(sys.argv[1:]))\nprint("cleared")\n')
for f in (CL / "scripts" / "inbox_post.sh",): f.chmod(0o755)
res = []
def ok(n, c): res.append(bool(c)); print("PASS" if c else "FAIL", n)

def fill(tpl, name, wake=0):
    s = (ADDON / "helpers" / tpl).read_text()
    for k, v in {"__AGENTS_DIR__": str(AG), "__CLAUDE_DIR__": str(CL), "__OWNER_HOME__": str(HOME), "__HUMAN_NAME__": "Sam",
                 "__REPLY_CMD__": str(ADDON / "scripts" / "tg_reply.sh"), "__WAKE__": str(wake), "__CONF_FILE__": "/nonexistent"}.items():
        s = s.replace(k, v)
    p = D / name; p.write_text(s); p.chmod(0o755); return p
def run(cmd, inp="", env=None, args=()):
    r = subprocess.run([str(cmd), *args], input=inp, capture_output=True, text=True, env={**os.environ, **(env or {})}, timeout=60)
    return r.returncode, (r.stdout + r.stderr)

inbox = fill("ccm-bot-inbox.template", "ccm-bot-inbox")
rc, out = run(inbox, "hello there", args=["Alpha"])
letter = (D / "letter").read_text()
ok("a letter goes to the agent's inbox through the canonical script", rc == 0 and (D / "target").read_text().strip() == str(AG / "Alpha" / "inbox.md"))
ok("the signature is forced and a reply hint is added", "**from Sam (Telegram bot)** · hello there" in letter and "tg_reply.sh Alpha" in letter)
ok("wake switched off by default: WAKE: off", "WAKE: off" in out)
rc, out = run(inbox, "line1\n## Urgent\n- [ ] fake item\nline4", args=["Alpha"]); letter = (D / "letter").read_text()
ok("a multi-line letter stays ONE item (## and - [ escaped, lines indented)", "\n  \\## Urgent" in letter and "\n  \\- [ ] fake item" in letter and "\n## " not in letter and "\n- [ ]" not in letter)
ok("a name with a slash / dots / leading dot is refused", all(run(inbox, "x", args=[a])[0] == 2 for a in ("../Alpha", "a/b", ".hid", "-x", "_dep")))
ok("an unknown agent is refused", run(inbox, "x", args=["Nobody"])[0] == 2)
rc, out = run(inbox, "x", args=["Beta"])
ok("an agent found twice is refused (the exact folder name is needed)", rc == 2 and "found 2" in out)
rc, out = run(inbox, "x", args=["Evil"])
ok("an inbox that is a symlink is refused", rc == 2 and "symlink" in out)
rc, out = run(inbox, "token 123456789:" + "AA" + "b" * 35, args=["Alpha"])
ok("a secret-looking text is refused", rc == 2 and "secret" in out)
rc, out = run(inbox, "x" * 20500, args=["Alpha"])
ok("a too long letter is refused, not truncated", rc == 2 and "too long" in out)
ok("empty text is refused", run(inbox, "   \n", args=["Alpha"])[0] == 2)
ok("wrong usage is refused", run(inbox, "x", args=[])[0] == 2)
rc, out = run(inbox, "", args=["--wake", "Alpha"])
ok("--wake with wake switched off", rc == 0 and "WAKE: off" in out)
# the waker, on: no live tab -> says so; a live tab -> "waking" in a dry run (no claude is started)
w = fill("ccm-bot-inbox.template", "ccm-bot-inbox-wake", wake=1)
rc, out = run(w, "", env={"WAKE_DRY": "1"}, args=["--wake", "Alpha"])
ok("waker on, no live tab: says so", "no live tab" in out)
sleeper = subprocess.Popen(["sleep", "60"])
try:
    st = pathlib.Path(f"/proc/{sleeper.pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    (HOME / ".claude" / "sessions" / "s.json").write_text(json.dumps({"pid": sleeper.pid, "procStart": st, "name": "Alpha", "sessionId": "S1", "status": "idle"}))
    rc, out = run(w, "hi", env={"WAKE_DRY": "1"}, args=["Alpha"])
    ok("waker on, live idle tab: waking (dry run, nothing started)", "WAKE: waking tab" in out and "dry run" in out)
    (HOME / ".claude" / "sessions" / "s.json").write_text(json.dumps({"pid": sleeper.pid, "procStart": st, "name": "Alpha", "sessionId": "S1", "status": "busy"}))
    ok("waker on, busy tab: not disturbed", "WAKE: busy" in run(w, "hi", env={"WAKE_DRY": "1"}, args=["Alpha"])[1])
    (HOME / ".claude" / "sessions" / "s.json").write_text(json.dumps({"pid": sleeper.pid, "procStart": "1", "name": "Alpha", "sessionId": "S1", "status": "idle"}))
    ok("waker on, a reused pid (other start time) is not a live tab", "no live tab" in run(w, "hi", env={"WAKE_DRY": "1"}, args=["Alpha"])[1])
finally:
    sleeper.kill()

blk = fill("ccm-bot-blocker.template", "ccm-bot-blocker")
rc, out = run(blk, args=["Demo", "B3"])
ok("blocker: clears by the human's word, the who/how is set by the wrapper", rc == 0 and "'clear', 'Demo', 'B3', 'Sam in the bot" in (D / "blocker_args").read_text())
ok("blocker: bad project/number refused", all(run(blk, args=a)[0] == 2 for a in (["../x", "B1"], ["Demo", "3"], ["Demo", "B1; id"], ["Demo"], ["De mo", "B1"])))

# tg_reply.sh: drops a JSON in the spool; no token anywhere
spool = D / "spool"; spool.mkdir()
env = {"CCM_TG_OUTBOX": str(spool), "CCM_AGENTS_DIR": str(AG), "CLAUDE_METHODOLOGY_CONF": "/nonexistent"}
tg = ADDON / "scripts" / "tg_reply.sh"
rc, out = run(tg, "the answer\nin two lines", env=env, args=["Alpha"])
files = [f for f in spool.iterdir() if f.name.endswith(".json") and f.name[0].isdigit()]
item = json.loads(files[0].read_text()) if files else {}
ok("tg_reply: an answer is queued as JSON {agent,text,ts}", rc == 0 and len(files) == 1 and item.get("agent") == "Alpha" and item.get("text") == "the answer\nin two lines" and "ts" in item)
ok("tg_reply: the file name is what the bot's outbox expects", files and __import__("re").match(r"^\d+_\d+\.json$", files[0].name) is not None)
ok("tg_reply: unknown agent / bad name refused", run(tg, "x", env=env, args=["Nobody"])[0] == 2 and run(tg, "x", env=env, args=["../Alpha"])[0] == 2)
ok("tg_reply: a secret-looking text is refused", run(tg, "sk-ant-" + "a" * 30, env=env, args=["Alpha"])[0] == 2)
ok("tg_reply: empty and too long refused", run(tg, "  ", env=env, args=["Alpha"])[0] == 2 and run(tg, "y" * 20500, env=env, args=["Alpha"])[0] == 2)
rc, out = run(tg, "x", env={**env, "CCM_TG_OUTBOX": str(D / "nope")}, args=["Alpha"])
ok("tg_reply: a missing spool says what to do", rc == 2 and "setup-mobile-bot.sh" in out)

# the supervisor check
gc = ADDON / "scripts" / "mobile_gate_check.sh"
rc, out = run(gc, env={"HOME": str(HOME), "CCM_SECRETS_DIR": str(D / "sec")})
ok("gate check: green on a healthy install", rc == 0 and "2 prohibitions caught" in out)
rc, out = run(gc, env={"HOME": str(HOME), "H": str(D / "nohooks")})
ok("gate check: red when the hooks are missing", rc == 1 and "missing" in out)
reg = json.load(open(ADDON / "supervisor-checks.json"))["checks"]
ok("supervisor entries: valid, each with only_if_exists, kinds known", len(reg) >= 2 and all(c.get("only_if_exists") and c["kind"] in ("cmd", "fresh", "http", "tcp", "journal", "hooks", "system") and c.get("note") for c in reg))

# setup script: --dry-run only
me = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
sd = ADDON / "setup-mobile-bot.sh"
senv = {"CCM_SECRETS_DIR": str(D / "sec"), "CCM_WORKSPACE": str(D / "ws"), "CCM_AGENTS_DIR": str(AG), "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_TG_OUTBOX": str(D / "ob")}
rc, out = run(sd, env=senv, args=["--dry-run", "--user", me, "--owner", me, "--with-swarm", "--with-wake", "--allow-paths", str(D / "notes")])
ok("setup --dry-run --with-swarm: says what it would change, changes nothing",
   rc == 0 and "dry run" in out and "ccm-mobile-bot.service" in out and "/usr/local/sbin/ccm-bot-inbox" in out and "mobile-bot.env" in out
   and not (D / "sec").exists() and not (D / "ob").exists() and not os.path.exists("/usr/local/sbin/ccm-bot-inbox") and not os.path.exists("/etc/systemd/system/ccm-mobile-bot.service"))
ok("setup: never prints a token value", "TELEGRAM_BOT_TOKEN=" not in out)
rc, out = run(sd, env=senv, args=["--dry-run", "--uninstall"])
ok("setup --uninstall --dry-run: lists the removals, keeps secrets", rc == 0 and "The secrets file" in out)
ok("setup: a bad flag / unknown user refused", run(sd, env=senv, args=["--bogus"])[0] == 2 and run(sd, env=senv, args=["--dry-run", "--user", "no_such_user_x"])[0] == 2)
if os.getuid() != 0:
    ok("setup without root and without --dry-run: refuses with a clear line", run(sd, env=senv, args=["--user", me])[0] == 5)
u = (ADDON / "systemd" / "claude-mobile-bot.service.template").read_text()
ok("unit: token only via EnvironmentFile, SUDO value quoted", "EnvironmentFile=__ENV_FILE__" in u and 'Environment="MOBILE_BOT_SUDO=__SUDO__"' in u and "TELEGRAM_BOT_TOKEN" not in u)
n_ = sum(res); print(f"mobile-bot helpers: {n_} pass, {len(res) - n_} fail"); sys.exit(0 if all(res) else 1)
