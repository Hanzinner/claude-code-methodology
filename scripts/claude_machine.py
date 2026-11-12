#!/usr/bin/env python3
"""claude_machine.py <label> -p [claude -p arguments...] - a machine run of `claude -p` WITHOUT saving a session, with cost accounting.

Why: every `claude -p` run from a script was saved as a session - 79 reviewer sessions cluttered the sessions list
in the editor. `--no-session-persistence` removes that, but then a quota tool no longer sees the spend (service runs
were 29% of one week's quota) - so every run writes a usage line to the MACHINE_USAGE log, which a quota tool can
count as "service: <label>".

What it does: adds --no-session-persistence and --output-format json (a caller's own --output-format is dropped),
passes stdin through, prints only the answer text on stdout (as --output-format text would), and returns claude's rc
(an answer with is_error -> rc 1). The label says who is calling: cross_review, consolidation...
Log: $MACHINE_USAGE, default ~/.claude/machine-usage.jsonl. Binary: $CLAUDE_BIN (default `claude`).
"""
import os
import json, signal, subprocess, sys, time

LOG = os.environ.get("MACHINE_USAGE") or os.path.expanduser("~/.claude/machine-usage.jsonl")


def main():
    if len(sys.argv) < 3 or sys.argv[2] != "-p":
        print("usage: claude_machine.py <label> -p [claude arguments] - see the header", file=sys.stderr)
        return 2
    tag, args = sys.argv[1], sys.argv[2:]
    clean, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a == "--output-format":
            skip = True
            continue
        if a.startswith("--output-format="):
            continue
        clean.append(a)
    # our own flags go BEFORE the caller's arguments: after `--` they would become text
    cmd = [os.environ.get("CLAUDE_BIN", "claude"), "--no-session-persistence", "--output-format", "json", *clean]
    # `timeout N claude_machine.py ...` sends SIGTERM only to us - forward it to the child, or claude is orphaned.
    # The handler is installed BEFORE the child starts, or a signal between Popen and signal() kills us without forwarding
    child = []
    def fwd(n, f):
        if child:
            child[0].send_signal(n)
        sys.exit(128 + n)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, fwd)
    p = subprocess.Popen(cmd, stdin=sys.stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    child.append(p)
    out, err = p.communicate()
    r = subprocess.CompletedProcess(cmd, p.returncode, out, err)
    sys.stderr.write(r.stderr)
    try:
        d = json.loads(r.stdout)
    except ValueError:
        sys.stdout.write(r.stdout)   # not json (claude failed before starting) - pass it through as is, with claude's rc
        return r.returncode
    res = next((e for e in reversed(d) if isinstance(e, dict) and e.get("type") == "result"), {}) if isinstance(d, list) else d
    text = res.get("result") or ""
    sys.stdout.write(text + ("\n" if text and not text.endswith("\n") else ""))
    if not res.get("modelUsage"):
        print("claude_machine: no modelUsage in the answer - this run's cost is not accounted", file=sys.stderr)
    try:
        os.makedirs(os.path.dirname(LOG) or ".", exist_ok=True)
        with open(LOG, "a") as f:
            for model, u in (res.get("modelUsage") or {}).items():
                f.write(json.dumps({"ts": int(time.time()), "tag": tag, "model": model,
                                    "i": u.get("inputTokens", 0), "o": u.get("outputTokens", 0),
                                    "cr": u.get("cacheReadInputTokens", 0), "cc": u.get("cacheCreationInputTokens", 0),
                                    "usd": u.get("costUSD")}) + "\n")
    except OSError as e:
        print(f"claude_machine: usage line not written ({e})", file=sys.stderr)
    if r.returncode:
        return r.returncode
    return 1 if res.get("is_error") else 0


if __name__ == "__main__":
    sys.exit(main())
