#!/usr/bin/env python3
"""code-pitfalls-hint — show already-paid-for lessons BEFORE touching code.

PreToolUse on Edit|Write: by the file's extension/path → inject ONLY the headings
(### …) of the matching code-pitfalls/<topic>.md plus its path. The bodies stay
out of context; the agent opens the file if a heading looks like its case.
PreToolUse on Bash: flock/lock files → concurrency.md; git → git.md;
ssh/scp/qemu → vm.md; adb → android.md (the last three ship empty — add your own
git.md / vm.md / android.md and they start showing). Edit|Write whose new text
takes a lock or spawns threads also gets concurrency.md.

Pitfall files are read at runtime, so agents append new lessons without anyone
touching this hook. Dedup: topic × session × hour. Blocks nothing; fail-open
(run it under hook-safe.sh).

Why: the same technical mistakes kept recurring across agents and projects —
`pkill -f` killing its own shell, a shared file written without a lock, a fixed
`sleep` racing an event of variable length. Lessons written in a postmortem are
read by nobody at the moment they matter; a heading shown right before the edit is.

Config: CODE_PITFALLS_DIR (default: $CLAUDE_METHODOLOGY_DIR/code-pitfalls,
then ~/.claude/code-pitfalls). Format of the files: see code-pitfalls/README.md.
"""
import json, os, re, sys, time

base = os.environ.get("CLAUDE_METHODOLOGY_DIR", os.path.expanduser("~/.claude"))
ROOT = os.environ.get("CODE_PITFALLS_DIR", os.path.join(base, "code-pitfalls"))


def topics_for_file(fp):
    t = []
    low = fp.lower()
    ext = os.path.splitext(low)[1]
    if ext == ".sh" or "/cron" in low:
        t.append("shell")
    if ext == ".py":
        t.append("python")
    if ext in (".html", ".htm", ".js", ".css"):
        t.append("web")
    if ext in (".ps1", ".psm1", ".cmd", ".bat"):
        t.append("windows")
    if ext in (".service", ".timer"):
        t.append("services")
    if "/.claude/hooks/" in low or "/.claude/scripts/" in low \
            or low.endswith("/settings.json") or low.endswith("/settings.local.json"):
        t.append("hooks")
    if t:
        t.append("verification")   # any code change: how to prove it works
    return t


CONCURRENCY = re.compile(r"\bflock\b|\bfcntl\b|O_EXCL|\.lock\b|\bthreading\b|\bmultiprocessing\b")


def topics_for_cmd(cmd):
    t = []
    if CONCURRENCY.search(cmd):
        t.append("concurrency")
    if re.search(r"(^|[\s;&|(])git\s", cmd):
        t.append("git")
    if re.search(r"(^|[\s;&|(])(ssh|scp)\s|qemu-", cmd):
        t.append("vm")
    if re.search(r"(^|[\s;&|(])adb(\.exe)?\s", cmd):
        t.append("android")
    return t


def headings(topic):
    try:
        with open(os.path.join(ROOT, f"{topic}.md"), encoding="utf-8") as f:
            return [l[4:].strip() for l in f if l.startswith("### ")]
    except OSError:
        return []


def main():
    d = json.load(sys.stdin)
    tool = d.get("tool_name")
    ti = d.get("tool_input") or {}
    if tool in ("Edit", "Write"):
        fp = ti.get("file_path", "") or ""
        if os.path.abspath(fp).startswith(os.path.abspath(ROOT) + os.sep):
            return  # editing the pitfalls themselves
        topics = topics_for_file(fp)
        new_text = (ti.get("new_string") or ti.get("content") or "")[:20000]
        if CONCURRENCY.search(new_text) and not fp.lower().endswith((".md", ".txt")):
            topics.insert(0, "concurrency")
    elif tool == "Bash":
        topics = topics_for_cmd((ti.get("command") or "")[:4000])
    else:
        return
    sid = (d.get("session_id") or "x")[:8]
    hour = time.strftime("%d%H")
    blocks = []
    for tp in topics:
        hs = headings(tp)
        if not hs:
            continue
        try:  # O_EXCL: two parallel Edits can't both pass "not seen yet"
            os.close(os.open(f"/tmp/cph-{sid}-{tp}-{hour}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        blocks.append(os.path.join(ROOT, f"{tp}.md") + " — " + " · ".join(hs))
    if not blocks:
        return
    ctx = ("[code pitfalls] Before this action — headings of lessons already paid for. "
           "If one looks like your case, open the file and read that entry in full. "
           "Stepped on a new one? Append it at the bottom.\n" + "\n".join(blocks))
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "additionalContext": ctx}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(1)
