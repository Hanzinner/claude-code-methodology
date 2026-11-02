#!/usr/bin/env python3
"""Extract user/assistant messages since the last compaction boundary.

Used by the /recap skill to harvest material worth saving to memory.
Picks THIS session's transcript by $CLAUDE_CODE_SESSION_ID and dumps its
post-compaction content. Without the variable it falls back to the most
recently modified transcript, with a warning: with several sessions running,
"newest file" is a lottery — /recap once pulled another session's dialogue
into memory, silently.

Override the project dir with $CLAUDE_PROJECT_TRANSCRIPT_DIR.
"""
import json
import glob
import os
import sys

# Default location of Claude Code session transcripts. Override per project.
project_dir = os.environ.get(
    "CLAUDE_PROJECT_TRANSCRIPT_DIR",
    os.path.expanduser("~/.claude/projects"),
)

sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
files = glob.glob(f"{project_dir}/**/{sid}.jsonl", recursive=True) if sid else []
if not files:
    print("recap_extract: CLAUDE_CODE_SESSION_ID unset or its transcript not found — "
          "using the newest transcript. With parallel sessions this may be ANOTHER "
          "session; check the output against your own context.", file=sys.stderr)
    files = sorted(
        glob.glob(f"{project_dir}/**/*.jsonl", recursive=True),
        key=os.path.getmtime,
        reverse=True,
    )

if not files:
    print(f"No session files found under {project_dir}.", file=sys.stderr)
    sys.exit(1)

session_file = files[0]
print(f"# Session: {os.path.basename(session_file)}\n")

records = []
with open(session_file) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            pass

last_compact = -1
for i, obj in enumerate(records):
    if obj.get("type") == "system" and obj.get("subtype") == "compact_boundary":
        last_compact = i

if last_compact == -1:
    print("# No compaction found — using full session\n")
else:
    ts = records[last_compact].get("timestamp", "")
    print(f"# Since last compaction: {ts}\n")

messages = []
for obj in records[last_compact + 1:]:
    t = obj.get("type")
    if t not in ("user", "assistant"):
        continue
    msg = obj.get("message", {})
    role = msg.get("role", t)
    content = msg.get("content", "")
    if isinstance(content, list):
        text = " ".join(
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        )
    else:
        text = str(content)
    text = text.strip()
    if text and len(text) > 5:
        messages.append((role, text))

print(f"# Total messages since compaction: {len(messages)}\n")

for role, text in messages:
    print(f"[{role.upper()}]")
    print(text[:600])
    print()
