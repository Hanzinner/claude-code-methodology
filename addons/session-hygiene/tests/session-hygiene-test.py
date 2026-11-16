#!/usr/bin/env python3
"""Sandboxed test of session-hygiene.py: a temp session root and a temp chat backup, small thresholds. HYG=path tests
another copy. Checks the interlock (no backup / stale backup / session changed since the copy / active session -> not one
byte changed), what is cut and what never is (conversation text, thinking, tool inputs, attachments, the newest records,
a line that was already broken), the -cut.jsonl that restores the original, --dry-run, and rc 1 on a file it cannot read.
Last line: session-hygiene-test: N pass, M fail."""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, time
from datetime import date
from pathlib import Path

HYG = os.environ.get("HYG") or str(Path(__file__).resolve().parent.parent / "session-hygiene.py")
T = Path(tempfile.mkdtemp(prefix="hyg-test-"))
ROOT, BK = T / "projects", T / "backups"
passed = failed = 0


def ok(name, cond, detail=""):
    global passed, failed
    if cond: passed += 1
    else: failed += 1; print("FAIL:", name, str(detail)[:400])


BIG = "x" * 3000
def session(n_turns=6):
    """user text -> assistant (thinking + tool_use) -> user tool_result (+toolUseResult) ..., an attachment, a broken line"""
    recs = []
    for k in range(n_turns):
        recs.append({"type": "user", "uuid": f"u{k}", "message": {"role": "user", "content": [
            {"type": "text", "text": f"question {k} — питання"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "P" * 2500}}]}})
        recs.append({"type": "assistant", "uuid": f"a{k}", "message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": f"thinking {k} " + "t" * 1500},
            {"type": "text", "text": f"answer {k}"},
            {"type": "tool_use", "id": f"t{k}", "name": "Bash", "input": {"command": "cat big " + "c" * 1500}}]}})
        recs.append({"type": "user", "uuid": f"r{k}", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"t{k}", "content": [{"type": "text", "text": f"out {k} " + BIG}]}]},
            "toolUseResult": {"stdout": f"out {k} " + BIG, "stderr": ""}})
    lines = [json.dumps(r, ensure_ascii=False) for r in recs]
    lines.insert(3, '{"broken json line')
    return "\n".join(lines) + "\n"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def fresh(name="s1", old=True, copy=True, backup_age_h=1):
    """a session file + (optionally) its copy in today's backup folder, both with the same mtime"""
    shutil.rmtree(ROOT, ignore_errors=True); shutil.rmtree(BK, ignore_errors=True)
    p = ROOT / "-home-u-proj" / f"{name}.jsonl"; p.parent.mkdir(parents=True)
    p.write_text(session(), encoding="utf-8")
    t = time.time() - (7200 if old else 10)
    os.utime(p, (t, t))
    day = BK / date.today().isoformat()
    day.mkdir(parents=True)
    if copy:
        c = day / "home" / "-home-u-proj" / p.name; c.parent.mkdir(parents=True); shutil.copy2(p, c)
    bt = time.time() - backup_age_h * 3600
    os.utime(day, (bt, bt))
    return p


