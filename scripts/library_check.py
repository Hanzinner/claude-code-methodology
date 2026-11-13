#!/usr/bin/env python3
"""library_check.py - nightly check of the catalog LIBRARY.md against reality.

  (a) every path in a line `- <code> [name](path) - ... {tags}` exists (retired `~~...~~` lines are skipped);
  (b) every script from the hooks of settings.json and from the crontab has a line in LIBRARY (match by full path or
      basename); a cron line without a script (an inline `find ... -delete`) is skipped;
  (c) the `{hook:Event}` tags of a line = the events the script is really subscribed to in settings.json;
  (d) duplicate line numbers (the same code twice);
  (e) NEW/CHANGED within a day in the script folders without a mention in LIBRARY or SWARM-TOOLS -> a letter to the
      AUTHOR (the session that wrote the file, found from transcripts -> ~/.claude/agent-identity -> agent) + a line in
      the keeper's letter. Why: two scripts lived 2 hours without a line and the check was silent, because it only saw
      hooks and cron.
Differences -> ONE letter to CCM_LIBRARY_KEEPER (empty = print/log only); none -> a single log line.
`--dry` only prints. The stop-dispatch.sh dispatcher: the detectors it runs inherit its events.
Settings: CCM_WORKSPACE (LIBRARY.md, SWARM-TOOLS.md there), CCM_CLAUDE_DIR, CCM_LIBRARY_KEEPER, CCM_INBOX_POST.
Test overrides (LIBCHECK_*): REPO, SETTINGS, CRON_FILE, FRESH_DIRS, TRANSCRIPTS, IDENTITY. Test: tests/library-check-test.py
Cron: 52 12 * * *"""
import glob, json, os, re, shlex, subprocess, sys, time
from urllib.parse import unquote

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf

HOME = os.path.expanduser("~")
CLAUDE_DIR = conf("CCM_CLAUDE_DIR")
REPO = os.environ.get("LIBCHECK_REPO", conf("CCM_WORKSPACE"))
LIB = f"{REPO}/LIBRARY.md"
SETTINGS = os.environ.get("LIBCHECK_SETTINGS", os.path.join(HOME, ".claude", "settings.json")).split(":")
CRON_FILE = os.environ.get("LIBCHECK_CRON_FILE")  # instead of `crontab -l`
POST = conf("CCM_INBOX_POST", os.path.join(HERE, "inbox_post.sh"))
KEEPER = conf("CCM_LIBRARY_KEEPER", "")
WRAPPERS = {"hook_safe.sh", "hook-safe.sh"}            # the wrapper is not a mechanism by itself
DISPATCHERS = {"stop_dispatch.sh", "stop-dispatch.sh"}  # runs the branches itself -> they inherit its event
# a path may contain one pair of brackets: `…Fallacy%20(2026).pdf`
LINE = re.compile(r"^\s*- ([IVX]+(?:\.[\w]+)+)\s+\[([^\]]*)\]\(((?:[^()\s]|\([^()\s]*\))+)\)(.*)$")
TAG_HOOK = re.compile(r"\{hook:([^}]+)\}")
MAX_SHOW = 25
FRESH_DIRS = os.environ.get("LIBCHECK_FRESH_DIRS", f"{CLAUDE_DIR}/scripts:{CLAUDE_DIR}/hooks:{CLAUDE_DIR}/bin").split(":")
FRESH_S = 24 * 3600
TRANSCRIPTS = os.environ.get("LIBCHECK_TRANSCRIPTS", os.path.join(HOME, ".claude", "projects", "*", "*.jsonl"))
IDENTITY = os.environ.get("LIBCHECK_IDENTITY", os.path.join(HOME, ".claude", "agent-identity"))


def lib_rows():
    rows = []
    for n, l in enumerate(open(LIB, encoding="utf-8").read().split("\n"), 1):
        m = LINE.match(l)
        if m:
            code, name, path, rest = m.groups()
            rows.append({"n": n, "code": code, "name": name, "path": path.strip("<>"), "rest": rest,
                         "retired": "~~" in name or "RETIRED" in rest.upper() or "СПИСАНО" in rest})
    return rows


def abspath(p):
    p = os.path.expanduser(unquote(p.split("#")[0]))  # `%20` in a markdown link
    return os.path.normpath(p if p.startswith("/") else os.path.join(REPO, p))


def scripts_in(cmd):
    """Script paths in a hook/cron command (without interpreters and the hook-safe wrapper)."""
    try:
        words = shlex.split(cmd, posix=True)
    except ValueError:
        words = cmd.split()
    out, prev = [], ""
    for w in words:
        w = w.rstrip(";&|")  # "script.py; sleep 5" in a cron loop
        was, prev = prev, w
        if was in (">", ">>", "2>", "2>>", "<", "&>"):  # a redirect target (`>> x.log`) is not a script
            continue
        w = w.split(">")[0]
        if not w.startswith("/") or w.startswith(("/usr/bin/", "/bin/", "/dev/")):
            continue
        if os.path.basename(w) in WRAPPERS:
            continue
        if re.search(r"\.(sh|py)$", w) or "/scripts/" in w or "/hooks/" in w:
            out.append(w)
    return out


