#!/usr/bin/env python3
"""draft-guard: signs a+b+c+d(numbers only), skip-list, once per draft. DG=<path> tests another copy.
Sandbox only: HOME and CCM_* are temp."""
import importlib.machinery as M, importlib.util as U, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
DG = os.environ.get("DG", os.path.join(HERE, "..", "hooks", "draft-guard.py"))
H = tempfile.mkdtemp(prefix="dg-test-"); os.makedirs(f"{H}/.claude/agent-identity")
ENV = {**os.environ, "HOME": H, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_HUMAN_NAME": "Alex", "CCM_DRAFT_GUARD_SKIP": "Image-agent"}
os.environ.update(ENV)
s = U.spec_from_file_location("dg", DG, loader=M.SourceFileLoader("dg", DG)); dg = U.module_from_spec(s); s.loader.exec_module(dg)
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def sg(text):
    r = dg.drafts(text)
    return dg.signs(*r[0]) if r else None


def has(text, word): return any(word in x for x in (sg(text) or []))


ok("short staccato sentences → (a)", has("> Checked the alert. It was the CEO. App is internal. Closing now as benign.", "short sentences"))
ok("two stamps → (b)", has("> Please see the attached report for the details of the incident. Let me know if you need anything else from our side.", "stamps"))
ok("a question → (c)", has("> We reviewed the sign-in logs for the account. Can you confirm the user was travelling last week?", "question"))
ok("a number twice → (d)", has("> The rule fired 61 times last week across tenants. All 61 were the same service account doing token refresh.", "number"))
ok("a name twice is NOT a sign", sg("> Acme tenant has a new analytics rule enabled this morning. The Acme rule creates incidents for spray followed by success.") == [])
ok("a Cyrillic quote is not a draft", dg.drafts("> це не чернетка, а цитата українською з листа, яка має кілька речень. Ось друге речення.") == [])
ok("a KQL code block is not a draft", dg.drafts("```kql\nSigninLogs | where ResultType == 0 | summarize count() by UserPrincipalName\n```") == [])
ok("a normal draft without signs → no flag", sg("> hey - the alert in the Acme tenant was the CEO granting consent to an internal app he is building, so i closed it as benign positive and added a note on the ticket. nothing else needed from your side for this one.") == [])


def stop(sid, agent, text, env=ENV):
    open(f"{H}/.claude/agent-identity/{sid}", "w").write(f"/x/Agents/{agent}")
    tp = f"{H}/{sid}.jsonl"
    open(tp, "w").write(json.dumps({"type": "user", "uuid": "u", "message": {"role": "user", "content": "draft it"}}) + "\n" +
                        json.dumps({"type": "assistant", "uuid": "a", "message": {"model": "m", "content": [{"type": "text", "text": text}]}}) + "\n")
    subprocess.run([sys.executable, DG], input=json.dumps({"session_id": sid, "transcript_path": tp}), capture_output=True, text=True, env=env)
    p = f"{H}/.claude/draft-guard-flags/{sid}"
    r = open(p).read() if os.path.exists(p) else None
    if r: os.remove(p)
    return r


D = "Here is the draft:\n\n> Checked the alert. It was the CEO. App is internal. Closing now.\n"
r = stop("s1", "Ops-agent", D)
ok("Stop: flag with the finished hint, human's name, generic (no guide)", r and r.startswith("✍️ [draft-guard]") and "Alex" in r and "Checked the alert" in r and "gate at the top" not in r, r)
ok("Stop: the same draft again → no flag (once per draft)", stop("s1", "Ops-agent", D) is None)
ok("Stop: an agent in CCM_DRAFT_GUARD_SKIP → no flag", stop("s2", "Image-agent", D) is None)
r = stop("s3", "Ops-agent", D, env={**ENV, "CCM_DRAFTING_GUIDE": "/g/style.md"})
ok("Stop: with CCM_DRAFTING_GUIDE the hint names the file", r and "/g/style.md" in r, r)
ok("Stop: a reply with no draft → no flag", stop("s4", "Ops-agent", "Done. All good.") is None)
print(f"draft-guard: {P} pass, {F} fail"); sys.exit(1 if F else 0)
