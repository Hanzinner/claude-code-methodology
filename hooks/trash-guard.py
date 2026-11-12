#!/usr/bin/env python3
"""trash-guard - when the trash grows past a limit, shout at WHOEVER MADE THE MESS.

What happened: a script moved a throw-away browser profile into the trash on every run - 1602 folders, 32 GB in a
day, on a laptop with <1 GB free. The rule "delete = mv to the trash" had neither a limit nor a cleanup.

Modes:
  --pre      PreToolUse Bash: remember this session's command start time.
  --post     PostToolUse Bash: what appeared in the trash DURING the command (top-level ctime >= start) goes into a
             ledger for this session. An mv can hide inside a script, so the command text is not read - only the
             growth. Trash over the limit and this session's items are in it -> a shout into the context
             (once per 10 min).
  --measure  cron every 10 min (the hook also starts it when something new appeared and the measure is older than a
             minute): `du` of the top level at low priority -> state file. The hook never runs du itself (35 GB of
             small files takes minutes). Over the limit and most of it belongs to nobody (grew outside any session)
             OR the culprit ignores it for an hour -> one line to the board file, once a day.
  --clean [--dry]  cron once a day: delete everything that has lain in the trash LONGER THAN CCM_TRASH_DAYS. Age is
             the ctime of the top-level item (mv into the trash updates it) = "how long in the trash", not "when the
             file was created". The only place where deletion is real; each one is a line in clean.log.
Wiring: PreToolUse Bash `trash-guard.py --pre`, PostToolUse Bash `trash-guard.py --post`, cron
  */10 * * * *  python3 <install>/hooks/trash-guard.py --measure
  35 * * * *    python3 <install>/hooks/trash-guard.py --clean      (idempotent: only old items go)
State: ~/.claude/trash-guard/ (state.json, ledger.jsonl, start-<sid>, shout-<sid>, board.md). Error -> silent (fail-open).
Config: CCM_TRASH_DIR, CCM_TRASH_DAYS, CCM_TRASH_LIMIT_GB (default 3), CCM_TRASH_BOARD (default
~/.claude/trash-guard/board.md), CCM_HUMAN_NAME."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

import fcntl, json, re, subprocess, time

HOME = os.path.expanduser("~")
TRASH = conf("CCM_TRASH_DIR")
ST = f"{HOME}/.claude/trash-guard"
LIMIT = float(conf("CCM_TRASH_LIMIT_GB", "3")) * 1024 ** 3
BOARD = conf("CCM_TRASH_BOARD", "") or f"{ST}/board.md"
DU_TIMEOUT = int(os.environ.get("TRASH_DU_TIMEOUT", "300"))
SHOUT_EVERY, STALE, DEAF_AFTER = 600, 60, 3600
GB = 1024 ** 3


def group(name):
    """prof.Ab12Cd -> "prof.*", chrome-profile-1234 -> "chrome-profile-*": the name up to the first digit or dot."""
    m = re.match(r"[^\d.]{2,}\.?", name)
    return (m.group(0) + ("" if m.group(0) == name else "*")) if m else name[:10] + "*"


def jread(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def jwrite(p, obj):
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(p + ".tmp", p)


def ledger():
    """-> {name in the trash: (sid, agent)}; a later record overrides."""
    own = {}
    try:
        for l in open(f"{ST}/ledger.jsonl", encoding="utf-8"):
            try: r = json.loads(l)
            except ValueError: continue
            for n in r.get("names") or []:
                own[n] = (r.get("sid") or "", r.get("agent") or "?")
    except OSError:
        pass
    return own


def agent_of(sid):
    try:
        return os.path.basename(open(f"{HOME}/.claude/agent-identity/{sid}").read().strip().rstrip("/")) or "?"
    except OSError:
        return "?"


def top(sizes, names, n=4):
    """Top name groups among names: "prof.* x1523 - 30.1 GB; ..."."""
    g = {}
    for x in names:
        k = group(x); c, b = g.get(k, (0, 0)); g[k] = (c + 1, b + sizes.get(x, 0))
    rows = sorted(g.items(), key=lambda kv: (-kv[1][1], -kv[1][0]))[:n]
    return "; ".join(f"{k} x{c} - {b / GB:.1f} GB" for k, (c, b) in rows)


def pre(d):
    os.makedirs(ST, exist_ok=True)
    open(f"{ST}/start-{d.get('session_id') or 'x'}", "w").write(repr(time.time()))


def post(d):
    sid = d.get("session_id") or "x"
    try: start = float(open(f"{ST}/start-{sid}").read())
    except (OSError, ValueError): return           # without a start mark the growth is attributed to nobody
    try:
        new = [e.name for e in os.scandir(TRASH) if e.stat(follow_symlinks=False).st_ctime >= start]
    except OSError:
        return
    state = jread(f"{ST}/state.json", {})
    if new:                                    # already attributed to another session (its command was still running) is not taken over
        own = ledger()
        new = [n for n in new if own.get(n, (sid,))[0] == sid]
    if new:
        os.makedirs(ST, exist_ok=True)
        with open(f"{ST}/ledger.jsonl", "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps({"ts": int(time.time()), "sid": sid, "agent": agent_of(sid), "names": new[:5000]}, ensure_ascii=False) + "\n")
        if time.time() - state.get("ts", 0) > STALE:        # a fresh measure before the next command; the hook does not wait
            subprocess.Popen([sys.executable, os.path.abspath(__file__), "--measure"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    total = state.get("total", 0)
    if total < LIMIT:
        return
    sizes = state.get("sizes") or {}
    mine = [n for n, (s, _) in ledger().items() if s == sid and n in sizes]
    if not mine or sum(sizes[n] for n in mine) < LIMIT / 10:
        return                                   # small stuff (<10% of the limit) in an overfull trash - not the culprit
    sp = f"{ST}/shout-{sid}"
    try:
        if time.time() - os.path.getmtime(sp) < SHOUT_EVERY: return
    except OSError: pass
    open(sp, "w").write(str(int(time.time())))
    mb = sum(sizes[n] for n in mine)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
        f"🗑🔥 TRASH {'at least ' if not state.get('complete') else ''}{total / GB:.1f} GB (limit {LIMIT / GB:g} GB) - AND THIS IS YOU. "
        f"During your commands {len(mine)} items appeared in {TRASH} and are still there, about {mb / GB:.1f} GB: {top(sizes, mine)}. "
        f"Rule: the trash must stay below {LIMIT / GB:g} GB, and whoever fills it is told. Now, before any other work: "
        "(1) find the source - which command or SCRIPT does an mv into the trash on every run (the mv may be inside a "
        "script) - and stop it: throw-away junk (caches, temporary profiles, build output) does not go to the trash, it "
        "belongs in an mktemp folder the script removes itself on exit; (2) tell "
        f"{conf('CCM_HUMAN_NAME')} in one line what is there and how much - emptying the trash needs their yes. While the "
        "source lives, this line comes back every 10 min."}}, ensure_ascii=False))
    try:
        with open(f"{ST}/shouts.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')} [{sid[:8]}] {agent_of(sid)}: trash {total / GB:.1f} GB, theirs {len(mine)} items {mb / GB:.1f} GB\n")
    except OSError: pass


def measure():
    os.makedirs(ST, exist_ok=True)
    lk = open(f"{ST}/measure.lock", "a")
    try: fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: return 0                              # the previous measure is still running
    cmd = ["nice", "-n", "19", "ionice", "-c", "3", "du", "-k", "-d", "1", "--", TRASH]
    complete = True
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=DU_TIMEOUT).stdout
    except subprocess.TimeoutExpired as e:               # du prints folders as it walks - partial output = a lower bound
        out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""); complete = False
    sizes, total = {}, None
    for l in out.splitlines():
        kb, _, p = l.partition("\t")
        if not kb.isdigit(): continue
        if p.rstrip("/") == TRASH.rstrip("/"): total = int(kb) * 1024
        else: sizes[os.path.basename(p.rstrip("/"))] = int(kb) * 1024
    try:
        for e in os.scandir(TRASH):                      # du -d1 does not list top-level files separately
            if e.name not in sizes and not e.is_dir(follow_symlinks=False):
                sizes[e.name] = e.stat(follow_symlinks=False).st_blocks * 512
    except OSError: pass
    if total is None:
        total = sum(sizes.values())
    prev = jread(f"{ST}/state.json", {})
    over_since = (prev.get("over_since") or int(time.time())) if total >= LIMIT else None
    state = {"ts": int(time.time()), "total": total, "complete": complete, "sizes": sizes, "over_since": over_since}
    jwrite(f"{ST}/state.json", state)
    own = ledger()
    try:                                                  # the ledger does not grow: keep only records of what is still there
        with open(f"{ST}/ledger.jsonl", "r+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            keep = []
            for l in f:
                try: r = json.loads(l)
                except ValueError: continue
                r["names"] = [n for n in r.get("names") or [] if n in sizes]
                if r["names"]: keep.append(json.dumps(r, ensure_ascii=False) + "\n")
            f.seek(0); f.truncate(); f.writelines(keep)
    except OSError: pass
    print(f"trash {total / GB:.2f} GB{'' if complete else ' (at least: du ran out of time)'}, items {len(sizes)}, limit {LIMIT / GB:g} GB; "
          f"top: {top(sizes, list(sizes)) or '-'}")
    if total < LIMIT:
        return 0
    orphan = [n for n in sizes if n not in own]
    ob = sum(sizes[n] for n in orphan)
    by = {}
    for n in sizes:
        if n in own: by[own[n][1]] = by.get(own[n][1], 0) + sizes[n]
    who = "; ".join(f"{a} {b / GB:.1f} GB" for a, b in sorted(by.items(), key=lambda kv: -kv[1])[:3])
    deaf = bool(by) and time.time() - over_since >= DEAF_AFTER
    if not (ob >= total / 2 or deaf):
        return 0
    day = f"{ST}/board-{time.strftime('%F')}"
    if os.path.exists(day):
        return 0
    line = (f"- [ ] 🟥 [{time.strftime('%F')}] **Trash {total / GB:.1f} GB (limit {LIMIT / GB:g} GB)** - "
            + (f"no culprit visible, it grew outside agent sessions: {top(sizes, orphan)}" if ob >= total / 2
               else f"made and not cleaned up for an hour: {who}; what lies there: {top(sizes, list(sizes))}")
            + ". Ask an agent to empty the trash - or whoever owns the source to stop it.\n")
    try:
        with open(BOARD, "a", encoding="utf-8") as f:
            f.write(line)
        open(day, "w").write(line)
        print("-> a line to the board file")
    except OSError: pass
    return 0


KEEP_DAYS = float(conf("CCM_TRASH_DAYS", "14"))


def clean(dry):
    import shutil
    real = os.path.realpath(TRASH)
    # safety: clean only a folder whose name says it is a trash (.Trash, .claude-trash) that lies no closer than
    # /x/y/<it>; not a symlink — a misconfigured CCM_TRASH_DIR=$HOME must not get emptied
    if "trash" not in os.path.basename(real).lower() or real.count("/") < 3 or os.path.islink(TRASH) or not os.path.isdir(real):
        print(f"trash-guard --clean: \"{TRASH}\" does not look like a trash folder - touching nothing", file=sys.stderr); return 2
    cut = time.time() - KEEP_DAYS * 86400
    sizes = jread(f"{ST}/state.json", {}).get("sizes") or {}
    n = b = err = 0; os.makedirs(ST, exist_ok=True)
    with open(f"{ST}/clean.log", "a", encoding="utf-8") as lg:
        for e in sorted(os.scandir(real), key=lambda e: e.name):
            try:
                st = e.stat(follow_symlinks=False)
                if st.st_ctime >= cut: continue
                days = int((time.time() - st.st_ctime) / 86400); sz = sizes.get(e.name, 0)
                if not dry:
                    if e.is_dir(follow_symlinks=False): shutil.rmtree(e.path)
                    else: os.remove(e.path)
                n += 1; b += sz
                lg.write(f"{time.strftime('%F %T')} {'WOULD DELETE' if dry else 'DELETED'} {e.name} (lay {days} d, {sz / 1024 ** 2:.0f} MB)\n")
            except OSError as x:
                err += 1; lg.write(f"{time.strftime('%F %T')} ERROR {e.name}: {x}\n")
    print(f"trash: {'would delete' if dry else 'deleted'} {n} items older than {KEEP_DAYS:g} d, ~{b / GB:.2f} GB"
          + (f"; errors {err} (see {ST}/clean.log)" if err else ""))
    return 1 if err else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if mode == "--clean":
            sys.exit(clean("--dry" in sys.argv[2:]))
        if mode == "--measure":
            sys.exit(measure())
        if mode in ("--pre", "--post"):
            raw = sys.stdin.read()
            d = json.loads(raw) if raw.strip() else {}
            if d.get("tool_name", "Bash") == "Bash":
                (pre if mode == "--pre" else post)(d)
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(1)