def settings_hooks():
    """{script: {events}} from all settings.json files."""
    res = {}
    for sp in SETTINGS:
        try:
            s = json.load(open(sp))
        except (OSError, ValueError):
            continue
        for ev, groups in (s.get("hooks") or {}).items():
            for g in groups:
                for h in g.get("hooks", []):
                    for sc in scripts_in(h.get("command", "")):
                        res.setdefault(sc, set()).add(ev)
    # Dispatcher (stop-dispatch.sh): the scripts it runs inherit its events. Only the explicit DISPATCHERS: the
    # watchman merely MENTIONS inbox_post/cross-review in hint texts.
    for sc, evs in list(res.items()):
        if os.path.basename(sc) not in DISPATCHERS or not os.path.isfile(sc):
            continue
        body = "\n".join(re.sub(r"\s#.*$", "", l) for l in open(sc, encoding="utf-8", errors="replace")
                         if not l.lstrip().startswith("#"))  # a comment only MENTIONS a script - it is not a branch
        d = os.path.dirname(sc)
        names = set(re.findall(r"[\w.-]+\.(?:py|sh)", body))
        # the branches are arrays of bare names: BLOCKING=(a b) DETECTORS=(c d) -> hooks/<name>.py|.sh
        for arr in re.findall(r"^\s*(?:BLOCKING|DETECTORS|DET)=\((.*?)\)", body, re.S | re.M):
            for n in re.findall(r"[\w.-]+", arr):
                names |= {f"{n}.py", f"{n}.sh"}
        for name in names:
            child = os.path.join(d, name)
            if child != sc and os.path.isfile(child) and os.path.basename(child) not in WRAPPERS:
                res.setdefault(child, set()).update(evs)
    return res


def cron_scripts():
    res = set()
    for u in [None]:
        try:
            out = open(CRON_FILE).read() if CRON_FILE else \
                subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10).stdout
        except Exception:
            continue
        for l in out.split("\n"):
            l = l.strip()
            if not l or l.startswith("#") or re.match(r"^[A-Z_]+=", l):
                continue
            cmd = l.split(None, 1)[1] if l.startswith("@") else " ".join(l.split()[5:])
            res.update(scripts_in(cmd))
    return res


def fresh_uncatalogued():
    """(e) files changed within a day that are in neither LIBRARY nor SWARM-TOOLS (by basename)."""
    try:
        cat = open(LIB, encoding="utf-8").read() + open(conf("CCM_SWARM_TOOLS", f"{REPO}/SWARM-TOOLS.md"), encoding="utf-8").read()
    except OSError:
        cat = open(LIB, encoding="utf-8").read()
    now, out = __import__("time").time(), []
    for d in FRESH_DIRS:
        if not os.path.isdir(d):
            continue
        for n in os.listdir(d):
            fp = os.path.join(d, n)
            if (os.path.islink(fp) or not os.path.isfile(fp) or ".bak" in n or n.endswith((".pyc", ".log", ".tmp", ".new"))
                    or n.startswith(".") or now - os.path.getmtime(fp) > FRESH_S):
                continue
            if d.endswith("/bin") and not re.search(r"\.(sh|py)$|^[\w-]+$", n):
                continue
            if n not in cat and os.path.splitext(n)[0] not in cat:
                out.append(fp)
    return out


