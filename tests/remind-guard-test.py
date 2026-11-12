#!/usr/bin/env python3
"""remind-guard: a promise to remind without running remind.py in the same turn -> a flag; with a run -> silent.
Runs the repo copy; RG=<path> tests another one. Sandbox: temp HOME, no config file, CCM_LANG_EXTRA set per case."""
import importlib.util as U, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
RG = os.environ.get("RG", os.path.join(HERE, "..", "hooks", "remind-guard.py"))
H = tempfile.mkdtemp(prefix="rg-test-")
os.environ.update({"HOME": H, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_HUMAN_NAME": "Sam"})


def load(lang):
    os.environ["CCM_LANG_EXTRA"] = lang
    s = U.spec_from_file_location("rg" + (lang or "en"), RG); m = U.module_from_spec(s); s.loader.exec_module(m); return m


en, uk = load(""), load("uk")
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def v(text, bash=(), m=en): return m.verdict({"text": text, "bash": list(bash)})


RUN = (1, '/opt/x/scripts/remind.py Helper 2h "blood pressure"', True)
ok("\"I'll remind you\" without a run -> flag", v("Sure, I'll remind you in two hours."))
ok("\"I've set a reminder\" without a run -> flag", v("I've set a reminder for 18:30."))
ok("\"reminder is set\" without a run -> flag", v("The reminder is set for tomorrow 09:00."))
ok("\"Reminder set\" without a run -> flag", v("Reminder set for 07.10 18:30, id 9f703."))
ok("\"I'll come back to this at 18:00\" without a run -> flag", v("I'll come back to this at 18:00."))
ok("with a run of remind.py in the turn -> silent", v("I've set a reminder for 18:30.", [RUN]) is None)
ok("a run that failed -> flag \"failed\"", "failed" in (v("I've set a reminder for 18:30.", [(1, "remind.py Helper sometime x", False)]) or ""))
ok("only --list is not a set-up -> flag", v("I'll remind you at 18:30.", [(1, "remind.py --list", True)]))
ok("cat/grep of the script is not a run -> flag", v("I'll remind you at 18:30.", [(1, "cat /opt/x/scripts/remind.py", True)]))
ok("python3 .../remind.py Agent ... is a run -> silent", v("I'll remind you at 18:30.", [(1, 'cd /x && python3 /opt/x/scripts/remind.py Helper 18:30 "x"', True)]) is None)
ok("\"I'll remind you: ...\" (retelling context) -> silent", v("I'll remind you: the rule applies from Monday.") is None)
ok("\"I'll remind you that ...\" -> silent", v("Let me say again, I'll remind you that the row is missing from the schedule.") is None)
ok("negation \"I can't set a reminder\" -> silent", v("I can't set a reminder here, there is no mechanism.") is None)
ok("negation \"No reminder is set\" -> silent", v("No reminder is set yet.") is None)
ok("\"I didn't set a reminder\" -> silent", v("I didn't actually set a reminder.") is None)
ok("a question \"shall I set a reminder\" -> silent", v("Shall I set a reminder for six?") is None)
ok("an instruction \"to set a reminder, run ...\" -> silent", v("To set a reminder, run the script with the agent name.") is None)
ok("a quote / code isn't counted", v("> I'll remind you tomorrow\n\nThat is a quote from the letter.") is None)
ok("inline code isn't counted", v("The string `reminder is set` is what the test greps for.") is None)
ok("an ordinary reply -> silent", v("Did three items, the test is green.") is None)
ok("Ukrainian phrase without the uk list -> silent", v("Добре, нагадаю через дві години.") is None)
ok("Ukrainian \"нагадаю\" with the uk list -> flag", v("Добре, нагадаю через дві години.", m=uk))
ok("Ukrainian \"нагадаю: …\" with uk -> silent", v("Нагадаю: правило діє з 02.10.", m=uk) is None)
ok("Ukrainian negation with uk -> silent", v("Сам я не нагадаю — механізму нема.", m=uk) is None)
ok("Ukrainian \"повернусь до цього о 18:00\" with uk -> flag", v("Повернусь до цього о 18:00.", m=uk))
ok("English still works with uk on", v("I'll remind you at 18:30.", m=uk))

# through stdin on a real transcript format
tp = f"{H}/t.jsonl"
def w(rows): open(tp, "w").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
def stop(sid, lang=""):
    open(f"{H}/.x", "w").close()
    return subprocess.run([sys.executable, RG], input=json.dumps({"session_id": sid, "transcript_path": tp}), capture_output=True, text=True,
                          env={**os.environ, "HOME": H, "CCM_LANG_EXTRA": lang})
def flag(sid): p = f"{H}/.claude/remind-guard-flags/{sid}"; return open(p).read() if os.path.exists(p) else ""
os.makedirs(f"{H}/.claude/agent-identity"); open(f"{H}/.claude/agent-identity/sidX", "w").write("/ws/Agents/Helper")
w([{"type": "user", "uuid": "u1", "message": {"role": "user", "content": "remind me in an hour"}},
   {"type": "assistant", "uuid": "a1", "message": {"model": "m", "content": [{"type": "text", "text": "Ok, I'll remind you in an hour."}]}}])
r = stop("sidX")
ok("Stop on a transcript: the flag is written, stdout empty", r.returncode == 0 and r.stdout == "" and "remind-guard" in flag("sidX"), r.stderr[-300:])
ok("the flag is a FINISHED hint: tool path, agent name from identity, human name", "remind.py Helper <when>" in flag("sidX") and "Sam" in flag("sidX"), flag("sidX"))
w([{"type": "user", "uuid": "u1", "message": {"role": "user", "content": "remind me in an hour about the call"}},
   {"type": "assistant", "uuid": "a1", "message": {"model": "m", "content": [{"type": "text", "text": "Ok, I'll remind you in an hour. First a look at the file."}]}},
   {"type": "assistant", "uuid": "a2", "message": {"model": "m", "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/etc/hostname"}}]}},
   {"type": "user", "uuid": "u2", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x"}]}},
   {"type": "assistant", "uuid": "a3", "message": {"model": "m", "content": [{"type": "text", "text": "Read it, three items there."}]}}])
