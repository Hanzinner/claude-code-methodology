#!/usr/bin/env python3
"""Supervisor check: reminders (scripts/remind.py) are not stuck. A pending reminder is a file <epoch>-<id>.json in the
reminders dir; one overdue by more than 10 minutes means the per-minute cron `remind.py --fire` does not deliver.
Dir: env REMIND_DIR, else config CCM_REMINDERS_DIR, else ~/.claude/reminders. No dir yet = nothing was ever set = green.
rc 0 green · 1 overdue found. Env STUCK_MIN (10), REMIND_NOW (epoch, tests)."""
import os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

D = os.environ.get("REMIND_DIR") or conf("CCM_REMINDERS_DIR", "") or os.path.join(os.path.expanduser("~"), ".claude", "reminders")
STUCK = int(os.environ.get("STUCK_MIN", "10")) * 60


def main():
    if not os.path.isdir(D):
        print(f"no reminders dir {D} - nothing was ever set")
        return 0
    now = int(os.environ.get("REMIND_NOW") or time.time())
    late = []
    for f in sorted(os.listdir(D)):
        head = f.split("-", 1)[0]
        if not f.endswith(".json") or not head.isdigit():
            continue
        if now - int(head) > STUCK:
            late.append(f"overdue: {f} by {(now - int(head)) // 60} min")
    if not late:
        print("no overdue reminders")
        return 0
    print("\n".join(late))
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"check crashed: {type(e).__name__}: {e}"); sys.exit(3)
