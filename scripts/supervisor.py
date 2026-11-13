#!/usr/bin/env python3
"""supervisor.py - the swarm's watchman over its own machinery. Cron every 15 minutes.

Why: a restart policy only knows "the process is up". A bot once sat `active` for a month with 825 restarts and did
no work. The supervisor runs a registry of FUNCTIONAL checks (does the mechanism still do its job?) and reports the
red ones:
  1. a service check fails -> `systemctl restart <service>` (only for checks that name a `service`) -> re-check;
  2. >= max_restarts_hour restarts in an hour (ours or systemd's NRestarts) -> restarts STOP, the owner is told;
  3. a red check -> a letter into the OWNER agent's inbox (check field `owner`: a name or a list; empty = no letter),
     through scripts/inbox_post.sh; the same alarm is not sent again for 6 h and not while the previous copy still sits
     in the owner's "New" section;
  4. severity "human" -> additionally a one-line flag for every live Claude Code session
     (~/.claude/supervisor-flags/<session_id>, shown once by hooks/surface-flags.sh on the next prompt);
  5. "CHECK BROKEN" is not "the object is down": a cmd that exits 126/127 (command missing) or 3 (UNKNOWN: could not
     measure, the Nagios convention), prints a Python traceback, or raises inside the engine -> no restart, ONE letter to
     the infra agent (config CCM_INFRA_AGENT; none set -> to the owner), nobody else. (Two LAN checks once screamed as
     outages for 17 hours when the measuring itself could not run.)
  6. silence after downtime: checks about AGE ("nothing updated for N min") all turn red together after a machine
     was off. The engine measures its OWN gap between runs (uptime lies: a paused VM keeps it); a gap over
     SUPERVISOR_GAP_MIN (20) minutes = downtime, and age checks stay quiet until their own age limit passes.
  7. every run writes <state>/summary.json (what is red), <state>/heartbeat (epoch) and a log line; if config
     CCM_SUPERVISOR_HEARTBEAT is set that file gets the epoch too (the briefing watchman warns when it is stale).

The ENGINE is generic; the REGISTRY is the machine's data (default <state>/checks.json; a template with the checks
shipped in this repo is config/supervisor-checks.template.json, `--init` copies it). `__CLAUDE_DIR__` and `__HOME__`
in the registry are replaced when it is read.

Check kinds: http | tcp | cmd | fresh (file age) | journal (a fresh line in journalctl) | hooks (hook files of
settings.json exist) | system (/dev/null is a device, free space). Fields: name, kind, severity (human|infra), owner,
service, max_restarts_hour, ok_rc (cmd: rc values that are green, default [0]), recheck_before_restart_s, restart_only_if_dead, grace_min, timeout_s, only_if_exists,
enabled (false = skipped), project (see CCM_SUPERVISOR_PAUSED), note.
Nothing here deletes anything.

Usage: supervisor.py [--checks F] [--state DIR] [--dry-run] [--only NAME] [--init TEMPLATE]
Config: CCM_SUPERVISOR_DIR (state dir, default ~/.claude/supervisor) · CCM_SUPERVISOR_LOG · CCM_SUPERVISOR_CHECKS ·
CCM_SUPERVISOR_PAUSED (file: project names, one per line, whose checks are skipped) · CCM_INFRA_AGENT ·
CCM_SUPERVISOR_HEARTBEAT · CCM_AGENTS_DIR · CCM_HUMAN_NAME · CCM_CLAUDE_DIR.
Env for tests: SUPERVISOR_POST (the inbox_post script), SUPERVISOR_SESSIONS, SUPERVISOR_FLAGS, SUPERVISOR_GAP_MIN,
SUPERVISOR_RECHECK_S, SUPERVISOR_FLAP_S, SUPERVISOR_HUMAN_RECHECK_S, SUPERVISOR_SETTINGS."""
import argparse, glob, json, os, re, socket, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402

