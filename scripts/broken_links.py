#!/usr/bin/env python3
"""broken_links.py [--all] - sweep of broken `](...md)` links over the workspace's markdown corpus.
Corpus = `git ls-files *.md` + new unignored files (or a plain walk when the workspace is not a git repo).
Each link is resolved from the folder of its file; a candidate = the only file with the same basename (the file was
most likely moved). Code blocks and inline code are skipped (an example `[T](file.md)` is not a link).
Deliberate non-links are skipped unless --all: folders listed in CCM_BROKEN_LINKS_SKIP (comma-separated, relative to the
workspace; default empty). [[wiki]] links are not checked: a dangling [[slug]] in memory is by design.
Read-only. Workspace: CCM_WORKSPACE. Test: tests/broken-links-test.py"""
import collections, os, re, subprocess, sys
from urllib.parse import unquote

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf

REPO = conf("CCM_WORKSPACE")
SKIP = tuple(s.strip() for s in conf("CCM_BROKEN_LINKS_SKIP", "").split(",") if s.strip())
LINK = re.compile(r"\]\((<[^>\n]*>|[^)\s]+)")


def corpus():
    out = set()
    for extra in ([], ["-o", "--exclude-standard"]):
        r = subprocess.run(["git", "-c", "safe.directory=*", "-C", REPO, "ls-files", "-z", *extra, "--", "*.md"],
                           capture_output=True, text=True)
        out |= {p for p in r.stdout.split("\0") if p}
    if not out:   # not a git repo: plain walk
        for d, dirs, files in os.walk(REPO):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            out |= {os.path.relpath(os.path.join(d, f), REPO) for f in files if f.endswith(".md")}
    return sorted(p for p in out if os.path.isfile(os.path.join(REPO, p)))


def main():
    show_all = "--all" in sys.argv
    fs = corpus()
    bybase = collections.defaultdict(list)
    for f in fs:
        bybase[os.path.basename(f).lower()].append(f)
    fixable, orphan = [], []
    for f in fs:
        if not show_all and SKIP and f.startswith(SKIP):
            continue
        try:
            t = open(os.path.join(REPO, f), encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        t = re.sub(r"```.*?```", "", t, flags=re.S)
        t = re.sub(r"`[^`\n]+`", "", t)
        for m in LINK.finditer(t):
            x = m.group(1).strip("<>").partition("#")[0]
            if not x or re.match(r"^[a-z][a-z0-9+.-]*:", x, re.I) or not x.lower().endswith(".md"):
                continue
            x = unquote(x)
            p = os.path.normpath(os.path.expanduser(x) if x.startswith(("/", "~")) else os.path.join(REPO, os.path.dirname(f), x))
            if os.path.exists(p):
                continue
            cand = bybase.get(os.path.basename(p).lower(), [])
            if len(cand) == 1:
                good = os.path.relpath(os.path.join(REPO, cand[0]), os.path.join(REPO, os.path.dirname(f)))
                fixable.append(f"{f} :: {m.group(1)} -> {good}")
            else:
                orphan.append(f"{f} :: {m.group(1)}  [{len(cand)} candidates]")
    print(f"files: {len(fs)}; broken: {len(fixable) + len(orphan)} "
          f"(with a ready fix: {len(fixable)}, no target/ambiguous: {len(orphan)})")
    if fixable:
        print("== fix available (path relative to the file's folder):")
        print("\n".join("  " + l for l in fixable))
    if orphan:
        print("== no target / ambiguous:")
        print("\n".join("  " + l for l in orphan))


if __name__ == "__main__":
    main()
