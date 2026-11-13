#!/usr/bin/env python3
"""stats_adoption.py - an audit of whether the swarm's rules are actually USED, not whether a mechanism "is running".

Once a day (and by hand): per agent counts the size·priority tags in its task list (`S·45`, `M·70`...), the age of
letters in its inbox, the stuck urgent items (marked 🖐/🟥/🔴 or priority >= 90, older than a day); for the journal
(MISTAKES.md) counts the entries of the last week and those without a class / OPEN for more than 14 days.
Writes <stats>/adoption.json. Red findings go into that file ("red"); ONE letter per day goes to the agent named in
CCM_STATS_OWNER (empty = no letter) when the journal has unsorted entries.

Left out of the port (they were tied to the original machine): the coding-standard version check, the list of "coder"
agents, per-project roadmap/test/gate counters.
Cron (daily):  40 * * * * python3 ~/.claude/scripts/stats_adoption.py
Settings: STATS_DIR (default ~/.claude/stats) · CCM_AGENTS_DIR · CCM_MISTAKES (journal path; empty = <workspace>/MISTAKES.md) ·
CCM_TIMEZONE · STATS_PAUSED (see stats_orphan_docs.py: paused agents are not reported) · CCM_STATS_OWNER.
"""
import glob, json, os, re, subprocess, sys, time
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402

HOME = os.path.expanduser("~")
WS = conf("CCM_WORKSPACE", os.path.join(HOME, "claude-projects"))
AGENTS = conf("CCM_AGENTS_DIR", "") or os.path.join(WS, "Agents")
STATS = os.path.expanduser(os.environ.get("STATS_DIR", "~/.claude/stats"))
OUT = f"{STATS}/adoption.json"
MISTAKES = conf("CCM_MISTAKES", "") or os.path.join(WS, "MISTAKES.md")
PAUSED = os.environ.get("STATS_PAUSED", f"{STATS}/paused-agents.txt")
POST = os.path.join(HERE, "inbox_post.sh")
_tz = conf("CCM_TIMEZONE", "")
TZ = ZoneInfo(_tz) if _tz else datetime.now().astimezone().tzinfo
NOW = time.time()
TAG = re.compile(r"\b(XS|S|M|L|XL)\s*[·.]\s*\d{1,3}\b")
DATE = re.compile(r"\[(\d{4}-\d{2}-\d{2})(?: (\d{2}:\d{2}))?\]")
# 🖐/🟥/🔴 as a letter's mark: right after the date (+ optional time) and maybe a sender name with " · "; or priority 90-100
HOT = re.compile(r"^(?:\[[^\]]*\]\s*)+(?:[^·\n]{0,48}·\s*)?\**\s*(🖐|🟥|🔴)|\b(XS|S|M|L|XL)\s*[·.]\s*(9\d|100)\b")
NEW_HEADS = ("## New", "## Нові") if "uk" in conf("CCM_LANG_EXTRA", "") else ("## New",)


def age_days(line):
    m = DATE.search(line)
    if not m:
        return None
    try:
        t = time.mktime(time.strptime(m.group(1) + " " + (m.group(2) or "00:00"), "%Y-%m-%d %H:%M"))
    except ValueError:
        return None
    return (NOW - t) / 86400


def section(text, heads):
    for head in heads:
        i = text.find(head)
        if i >= 0:
            j = text.find("\n## ", i + len(head))
            return text[i:j if j > 0 else None]
    return ""


def read_lines(p):
    try:
        return open(p, errors="replace").read().splitlines()
    except OSError:
        return []


def is_human_todo(path):
    n = os.path.basename(path).lower()
    who = (conf("CCM_HUMAN_NAME", "") or "").lower().split()
    return "human" in n or bool(who and who[0] in n)


