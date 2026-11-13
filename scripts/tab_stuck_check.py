#!/usr/bin/env python3
"""Supervisor check: an agent's tab stopped on a SERVICE ERROR while it has work - it will not wake up by itself.

Why: the network dropped for 6 minutes; Claude Code in an agent's tab failed to reach the API 10 times and ended the turn
with a synthetic "API Error: Can't reach the API server". Such an end of turn does not pass through the Stop hooks (the model
never answered), so no alarm restarted. The tab stood 21 h with a letter in its inbox until the human wrote to it.
api_silence_check.py only catches an error AFTER a human message; here the previous event was a service one.

What it does: for every agent in the guard file (config CCM_WORK_GUARD_AGENTS - the same list work-guard uses; empty =
the check is off) it takes the freshest transcript of that agent's session (by ~/.claude/agent-identity). If the LAST reply
in it is a synthetic service error, nothing came after it, it is older than STUCK minutes (10), and the agent has no live
alarm (inbox_wait) -> red. Only a human can wake the tab, so each such case = ONE line in the agent's human-TODO file
(<agent folder>/human-TODO.md, or the old <agent>-<Name>-TODO.md style if that file exists) and a stdout line.
rc 0 none · 1 stuck tabs · 3 could not read.
Env (tests): TAB_STUCK_IDENT, TAB_STUCK_ROOTS (colon-separated), TAB_STUCK_AGENTS (the guard file), TAB_STUCK_WAIT,
TAB_STUCK_STATE, TAB_STUCK_MIN."""
import glob, json, os, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.path.insert(0, HERE)
from ccm_conf import conf  # noqa: E402
from agent_listening import last_ts  # noqa: E402

HOME = os.path.expanduser("~")
IDENT = os.environ.get("TAB_STUCK_IDENT", os.path.join(HOME, ".claude", "agent-identity"))
ROOTS = os.environ.get("TAB_STUCK_ROOTS", os.path.join(HOME, ".claude", "projects")).split(":")
AGENTS = os.environ.get("TAB_STUCK_AGENTS") or conf("CCM_WORK_GUARD_AGENTS", "")
WAIT = os.environ.get("TAB_STUCK_WAIT", os.path.join(HOME, ".claude", "inbox-wait"))
STATE = os.environ.get("TAB_STUCK_STATE", os.path.join(HOME, ".claude", "tab-stuck"))
STUCK = int(os.environ.get("TAB_STUCK_MIN", "10")) * 60
ERR = ("API Error", "Failed to authenticate", "OAuth", "rate limit", "Rate limit", "overloaded", "Can't reach")
TAIL = 256 * 1024


def last_turn(tp):
    """-> (epoch, text) of the last reply if it is a synthetic service error; else None"""
    try:
        with open(tp, "rb") as f:
            f.seek(0, 2); n = f.tell(); f.seek(max(0, n - TAIL)); raw = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    last = None
    for l in raw.splitlines():
        flat = l.replace(" ", "")
        if '"type":"assistant"' not in flat and '"type":"user"' not in flat:
            continue
        try:
            o = json.loads(l)
        except ValueError:
            continue
        if o.get("type") in ("assistant", "user") and not o.get("isSidechain"):
            last = o
    if not last or last.get("type") != "assistant":
        return None
    m = last.get("message") or {}
    if m.get("model") != "<synthetic>":
        return None
    t = " ".join(x.get("text", "") for x in m.get("content") or [] if isinstance(x, dict))
    if not any(e in t for e in ERR):
        return None
    try:
        import calendar
        ts = calendar.timegm(time.strptime(last.get("timestamp", "")[:19], "%Y-%m-%dT%H:%M:%S"))   # transcripts stamp UTC
    except ValueError:
        return None
    return ts, t.strip()[:120]


def waiter_alive(agent):
    try:
        p = open(os.path.join(WAIT, agent)).read().strip()
        return bool(p) and os.path.exists(f"/proc/{p}")
    except OSError:
        return False


def todo_file(d, agent):
    old = sorted(glob.glob(os.path.join(d, f"{agent}-*-TODO.md")))
    old = [p for p in old if not p.endswith("-agent-TODO.md")]
    return old[0] if old else os.path.join(d, "human-TODO.md")


def main():
    if not AGENTS:
        print("off: no guard file (config CCM_WORK_GUARD_AGENTS) - no agents to watch")
        return 0
    try:
        agents = [l.strip() for l in open(AGENTS, encoding="utf-8") if l.strip() and not l.startswith("#")]
    except OSError:
        print(f"cannot read {AGENTS}")
        return 3
    best = {}                                         # agent -> (last event time, transcript, agent folder)
    for p in glob.glob(os.path.join(IDENT, "*")):
        try:
            d = open(p).read().strip().rstrip("/")
        except OSError:
            continue
        a = os.path.basename(d)
        if a not in agents:
            continue
        sid = os.path.basename(p)
        for r in ROOTS:
            for tp in glob.glob(os.path.join(r, "*", sid + ".jsonl")):
                # time of the last event INSIDE the transcript, not the mtime: a nightly job that rewrites session files
                # made a sleeping session the "freshest" one
                mt = last_ts(tp) or os.path.getmtime(tp)
                if mt > best.get(a, (0,))[0]:
                    best[a] = (mt, tp, d)
    now, stuck = time.time(), []
    os.makedirs(STATE, exist_ok=True)
    human = conf("CCM_HUMAN_NAME")
    for a, (mt, tp, d) in sorted(best.items()):
        r = last_turn(tp)
        if not r or now - r[0] < STUCK or waiter_alive(a):
            continue
        ts, txt = r
        when = time.strftime("%d.%m %H:%M", time.localtime(ts))
        stuck.append(f"{a} since {when}")
        mark = os.path.join(STATE, f"{a}-{int(ts)}")
        if os.path.exists(mark):
            continue                                  # the human was already told about this very stop
        line = (f"- [ ] 🟥 [{time.strftime('%F %H:%M')}] **Tab {a} has stood since {when}** - Claude Code could not reach the "
                f"service (\"{txt[:70]}\") and stopped; it will not wake up by itself. {human}: write \"+\" in that tab and it "
                f"continues from where it stopped.\n")
        try:
            with open(todo_file(d, a), "a", encoding="utf-8") as f:
                f.write(line)
            open(mark, "w").write(line)
        except OSError:
            pass
    if stuck:
        print("stopped on a service error, no alarm: " + "; ".join(stuck) + " - a line was added to the agent's human TODO")
        return 1
    print(f"no stuck tabs (agents checked: {len(best)})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"check crashed: {type(e).__name__}: {e}"); sys.exit(3)
