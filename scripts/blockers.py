#!/usr/bin/env python3
r"""blockers.py - blockers as records with a check, not as words (the "what is waiting for the human" register).

Why: a story's code was finished on day 1, but the blocker ("token permissions") lived as a sentence in someone's TODO; the
coordinator dropped it "until prod" and the story stood still for 5 days until the human found it by accident. A blocker as
a word can be overlooked, rephrased, postponed. A blocker as a record with a check cannot.

Register: <workspace>/<project folder>/BLOCKERS.md (project folders match CCM_PROJECTS_GLOB, default `Project-*`), a table,
one blocker = one row:
  | B3 | what exactly is needed | who clears it | `check` | 2026-10-28 | (any further columns - for people) |
  | ✅ B3 | ... | ... | ... | 2026-10-28 · cleared 2026-10-28 05:10 (check) |      <- written by the watcher / `clear`
The check is a cell with exactly one command in backticks (`|` inside it as `\|`): exit code 0 = the blocker is GONE (the
permission exists, the zone exists, the key file is there). Anything else in the cell (`manual`, a description) is cleared
by a human; a cell that is neither a command nor `manual` makes the watcher log "check is not machine-readable".
Safety: the watcher runs commands, and anyone who can edit BLOCKERS.md can write one. So only a command APPROVED earlier is
executed: `add` approves the command it writes itself, a row edited by hand (or a command changed after approval) is
NOT run until `blockers.py approve <project> B<n>` (read the command first). Not approved -> the watcher only tells the
project lead (one message per command) and the blocker is never cleared by itself. The approvals file must be owned by
the current user with mode 0600, otherwise nothing is executed.
A `manual` check is cleared only by the person who holds the blocker: `blockers.py clear <project> B3 "<who, how>"`.
A story in <project>/ROADMAP.md refers to a blocker by number: "blockers: B3, B7". When the LAST blocker of a story is
cleared the watcher: turns the story line "- ⏳" into "- 🔄" + a trace; posts a message to every agent named in the line
(scripts/inbox_post.sh, if installed); appends one line for the human to ~/.claude/blockers/cleared.log. It does NOT wake an
agent's tab (a cron job can't): the message waits until that agent's next turn.

  blockers.py run [--dry]                       - cron: all projects (checks, clearing, consequences); --dry still runs approved checks
  blockers.py approve <project> B<n>            - allow this row's command to be executed (read it first)
  blockers.py add <project> "<what>" "<who>" "<command | manual>"   - new blocker, prints its number (blocker_add.sh)
  blockers.py clear <project> B<n> "<who/how>"  - clear by a human's word
  blockers.py list [<project>] [--json]         - open ones with story count and days waiting (for a dashboard)
<project> is "Bid" or "Project-Bid". rc: 0 ok - 2 usage - 4 not found.

Config: CCM_WORKSPACE, CCM_AGENTS_DIR, CCM_PROJECTS_GLOB (NEW, default "Project-*"), CCM_BLOCKERS_LEAD (NEW, default
"{project}-HQ": the agent told about an unapproved command; "{project}" = folder name without the glob prefix).
State: ~/.claude/blockers/ (blockers.log, approved-checks.json, open.json, cleared.log).
Env overrides (tests): BLOCKERS_REPO, BLOCKERS_POST, BLOCKERS_LOG, BLOCKERS_APPROVED, BLOCKERS_SNAP, BLOCKERS_STATE.
"""
import datetime as dt, fcntl, glob, hashlib, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402

