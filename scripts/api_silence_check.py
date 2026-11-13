#!/usr/bin/env python3
"""Supervisor check: an agent is silent NOT by its own fault - the harness answers the human with a synthetic API error.

Why: for ~2 h a human wrote "what is with you / are you alive?" and every "reply" was `model: <synthetic>` - "API Error:
Can't reach the API server (EAI_AGAIN)" (DNS broke on the machine), "Failed to authenticate: OAuth session expired", and
to the service line "Continue from where you left off." the harness itself wrote "No response requested." The model was
never called, so a Stop gate is powerless. The signal therefore goes around the agent: supervisor -> human, with the cause.

Red (rc 1): in the last WINDOW minutes (20) some transcript holds a synthetic error reply (API Error / Failed to
authenticate / OAuth / rate limit / overloaded) that FOLLOWS a real human message (not isMeta, not a tool_result).
stdout = one line: how many, which sessions, the cause. Green (rc 0) = silence. Could not read = rc 3.
Env: API_SILENCE_ROOTS (colon-separated projects dirs, default ~/.claude/projects), API_SILENCE_WINDOW_MIN (20)."""
import glob, json, os, sys, time

ROOTS = os.environ.get("API_SILENCE_ROOTS", os.path.join(os.path.expanduser("~"), ".claude", "projects")).split(":")
WINDOW = int(os.environ.get("API_SILENCE_WINDOW_MIN", "20")) * 60
TAIL = 512 * 1024
ERR_MARKS = ("API Error", "Failed to authenticate", "OAuth", "rate limit", "Rate limit", "overloaded")


def epoch(ts):
    import calendar
    try:
        return calendar.timegm(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))   # transcripts stamp UTC
    except (ValueError, TypeError):
        return 0


def human_text(o):
    """text of a real human message, or None (service line, tool result)"""
    if o.get("type") != "user" or o.get("isMeta"):
        return None
    c = (o.get("message") or {}).get("content")
    if isinstance(c, str):
        t = c
    elif isinstance(c, list):
        if any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c):
            return None
        t = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    else:
        return None
    t = t.strip()
    if not t or t.startswith("<") or t.startswith("[Request interrupted"):
        return None
    return t


def scan(tp, now):
    """-> [(cause, the human's text)] inside the window"""
    try:
        with open(tp, "rb") as f:
            size = f.seek(0, 2)
            start = max(0, size - TAIL)
            f.seek(start)
            lines = f.read().decode("utf-8", "replace").split("\n")
            if start:
                lines = lines[1:]           # we started mid-line - it is incomplete
    except OSError:
        return []
    out, last_human = [], None
    for l in lines:
        if '"type":"user"' in l or '"type": "user"' in l:
            try:
                o = json.loads(l)
            except ValueError:
                continue
            h = human_text(o)
            if h is not None:
                last_human = h
            elif not o.get("isMeta"):
                last_human = None          # a tool result - the agent is working
            continue
        if '"<synthetic>"' not in l:
            if '"type":"assistant"' in l or '"type": "assistant"' in l:
                last_human = None          # a real model reply
            continue
        try:
            o = json.loads(l)
        except ValueError:
            continue
        if now - epoch(o.get("timestamp", "")) > WINDOW:
            continue
        txt = " ".join(x.get("text", "") for x in (o.get("message") or {}).get("content") or []
                       if isinstance(x, dict) and x.get("type") == "text")
        if last_human and any(m in txt for m in ERR_MARKS):
            out.append((txt.strip()[:90], last_human[:40]))
    return out


def main():
    now = time.time()
    hits, read = [], 0
    for root in ROOTS:
        for tp in glob.glob(os.path.join(root, "*", "*.jsonl")):
            if tp.endswith("-cut.jsonl"):
                continue
            try:
                if now - os.path.getmtime(tp) > WINDOW:
                    continue
            except OSError:
                continue
            read += 1
            for why, said in scan(tp, now):
                hits.append((os.path.basename(tp)[:8], why, said))
    if not hits:
        print(f"silence (transcripts in the window: {read})")
        return 0
    sessions = sorted({h[0] for h in hits})
    print(f"agents do not answer the human - the harness returns an error ({len(hits)} times, sessions {', '.join(sessions)}): "
          f"\"{hits[-1][1]}\"; the human's last message: \"{hits[-1][2]}\"")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"check crashed: {type(e).__name__}: {e}")
        sys.exit(3)
