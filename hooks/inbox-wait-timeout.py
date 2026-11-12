#!/usr/bin/env python3
"""inbox-wait-timeout - PreToolUse Bash: add the link's `timeout` to a BARE background call of the alarm
(inbox_wait.sh). A measurement showed a background task living 81 minutes with no timeout; this is insurance in case
a harness brings back a 30-minute limit - the alarm's link is 55 minutes because the prompt cache lives an hour.
Only when the WHOLE call is a bare `inbox_wait.sh <agent> [--until/--max ...]` run in the background: then the "allow"
approves nothing extra (a glued command like `inbox_wait.sh X; rm -rf y` is left alone, so is a call that is not in the
background or already has a longer timeout).
The script is recognised by bare name or by a path under the install dir / ~/.claude/scripts.
Env: INBOX_WAIT_TIMEOUT_MS (default 3300000). Fail-open under hook-safe.sh."""
import json, os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

T_MS = int(os.environ.get("INBOX_WAIT_TIMEOUT_MS", "3300000"))
DIRS = [os.path.join(conf("CCM_CLAUDE_DIR"), "scripts"), os.path.expanduser("~/.claude/scripts"), "$HOME/.claude/scripts", "~/.claude/scripts"]
PREFIX = "(?:(?:" + "|".join(re.escape(d.rstrip("/")) for d in DIRS) + ")/)?"
CMD = re.compile(r"\s*" + PREFIX + r"inbox_wait\.sh\s+[\w.-]+(?:\s+--(?:until|max)\s+[\w:]+)*\s*")


def main():
    d = json.load(sys.stdin)
    if d.get("tool_name") != "Bash":
        return
    ti = d.get("tool_input") or {}
    if not ti.get("run_in_background") or not CMD.fullmatch(ti.get("command") or ""):
        return
    if int(ti.get("timeout") or 0) >= T_MS:
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                             "permissionDecisionReason": f"alarm: link of {T_MS // 60000} min",
                                             "updatedInput": {**ti, "timeout": T_MS}}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