def main():
    agents = {}
    try:
        paused = [l.strip() for l in open(PAUSED, encoding="utf-8") if l.strip() and not l.startswith("#")]
    except OSError:
        paused = []
    is_paused = lambda n: any(n.startswith(p) for p in paused)
    for b in sorted(glob.glob(f"{AGENTS}/*/briefing.md") + glob.glob(f"{AGENTS}/*/*/briefing.md")):
        d = os.path.dirname(b)
        name = os.path.basename(d)
        if name.startswith("_"):      # templates / examples
            continue
        a = {"open": 0, "tagged": 0, "inbox_new": 0, "inbox_old3": 0, "inbox_oldest": 0.0, "hot_stale": []}
        for f in glob.glob(f"{d}/*TODO*.md"):
            if is_human_todo(f):
                continue
            for l in read_lines(f):
                if l.lstrip().startswith("- [ ]"):
                    a["open"] += 1
                    a["tagged"] += bool(TAG.search(l))
        ib = f"{d}/inbox.md"
        if os.path.isfile(ib):
            for l in section(open(ib, errors="replace").read(), NEW_HEADS).split("\n"):
                if not l.startswith("- [ ]"):
                    continue
                a["inbox_new"] += 1
                ag = age_days(l)
                if ag is None:
                    continue
                a["inbox_oldest"] = max(a["inbox_oldest"], round(ag, 1))
                if ag >= 3:
                    a["inbox_old3"] += 1
                if ag >= 1 and HOT.search(l[6:].strip()):
                    a["hot_stale"].append({"age": round(ag, 1), "text": re.sub(r"\s+", " ", l[6:])[:140]})
        agents[name] = a

    # the journal: reviewed every day, not once a week - entries without a class / OPEN for more than 14 days
    mist = open(MISTAKES, errors="replace").read() if os.path.isfile(MISTAKES) else ""
    full = re.findall(r"^## (\d{4}-\d{2}-\d{2}[^\n]*)", mist, re.M)
    recent = [h for h in full if (NOW - time.mktime(time.strptime(h[:10], "%Y-%m-%d"))) / 86400 <= 7]
    mistakes = {"week": len(recent), "week_with_class": sum("[class" in h or "[repeat" in h for h in recent)}
    untagged, stale = [], []
    for e in re.split(r"\n(?=## 20\d\d-\d\d-\d\d)", mist)[1:]:
        h = e.split("\n")[0][3:]
        age = (NOW - time.mktime(time.strptime(h[:10], "%Y-%m-%d"))) / 86400
        st = re.search(r"\*\*Status:?\*\*:?\s*([A-Za-z]+)", e)
        if "[class" not in h and "[repeat" not in h and "[one-off]" not in h and 1 <= age <= 30:
            untagged.append(h[:90])
        if st and st.group(1).upper() == "OPEN" and age > 14:
            rv = re.search(r"reviewed (\d{4}-\d{2}-\d{2})", e)   # an OPEN entry reviewed within 14 days is not "unsorted"
            if rv and (NOW - time.mktime(time.strptime(rv.group(1), "%Y-%m-%d"))) / 86400 <= 14:
                continue
            stale.append(h[:90])
    mistakes.update({"untagged": len(untagged), "stale_open": len(stale)})

    red = []
    for n, a in agents.items():
        if is_paused(n):
            continue
        for h in a["hot_stale"]:
            red.append(f"urgent item hangs {h['age']:.0f} d in {n}: {h['text'][:90]}")
        if a["inbox_old3"] >= 10:
            red.append(f"{n}: {a['inbox_old3']} inbox letters older than 3 days")
    tot_open = sum(a["open"] for a in agents.values())
    tot_tag = sum(a["tagged"] for a in agents.values())
    data = {"generated": datetime.fromtimestamp(NOW, TZ).strftime("%Y-%m-%d %H:%M"),
            "summary": {"agents": len(agents), "open": tot_open, "tagged": tot_tag,
                        "tagged_pct": round(tot_tag * 100 / max(tot_open, 1), 1),
                        "inbox_old3": sum(a["inbox_old3"] for a in agents.values()), "paused": paused, **mistakes},
            "agents": agents, "red": red}
    os.makedirs(STATS, exist_ok=True)
    tmp = OUT + f".{os.getpid()}.tmp"
    json.dump(data, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, OUT)

    # a letter to the owner once a day if the journal has unsorted entries (dedupe by date in a state file)
    today = datetime.fromtimestamp(NOW, TZ).strftime("%Y-%m-%d")
    stamp = f"{STATS}/.adoption-mistakes-letter"
    last = open(stamp).read().strip() if os.path.isfile(stamp) else ""
    owner = conf("CCM_STATS_OWNER", "")
    if owner and (untagged or stale) and last != today:
        txt = (f"adoption - the mistakes journal has unsorted entries: without a class {len(untagged)}"
               + (f" (e.g. {untagged[0][:70]})" if untagged else "")
               + f" · OPEN older than 14 days {len(stale)} - set a class / check whether a mechanism already exists (MECHANIZED/ACCEPTED)")
        try:
            rc = subprocess.run([POST, owner, txt], capture_output=True, timeout=30).returncode
        except (OSError, subprocess.TimeoutExpired):
            rc = 1
        if rc == 0:
            open(stamp, "w").write(today)
        else:
            print(f"letter to {owner} did not go: rc={rc}")
    hot = [r for r in red if r.startswith("urgent")]
    print(f"ok: {len(agents)} agents, red {len(red)} (urgent {len(hot)}); journal: no class {len(untagged)}, OPEN>14d {len(stale)} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
