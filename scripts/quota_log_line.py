#!/usr/bin/env python3
"""quota_log_line.py - append ONE line per run to a history log: "<date time> <weekly %> <session %> <weekly resets_at>".

Why: to see how much of the week a swarm really eats (and so which plan to pay for) you need a curve, not a
snapshot. Reads the real-quota state quota_status.py keeps (~/.claude/quota-real.json); no file / no data -> writes
nothing, rc 0 (a quota log is not worth a failing cron job).

Cron (hourly):  7 * * * * python3 ~/.claude/scripts/quota_log_line.py
Settings: QUOTA_REAL_STATE (default ~/.claude/quota-real.json), QUOTA_HISTORY (default ~/.claude/quota-weekly-history.log).
"""
import json, os, sys, time

CD = os.path.expanduser("~/.claude")
STATE = os.environ.get("QUOTA_REAL_STATE", os.path.join(CD, "quota-real.json"))
LOG = os.environ.get("QUOTA_HISTORY", os.path.join(CD, "quota-weekly-history.log"))


def main():
    try:
        d = json.load(open(STATE))["data"]
        line = "%s %s %s %s" % (time.strftime("%Y-%m-%d %H:%M"), d["weekly"]["pct"], d["session"]["pct"], d["weekly"]["resets_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
