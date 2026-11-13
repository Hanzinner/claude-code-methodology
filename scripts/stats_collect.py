#!/usr/bin/env python3
"""stats_collect.py - swarm statistics from the Claude Code session logs: working time, tokens, cost, agents, and the
human's messages (how many, how many are corrections, how many swear).

Reads ~/.claude/projects/**/*.jsonl (subagent transcripts are folded into the parent session), caches the parse of each
file by (mtime, size) in <stats dir>/.cache.json and writes the aggregates to <stats dir>/data.json (default
~/.claude/stats/). A plain JSON file - the original also drew a web page from it; that page is not ported.
Settings: STATS_DIR (default ~/.claude/stats) · CLAUDE_PROJECTS_DIR (default ~/.claude/projects) ·
CCM_TIMEZONE (day boundaries; empty = system) · CCM_AGENTS_DIR (agent folders with a briefing.md name the agents) ·
CCM_LANG_EXTRA ("uk" also matches Ukrainian correction/swear words).
Cron (hourly):  35 * * * * python3 ~/.claude/scripts/stats_collect.py
"""
import glob, json, os, re, sys, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

HOME = os.path.expanduser("~")
_tz = conf("CCM_TIMEZONE", "")
TZ = ZoneInfo(_tz) if _tz else datetime.now().astimezone().tzinfo
STATS = os.path.expanduser(os.environ.get("STATS_DIR", "~/.claude/stats"))
AGENTS_DIR = conf("CCM_AGENTS_DIR", "") or os.path.join(conf("CCM_WORKSPACE", os.path.join(HOME, "claude-projects")), "Agents")
SRC = [os.path.expanduser(os.environ.get("CLAUDE_PROJECTS_DIR", "~/.claude/projects"))]
CACHE = os.path.join(STATS, ".cache.json")
OUT = os.path.join(STATS, "data.json")
IDENT = os.path.join(HOME, ".claude", "agent-identity")
GAP_ACTIVE = 5 * 60      # a gap between session events that still counts as "working"
GAP_HUMAN = 10 * 60      # a gap between the human's messages that still counts as "at the keyboard"

AGENTS = sorted({os.path.basename(os.path.dirname(p)) for p in
                 glob.glob(f"{AGENTS_DIR}/*/briefing.md") + glob.glob(f"{AGENTS_DIR}/*/*/briefing.md")},
                key=len, reverse=True)

# A "correction" = the human's message that starts like a rebuke. A heuristic: it counts, it does not judge.
_CORR_EN = (r"no[,.! ]|no$|that'?s not|not that|wrong|stop|don'?t|do not|i (said|told you|didn'?t ask)|again|why did you|"
            r"you (didn'?t|forgot|ignored)|re-?read")
_CORR_UK = (r"ні[,.! ]|ні$|не так|не те|не треба|стоп|нахуя|нафіга|навіщо ти|перечитай|я ж (казав|сказав)|знову|ти (що|шо|не)|"
            r"схуялі|бля|не роби|я не просив|не зрозумів ти|неправильно|це не")
_SWEAR_EN = r"fuck|shit|bullshit|damn|wtf|bitch|asshole|crap\b"
_L = r"[а-яіїєґё'a-z]"
_SWEAR_UK = (rf"(?<!{_L})(на|за|по|від|ви|у|з|до|пере|роз|при|об|под|недо)?[їєеё]б(а|у|и|о|л|ан|ну)|(?<!{_L})(на|по|ні|с|з|до|за|від|об)?ху[йяєїюи]|"
             rf"пизд|пізд|(?<!{_L})бля|(?<!{_L})сук[аиоу](?!{_L})|мудак|мудил|долбо|(?<!{_L})дебіл|підар|пидар|гандон|залуп")
_uk = "uk" in conf("CCM_LANG_EXTRA", "")
CORR = re.compile(r"^\s*(" + _CORR_EN + (("|" + _CORR_UK) if _uk else "") + ")", re.I)
SWEAR = re.compile(_SWEAR_EN + (("|" + _SWEAR_UK) if _uk else ""), re.I)


def ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def human_text(d):
    """Text of a live human message, or None (tool_result, system injections, commands)."""
    if d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta"):
        return None
    if d.get("userType") not in (None, "external"):
        return None
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list):
        if any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c):
            return None
        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    if not isinstance(c, str):
        return None
    c = c.strip()
    if not c or c.startswith("<") or c.startswith("[Request interrupted") or c.startswith("This session is being continued"):
        return None
    return c


PARSE_V = 2   # 2: the 7th field of tok = 1-hour cache write (for cost); a version change = every file is re-parsed

# Cost "as by the API", $ per 1M tokens. Cache write: 5 min = 1.25x input, 1 h = 2x input.
# Source: the provider's API price page as of PRICES_AS_OF. A price changed -> edit here and PRICES_AS_OF.
PRICES_AS_OF = "2026-06-24"
PRICES = {  # model id prefix -> (input, cache_read, output)
    "claude-fable-5-1": (10, 0.25, 50), "claude-fable-5": (10, 1.0, 50),
    "claude-opus-5-5": (4, 0.20, 20), "claude-opus-5": (5, 0.5, 25),
    "claude-opus-4-8": (5, 0.5, 25), "claude-opus-4-7": (5, 0.5, 25), "claude-opus-4-6": (5, 0.5, 25),
    "claude-sonnet-5": (2, 0.2, 10), "claude-sonnet-4-6": (3, 0.3, 15), "claude-haiku-4-5": (1, 0.1, 5),
}


def price_of(model):
    for k in sorted(PRICES, key=len, reverse=True):   # longest prefix first: opus-5-5 before opus-5
        if model == k or model.startswith(k + "-"):
            return PRICES[k]
    return None


def cost_usd(t):
    """t = [ts, model, input, cache_write_all, cache_read, output, cache_write_1h] -> $ or None (a model without a price)."""
    p = price_of(t[1])
    if p is None:
        return None
    inp, cr, out = p
    w1h = t[6] if len(t) > 6 else 0
    return (t[2] * inp + (t[3] - w1h) * inp * 1.25 + w1h * inp * 2 + t[4] * cr + t[5] * out) / 1e6


