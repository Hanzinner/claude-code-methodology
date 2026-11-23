#!/usr/bin/env python3
"""lib/ws_docs.py: the six shared documents in the workspace. A temp copy of the repo's docs, a temp workspace and stamp
dir. Checks the link rewrite, no broken link, that hooks/proof-guard.py sees the four rules (not the playbook, a journal), and the update scheme: untouched
-> replaced, edited by the human -> kept + .new + .changes, merged -> quiet, an old raw copy -> replaced, --dry-run ->
nothing written. WSD=path tests another copy. Last line: workspace-docs-test: N pass, M fail."""
import os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # the repo, or an install dir (<claude dir>/tests/..)
WSD = os.environ.get("WSD") or str(HERE / "lib" / "ws_docs.py")


def find_repo():
    """the clone with docs/: CCM_REPO_DIR (install.sh sets it when it runs the tests), this folder, or the install stamp"""
    cands = [os.environ.get("CCM_REPO_DIR", ""), str(HERE)]
    try:
        cands += [l[5:].strip() for l in open(HERE / ".methodology-installed" / "source") if l.startswith("repo=")]
    except OSError:
        pass
    return next((Path(c) for c in cands if c and (Path(c) / "docs" / "coding-standard.md").is_file()), None)


REPO = find_repo()
if REPO is None:
    print("workspace-docs-test: SKIP (no clone of the repo found: set CCM_REPO_DIR=<clone> - nothing was tested)")
    sys.exit(0)
T = Path(tempfile.mkdtemp(prefix="wsdocs-test-")).resolve()   # ws_docs.py writes realpath(repo); a macOS temp dir is a link
R, WS, ST = T / "repo", T / "ws", T / "stamp"
for d in ("docs", "code-pitfalls", "swarm-template"):
    shutil.copytree(REPO / d, R / d)
RULES = ("CODING-STANDARD.md", "PROJECT-WORK.md", "DEV-METHODOLOGY.md", "PO-INTERFACE.md")
NAMES = RULES + ("WEB-PLAYBOOK.md", "DOC-SLOP.md")
passed = failed = 0


def ok(name, cond, detail=""):
    global passed, failed
    if cond: passed += 1
    else: failed += 1; print("FAIL:", name, str(detail)[:400])


