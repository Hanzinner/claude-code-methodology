#!/usr/bin/env python3
"""Session hygiene: trim old tool outputs from large, inactive Claude Code session files.

See docs/context-management.md and docs/multi-agent.md.
- Only files > MIN_FILE_BYTES and mtime older than ACTIVE_SECONDS.
- Cuts tool_result content items AND the sibling toolUseResult field
  (the harness stores the same output twice; toolUseResult is usually the bigger copy).
- Never touches: the freshest FRESH_WINDOW user/assistant records, conversation
  text, thinking, tool_use inputs, user-pasted attachments.
- Everything cut is appended to <session-id>-cut.jsonl (rollback + reference).
- Atomic: writes to a temp file in the same dir, validates every line as JSON, then rename.
- Zero-trust interlock: refuses to touch a session unless a fresh copy exists in
  the daily chat backup.

Config (env):
  CLAUDE_SESSION_ROOTS      comma-separated "path:tag" pairs to scan
                            (default: ~/.claude/projects:home)
  CLAUDE_CHAT_BACKUP_ROOT   dated chat-backup root (default: ~/.claude-backups)
                            Backup is expected to mirror each root under
                            <backup>/<date>/<tag>/<relpath>.
"""
import json
import os
import sys
import tempfile
from datetime import date


def _load_roots():
    """Session roots as (abs_path, backup_tag) pairs."""
    env = os.environ.get("CLAUDE_SESSION_ROOTS")
    if env:
        out = []
        for part in env.split(","):
            part = part.strip()
            if not part:
                continue
            path, _, tag = part.partition(":")
            out.append((os.path.expanduser(path), tag or "root"))
        return out
    return [(os.path.expanduser("~/.claude/projects"), "home")]


SESSION_ROOTS = _load_roots()
BACKUP_ROOT = os.environ.get("CLAUDE_CHAT_BACKUP_ROOT",
                             os.path.expanduser("~/.claude-backups"))
BACKUP_MAX_AGE_H = 30  # newest backup must be younger than this
MIN_FILE_BYTES = 5 * 1024 * 1024   # only files > 5 MB
ACTIVE_SECONDS = 3600              # skip files modified in the last hour
FRESH_WINDOW = 150                 # protect last N user/assistant records
MIN_ITEM_BYTES = 1024              # don't bother replacing tiny outputs

PLACEHOLDER = f"[tool output trimmed by session-hygiene {date.today().isoformat()}]"


def jsize(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False))


def latest_backup_dir():
    """Newest dated backup dir, or None if missing/stale."""
    import time
    try:
        days = sorted(d for d in os.listdir(BACKUP_ROOT) if d[:2] == "20")
    except OSError:
        return None
    if not days:
        return None
    path = os.path.join(BACKUP_ROOT, days[-1])
    if time.time() - os.path.getmtime(path) > BACKUP_MAX_AGE_H * 3600:
        return None
    return path


def backed_up_copy(path: str, backup_dir: str):
    """Path of this session's copy inside the backup, or None if absent/empty.

    Backup layout: <backup_dir>/<tag>/... mirrors each configured session root.
    """
    for root, tag in SESSION_ROOTS:
        prefix = root.rstrip("/") + "/"
        if path.startswith(prefix):
            cand = os.path.join(backup_dir, tag, path[len(prefix):])
            if os.path.isfile(cand) and os.path.getsize(cand) > 0:
                return cand
            return None
    return None


