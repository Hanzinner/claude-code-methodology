#!/usr/bin/env python3
"""Supervisor check: hooks do not die by timeout (a sign of an overloaded machine or a slow hook). More than MAX
[TIMEOUT lines in ~/.claude/hook-errors.log (written by hooks/hook-safe.sh) in the last hour -> red. Why: a runaway cron
loop pushed the load to 25 and 5 hooks timed out within minutes - only the agents noticed.
Env: HOOK_ERRORS_LOG (default ~/.claude/hook-errors.log), MAX (3), WINDOW_MIN (60)."""
import datetime, os, re, sys, time

L = os.environ.get("HOOK_ERRORS_LOG", os.path.join(os.path.expanduser("~"), ".claude", "hook-errors.log"))
MAX = int(os.environ.get("MAX", "3"))
WINDOW = int(os.environ.get("WINDOW_MIN", "60")) * 60
LINE = re.compile(r"^(\d{4}-\d\d-\d\dT[\d:]{8}(?:[+-]\d\d:\d\d|Z)?)[^\[]*\[TIMEOUT")


def main():
    if not os.path.isfile(L):
        print(f"no {L} - hooks have never failed")
        return 0
    since, n = time.time() - WINDOW, 0
    for ln in open(L, encoding="utf-8", errors="replace"):
        m = LINE.match(ln)
        if not m:
            continue
        try:
            ts = datetime.datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
            t = ts.timestamp()          # a naive stamp is read as local time
        except ValueError:
            continue
        if t >= since:
            n += 1
    try:
        load = " ".join(f"{x:.2f}" for x in os.getloadavg())
    except (OSError, AttributeError):
        load = "n/a"
    print(f"hook TIMEOUTs in the last hour: {n} (limit {MAX}); load {load}")
    return 0 if n <= MAX else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"check crashed: {type(e).__name__}: {e}"); sys.exit(3)
