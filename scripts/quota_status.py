#!/usr/bin/env python3
"""quota_status.py - how much of your Claude session / weekly quota is gone, and who spent it.

Two sources:
  1. REAL numbers: the account's usage endpoint, read with the access token the Claude Code CLI already holds in
     ~/.claude/.credentials.json (an answer is cached QUOTA_REAL_EVERY_S seconds, default 300).
  2. ESTIMATE (fallback): token usage summed from the session transcripts (~/.claude/projects/**.jsonl) over the
     current 5-hour session window, divided by an empirical ceiling. The estimate only covers THIS machine and
     the ceiling is rough: treat it as a lower bound, the real number wins whenever it is fresh.

HARD RULE - NEVER REFRESH THE OAUTH TOKEN. The refresh token is single-use: a second refresh (ours, while the CLI
also refreshes) logs the live CLI out. This script only READS `claudeAiOauth.accessToken`; an expired token means
"wait until the CLI renews it" (the next CLI start does that), nothing more. Do not add a refresh call here, ever.

Usage:
  quota_status.py                      human report
  quota_status.py --json               JSON on stdout (for hooks / the supervisor)
  quota_status.py --json --out FILE    same, written atomically to FILE only if the run succeeded (cron form)
  quota_status.py --line AGENT         one line about AGENT's own spend, from the finished status file
  quota_status.py --hours N            another window length (default 5)

Cron (every minute):
  * * * * * flock -n ~/.claude/quota.lock timeout 50 python3 ~/.claude/scripts/quota_status.py --json --out ~/.claude/quota-status.json 2>>~/.claude/quota.err

Settings (environment variables; the file paths are only for tests / unusual installs):
  QUOTA_ROOTS        transcript roots, ':'-separated        default ~/.claude/projects
  QUOTA_IDENT        agent-identity dirs, ':'-separated      default ~/.claude/agent-identity
  QUOTA_CREDS        credentials file (read only)             default ~/.claude/.credentials.json
  QUOTA_USAGE_URL    usage endpoint                           default https://api.anthropic.com/api/oauth/usage
  QUOTA_CEILING      weighted-token ceiling of one window     default 4800000 (conservative lower bound)
  MACHINE_USAGE      usage log of claude_machine.py runs      default ~/.claude/machine-usage.jsonl
  QUOTA_CACHE / QUOTA_REAL_STATE / QUOTA_LIMIT_STATE / QUOTA_STATUS   state files, default under ~/.claude/
"""
import json, os, sys, time, glob

HOME = os.path.expanduser("~")
CD = os.path.join(HOME, ".claude")
WINDOW_H = 5.0
# Weighted tokens = output + input/10 + cache_write/10. Two calibration points on the original machine
# contradicted each other (8% at 1.36M and 92% at 4.42M), no linear formula reproduces the provider's accounting,
# so the ceiling is the SMALLEST observed one: better to warn early than late. Override with QUOTA_CEILING.
CEILING_WEIGHTED = int(os.environ.get("QUOTA_CEILING") or 4_800_000)

ROOTS = os.environ.get("QUOTA_ROOTS", os.path.join(CD, "projects")).split(":")
IDENT_DIRS = os.environ.get("QUOTA_IDENT", os.path.join(CD, "agent-identity")).split(":")
KEEP_S = 48 * 3600
WEEK_DAYS = 8                       # daily sums are kept 8 days (the weekly window + a margin)
CACHE = os.environ.get("QUOTA_CACHE", os.path.join(CD, "quota-cache3.json"))
CREDS = os.environ.get("QUOTA_CREDS", os.path.join(CD, ".credentials.json"))
REAL_STATE = os.environ.get("QUOTA_REAL_STATE", os.path.join(CD, "quota-real.json"))
REAL_EVERY_S = int(os.environ.get("QUOTA_REAL_EVERY_S", "300"))
USAGE_URL = os.environ.get("QUOTA_USAGE_URL", "https://api.anthropic.com/api/oauth/usage")
MACHINE_USAGE = os.environ.get("MACHINE_USAGE", os.path.join(CD, "machine-usage.jsonl"))
_FILES = None


def wt(i, o, cc):
    return o + i // 10 + cc // 10


def cost_units(model, i, o, cr, cc):
    """Relative cost units of one request, from the price ratios: output x5, cache write x1.25, cache read x0.1 of an
    input token; model multiplier opus/fable x5, sonnet x3, haiku x1. A plain "output + input/10" ignores cache reads
    (the bulk of all tokens) and made the per-1% figure far worse. Accuracy about +-40%, hence "≈" in agent lines."""
    m = (model or "").lower()
    k = 5 if ("opus" in m or "fable" in m) else 1 if "haiku" in m else 3
    return k * (i + 1.25 * cc + 0.1 * cr + 5 * o)


