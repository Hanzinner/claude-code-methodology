#!/usr/bin/env python3
"""story_status.py <project> <S-code> - the state of a story computed from SOURCES, never from memory.
Prints: the ROADMAP line - its blockers from BLOCKERS.md (open/cleared) - mentions in the TODO files and inboxes of the
project's agents (open items) - commits with the code in the message or in the changed text - code files carrying the code.
<project>: "Bid" or "Project-Bid" (folder matching CCM_PROJECTS_GLOB). Paste the output into the report;
status-guard lets a state report through only after such a run in the same turn.
Why: a coordinator reported one story's state three times from memory ("code ready" -> "not started" -> "nobody started")
while the code had been committed for days. A plan is not a fact about code.
Agents of the project are the folders <CCM_AGENTS_DIR>/<project>-* (their agent-TODO.md / human-TODO.md / inbox.md).
Config: CCM_WORKSPACE, CCM_AGENTS_DIR, CCM_PROJECTS_GLOB (NEW, default "Project-*"). Env overrides (tests): STORY_REPO."""
import glob, os, re, subprocess, sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402

REPO = os.environ.get("STORY_REPO", conf("CCM_WORKSPACE"))
AGENTS = os.environ.get("STORY_AGENTS", conf("CCM_AGENTS_DIR") if not os.environ.get("STORY_REPO") else os.path.join(REPO, "Agents"))
PREFIX = conf("CCM_PROJECTS_GLOB", "Project-").split("*")[0]


def main(a):
    if len(a) != 2:
        print(__doc__); return 2
    pn = a[0] if (a[0].startswith(PREFIX) or os.path.isdir(os.path.join(REPO, a[0]))) else PREFIX + a[0]
    pd = os.path.join(REPO, pn)
    pref = pn[len(PREFIX):] if pn.startswith(PREFIX) else pn
    code = a[1].upper().split(".")[-1]
    if not os.path.isdir(pd):
        print(f"no project {pn}"); return 4
    rx = re.compile(rf"(?<![\w.])(?:E\d+\.)?{re.escape(code)}(?!\d)")
    print(f"== {pn} {code}")
    refs = []
    try:
        for i, l in enumerate(open(os.path.join(pd, "ROADMAP.md"), encoding="utf-8"), 1):
            if rx.search(l) and re.match(r"^\s*- ", l):
                print(f"ROADMAP.md:{i}: {l.strip()[:400]}")
                m = re.search(r"(?:blockers|блокери):\s*((?:B\d+[,\s]*)+)", l, re.I)
                refs += re.findall(r"B\d+", m.group(1)) if m else []
    except OSError:
        print("no ROADMAP.md")
    bpath = os.path.join(pd, "BLOCKERS.md")
    for b in refs:
        row = next((l.strip() for l in open(bpath, encoding="utf-8")
                    if re.match(rf"^\|\s*(✅\s*)?{b}\s*\|", l)), None) if os.path.exists(bpath) else None
        print(f"  blocker {b}: " + (("CLEARED " if "✅" in row.split("|")[1] else "OPEN ") + row[:200] if row else "NOT in BLOCKERS.md"))
    print("-- open items of the project's agents:")
    n = 0
    for f in sorted(glob.glob(os.path.join(AGENTS, f"{pref}-*", "*TODO*.md")) + glob.glob(os.path.join(AGENTS, f"{pref}-*", "inbox.md"))):
        for i, l in enumerate(open(f, encoding="utf-8", errors="replace"), 1):
            if rx.search(l) and l.lstrip().startswith("- [ ]"):
                print(f"  {os.path.relpath(f, REPO)}:{i}: {l.strip()[:220]}"); n += 1
    print(f"  ({n})" if n else "  - none")
    g = lambda *x: subprocess.run(["git", "-c", "core.quotepath=off", "-C", REPO, *x], capture_output=True, text=True).stdout.strip()
    log = g("log", "--oneline", "-8", f"--grep={code}\\b", "-E", "--", pn) or "- none"
    print(f"-- commits with {code} in the message:\n{log}")
    files = g("grep", "-l", "-E", f"(^|[^A-Za-z0-9.])(E[0-9]+\\.)?{code}([^0-9]|$)", "--", f"{pn}/*.py", f"{pn}/*.js", f"{pn}/*.html", f"{pn}/*.sh", f"{pn}/*.css")
    print(f"-- code carrying {code}:\n" + ("\n".join(files.split("\n")[:15]) if files else "- none"))
    if files:
        last = g("log", "-1", "--format=%h %cd %s", "--date=format:%d.%m %H:%M", "--", *files.split("\n")[:15])
        print(f"   last commit of these files: {last}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