def parse_file(path):
    sid = os.path.basename(path)[:-6]
    parent = None
    if "/subagents/" in path:
        parent = path.split("/subagents/")[0].rsplit("/", 1)[-1]
    ev, hum, tok, seen = [], [], [], set()
    title = aname = entry = cwd = None
    ui = False   # traces of a human UI; claude -p runs (reviewers, cron) have none, even when entrypoint=claude-vscode
    first_text = None
    with open(path, errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = d.get("type")
            if t in ("custom-title", "ai-title", "mode", "agent-name", "atis-latch") or \
                    (isinstance(d.get("origin"), dict) and d["origin"].get("kind") == "human"):
                ui = True
            if t == "custom-title":
                title = d.get("customTitle") or title
            elif t == "agent-name":
                aname = d.get("agentName") or d.get("name") or aname
            entry = entry or d.get("entrypoint")
            cwd = cwd or d.get("cwd")
            x = ts(d.get("timestamp", "")) if d.get("timestamp") else None
            if t == "assistant" and x:
                m = d.get("message") or {}
                rid = d.get("requestId") or m.get("id")
                u = m.get("usage")
                if u and rid not in seen:
                    seen.add(rid)
                    tok.append([x, m.get("model", "?"), u.get("input_tokens", 0) or 0,
                                u.get("cache_creation_input_tokens", 0) or 0,
                                u.get("cache_read_input_tokens", 0) or 0, u.get("output_tokens", 0) or 0,
                                (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0) or 0])
                ev.append(x)
            elif t == "user" and x:
                ev.append(x)
                h = human_text(d)
                if h is not None:
                    hum.append([x, len(h), 1 if CORR.search(h) else 0, 1 if SWEAR.search(h) else 0])
                    if first_text is None:
                        first_text = h[:80]
    return {"sid": sid, "parent": parent, "title": title, "aname": aname, "entry": entry, "cwd": cwd,
            "first": first_text, "ui": ui, "ev": sorted(ev), "hum": hum, "tok": tok}


def agent_of(r):
    sid = r["parent"] or r["sid"]
    p = os.path.join(IDENT, sid)
    cand = []
    if os.path.isfile(p):
        try:
            cand.append(os.path.basename(open(p).read().strip().rstrip("/")))
        except Exception:
            pass
    cand += [r.get("aname"), r.get("title"), (r.get("first") or "").split("\n")[0]]
    for c in cand:
        if not c:
            continue
        c = c.strip()
        low = c.lower()
        for a in AGENTS:
            al = a.lower()
            if low == al or low.startswith(al) or low == al.replace("-agent", "") or al.startswith(low + "-agent"):
                return a
    cw = r.get("cwd") or ""
    m = re.search(r"/Agents/(?:[^/]+/)?([^/]+)", cw)
    if m and m.group(1) in AGENTS:
        return m.group(1)
    return None


def main():
    t0 = time.time()
    try:
        cache = json.load(open(CACHE))
    except Exception:
        cache = {}
    files = []
    for s in SRC:
        files += glob.glob(f"{s}/*/*.jsonl") + glob.glob(f"{s}/*/*/subagents/*.jsonl")
    newc, parsed = {}, 0
    recs = []
    for p in files:
        st = os.stat(p)
        key = f"{PARSE_V}:{st.st_mtime_ns}:{st.st_size}"
        c = cache.get(p)
        if c and c["k"] == key:
            r = c["r"]
        else:
            r = parse_file(p)
            parsed += 1
        newc[p] = {"k": key, "r": r}
        recs.append(r)
    os.makedirs(STATS, exist_ok=True)
    json.dump(newc, open(CACHE + ".tmp", "w"))
    os.replace(CACHE + ".tmp", CACHE)

    # fold subagents into the parent session
    sess = {}
    for r in recs:
        k = r["parent"] or r["sid"]
        s = sess.setdefault(k, {"sid": k, "ev": [], "hum": [], "tok": [], "sub": 0, "meta": None})
        s["ev"] += r["ev"]; s["tok"] += r["tok"]
        if r["parent"]:
            s["sub"] += 1
        else:
            s["hum"] += r["hum"]; s["meta"] = r
    day = lambda x: datetime.fromtimestamp(x, TZ).strftime("%Y-%m-%d")

    by_day = defaultdict(lambda: defaultdict(float))
    by_agent = defaultdict(lambda: defaultdict(float))
    heat = [[0] * 24 for _ in range(7)]
    human_ts = []
    models = defaultdict(float)
    model_days = defaultdict(lambda: defaultdict(float))
    cost_days = defaultdict(lambda: defaultdict(float))
    unpriced = defaultdict(float)
    agent_days = defaultdict(lambda: defaultdict(float))
    sess_len = []
    sessions_out = []
    for k, s in sess.items():
        m = s["meta"] or {}
        headless = (m.get("entry") or "") not in ("claude-vscode", "cli") or not s["hum"] or not m.get("ui")
        if headless:
            s["hum"] = []          # claude -p prompts are written by a script, not the human
        agent = agent_of(m) if m else None
        tab = (m.get("title") or "").strip()
        if not agent and not headless and tab and tab.lower() not in ("scratch",):
            name = tab + " (tab)"       # a named tab without an agent folder
        else:
            name = agent or ("background" if headless else "unnamed")
        ev = sorted(s["ev"])
        active = 0.0
        for a, b in zip(ev, ev[1:]):
            g = b - a
            if g <= GAP_ACTIVE:
                active += g
                agent_days[day(b)][name] += g / 60
                by_day[day(b)]["active_min"] += g / 60
        out = sum(t[5] for t in s["tok"]); inp = sum(t[2] + t[3] for t in s["tok"]); cr = sum(t[4] for t in s["tok"])
        for t in s["tok"]:
            dd = day(t[0])
            by_day[dd]["out"] += t[5]; by_day[dd]["in"] += t[2] + t[3]; by_day[dd]["cache"] += t[4]
            by_day[dd]["calls"] += 1
            models[t[1]] += t[5]
            if t[1] != "<synthetic>":
                model_days[dd][t[1]] += t[5]
                c = cost_usd(t)
                if c is None:
                    unpriced[t[1]] += t[2] + t[3] + t[4] + t[5]
                else:
                    cost_days[dd][re.sub(r"-20\d{6}$", "", t[1])] += c
        A = by_agent[name]
        A["active_min"] += active / 60; A["out"] += out; A["in"] += inp; A["cache"] += cr
        A["sessions"] += 1; A["human_msgs"] += len(s["hum"]); A["corr"] += sum(h[2] for h in s["hum"]); A["swear"] += sum(h[3] for h in s["hum"] if len(h) > 3)
        A["human_chars"] += sum(h[1] for h in s["hum"]); A["calls"] += len(s["tok"])
        if ev:
            A["last"] = max(A.get("last", 0), ev[-1]); A["first"] = min(A.get("first", 9e18), ev[0])
        for h in s["hum"]:
            dt = datetime.fromtimestamp(h[0], TZ)
            heat[dt.weekday()][dt.hour] += 1
            by_day[day(h[0])]["human_msgs"] += 1
            by_day[day(h[0])]["corr"] += h[2]
            by_day[day(h[0])]["swear"] += h[3] if len(h) > 3 else 0
            human_ts.append((h[0], k))
        if ev and not headless:
            sess_len.append([round(active / 60), round((ev[-1] - ev[0]) / 86400, 2), len(s["hum"])])
            sessions_out.append({"agent": name, "start": ev[0], "end": ev[-1], "active_min": round(active / 60),
                                 "human_msgs": len(s["hum"]), "out": out})
    # the human's time at the keyboard + parallel chats
    human_ts.sort()
    for (a, sa), (b, sb) in zip(human_ts, human_ts[1:]):
        if b - a <= GAP_HUMAN:
            by_day[day(b)]["human_min"] += (b - a) / 60
    par = defaultdict(set)
    for x, sid in human_ts:
        par[(day(x), datetime.fromtimestamp(x, TZ).hour)].add(sid)
    for (dd, hh), ss in par.items():
        by_day[dd]["max_parallel"] = max(by_day[dd].get("max_parallel", 0), len(ss))
    # the longest unbroken stretch of the human
    streak_best, cur_start, prev = (0, None), None, None
    for x, _ in human_ts:
        if prev is None or x - prev > GAP_HUMAN:
            cur_start = x
        if x - cur_start > streak_best[0]:
            streak_best = (x - cur_start, cur_start)
        prev = x

    now = time.time()
    data = {
        "generated": datetime.fromtimestamp(now, TZ).strftime("%Y-%m-%d %H:%M"),
        "files": len(files), "parsed_now": parsed, "sessions": len(sess),
        "interactive_sessions": len(sessions_out),
        "days": {d: {k: round(v, 1) for k, v in v.items()} for d, v in sorted(by_day.items())},
        "agents": {a: {k: (round(v, 1) if isinstance(v, float) else v) for k, v in v.items()}
                   for a, v in by_agent.items()},
        "heat": heat, "models_out": {k: int(v) for k, v in models.items()},
        "human_msgs_total": len(human_ts),
        "longest_streak_min": round(streak_best[0] / 60),
        "longest_streak_at": datetime.fromtimestamp(streak_best[1], TZ).strftime("%Y-%m-%d %H:%M") if streak_best[1] else None,
        "top_sessions": sorted(sessions_out, key=lambda s: -s["active_min"])[:15],
        "tz": str(TZ),
        "model_days": {d: {k: int(v) for k, v in v.items()} for d, v in sorted(model_days.items())},
        "agent_days": {d: {k: round(v, 1) for k, v in v.items() if v >= 1} for d, v in sorted(agent_days.items())},
        "sess_len": sess_len,
        "cost_days": {d: {k: round(v, 3) for k, v in v.items() if v >= 0.001} for d, v in sorted(cost_days.items())},
        "prices": {"as_of": PRICES_AS_OF, "per_mtok": {k: list(v) for k, v in PRICES.items()},
                   "cache_write": {"5m": 1.25, "1h": 2.0}},
        "unpriced_tokens": {k: int(v) for k, v in unpriced.items()},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT + ".tmp", "w"), ensure_ascii=False)
    os.replace(OUT + ".tmp", OUT)
    print(f"ok: {len(files)} files ({parsed} re-parsed), {len(sess)} sessions, {len(human_ts)} human messages, "
          f"{time.time() - t0:.0f} s -> {OUT}")


if __name__ == "__main__":
    main()
