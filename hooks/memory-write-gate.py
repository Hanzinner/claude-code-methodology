#!/usr/bin/env python3
"""Memory-write gate — against a memory-poisoning cascade.

PreToolUse on Write|Edit: a file under the memory dir must carry two frontmatter
fields — metadata.source (where the fact came from) and metadata.verified
(yes|inferred|unverified). Missing → BLOCK with a hint.

⚠ Deliberately fail-CLOSED — the exception to the usual fail-open rule (see
hook-safe.sh). Better to refuse a write than to poison memory with an
unattributed guess that later hardens into a "fact".

Exempt: episodic/ (a dated log), the MEMORY.md index, feedback-index.md, archive/.
A file that ALREADY has the fields on disk (editing an old one) passes — the
friction is one-time, at creation.

Config: CLAUDE_MEMORY_DIR (default ~/.claude/memory)
"""
import json, os, re, sys

MEM = os.path.realpath(os.environ.get("CLAUDE_MEMORY_DIR",
                                      os.path.expanduser("~/.claude/memory"))) + "/"
SKIP_DIRS = ("episodic/", "archive/")            # top-level folders, by prefix
SKIP_FILES = ("MEMORY.md", "feedback-index.md")  # top-level files, exact name


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": reason}}, ensure_ascii=False))
    sys.exit(0)


def has_fields(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return False
    fm = m.group(1)
    return bool(re.search(r"^\s*source:\s*[\"']?[^\s\"']", fm, re.M)) and \
           bool(re.search(r"^\s*verified:\s*[\"']?(yes|inferred|unverified)\b", fm, re.M))


try:
    d = json.load(sys.stdin)
    tool = d.get("tool_name", "")
    ti = d.get("tool_input") or {}
    path = ti.get("file_path", "")
    rp = os.path.realpath(path) if path else ""
    rel = rp[len(MEM):]   # MEM ends with "/"
    # Prefix / exact match, never a substring: "project_archive/x.md" is NOT archive/.
    if not rp.startswith(MEM) or not rp.endswith(".md") or \
       rel.startswith(SKIP_DIRS) or rel in SKIP_FILES:
        sys.exit(0)                     # not a memory file — gate doesn't apply
    if tool == "Write":
        ok = has_fields(ti.get("content", ""))
    else:                               # Edit: check the file as it will be AFTER this edit
        disk = ""
        try:
            disk = open(rp, encoding="utf-8").read()
        except OSError:
            pass
        old, new = ti.get("old_string", ""), ti.get("new_string", "")
        # Checking only the file before the edit let an edit that deletes source:/verified:
        # through. Apply it the way the Edit tool will (first match, or all with replace_all).
        after = disk.replace(old, new, -1 if ti.get("replace_all") else 1) if old and old in disk else disk
        ok = has_fields(after)
    if not ok:
        deny("MEMORY GATE: write to memory without provenance. Add to the frontmatter, "
             "under metadata: `source: <conversation date / file path / URL / inferred>` and "
             "`verified: yes|inferred|unverified`. A guess is honestly `inferred` (a decay sweep "
             "can remind you to re-check it later). This is what separates a fact from a "
             "quote-of-a-quote.")
except SystemExit:
    raise
except Exception as e:
    # fail-CLOSED on purpose: unknown gate state → don't let the write into memory
    deny(f"MEMORY GATE crashed ({type(e).__name__}: {e}) — write to memory blocked "
         f"(fail-closed by design).")
sys.exit(0)
