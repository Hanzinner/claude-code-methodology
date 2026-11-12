#!/usr/bin/env python3
"""order-capture-hint: an imperative work order from the human in a coordinator session → reminder; questions,
non-coordinator sessions, plain chat → silent. OH=<path> tests another copy. Sandbox: temp HOME, no config."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
OH = os.environ.get("OH", os.path.join(HERE, "..", "hooks", "order-capture-hint.sh"))
T = tempfile.mkdtemp(prefix="oh-test-")
P = F = 0
n = 0


def run(prompt, ident="Project-HQ", lang="", pattern=None, sid="sidA"):
    global n
    n += 1
    home = f"{T}/h{n}"; os.makedirs(f"{home}/.claude/agent-identity")
    if ident is not None:
        open(f"{home}/.claude/agent-identity/{sid}", "w").write(f"/x/Agents/{ident}")
    env = {**os.environ, "HOME": home, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_LANG_EXTRA": lang}
    env.pop("CCM_COORDINATOR_PATTERN", None)
    if pattern is not None:
        env["CCM_COORDINATOR_PATTERN"] = pattern
    r = subprocess.run(["bash", OH], input=json.dumps({"session_id": sid, "prompt": prompt}), capture_output=True, text=True, env=env)
    log = f"{home}/.claude/order-hits.log"
    return r.stdout, os.path.exists(log), r.returncode


def t(name, want, *a, **k):
    global P, F
    o, logged, rc = run(*a, **k)
    good = rc == 0 and ((want and "FIRST action" in o and logged) or (not want and o == "" and not logged))
    if good: P += 1
    else: F += 1; print(f"FAIL: {name}: {o!r} logged={logged} rc={rc}")


t("imperative order in a coordinator session", True, "Set up CI for the uploader repo.")
t("'please' + verb", True, "Please add a retry to the uploader")
t("'I want you to' + verb", True, "I want you to build the nightly report job")
t("question → silent", False, "Can you add a retry to the uploader?")
t("verb not opening the sentence → silent", False, "The make target is broken but I am just chatting")
t("'make sure' is not an order → silent", False, "Make sure you read the brief first")
t("plain chat → silent", False, "thanks, that makes sense")
t("worker session (identity not a coordinator) → silent", False, "Set up CI for the uploader repo.", ident="Worker-agent")
t("no identity file → silent", False, "Set up CI for the uploader repo.", ident=None)
t("pattern '*' → every session", True, "Set up CI for the uploader repo.", ident=None, pattern="*")
t("custom pattern matches identity", True, "Fix the flaky test in the suite", ident="Lead-Alpha", pattern="Lead")
t("uk verb with uk off → silent", False, "Зроби CI для репозиторію")
t("uk verb with uk on → reminder", True, "Зроби CI для репозиторію", lang="uk")
print(f"order-capture-hint: {P} pass, {F} fail"); sys.exit(1 if F else 0)