def files():
    """Incremental per-file cache: {path: {ino, off, ev, daily, sub}}. Each file remembers the byte offset it was read
    to (whole lines only) and its events, so a run reads only the tail (re-reading GBs of transcripts every minute
    loaded the original machine to 26). A shorter file / another inode -> re-read. ev = events of the last 48 h
    [epoch, model, in, out, cache_read, cache_creation]; daily = cost units per UTC day for 8 days; sub = a subagent
    transcript (<project>/<sid>/subagents/*.jsonl): not in the ESTIMATE (the ceiling was calibrated without them),
    but in the agent's share."""
    global _FILES
    if _FILES is not None:
        return _FILES
    now = time.time()
    try:
        cache = json.load(open(CACHE))
    except (OSError, ValueError):
        cache = {}
    new_cache = {}
    old_day = time.strftime("%Y-%m-%d", time.gmtime(now - WEEK_DAYS * 86400))
    for root in ROOTS:
        for p in glob.glob(f"{root}/*/*.jsonl") + glob.glob(f"{root}/*/*/subagents/*.jsonl"):
            if p.endswith("-cut.jsonl"):
                continue
            try:
                st = os.stat(p)
                if st.st_mtime < now - WEEK_DAYS * 86400:
                    continue
                c = cache.get(p)
                if not c or c.get("ino") != st.st_ino or c.get("off", 0) > st.st_size:
                    c = {"ino": st.st_ino, "off": 0, "ev": [], "daily": {}, "sub": "/subagents/" in p}
                if c["off"] < st.st_size:
                    with open(p, "rb") as f:
                        f.seek(c["off"])
                        chunk = f.read()
                    end = chunk.rfind(b"\n") + 1          # an unfinished last line waits for the next run
                    for raw in chunk[:end].split(b"\n"):
                        if b'"usage"' not in raw or b'"timestamp"' not in raw:
                            continue
                        try:
                            o = json.loads(raw)
                        except ValueError:
                            continue
                        ts = o.get("timestamp", "")
                        u = (o.get("message") or {}).get("usage")
                        if not ts or not u:
                            continue
                        try:
                            e = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
                        except ValueError:
                            continue
                        ev = [e, (o.get("message") or {}).get("model", "?"), u.get("input_tokens", 0) or 0,
                              u.get("output_tokens", 0) or 0, u.get("cache_read_input_tokens", 0) or 0,
                              u.get("cache_creation_input_tokens", 0) or 0]
                        day = ts[:10]
                        c["daily"][day] = c["daily"].get(day, 0) + cost_units(ev[1], ev[2], ev[3], ev[4], ev[5])
                        if e >= now - KEEP_S:
                            c["ev"].append(ev)
                    c["off"] += end
                c["ev"] = [x for x in c["ev"] if x[0] >= now - KEEP_S]
                c["daily"] = {d: v for d, v in c["daily"].items() if d >= old_day}
                new_cache[p] = c
            except OSError:
                continue
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = f"{CACHE}.{os.getpid()}"
        json.dump(new_cache, open(tmp, "w")); os.replace(tmp, CACHE)
    except OSError:
        pass
    _FILES = new_cache
    return new_cache


