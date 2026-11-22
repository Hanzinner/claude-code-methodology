#!/usr/bin/env python3
"""Memory health check — orphans, broken index links, unresolved wikilinks, frontmatter problems, files untouched for
a long time, and possibly-related groups (same name prefix). Read-only: it reports, the agent reviews and acts.

Run weekly via the SessionStart hook (`memory-curation-check.sh`). Exit code:
  0 — memory is clean (no report emitted)
  1 — findings — report on stdout, hook injects into session context

This is a starter implementation. Extend the heuristics below as your
memory grows. Common things worth checking:

  - Duplicate entries (same fact written into two files)
  - Files referenced from MEMORY.md that no longer exist
  - Files in memory/ that are NOT referenced from MEMORY.md (orphans)
  - Wikilinks `[[name]]` that don't resolve
  - Memories tagged with a date older than N months and not touched since
  - Files whose `name:` frontmatter doesn't match the filename
"""
import os
import re
import sys
import pathlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "lib"))
try:
    from ccm_conf import conf   # CCM_MEMORY_DIR: autoMemoryDirectory in settings.json, the folder Claude's auto memory uses
    _mem = conf("CCM_MEMORY_DIR", "")
except ImportError:
    _mem = ""
MEMORY_DIR = pathlib.Path(_mem or os.environ.get("CLAUDE_MEMORY_DIR") or os.path.expanduser("~/.claude/memory"))

STALE_DAYS = int(os.environ.get("MEMORY_STALE_DAYS") or 60)
VALID_TYPES = {"user", "feedback", "project", "reference"}
# Not memory: the index and the folder's own "how to write memory here" (README.md, installed from memory-template/).
# Top level only (the checks below glob the top level): a README.md in a subfolder is not exempt.
NOT_MEMORY = ("MEMORY.md", "README.md")
SKIP = NOT_MEMORY + ("feedback-index.md",)
findings = []


def strip_comments(text):
    """Drop <!-- ... --> (also multi-line, also an unclosed one to the end) before reading links: the template's
    MEMORY.md shows example entries inside comments, and a commented-out line is not in the index."""
    return re.sub(r"<!--.*?(?:-->|\Z)", "", text, flags=re.S)


def check_index_exists():
    idx = MEMORY_DIR / "MEMORY.md"
    if not idx.exists():
        findings.append(f"MEMORY.md missing at {idx}")
        return None
    return strip_comments(idx.read_text(encoding="utf-8"))


def check_orphans(index_text):
    """Files in memory/ not referenced from MEMORY.md."""
    referenced = set(re.findall(r"\[[^\]]+\]\(([^)]+\.md)\)", index_text))
    referenced |= set(re.findall(r"\[\[([^\]]+)\]\]", index_text))
    for f in MEMORY_DIR.glob("*.md"):
        if f.name in NOT_MEMORY:
            continue
        if f.name not in referenced and f.stem not in referenced:
            findings.append(f"orphan: {f.name} (not linked from MEMORY.md)")


def check_broken_links(index_text):
    """References from MEMORY.md to files that no longer exist."""
    for path in re.findall(r"\[[^\]]+\]\(([^)]+\.md)\)", index_text):
        if path.startswith(("http://", "https://")):
            continue
        target = (MEMORY_DIR / path).resolve()
        if not target.exists():
            findings.append(f"broken link in MEMORY.md: {path}")


def check_wikilinks():
    """Find [[name]] wikilinks that resolve neither to a file name nor to a `name:` slug."""
    valid_names = {f.stem for f in MEMORY_DIR.glob("*.md")}
    for f in MEMORY_DIR.glob("*.md"):
        m = re.search(r"^name:\s*(.+?)\s*$", f.read_text(encoding="utf-8"), re.M)
        if m:
            valid_names.add(m.group(1).strip("\"'"))
    for f in MEMORY_DIR.glob("*.md"):
        if f.name == "README.md":   # documentation: its [[name]] is the syntax being explained
            continue
        text = strip_comments(f.read_text(encoding="utf-8"))
        for ref in re.findall(r"\[\[([^\]]+)\]\]", text):
            ref_name = ref.split("#")[0].split("|")[0].strip()
            if ref_name and ref_name not in valid_names:
                findings.append(f"unresolved wikilink in {f.name}: [[{ref}]]")


def frontmatter(text):
    """→ dict of the frontmatter's keys (nested `metadata:` keys flattened), or None when there is no frontmatter."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep:
            fm.setdefault(k.strip(), v.strip().strip("\"'"))
    return fm


def check_frontmatter():
    """name / description / type present (type may sit under metadata:), type one of the four."""
    for f in sorted(MEMORY_DIR.glob("*.md")):
        if f.name in SKIP:
            continue
        fm = frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        if fm is None:
            findings.append(f"no frontmatter: {f.name}")
            continue
        missing = [k for k in ("name", "description", "type") if not fm.get(k)]
        if missing:
            findings.append(f"frontmatter of {f.name} lacks: {', '.join(missing)}")
        elif fm["type"] not in VALID_TYPES:
            findings.append(f"frontmatter of {f.name}: unknown type '{fm['type']}' (one of {', '.join(sorted(VALID_TYPES))})")


def check_stale():
    """Untouched for STALE_DAYS — not wrong by itself; a prompt to re-check that it is still true."""
    import time
    for f in sorted(MEMORY_DIR.glob("*.md")):
        if f.name in SKIP:
            continue
        days = int((time.time() - f.stat().st_mtime) // 86400)
        if days > STALE_DAYS:
            findings.append(f"untouched {days} days: {f.name} — still true?")


def check_related():
    """Same type_topic prefix in several files — possibly one fact written twice; a human look, not an error."""
    groups = {}
    for f in MEMORY_DIR.glob("*.md"):
        if f.name in SKIP:
            continue
        parts = f.stem.split("_", 2)
        if len(parts) >= 2:
            groups.setdefault("_".join(parts[:2]), []).append(f.name)
    for key, names in sorted(groups.items()):
        if len(names) > 1:
            findings.append(f"possibly related ({key}_*): {', '.join(sorted(names))}")


def main():
    if not MEMORY_DIR.exists():
        print(f"memory dir not found: {MEMORY_DIR}", file=sys.stderr)
        sys.exit(0)
    idx_text = check_index_exists()
    if idx_text is not None:
        check_orphans(idx_text)
        check_broken_links(idx_text)
    check_wikilinks()
    check_frontmatter()
    check_stale()
    check_related()

    if not findings:
        sys.exit(0)

    print("Memory curation findings:\n")
    for f in findings:
        print(f"  - {f}")
    print(f"\nTotal: {len(findings)} issue(s). Review and clean up.")
    sys.exit(1)


if __name__ == "__main__":
    main()
