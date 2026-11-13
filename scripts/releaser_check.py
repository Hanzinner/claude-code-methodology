#!/usr/bin/env python3
"""Supervisor check for the release queue (scripts/releaser.py; only present with install.sh --with-releaser): a marker
<state>/queue/<Project>/*.ready older than MAX_MIN (15) = the releaser's cron does not run or is hung. Measures the age of
the OLDEST marker, not of the state file: the state is rewritten only when something is processed, so a fresh marker
after a quiet hour looked like "silent for 25 min" (a false alarm). Empty queue = green. No queue dir (releaser not
installed) = green with a note. Config: CCM_RELEASER_STATE (default /var/lib/ccm-release). Env: MAX_MIN, RELEASER_STATE."""
import glob, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

S = os.environ.get("RELEASER_STATE") or conf("CCM_RELEASER_STATE", "/var/lib/ccm-release")
MAX_MIN = int(os.environ.get("MAX_MIN", "15"))


def main():
    q = os.path.join(S, "queue")
    if not os.path.isdir(q):
        print(f"no release queue at {q} - the releaser is not installed")
        return 0
    now, bad = time.time(), []
    for d in sorted(glob.glob(os.path.join(q, "*", ""))):
        marks = glob.glob(os.path.join(d, "*.ready"))
        if not marks:
            continue
        age = int((now - min(os.path.getmtime(m) for m in marks)) / 60)
        if age > MAX_MIN:
            bad.append(f"{os.path.basename(d.rstrip('/'))}: a marker has waited {age} min, the releaser does not take it")
    if not bad:
        print("releaser: queues are processed in time")
        return 0
    print("\n".join(bad))
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"check crashed: {type(e).__name__}: {e}"); sys.exit(3)
