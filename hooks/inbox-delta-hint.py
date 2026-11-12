#!/usr/bin/env python3
"""inbox-delta-hint - PostToolUse (matcher *): a new letter arrived in the agent's inbox MID-TURN -> a hint on the
agent's next tool call.

Why: an agent spent an hour finishing buttons to a specification its coordinator had already replaced twice - the
letters arrived in the middle of a long turn, and the briefing watchman delivers only on UserPromptSubmit.

Logic (cheap - it runs on EVERY tool call):
  1. the session's identity (~/.claude/agent-identity/<session id>, written by the watchman) -> the agent's folder;
     none -> silence.
  2. the inbox.md mtime is unchanged since last time -> exit (a stat only).
  3. changed -> the `- [ ]` items of "## New" against the stored set; NEW ones -> additionalContext. Only the delta
     (first line of an item, cut), never the whole inbox.
  4. throttle: no more often than THROTTLE seconds between hints; under the throttle the state is NOT updated - the
     letter is not lost, it arrives with the next call after the throttle.
The first call of a session (no state) is a silent baseline: what already lay there was shown by the watchman.
Known tolerances: a letter that landed between UserPromptSubmit and the first tool of the FIRST turn is absorbed by the
baseline (the watchman shows it on the next prompt). Parallel tools may rarely give a double hint (check-then-act
without a lock; the price is noise, not loss). A letter outside "## New" is not seen (parity with the watchman).
The state is written BEFORE the print: a crash in between = "seen" without a hint; the backstop is the watchman.
Section names: "## New" (and "## New candidates"); Ukrainian "## Нові" is accepted too.
Env: INBOX_DELTA_THROTTLE (seconds, default 60). Fail-open under hook-safe.sh."""
import hashlib, json, os, sys, time

STATE_DIR = os.path.expanduser("~/.claude/inbox-delta")
IDENTITY_DIR = os.path.expanduser("~/.claude/agent-identity")
try:
    THROTTLE = int(os.environ.get("INBOX_DELTA_THROTTLE", "60"))
except ValueError:
    THROTTLE = 60
STATE_TTL = 30 * 86400  # state of dead sessions
MAX_SHOW = 3
MAX_LEN = 220
NEW_HEADS = ("## New", "## Нові")


def new_items(path):
    """First lines of the `- [ ]` items in the "## New" section (the same rule as the watchman's awk)."""
    out, sect = [], False
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f.read().split("\n"):  # not splitlines(): it also splits on form feeds, U+2028...
            if line.startswith("## "):
                sect = line.startswith(NEW_HEADS)
                continue
            if sect and line.startswith("- [ ]"):
                out.append(line.strip())
    return out


def prune(now):
    """Once per new session: remove the state of sessions older than STATE_TTL."""
    try:
        for n in os.listdir(STATE_DIR):
            fp = os.path.join(STATE_DIR, n)
            if now - os.stat(fp).st_mtime > STATE_TTL:
                os.remove(fp)
    except OSError:
        pass


def key(item):
    return hashlib.sha1(item.encode()).hexdigest()[:16]


def main():
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return
    sid = ev.get("session_id") or ""
    if not sid or "/" in sid:
        return
    try:
        agent_dir = open(os.path.join(IDENTITY_DIR, sid)).read().strip()
    except OSError:
        return
    if not os.path.isabs(agent_dir):  # an empty/broken identity would make inbox.md relative to the cwd
        return
    inbox = os.path.join(agent_dir, "inbox.md")
    try:
        mtime = os.stat(inbox).st_mtime_ns
    except OSError:
        return

    sf = os.path.join(STATE_DIR, sid + ".json")
    try:
        st = json.load(open(sf))
    except Exception:
        st = None
    if st and st.get("mtime") == mtime:
        return
    now = time.time()
    if st and now - st.get("hinted_at", 0) < THROTTLE:
        return  # the state is not touched - the delta survives until the next call

    items = new_items(inbox)
    keys = {key(i) for i in items}
    fresh = [] if st is None else [i for i in items if key(i) not in set(st.get("keys", []))]

    if st is None:
        prune(now)
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = sf + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"mtime": mtime, "keys": sorted(keys),
                   "hinted_at": now if fresh else (st or {}).get("hinted_at", 0)}, f)
    os.replace(tmp, sf)

    if not fresh:
        return
    lines = [(i if len(i) <= MAX_LEN else i[:MAX_LEN] + "…") for i in fresh[:MAX_SHOW]]
    more = f"\n(+ {len(fresh) - MAX_SHOW} more)" if len(fresh) > MAX_SHOW else ""
    msg = (f"📥 A new item arrived in your inbox ({inbox}) in the middle of your turn ({len(fresh)}):\n"
           + "\n".join(lines) + more
           + "\nRe-read \"New\" BEFORE your next step - the letter may change the current task.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": msg}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
