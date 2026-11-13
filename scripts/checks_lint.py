#!/usr/bin/env python3
"""Gate on a class of bad checks: "the watchman looks at a SIGN, not at the RESULT" (found three times: a restic
error log that was fresh for 21 h, a mech snapshot, session hygiene). Rule: a `fresh` check on a *.log file is forbidden
unless it carries a `fresh_ok` field with a reason - a log is written on failures too, so its freshness proves nothing.
rc 1 + the list of offenders; rc 3 if the registry is unreadable or suspiciously small (the linter itself is probably
reading the wrong file). The supervisor runs it on its own registry (it watches itself).
Usage: checks_lint.py [--checks FILE]   (default: <CCM_SUPERVISOR_CHECKS or <state>/checks.json>)   Env: CHECKS_LINT_MIN (1)."""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

default = conf("CCM_SUPERVISOR_CHECKS", "") or os.path.join(conf("CCM_SUPERVISOR_DIR", "") or os.path.join(os.path.expanduser("~"), ".claude", "supervisor"), "checks.json")
p = sys.argv[sys.argv.index("--checks") + 1] if "--checks" in sys.argv else default
try:
    cs = json.load(open(p))["checks"]
except (OSError, ValueError, KeyError) as e:
    print(f"cannot read the registry {p}: {e}"); sys.exit(3)
bad = [c.get("name", "?") for c in cs if c.get("kind") == "fresh" and str(c.get("path", "")).endswith(".log") and not c.get("fresh_ok")]
print(f"checked {len(cs)} checks; fresh-on-a-log without a reason: {len(bad)}" + (": " + "; ".join(bad) if bad else ""))
if len(cs) < int(os.environ.get("CHECKS_LINT_MIN", "1")):
    print("suspiciously few checks - the linter is probably reading the wrong file"); sys.exit(3)
sys.exit(1 if bad else 0)
