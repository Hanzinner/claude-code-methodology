#!/usr/bin/env python3
"""Session hygiene: trim old tool outputs from large, inactive Claude Code session files.

  session-hygiene.py                 # every session under ~/.claude/projects (the cron line)
  session-hygiene.py FILE...         # only these files - the same checks apply
  session-hygiene.py --dry-run       # say what would be cut, change nothing

A long chat keeps every tool output twice (the tool_result item and the toolUseResult field next to it); a session
file grows to hundreds of MB and the chat gets slow to load. This cuts those two copies in old records and nothing else.

Never touched: conversation text, thinking, tool inputs, pasted attachments, the newest FRESH_WINDOW records, any session
written in the last hour, any session under the size threshold.
Kept: everything cut is appended to <session-id>-cut.jsonl next to the session (fsync'ed BEFORE the session is rewritten);
the session is written to a temp file, every line re-parsed as JSON, then renamed over the original.

Safety interlock - nothing is changed without a backup of exactly the current content:
  * the newest day folder of the nightly chat copy (scripts/backup-chats.sh: <backup>/<YYYY-MM-DD>/home/<path under
    ~/.claude/projects>) must be younger than BACKUP_MAX_AGE_H, otherwise nothing at all is touched (rc 75 =
    "not ready, try later": bin/catchup-run retries the next hour);
  * a session is trimmed only if that folder holds a copy with the same size and modification time (rsync -a keeps
    the time), i.e. the session has not changed since it was copied. Otherwise it is skipped.

Exit: 0 done (also: nothing to do) · 1 a session could not be processed (ERROR / ABORT lines) · 75 no fresh backup.
Env (tests): CLAUDE_SESSION_ROOT (default ~/.claude/projects), CLAUDE_CHAT_BACKUP_ROOT (default ~/.claude-backups),
HYGIENE_MIN_BYTES (default 5 MB), HYGIENE_ACTIVE_SECONDS (3600), HYGIENE_FRESH_WINDOW (150).
"""
import json
import os
import sys
import tempfile
import time
from datetime import date

SESSION_ROOT = os.path.realpath(os.path.expanduser(os.environ.get("CLAUDE_SESSION_ROOT", "~/.claude/projects")))
BACKUP_TAG = "home"   # backup-chats.sh copies ~/.claude/projects to <day>/home/
BACKUP_ROOT = os.path.expanduser(os.environ.get("CLAUDE_CHAT_BACKUP_ROOT", "~/.claude-backups"))
BACKUP_MAX_AGE_H = 30
MIN_FILE_BYTES = int(os.environ.get("HYGIENE_MIN_BYTES", 5 * 1024 * 1024))
ACTIVE_SECONDS = int(os.environ.get("HYGIENE_ACTIVE_SECONDS", 3600))
FRESH_WINDOW = int(os.environ.get("HYGIENE_FRESH_WINDOW", 150))
MIN_ITEM_BYTES = 1024              # don't bother replacing tiny outputs

PLACEHOLDER = f"[tool output trimmed by session-hygiene {date.today().isoformat()}]"


def jsize(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False))


def latest_backup_dir():
    """Newest dated backup folder, or None if there is none or it is older than BACKUP_MAX_AGE_H."""
    try:
        days = sorted(d for d in os.listdir(BACKUP_ROOT) if d[:2] == "20" and os.path.isdir(os.path.join(BACKUP_ROOT, d)))
    except OSError:
        return None
    if not days:
        return None
    path = os.path.join(BACKUP_ROOT, days[-1])
    if time.time() - os.path.getmtime(path) > BACKUP_MAX_AGE_H * 3600:
        return None
    return path


def backed_up(path: str, backup_dir: str) -> bool:
    """True only if the backup holds this session as it is now: same size, same modification time."""
    prefix = SESSION_ROOT + "/"
    if not path.startswith(prefix):
        return False
    cand = os.path.join(backup_dir, BACKUP_TAG, path[len(prefix):])
    try:
        a, b = os.stat(path), os.stat(cand)
    except OSError:
        return False
    return a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)