STATE = os.environ.get("BLOCKERS_STATE", os.path.join(os.path.expanduser("~"), ".claude", "blockers"))
REPO = os.environ.get("BLOCKERS_REPO", conf("CCM_WORKSPACE"))
AGENTS = os.environ.get("BLOCKERS_AGENTS", conf("CCM_AGENTS_DIR") if not os.environ.get("BLOCKERS_REPO") else os.path.join(REPO, "Agents"))
GLOB = conf("CCM_PROJECTS_GLOB", "Project-*")
PREFIX = GLOB.split("*")[0]
LEAD = conf("CCM_BLOCKERS_LEAD", "{project}-HQ")
POST = os.environ.get("BLOCKERS_POST", os.path.join(HERE, "inbox_post.sh"))
LOG = os.environ.get("BLOCKERS_LOG", os.path.join(STATE, "blockers.log"))
SNAP = os.environ.get("BLOCKERS_SNAP", os.path.join(STATE, "open.json"))   # plain JSON for any dashboard
APPROVED = os.environ.get("BLOCKERS_APPROVED", os.path.join(STATE, "approved-checks.json"))   # owner-only, 0600
CLEARED = os.path.join(STATE, "cleared.log")
CHECK_TIMEOUT = int(os.environ.get("BLOCKERS_CHECK_TIMEOUT", "30"))
ROW = re.compile(r"^\|\s*(✅\s*)?(B\d+)\s*\|")
STORY = re.compile(r"\[(E\d+\.S\d+)\]|\b(S\d+)\b")
REFS = re.compile(r"(?:blockers|блокери):\s*((?:B\d+[,\s]*)+)", re.I)
MANUAL = ("manual", "слово")


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{now()} {msg}\n")
    except OSError:
        pass


def proj_dir(name):
    n = name if (name.startswith(PREFIX) or os.path.isdir(os.path.join(REPO, name))) else PREFIX + name
    d = os.path.join(REPO, n)
    return d if os.path.isdir(d) else None


def short(pd):
    b = os.path.basename(pd)
    return b[len(PREFIX):] if PREFIX and b.startswith(PREFIX) else b


def cells(line):
    r"""cells of a table row; `\|` is a pipe inside a cell"""
    parts = re.split(r"(?<!\\)\|", line.strip().strip("|"))
    return [c.strip().replace("\\|", "|") for c in parts]


def parse(path):
    """-> (file lines, [(index, dict)], [broken rows])"""
    out, bad = [], []
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except OSError:
        return [], [], []
    for i, l in enumerate(lines):
        m = ROW.match(l)
        if not m:
            continue
        c = cells(l)
        if len(c) < 5:
            bad.append(l); continue
        _, what, who, check, since = c[:5]
        cm = re.fullmatch(r"`([^`]+)`", check)
        cmd = cm.group(1) if cm and cm.group(1) not in MANUAL else None
        out.append((i, {"id": m.group(2), "open": not m.group(1), "what": what, "who": who, "check": cmd or check,
                        "word": cmd is None, "machine": cmd is not None or any(w in check for w in MANUAL),
                        "since": since, "raw": l}))
    return lines, out, bad


class Locked:
    def __init__(self, path): self.path = path + ".lock"
    def __enter__(self):
        self.f = open(self.path, "w"); fcntl.flock(self.f, fcntl.LOCK_EX); return self
    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN); self.f.close()


def write(path, lines, seen):
    """atomic (tmp + rename) and only if the file did not change since it was read (seen = st_mtime_ns): agents edit
    BLOCKERS/ROADMAP through their own Edit tool without our lock - their edit between our read and write must not be
    overwritten. False -> the caller re-reads and retries."""
    if os.stat(path).st_mtime_ns != seen:
        return False
    tmp = f"{path}.tmp{os.getpid()}"
    open(tmp, "w", encoding="utf-8").write("\n".join(lines))
    st = os.stat(path)
    os.chown(tmp, st.st_uid, st.st_gid); os.chmod(tmp, st.st_mode & 0o777)
    if st.st_mtime_ns != seen:
        os.remove(tmp); return False
    os.replace(tmp, path)
    return True


def mt(path):
    return os.stat(path).st_mtime_ns


def stories(pd):
    """-> [(index, line, story code, [B...])] from ROADMAP"""
    out = []
    try:
        lines = open(os.path.join(pd, "ROADMAP.md"), encoding="utf-8").read().split("\n")
    except OSError:
        return [], []
    for i, l in enumerate(lines):
        r = REFS.search(l)
        if not r:
            continue
        sm = STORY.search(l)
        out.append((i, l, (sm.group(1) or sm.group(2)) if sm else f"line {i + 1}", re.findall(r"B\d+", r.group(1))))
    return lines, out


def agents_in(line):
    names = {os.path.basename(d) for d in glob.glob(os.path.join(AGENTS, "*")) if os.path.isdir(d)}
    return sorted({w for w in re.findall(r"[A-Za-z][\w-]+", line) if w in names})


