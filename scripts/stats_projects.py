#!/usr/bin/env python3
"""stats_projects.py - an overview of projects: epics and stories read from each project's ROADMAP.md -> <stats>/projects.json.

State is NOT kept here - it is read from the roadmap that the project's own lead agent writes:
  `## EPIC N - title ✅|🔄|⏳|🔮`   and   `- ✅ **[EN.SM] story title** `M·90` · ... Done when: ...`
(`## ЕПІК N` and `Готово коли:` are accepted too). A story without a mark = not started. Epic order = the file's order
(the human sets it). A project on pause carries a line `## ⏸ PAUSE since <date> - <why>` under its title (the Ukrainian
"ПАУЗА" is accepted).
Marks: ✅ done · 🔄 in progress · ⏸ paused · ⛔ reset · ⏳ waiting · 🔮 far · 🛑 debt.
Projects = every `ROADMAP.md` of the folders matching CCM_PROJECTS_GLOB (default `Project-*`) in the workspace.
Cron (every 15 min):  */15 * * * * python3 ~/.claude/scripts/stats_projects.py
Settings: STATS_DIR (default ~/.claude/stats) · CCM_WORKSPACE · CCM_PROJECTS_GLOB · CCM_TIMEZONE. rc 1 if a roadmap
could not be parsed (a project without data must be visible, not silently absent).
"""
import glob, json, os, re, subprocess, sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

ROOT = conf("CCM_WORKSPACE", os.path.expanduser("~/claude-projects"))
STATS = os.path.expanduser(os.environ.get("STATS_DIR", "~/.claude/stats"))
OUT = os.path.join(STATS, "projects.json")
_tz = conf("CCM_TIMEZONE", "")
TZ = ZoneInfo(_tz) if _tz else datetime.now().astimezone().tzinfo
MARKS = "✅🔄⏸⛔⏳🔮🛑"
EPIC = re.compile(r"^##\s+(?:EPIC|ЕПІК)\s+(\d+)\s*[—–-]\s*(.+?)\s*$", re.I)
STORY = re.compile(r"^\s*[-*]\s*(?P<pre>.*?)\*\*\[(?P<id>E(?P<ep>\d+)\.[A-Z]\d+[a-z]?)\]\s*(?P<title>.+?)\*\*(?P<rest>.*)$")
SIZE = re.compile(r"`((?:XS|S|M|L|XL)\s*·\s*\d{1,3})`")
DOD = re.compile(r"(?:Done when|Готово коли):\s*(.+?)(?:\s*\*\(|$)")
STORY_PREFIX = re.compile(r"^(?:STORY|СТОРІ):\s*")


def mark_of(s):
    for ch in s:
        if ch in MARKS:
            return ch
    return ""


def clean(t):
    t = STORY_PREFIX.sub("", t.strip())
    t = re.sub(f"[{MARKS}]", "", t)
    return re.sub(r"\s+", " ", t).strip(" ·-—")


def parse(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    north, epics, cur, pause = "", [], None, ""
    for i, line in enumerate(lines):
        if line.startswith("## ") and ("North" in line or "Північн" in line) and not north:
            for nxt in lines[i + 1:i + 8]:
                if nxt.strip() and not nxt.startswith("#"):
                    north = re.sub(r"\*\*|`", "", nxt.strip(" >-*"))
                    break
            continue
        pm = re.match(r"^#+\s*⏸\s*(?:PAUSE|ПАУЗА)\s*(.*)$", line)
        if pm and not pause:
            pause = re.sub(r"\*\*|`", "", pm.group(1)).strip(" —-·") or "paused"
            continue
        m = EPIC.match(line)
        if m:
            head = m.group(2)
            par = re.search(r"\(([^)]*)\)\s*$", head)
            note = par.group(1) if par else next((k for k in ("postponed", "debt", "load-bearing", "відкладено", "БОРГ", "НЕСУЧИЙ") if k in head), "")
            title = re.sub(r"\s*\([^)]*\)\s*$", "", head)
            title = re.sub(r"\s+(НЕСУЧИЙ|відкладено|postponed|load-bearing).*$", "", title)
            title = re.sub(r"🔴.*$", "", title)
            cur = {"id": "E" + m.group(1), "title": clean(title), "mark": mark_of(head) or ("🛑" if "🔴" in head else ""),
                   "note": note, "stories": []}
            epics.append(cur)
            continue
        s = STORY.match(line)
        if s:                                      # to an epic by the number in the id: a story may sit outside its epic's section
            cur = next((e for e in epics if e["id"] == "E" + s.group("ep")), None)
            if cur is None:
                cur = {"id": "E" + s.group("ep"), "title": "?", "mark": "", "note": "", "stories": []}
                epics.append(cur)
            rest = s.group("rest")
            mk = mark_of(s.group("pre")) or ("✅" if "**DONE**" in rest else "")
            title = clean(s.group("title"))
            if not title:                          # "**[E2.S5]** title ..." - the title is outside the bold
                title = clean(re.split(r"\s·\s|`|Done when|Готово коли", rest.lstrip(" *"))[0])[:160]
            sz = SIZE.search(rest)
            dod = DOD.search(rest)
            cur["stories"].append({"id": s.group("id"), "title": title, "mark": mk,
                                   "size": sz.group(1).replace(" ", "") if sz else "",
                                   "dod": re.sub(r"\*\*|`", "", dod.group(1)).strip()[:400] if dod else ""})
    return north, epics, pause


def last_change(path):
    try:
        out = subprocess.run(["git", "-C", os.path.dirname(path), "log", "-1", "--format=%ct", "--", os.path.basename(path)],
                             capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    return max(int(out or 0), int(os.path.getmtime(path)))


def main():
    data = {"generated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"), "projects": [], "errors": []}
    pat = conf("CCM_PROJECTS_GLOB", "Project-*")
    for path in sorted(glob.glob(os.path.join(ROOT, pat, "ROADMAP.md"))):
        pdir = os.path.basename(os.path.dirname(path))
        name = re.sub(r"^Project-", "", pdir)
        try:
            north, epics, pause = parse(path)
        except Exception as e:                      # do not swallow: a project without data must be visible
            data["errors"].append(f"{name}: {type(e).__name__}: {e}")
            continue
        if not epics:
            data["errors"].append(f"{name}: no '## EPIC N -' found in {pdir}/ROADMAP.md")
        ts = last_change(path)
        data["projects"].append({"id": name.lower(), "name": name, "north": north[:300], "roadmap": f"{pdir}/ROADMAP.md",
                                 "pause": pause, "updated": datetime.fromtimestamp(ts, TZ).strftime("%Y-%m-%d %H:%M"),
                                 "updated_ts": ts, "epics": epics})
    os.makedirs(STATS, exist_ok=True)
    tmp = OUT + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, OUT)
    for p in data["projects"]:
        st = [s for e in p["epics"] for s in e["stories"]]
        print(f"{p['name']}: epics {len(p['epics'])}, stories {len(st)} (done {sum(s['mark'] == '✅' for s in st)}, in progress {sum(s['mark'] == '🔄' for s in st)})")
    for e in data["errors"]:
        print("ERROR:", e)
    return 1 if data["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
