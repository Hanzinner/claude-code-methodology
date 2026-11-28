#!/usr/bin/env python3
"""Per-finding artifact gate for the quality loop.

A finding cannot be marked done until every required artifact exists on disk.
Store: ~/.claude/quality-loop/<sha1 of git toplevel>/findings/ (never inside the tree or .git).
Steps that were previously prose ("attack your own fix with sibling cases") are
now files: skipping one is visible and blocking instead of silent.

Usage:
  gate.py start   <id> "<one-line description>" [--concurrency]
  gate.py record  <id> <artifact> "<value>"
  gate.py status  <id>
  gate.py done    <id>            # exits 1 and lists gaps if incomplete
  gate.py trailer <id>            # emit the commit-message trailer block
  gate.py list
  gate.py state-path              # print the loop state file path (same key), create its folder

Artifacts:
  repro         test that FAILED before the fix, with its observed output
  class         the CLASS of defect, not the instance
  siblings      every sibling site/input/ordering checked, each with a verdict
  interleavings ordering table (required only when --concurrency)
  fix           what changed
  pin_verified  structured: expected=<v> observed=<v> verdict=PASS (prose is rejected)
  regression    prior pins re-run, with counts
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASE = ["repro", "class", "siblings", "fix", "pin_verified", "regression"]


def loop_dir() -> Path:
    # Outside the tree and .git: a file written there by another OS user than the tree's owner breaks `git worktree remove`.
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    ).stdout.strip()
    if not top:
        sys.exit("not inside a git repository")
    key = hashlib.sha1(top.encode()).hexdigest()
    return Path.home() / ".claude" / "quality-loop" / key


def store() -> Path:
    d = loop_dir() / "findings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def path_for(fid: str) -> Path:
    return store() / f"{fid}.json"


def load(fid: str) -> dict:
    p = path_for(fid)
    if not p.exists():
        sys.exit(f"no such finding '{fid}' - run: gate.py start {fid} \"<description>\"")
    return json.loads(p.read_text())


def required(rec: dict) -> list[str]:
    return BASE + (["interleavings"] if rec.get("concurrency") else [])


def missing(rec: dict) -> list[str]:
    return [a for a in required(rec) if not str(rec["artifacts"].get(a, "")).strip()]


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]

    if cmd == "state-path":
        d = loop_dir()
        d.mkdir(parents=True, exist_ok=True)
        print(d / "state.md")
        return 0

    if cmd == "list":
        for p in sorted(store().glob("*.json")):
            r = json.loads(p.read_text())
            gaps = missing(r)
            state = "DONE" if not gaps else f"missing: {','.join(gaps)}"
            print(f"  {r['id']:<14} {state:<52} {r['description'][:44]}")
        return 0

    if len(sys.argv) < 3:
        sys.exit(__doc__)
    fid = sys.argv[2]

    if cmd == "start":
        if len(sys.argv) < 4:
            sys.exit("start needs a description")
        rec = {
            "id": fid,
            "description": sys.argv[3],
            "concurrency": "--concurrency" in sys.argv,
            "artifacts": {},
        }
        path_for(fid).write_text(json.dumps(rec, indent=2))
        req = ", ".join(required(rec))
        print(f"started {fid}\nrequired artifacts: {req}")
        if rec["concurrency"]:
            print(
                "CONCURRENCY: enumerate the interleavings BEFORE fixing. If you cannot\n"
                "list them, you do not understand the bug yet - do not write a fix."
            )
        return 0

    rec = load(fid)

    if cmd == "record":
        if len(sys.argv) < 5:
            sys.exit("record needs <artifact> \"<value>\"")
        art, val = sys.argv[3], sys.argv[4]
        if art not in required(rec):
            sys.exit(f"unknown artifact '{art}'; expected one of {required(rec)}")
        if art == "pin_verified":
            low = val.lower()
            missing_keys = [k for k in ("expected", "observed", "verdict") if k not in low]
            if missing_keys:
                sys.exit(
                    "REJECTED: pin_verified must be structured, not prose.\n"
                    f"  missing: {', '.join(missing_keys)}\n"
                    "  required shape: expected=<value> observed=<value> verdict=PASS|FAIL\n"
                    "  A measurement you narrate instead of comparing is how a printed\n"
                    "  '2' gets written up as expected behaviour. State the expected value\n"
                    "  BEFORE you look at the observed one."
                )
            if "verdict=fail" in low.replace(" ", ""):
                sys.exit("REJECTED: verdict=FAIL - the fix does not work. Do not record it as verified.")
        rec["artifacts"][art] = val
        path_for(fid).write_text(json.dumps(rec, indent=2))
        gaps = missing(rec)
        print(f"recorded {art}. still missing: {', '.join(gaps) if gaps else 'nothing'}")
        return 0

    if cmd == "status":
        print(json.dumps(rec, indent=2))
        return 0

    if cmd == "done":
        gaps = missing(rec)
        if gaps:
            print(f"NOT DONE - {fid} is missing {len(gaps)} artifact(s):", file=sys.stderr)
            for a in gaps:
                print(f"  - {a}", file=sys.stderr)
            print(
                "\nThis finding is not fixed. Produce the artifact, do not narrate it.\n"
                "'siblings' empty means you fixed the instance, not the class.",
                file=sys.stderr,
            )
            return 1
        print(f"{fid} complete - all artifacts present")
        return 0

    if cmd == "trailer":
        if missing(rec):
            sys.exit(f"refusing: {fid} incomplete ({', '.join(missing(rec))})")
        a = rec["artifacts"]
        print(f"Class: {a['class']}")
        print(f"Siblings-checked: {a['siblings']}")
        if rec.get("concurrency"):
            print(f"Interleavings: {a['interleavings']}")
        print(f"Verified-by: {a['pin_verified']}")
        print(f"Regression: {a['regression']}")
        return 0

    sys.exit(f"unknown command '{cmd}'")


if __name__ == "__main__":
    sys.exit(main())
