#!/usr/bin/env python3
"""What native Windows Python (python.org, under Git Bash) does differently, imitated here so it is tested on Linux too.
Each scenario runs the real script in a child Python whose sitecustomize.py (a temp folder first in PYTHONPATH) takes
away or bends one thing, selected by CCM_WINSIM:
  nochown   - os.chown/fchown/lchown do not exist (Windows: AttributeError, which `except OSError` does not catch)
  noeuid    - os.geteuid does not exist (Windows: no Unix owner; blockers.py trusts approvals by their place instead)
  notzdata  - zoneinfo finds no zone (Windows Python without the tzdata package: ZoneInfoNotFoundError)
  heldopen  - the first os.replace onto each path fails with PermissionError (WinError 32: an antivirus or the indexer
              holds the file for a moment); lib/ccm_fs sees os.name "nt" (only there: a global "nt" breaks os.path)
Sandbox: temp HOME and workspace, no config file. CCM_WIN_ROOT=<another checkout> tests that copy (e.g. an older
commit, to see a scenario red before its fix). Last line: windows-py-test: N pass, M fail."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.realpath(os.environ.get("CCM_WIN_ROOT") or os.path.dirname(HERE))
res = {"pass": 0, "fail": 0}

SITE = r'''
import os, sys
# only one sitecustomize is imported: run the one this folder hides (on Windows lib/pyshim's: \r\n -> \n in output)
_me = os.path.dirname(os.path.abspath(__file__))
for _d in sys.path:
    _f = os.path.join(_d, "sitecustomize.py")
    if _d and os.path.abspath(_d) != _me and os.path.isfile(_f):
        exec(compile(open(_f, encoding="utf-8").read(), _f, "exec"), {"__file__": _f, "__name__": "sitecustomize"})
        break
_sim = set(filter(None, os.environ.get("CCM_WINSIM", "").split(",")))
if "nochown" in _sim:
    for _n in ("chown", "fchown", "lchown"):
        if hasattr(os, _n):
            delattr(os, _n)
if "noeuid" in _sim and hasattr(os, "geteuid"):
    del os.geteuid
if "notzdata" in _sim:
    import zoneinfo
    def _nozone(key, *a, **k):
        raise zoneinfo.ZoneInfoNotFoundError(f"No time zone found with key {key}")
    zoneinfo.ZoneInfo = _nozone
if "heldopen" in _sim:
    _real, _held = os.replace, set()
    def _replace(src, dst, *a, **k):
        key = os.path.abspath(os.fspath(dst))
        if key not in _held:
            _held.add(key)
            with open(os.environ["CCM_WINSIM_LOG"], "a") as f:
                f.write("held " + key + "\n")
            raise PermissionError(13, "[WinError 32] The process cannot access the file because it is being used by another process", key)
        return _real(src, dst, *a, **k)
    os.replace = _replace
    sys.path.insert(0, os.environ["CCM_WINSIM_LIB"])
    try:
        import ccm_fs
        class _NtOs:
            name = "nt"
            def __getattr__(self, n):
                return getattr(os, n)
        ccm_fs.os = _NtOs()
    except ImportError:
        pass
'''


def check(cond, what, extra=""):
    if cond:
        res["pass"] += 1
        print(f"ok   {what}")
    else:
        res["fail"] += 1
        print(f"FAIL {what} {extra}")


def run(T, sim, argv, env=None, stdin=None, timeout=60):
    """argv[0] = a path relative to ROOT (a .py runs on this Python, a .sh on bash); -> (rc, stdout + stderr)"""
    e = {k: v for k, v in os.environ.items() if not k.startswith(("CCM_", "BLOCKERS_", "STORY_ADD_", "ACCEPT_"))}
    e.update({"HOME": os.path.join(T, "home"), "USERPROFILE": os.path.join(T, "home"), "CCM_TEST": "1",
              "CLAUDE_METHODOLOGY_CONF": os.path.join(T, "none.conf"), "CCM_WINSIM": sim,
              "CCM_WINSIM_LOG": os.path.join(T, "winsim.log"), "CCM_WINSIM_LIB": os.path.join(ROOT, "lib"),
              "PYTHONPATH": os.path.join(T, "site") + os.pathsep + os.environ.get("PYTHONPATH", "")})
    e.update(env or {})
    script = os.path.join(ROOT, argv[0])
    cmd = (["bash", script] if script.endswith(".sh") else [sys.executable, script]) + list(argv[1:])
    p = subprocess.run(cmd, env=e, input=stdin, capture_output=True, text=True, timeout=timeout, cwd=T)
    return p.returncode, p.stdout + p.stderr


def held(T):
    """paths the heldopen imitation refused once (proof that the imitation was hit at all); the log is emptied"""
    p = os.path.join(T, "winsim.log")
    try:
        lines = open(p).read().split()
        os.remove(p)
    except OSError:
        return []
    return [x for x in lines if x != "held"]


# ccm_fs itself; supervisor/trash-guard: separate work; releaser/repo_stale run as root on a Linux server only (fcntl, pwd,
# runuser at import time) and must stay runnable from a copy with just lib/ccm_conf.py (releaser-test 16)
SKIP_F = {"lib/ccm_fs.py", "scripts/supervisor.py", "hooks/trash-guard.py", "scripts/releaser.py", "scripts/repo_stale.py"}


def fresh(T, name):
    d = os.path.join(T, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    return d


def main():
    T = tempfile.mkdtemp(prefix="windows-py-test.")
    try:
        os.makedirs(os.path.join(T, "home"))
        os.makedirs(os.path.join(T, "site"))
        with open(os.path.join(T, "site", "sitecustomize.py"), "w") as f:
            f.write(SITE)
        print(f"testing {ROOT}")

        # --- (a) no os.chown ------------------------------------------------------------------------------------
        ws = fresh(T, "ws-a")
        pd = os.path.join(ws, "Project-G")
        os.makedirs(pd)
        open(os.path.join(pd, "ROADMAP.md"), "w").write("# G\n\n## EPIC 1 - One\n- ⏳ **[E1.S1] first**\n")
        rc, out = run(T, "nochown", ["scripts/story_add.py", "G", "second thing", "--epic", "E1"], {"STORY_ADD_REPO": ws})
        check(rc == 0 and "Traceback" not in out and "[E1.S2] second thing" in open(os.path.join(pd, "ROADMAP.md")).read(),
              "a1 story_add.py without os.chown -> rc 0, the story is in ROADMAP", f"rc={rc} {out[-600:]!r}")

        acc = os.path.join(pd, "ACCEPTED.jsonl")
        code = ("import importlib.machinery, importlib.util, sys\n"
                "l = importlib.machinery.SourceFileLoader('acc', sys.argv[1]); s = importlib.util.spec_from_loader('acc', l)\n"
                "m = importlib.util.module_from_spec(s); l.exec_module(m)\n"
                "print('appended:', m.append_jsonl(sys.argv[2], {'story': 'E1.S1'}, ('story',)))\n")
        open(os.path.join(T, "acc_append.py"), "w").write(code)
        e = dict(os.environ, HOME=os.path.join(T, "home"), CLAUDE_METHODOLOGY_CONF=os.path.join(T, "none.conf"),
                 CCM_WINSIM="nochown", ACCEPT_REPO=ws,
                 PYTHONPATH=os.path.join(T, "site") + os.pathsep + os.environ.get("PYTHONPATH", ""))
        p = subprocess.run([sys.executable, os.path.join(T, "acc_append.py"), os.path.join(ROOT, "scripts", "accept.py"), acc],
                           env=e, capture_output=True, text=True, timeout=60)
        check(p.returncode == 0 and "appended: True" in p.stdout and os.path.isfile(acc),
              "a2 accept.py append_jsonl without os.chown -> a new ACCEPTED.jsonl, no AttributeError",
              f"rc={p.returncode} {(p.stdout + p.stderr)[-600:]!r}")

        open(os.path.join(pd, "BLOCKERS.md"), "w").write(
            "| No | What | Who | Check | Date |\n|---|---|---|---|---|\n| B1 | a talk | human | `manual` | 2026-11-20 |\n")
        rc, out = run(T, "nochown", ["scripts/blockers.py", "clear", "G", "B1", "the human"],
                      {"BLOCKERS_REPO": ws, "BLOCKERS_STATE": os.path.join(T, "bl-state-a"), "BLOCKERS_POST": "/nonexistent"})
        check(rc == 0 and "Traceback" not in out and "| ✅ B1 |" in open(os.path.join(pd, "BLOCKERS.md")).read(),
              "a3 blockers.py clear (rewrites BLOCKERS.md) without os.chown -> rc 0, ✅ B1", f"rc={rc} {out[-600:]!r}")

        rws = fresh(T, "ws-ra")
        for a in ("Old-Ops", "Other"):
            os.makedirs(os.path.join(rws, "Agents", a))
            open(os.path.join(rws, "Agents", a, "briefing.md"), "w").write(f"# {a}\nAsk Old-Ops about deploys.\n")
        os.makedirs(os.path.join(T, "home", ".claude", "agent-identity"), exist_ok=True)
        rc, out = run(T, "nochown", ["scripts/rename_agent.sh", "Old-Ops", "New-Ops", "--apply"],
                      {"CCM_WORKSPACE": rws, "CCM_AGENTS_DIR": os.path.join(rws, "Agents"),
                       "CCM_ALARM_MODE_DIR": os.path.join(T, "mode-ra"), "CCM_WORK_GUARD_AGENTS": os.path.join(T, "wga-ra")})
        other = open(os.path.join(rws, "Agents", "Other", "briefing.md")).read()
        check(rc == 0 and "Traceback" not in out and "Ask New-Ops" in other,
              "a4 rename_agent.sh --apply (rewrites briefings) without os.chown -> rc 0, mention renamed",
              f"rc={rc} {out[-800:]!r}")

        # --- (f) a file held open by another process for a moment ----------------------------------------------------
        left = []
        for top in ("hooks", "scripts", "lib", "bin", "mcp", "addons"):
            for d, dirs, files in os.walk(os.path.join(ROOT, top)):
                dirs[:] = [x for x in dirs if x not in ("tests", "node_modules", "__pycache__", "engine")]
                for n in files:
                    rel = os.path.relpath(os.path.join(d, n), ROOT).replace(os.sep, "/")
                    if rel in SKIP_F:
                        continue
                    try:
                        text = open(os.path.join(d, n), encoding="utf-8").read()
                    except (OSError, UnicodeDecodeError):
                        continue
                    left += [f"{rel}:{i}" for i, l in enumerate(text.split("\n"), 1)
                             if re.search(r"(?<![\w.])os\.replace\(", l)]
        check(not left, "f1 no bare os.replace( left in hooks/ scripts/ lib/ bin/ mcp/ addons/ (ccm_fs.replace instead)",
              " ".join(left[:20]))

        ws = fresh(T, "ws-f")
        pd = os.path.join(ws, "Project-G")
        os.makedirs(pd)
        open(os.path.join(pd, "ROADMAP.md"), "w").write("# G\n\n## EPIC 1 - One\n- ⏳ **[E1.S1] first**\n")
        held(T)
        rc, out = run(T, "heldopen", ["scripts/story_add.py", "G", "second thing", "--epic", "E1"], {"STORY_ADD_REPO": ws})
        h = held(T)
        check(rc == 0 and h and "[E1.S2] second thing" in open(os.path.join(pd, "ROADMAP.md")).read(),
              "f2 story_add.py, ROADMAP held open for a moment -> rc 0, the story written", f"rc={rc} held={h} {out[-600:]!r}")

        open(os.path.join(pd, "BLOCKERS.md"), "w").write(
            "| No | What | Who | Check | Date |\n|---|---|---|---|---|\n| B1 | a talk | human | `manual` | 2026-11-20 |\n"
            "| B2 | a flag | human | `true` | 2026-11-20 |\n")
        benv = {"BLOCKERS_REPO": ws, "BLOCKERS_STATE": os.path.join(T, "bl-state-f"), "BLOCKERS_POST": "/nonexistent"}
        rc, out = run(T, "heldopen", ["scripts/blockers.py", "clear", "G", "B1", "the human"], benv)
        rc2, out2 = run(T, "heldopen", ["scripts/blockers.py", "approve", "G", "B2"], benv)
        h = held(T)
        check(rc == 0 and rc2 == 0 and len(h) >= 2 and "| ✅ B1 |" in open(os.path.join(pd, "BLOCKERS.md")).read()
              and os.path.isfile(os.path.join(T, "bl-state-f", "approved-checks.json")),
              "f3 blockers.py clear + approve, both files held open for a moment -> ✅ B1 and the approval written",
              f"rc={rc}/{rc2} held={h} {(out + out2)[-600:]!r}")

        hin = json.dumps({"session_id": "abcdef1234", "compact_summary": "summary text"})
        rc, out = run(T, "heldopen", ["hooks/postcompact-archive.sh"], stdin=hin)
        logs = glob.glob(os.path.join(T, "home", ".claude", "compaction-log", "abcdef12-*.md"))
        h = held(T)
        check(rc == 0 and h and len(logs) == 1 and "summary text" in open(logs[0]).read(),
              "f4 postcompact-archive.sh (Python inside bash), the new file held for a moment -> the summary is filed",
              f"rc={rc} held={h} files={logs} {out[-400:]!r}")

        # --- (g) blockers.py approvals on Windows: trusted by place (inside the profile, no link), not by owner/mode ---
        ws = fresh(T, "ws-g")
        pd = os.path.join(ws, "Project-G")
        os.makedirs(pd)
        open(os.path.join(pd, "BLOCKERS.md"), "w").write(
            "| No | What | Who | Check | Date |\n|---|---|---|---|---|\n"
            f"| B1 | a flag | human | `touch {T.replace(os.sep, '/')}/g-flag` | 2026-11-20 |\n")   # bash eats \\
        reg = os.path.join(pd, "BLOCKERS.md")

        def g_run(state=None, approved=None, approve=True):
            if os.path.exists(os.path.join(T, "g.log")):
                os.remove(os.path.join(T, "g.log"))
            e = {"BLOCKERS_REPO": ws, "BLOCKERS_POST": "/nonexistent", "BLOCKERS_LOG": os.path.join(T, "g.log")}
            if state:
                e["BLOCKERS_STATE"] = state
            if approved:
                e["BLOCKERS_APPROVED"] = approved
            rc1, o1 = run(T, "nochown,noeuid", ["scripts/blockers.py", "approve", "G", "B1"], e) if approve else (0, "")
            rc2, o2 = run(T, "nochown,noeuid", ["scripts/blockers.py", "run"], e)
            log = open(os.path.join(T, "g.log")).read() if os.path.exists(os.path.join(T, "g.log")) else ""
            return rc1, rc2, o1 + o2, log

        outside = os.path.join(T, "g-outside")   # T itself is not in the (imitated) profile T/home
        rc1, rc2, out, log = g_run(state=outside)
        check(not os.path.exists(os.path.join(T, "g-flag")) and "outside the user's profile folder" in log
              and "| B1 |" in open(reg).read(),
              "g1 Windows: approvals file outside the profile folder -> the command is not run, the reason logged",
              f"rc={rc1}/{rc2} {(out + log)[-600:]!r}")

        try:
            os.symlink(outside, os.path.join(T, "home", "g-linkdir"), target_is_directory=True)
        except OSError as e:   # Windows without developer mode or admin rights
            print(f"SKIP g2: cannot make a symlink here ({e})")
        else:
            rc1, rc2, out, log = g_run(approved=os.path.join(T, "home", "g-linkdir", "approved-checks.json"))
            check(not os.path.exists(os.path.join(T, "g-flag")) and "outside the user's profile folder" in log,
                  "g2 Windows: approvals in a profile folder that is a link to outside -> resolved, not run",
                  f"rc={rc1}/{rc2} {(out + log)[-600:]!r}")

        os.makedirs(os.path.join(T, "home", "g-hl"))
        os.link(os.path.join(outside, "approved-checks.json"), os.path.join(T, "home", "g-hl", "approved-checks.json"))
        # not approved again: approve rewrites the file (tmp + replace), which would drop the second link
        rc1, rc2, out, log = g_run(approved=os.path.join(T, "home", "g-hl", "approved-checks.json"), approve=False)
        check(not os.path.exists(os.path.join(T, "g-flag")) and "another hard link" in log,
              "g3 Windows: approvals in the profile with a second hard link elsewhere -> not run",
              f"rc={rc1}/{rc2} {(out + log)[-600:]!r}")

        rc1, rc2, out, log = g_run()   # the default place: ~/.claude/blockers/approved-checks.json
        check(rc1 == 0 and os.path.exists(os.path.join(T, "g-flag")) and "| ✅ B1 |" in open(reg).read(),
              "g4 Windows: approvals in ~/.claude/blockers (the profile), approved command -> run, ✅ B1",
              f"rc={rc1}/{rc2} {(out + log)[-600:]!r}")

        # --- (h) CCM_TIMEZONE without a zone database ----------------------------------------------------------------
        code = ("import sys, datetime; sys.path.insert(0, sys.argv[1]); import ccm_time\n"
                "a = ccm_time.zone('Asia/Dubai'); b = ccm_time.zone('Asia/Dubai'); u = ccm_time.zone('UTC')\n"
                "print('zones:', a, b, u is datetime.timezone.utc, ccm_time.zone(''))\n")
        e = dict(os.environ, CCM_WINSIM="notzdata",
                 PYTHONPATH=os.path.join(T, "site") + os.pathsep + os.environ.get("PYTHONPATH", ""))
        p = subprocess.run([sys.executable, "-c", code, os.path.join(ROOT, "lib")], env=e, capture_output=True, text=True,
                           timeout=60)
        check(p.returncode == 0 and "zones: None None True None" in p.stdout and p.stderr.count("pip install tzdata") == 1,
              "h1 lib/ccm_time.zone without tzdata: a name -> None (system zone) with ONE warning, UTC works anyway",
              f"rc={p.returncode} {(p.stdout + p.stderr)[-500:]!r}")

        ws = fresh(T, "ws-h")
        os.makedirs(os.path.join(ws, "Project-H"))
        open(os.path.join(ws, "Project-H", "ROADMAP.md"), "w").write(
            "# H\n\n## EPIC 1 - One 🔄\n- ✅ **[E1.S1] first**\n- ⏳ **[E1.S2] second**\n")
        stats = os.path.join(T, "stats-h")
        rc, out = run(T, "notzdata", ["scripts/stats_projects.py"],
                      {"CCM_WORKSPACE": ws, "STATS_DIR": stats, "CCM_TIMEZONE": "Asia/Dubai"})
        check(rc == 0 and "Traceback" not in out and os.path.isfile(os.path.join(stats, "projects.json"))
              and out.count("pip install tzdata") == 1,
              "h2 stats_projects.py, CCM_TIMEZONE=Asia/Dubai without tzdata -> projects.json written, one warning",
              f"rc={rc} {out[-600:]!r}")

        rc, out = run(T, "notzdata", ["scripts/token_daily_report.py"],
                      {"CCM_TIMEZONE": "Asia/Dubai", "CLAUDE_PROJECTS_DIR": os.path.join(T, "no-projects"),
                       "TOKEN_REPORT_DIR": os.path.join(T, "tok-h")})
        check(rc == 0 and "Traceback" not in out and out.count("pip install tzdata") == 1,
              "h3 token_daily_report.py, CCM_TIMEZONE=Asia/Dubai without tzdata -> no traceback, one warning",
              f"rc={rc} {out[-600:]!r}")
    finally:
        shutil.rmtree(T, ignore_errors=True)
    print(f"windows-py-test: {res['pass']} pass, {res['fail']} fail")
    return 0 if res["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
