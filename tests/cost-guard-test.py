#!/usr/bin/env python3
"""cost-guard: a line only on an expensive/anomalous turn, with a reason, at most once per 20 min.
Runs against the repo copy; CG=<path> tests an installed/other one. Sandbox only: HOME, state, quota file are temp."""
import importlib.machinery as M, importlib.util as U, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
CG = os.environ.get("CG", os.path.join(HERE, "..", "hooks", "cost-guard.py"))
T = tempfile.mkdtemp(prefix="cg-test-")
ENV = {**os.environ, "HOME": T, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "COST_GUARD_STATE": f"{T}/st",
       "QUOTA_STATUS": f"{T}/q.json", "COST_GUARD_AGENTS": f"{T}/none.txt", "CCM_CLAUDE_DIR": f"{T}/claude",
       "CCM_WORKSPACE": f"{T}/ws"}
os.environ.update(ENV)
s = U.spec_from_file_location("cg", CG, loader=M.SourceFileLoader("cg", CG))
cg = U.module_from_spec(s); s.loader.exec_module(cg)
PER = 20_000_000
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:260])


def call(out=500, cr=100_000, cc=2_000, rid=None, cmd=None, model="claude-opus-5-5"):
    c = [{"type": "text", "text": "x"}]
    if cmd: c.append({"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": cmd}})
    return {"type": "assistant", "requestId": rid or os.urandom(4).hex(), "message": {"model": model, "content": c,
            "usage": {"input_tokens": 10, "output_tokens": out, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cc}}}


c = cg.turn_cost([call()])
ok("1 cheap turn → silent", cg.decide(c, [c["total"]] * 10, PER, 1e9, 0) is None)
big = [call(cr=700_000) for _ in range(80)]
c = cg.turn_cost(big); line = cg.decide(c, [75_000] * 10, PER, 1e9, 0)
ok("2 80 calls on a 700k context → line >=1%, reason is calls x context", line and "80 model calls" in line and "702k" in line, line)
ok("2b the line compares with the usual turn", line and "usual" in line, line)
ok("3 throttle: 10 min after a line → silent", cg.decide(c, [75_000] * 10, PER, 1e9, 1e9 - 600) is None)
c = cg.turn_cost([call(cr=0, cc=800_000)])
ok("4 dropped cache: reason named", "cache was dropped" in cg.reason(c), cg.reason(c))
ok("4b dropped cache after a pause (0.25%, not the agent's fault) → silent", cg.decide(c, [75_000] * 10, PER, 1e9, 0) is None)
ok("5 long reply → reason is reply and reasoning", "long reply" in cg.reason(cg.turn_cost([call(out=60_000, cr=50_000)])))
dup = [call(rid="same"), call(rid="same"), call(rid="same")]
ok("6 one request written as three rows counts once", abs(cg.turn_cost(dup)["total"] - cg.turn_cost([call()])["total"]) < 1)
c = cg.turn_cost([call(cr=900_000, cmd="pytest -x tests/") for _ in range(7)])
line = cg.decide(c, [c["total"]] * 10, PER, 1e9, 0)
ok("7 same command 7 times → loop line", line and "7 times" in line, line)
ok("8 no calibration (per_pct None) → silent", cg.decide(cg.turn_cost(big), [75_000] * 10, None, 1e9, 0) is None)
mid = cg.turn_cost([call(cr=700_000) for _ in range(20)])
ok("9 0.35% when usual is 0.3% (not an anomaly) → silent", cg.decide(mid, [mid["total"] * 0.9] * 10, PER, 1e9, 0) is None)
ok("9b same 0.35% when usual is 0.004% → line", cg.decide(mid, [75_000] * 10, PER, 1e9, 0) is not None)
ok("9c little history (<8 turns) and <1% → silent", cg.decide(mid, [75_000] * 3, PER, 1e9, 0) is None)

# end to end as a subprocess: Stop event → flag file for surface-flags
os.makedirs(f"{T}/.claude")
rows = [{"type": "user", "message": {"role": "user", "content": "do it"}}] + big
open(f"{T}/t.jsonl", "w").write("".join(json.dumps(r) + "\n" for r in rows))
ev = json.dumps({"session_id": "sidZ", "transcript_path": f"{T}/t.jsonl"})
flag = f"{T}/.claude/cost-guard-flags/sidZ"


def stop(env=ENV):
    subprocess.run([sys.executable, CG], input=ev, capture_output=True, text=True, env=env)


def reset():
    for x in (flag, f"{T}/st/sidZ.json"):
        if os.path.exists(x): os.remove(x)


stop()
ok("10a no calibration anywhere → no flag", not os.path.exists(flag))
stop({**ENV, "CCM_COST_UNITS_PER_PCT": str(PER)})     # state of the 1st run keeps no 'shown' → fresh decision
ok("10 setting CCM_COST_UNITS_PER_PCT → flag with the finished line", os.path.exists(flag) and "[cost-guard]" in open(flag).read(),
   open(flag).read() if os.path.exists(flag) else "no flag")
reset()
json.dump({"cost_units_per_pct": PER}, open(f"{T}/q.json", "w"))
stop(); ok("10b calibration from the status file → flag", os.path.exists(flag))
reset()
open(f"{T}/none.txt", "w").write("Other-agent\n")
stop(); ok("11 agent not in the opt-in list → silent", not os.path.exists(flag))
print(f"cost-guard: {P} pass, {F} fail"); sys.exit(1 if F else 0)