def process_file(path: str, dry_run: bool = False):
    """Returns (cut_count, bytes_saved) or None if skipped/failed."""
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    # positions of conversational records; the last FRESH_WINDOW are protected
    msg_positions = []
    parsed = []
    preexisting_bad = set()  # lines already unparseable before we touch anything
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            obj = None  # leave unknown lines untouched
            preexisting_bad.add(i)
        parsed.append(obj)
        if obj is not None and obj.get("type") in ("user", "assistant"):
            msg_positions.append(i)

    protected = set(msg_positions[-FRESH_WINDOW:])

    cut_records = []
    cut_count = 0
    for i, obj in enumerate(parsed):
        if obj is None or i in protected or obj.get("type") != "user":
            continue

        cut_entry = {"uuid": obj.get("uuid"), "line": i}

        msg = obj.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), list):
            for j, item in enumerate(msg["content"]):
                if (isinstance(item, dict) and item.get("type") == "tool_result"
                        and jsize(item) > MIN_ITEM_BYTES):
                    cut_entry.setdefault("tool_results", []).append(
                        {"index": j, "item": item})
                    replacement = ([{"type": "text", "text": PLACEHOLDER}]
                                   if isinstance(item.get("content"), list)
                                   else PLACEHOLDER)
                    msg["content"][j] = {**item, "content": replacement}

        tur = obj.get("toolUseResult")
        if tur is not None and jsize(tur) > MIN_ITEM_BYTES:
            cut_entry["toolUseResult"] = tur
            obj["toolUseResult"] = PLACEHOLDER

        if "tool_results" in cut_entry or "toolUseResult" in cut_entry:
            cut_records.append(cut_entry)
            cut_count += 1
            lines[i] = json.dumps(obj, ensure_ascii=False) + "\n"

    if not cut_records:
        return (0, 0)

    new_content = "".join(lines)
    saved = os.path.getsize(path) - len(new_content.encode("utf-8"))

    # validate: every non-empty line must parse
    # (split on \n only — splitlines() also breaks on   etc. inside JSON strings)
    # lines already broken before us must remain byte-identical ("no worse than
    # before"); every other line must parse
    for i, line in enumerate(new_content.split("\n")):
        if not line.strip():
            continue
        if i in preexisting_bad:
            if i >= len(lines) or line + "\n" != lines[i] and line != lines[i]:
                print(f"  ABORT {path}: pre-existing bad line {i+1} was altered",
                      file=sys.stderr)
                return None
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as e:
            print(f"  ABORT {path}: line {i+1} invalid after edit: {e}",
                  file=sys.stderr)
            return None

    if dry_run:
        return (cut_count, saved)

    st = os.stat(path)
    cut_path = path[:-len(".jsonl")] + "-cut.jsonl"

    # 1) persist cut data first (worst case on crash: duplicates in -cut, main intact)
    with open(cut_path, "a", encoding="utf-8") as f:
        for rec in cut_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.chown(cut_path, st.st_uid, st.st_gid)
    os.chmod(cut_path, 0o600)

    # 2) atomic replace of the session file
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".hygiene-tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
            f.flush()
            os.fsync(f.fileno())
        os.chown(tmp, st.st_uid, st.st_gid)
        os.chmod(tmp, st.st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return (cut_count, saved)


def main():
    dry_run = "--dry-run" in sys.argv
    explicit = [a for a in sys.argv[1:] if not a.startswith("--")]

    backup_dir = None
    if explicit:
        targets = explicit  # manual/test mode: no backup interlock
        print("manual mode (explicit paths): backup interlock OFF")
    else:
        backup_dir = latest_backup_dir()
        if backup_dir is None:
            print(f"ABORT: no fresh chat backup (<{BACKUP_MAX_AGE_H}h) under "
                  f"{BACKUP_ROOT} — refusing to touch any session",
                  file=sys.stderr)
            sys.exit(1)
        import time
        now = time.time()
        targets = []
        for root, _tag in SESSION_ROOTS:
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    if not name.endswith(".jsonl") or name.endswith("-cut.jsonl"):
                        continue
                    p = os.path.join(dirpath, name)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    if st.st_size > MIN_FILE_BYTES and now - st.st_mtime > ACTIVE_SECONDS:
                        targets.append(p)

    total_cut = total_saved = done = 0
    for p in targets:
        if backup_dir is not None and backed_up_copy(p, backup_dir) is None:
            print(f"  SKIP {p}: no copy in latest backup {backup_dir} — "
                  f"zero-trust interlock", file=sys.stderr)
            continue
        try:
            res = process_file(p, dry_run=dry_run)
        except Exception as e:
            print(f"  ERROR {p}: {e}", file=sys.stderr)
            continue
        if res is None:
            continue
        cut, saved = res
        done += 1
        total_cut += cut
        total_saved += saved
        if cut:
            print(f"  {p}: {cut} records trimmed, {saved/1e6:.1f} MB freed"
                  f"{' (dry-run)' if dry_run else ''}")

    print(f"session-hygiene {date.today().isoformat()}: {done} file(s) processed, "
          f"{total_cut} records trimmed, {total_saved/1e6:.1f} MB freed"
          f"{' (dry-run)' if dry_run else ''}")


if __name__ == "__main__":
    main()
