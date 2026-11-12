#!/usr/bin/env python3
"""
rename_session.py — set a custom title on a Claude Code session.

Appends a `custom-title` record to the session's .jsonl. The webview UI reads
the latest such record (falling back to ai-title) to render the sessions list.

Usage:
    rename_session.py <selector> "<new title>"
    rename_session.py --list [<selector>]

selector: substring of session UUID, ai-title, or existing custom-title
          (case-insensitive). Must uniquely identify one session.

Note: VS Code may need to refresh the sidebar to pick up the change
      (close/reopen the sessions panel, or reload window).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECTS_ROOT = Path(os.path.expanduser("~/.claude/projects"))


def find_sessions():
    """Yield (jsonl_path, session_id, ai_title, custom_title)."""
    for jsonl in PROJECTS_ROOT.rglob("*.jsonl"):
        m = re.fullmatch(
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl",
            jsonl.name,
        )
        if not m:
            continue
        sid = m.group(1)
        ai_title = None
        custom_title = None
        try:
            with jsonl.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"ai-title"' not in line and '"custom-title"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    t = rec.get("type")
                    if t == "ai-title":
                        ai_title = rec.get("aiTitle") or ai_title
                    elif t == "custom-title":
                        custom_title = rec.get("customTitle") or custom_title
        except OSError:
            continue
        yield jsonl, sid, ai_title, custom_title


def match_sessions(selector: str):
    sel = selector.lower()
    matches = []
    for jsonl, sid, ai, custom in find_sessions():
        haystack = " | ".join(filter(None, [sid, ai, custom])).lower()
        if sel in haystack:
            matches.append((jsonl, sid, ai, custom))
    return matches


def fmt_session(sid, ai, custom):
    title = custom or ai or "(no title)"
    marker = "★" if custom else " "
    return f"  {marker} {sid[:8]}…  {title}"


def cmd_list(selector: str | None):
    rows = []
    for jsonl, sid, ai, custom in find_sessions():
        if selector:
            sel = selector.lower()
            haystack = " | ".join(filter(None, [sid, ai, custom])).lower()
            if sel not in haystack:
                continue
        rows.append((jsonl.stat().st_mtime, sid, ai, custom))
    rows.sort(reverse=True)
    print(f"Sessions ({len(rows)}):  ★ = has custom-title\n")
    for _, sid, ai, custom in rows:
        print(fmt_session(sid, ai, custom))


def cmd_rename(selector: str, new_title: str):
    if not new_title.strip():
        print("ERROR: empty title", file=sys.stderr)
        sys.exit(2)

    matches = match_sessions(selector)
    if not matches:
        print(f"ERROR: no session matches '{selector}'", file=sys.stderr)
        sys.exit(2)
    if len(matches) > 1:
        print(f"ERROR: '{selector}' is ambiguous, matches {len(matches)}:", file=sys.stderr)
        for jsonl, sid, ai, custom in matches:
            print(fmt_session(sid, ai, custom), file=sys.stderr)
        sys.exit(2)

    jsonl, sid, ai, custom = matches[0]
    stat = jsonl.stat()
    record = {
        "type": "custom-title",
        "sessionId": sid,
        "customTitle": new_title,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
    }
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with jsonl.open("a", encoding="utf-8") as f:
        f.write(line)
    os.utime(jsonl, (stat.st_atime, stat.st_mtime))

    prev = custom or ai or "(no title)"
    print(f"Renamed {sid[:8]}…  '{prev}'  →  '{new_title}'")
    print(f"  file: {jsonl}")
    print("  UI may need a sidebar refresh (close/reopen sessions panel) to update.")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0)
    if args[0] == "--list":
        cmd_list(args[1] if len(args) > 1 else None)
        return
    if len(args) != 2:
        print("ERROR: expected <selector> <new title>", file=sys.stderr)
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
    cmd_rename(args[0], args[1])


if __name__ == "__main__":
    main()
