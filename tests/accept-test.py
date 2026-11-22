#!/usr/bin/env python3
"""scripts/accept.py + lib/human_quote.py on a synthetic transcript in a sandbox (temp HOME/workspace/transcripts,
no config file). Checks: a fragment in a message of the human -> ✅ and a line in ACCEPTED.jsonl; not there -> rc 2;
only in the assistant's text, a tool_result, a system-reminder, isMeta, a task-notification, a peer agent's message,
`claude -p` (sdk-cli), a compact summary, a <command-...>, an <ide_selection> -> refused; scripts/story_status.py shows
the record. ACC=<path to accept.py> tests another copy (its human_quote is imported from ../lib next to it).
Last line: accept-test: N pass, M fail."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
ACC = os.environ.get("ACC") or os.path.join(ROOT, "scripts", "accept.py")
SS = os.path.join(ROOT, "scripts", "story_status.py")
SID = "11111111-2222-3333-4444-555555555555"
NAME = "accept-test"
res = {"pass": 0, "fail": 0}


def check(cond, what, extra=""):
    if cond:
        res["pass"] += 1
        print(f"ok   {what}")
    else:
        res["fail"] += 1
        print(f"FAIL {what} {extra}")


def user(text, ts, **kw):
    r = {"type": "user", "message": {"role": "user", "content": text}, "timestamp": ts,
         "sessionId": SID, "entrypoint": "claude-vscode", "origin": {"kind": "human"}}
    r.update(kw)
    return r


T = tempfile.mkdtemp(prefix="accept-test.")
if not T or not os.path.isdir(T) or T == "/":
    print("no temp dir")
    sys.exit(2)
try:
    ws, projects, ident, home = (os.path.join(T, d) for d in ("ws", "projects", "ident", "home"))
    pd = os.path.join(ws, "Project-Game")
    os.makedirs(pd)
    os.makedirs(os.path.join(projects, "-home-x"))
    os.makedirs(ident)
    os.makedirs(home)
    root = os.geteuid() == 0
    if root:
        os.chown(pd, 65534, 65534)  # a folder of another user: the new ACCEPTED.jsonl must take its owner
    with open(os.path.join(pd, "ROADMAP.md"), "w", encoding="utf-8") as f:
        f.write("# R\n\n## EPIC 7 - Bugs\n- ⏳ **[E7.S2] wheel**\n- ⏳ **[E7.S3] lines**\n")
    with open(os.path.join(ident, SID), "w") as f:
        f.write(os.path.join(ws, "Agents", "Game-HQ") + "\n")
    recs = [
        user("the wheel works, no lines. yes, “I accept”   E7.S2", "2026-11-22T06:25:00.000Z"),
        user([{"type": "text", "text": "Block list: YES I ACCEPT the lines"}], "2026-11-22T06:30:00.000Z"),
        {"type": "attachment", "timestamp": "2026-11-22T06:40:00.000Z",
         "attachment": {"type": "queued_command", "commandMode": "prompt", "origin": {"kind": "human"},
                        "prompt": [{"type": "text", "text": "queued: taking the menu as is"}],
                        "timestamp": "2026-11-22T06:40:01.000Z"}},
        {"type": "assistant", "timestamp": "2026-11-22T06:41:00.000Z",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "the assistant says: assistant phrase here"}]}},
        user([{"type": "tool_result", "tool_use_id": "t1", "content": "tool output: secret tool phrase"}],
             "2026-11-22T06:42:00.000Z"),
        user("ok\n<system-reminder>\nhook reminder: phrase from the reminder\n</system-reminder>",
             "2026-11-22T06:43:00.000Z"),
        user("skill meta text: phrase from the meta", "2026-11-22T06:44:00.000Z", isMeta=True),
        user("<task-notification>\n<summary>phrase from the notification</summary>\n</task-notification>",
             "2026-11-22T06:45:00.000Z", origin={"kind": "task-notification"}),
        {"type": "attachment", "timestamp": "2026-11-22T06:46:00.000Z",
         "attachment": {"type": "queued_command", "commandMode": "prompt", "isMeta": True,
                        "origin": {"kind": "peer", "from": "uds:x"},
                        "prompt": "<cross-session-message from=\"x\">phrase from a fellow agent</cross-session-message>"}},
        user("[from agent: Shop-HQ] phrase through a script run", "2026-11-22T06:47:00.000Z", entrypoint="sdk-cli"),
        user("This session is being continued... phrase from the compact summary", "2026-11-22T06:48:00.000Z",
             isCompactSummary=True, isVisibleInTranscriptOnly=True),
        user("<command-name>/x</command-name><command-args>phrase from the command</command-args>",
             "2026-11-22T06:49:00.000Z"),
        user("<ide_selection>The user selected: phrase from the selection in a file</ide_selection>",
             "2026-11-22T06:50:00.000Z"),
    ]
    tp = os.path.join(projects, "-home-x", f"{SID}.jsonl")
    with open(tp, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write("{broken line\n")
        f.write('["user", "a list, not a record"]\n')

    env = dict(os.environ, CCM_TEST="1", HOME=home, CLAUDE_METHODOLOGY_CONF="/nonexistent", CCM_HUMAN_NAME="Alex",
               ACCEPT_REPO=ws, CLAUDE_PROJECTS_DIR=projects, ACCEPT_IDENTITY_DIR=ident, CLAUDE_CODE_SESSION_ID=SID)
    for k in ("CCM_PROJECTS_GLOB", "CCM_WORKSPACE"):
        env.pop(k, None)
    acc = os.path.join(pd, "ACCEPTED.jsonl")

    def run(*a, env_=None, script=ACC):
        p = subprocess.run([sys.executable, script, *a], env=env_ or env, capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout + p.stderr

    def nlines():
        return len(open(acc, encoding="utf-8").read().split("\n")) - 1 if os.path.exists(acc) else 0

    # 1. a message of the human (a string), other quotes/case/spacing
    rc, out = run("Project-Game", "e7.s2", 'no lines. YES, "i accept" e7.s2')
    check(rc == 0 and "✅" in out and "accepted by Alex" in out, "message of the human -> ✅ rc 0, names CCM_HUMAN_NAME",
          f"rc={rc} {out!r}")
    check(nlines() == 1, "1 line appended to ACCEPTED.jsonl", f"n={nlines()}")
    rec = json.loads(open(acc, encoding="utf-8").read().split("\n")[0]) if nlines() else {}
    check(rec.get("story") == "E7.S2" and rec.get("ts") == "2026-11-22T06:25:00.000Z" and rec.get("sid") == SID,
          "fields story/ts/sid", repr(rec))
    check(rec.get("quote", "").startswith("the wheel works") and rec.get("agent") == "Game-HQ" and rec.get("at"),
          "quote = the whole message, agent = basename of the identity, at present", repr(rec))
    st = os.stat(acc) if os.path.exists(acc) else os.stat(T)
    if root:
        check(st.st_uid == 65534 and st.st_mode & 0o777 == 0o664, "ACCEPTED.jsonl: the folder's owner, 664",
              f"uid={st.st_uid} mode={oct(st.st_mode)}")
    else:
        check(st.st_mode & 0o777 == 0o664, "ACCEPTED.jsonl: 664 (not root: owner not changed)", oct(st.st_mode))
    # 2. the same message again - no duplicate
    rc, out = run("Game", "E7.S2", "no lines. yes, i accept")
    check(rc == 0 and nlines() == 1 and "already recorded" in out, "repeat -> rc 0, no duplicate", f"rc={rc} n={nlines()} {out!r}")
    # 3. text blocks and queued_command are messages of the human too
    rc, out = run("Game", "E7.S3", "block list: yes i accept")
    check(rc == 0 and nlines() == 2, "text block -> ✅", f"rc={rc} {out!r}")
    rc, out = run("Game", "E7.S3", "taking the menu as is")
    check(rc == 0 and nlines() == 3, "queued_command (typed while the agent worked) -> ✅", f"rc={rc} {out!r}")
    # 4. refusals: not there / not the human
    before = nlines()
    for frag, what in [("nobody ever said this", "no such fragment"),
                       ("assistant phrase here", "only in the assistant's text"),
                       ("secret tool phrase", "only in a tool_result"),
                       ("phrase from the reminder", "only in a system-reminder"),
                       ("phrase from the meta", "only in isMeta"),
                       ("phrase from the notification", "only in a task-notification"),
                       ("phrase from a fellow agent", "only in a peer agent's message"),
                       ("phrase through a script run", "only in claude -p (sdk-cli)"),
                       ("phrase from the compact summary", "only in a compact summary"),
                       ("phrase from the command", "only in <command-...>"),
                       ("phrase from the selection in a file", "only in <ide_selection>")]:
        rc, out = run("Game", "E7.S2", frag)
        check(rc == 2 and "did not type this" in out, f"{what} -> rc 2", f"rc={rc} {out!r}")
    check(nlines() == before, "after the refusals ACCEPTED.jsonl unchanged", f"{before}->{nlines()}")
    # 5. usage errors
    rc, out = run("Game", "E7.S2", "yes ok")
    check(rc == 1 and "shorter" in out, "fragment < 8 characters -> rc 1", f"rc={rc} {out!r}")
    rc, out = run("Game", "E7.S9", "no lines. yes, i accept")
    check(rc == 4 and "not in" in out, "story not in ROADMAP -> rc 4", f"rc={rc} {out!r}")
    rc, out = run("Game", "E7.S", "no lines. yes, i accept")
    check(rc == 1 and "odd S-code" in out, "malformed code -> rc 1", f"rc={rc} {out!r}")
    rc, out = run("Nope", "E7.S2", "no lines. yes, i accept")
    check(rc == 4, "no project -> rc 4", f"rc={rc} {out!r}")
    env2 = {k: v for k, v in env.items() if k != "CLAUDE_CODE_SESSION_ID"}
    rc, out = run("Game", "E7.S2", "no lines. yes, i accept", env_=env2)
    check(rc == 1 and "session" in out, "no session -> rc 1", f"rc={rc} {out!r}")
    rc, out = run("Game", "E7.S2", "no lines. yes, i accept", "--session", "99999999-0000-0000-0000-000000000000")
    check(rc == 1 and "not found" in out, "another / missing session -> rc 1", f"rc={rc} {out!r}")
    rc, out = run("Game", "E7.S2", "no lines. yes, i accept", "--session", "../x*")
    check(rc == 1 and "odd session id" in out, "session id with glob/path characters -> rc 1", f"rc={rc} {out!r}")
    check(nlines() == before, "after the errors ACCEPTED.jsonl unchanged", f"{before}->{nlines()}")
    # 6. CCM_PROJECTS_GLOB: another folder prefix
    wd = os.path.join(ws, "Work-Tool")
    os.makedirs(wd)
    with open(os.path.join(wd, "ROADMAP.md"), "w", encoding="utf-8") as f:
        f.write("- ⏳ **[S4] menu**\n")
    rc, out = run("Tool", "S4", "taking the menu as is", env_=dict(env, CCM_PROJECTS_GLOB="Work-*"))
    check(rc == 0 and os.path.exists(os.path.join(wd, "ACCEPTED.jsonl")), "CCM_PROJECTS_GLOB=Work-* -> Work-Tool/ACCEPTED.jsonl",
          f"rc={rc} {out!r}")
    # 7. the module directly (scope: how many human messages it sees in the transcript)
    seen = -1
    hqp = os.path.join(os.path.dirname(os.path.realpath(ACC)), "..", "lib", "human_quote.py")
    if os.path.isfile(hqp):
        spec = importlib.util.spec_from_file_location("human_quote", hqp)
        hq = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hq)
        seen = 0
    with open(tp if seen == 0 else os.devnull, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            seen += bool(isinstance(r, dict) and hq.human_text(r))
    check(seen == 4, "the module sees exactly 4 human messages of 13 records (3 + \"ok\" without the reminder)", f"seen={seen}")
    # 8. story_status.py shows the accepted record (the reader of ACCEPTED.jsonl)
    if not os.environ.get("ACC"):
        rc, out = run("Game", "E7.S2", script=SS, env_=dict(env, STORY_REPO=ws))
        check(rc == 0 and "accepted by the human: ACCEPTED.jsonl:1" in out and "the wheel works" in out,
              "story_status.py E7.S2 -> the accepted line with the quote", f"rc={rc} {out!r}")
        rc, out = run("Game", "E7.S9", script=SS, env_=dict(env, STORY_REPO=ws))
        check(rc == 0 and "accepted by the human: - none" in out, "story_status.py, no record -> \"- none\"", f"rc={rc} {out!r}")
finally:
    shutil.rmtree(T)  # the test's own sandbox

print(f"{NAME}: {res['pass']} pass, {res['fail']} fail")
sys.exit(1 if res["fail"] else 0)