stop("sidY"); ok("a promise in an intermediate block (before tool calls) is caught too", "remind-guard" in flag("sidY"))
w([{"type": "user", "uuid": "u1", "message": {"role": "user", "content": "remind me in an hour"}},
   {"type": "assistant", "uuid": "a1", "message": {"model": "m", "content": [{"type": "text", "text": "Setting it."}, {"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "python3 /x/scripts/remind.py Helper 1h \"call\""}}]}},
   {"type": "user", "uuid": "u2", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "b1", "content": "ok"}]}},
   {"type": "assistant", "uuid": "a2", "message": {"model": "m", "content": [{"type": "text", "text": "I've set a reminder for 11:00."}]}}])
stop("sidZ"); ok("the run happened in the turn (tool_use + ok result) -> no flag", flag("sidZ") == "")
w([{"type": "user", "uuid": "u1", "message": {"role": "user", "content": "remind me"}},
   {"type": "assistant", "uuid": "a1", "message": {"model": "m", "content": [{"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "remind.py Helper bogus x"}}]}},
   {"type": "user", "uuid": "u2", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "b1", "is_error": True, "content": "bad time"}]}},
   {"type": "assistant", "uuid": "a2", "message": {"model": "m", "content": [{"type": "text", "text": "I've set a reminder for 11:00."}]}}])
stop("sidW"); ok("the run failed (is_error) -> flag \"failed\"", "failed" in flag("sidW"), flag("sidW"))
w([{"type": "user", "uuid": "u1", "message": {"role": "user", "content": "remind me later"}},
   {"type": "assistant", "uuid": "a1", "message": {"model": "m", "content": [{"type": "text", "text": "Ok, I'll remind you later."}]}},
   {"type": "user", "uuid": "u2", "message": {"role": "user", "content": "thanks, now something else"}},
   {"type": "assistant", "uuid": "a2", "message": {"model": "m", "content": [{"type": "text", "text": "Sure, here is the other thing."}]}}])
stop("sidV"); ok("a promise in an EARLIER turn doesn't count -> no flag", flag("sidV") == "")
r = subprocess.run([sys.executable, RG], input="", capture_output=True, text=True, env={**os.environ, "HOME": H})
ok("empty stdin -> rc 0, silent", r.returncode == 0 and r.stdout == "")
print(f"remind-guard: {P} pass, {F} fail"); raise SystemExit(1 if F else 0)
