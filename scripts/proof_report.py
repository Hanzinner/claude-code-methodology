#!/usr/bin/env python3
"""proof_report — a check run that leaves a record hooks/proof-guard.py can count (the verify skill).

Why: proof-guard used to count a subagent call (Task/Agent) whose task mentioned a test as a run, without knowing
whether the test ran or passed. Now a subagent counts only when the session's report holds runs started after the last
code edit, all with rc 0. The report is not the agent's words: this script runs the command and writes its exit code.

  proof_report.py run [--sid SID] -- <command…>   run it (bash -c), output as is, rc = the command's; a line in the report
  proof_report.py show [--sid SID]                 the session's report lines
SID: --sid, else $CLAUDE_CODE_SESSION_ID (the verify skill puts the parent session's id into the subagent's task).
Report: <dir>/<sid>.jsonl, one {"cmd","rc","start","end","cwd"} per run; times in UTC ISO, as in the transcript.
<dir>: PROOF_REPORTS_DIR, else config CCM_PROOF_REPORTS_DIR, else ~/.claude/proof-reports (proof-guard reads the same)."""
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402

DIR = (os.environ.get("PROOF_REPORTS_DIR") or conf("CCM_PROOF_REPORTS_DIR", "")
       or os.path.join(os.path.expanduser("~"), ".claude", "proof-reports"))


def now():
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t * 1000) % 1000:03d}Z"


def path(sid):
    return os.path.join(DIR, f"{os.path.basename(sid)}.jsonl")


def entries(sid, since=""):
    """the session's report lines started at or after `since` (ISO strings compare as text)"""
    try:
        rows = [json.loads(l) for l in open(path(sid), encoding="utf-8") if l.strip()]
    except (OSError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict) and str(r.get("start", "")) >= since]


def main(argv):
    if not argv or argv[0] not in ("run", "show"):
        print(__doc__); return 2
    cmd, sid, rest = argv[0], os.environ.get("CLAUDE_CODE_SESSION_ID", ""), argv[1:]
    if rest[:1] == ["--sid"] and len(rest) > 1:
        sid, rest = rest[1], rest[2:]
    if not sid:
        print("proof_report: no session id - pass --sid <the parent session's id> (or set CLAUDE_CODE_SESSION_ID)",
              file=sys.stderr)
        return 2
    if cmd == "show":
        for r in entries(sid):
            print(f"{r.get('start')} rc={r.get('rc')} {r.get('cmd')}")
        return 0
    if rest[:1] == ["--"]:
        rest = rest[1:]
    if not rest:
        print("proof_report: no command after --", file=sys.stderr); return 2
    line = " ".join(rest) if len(rest) > 1 else rest[0]
    start = now()
    rc = subprocess.call(["bash", "-c", line])
    os.makedirs(DIR, exist_ok=True)
    with open(path(sid), "a", encoding="utf-8") as f:
        f.write(json.dumps({"cmd": line[:500], "rc": rc, "start": start, "end": now(), "cwd": os.getcwd()},
                           ensure_ascii=False) + "\n")
    print(f"[proof_report] rc={rc} -> {path(sid)}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
