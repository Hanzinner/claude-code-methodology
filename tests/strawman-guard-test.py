#!/usr/bin/env python3
"""strawman-guard: strawman (attribution+negation, no quote), fake fork, state of the human, risk in the 2nd person.
Repo copy by default; SG=<path> tests another. Sandbox: temp HOME, no config, CCM_LANG_EXTRA set per case."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SG = os.environ.get("SG", os.path.join(HERE, "..", "hooks", "strawman-guard.py"))
T = tempfile.mkdtemp(prefix="sg-test-")
P = F = 0
n = 0


def run(user, asst, lang=""):
    global n
    n += 1
    home = f"{T}/h{n}"; os.makedirs(home)
    tp = f"{home}/t.jsonl"
    with open(tp, "w") as f:
        f.write(json.dumps({"type": "user", "message": {"content": user}}) + "\n")
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": asst}]}}) + "\n")
    env = {**os.environ, "HOME": home, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_LANG_EXTRA": lang, "CCM_HUMAN_NAME": "Sam"}
    r = subprocess.run([sys.executable, SG], input=json.dumps({"session_id": "sidA", "transcript_path": tp}),
                       capture_output=True, text=True, env=env)
    fl = f"{home}/.claude/strawman-guard-flags/sidA"
    return (open(fl).read() if os.path.exists(fl) else ""), r.returncode


def t(name, user, asst, want, lang=""):
    """want = substring expected in the flag, or None for silence"""
    global P, F
    fl, rc = run(user, asst, lang)
    good = rc == 0 and ((want is None and fl == "") or (want is not None and want in fl and fl.startswith("⚠️ [strawman-guard]")))
    if good: P += 1
    else: F += 1; print(f"FAIL: {name}: rc={rc} flag={fl!r} (want {want!r})")


U_ = "watched two German films, liked both"
t("state: 'you just didn't know' flat", U_, "One director made both, you just didn't know.", "state of the human")
t("state: a question is fine", U_, "One director made both, did you not know?", None)
t("state: hedged", U_, "Probably you didn't know that one director made both.", None)
t("state: the human said it themselves", "i didn't know the director was the same", "Right, you didn't know; same director.", None)
t("state: 'you find it hard' flat", "explain the tax programs", "FSW is fine, but you find it hard to read the CRS table.", "state of the human")
t("advice 'you don't need to' is not a state", "what to set in the bot", "You don't need to wait for every message.", None)
t("state inside a quote line is ignored", U_, "> you just didn't know\n\nI partly agree with the quote.", None)
t("risk: 'your weak spot', nobody asked", "here is a vacancy, look at the stack", "Mosyle in the stack is your weak spot in the interview.", "risk in the 2nd person")
t("risk: the human asked about risks", "what risks are there for me?", "The main risk for you is the probation period.", None)
t("risk: negated", "how to clean the disk", "This is your level, GUI only, no risk.", None)
t("risk: technical, no 2nd person", "write a hook", "There is a race-condition risk between the two processes.", None)
t("strawman: attribution + negation, no quote", "make the error code understandable", "Your goal is wrong: actually the real goal is something else.", "attribution")
t("strawman: a verbatim quote makes it honest", "make the error code something you can google when it happens",
  "You said: make the error code something you can google when it happens. Actually the real goal is the same, with a link.", None)
t("strawman: a check-question softens it", "ship it friday", "Do I understand correctly — your goal is to ship Friday? Actually that is unrealistic.", None)
t("fake fork", "what next", "This is already decided by the rule. Your call: option A or option B?", "fake fork")
t("neutral answer", "status?", "Three items done, the suite is green.", None)
# Ukrainian lists, switched on explicitly
t("uk: 'ти просто не знав' with uk on", "подивився два німецькі фільми", "Їх зняв один режисер, ти просто не знав.", "state of the human", lang="uk")
t("uk: same text with uk off → silent", "подивився два німецькі фільми", "Їх зняв один режисер, ти просто не знав.", None, lang="")
t("uk: опудало", "зроби щоб код помилки був зрозумілий", "Твоя ціль хибна: насправді треба інше.", "attribution", lang="uk")
t("uk: фейкова розвилка", "що далі", "Це вже вирішено правилом. Твоє рішення: А чи Б?", "fake fork", lang="uk")
print(f"strawman-guard: {P} pass, {F} fail"); sys.exit(1 if F else 0)
