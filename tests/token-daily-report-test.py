#!/usr/bin/env python3
"""token_daily_report.py in a sandbox: temp HOME with fake transcripts. No network, no messaging. TR=<path> tests another copy."""
import json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.realpath(__file__))
TR = os.environ.get("TR", os.path.join(HERE, "..", "scripts", "token_daily_report.py"))
T = tempfile.mkdtemp(prefix="tokrep-test-")
H = T + "/home"; os.makedirs(H + "/.claude/projects/p")
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:400])


def line(day, hour, model, i, o, rd, w5, w1=0, typ="assistant"):
    return json.dumps({"type": typ, "timestamp": f"{day}T{hour:02d}:00:00.000Z",
                       "message": {"model": model, "usage": {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": rd,
                                   "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1}}}})


with open(H + "/.claude/projects/p/a.jsonl", "w") as f:
    f.write(line("2026-11-10", 10, "claude-opus-4-8", 1_000_000, 100_000, 2_000_000, 400_000, 100_000) + "\n")
    f.write(line("2026-11-10", 11, "claude-haiku-4-5", 1_000_000, 0, 0, 0) + "\n")
    f.write(line("2026-11-10", 12, "<synthetic>", 5, 5, 5, 5) + "\n")            # not a real call
    f.write(line("2026-11-10", 13, "claude-opus-4-8", 9, 9, 9, 9, typ="user") + "\n")   # not an assistant turn
    f.write("garbage line\n")
    f.write(line("2026-11-09", 10, "claude-opus-4-8", 1, 1, 1, 1) + "\n")        # another day
OUT = H + "/.claude/reports/token-daily"


def run(*a, extra=None):
    env = {**os.environ, "HOME": H, "CCM_TIMEZONE": "UTC", "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "HANZ_TEST": "1", **(extra or {})}
    for k in ("TOKEN_REPORT_DIR", "CLAUDE_PROJECTS_DIR", "SUPERVISOR_SUMMARY"):
        env.pop(k, None) if not extra or k not in extra else None
    return subprocess.run([sys.executable, TR, *a], capture_output=True, text=True, env=env)


r = run("--date", "2026-11-10", "--print")
# opus: 1M*5 + 100k*25 + 2M*0.5 + 400k*6.25 + 100k*10 = 5+2.5+1+2.5+1 = 12.0 ; haiku: 1M*1 = 1.0  -> 13.00
ok("1 cost: opus 12.00 + haiku 1.00 = about $13.00; 2 requests (synthetic/user/garbage/other day ignored)", "about $13.00" in r.stdout and "Requests: 2" in r.stdout, r.stdout + r.stderr)
ok("2 --print writes nothing", not os.path.exists(OUT))
r = run("--date", "2026-11-10")
ok("3 report written: .md .json latest.md", all(os.path.exists(f"{OUT}/{n}") for n in ("2026-11-10.md", "2026-11-10.json", "latest.md")), r.stdout + r.stderr)
d = json.load(open(OUT + "/2026-11-10.json"))
ok("4 JSON: requests, tokens, cost", d["requests"] == 2 and d["tokens"]["in"] == 2_000_000 and abs(d["cost_usd"] - 13.0) < 0.01, d)
m1 = os.path.getmtime(OUT + "/2026-11-10.md"); time.sleep(0.05)
open(OUT + "/2026-11-10.md", "a").write("MARK\n")
run("--date", "2026-11-10")
ok("5 idempotent: a second run does not rewrite the day's report", "MARK" in open(OUT + "/2026-11-10.md").read())
run("--date", "2026-11-10", "--force")
ok("6 --force rewrites it", "MARK" not in open(OUT + "/2026-11-10.md").read())
r = run("--date", "2026-11-05", "--print")
ok("7 a day with no requests -> says so", "No requests" in r.stdout, r.stdout)
r = run("--date", "2026-11-10", "--print", extra={"TOKEN_REPORT_PLAN": "subscription"})
ok("8 subscription plan marks $ as already paid", "already paid" in r.stdout, r.stdout)
r = run("--after", "25")
ok("9 --after 25 (hour not reached) -> silent no-op, rc 0, nothing written for yesterday", r.returncode == 0 and r.stdout == "", r.stdout)
open(H + "/sup.json", "w").write(json.dumps({"problems": ["quota", "mech"], "checks": 9}))
r = run("--date", "2026-11-10", "--print", extra={"SUPERVISOR_SUMMARY": H + "/sup.json"})
ok("10 supervisor line appended when a summary exists", "supervisor: 2 problems - quota, mech" in r.stdout, r.stdout)
ok("11 report text is English", not any("Ѐ" <= ch <= "ӿ" for ch in r.stdout), r.stdout)
print(f"token-daily-report: {P} pass, {F} fail")
sys.exit(1 if F else 0)
