#!/usr/bin/env python3
"""stuck-detector — "stuck in a hole".

The written rule "after 3 failures, stop and search how others do it" went
unfollowed for a month by every agent it was addressed to. One real case: 40
attempts in 40 minutes at installing something on an OS it didn't support —
a one-minute search had the answer. So the rule became this hook.

PostToolUseFailure(Bash) → counter +1; PostToolUse(Bash) → reset to 0.
At 3, 6, 9… failures in a row → additionalContext "stop, go look it up".
Not counted: interrupts (is_interrupt) and a bare "Exit code 1" with no text —
that's grep/test reporting "no match", a normal state, not a hole.

State: ~/.claude/stuck-state/<session>; hit log: ~/.claude/stuck-hits.log.
Wire it to both PostToolUse and PostToolUseFailure with matcher "Bash".
"""
import json, os, re, sys, time

N = 3


def main():
    d = json.load(sys.stdin)
    if d.get("tool_name") != "Bash":
        return
    ev = d.get("hook_event_name", "")
    sid = d.get("session_id") or "x"
    home = os.path.expanduser("~")
    sdir = f"{home}/.claude/stuck-state"
    os.makedirs(sdir, exist_ok=True)
    sf = f"{sdir}/{sid}"
    if ev == "PostToolUse":
        if os.path.exists(sf):
            open(sf, "w").write("0")
        return
    if ev != "PostToolUseFailure" or d.get("is_interrupt"):
        return
    err = (d.get("error") or "").strip()
    if re.fullmatch(r"Exit code 1", err):
        return
    try:
        n = int(open(sf).read().strip() or 0)
    except (OSError, ValueError):
        n = 0
    n += 1
    open(sf, "w").write(str(n))
    if n % N:
        return
    cmd = ((d.get("tool_input") or {}).get("command") or "")[:80].replace("\n", " ")
    with open(f"{home}/.claude/stuck-hits.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%F %T')} [{sid[:8]}] {n} failures in a row; last: {cmd}\n")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUseFailure",
        "additionalContext":
            f"[stuck] {n} failed Bash calls in a row. STOP before the next attempt: "
            "(1) search how people actually do this — the symptom plus your stack, five "
            "minutes; (2) re-read the relevant playbook / pitfalls file IN FULL, not by grep; "
            "(3) in your next reply to the human, include a 'source: …' line naming what you "
            "found or read. A third fix to the same spot that opens a new hole means the "
            "approach is wrong, not that there's one more bug."}},
        ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # don't swallow silently: trace to stderr, rc=1 → hook-safe.sh logs it (fail-open)
        import traceback; traceback.print_exc(); sys.exit(1)
