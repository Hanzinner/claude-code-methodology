#!/usr/bin/env python3
"""remind — a reminder to an agent as a letter in its inbox ("remind me at <time>"): the human can tell an agent to set
a reminder, and when the timer runs out a letter lands in the agent's inbox.

  remind.py <agent> <when> <text>     set one. <when>: 15m | 2h | 3d | 1h30m | 18:30 (today; already past — tomorrow)
                                      | "2026-10-09 10:00" | anything GNU `date -d` understands ("tomorrow 09:00")
  remind.py --list [agent]            what is pending
  remind.py --cancel <id>             cancel (the file goes to done/ with a mark)
  remind.py --fire                    cron, every minute: everything whose time has come -> inbox_post to the addressee

A reminder is a file in the reminders dir (config CCM_REMINDERS_DIR, default ~/.claude/reminders) — it survives a
reboot and a session compaction; the agent may remember nothing. If the machine was off at the time, the letter arrives
in the first minute after start, with a note "late". A letter that could not be delivered (the mail script refused)
stays as a file, the next minute tries again; after a day of failures it goes to failed/ and a line to the log.
The letter only LANDS in the inbox: the tab wakes by itself only if a live alarm inbox_wait.sh is running in it;
otherwise the agent sees the letter when the human writes in it.

Cron (user crontab):  * * * * * python3 <install dir>/scripts/remind.py --fire >/dev/null 2>&1
The addressee is a folder name under the agents dir (config CCM_AGENTS_DIR); scripts/inbox_resolve.sh is used when
it is installed next to this file, otherwise the same lookup is done here. Delivery goes through scripts/inbox_post.sh."""
import fcntl, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402

D = os.environ.get("REMIND_DIR") or conf("CCM_REMINDERS_DIR", "") or os.path.join(os.path.expanduser("~"), ".claude", "reminders")
POST = os.environ.get("REMIND_POST", f"{HERE}/inbox_post.sh")
RESOLVE = os.environ.get("REMIND_RESOLVE", f"{HERE}/inbox_resolve.sh")
LOG = os.environ.get("REMIND_LOG", f"{D}/remind.log")
GIVE_UP = 86400
REL = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?$")
HM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def now():
    return int(os.environ.get("REMIND_NOW") or time.time())


def parse_when(s, t0):
    """-> epoch or None. Relative — from t0; HH:MM — the nearest in the future."""
    s = s.strip()
    m = REL.match(s.replace(" ", "").lower())
    if m and any(m.groups()):
        d, h, mi = (int(x or 0) for x in m.groups())
        return t0 + d * 86400 + h * 3600 + mi * 60
    m = HM.match(s)
    if m:
        lt = time.localtime(t0)
        t = int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, int(m.group(1)), int(m.group(2)), 0, 0, 0, -1)))
        return t if t > t0 else t + 86400
    if re.fullmatch(r"\d+", s):          # a bare "10": `date -d` would read it as 10:00 today, while 10 minutes was meant
        return None
    try:
        r = subprocess.run(["date", "-d", s, "+%s"], capture_output=True, text=True, timeout=5)
        return int(r.stdout) if r.returncode == 0 else None
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return None


def fmt(t):
    return time.strftime("%d.%m %H:%M", time.localtime(t))


def span(sec):
    sec = max(int(sec), 0); d, h, m = sec // 86400, sec % 86400 // 3600, sec % 3600 // 60
    return " ".join(x for x in (f"{d} d" if d else "", f"{h} h" if h else "", f"{m} min" if m or not (d or h) else "") if x)


def pending():
    out = []
    try:
        names = sorted(os.listdir(D))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".json"):
            continue
        try:
            r = json.load(open(f"{D}/{n}", encoding="utf-8"))
        except OSError:
            continue
        except ValueError:
            r = None
        if not (isinstance(r, dict) and {"id", "agent", "due", "text"} <= r.keys() and isinstance(r["due"], (int, float))):
            # a broken file (hand-edited) must not stop the rest: aside and into the log
            try:
                os.makedirs(f"{D}/failed", exist_ok=True); os.replace(f"{D}/{n}", f"{D}/failed/{n}")
                log(f"BROKEN {n}: not a reminder (no id/agent/due/text) -> failed/")
            except OSError:
                pass
            continue
        r["_file"] = f"{D}/{n}"; out.append(r)
    return sorted(out, key=lambda r: r.get("due", 0))


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')} {msg}\n")
    except OSError:
        pass


