#!/usr/bin/env python3
"""scripts/accept.py + lib/human_quote.py on a synthetic transcript in a sandbox (temp HOME/workspace/transcripts,
no config file). Checks: a fragment in a message of the human -> ✅ and a line in ACCEPTED.jsonl; not there -> rc 2;
only in the assistant's text, a tool_result, a system-reminder, isMeta, a task-notification, a peer agent's message,
`claude -p` (sdk-cli), a compact summary, a <command-...>, an <ide_selection> -> refused; scripts/story_status.py shows
the record. Short form ("yes" / "+" / "ok", under 8 characters; a session of its own with parentUuid chains): a whole
message of the human that is a word of agreement + the S-code in the last assistant message before it (in the same
branch) -> ✅ with short_form/question; otherwise rc 2; Ukrainian words only with CCM_LANG_EXTRA=uk.
ACC=<path to accept.py> tests another copy (its human_quote is imported from ../lib next to it).
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
    root = getattr(os, "geteuid", lambda: -1)() == 0   # Windows Python has no geteuid
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
    for k in ("CCM_PROJECTS_GLOB", "CCM_WORKSPACE", "CCM_LANG_EXTRA"):
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
    elif os.name == "nt":
        print("SKIP on Windows: ACCEPTED.jsonl 664 - a file mode there is only the read-only flag (chmod does not set group bits)")
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
    check(rc == 2 and "WHOLE" in out and "ask Alex again" in out,
          "fragment < 8 characters, no such whole message -> rc 2 with what to do", f"rc={rc} {out!r}")
    rc, out = run("Game", "E7.S2", "ok")
    check(rc == 2 and "does not name E7.S2" in out,
          "\"ok\" as a whole message, older transcript without parentUuid (file order), assistant without the code -> rc 2",
          f"rc={rc} {out!r}")
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
    # 7. short form - a session of its own, records with uuid/parentUuid as in a real transcript
    SID2 = "22222222-3333-4444-5555-666666666666"
    pd2 = os.path.join(ws, "Project-Short")
    os.makedirs(pd2)
    with open(os.path.join(pd2, "ROADMAP.md"), "w", encoding="utf-8") as f:
        f.write("# S\n\n## EPIC 7\n" + "".join(f"- ⏳ **[E7.S{i}] story {i}**\n" for i in range(2, 14)))
    with open(os.path.join(ident, SID2), "w") as f:
        f.write(os.path.join(ws, "Agents", "Short-HQ") + "\n")
    recs2, seq = [], [0]

    def add(rec, parent="__last__"):
        seq[0] += 1
        u = f"u{seq[0]:03d}"
        rec = dict(rec, uuid=u, sessionId=SID2,
                   parentUuid=(recs2[-1]["uuid"] if recs2 else None) if parent == "__last__" else parent)
        recs2.append(rec)
        return u

    def asst(mid, *blocks, **kw):
        return add({"type": "assistant", "timestamp": "2026-11-22T07:00:00.000Z",
                    "message": {"id": mid, "role": "assistant", "content": list(blocks)}}, **kw)

    def txt(t):
        return {"type": "text", "text": t}

    def hum(t, ts, **kw):
        return add(user(t, ts), **kw)

    hum("make the wheel", "2026-11-22T07:00:00.000Z")
    asst("m1", {"type": "thinking", "thinking": "thinking about E7.S11"})
    asst("m1", txt("The wheel is ready, have a look. Do you accept [E7.S2]?"))
    add({"type": "system", "subtype": "stop_hook_summary", "timestamp": "2026-11-22T07:01:00.000Z"})
    hum("Yes!", "2026-11-22T07:01:00.000Z")                          # -> E7.S2 accepted
    # E7.S3: the code is in the previous API message, the last message has none
    asst("m2", txt("Story E7.S3 is done."))
    asst("m2", {"type": "tool_use", "id": "t2", "name": "Bash", "input": {}})
    add(user([{"type": "tool_result", "tool_use_id": "t2", "content": "ok"}], "2026-11-22T07:02:00.000Z"))
    asst("m3", txt("Do you accept?"))
    hum("+", "2026-11-22T07:03:00.000Z")
    # E7.S4: the code is in the first text block of the same API message (each block is a record of its own)
    asst("m4", txt("Story E7.S4 is ready."))
    asst("m4", txt("Do you accept?"))
    hum("ok", "2026-11-22T07:04:00.000Z")
    # no code: a "yes" to another question
    asst("m5", txt("Delete the old file?"))
    hum("yes", "2026-11-22T07:05:00.000Z")
    # "accept" only inside a longer message
    asst("m6", txt("Do you accept E7.S6?"))
    hum("accept, but change the button", "2026-11-22T07:06:00.000Z")
    # E7.S8: a "yes" only from non-humans
    asst("m8", txt("Do you accept E7.S8?"))
    add(user("yes", "2026-11-22T07:08:00.000Z", origin={"kind": "task-notification"}))
    add(user("[from agent: Shop-HQ] yes", "2026-11-22T07:08:01.000Z", entrypoint="sdk-cli"))
    add(user("<system-reminder>yes</system-reminder>", "2026-11-22T07:08:02.000Z"))
    add(user("yes", "2026-11-22T07:08:03.000Z", isMeta=True))
    add({"type": "attachment", "timestamp": "2026-11-22T07:08:04.000Z",
         "attachment": {"type": "queued_command", "commandMode": "prompt", "isMeta": True,
                        "origin": {"kind": "peer", "from": "uds:x"}, "prompt": "yes"}})
    asst("m8b", txt("Got the notification, looking further."))
    hum("show the log", "2026-11-22T07:08:10.000Z")
    # E7.S9: branches - the "yes" hangs on the "Delete?" branch, "Do you accept E7.S9?" is on the sibling (rewind/fork)
    fork = asst("m9a", txt("Delete the cache?"))
    asst("m9b", txt("Do you accept E7.S9?"), parent=recs2[-2]["uuid"])
    hum("yes", "2026-11-22T07:09:00.000Z", parent=fork)
    # E7.S10: another message of the human between the question and the "yes"
    asst("m10", txt("Do you accept E7.S10?"))
    hum("show it again", "2026-11-22T07:10:00.000Z")
    asst("m10b", {"type": "tool_use", "id": "t10", "name": "Bash", "input": {}})
    add(user([{"type": "tool_result", "tool_use_id": "t10", "content": "ok"}], "2026-11-22T07:10:01.000Z"))
    hum("yes", "2026-11-22T07:10:02.000Z")
    # E7.S7: a question over 200 characters, the code in the middle
    asst("m7", txt("A long report. " * 30 + "Do you accept E7.S7? " + "More details. " * 30))
    hum("yes.", "2026-11-22T07:11:00.000Z")
    # E7.S12: a whole "no" to a question with the code - not acceptance (the list of words of agreement)
    asst("m12", txt("Do you accept E7.S12?"))
    hum("no", "2026-11-22T07:12:00.000Z")
    # E7.S13: a Ukrainian "yes" - a word of agreement only with CCM_LANG_EXTRA=uk
    asst("m13", txt("Do you accept E7.S13?"))
    hum("так", "2026-11-22T07:13:00.000Z")
    with open(os.path.join(projects, "-home-x", f"{SID2}.jsonl"), "w", encoding="utf-8") as f:
        for r in recs2:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    env3 = dict(env, CLAUDE_CODE_SESSION_ID=SID2)
    acc2 = os.path.join(pd2, "ACCEPTED.jsonl")

    def recs_acc2():
        if not os.path.exists(acc2):
            return []
        return [json.loads(x) for x in open(acc2, encoding="utf-8").read().split("\n") if x.strip()]

    rc, out = run("Short", "E7.S2", "yes", env_=env3)
    r2 = recs_acc2()
    check(rc == 0 and "✅" in out and len(r2) == 1, "\"Yes!\" as a whole message + the code in the assistant's question -> ✅",
          f"rc={rc} {out!r}")
    r2 = r2[-1] if r2 else {}
    check(r2.get("short_form") is True and "E7.S2" in r2.get("question", "") and r2.get("quote") == "Yes!"
          and r2.get("ts") == "2026-11-22T07:01:00.000Z" and r2.get("agent") == "Short-HQ",
          "record: short_form, question with the code, quote = the whole message, ts", repr(r2))
    rc, out = run("Short", "E7.S4", "Ok.", env_=env3)
    check(rc == 0 and len(recs_acc2()) == 2, "the code in the first text block of the same API message -> ✅",
          f"rc={rc} {out!r}")
    rc, out = run("Short", "E7.S7", "YES", env_=env3)
    r7 = recs_acc2()[-1] if len(recs_acc2()) == 3 else {}
    check(rc == 0 and "E7.S7" in r7.get("question", "") and len(r7.get("question", "")) <= 202,
          "a long question -> question of at most 200 characters around the code", f"rc={rc} {out!r} {r7!r}")
    n_ok = len(recs_acc2())
    rc, out = run("Short", "E7.S12", "no", env_=env3)
    check(rc == 2 and "not a word of agreement" in out and len(recs_acc2()) == n_ok,
          "a whole \"no\" to \"Do you accept E7.S12?\" -> rc 2, not written", f"rc={rc} {out!r}")
    rc, out = run("Short", "E7.S13", "так", env_=env3)
    check(rc == 2 and "not a word of agreement" in out and len(recs_acc2()) == n_ok,
          "a whole \"так\" without CCM_LANG_EXTRA=uk -> rc 2, not written", f"rc={rc} {out!r}")
    for code, frag, need, what in [
            ("E7.S3", "+", "does not name E7.S3", "the code only in the previous API message, the last one has none"),
            ("E7.S5", "yes", "does not name E7.S5", "a \"yes\" with no code in the message before it"),
            ("E7.S6", "accept", "WHOLE", "\"accept\" only inside a longer message"),
            ("E7.S2", "+", "does not name E7.S2", "a \"+\" to another code (E7.S3)"),
            ("E7.S8", "yes", "does not name E7.S8", "a \"yes\" from a notification / agent / hook / isMeta / peer"),
            ("E7.S9", "yes", "does not name E7.S9", "a \"yes\" in another branch of the conversation (the code is in the sibling)"),
            ("E7.S10", "yes", "does not name E7.S10", "another message of the human between the question and the \"yes\""),
            ("E7.S11", "yes", "does not name E7.S11", "the code only in thinking - the human never saw it")]:
        rc, out = run("Short", code, frag, env_=env3)
        check(rc == 2 and need in out and "ask Alex again" in out, f"{what} -> rc 2 with what to do",
              f"rc={rc} {out!r}")
    check(len(recs_acc2()) == n_ok, "after the short refusals ACCEPTED.jsonl unchanged", f"{n_ok}->{len(recs_acc2())}")
    rc, out = run("Short", "E7.S13", "так", env_=dict(env3, CCM_LANG_EXTRA="uk"))
    r13 = recs_acc2()[-1] if recs_acc2() else {}
    check(rc == 0 and r13.get("story") == "E7.S13" and r13.get("quote") == "так" and r13.get("short_form") is True,
          "a whole \"так\" with CCM_LANG_EXTRA=uk -> ✅", f"rc={rc} {out!r} {r13!r}")
    rc, out = run("Short", "E7.S6", "change the button", env_=env3)
    r6 = recs_acc2()[-1] if recs_acc2() else {}
    check(rc == 0 and r6.get("story") == "E7.S6" and "short_form" not in r6 and "question" not in r6,
          "a long fragment (>= 8) - as before, no short_form", f"rc={rc} {out!r} {r6!r}")
    # 8. the module directly (scope: how many human messages it sees in the transcript)
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
    check(seen >= 0 and hasattr(hq, "code_re") and hq.code_re("S7").search("E7.S7") is None
          and hq.code_re("E7.S7").search("E7.S70") is None and hq.code_re("E7.S7").search("(e7.s7)")
          and hq.code_re("S68").search("story S68?"),
          "code_re: S7 is not found in E7.S7, E7.S7 not in E7.S70; case does not matter")
    # 9. story_status.py shows the accepted record (the reader of ACCEPTED.jsonl)
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