def run(*a):
    r = subprocess.run([sys.executable, WSD, *a], capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout + r.stderr


def inst(*extra):
    return run("install", str(R), str(WS), str(ST), *extra)


rc, out = run("render", str(R), str(R / "docs/project-work.md"))
ok("1 between the four -> the workspace names", "](CODING-STANDARD.md" in out and "](PO-INTERFACE.md" in out and "](coding-standard.md" not in out, out[:200])
ok("2 other repo files -> absolute path in the clone", f"]({R}/docs/mistakes-journal.md)" in out and f"]({R}/code-pitfalls/README.md)" in out)
ok("3 the text 'docs/po-interface.md' -> PO-INTERFACE.md", "docs/po-interface.md" not in out and "docs/project-work.md" not in out)

rc, out = inst()
ok("4 fresh install -> all six written", rc == 0 and all((WS / n).is_file() for n in NAMES) and "6 added" in out, out)
rc, out = run("links", str(WS)); ok("5 no broken link in any of the six", rc == 0, out)
pg = subprocess.run([sys.executable, "-c", "import importlib.util,sys; s=importlib.util.spec_from_file_location('pg', sys.argv[1]); "
                     "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('\\n'.join(m.SHARED_DOCS))", str(HERE / "hooks/proof-guard.py")],
                    capture_output=True, text=True, timeout=30, env={**os.environ, "CCM_WORKSPACE": str(WS), "CLAUDE_METHODOLOGY_CONF": str(T / "none"), "HOME": str(T / "home")})
seen = pg.stdout.split()
ok("6 proof-guard's shared documents are these four files, all present", all(str(WS / n) in seen and (WS / n).is_file() for n in RULES), (pg.stdout, pg.stderr[-300:]))
ok("6b the playbook is a journal agents append to, not a rule -> not in proof-guard's list", str(WS / "WEB-PLAYBOOK.md") not in seen, pg.stdout)
pwk = (WS / "PROJECT-WORK.md").read_text(encoding="utf-8")
ok("6c project-work's link to hall-of-shame-docs.md -> DOC-SLOP.md in the workspace", "](DOC-SLOP.md)" in pwk and "hall-of-shame-docs" not in pwk,
   [l for l in pwk.splitlines() if "SLOP" in l or "hall-of" in l][:3])
sw = (REPO / "swarm-template" / "MISTAKES.md").read_text(encoding="utf-8")
ok("6d swarm-template/MISTAKES.md (copied raw into the workspace) names DOC-SLOP.md, not the repo path", "`DOC-SLOP.md`" in sw and "hall-of-shame-docs" not in sw)

rc, out = inst(); ok("7 re-run, nothing changed -> 0 added 0 updated, no .new", "0 added, 0 updated" in out and not list(WS.glob("*.new")), out)

# a new version of ours; CODING-STANDARD untouched by the human, PROJECT-WORK edited by the human
with open(R / "docs/coding-standard.md", "a") as f: f.write("\nNEW RULE A\n")
with open(R / "docs/project-work.md", "a") as f: f.write("\nNEW RULE B\n")
with open(WS / "PROJECT-WORK.md", "a") as f: f.write("\nMY OWN NOTE\n")
rc, out = inst()
ok("8 untouched file -> replaced by the new version", "NEW RULE A" in (WS / "CODING-STANDARD.md").read_text(), out)
pw = (WS / "PROJECT-WORK.md").read_text()
ok("9 edited file -> kept as is (own note, no new rule)", "MY OWN NOTE" in pw and "NEW RULE B" not in pw, out)
ch = (WS / "PROJECT-WORK.md.changes").read_text() if (WS / "PROJECT-WORK.md.changes").exists() else ""
ok("10 ... ours next to it as .new, .changes = only what changed in ours", (WS / "PROJECT-WORK.md.new").is_file() and "+NEW RULE B" in ch
   and len([l for l in ch.splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]) <= 3, ch[:300])
ok("11 the warning names the file and the merge command", "PROJECT-WORK.md is yours" in out and f"mv {WS}/PROJECT-WORK.md.new {ST}/ws-PROJECT-WORK.md.base" in out, out)
# the human merges (adds the rule) and marks it merged
with open(WS / "PROJECT-WORK.md", "a") as f: f.write("\nNEW RULE B\n")
os.replace(WS / "PROJECT-WORK.md.new", ST / "ws-PROJECT-WORK.md.base"); (WS / "PROJECT-WORK.md.changes").unlink()
rc, out = inst(); ok("12 after the merge, same version -> quiet, no .new", not (WS / "PROJECT-WORK.md.new").exists() and "kept as yours" not in out, out)
with open(R / "docs/project-work.md", "a") as f: f.write("\nNEW RULE C\n")
rc, out = inst(); ch = (WS / "PROJECT-WORK.md.changes").read_text()
ok("13 next version -> .changes holds only NEW RULE C, not B again", "+NEW RULE C" in ch and "+NEW RULE B" not in ch, ch[:300])

# an older installer copied a docs file raw, with no stamps. Pick one whose workspace version differs from the raw text
# (has links to rewrite) - the docs change, and a test bound to one file's links went red when that file lost them.
raw_src = next((s for s in ("coding-standard", "dev-methodology", "po-interface")
                if run("render", str(R), str(R / f"docs/{s}.md"))[1] != (R / f"docs/{s}.md").read_text()), None)
if raw_src:
    name = {"coding-standard": "CODING-STANDARD.md", "dev-methodology": "DEV-METHODOLOGY.md", "po-interface": "PO-INTERFACE.md"}[raw_src]
    shutil.rmtree(ST); (WS / name).write_text((R / f"docs/{raw_src}.md").read_text())
    rc, out = inst()
    ok(f"14 an untouched raw copy from an older installer ({name}) -> replaced silently by the workspace version",
       (WS / name).read_text() == run("render", str(R), str(R / f"docs/{raw_src}.md"))[1] and not (WS / f"{name}.new").exists(), out)
else:
    ok("14 at least one of the documents has links to rewrite (else case 14 tests nothing)", False)

shutil.rmtree(WS); rc, out = inst("--dry-run")
ok("15 --dry-run -> nothing written", not any((WS / n).exists() for n in NAMES), out)

shutil.rmtree(T, ignore_errors=True)
print(f"workspace-docs-test: {passed} pass, {failed} fail")
sys.exit(1 if failed else 0)