def move(r, sub, **extra):
    os.makedirs(f"{D}/{sub}", exist_ok=True)
    body = {k: v for k, v in r.items() if k != "_file"}; body.update(extra)
    with open(f"{D}/{sub}/{os.path.basename(r['_file'])}", "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    try:
        os.remove(r["_file"])
    except FileNotFoundError:        # --cancel and --fire met on the same file
        pass


def resolve(agent):
    """-> (ok, message). Uses inbox_resolve.sh next to this file when installed, else the same lookup inline:
    a folder <agent> or <agent>-agent under the agents dir (also one level down), case-insensitive, with an inbox.md."""
    if os.path.isfile(RESOLVE):
        r = subprocess.run([RESOLVE, agent], capture_output=True, text=True)
        return r.returncode == 0, (r.stderr or r.stdout).strip()[:300]
    root = conf("CCM_AGENTS_DIR", "")
    want = {agent.lower(), agent.lower() + "-agent"}
    hits = []
    bases = [root] + ([os.path.join(root, g) for g in sorted(os.listdir(root))] if os.path.isdir(root) else [])
    for base in bases:
        try:
            for n in os.listdir(base):
                if n.lower() in want and os.path.isfile(os.path.join(base, n, "inbox.md")):
                    hits.append(os.path.join(base, n))
        except OSError:
            pass
    if len(hits) == 1:
        return True, hits[0]
    return False, (f"no inbox found for '{agent}' under {root}" if not hits else f"'{agent}' is ambiguous: {' '.join(hits)}")


def add(agent, when, text):
    t0 = now(); due = parse_when(when, t0)
    if due is None:
        print(f"remind: can't understand the time \"{when}\". Examples: 15m · 2h · 3d · 1h30m · 18:30 · \"2026-10-09 10:00\" · \"tomorrow 09:00\"", file=sys.stderr); return 2
    if due <= t0:
        print(f"remind: the time \"{when}\" ({fmt(due)}) is already past — not setting it", file=sys.stderr); return 2
    if not text.strip():
        print("remind: empty reminder text", file=sys.stderr); return 2
    ok, why = resolve(agent)
    if not ok:
        print(f"remind: addressee \"{agent}\" not found — {why}", file=sys.stderr); return 2
    os.makedirs(D, exist_ok=True)
    rid = os.urandom(3).hex()
    path = f"{D}/{due}-{rid}.json"
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"id": rid, "agent": agent, "due": due, "set": t0, "text": text.strip()}, f, ensure_ascii=False)
    os.replace(path + ".tmp", path)
    print(f"⏰ reminder {rid} for {agent}: {fmt(due)} (in {span(due - t0)}) — \"{text.strip()[:80]}\". "
          f"A letter will land in the inbox; for the tab to wake by itself keep the alarm inbox_wait.sh {agent} running. Cancel: remind.py --cancel {rid}")
    return 0


def fire():
    os.makedirs(D, exist_ok=True)
    lk = open(f"{D}/.fire.lock", "a")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0
    t = now(); bad = 0
    for r in pending():
        if r.get("due", 0) > t:
            break
        late = t - r["due"]
        msg = (f"⏰ **Reminder** (set {fmt(r.get('set', r['due']))} for {fmt(r['due'])}"
               + (f"; late by {span(late)} — the machine was off or the mail refused" if late > 300 else "") + f"): {r['text']}")
        try:
            p = subprocess.run([POST, r["agent"], msg], capture_output=True, text=True, timeout=60); rc = p.returncode
            err = (p.stderr or p.stdout).strip()[:200]
        except (OSError, subprocess.TimeoutExpired) as e:
            rc, err = 99, str(e)[:200]
        if rc == 0:
            move(r, "done", fired=t); log(f"FIRED {r['id']} -> {r['agent']} (late {late} s)")
        elif t - r.get("first_fail", t) > GIVE_UP:      # a day from the FIRST failure, not from the reminder's time
            move(r, "failed", error=err); bad += 1; log(f"GAVE UP {r['id']} -> {r['agent']}: no letter for a day ({err})")
        else:
            bad += 1; log(f"RETRY {r['id']} -> {r['agent']}: rc={rc} {err}")
            if "first_fail" not in r:
                body = {k: v for k, v in r.items() if k != "_file"}; body["first_fail"] = t
                try:
                    with open(r["_file"] + ".tmp", "w", encoding="utf-8") as f:
                        json.dump(body, f, ensure_ascii=False)
                    os.replace(r["_file"] + ".tmp", r["_file"])
                except OSError:
                    pass
    return 1 if bad else 0


def main(a):
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__.split("\n\nA reminder is a file")[0]); return 0 if a else 2
    if a[0] == "--fire":
        return fire()
    if a[0] == "--list":
        rows = [r for r in pending() if len(a) < 2 or r.get("agent", "").lower() == a[1].lower()]
        for r in rows:
            print(f"{r['id']}  {fmt(r['due'])} (in {span(r['due'] - now())})  {r['agent']}: {r['text'][:100]}")
        if not rows:
            print("no reminders")
        return 0
    if a[0] == "--cancel":
        for r in pending():
            if len(a) > 1 and r.get("id") == a[1]:
                move(r, "done", cancelled=now()); print(f"cancelled {a[1]}: {r['agent']} {fmt(r['due'])} — {r['text'][:80]}"); return 0
        print(f"remind: no reminder \"{a[1] if len(a) > 1 else ''}\" (see --list)", file=sys.stderr); return 4
    if a[0].startswith("-"):
        print(f"remind: unknown option {a[0]}", file=sys.stderr); return 2
    if len(a) < 3:
        print("remind: need <agent> <when> <text>", file=sys.stderr); return 2
    return add(a[0], a[1], " ".join(a[2:]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