def run(*args):
    # HOME in the sandbox too: a copy under test that reads its roots from other variables must still not reach real sessions
    env = {**os.environ, "HOME": str(T / "home"), "CLAUDE_SESSION_ROOT": str(ROOT), "CLAUDE_CHAT_BACKUP_ROOT": str(BK),
           "HYGIENE_MIN_BYTES": "1000", "HYGIENE_FRESH_WINDOW": "4"}
    r = subprocess.run([sys.executable, HYG, *args], env=env, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr


def kept_parts(text):
    """everything that must never change: per record its text, thinking, tool_use inputs, attachments"""
    out = []
    for l in text.split("\n"):
        try:
            o = json.loads(l)
        except json.JSONDecodeError:
            out.append(("raw", l)); continue
        for it in (o.get("message") or {}).get("content") or []:
            if isinstance(it, dict) and it.get("type") in ("text", "thinking", "tool_use", "image"):
                out.append((o.get("uuid"), json.dumps(it, ensure_ascii=False, sort_keys=True)))
    return out


# 1-4: the interlock - not one byte changed
p = fresh(); shutil.rmtree(BK); h = sha(p)
rc, out = run(); ok("1 no chat backup at all -> rc 75, session unchanged, no -cut", rc == 75 and sha(p) == h and not list(ROOT.rglob("*-cut.jsonl")), (rc, out))
p = fresh(backup_age_h=40); h = sha(p)
rc, out = run(); ok("2 newest backup older than 30 h -> rc 75, unchanged", rc == 75 and sha(p) == h, (rc, out))
p = fresh(); h0 = sha(p)
with open(p, "a", encoding="utf-8") as f: f.write(json.dumps({"type": "user", "uuid": "late", "message": {"content": "later"}}) + "\n")
t = time.time() - 7200; os.utime(p, (t, t)); h = sha(p)
rc, out = run(); ok("3 session changed after the backup copy -> SKIP, unchanged, rc 0", rc == 0 and sha(p) == h and "SKIP" in out, (rc, out))
p = fresh(copy=False); h = sha(p)
rc, out = run(); ok("3b session missing from the backup -> SKIP, unchanged", rc == 0 and sha(p) == h and "SKIP" in out, (rc, out))
p = fresh(old=False); h = sha(p)
rc, out = run(); ok("4 active session (written 10 s ago), even with a copy -> unchanged", rc == 0 and sha(p) == h, (rc, out))

# 5-9: a large old session with a matching copy -> trimmed
p = fresh(); before = p.read_text(encoding="utf-8"); size0 = p.stat().st_size
rc, out = run("--dry-run"); ok("5 --dry-run -> says what it would cut, changes nothing", rc == 0 and sha(p) == hashlib.sha256(before.encode()).hexdigest() and "dry-run" in out and not list(ROOT.rglob("*-cut.jsonl")), (rc, out))
rc, out = run()
after = p.read_text(encoding="utf-8")
cut = p.with_name("s1-cut.jsonl")
ok("6 trimmed: rc 0, smaller, -cut.jsonl written (0600)", rc == 0 and p.stat().st_size < size0 and cut.is_file() and (cut.stat().st_mode & 0o777) == 0o600, (rc, out, p.stat().st_size, size0))
ok("7 conversation text, thinking, tool inputs, attachments, broken line: byte-identical", kept_parts(before) == kept_parts(after))
recs_b = [json.loads(l) for l in before.split("\n") if l.strip() and not l.startswith('{"broken')]
recs_a = [json.loads(l) for l in after.split("\n") if l.strip() and not l.startswith('{"broken')]
ok("8 every line still valid JSON, same count", len(recs_a) == len(recs_b) and '{"broken json line' in after)
old_outs = [r for r in recs_a if r["uuid"] in ("r0", "r1", "r2", "r3")]
new_outs = [r for r in recs_a if r["uuid"] in ("r5",)]
ok("9 old tool outputs replaced (both copies), the newest 4 records untouched",
   all("trimmed by session-hygiene" in json.dumps(r) and BIG not in json.dumps(r) for r in old_outs)
   and all(BIG in json.dumps(r) for r in new_outs), [json.dumps(r)[:120] for r in old_outs + new_outs])
# restore from -cut.jsonl -> the original records
by_uuid = {r["uuid"]: r for r in recs_a}
for c in (json.loads(l) for l in cut.read_text(encoding="utf-8").splitlines()):
    r = by_uuid[c["uuid"]]
    for tr in c.get("tool_results", []):
        r["message"]["content"][tr["index"]] = tr["item"]
    if "toolUseResult" in c:
        r["toolUseResult"] = c["toolUseResult"]
ok("10 -cut.jsonl restores every cut record exactly", [by_uuid[r["uuid"]] for r in recs_b] == recs_b)
n_cut, h = len(cut.read_text().splitlines()), sha(p)
rc, out = run(); ok("11 second run right after (session just rewritten = active) -> unchanged, -cut not appended",
                    rc == 0 and sha(p) == h and len(cut.read_text().splitlines()) == n_cut, (rc, out, n_cut))
ok("12 -cut.jsonl is never itself treated as a session", "s1-cut.jsonl" not in out, out)

# 13: a file it cannot process -> rc 1
p = fresh(); p.write_bytes(b"\xff\xfe not utf-8 " * 200); t = time.time() - 7200; os.utime(p, (t, t))
c = BK / date.today().isoformat() / "home" / "-home-u-proj" / p.name; shutil.copy2(p, c)
rc, out = run(); ok("13 unreadable session -> ERROR line, rc 1 (catchup-run records a failure)", rc == 1 and "ERROR" in out, (rc, out))
# 14: no owner-specific paths in the code
src = Path(HYG).read_text(encoding="utf-8")
ok("14 no /root or /home/<someone> paths in the code", not re.search(r"/root/|/home/\w", src))

shutil.rmtree(T, ignore_errors=True)
print(f"session-hygiene-test: {passed} pass, {failed} fail")
sys.exit(1 if failed else 0)