HOME = os.path.expanduser("~")
STATE_DIR = conf("CCM_SUPERVISOR_DIR", "") or os.path.join(HOME, ".claude", "supervisor")
DEDUP_S = 6 * 3600
BROKEN_RC = (3, 126, 127)   # 3 = UNKNOWN (Nagios): the check could not measure
HOUR = 3600
LOG = None                  # set in main() once the state dir is known


def sh(cmd, timeout=20):
    try:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def nrestarts(unit):
    rc, out = sh(f"systemctl show {unit} -p NRestarts --value")
    return int(out) if rc == 0 and out.isdigit() else None


# ── checks: -> (ok, detail)
def check(c):
    k = c["kind"]
    guard = c.get("only_if_exists")
    if guard and not os.path.exists(os.path.expanduser(guard)):
        return True, "off (precondition missing)"
    if k == "http":
        try:
            with urllib.request.urlopen(c["url"], timeout=5) as r:
                return r.status == 200, f"HTTP {r.status}"
        except Exception as e:
            return False, f"HTTP: {str(e)[:80]}"
    if k == "tcp":
        try:
            socket.create_connection((c["host"], c["port"]), timeout=3).close()
            return True, "port open"
        except OSError as e:
            return False, f"port {c['port']}: {e.strerror or e}"
    if k == "cmd":
        rc, out = sh(c["cmd"], c.get("timeout_s", 20))
        if rc in BROKEN_RC or "Traceback (most recent call last)" in out:
            c["_broken"] = True
            why = {126: "command not executable", 127: "command not found", 3: "could not measure (UNKNOWN)"}.get(rc, "Python traceback")
            return False, f"rc={rc} {why}: {out[-80:]}"
        good = rc in c.get("ok_rc", [0])      # ok_rc: for a check whose "other" answers are information, not failure
        return good, "ok" if good else f"rc={rc} {out[-80:]}"
    if k == "fresh":
        p = os.path.expanduser(c["path"])
        try:
            age = (time.time() - os.path.getmtime(p)) / 60
        except OSError:
            return False, f"missing {p}"
        return age <= c["max_age_min"], f"age {age:.0f} min (limit {c['max_age_min']})"
    if k == "journal":
        rc, out = sh(f"journalctl -u {c['unit']} --since '-{c['max_silence_min']}min' --no-pager -q | wc -l")
        n = int(out) if out.isdigit() else 0
        return n > 0, f"{n} lines in {c['max_silence_min']} min"
    if k == "hooks":
        return check_hooks()
    if k == "system":
        return check_system(c)
    return False, f"unknown kind {k}"


def missing_imports(py):
    """modules a script imports that exist neither next to it nor among the installed ones"""
    import importlib.util
    try:
        src = open(py, encoding="utf-8").read()
    except OSError:
        return []
    out = []
    for a, b in set(re.findall(r"(?m)^\s*(?:from\s+([\w]+)[\w.]*\s+import|import\s+([\w]+))", src)):
        mod = a or b
        if os.path.isfile(os.path.join(os.path.dirname(py), mod + ".py")):
            continue
        if os.path.isfile(os.path.join(os.path.dirname(py), "..", "lib", mod + ".py")):
            continue
        try:
            if importlib.util.find_spec(mod) is not None:
                continue
        except (ImportError, ValueError):
            pass
        out.append(f"no module {mod} (imported by {os.path.basename(py)})")
    return out


def hook_paths(cmd):
    """-> [(path, called DIRECTLY)] for the scripts named in a hook command. After python3/bash +x is not needed."""
    import shlex
    try:
        toks = shlex.split(cmd)
    except ValueError:
        toks = cmd.split()
    out = []
    for i, tok in enumerate(toks):
        if tok.startswith("/") and ("/scripts/" in tok or "/hooks/" in tok):
            out.append((tok, not (i and os.path.basename(toks[i - 1]) in ("python3", "python", "bash", "sh"))))
    return out


def dispatch_branches(path):
    """names in the BLOCKING=(...) / DETECTORS=(...) arrays of a *-dispatch.sh: the dispatcher SKIPS a branch whose
    file is missing without a word, which is exactly a silently disabled gate"""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return []
    names = []
    for body in re.findall(r"(?m)^[A-Z_]+=\(([^)]*)\)", text):
        names += body.split()
    return names