def process_file(path: str, dry_run: bool = False):
    """Returns (cut_count, bytes_saved) or None if the result failed validation (nothing written)."""
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
        if isinstance(obj, dict) and obj.get("type") in ("user", "assistant"):
            msg_positions.append(i)

    protected = set(msg_positions[-FRESH_WINDOW:]) if FRESH_WINDOW > 0 else set()

    cut_records = []
    cut_count = 0
    for i, obj in enumerate(parsed):
        if not isinstance(obj, dict) or i in protected or obj.get("type") != "user":
            continue

        cut_entry = {"uuid": obj.get("uuid"), "line": i}

        msg = obj.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), list):
            for j, item in enumerate(msg["content"]):
                if (isinstance(item, dict) and item.get("type") == "tool_result"
                        and jsize(item) > MIN_ITEM_BYTES):
                    cut_entry.setdefault("tool_results", []).append({"index": j, "item": item})
                    replacement = ([{"type": "text", "text": PLACEHOLDER}]
                                   if isinstance(item.get("content"), list) else PLACEHOLDER)
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

    # validate: lines broken before us stay byte-identical; every other non-empty line must parse.
    # Split on \n only - splitlines() also breaks on U+2028 etc. inside JSON strings.
    for i, line in enumerate(new_content.split("\n")):
        if not line.strip():
            continue
        if i in preexisting_bad:
            if i >= len(lines) or (line + "\n" != lines[i] and line != lines[i]):
                print(f"  ABORT {path}: pre-existing bad line {i+1} was altered", file=sys.stderr)
                return None
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as e:
            print(f"  ABORT {path}: line {i+1} invalid after edit: {e}", file=sys.stderr)
            return None

    if dry_run:
        return (cut_count, saved)

    st = os.stat(path)
    cut_path = path[:-len(".jsonl")] + "-cut.jsonl"

    # 1) persist the cut data first (worst case on a crash: duplicates in -cut, the session intact)
    with open(cut_path, "a", encoding="utf-8") as f:
        for rec in cut_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.chmod(cut_path, 0o600)

    # 2) atomic replace of the session file
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".hygiene-tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, st.st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return (cut_count, saved)


def candidates(explicit):
    if explicit:
        return [os.path.realpath(p) for p in explicit]
    out = []
    for dirpath, _dirs, files in os.walk(SESSION_ROOT):
        for name in files:
            if name.endswith(".jsonl") and not name.endswith("-cut.jsonl"):
                out.append(os.path.join(dirpath, name))
    return out


def main():
    dry_run = "--dry-run" in sys.argv
    explicit = [a for a in sys.argv[1:] if not a.startswith("--")]

    backup_dir = latest_backup_dir()
    if backup_dir is None:
        print(f"session-hygiene: no chat backup younger than {BACKUP_MAX_AGE_H} h under {BACKUP_ROOT} - "
              f"nothing touched (scripts/backup-chats.sh makes it nightly)", file=sys.stderr)
        sys.exit(75)

    now = time.time()
    total_cut = total_saved = done = 0
    failed = False
    for p in candidates(explicit):
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_size <= MIN_FILE_BYTES or now - st.st_mtime <= ACTIVE_SECONDS:
            continue
        if not backed_up(p, backup_dir):
            print(f"  SKIP {p}: changed since the last chat backup ({os.path.basename(backup_dir)}) or not in it",
                  file=sys.stderr)
            continue
        try:
            res = process_file(p, dry_run=dry_run)
        except Exception as e:
            print(f"  ERROR {p}: {e}", file=sys.stderr)
            failed = True
            continue
        if res is None:
            failed = True
            continue
        cut, saved = res
        done += 1
        total_cut += cut
        total_saved += saved
        if cut:
            print(f"  {p}: {cut} records trimmed, {saved/1e6:.1f} MB freed{' (dry-run)' if dry_run else ''}")

    print(f"session-hygiene {date.today().isoformat()}: {done} file(s) processed, "
          f"{total_cut} records trimmed, {total_saved/1e6:.1f} MB freed{' (dry-run)' if dry_run else ''}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
