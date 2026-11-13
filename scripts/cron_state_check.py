#!/usr/bin/env python3
"""Supervisor check for jobs run under bin/catchup-run: cron_state_check.py <name> <max_hours>
Red if <name>.fail exists (the last run failed) or the last success (<name>.ok) is older than max_hours; no .ok and
no .fail = the job has not run yet -> rc 3 (could not measure; the registry entry can gate it with only_if_exists).
The age counts WORKING hours: the time the machine was off (gaps between boots in the system journal) is subtracted.
Once a VM was off for 34 h and 12 alarms "last success 44-62 h ago" went off for jobs that were just waiting for
their hour; the engine's own silence-after-downtime does not cover a downtime longer than the limits.
No journal (not systemd, no access, not JSON) -> 0 h of downtime: better a needless alarm than blindness.
Config: CCM_CRON_STATE (default ~/.claude/cron-state), CCM_CRON_LOGDIR. Env for tests: CRON_STATE_NOW (epoch),
CRON_STATE_BOOTS (a file with `journalctl --list-boots --output=json`)."""
import json, os, subprocess, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

HOME = os.path.expanduser("~")
D = conf("CCM_CRON_STATE", "") or os.path.join(HOME, ".claude", "cron-state")
LOGDIR = conf("CCM_CRON_LOGDIR", "") or os.path.join(HOME, ".claude", "cron-logs")


def downtime(ok_s, now):
    try:
        if os.environ.get("CRON_STATE_BOOTS"):
            raw = open(os.environ["CRON_STATE_BOOTS"]).read()
        else:
            raw = subprocess.run(["journalctl", "--list-boots", "--output=json"], capture_output=True, text=True, timeout=10).stdout
        b = sorted(json.loads(raw), key=lambda x: x["first_entry"])
        down = 0.0
        for prev, cur in zip(b, b[1:]):
            lo, hi = max(prev["last_entry"] / 1e6, ok_s), min(cur["first_entry"] / 1e6, now)
            if hi > lo:
                down += hi - lo
        return int(down)
    except Exception:
        return 0


def main():
    if len(sys.argv) < 3:
        print("usage: cron_state_check.py <name> <max_hours>"); return 2
    n, max_h = sys.argv[1], float(sys.argv[2])
    fail, ok = os.path.join(D, n + ".fail"), os.path.join(D, n + ".ok")
    if os.path.isfile(fail) and os.path.getsize(fail) > 0:
        print(f"FAILED: {open(fail).read().strip()}; log {os.path.join(LOGDIR, n + '.log')}")
        return 1
    if not (os.path.isfile(ok) and os.path.getsize(ok) > 0):
        print(f"no successful run yet (no state file {ok})")
        return 3
    d, t, key = (open(ok).read().split() + ["", "", ""])[:3]
    ok_s = time.mktime(time.strptime(f"{d} {t}", "%Y-%m-%d %H:%M"))
    now = float(os.environ.get("CRON_STATE_NOW") or time.time())
    down_s = downtime(ok_s, now)
    age_h, work_h, down_h = int((now - ok_s) / 3600), int((now - ok_s - down_s) / 3600), int(down_s / 3600)
    if down_h > 0:
        print(f"last success {age_h} h ago ({d} {t}, period {key}), the machine was off {down_h} h of it -> {work_h} working h; limit {max_h:g} h")
    else:
        print(f"last success {age_h} h ago ({d} {t}, period {key}); limit {max_h:g} h")
    return 0 if work_h <= max_h else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"check crashed: {type(e).__name__}: {e}"); sys.exit(3)