def check_hooks():
    """Hook files of settings.json exist; the ones called directly are executable; the branches of the stop
    dispatcher exist; a hook's imports resolve (a gate whose helper module is gone is silently off)."""
    settings = os.environ.get("SUPERVISOR_SETTINGS") or os.path.join(conf("CCM_CLAUDE_DIR"), "settings.json")
    try:
        s = json.load(open(settings))
    except (OSError, ValueError) as e:
        return False, f"settings.json: {e}"
    bad, seen = [], set()
    for ev in s.get("hooks", {}).values():
        for grp in ev:
            for h in grp.get("hooks", []):
                for tok, direct in hook_paths(h.get("command", "")):
                    if (tok, direct) in seen:
                        continue
                    seen.add((tok, direct))
                    if not os.path.isfile(tok):
                        bad.append(f"missing {os.path.basename(tok)}")
                        continue
                    if direct and not os.access(tok, os.X_OK):
                        bad.append(f"no +x {os.path.basename(tok)}")
                    if tok.endswith("-dispatch.sh"):
                        for n in dispatch_branches(tok):
                            if not os.path.isfile(os.path.join(os.path.dirname(tok), n + ".py")):
                                bad.append(f"dispatch branch {n}: no {n}.py")
                    if tok.endswith(".py"):
                        bad += missing_imports(tok)
    return (not bad), ("; ".join(sorted(set(bad))) if bad else f"all in place ({len({t for t, _ in seen})})")


def check_system(c):
    bad = []
    import stat
    try:
        if not stat.S_ISCHR(os.stat("/dev/null").st_mode):
            bad.append("/dev/null is NOT a device")
    except OSError:
        bad.append("/dev/null is gone")
    for path, lim in (("/", c.get("min_free_root_pct", 5)), ("/tmp", c.get("min_free_tmp_pct", 5))):
        st = os.statvfs(path)
        free = 100 * st.f_bavail / st.f_blocks if st.f_blocks else 100
        if free < lim:
            bad.append(f"{path} {free:.0f}% free (<{lim}%)")
    return (not bad), ("; ".join(bad) if bad else "ok")


# ── state, messages
GAP_S = int(os.environ.get("SUPERVISOR_GAP_MIN", "20")) * 60      # cron every 15 min -> over 20 min of silence = downtime
AGE_CMD = re.compile(r"stat -c %Y|cron_state_check")


def grace_s(c):
    """seconds of silence after downtime: `grace_min` of the check, else its own age limit; 0 = not an age check"""
    if "grace_min" in c:
        return c["grace_min"] * 60
    if c.get("kind") == "fresh":
        return c.get("max_age_min", 60) * 60
    if c.get("kind") == "journal":
        return c.get("max_silence_min", 60) * 60
    if c.get("kind") == "cmd" and AGE_CMD.search(str(c.get("cmd", ""))):
        return 3600
    return 0


def load_state(d):
    try:
        return json.load(open(f"{d}/state.json"))
    except (OSError, ValueError):
        return {}


def save_state(d, st):
    tmp = f"{d}/state.json.tmp"
    json.dump(st, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, f"{d}/state.json")


def log(line):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')} {line}\n")
    except OSError:
        pass


def inbox_path(agent_or_path):
    if os.path.isfile(agent_or_path):
        return agent_or_path
    root = conf("CCM_AGENTS_DIR")
    for p in (f"{root}/{agent_or_path}/inbox.md", f"{root}/{agent_or_path}-agent/inbox.md",
              *glob.glob(f"{root}/*/{agent_or_path}/inbox.md")):
        if os.path.isfile(p):
            return p
    return None


def pending(agent_or_path, name):
    """an alarm about this check still sits in the addressee's "New" section -> do not send another"""
    p = inbox_path(agent_or_path)
    if not p:
        return False
    sect = False
    for l in open(p, encoding="utf-8", errors="replace").read().split("\n"):
        if l.startswith("## "):
            sect = l.startswith(("## New", "## Нові"))
        elif sect and l.startswith("- [ ]") and "Supervisor" in l and f"«{name}»" in l:
            return True
    return False


