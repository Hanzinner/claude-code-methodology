#!/usr/bin/env python3
"""project_drift.py - nightly watchman: does every project folder with code sit under the mechanisms, so that a project
that skipped new_project.sh is visible on day one. For each project: does release.toml exist and parse? is there a
gate command? did the releaser run in the last DRIFT_DAYS days and was the last result green?
Prints red lines, writes <state>/drift.json (for a dashboard). Projects listed in the paused-projects file stay quiet.
exit: 0 all good · 1 there are red projects · 3 could not measure (zero projects with code).
Settings: CCM_WORKSPACE, CCM_PROJECTS_GLOB (default Project-*), CCM_RELEASER_STATE (default /var/lib/ccm-release),
CCM_PAUSED_PROJECTS (file, one project per line; default <agents dir>/paused-projects.txt), CCM_DRIFT_DAYS (default 7).
Test: tests/project-drift-test.sh
"""
import glob, json, os, sys, time, tomllib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf

REPO = conf("CCM_WORKSPACE")
GLOB = conf("CCM_PROJECTS_GLOB", "Project-*")
PREFIX = GLOB.split("*")[0]
STATE = conf("CCM_RELEASER_STATE", "/var/lib/ccm-release")
PAUSED = conf("CCM_PAUSED_PROJECTS", os.path.join(conf("CCM_AGENTS_DIR"), "paused-projects.txt"))
DAYS = int(conf("CCM_DRIFT_DAYS", "7"))
CODE = (".py", ".js", ".ts", ".rs", ".sh", ".go", ".html")
SKIP = {".git", "node_modules", ".venv", "__pycache__", "target"}


def has_code(d):
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in SKIP]
        if any(f.endswith(CODE) for f in files):
            return True
    return False


def problems(d):
    name = os.path.basename(d)
    if not os.path.exists(os.path.join(d, ".git")):
        return ["no repo of its own: the releaser cannot attach"]
    try:
        with open(os.path.join(d, "release.toml"), "rb") as f:
            c = tomllib.load(f)
    except FileNotFoundError:
        return ["no release.toml: the releaser does not know this project"]
    except (OSError, ValueError) as e:
        return [f"release.toml does not parse: {e}"]
    if not c.get("test"):
        return ["release.toml has no gate command"]
    try:
        s = json.load(open(os.path.join(STATE, f"{name}.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return ["the releaser has not run yet"]
    age = (time.time() - s.get("ts", 0)) / 86400
    out = [f"last run {age:.0f} days ago"] if age > DAYS else []
    if s.get("result") != "green":
        out.append(f"last result {s.get('result')}: {str(s.get('detail', ''))[:120]}")
    return out


def main():
    try:
        paused = {l.strip() for l in open(PAUSED, encoding="utf-8") if l.strip() and not l.startswith("#")}
    except OSError:
        paused = set()
    dirs = [d for d in sorted(glob.glob(os.path.join(REPO, GLOB))) if os.path.isdir(d)]
    seen, red = 0, {}
    for d in dirs:
        name = os.path.basename(d)
        if name in paused or name[len(PREFIX):] in paused or not has_code(d):
            continue
        seen += 1
        p = problems(d)
        if p:
            red[name] = p
    if not seen:
        print("no projects with code found: the check itself is broken"); return 3
    try:
        os.makedirs(STATE, exist_ok=True)
        tmp = f"{STATE}/drift.json.tmp"
        json.dump({"at": time.strftime("%F %H:%M"), "checked": seen, "red": red}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.chmod(tmp, 0o644); os.replace(tmp, f"{STATE}/drift.json")
    except OSError as e:
        print(f"state not written: {e}")
    for n, p in red.items():
        print(f"RED {n}: {'; '.join(p)}")
    print(f"projects checked {seen}, red {len(red)}")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
