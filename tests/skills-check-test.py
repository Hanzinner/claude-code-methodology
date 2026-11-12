#!/usr/bin/env python3
"""skills-check: validates every skills/*/SKILL.md in the repo.
Checks: frontmatter parses, has name (= folder) + description, referenced repo files exist
(scripts/, hooks/, lib/, bin/ paths, also via $CLAUDE_METHODOLOGY_DIR), no Cyrillic, no personal/project names.
SKILLS_DIR=<path> overrides the skills directory. Read-only."""
import glob, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..")
SKILLS = os.environ.get("SKILLS_DIR") or os.path.join(ROOT, "skills")
# paths under these roots must exist in the repo; anything else (memory/, ~/.claude/skills, /tmp) is a runtime dir
REPO_DIRS = ("scripts", "hooks", "lib", "bin")
FORBIDDEN = ["Marko", "Hanz", "Olha", "Patsy", "Scalpel", "Appflame", "Trofeo", "Danylo",
             "HanzOS", "RoxBid", "Vertical", "Mercury", "REW", "Scout", "Pasikov"]
CYR = re.compile(r"[Ѐ-ӿ]")
PATH = re.compile(r"(?:\$\{?CLAUDE_METHODOLOGY_DIR(?::-[^}]*)?\}?|\$CCM_CLAUDE_DIR|~/\.claude)?/?((?:%s)/[\w.\-]+\.(?:py|sh|md|json))" % "|".join(REPO_DIRS))

ok = fail = 0
def check(name, cond, msg=""):
    global ok, fail
    if cond: ok += 1
    else:
        fail += 1
        print("FAIL %s: %s" % (name, msg))

files = sorted(glob.glob(os.path.join(SKILLS, "*", "SKILL.md")))
check("any-skills", bool(files), "no SKILL.md found in %s" % SKILLS)
for f in files:
    folder = os.path.basename(os.path.dirname(f))
    text = open(f, encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    check(folder + ":frontmatter", bool(m), "no frontmatter block")
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1); fm[k.strip()] = v.strip()
    check(folder + ":name", fm.get("name") == folder, "name %r != folder" % fm.get("name"))
    check(folder + ":description", len(fm.get("description", "")) > 40, "missing/short description")
    check(folder + ":cyrillic", not CYR.search(text), "Cyrillic text: %s" % (CYR.search(text) or [""])[0])
    for w in FORBIDDEN:
        check(folder + ":name-" + w, not re.search(r"\b%s\b" % re.escape(w), text), "contains %r" % w)
    for rel in sorted(set(PATH.findall(text))):
        check(folder + ":ref-" + rel, os.path.exists(os.path.join(ROOT, rel)), "%s not in repo" % rel)

print("skills-check: %d pass, %d fail (%d skills)" % (ok, fail, len(files)))
sys.exit(1 if fail else 0)
