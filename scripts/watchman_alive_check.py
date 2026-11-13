#!/usr/bin/env python3
"""Supervisor check: the briefing watchman (hooks/briefing-watchman.sh, the UserPromptSubmit hook through which agents see
their inbox, hook errors and a dead supervisor) is alive. A RESULT, not "a file exists": if chats are alive (a transcript
was written within ACTIVE_MIN), the watchman must have run within MAX_MIN. Quiet chats = nothing to check = green.
Pulse = ~/.claude/briefing-watchman/heartbeat, which the watchman touches on EVERY run (the newest marker file gave a
false "silent": the watchman writes markers only on change). rc 0 green · 1 red · 3 no data (a missing pulse file means
the installed watchman does not write one yet - the registry entry skips the check until the file exists).
Env: WATCHMAN_DIR, TRANSCRIPTS (the projects dir), ACTIVE_MIN (20), MAX_MIN (90)."""
import glob, os, sys, time

HOME = os.path.expanduser("~")
W = os.environ.get("WATCHMAN_DIR", os.path.join(HOME, ".claude", "briefing-watchman"))
P = os.environ.get("TRANSCRIPTS", os.path.join(HOME, ".claude", "projects"))
ACTIVE_MIN = int(os.environ.get("ACTIVE_MIN", "20"))
MAX_MIN = int(os.environ.get("MAX_MIN", "90"))


def main():
    now = time.time()
    chats = [os.path.getmtime(f) for f in glob.glob(os.path.join(P, "*", "*.jsonl"))]
    try:
        t_w = os.path.getmtime(os.path.join(W, "heartbeat"))
    except OSError:
        t_w = None
    if not chats:
        print("no sessions yet - nothing to watch")
        return 0
    if t_w is None:
        print(f"no data (transcripts: {len(chats)}, watchman pulse: -)")
        return 3
    chat_min, w_min = int((now - max(chats)) / 60), int((now - t_w) / 60)
    print(f"chats: last write {chat_min} min ago; watchman: {w_min} min ago")
    if chat_min > ACTIVE_MIN:
        print("chats are quiet - nothing to check")
        return 0
    if w_min > MAX_MIN:
        print(f"chats are alive and the watchman is silent for over {MAX_MIN} min - agents do not see inbox/alarms")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"check crashed: {type(e).__name__}: {e}"); sys.exit(3)