def author_of(fp):
    """The agent whose session wrote fp within a day (Write/Edit with this path, or Bash that writes into it) - from transcripts."""
    now = __import__("time").time()
    best = None
    for tp in glob.glob(TRANSCRIPTS):
        if now - os.path.getmtime(tp) > FRESH_S + 3600:
            continue
        try:
            txt = open(tp, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if fp not in txt:
            continue
        hit = False
        for l in txt.split("\n"):
            if fp not in l or '"tool_use"' not in l:
                continue
            # a write of exactly THIS file: > / >> before the path, mv/cp/install with it as the LAST argument, open(...,'w');
            # not any `>` in the line (a reader's 2>/dev/null once made it the "author")
            q = re.escape(fp)
            if re.search(r'"name":\s*"(?:Write|Edit|MultiEdit)"', l) or re.search(
                    rf"(?:>>?\s*['\\\"]*{q}|(?:mv|cp|install)\s[^;&|\n]*\s['\\\"]*{q}['\\\"]*(?:\s*(?:$|[;&|)\x7d\x22\\\\]|\\\\n))|open\(['\\\"]*{q}['\\\"]*\s*,\s*['\\\"]+w)", l) or (
                    re.search(rf"=\s*['\\\"]+{q}['\\\"]", l) and re.search(r"open\([^)]*,\s*['\\\"]+[wa]", l)):
                hit = True; break
        if hit:
            sid = os.path.basename(tp)[:-6]
            try:
                who = os.path.basename(open(f"{IDENTITY}/{sid}").read().strip().rstrip("/"))
            except OSError:
                who = None
            if who and (best is None or os.path.getmtime(tp) > best[1]):
                best = (who, os.path.getmtime(tp))
    return best[0] if best else None


def main():
    dry = "--dry" in sys.argv
    if not os.path.isfile(LIB):
        print(f"library_check: no {LIB} - nothing to check")
        return
    rows = lib_rows()
    by_path = {abspath(r["path"]): r for r in rows}
    by_base = {}
    for r in rows:
        by_base.setdefault(os.path.basename(abspath(r["path"])), []).append(r)

    def find(sc):
        r = by_path.get(os.path.normpath(sc))
        if r:
            return r
        c = by_base.get(os.path.basename(sc), [])
        return c[0] if len(c) == 1 else None

    issues = []
    # (a) paths
    for r in rows:
        if r["retired"] or re.match(r"^[a-z]+://", r["path"]):
            continue
        if not os.path.exists(abspath(r["path"])):
            issues.append(f"(a) LIBRARY.md:{r['n']} {r['code']} — path does not exist: {r['path']}")
    # (b) + (c)
    hooks = settings_hooks()
    for sc, evs in sorted(hooks.items()):
        r = find(sc)
        if not r:
            issues.append(f"(b) hook without a LIBRARY line: {sc} {{hook:{','.join(sorted(evs))}}}")
            continue
        tagged = {e.strip() for t in TAG_HOOK.findall(r["rest"]) for e in t.split(",")} - {"*", "<Event>"}
        if tagged != evs:
            issues.append(f"(c) LIBRARY.md:{r['n']} {r['code']} {os.path.basename(sc)} — tags {{hook:{','.join(sorted(tagged)) or '—'}}}, "
                          f"settings say {{hook:{','.join(sorted(evs))}}}")
    for r in rows:  # the tag hook:Event is there, but the script is not subscribed in settings
        tagged = {e.strip() for t in TAG_HOOK.findall(r["rest"]) for e in t.split(",")} - {"*", "<Event>", "none"}
        if tagged and not r["retired"] and not any(os.path.normpath(sc) == abspath(r["path"]) or
                                                   os.path.basename(sc) == os.path.basename(abspath(r["path"]))
                                                   for sc in hooks):
            issues.append(f"(c) LIBRARY.md:{r['n']} {r['code']} — tag {{hook:{','.join(sorted(tagged))}}}, but it is not subscribed in settings.json")
    for sc in sorted(cron_scripts()):
        if not find(sc):
            issues.append(f"(b) cron job without a LIBRARY line: {sc}")

    # (d) duplicate line numbers
    seen = {}
    for n, l in enumerate(open(LIB, encoding="utf-8").read().split("\n"), 1):
        m = re.match(r"^- ([IVX]+(?:\.\d+)+[a-z]?) ", l)
        if m:
            seen.setdefault(m.group(1), []).append(n)
    for code, ns in sorted(seen.items()):
        if len(ns) > 1:
            issues.append(f"(d) number {code} twice: LIBRARY.md lines {', '.join(map(str, ns))}")

    fresh = fresh_uncatalogued()
    by_author = {}
    for fp in fresh:
        who = author_of(fp)
        issues.append(f"(e) new/changed within a day without a line in LIBRARY and SWARM-TOOLS: {fp} (author: {who or 'unknown'})")
        if who:
            by_author.setdefault(who, []).append(fp)
    for who, fps in by_author.items():
        msg_a = (f"library_check: within a day you created/changed {len(fps)} mechanism file(s) with no line in LIBRARY.md "
                 f"or SWARM-TOOLS.md: {', '.join(fps)}. Add a line (what it does, when, test), otherwise for the swarm it "
                 "\"does not exist\".")
        if dry:
            print(f"→ {who}: {msg_a}")
        else:
            post(who, msg_a, critical=False)

    if not issues:
        print(f"{time.strftime('%F %T')} library_check: no differences")   # a success trace in prod too
        return
    body = "\n".join("  - " + i for i in issues[:MAX_SHOW])
    more = f"\n  - ... {len(issues) - MAX_SHOW} more" if len(issues) > MAX_SHOW else ""
    msg = (f"library_check: nightly LIBRARY vs reality: {len(issues)} difference(s) "
           f"(fix the line; a script/hook that is gone - remove the line or mark it retired):\n{body}{more}")
    if dry or not KEEPER:
        print(msg)
    else:
        print(f"{time.strftime('%F %T')} library_check: {len(issues)} difference(s) -> {KEEPER}")
        post(KEEPER, msg)


FAILED = []

def post(who, msg, critical=True):
    """A letter with the rc checked (a lost rc once meant silence in the log while the letter never went)."""
    r = subprocess.run([POST, who, msg], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        if critical:   # a failed letter to the author does not fail the run: a retry would repeat ALL letters
            FAILED.append(who)
        print(f"{time.strftime('%F %T')} library_check: WARNING letter to {who} NOT sent (rc {r.returncode}): {(r.stderr or r.stdout).strip()[:150]}")


if __name__ == "__main__":
    main()
    sys.exit(1 if FAILED else 0)   # a wrapper counts success by rc
