#!/usr/bin/env python3
"""reply-guard — detects "the agent wrote the user's line for them".

On Stop, reads the transcript, takes the LAST assistant message, and looks for
role markers at the start of lines OUTSIDE code blocks: "User:", "Human:", or a
configured name. A detector, not a preventer — the text is already streamed;
a hit → a log line + a flag file, so it doesn't pass silently. Fail-open.

Why: an agent that fabricates a "User: ..." turn is putting words in the human's
mouth. That failure had been "just be careful" for too long; this makes it visible.

Config: REPLY_GUARD_NAMES (comma-separated extra name markers, e.g. the operator's name)
"""
import json, os, re, sys, time

LOG = os.path.expanduser("~/.claude/reply-guard.log")
FLAGDIR = os.path.expanduser("~/.claude/reply-guard-flags")
names = ["User", "Human"] + [n.strip() for n in
                             os.environ.get("REPLY_GUARD_NAMES", "").split(",") if n.strip()]
MARK = re.compile(r"^\s*(?:\*\*)?(" + "|".join(re.escape(n) for n in names) + r")(?:\*\*)?\s*:", re.I)

try:
    d = json.load(sys.stdin)
    tp = d.get("transcript_path", "")
    sid = d.get("session_id", "?")
    last_text = ""
    with open(tp, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"assistant"' not in line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("type") == "assistant":
                for c in (o.get("message") or {}).get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "text":
                        last_text = c["text"]
    hits, in_code = [], False
    for ln in last_text.split("\n"):
        if ln.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code and MARK.match(ln):
            hits.append(ln.strip()[:120])
    if hits:
        os.makedirs(FLAGDIR, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%FT%T')} sid={sid[:8]} FABRICATED USER LINE? {len(hits)} line(s): {hits[0]}\n")
        with open(os.path.join(FLAGDIR, sid), "w", encoding="utf-8") as f:
            f.write("\n".join(hits) + "\n")
except Exception:
    sys.exit(0)   # fail-open: the guard never blocks completion
sys.exit(0)