def machine():
    """The claude_machine.py log in the shape of files(): {"machine:<tag>": {ev, daily}} - those runs leave no transcript."""
    out, now = {}, time.time()
    old_day = time.strftime("%Y-%m-%d", time.gmtime(now - WEEK_DAYS * 86400))
    try:
        rows = open(MACHINE_USAGE, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return out
    for raw in rows:
        try:
            r = json.loads(raw)
            ev = [float(r["ts"]), r.get("model", "?"), int(r.get("i", 0)), int(r.get("o", 0)), int(r.get("cr", 0)), int(r.get("cc", 0))]
        except (ValueError, KeyError, TypeError):
            continue
        day = time.strftime("%Y-%m-%d", time.gmtime(ev[0]))
        if day < old_day:
            continue
        c = out.setdefault(f"machine:{r.get('tag', '?')}", {"ev": [], "daily": {}, "sub": False})
        c["daily"][day] = c["daily"].get(day, 0) + cost_units(ev[1], ev[2], ev[3], ev[4], ev[5])
        if ev[0] >= now - KEEP_S:
            c["ev"].append(ev)
    return out


def all_files():
    return {**files(), **machine()}


def events():
    """Usage events of the last 48 h from MAIN transcripts (no subagents) and machine runs - for the estimate."""
    return [e for c in all_files().values() if not c.get("sub") for e in c["ev"]]


_IDENT = {}


def agent_of(path):
    """Agent name of a transcript: the session's identity file (a subagent -> its parent session's identity)."""
    if path.startswith("machine:"):
        return f"service: {path[8:]}"
    parts = path.split("/")
    sid = parts[-3] if "/subagents/" in path else parts[-1][:-6]
    if sid not in _IDENT:
        name = None
        for d in IDENT_DIRS:
            try:
                name = os.path.basename(open(f"{d}/{sid}").read().strip().rstrip("/")) or None
                break
            except OSError:
                continue
        _IDENT[sid] = name or "unnamed (claude -p / service)"
    return _IDENT[sid]


def by_agent(win_start, week_start):
    """Each agent's share in COST UNITS (model x input/output/cache) for the session window (events) and the week
    (daily sums, UTC-day precision). Counting output + input/10 without the model and cache reads once made a cheap
    Haiku bot look like 41.7% of a week when it was about 8%, and a human switched it off on that number - so the
    share is an approximation, never an invoice: the provider's real formula is unknown, and a transcript does not
    say which account a request went through."""
    win, week = {}, {}
    wk_day = time.strftime("%Y-%m-%d", time.gmtime(week_start))
    for p, c in all_files().items():
        w = sum(cost_units(e[1], e[2], e[3], e[4], e[5]) for e in c["ev"] if e[0] >= win_start)
        k = sum(v for d, v in c["daily"].items() if d >= wk_day)
        if w or k:
            a = agent_of(p)
            win[a] = win.get(a, 0) + w
            week[a] = week.get(a, 0) + k
    tw, tk = sum(win.values()) or 1, sum(week.values()) or 1
    by_agent.window_total = sum(wt(e[2], e[3], e[5]) for c in all_files().values() for e in c["ev"] if e[0] >= win_start)
    by_agent.window_cost = sum(win.values())
    return {a: {"window_share": round(100 * win.get(a, 0) / tw, 1), "week_share": round(100 * week.get(a, 0) / tk, 1)}
            for a in sorted(set(win) | set(week), key=lambda a: -week.get(a, 0))}


def fetch_real():
    """GET the usage endpoint with the CURRENT accessToken. NEVER REFRESH (see the module docstring): the refresh
    token is single-use and a second refresh logs the live CLI out. Expired token -> wait for the CLI to renew it.
    -> (body | None, error | None)."""
    import urllib.request, urllib.error
    try:
        c = json.load(open(CREDS))["claudeAiOauth"]
        if c.get("expiresAt") and c["expiresAt"] / 1000 < time.time():
            return None, "token expired - waiting for the CLI to renew it"
        req = urllib.request.Request(USAGE_URL, headers={"Authorization": "Bearer " + c["accessToken"],
                                     "anthropic-beta": "oauth-2025-04-20", "User-Agent": "claude-code"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, type(e).__name__


def normalize(body):
    """Endpoint body -> {session:{pct,resets_at}, weekly:{pct,resets_at}, models:[{label,pct}], extra_enabled}, or None
    for an unknown shape. Understands both the `limits` array and the older named windows."""
    if not isinstance(body, dict):
        return None
    out = {"models": []}
    for it in body.get("limits") or []:
        if not isinstance(it, dict) or not isinstance(it.get("percent"), (int, float)):
            continue
        row = {"pct": float(it["percent"]), "resets_at": it.get("resets_at")}
        if it.get("kind") == "session":
            out["session"] = row
        elif it.get("kind") == "weekly_all":
            out["weekly"] = row
        elif it.get("kind") == "weekly_scoped":
            label = (((it.get("scope") or {}).get("model") or {}).get("display_name")) or "model"
            out["models"].append({"label": label, **row})
    for key, name in (("five_hour", "session"), ("seven_day", "weekly")):
        v = body.get(key)
        if name not in out and isinstance(v, dict) and isinstance(v.get("utilization"), (int, float)):
            out[name] = {"pct": float(v["utilization"]), "resets_at": v.get("resets_at")}
    if "session" not in out and "weekly" not in out:
        return None
    out["extra_enabled"] = bool((body.get("extra_usage") or {}).get("is_enabled"))
    return out


def real(fetch=fetch_real):
    """The real quota, cached: the endpoint is asked at most every REAL_EVERY_S; an error keeps the last good value."""
    now = time.time()
    try:
        st = json.load(open(REAL_STATE))
    except (OSError, ValueError):
        st = {}
    if now - st.get("tried_at", 0) >= REAL_EVERY_S:
        body, err = fetch()
        st["tried_at"] = now
        n = normalize(body) if body is not None else None
        if n:
            st.update(ok_at=now, data=n, error=None)
        else:
            st["error"] = err or "unrecognised response shape"
        try:
            os.makedirs(os.path.dirname(REAL_STATE), exist_ok=True)
            tmp = f"{REAL_STATE}.{os.getpid()}"
            json.dump(st, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, REAL_STATE)
        except OSError:
            pass
    return st


def iso_epoch(s):
    try:
        import datetime
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError, TypeError):
        return None


def session_window_start(hours):
    """The provider's session is NOT a trailing "last 5 hours" but a FIXED window: it starts at the first message
    after an idle gap / reset and lives 5 hours (a trailing estimate said 59.7% when the panel said 8%). We rebuild the
    boundaries: take the usage events of 48 h, find the last idle gap >= the window - the event after it anchors the
    chain of 5-hour windows up to now. No such gap in 48 h -> an honest fallback to trailing (marked "rolling")."""
    now = time.time()
    ts = sorted(e[0] for e in events() if e[0] >= now - 48 * 3600)
    if not ts:
        return now - hours * 3600, "rolling"
    anchor, prev = None, ts[0]
    for e in ts[1:]:
        if e - prev >= hours * 3600:
            anchor = e
        prev = e
    if anchor is None:
        return now - hours * 3600, "rolling"
    start = anchor
    while start + hours * 3600 <= now:
        nxt = [e for e in ts if e >= start + hours * 3600]
        if not nxt:
            break
        start = nxt[0]
    return start, "session"


def agent_line(agent, status=None):
    """A line for an agent about ITS spend, from the finished status file (no recomputation). Empty without data."""
    try:
        d = json.load(open(status or os.environ.get("QUOTA_STATUS", os.path.join(CD, "quota-status.json"))))
    except (OSError, ValueError):
        return ""
    if d.get("source") != "api":
        return ""
    a = (d.get("by_agent") or {}).get(agent)
    w = d.get("weekly") or {}
    head = f"Account quota: session {d['pct']:g}% (resets in {d['resets_in_min']} min), week {w.get('pct', '?')}%"
    if not a:
        return head + f" · {agent}: nothing spent in this window yet."
    return (head + f" · you ({agent}): {a['window_pct']:g}% of the session limit ({a['window_share']:g}% of everything the swarm "
            f"burned in the window), {a['week_pct']:g}% of the weekly limit ({a['week_share']:g}% of the swarm's spend).")


def compute(hours=WINDOW_H):
    cutoff, mode = session_window_start(hours)
    tot = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    by_model, msgs = {}, 0
    keys = tuple(tot)
    for e, model, *vals in events():
        if e < int(cutoff):
            continue
        msgs += 1
        bm = by_model.setdefault(model, dict.fromkeys(tot, 0))
        for k2, v in zip(keys, vals):
            tot[k2] += v; bm[k2] += v
    weighted = tot["output_tokens"] + tot["input_tokens"] // 10 + tot["cache_creation_input_tokens"] // 10
    out = {
        "window_h": hours, "mode": mode, "messages": msgs, **tot, "weighted": weighted,
        "window_started": time.strftime("%H:%M", time.localtime(cutoff)),
        "resets_in_min": max(0, int((cutoff + hours * 3600 - time.time()) / 60)),
        "ceiling_weighted": CEILING_WEIGHTED,
        "pct": round(100 * weighted / CEILING_WEIGHTED, 1) if CEILING_WEIGHTED else None,
    }
    # the real quota: pct and reset come from the account; the transcript estimate stays as the fallback
    out["estimate_pct"] = out["pct"]
    out["source"] = "estimate"
    rs = real()
    d = rs.get("data") or {}
    now = time.time()
    win_start, week_start = cutoff, now - 7 * 86400
    if d and rs.get("ok_at"):
        age = int((now - rs["ok_at"]) / 60)
        out["real_age_min"] = age
        out["real_error"] = rs.get("error")
        ses, wk = d.get("session"), d.get("weekly")
        s_reset = iso_epoch((ses or {}).get("resets_at"))
        # a reading older than its own window (s_reset passed) is about the previous session: its percent is void
        fresh = age <= 6 and not rs.get("error")
        if fresh and (not ses or (s_reset is not None and s_reset <= now)):
            # the account answered just now but has no open session (window reset, no new request yet): that is a
            # real "0%", not "endpoint silent" - otherwise a supervisor went red ~20 min after every window reset
            out.update(source="api", pct=0.0, session_idle=True)
        elif ses and (s_reset is None or s_reset > now):
            out.update(source="api", pct=ses["pct"])
            if s_reset:
                out["resets_in_min"] = max(0, int((s_reset - now) / 60))
                win_start = s_reset - hours * 3600
                out["window_started"] = time.strftime("%H:%M", time.localtime(win_start))
        if wk:
            w_reset = iso_epoch(wk.get("resets_at"))
            out["weekly"] = {"pct": wk["pct"], "resets_at": wk.get("resets_at"),
                             "resets_in_h": max(0, int((w_reset - now) / 3600)) if w_reset else None}
            if w_reset:
                week_start = w_reset - 7 * 86400
        out["weekly_models"] = [{"label": m["label"], "pct": m["pct"]} for m in d.get("models", [])]
        out["extra_usage_enabled"] = d.get("extra_enabled", False)
    elif rs.get("error"):
        out["real_error"] = rs["error"]
    ba = by_agent(win_start, week_start)
    wkp = (out.get("weekly") or {}).get("pct")
    for a, v in ba.items():      # an agent's percent of the account limit = its share x the real percent
        v["window_pct"] = round(v["window_share"] * out["pct"] / 100, 1) if out.get("source") == "api" else None
        v["week_pct"] = round(v["week_share"] * wkp / 100, 1) if wkp is not None else None
    out["by_agent"] = ba
    # How many cost units make 100% of the session (cost-guard prices ONE turn in percent with it). Measured only when
    # the real percent is already visible (>=10%): on small numbers the division is noise. Median of the last 12.
    lim_f = os.environ.get("QUOTA_LIMIT_STATE", os.path.join(CD, "quota-limit.json"))
    try:
        lim = json.load(open(lim_f))
    except (OSError, ValueError):
        lim = {}
    wcost = getattr(by_agent, "window_cost", 0)
    out["window_weighted_all"] = getattr(by_agent, "window_total", 0)
    if out.get("source") == "api" and out["pct"] >= 10 and wcost and out.get("real_age_min", 99) <= 6:
        ms = (lim.get("measures") or [])[-11:] + [wcost / out["pct"]]
        lim = {"measures": ms, "at": time.strftime("%F %T")}
        try:
            json.dump(lim, open(lim_f + ".tmp", "w")); os.replace(lim_f + ".tmp", lim_f)
        except OSError:
            pass
    ms = sorted(lim.get("measures") or [])
    out["cost_units_per_pct"] = int(ms[len(ms) // 2]) if ms else None
    return out, by_model, tot, ba


def main():
    argv = sys.argv[1:]
    if "--line" in argv:
        print(agent_line(argv[argv.index("--line") + 1])); return 0
    hours = float(argv[argv.index("--hours") + 1]) if "--hours" in argv else WINDOW_H
    out, by_model, tot, ba = compute(hours)
    if "--json" in argv:
        text = json.dumps(out, ensure_ascii=False)
        if "--out" in argv:                       # atomic, and only reached when compute() did not raise
            dest = argv[argv.index("--out") + 1]
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
            tmp = f"{dest}.{os.getpid()}"
            open(tmp, "w").write(text); os.replace(tmp, dest)
        else:
            print(text)
        return 0
    if out["source"] == "api":
        w = out.get("weekly") or {}
        print(f"REAL QUOTA (account, {out['real_age_min']} min ago): session {out['pct']}% (resets in "
              f"{out['resets_in_min']} min) · week {w.get('pct')}% (resets in {w.get('resets_in_h')} h)")
        for a, v in list(ba.items())[:12]:
            print(f"    {a}: window {v['window_share']}% of the swarm = {v['window_pct']}% of the limit · week {v['week_share']}% = {v['week_pct']}%")
        print("- estimate from the transcripts (fallback):")
    print(f"Window {hours:g} h ({out['mode']}, started {out['window_started']}, resets in ~{out['resets_in_min']} min) · messages with usage: {out['messages']}")
    print(f"  output: {tot['output_tokens']:,} · input: {tot['input_tokens']:,} · "
          f"cache_read: {tot['cache_read_input_tokens']:,} · cache_write: {tot['cache_creation_input_tokens']:,}")
    print(f"  weighted (output + input/10 + cache_write/10): {out['weighted']:,}")
    print(f"  ceiling: {CEILING_WEIGHTED:,} -> {out['estimate_pct']}% burned (estimate)")
    for m, u in sorted(by_model.items(), key=lambda x: -x[1]["output_tokens"]):
        w = u["output_tokens"] + u["input_tokens"] // 10 + u["cache_creation_input_tokens"] // 10
        print(f"    {m}: out {u['output_tokens']:,} · weighted {w:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
