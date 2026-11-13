#!/usr/bin/env python3
"""presence_check.py - is the human at the machine? For anything that wants to PUSH a message to them (a phone ping, a
bot): push only when the answer is "away". The machine may be always on (remote desktop), so this measures ACTIVITY,
not machine state:
  1. a fresh prompt in any Claude session (< 15 min; the timestamps hooks/check-prompt-gap.sh keeps in
     <claude dir>/cache/prompt-timestamps/<session id>, top level only - a "machine/" subfolder is not the human) -> present
  2. else the DESKTOP source: config CCM_PRESENCE_CMD = a command that prints the desktop's idle time (the human may be at
     the keyboard but not in Claude): a number of minutes, "." (= 0), "H:MM" or "D+HH:MM". Idle < 15 min -> present.
     Examples: `ssh desk 'quser' | awk '$4=="Active"{print $5; exit}'` (Windows RDP), `xprintidle | awk '{print int($1/60000)}'`
     (X11), `ioreg -c IOHIDSystem | awk '/HIDIdleTime/{print int($NF/1e9/60); exit}'` (macOS).
     Larger idle -> away. Empty key = no desktop source: the decision rests on prompts alone.
  3. the command fails or prints nothing -> unknown: FAIL-CLOSED (treat as present, do NOT push).
Output: "present:..." | "away:..." | "unknown:..."; rc 0 present · 1 away · 2 unknown. Push only on rc 1.
Env: PRESENCE_FRESH_S (900), DESKTOP_IDLE_MIN (15), PRESENCE_TS_DIR (tests), PRESENCE_NOW (tests)."""
import os, re, subprocess, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

FRESH_S = int(os.environ.get("PRESENCE_FRESH_S", "900"))
IDLE_MIN = int(os.environ.get("DESKTOP_IDLE_MIN", "15"))
TS_DIR = os.environ.get("PRESENCE_TS_DIR") or os.path.join(os.environ.get("CLAUDE_METHODOLOGY_DIR") or os.path.join(os.path.expanduser("~"), ".claude"), "cache", "prompt-timestamps")


def idle_minutes(raw):
    raw = raw.strip()
    if raw == ".":
        return 0
    if "+" in raw:
        return 99999                                   # days - away for sure
    m = re.fullmatch(r"(\d+):(\d+)", raw)
    if m:
        return 60 * int(m.group(1)) + int(m.group(2))
    if raw.isdigit():
        return int(raw)
    return None


def main():
    now = int(os.environ.get("PRESENCE_NOW") or time.time())
    newest = 0
    try:
        for f in os.listdir(TS_DIR):
            p = os.path.join(TS_DIR, f)
            if os.path.isfile(p):
                try:
                    newest = max(newest, int(open(p).read().strip()))
                except (OSError, ValueError):
                    pass
    except OSError:
        pass
    gap = now - newest
    if gap < FRESH_S:
        print(f"present:prompt {gap}s ago")
        return 0
    cmd = conf("CCM_PRESENCE_CMD", "")
    if not cmd:
        print(f"away:no prompt for {gap // 60} min; no desktop source configured (CCM_PRESENCE_CMD) - judged by prompts only")
        return 1
    try:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=20)
        out = r.stdout.strip().splitlines()
    except (subprocess.SubprocessError, OSError):
        out = []
    idle = idle_minutes(out[0]) if out else None
    if idle is None:
        print("unknown:the desktop source gave no usable answer (fail-closed -> do NOT push)")
        return 2
    if idle < IDLE_MIN:
        print(f"present:desktop idle {idle} min (at the desk, not in Claude; last prompt {gap // 60} min ago)")
        return 0
    print(f"away:desktop idle {idle} min, last prompt {gap // 60} min ago - push allowed")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"unknown:check crashed: {type(e).__name__}: {e}")
        sys.exit(2)