def notify_human(text):
    """no chat/pult messages: a line in a file the human (or a dashboard) can read"""
    log(f"FOR THE HUMAN: {text}")
    if os.environ.get("BLOCKERS_NO_NOTIFY") == "1":
        return
    try:
        os.makedirs(os.path.dirname(CLEARED), exist_ok=True)
        with open(CLEARED, "a", encoding="utf-8") as f:
            f.write(f"{now()} {text}\n")
    except OSError:
        pass


def post(agent, text):
    """message to an agent's inbox through scripts/inbox_post.sh; absent or failing -> logged, never fatal"""
    if not os.path.isfile(POST):
        log(f"inbox_post not found at {POST}: message to {agent} not sent")
        return
    try:
        subprocess.run([POST, agent], input=text, text=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"message to {agent} failed: {e}")


def close(pd, bid, how):
    """mark B closed in the register; True if it was open"""
    path = os.path.join(pd, "BLOCKERS.md")
    if not os.path.exists(path):
        return False
    with Locked(path):
      for _ in range(5):
        seen = mt(path); lines, rows, _ = parse(path)
        for i, r in rows:
            if r["id"] == bid and r["open"]:
                l = re.sub(r"^\|\s*B", "| ✅ B", r["raw"], count=1)
                # trace of clearing goes into the date cell (5th), other columns stay as they were
                parts = re.split(r"(?<!\\)\|", l)
                if len(parts) > 6:
                    parts[5] = parts[5].rstrip() + f" · cleared {now()} ({how.replace('|', '/')}) "
                lines[i] = "|".join(parts)
                if write(path, lines, seen):
                    return True
                break   # the file changed under us - re-read
        else:
            return False
    return False


def check_key(pd, cmd):
    return hashlib.sha256(f"{os.path.basename(pd)}\0{cmd}".encode()).hexdigest()


def load_approved():
    """-> {"checks": {key: {...}}, "told": {key: time}}; file not owned by the current user or open to others -> empty"""
    empty = {"checks": {}, "told": {}}
    try:
        st = os.stat(APPROVED)
        if st.st_uid != os.geteuid() or st.st_mode & 0o077:
            log(f"{APPROVED}: not owner-only 0600 - treating every command as unapproved"); return empty
        d = json.load(open(APPROVED, encoding="utf-8"))
        return {"checks": d.get("checks") or {}, "told": d.get("told") or {}}
    except FileNotFoundError:
        return empty
    except (OSError, ValueError) as e:
        log(f"{APPROVED} unreadable: {e}"); return empty


def update_approved(fn):
    """fn(data) under a lock; atomic write, 0600"""
    os.makedirs(os.path.dirname(APPROVED), exist_ok=True)
    with Locked(APPROVED):
        d = load_approved()
        fn(d)
        tmp = f"{APPROVED}.tmp{os.getpid()}"
        with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=0)
        os.replace(tmp, APPROVED)


def approve(pd, bid, cmd):
    update_approved(lambda d: d["checks"].__setitem__(check_key(pd, cmd), {"project": os.path.basename(pd), "id": bid, "cmd": cmd, "at": now()}))


def tell_unapproved(pd, r, key):
    """one message to the project lead per command: without it the blocker would silently never clear"""
    log(f"{os.path.basename(pd)} {r['id']}: command not approved, not running: {r['check'][:200]}")
    if key in load_approved()["told"]:
        return
    hq = LEAD.format(project=short(pd))
    if os.path.isdir(os.path.join(AGENTS, hq)):
        post(hq, f"- [ ] [{now()}] blockers watcher · {os.path.basename(pd)} {r['id']}: the check was edited outside blocker_add, "
                 f"so I am not running it. Verify in BLOCKERS.md that the command is yours, then: "
                 f"`blockers.py approve {short(pd)} {r['id']}`\n")
    update_approved(lambda d: d["told"].__setitem__(key, now()))


