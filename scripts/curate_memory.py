#!/usr/bin/env python3
"""Memory health check — finds duplicates, orphans, broken links, stale facts.

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

MEMORY_DIR = pathlib.Path(
    os.environ.get(
        "CLAUDE_MEMORY_DIR",
        os.path.expanduser("~/.claude/memory"),
    )
)

findings = []


def check_index_exists():
    idx = MEMORY_DIR / "MEMORY.md"
    if not idx.exists():
        findings.append(f"MEMORY.md missing at {idx}")
        return None
    return idx.read_text(encoding="utf-8")


def check_orphans(index_text):
    """Files in memory/ not referenced from MEMORY.md."""
    referenced = set(re.findall(r"\[[^\]]+\]\(([^)]+\.md)\)", index_text))
    referenced |= set(re.findall(r"\[\[([^\]]+)\]\]", index_text))
    for f in MEMORY_DIR.glob("*.md"):
        if f.name == "MEMORY.md":
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
    """Find [[name]] wikilinks that don't resolve to any memory file."""
    valid_names = {f.stem for f in MEMORY_DIR.glob("*.md")}
    for f in MEMORY_DIR.glob("*.md"):
        text = f.read_text(encoding="utf-8")
        for ref in re.findall(r"\[\[([^\]]+)\]\]", text):
            ref_name = ref.split("#")[0].split("|")[0].strip()
            if ref_name and ref_name not in valid_names:
                findings.append(f"unresolved wikilink in {f.name}: [[{ref}]]")


def main():
    if not MEMORY_DIR.exists():
        print(f"memory dir not found: {MEMORY_DIR}", file=sys.stderr)
        sys.exit(0)
    idx_text = check_index_exists()
    if idx_text is not None:
        check_orphans(idx_text)
        check_broken_links(idx_text)
    check_wikilinks()

    if not findings:
        sys.exit(0)

    print("Memory curation findings:\n")
    for f in findings:
        print(f"  - {f}")
    print(f"\nTotal: {len(findings)} issue(s). Review and clean up.")
    sys.exit(1)


if __name__ == "__main__":
    main()
