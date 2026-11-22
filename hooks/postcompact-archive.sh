#!/usr/bin/env bash
# PostCompact hook — the archival half of the pair. It receives the FULL text of
# the compaction summary (it can't inject into context) and files each one to
# ~/.claude/compaction-log/<session>-<ts>.md. The summary outlives the session —
# a direct counter to "knowledge dies at compaction". Fail-open.
#
# Note: read the event from an env var, not a stdin heredoc — stdin is single-use,
# and a heredoc-fed python would swallow the JSON before you could parse it.

DIR="$HOME/.claude/compaction-log"
mkdir -p "$DIR" 2>/dev/null || exit 0
HOOK_INPUT=$(cat 2>/dev/null || true)
export HOOK_INPUT
python3 - "$DIR" "$(dirname "$(readlink -f "$0")")/../lib" <<'EOF' 2>/dev/null
import json, sys, time, os
sys.path.insert(0, sys.argv[2])
import ccm_fs  # os.replace that waits out a file held open on Windows (an antivirus reading the new .tmp)
d = json.loads(os.environ.get("HOOK_INPUT") or "{}")
sid = (d.get("session_id") or "unknown")[:8]
summary = d.get("compact_summary") or d.get("summary") or ""
if not summary:
    summary = "⚠ compact_summary field empty — raw input:\n" + json.dumps(d, ensure_ascii=False)[:20000]
ts = time.strftime("%Y%m%d-%H%M%S")
tmp = os.path.join(sys.argv[1], f".{sid}-{ts}.tmp")
out = os.path.join(sys.argv[1], f"{sid}-{ts}.md")
with open(tmp, "w", encoding="utf-8") as f:
    f.write(f"# Compaction {ts} · session {sid}\n\n{summary}\n")
ccm_fs.replace(tmp, out)
EOF
exit 0