def consequences(pd, cleared, dry=False):
    """for just-cleared B's: stories with no open blockers left -> 🔄 + messages + a line for the human"""
    _, rows, _ = parse(os.path.join(pd, "BLOCKERS.md"))
    still = {r["id"] for _, r in rows if r["open"]}
    rp = os.path.join(pd, "ROADMAP.md")
    moved = {b: [] for b in cleared}
    mail = []
    # a project without ROADMAP: the blocker is closed, there is no story to move - only the line for the human
    for _ in range(5 if os.path.exists(rp) else 0):
      with Locked(rp):
        seen = mt(rp); lines, sts = stories(pd)
        changed = False
        moved = {b: [] for b in cleared}
        mail = []
        for i, l, code, refs in sts:
            hit = [b for b in refs if b in cleared]
            if not hit or any(b in still for b in refs):
                continue
            for b in hit:
                moved[b].append(code)
            if l.startswith("- ⏳"):
                lines[i] = "- 🔄" + l[len("- ⏳"):] + f" · (blockers watcher {now()}: {', '.join(hit)} cleared -> in progress)"
                changed = True
            mail += [(a, f"- [ ] [{now()}] blockers watcher · {', '.join(hit)} cleared -> {code} is in progress. "
                         f"Story line: {os.path.basename(pd)}/ROADMAP.md:{i + 1}\n") for a in agents_in(l)]
        if dry or not changed or write(rp, lines, seen):
            break
    if not dry:
        for a, text in mail:
            post(a, text)
    for b, codes in moved.items():
        what = next((r["what"] for _, r in rows if r["id"] == b), "")
        msg = f"✅ {short(pd)} {b} cleared ({what[:80]})" + (f" -> in progress: {', '.join(codes)}" if codes else "")
        log(msg)
        if not dry:
            notify_human(msg)
    return moved


def cmd_run(dry):
    rc = 0
    for path in sorted(glob.glob(os.path.join(REPO, GLOB, "BLOCKERS.md"))):
        try:
            run_project(path, dry)
        except Exception as e:     # a vanished or broken file must not leave the other projects unchecked
            log(f"{path}: pass crashed: {type(e).__name__}: {e}"); rc = 1
    return rc


def run_project(path, dry):
    pd = os.path.dirname(path)
    _, rows, bad = parse(path)
    for b in bad:
        log(f"{os.path.basename(pd)}: BROKEN register row (needs >=5 cells: no | what | who | check | date): {b[:120]}")
    for _, r in rows:
        if r["open"] and not r["machine"]:
            log(f"{os.path.basename(pd)} {r['id']}: check is not machine-readable (\"{r['check'][:60]}\") - only a human can clear it; give a command in backticks or `manual`")
    cleared = []
    ok_checks = load_approved()["checks"]
    for _, r in rows:
        if not r["open"] or r["word"]:
            continue
        if check_key(pd, r["check"]) not in ok_checks:
            if not dry:
                tell_unapproved(pd, r, check_key(pd, r["check"]))
            continue
        try:
            ok = subprocess.run(["bash", "-c", r["check"]], cwd=REPO, capture_output=True,
                                timeout=CHECK_TIMEOUT).returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
        if ok and (dry or close(pd, r["id"], "check")):
            cleared.append(r["id"])
    if cleared:
        consequences(pd, cleared, dry)
    print(f"{os.path.basename(pd)}: open {sum(r['open'] for _, r in rows) - len(cleared)}, cleared now {cleared or '-'}"
          + (f", broken rows {len(bad)}" if bad else ""))


def cmd_add(proj, what, who, check):
    pd = proj_dir(proj)
    if not pd:
        print(f"no project {proj}"); return 4
    path = os.path.join(pd, "BLOCKERS.md")
    if not os.path.exists(path):
        open(path, "w", encoding="utf-8").write(f"# BLOCKERS - {os.path.basename(pd)}\n\nFormat and rules: see scripts/blockers.py; "
                                                 "the watcher (cron, every 15 min) is `blockers.py run`.\n")
    with Locked(path):
      for _ in range(5):
        seen = mt(path); lines, rows, _ = parse(path)
        n = max([int(r["id"][1:]) for _, r in rows] or [0]) + 1
        chk = check.strip("`").replace("|", "\\|")
        row = f"| B{n} | {what.replace('|', '/')} | {who.replace('|', '/')} | `{chk}` | {dt.date.today()} | |"
        last = max([i for i, _ in rows] or [-1])
        if last < 0:   # new table
            while lines and not lines[-1].strip():
                lines.pop()
            lines += ["", "| No | What exactly is needed | Who clears it | Check | Since | Note |", "|---|---|---|---|---|---|", row, ""]
        else:
            lines.insert(last + 1, row)
        if write(path, lines, seen):
            break
    print(f"B{n}  <- put it in the story line of ROADMAP: \"blockers: B{n}\"")
    new = next((r for _, r in parse(path)[1] if r["id"] == f"B{n}"), None)
    if new and not new["word"]:
        approve(pd, new["id"], new["check"])   # written through add = the author vouches for the command
    log(f"{os.path.basename(pd)} ADDED B{n}: {what}")
    return 0


