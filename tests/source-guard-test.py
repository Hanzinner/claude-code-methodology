#!/usr/bin/env python3
"""source-guard: money/legal facts without a source → flag; with URL / hedge / quote / technical text → silent.
SG=<path> tests another copy. Sandbox: temp HOME, no config, CCM_LANG_EXTRA set per case."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SG = os.environ.get("SG", os.path.join(HERE, "..", "hooks", "source-guard.py"))
T = tempfile.mkdtemp(prefix="srcg-test-")
P = F = 0
n = 0


def run(text, lang="", active=False):
    global n
    n += 1
    home = f"{T}/h{n}"; os.makedirs(home)
    tp = f"{home}/t.jsonl"
    with open(tp, "w") as f:
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}) + "\n")
    env = {**os.environ, "HOME": home, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_LANG_EXTRA": lang}
    r = subprocess.run([sys.executable, SG], input=json.dumps({"session_id": "sidA", "transcript_path": tp, "stop_hook_active": active}),
                       capture_output=True, text=True, env=env)
    fl = f"{home}/.claude/source-guard-flags/sidA"
    return (open(fl).read() if os.path.exists(fl) else ""), r.returncode


def t(name, text, want, lang="", active=False):
    global P, F
    fl, rc = run(text, lang, active)
    good = rc == 0 and ((want is None and fl == "") or (want is not None and want in fl and fl.startswith("⚠️ [source-guard]")))
    if good: P += 1
    else: F += 1; print(f"FAIL: {name}: rc={rc} flag={fl!r}")


t("tax rate stated flat → flag", "The corporate tax rate is 15% for small companies.", "15%")
t("price in dollars", "Rent for a two-bed flat costs $600 a month.", "$600")
t("salary in euros", "The average salary there is 3,200 EUR.", "3,200 EUR")
t("fine / penalty", "The penalty for late filing is 200 USD.", "200 USD")
t("categorical legal claim", "No country allows dual residency for this visa.", "No country")
t("'by law' claim", "By law you must register within ten days.", "By law")
t("with a URL → silent", "The tax rate is 15% (https://example.gov/tax).", None)
t("hedged → silent", "The tax rate is probably around 15%, I haven't checked.", None)
t("'according to' → silent", "According to the ministry page the rent cap is 5%.", None)
t("technical percent without legal/price context → silent", "The cache hit ratio is 95% and the error rate dropped to 2%.", None)
t("technical 'required' → silent", "A restart is required after the config change.", None)
t("money in a quote → silent", "He wrote `tax 15%` in the test fixture; the parser handles it.", None)
t("fact paragraph sourced, another plain → silent", "Plain text paragraph.\n\nPrice is $5 (source: vendor pricing page).", None)
t("stop_hook_active → silent", "The tax rate is 15%.", None, active=True)
t("uk: ставка без джерела with uk on", "Податкова ставка становить 15% для малих фірм.", "15%", lang="uk")
t("uk: same with uk off → silent", "Податкова ставка становить 15% для малих фірм.", None, lang="")
print(f"source-guard: {P} pass, {F} fail"); sys.exit(1 if F else 0)
