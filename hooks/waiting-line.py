#!/usr/bin/env python3
"""UserPromptSubmit: one line "waiting for you" for a human who has no dashboard (decision 0021).

What stops work until the human acts lives in the blockers register (scripts/blockers.py, <project>/BLOCKERS.md); what
only asks for a direction (🎯) or a look (👁) lives in each agent's human-TODO.md. Without a dashboard nobody shows the
human either. Before the human's next message this hook hands the agent one line to put first in its reply:

  waiting for you: 2 blockers - Bid: B3 token permissions (12 d); Shop: B1 payment key (3 d) · in human-TODO: 4 open (3 agents)

* blockers: shown when the set of open blockers changed since this session last showed it, or every
  CCM_WAITING_REPEAT_H hours (default 4) - pushed, but not the same line before every message;
* human-TODO: only a count, at most once a day (across sessions); details when the human asks;
* nothing open -> nothing printed. A prompt that is not the human (a task notice, CCM_MACHINE_SESSION=1) -> nothing.
The hook reads files only; it never changes a blocker or a TODO.

Config (methodology.conf): CCM_WAITING_LINE (1 = on, the default here; 0 = off, e.g. when a dashboard shows the same),
CCM_WAITING_REPEAT_H, CCM_WORKSPACE, CCM_AGENTS_DIR. State: ~/.claude/waiting-line/.
"""
import glob, hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
INSTALL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(INSTALL, "lib"))
from ccm_conf import conf  # noqa: E402
import ccm_fs  # noqa: E402  (os.replace that waits out a file held open on Windows)

STATE = os.path.join(os.path.expanduser("~"), ".claude", "waiting-line")
MAX_LINE = 400


def blockers():
    """open blockers from blockers.py list --json; any failure = none (a hint must never block a prompt)"""
    bp = os.path.join(INSTALL, "scripts", "blockers.py")
    if not os.path.isfile(bp):
        return []
    try:
        r = subprocess.run([sys.executable, bp, "list", "--json"], capture_output=True, text=True, timeout=8)
        data = json.loads(r.stdout) if r.returncode == 0 else []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def human_todo():
    """(open items, agents with any) over every agent's human-TODO.md: '- ' lines in the '## Open' section, not '- [x]'"""
    agents = conf("CCM_AGENTS_DIR", "") or os.path.join(conf("CCM_WORKSPACE", ""), "Agents")
    items = owners = 0
    for p in sorted(set(glob.glob(os.path.join(agents, "*", "human-TODO.md")) + glob.glob(os.path.join(agents, "*", "*-human-TODO.md")))):
        try:
            lines = open(p, encoding="utf-8").read().splitlines()
        except OSError:
            continue
        sec, n = None, 0
        for l in lines:
            if l.startswith("## "):
                sec = l[3:].strip().lower()
            elif sec == "open" and l.lstrip().startswith("- ") and not l.lstrip().lower().startswith("- [x]"):
                n += 1
        items += n
        owners += 1 if n else 0
    return items, owners


def short(s, n=60):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def save(p, d):
    os.makedirs(STATE, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    ccm_fs.replace(tmp, p)


def main():
    if conf("CCM_WAITING_LINE", "1") in ("0", "off", "no", "false"):
        return
    raw = sys.stdin.read()
    if os.environ.get("CCM_MACHINE_SESSION") or "task-notification" in raw or "SYSTEM NOTIFICATION" in raw:
        return
    try:
        sid = str(json.loads(raw).get("session_id") or "x")
    except ValueError:
        sid = "x"
    sid = "".join(c for c in sid if c.isalnum() or c in "-_")[:64] or "x"
    now = time.time()
    repeat = float(conf("CCM_WAITING_REPEAT_H", "") or 4) * 3600

    parts = []
    bl = blockers()
    sess_p = os.path.join(STATE, f"{sid}.json")
    sess = load(sess_p)
    fp = hashlib.sha256(json.dumps(sorted(f"{b.get('project')}:{b.get('id')}" for b in bl)).encode()).hexdigest()[:16]
    if bl and (sess.get("fp") != fp or now - sess.get("at", 0) >= repeat):
        bl.sort(key=lambda b: -(b.get("days") or 0))
        shown = "; ".join(f"{b.get('project')}: {b.get('id')} {short(b.get('what'))} ({b.get('days', '?')} d)" for b in bl[:3])
        more = f"; +{len(bl) - 3} more" if len(bl) > 3 else ""
        parts.append(f"{len(bl)} blocker{'s' if len(bl) != 1 else ''} - {shown}{more}")
        sess = {"fp": fp, "at": now}
    elif not bl:
        sess = {"fp": fp, "at": sess.get("at", 0)}

    day_p = os.path.join(STATE, "human-todo-day")
    today = time.strftime("%Y-%m-%d")
    try:
        last_day = open(day_p, encoding="utf-8").read().strip()
    except OSError:
        last_day = ""
    if last_day != today:
        items, owners = human_todo()
        if items:
            parts.append(f"in human-TODO: {items} open ({owners} agent{'s' if owners != 1 else ''}) - details when asked")
            os.makedirs(STATE, exist_ok=True)
            with open(day_p, "w", encoding="utf-8") as f:
                f.write(today)
    save(sess_p, sess)
    if not parts:
        return
    line = short("waiting for you: " + " · ".join(parts), MAX_LINE)
    ctx = (f"📌 Put this as the FIRST line of your reply to the human, as is: «{line}». "
           f"Details: scripts/blockers.py list (blockers), the agents' human-TODO.md files (🎯 decisions, 👁 checks).")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(1)