def cmd_approve(proj, bid):
    pd = proj_dir(proj)
    if not pd:
        print(f"no project {proj}"); return 4
    r = next((r for _, r in parse(os.path.join(pd, "BLOCKERS.md"))[1] if r["id"] == bid and r["open"]), None)
    if not r:
        print(f"{bid} not found among the open ones in {os.path.basename(pd)}/BLOCKERS.md"); return 4
    if r["word"]:
        print(f"{bid}: the check is not a command, nothing to approve"); return 2
    approve(pd, bid, r["check"])
    print(f"{bid} approved, the watcher will run: {r['check']}")
    log(f"{os.path.basename(pd)} APPROVED {bid}: {r['check']}")
    return 0


def cmd_clear(proj, bid, how):
    pd = proj_dir(proj)
    if not pd:
        print(f"no project {proj}"); return 4
    if not close(pd, bid, how):
        print(f"{bid} not found among the open ones in {os.path.basename(pd)}/BLOCKERS.md"); return 4
    m = consequences(pd, [bid])
    print(f"{bid} cleared; moved to in-progress: {', '.join(m.get(bid) or []) or '- (no story refers to it, or it has other blockers)'}")
    return 0


def open_list(proj=None):
    out = []
    pds = [proj_dir(proj)] if proj else sorted(os.path.dirname(p) for p in glob.glob(os.path.join(REPO, GLOB, "BLOCKERS.md")))
    for pd in filter(None, pds):
        _, rows, _ = parse(os.path.join(pd, "BLOCKERS.md"))
        _, sts = stories(pd)
        for _, r in rows:
            if not r["open"]:
                continue
            try:
                days = (dt.date.today() - dt.date.fromisoformat(r["since"][:10])).days
            except ValueError:
                days = None
            out.append({"project": short(pd), **{k: r[k] for k in ("id", "what", "who", "check", "word", "since")},
                        "days": days, "stories": [c for _, _, c, refs in sts if r["id"] in refs]})
    return out


def snapshot():
    if os.environ.get("BLOCKERS_REPO") and not os.environ.get("BLOCKERS_SNAP"):
        return   # a sandbox repo without an explicit snapshot path must not overwrite the real snapshot
    try:
        os.makedirs(os.path.dirname(SNAP), exist_ok=True)
        tmp = SNAP + ".tmp"
        json.dump({"at": now(), "open": open_list()}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.chmod(tmp, 0o644); os.replace(tmp, SNAP)
    except OSError as e:
        log(f"dashboard snapshot not written: {e}")


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 2
    if a[0] == "run":
        return cmd_run("--dry" in a)
    if a[0] == "add" and len(a) == 5:
        return cmd_add(*a[1:])
    if a[0] == "approve" and len(a) == 3:
        return cmd_approve(*a[1:])
    if a[0] == "clear" and len(a) == 4:
        return cmd_clear(*a[1:])
    if a[0] == "list":
        rest = [x for x in a[1:] if x != "--json"]
        L = open_list(rest[0] if rest else None)
        if "--json" in a:
            print(json.dumps(L, ensure_ascii=False))
        else:
            for b in L:
                print(f"{b['project']} {b['id']} · {b['what']} · cleared by {b['who']} · stories {len(b['stories'])} "
                      f"({', '.join(b['stories'])}) · {b['days']} d")
        return 0
    print(__doc__); return 2


if __name__ == "__main__":
    rc = main(sys.argv[1:])
    if sys.argv[1:2] in (["run"], ["add"], ["clear"]) and "--dry" not in sys.argv:
        snapshot()
    sys.exit(rc)
