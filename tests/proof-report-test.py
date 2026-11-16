#!/usr/bin/env python3
"""scripts/proof_report.py and scripts/verify_prompt.py (the verify skill). proof_report: the command's rc is returned
and written, output passes through, no session id -> refused, the report lands where hooks/proof-guard.py reads it
(same dir from methodology.conf). verify_prompt: the project gate from the nearest release.toml, the line it prints
runs and writes the report. Sandbox: temp HOME, temp config, temp projects. PR=/VP= test other copies.
Last line: proof-report-test: N pass, M fail."""
import importlib.machinery, importlib.util, json, os, re, shlex, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
PR = os.environ.get("PR") or os.path.join(ROOT, "scripts", "proof_report.py")
VP = os.environ.get("VP") or os.path.join(ROOT, "scripts", "verify_prompt.py")
T = tempfile.mkdtemp(prefix="proof-report-test-")
RD = f"{T}/reports"
CONF = f"{T}/methodology.conf"
open(CONF, "w").write(f"CCM_PROOF_REPORTS_DIR={RD}\n")
ENV = {**os.environ, "HOME": f"{T}/home", "CLAUDE_METHODOLOGY_CONF": CONF, "CCM_TEST": "1"}
for k in ("PROOF_REPORTS_DIR", "CLAUDE_CODE_SESSION_ID"):
    ENV.pop(k, None)
os.makedirs(ENV["HOME"])
P = F = 0


def ok(name, cond, detail=""):
    global P, F
    if cond: P += 1
    else: F += 1; print("FAIL:", name, str(detail)[:400])


def run(script, *a, env=None):
    r = subprocess.run([sys.executable, script, *a], capture_output=True, text=True, timeout=60, env={**ENV, **(env or {})})
    return r.returncode, r.stdout, r.stderr


def rows(sid):
    try:
        return [json.loads(l) for l in open(f"{RD}/{sid}.jsonl") if l.strip()]
    except OSError:
        return []


rc, out, err = run(PR, "run", "--sid", "s1", "--", "echo hello; exit 3")
r = rows("s1")
ok("1 the command's rc is returned and written", rc == 3 and len(r) == 1 and r[0]["rc"] == 3, (rc, r, err))
ok("2 the output passes through", "hello" in out, out)
ok("3 start/end in the transcript's timestamp format (UTC, ms, Z)",
   r and all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", r[0][k]) for k in ("start", "end")), r)
rc, out, err = run(PR, "run", "--sid", "s1", "--", "true")
ok("4 a second run is appended", rc == 0 and [x["rc"] for x in rows("s1")] == [3, 0], rows("s1"))
rc, out, err = run(PR, "run", "--", "true")
ok("5 no session id -> refused (rc 2), nothing written", rc == 2 and "session id" in err and not os.path.exists(f"{RD}/.jsonl"), err)
rc, out, err = run(PR, "run", "--", "true", env={"CLAUDE_CODE_SESSION_ID": "s2"})
ok("6 CLAUDE_CODE_SESSION_ID is used when --sid is not given", rc == 0 and len(rows("s2")) == 1)
rc, out, err = run(PR, "show", "--sid", "s1")
ok("7 show lists the session's runs", rc == 0 and "rc=3" in out and "rc=0" in out, out)
rc, out, err = run(PR, "run", "--sid", "../../evil", "--", "true")
ok("8 a session id with a path in it stays inside the reports dir", rc == 0 and len(rows("evil")) == 1 and not os.path.exists(f"{T}/evil.jsonl"))

# proof-guard reads the same dir from the same config
pgpath = os.path.join(ROOT, "hooks", "proof-guard.py")
probe = ("import importlib.machinery as m, importlib.util as u, sys; l=m.SourceFileLoader('pg', sys.argv[1]); "
         "p=u.module_from_spec(u.spec_from_file_location('pg', sys.argv[1], loader=l)); l.exec_module(p); "
         "print(p.REPORTS); print(len(p.report_rows('s1', '')))")
r = subprocess.run([sys.executable, "-c", probe, pgpath], capture_output=True, text=True, timeout=30, env=ENV)
ok("9 proof-guard reads the reports from the same dir (CCM_PROOF_REPORTS_DIR) and sees both runs",
   r.stdout.split() == [RD, "2"], (r.stdout, r.stderr[-300:]))

# verify_prompt: a project with a gate, one without a test command, a file outside any project
PJ = f"{T}/work/Project-A"
os.makedirs(f"{PJ}/src/deep")
open(f"{PJ}/release.toml", "w").write('test = "echo gate-ran > gate.out"\n')
open(f"{PJ}/src/deep/x.py", "w").write("print(1)\n")
PB = f"{T}/work/Project-B"
os.makedirs(PB)
open(f"{PB}/release.toml", "w").write('name = "b"\n')
open(f"{PB}/y.sh", "w").write("true\n")
open(f"{T}/loose.py", "w").write("print(2)\n")

rc, out, err = run(VP, "--sid", "v1", "--note", "x prints 1", f"{PJ}/src/deep/x.py")
ok("10 the gate of the nearest release.toml, run from the project root",
   rc == 0 and f"cd {PJ} && echo gate-ran > gate.out" in out and "x prints 1" in out and f"{PJ}/src/deep/x.py" in out, out)
ok("11 every command goes through proof_report.py (its path shell-quoted) with this session's id",
   f"{shlex.quote(os.path.realpath(PR))} run --sid v1 --" in out, out)
ok("12 the last line the subagent must give is spelled out", "SUMMARY: all rc 0 | RED:" in out, out)
gl = next((l.strip() for l in out.splitlines() if " run --sid v1 --" in l and "gate-ran" in l), "")
g = subprocess.run(["bash", "-c", gl], capture_output=True, text=True, timeout=60, env={**ENV, "PROOF_REPORTS_DIR": RD})
ok("13 the printed gate line runs as is: the gate ran in the project root, a report line with rc 0",
   g.returncode == 0 and os.path.isfile(f"{PJ}/gate.out") and [x["rc"] for x in rows("v1")] == [0], (gl, g.stderr[-300:], rows("v1")))
rc, out, err = run(VP, "--sid", "v2", f"{PB}/y.sh")
ok("14 release.toml without a test command -> said plainly", rc == 0 and "Project-B: release.toml has no test command" in out, out)
rc, out, err = run(VP, "--sid", "v3", f"{T}/loose.py")
ok("15 a file outside any project -> no gate line, the file is listed", rc == 0 and "gate of project" not in out and f"{T}/loose.py" in out, out)
rc, out, err = run(VP, f"{PJ}/src/deep/x.py")
ok("16 no session id -> refused (rc 2)", rc == 2 and "session id" in err, err)
rc, out, err = run(VP, "--sid", "it's", f"{PJ}/src/deep/x.py")
ok("17 a session id with a quote is shell-quoted", rc == 0 and shlex.split(next((l for l in out.splitlines() if "gate-ran" in l), ""))[2:4] == ["--sid", "it's"], out)

subprocess.run(["chmod", "-R", "u+w", T])
import shutil; shutil.rmtree(T, ignore_errors=True)
print(f"proof-report-test: {P} pass, {F} fail")
sys.exit(1 if F else 0)