def post_inbox(agent_or_path, text):
    post = os.environ.get("SUPERVISOR_POST") or os.path.join(HERE, "inbox_post.sh")
    try:
        r = subprocess.run([post, agent_or_path, text], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:   # an rc != 0 used to vanish: the log said ALERT, the letter never went out
            log(f"INBOX not sent ({agent_or_path}): rc {r.returncode} {(r.stderr or r.stdout).strip()[:100]}")
            return False
        return True
    except Exception as e:
        log(f"INBOX not sent ({agent_or_path}): {str(e)[:100]}")
        return False


def live_sessions():
    """session ids of running Claude Code tabs (~/.claude/sessions/*.json with a live pid)"""
    d = os.environ.get("SUPERVISOR_SESSIONS") or os.path.join(HOME, ".claude", "sessions")
    out = []
    for p in glob.glob(f"{d}/*.json"):
        try:
            j = json.load(open(p))
            os.kill(int(j["pid"]), 0)
            out.append(j["sessionId"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def human_flag(text):
    """the finished hint for hooks/surface-flags.sh: ~/.claude/supervisor-flags/<session_id>; no live session -> nothing"""
    d = os.environ.get("SUPERVISOR_FLAGS") or os.path.join(HOME, ".claude", "supervisor-flags")
    sids = live_sessions()
    if not sids:
        log(f"FLAG not shown (no live session): {text[:80]}")
        return 0
    os.makedirs(d, exist_ok=True)
    for sid in sids:
        try:
            with open(os.path.join(d, sid), "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
    return len(sids)


def render_registry(raw):
    cdir = conf("CCM_CLAUDE_DIR")
    esc = lambda s: json.dumps(s)[1:-1]
    return raw.replace("__CLAUDE_DIR__", esc(cdir)).replace("__HOME__", esc(HOME))


def main():
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--checks", default=conf("CCM_SUPERVISOR_CHECKS", "") or f"{STATE_DIR}/checks.json")
    ap.add_argument("--state", default=STATE_DIR)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--init", metavar="TEMPLATE", help="copy a registry template to --checks (if it does not exist) and exit")
    a = ap.parse_args()
    os.makedirs(a.state, exist_ok=True)
    LOG = os.environ.get("SUPERVISOR_LOG") or conf("CCM_SUPERVISOR_LOG", "") or os.path.join(a.state, "supervisor.log")
    if a.init:
        if os.path.exists(a.checks):
            print(f"{a.checks} exists - left alone"); return
        os.makedirs(os.path.dirname(os.path.abspath(a.checks)), exist_ok=True)
        open(a.checks, "w", encoding="utf-8").write(render_registry(open(a.init, encoding="utf-8").read()))
        print(f"wrote {a.checks}"); return
    import fcntl   # overlapping runs (a slow restart + the next cron tick) used to write state.json against each other
    lk = open(os.path.join(a.state, ".lock"), "a")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("the previous supervisor run is still going - skipped"); return
    infra = conf("CCM_INFRA_AGENT", "") or ""
    human = conf("CCM_HUMAN_NAME")
    flag_on = not a.dry_run
    try:
        checks = json.loads(render_registry(open(a.checks, encoding="utf-8").read()))["checks"]
    except (OSError, ValueError, KeyError) as e:
        log(f"REGISTRY unreadable {a.checks}: {e}")
        print(f"supervisor: cannot read the registry {a.checks}: {e}", file=sys.stderr); sys.exit(2)
    st = load_state(a.state)
    now = time.time()
    problems, broken_l, report, after_l, details = [], [], [], [], []
    try:
        prev_hb = int(open(f"{a.state}/heartbeat").read().strip())
    except (OSError, ValueError):
        prev_hb = None
    meta = st.setdefault("__meta", {})
    if prev_hb and now - prev_hb > GAP_S:
        meta["resumed_at"] = now
        log(f"RESUME the supervisor did not run for {int((now - prev_hb) / 60)} min (machine off/paused) - age checks stay quiet until their own limit")
    resumed = meta.get("resumed_at", 0)
    paused = set()
    pf = conf("CCM_SUPERVISOR_PAUSED", "")
    if pf:   # projects on pause: their checks do not run and send no letters; remove from the list -> alive again
        try:
            paused = {l.strip() for l in open(pf, encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")}
        except OSError:
            pass
    for c in checks:
        if a.only and c["name"] != a.only:
            continue
        if c.get("enabled") is False:
            report.append(f"- {c['name']}: disabled in the registry")
            continue
        if c.get("project") in paused:
            report.append(f"⏸ {c['name']}: project {c['project']} is paused")
            continue
        s = st.setdefault(c["name"], {"restarts": [], "last_alert": 0, "nr": []})
        s["restarts"] = [t for t in s["restarts"] if now - t < HOUR]
        c.pop("_broken", None)
        try:
            ok, det = check(c)
        except Exception as e:  # one bad check must not take the whole run down
            ok, det = False, f"check crashed: {type(e).__name__}: {str(e)[:80]}"
            c["_broken"] = True
        broken = bool(c.get("_broken")) and not ok
        g = grace_s(c)
        if not ok and not broken and g and now - resumed < g:
            det = " ".join(str(det).split())
            report.append(f"⏳ {c['name']}: {det} - after downtime, waiting until {time.strftime('%H:%M', time.localtime(resumed + g))}")
            after_l.append(c["name"])
            continue
        unit = c.get("service")
        loop = False
        if unit:   # systemd's own restart loop (the bot: 825 restarts while "active")
            n = nrestarts(unit)
            if n is not None:
                s["nr"] = [x for x in s["nr"] if now - x[0] < HOUR] + [[now, n]]
                grew = s["nr"][-1][1] - min(x[1] for x in s["nr"])   # minimum in the window: the counter resets with the unit
                if grew > c.get("max_restarts_hour", 3):
                    loop, ok = True, False
                    det += f"; systemd restarted it {grew}x in an hour"
        # a short outage of someone else's network/API is not cured by a restart, and a restart cuts the service's work.
        # Registry field: a second try BEFORE the restart; restart only when the service itself is dead.
        if not ok and unit and not loop and not broken and c.get("recheck_before_restart_s"):
            time.sleep(int(os.environ.get("SUPERVISOR_FLAP_S", c["recheck_before_restart_s"])))
            try:
                ok, det2 = check(c)
            except Exception as e:
                ok, det2 = False, f"check crashed: {type(e).__name__}"
            if ok:
                log(f"FLAP {c['name']}: {' '.join(str(det).split())} -> second try ok, no restart")
                det = f"{det2} (short outage)"
        action = ""
        if not ok and unit and not loop and not broken and c.get("restart_only_if_dead") and sh(f"systemctl is-active -q {unit}")[0] == 0:
            action = "the service is alive, a restart does not cure it"
        elif not ok and unit and not loop and not broken and len(s["restarts"]) < c.get("max_restarts_hour", 3):
            if a.dry_run:
                action = "(dry-run: restart skipped)"
            else:
                sh(f"systemctl restart {unit}", timeout=60)
                s["restarts"].append(now)
                time.sleep(int(os.environ.get("SUPERVISOR_RECHECK_S", "15")))
                try:
                    ok, det2 = check(c)
                except Exception as e:
                    ok, det2 = False, f"check crashed: {type(e).__name__}"
                action = f"restart #{len(s['restarts'])}/h -> {'cured' if ok else 'did not help'}"
                log(f"RESTART {c['name']} ({unit}): {det} -> {det2}")
                det = det2 if ok else det
        det = " ".join(str(det).split())   # a newline in a letter tears its item apart in the inbox
        report.append(f"{'✅' if ok else '⚙' if broken else '❌'} {c['name']}: {det} {action}".strip())
        sev = c.get("severity", "infra")
        if ok:
            s["last_ok"] = now
            # the human was told "not working" and never "working again" (a bot was back in 40 s, the human thought it dead for 2 days)
            if s.pop("flag_alerted_at", None) is not None and sev == "human" and flag_on:
                down = int((now - s.pop("down_since", now)) / 60)
                human_flag(f"✅ [supervisor] \"{c['name']}\" works again (it was down about {max(down, 1)} min). Nothing is needed from {human}.")
                log(f"RECOVERED {c['name']} (about {down} min) -> flag")
            s.pop("down_since", None)
            continue
        s.setdefault("down_since", now)
        (broken_l if broken else problems).append(c["name"])
        details.append({"name": c["name"], "severity": sev, "broken": broken, "detail": det})
        owners = c.get("owner") or []
        owners = [owners] if isinstance(owners, str) else list(owners)
        if broken:  # the instrument, not the object: no restarts, one letter to the infra agent (or the owner), no human flag
            to = [infra] if infra else owners
            if now - s["last_alert"] < DEDUP_S or a.dry_run or not to or any(pending(t, c["name"]) for t in to):
                continue
            s["last_alert"] = now
            for t in to:
                post_inbox(t, f"- [ ] [{time.strftime('%F %H:%M')}] ⚙ **Supervisor: CHECK BROKEN «{c['name']}»** - {det}. "
                              f"I did NOT restart the object and do not know whether it is alive: fix the check itself "
                              f"(rc 3 = could not measure, 126/127 = command missing). Registry: {a.checks}")
            log(f"BROKEN-CHECK {c['name']}: {det}")
            continue
        exhausted = unit and (loop or len(s["restarts"]) >= c.get("max_restarts_hour", 3))
        if now - s["last_alert"] < DEDUP_S or a.dry_run or any(pending(o, c["name"]) for o in owners):
            continue
        s["last_alert"] = now
        why = ("restarts used up (3 per hour) - stopped, manual from here" if exhausted else
               "not a service, or the restart did not help")
        msg = (f"- [ ] [{time.strftime('%F %H:%M')}] 🛰 **Supervisor: «{c['name']}» is failing** - {det}. "
               f"{why}. {action} Registry: {a.checks} · log {LOG}")
        for o in owners:
            post_inbox(o, msg)
        log(f"ALERT {c['name']}: {det} | {why} | letters: {', '.join(owners) or 'none (no owner)'}")
        if sev == "human" and flag_on:
            # a second try before the human is told: a service restarted with network retries needs ~40 s
            time.sleep(int(os.environ.get("SUPERVISOR_HUMAN_RECHECK_S", "45")))
            try:
                ok2, _ = check(c)
            except Exception:
                ok2 = False
            if ok2:
                log(f"ALERT-SKIP-FLAG {c['name']}: second try after the wait - alive")
                continue
            s["flag_alerted_at"] = now
            human_flag(f"⚠️ [supervisor] \"{c['name']}\" is not working: {det}. {human} has not been told yet - say it in your next "
                       f"reply in one line, without the technique. The owner's inbox already has the details.")
    save_state(a.state, st)
    summary = {"ts": time.strftime("%F %T"), "checks": len(report), "problems": problems, "broken_checks": broken_l,
               "after_downtime": after_l, "details": details}
    tmp = f"{a.state}/summary.json.tmp"
    json.dump(summary, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, f"{a.state}/summary.json")
    open(f"{a.state}/heartbeat", "w").write(str(int(now)))
    hb = conf("CCM_SUPERVISOR_HEARTBEAT", "")
    if hb:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(hb)), exist_ok=True)
            open(hb, "w").write(str(int(now)))
        except OSError:
            pass
    log(f"RUN {len(report)} checks, problems {len(problems)}{': ' + ', '.join(problems) if problems else ''}"
        f"{f'; broken checks {len(broken_l)}: ' + ', '.join(broken_l) if broken_l else ''}"
        f"{f'; quiet after downtime {len(after_l)}: ' + ', '.join(after_l) if after_l else ''}")
    print("\n".join(report))


if __name__ == "__main__":
    main()
