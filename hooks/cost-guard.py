#!/usr/bin/env python3
"""cost-guard — a line to the agent when IT ate an unusual amount of quota in one turn.

The point is not to make the agent stop; it is to make it NOTICE when it burns quota and wastes it.

Stop branch (stdin = Stop event). Prices the turn that just finished from the usage records in the transcript and
shows a line on the NEXT prompt (flag file → surface-flags.sh), only when:
  (1) the turn is expensive: >= PCT_HARD % of the session limit, OR >= K_MEDIAN x this agent's usual turn (median of
      its recent turns) and at least PCT_MIN %;
  (2) it is looping: LOOP_N+ times the same command in one turn, or RISE_N turns in a row getting pricier with the
      last one >= PCT_MIN %.
Otherwise silence: ordinary work produces no line. At most one line per THROTTLE_MIN minutes per session.
The line carries the REASON (what the cost went on): a dropped prompt cache (the chat sat idle, the context was
re-read), tool/file output, a long reply and reasoning, subagents. The script sees "expensive" and "on what",
not "wasted" — the agent draws that conclusion.

Cost = relative units from token prices (output x5, cache write x1.25, cache read x0.1 of an input token; model
multiplier opus/fable x5, sonnet x3, haiku x1). The percentage needs a calibration: how many units make 1% of your
session limit. Sources, in order: the JSON file QUOTA_STATUS (default ~/.claude/quota-status.json, key
"cost_units_per_pct") or the setting CCM_COST_UNITS_PER_PCT. No calibration → no line (a figure without a
percentage would be noise). Accuracy of the calibration is about +-40%, hence the "≈" in the line.

Opt-in: if ~/.claude/cost_guard_agents.txt exists (agent folder names, one per line) only those agents are watched;
no file = everyone. The agent name comes from ~/.claude/agent-identity/<session_id> when something writes it.
`--calibrate [DAYS]` — which lines WOULD have been shown on your transcript history. Fail-open.
Left out of the port: the original also appended a per-agent share of the account's weekly window, which needs
the original machine's quota collector; here the line ends at the reason."""
import glob, json, os, re, statistics, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

HOME = os.path.expanduser("~")
STATE = os.environ.get("COST_GUARD_STATE", f"{HOME}/.claude/cost-guard")
STATUS = os.environ.get("QUOTA_STATUS", f"{HOME}/.claude/quota-status.json")
OPTIN = os.environ.get("COST_GUARD_AGENTS", f"{HOME}/.claude/cost_guard_agents.txt")
FLAGS = f"{HOME}/.claude/cost-guard-flags"
PCT_HARD, PCT_MIN, K_MEDIAN = 1.0, 0.3, 4
LOOP_N, RISE_N, THROTTLE_MIN, HIST = 6, 5, 20, 30


def cost_units(model, i, o, cr, cc):
    """Relative cost of one request, by the price ratios (see the module docstring)."""
    m = (model or "").lower()
    k = 5 if ("opus" in m or "fable" in m) else 1 if "haiku" in m else 3
    return k * (i + 1.25 * cc + 0.1 * cr + 5 * o)


def tail_turn(tp, is_prompt):
    """Transcript lines from the LAST line for which is_prompt(o) is true to the end (whole file if none).
    Reads backwards in growing blocks so a 60 MB transcript is not parsed at every Stop."""
    try:
        size = os.path.getsize(tp)
        f = open(tp, "rb")
    except OSError:
        return []
    with f:
        win = 2 * 1024 * 1024
        while True:
            start = max(0, size - win)
            f.seek(start)
            parts = f.read().split(b"\n")
            if start > 0:
                parts = parts[1:]                       # the first one may be cut in half
            lines = [p.decode("utf-8", "replace") for p in parts if p.strip()]
            for i in range(len(lines) - 1, -1, -1):
                if '"user"' not in lines[i] or '"tool_result"' in lines[i]:
                    continue
                try:
                    if is_prompt(json.loads(lines[i])):
                        return lines[i:]
                except ValueError:
                    continue
            if start == 0:
                return lines
            win *= 4


def turn_cost(rows):
    """rows — parsed lines of ONE turn. → dict(total, out, fresh, reread, read, tool_chars, agents, cmds, calls, ctx)."""
    c = {"total": 0.0, "out": 0.0, "fresh": 0.0, "reread": 0.0, "read": 0.0, "tool_chars": 0, "agents": 0,
         "cmds": {}, "calls": 0, "ctx": 0}
    seen_req, first = set(), True
    for o in rows:
        m = o.get("message") or {}
        content = m.get("content")
        if o.get("type") == "assistant":
            u = m.get("usage")
            rid = o.get("requestId") or m.get("id")
            if u and m.get("model") != "<synthetic>" and rid not in seen_req:   # one request = several rows, same usage
                seen_req.add(rid)
                model = m.get("model")
                i, out, cr, cc = (u.get(k, 0) or 0 for k in ("input_tokens", "output_tokens",
                                                              "cache_read_input_tokens", "cache_creation_input_tokens"))
                c["calls"] += 1
                c["ctx"] = max(c["ctx"], i + cr + cc)
                c["out"] += cost_units(model, 0, out, 0, 0)
                c["read"] += cost_units(model, 0, 0, cr, 0)
                w = cost_units(model, i, 0, 0, cc)
                # the first request of a turn writing more cache than it reads → the cache was dropped (the chat
                # sat idle) and the whole context was re-read
                if first and cc > cr and cc > 50_000:
                    c["reread"] += w
                else:
                    c["fresh"] += w
                first = False
            for x in content if isinstance(content, list) else []:
                if isinstance(x, dict) and x.get("type") == "tool_use":
                    if x.get("name") in ("Agent", "Task"):
                        c["agents"] += 1
                    if x.get("name") == "Bash":
                        k = re.sub(r"\s+", " ", str((x.get("input") or {}).get("command", "")))[:200]
                        c["cmds"][k] = c["cmds"].get(k, 0) + 1
        elif o.get("type") == "user" and isinstance(content, list):
            for x in content:
                if isinstance(x, dict) and x.get("type") == "tool_result":
                    c["tool_chars"] += len(json.dumps(x.get("content"), ensure_ascii=False))
    c["total"] = c["out"] + c["fresh"] + c["reread"] + c["read"]
    return c


def reason(c):
    """The biggest cost component, in words — what to change."""
    parts = [(c["reread"], f"the whole context was re-read — the cache was dropped, the chat sat idle (≈{c['reread'] / 6.25 / 1000:.0f}k tokens)"),
             (c["fresh"], f"new input — command and file output (≈{c['tool_chars'] / 4 / 1000:.0f}k tokens of it this turn)"),
             (c["out"], f"a long reply and reasoning (≈{c['out'] / 25 / 1000:.0f}k output tokens)"),
             (c["read"], f"{c['calls']} model calls x a context of ≈{c['ctx'] / 1000:.0f}k tokens — every tool call re-reads the "
                         f"whole context (cheaper: fewer small calls, chain commands, recap + compact)")]
    parts.sort(key=lambda x: -x[0])
    txt = parts[0][1]
    if parts[1][0] > 0.35 * c["total"]:
        txt += "; also — " + parts[1][1]
    if c["agents"]:
        txt += f"; {c['agents']} subagents were started (their spend is not counted here)"
    return txt


def decide(c, hist, per_pct, now, last_shown):
    """→ None | the line's text. hist — costs of this session's earlier turns (units)."""
    if not per_pct or c["total"] <= 0:
        return None
    pct = c["total"] / per_pct
    med = statistics.median(hist) if len(hist) >= 8 else None
    why = None
    if pct >= PCT_HARD:
        why = "an expensive turn"
    elif med and pct >= PCT_MIN and c["total"] >= K_MEDIAN * med:
        why = f"{c['total'] / med:.0f}x your usual turn"
    loop = max(c["cmds"].values(), default=0)
    if not why and loop >= LOOP_N and pct >= PCT_MIN / 2:
        why = f"the same command {loop} times in one turn"
    if not why and len(hist) >= RISE_N - 1 and pct >= PCT_MIN:
        tail = hist[-(RISE_N - 1):] + [c["total"]]
        if all(b > a for a, b in zip(tail, tail[1:])):
            why = f"{RISE_N} turns in a row getting pricier"
    if not why or now - last_shown < THROTTLE_MIN * 60:
        return None
    # a dropped cache after the human was away is neither the agent's fault nor something it can change (calibration:
    # several agents x3-x4 just because the human came back after a break). Silent if that is the main reason and the
    # turn doesn't reach the hard limit.
    if c["reread"] > 0.6 * c["total"] and pct < PCT_HARD:
        return None
    usual = f" (your usual ≈{med / per_pct:.2f}%)" if med else ""
    return f"💰 [cost-guard] Last turn: ≈{pct:.1f}% of the session limit{usual} — {why}. Mainly: {reason(c)}."


def per_pct_now():
    try:
        v = json.load(open(STATUS)).get("cost_units_per_pct")
        if v:
            return float(v)
    except (OSError, ValueError, AttributeError):
        pass
    try:
        return float(os.environ.get("CCM_COST_UNITS_PER_PCT") or conf("CCM_COST_UNITS_PER_PCT", "0")) or None
    except ValueError:
        return None


def parse(lines):
    out = []
    for l in lines:
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def is_prompt(o):
    if o.get("type") != "user" or o.get("isMeta"):
        return False
    c = (o.get("message") or {}).get("content")
    return isinstance(c, str) or (isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "text" for x in c)
                                  and not any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c))


def agent_of(sid):
    try:
        return os.path.basename(open(f"{HOME}/.claude/agent-identity/{sid}").read().strip().rstrip("/"))
    except OSError:
        return ""


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        return calibrate(int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return
    try:                       # empty / non-JSON input (a manual run) — silent
        d = json.load(sys.stdin)
    except ValueError:
        return
    sid, tp = d.get("session_id", ""), d.get("transcript_path", "")
    if not sid or not tp or d.get("stop_hook_active"):
        return
    agent = agent_of(sid)
    try:
        allowed = {l.strip() for l in open(OPTIN, encoding="utf-8") if l.strip() and not l.startswith("#")}
        if agent not in allowed:
            return
    except OSError:
        pass                                    # no file — on for everyone
    c = turn_cost(parse(tail_turn(tp, is_prompt)))
    os.makedirs(STATE, exist_ok=True)
    sf = f"{STATE}/{sid}.json"
    try:
        st = json.load(open(sf))
    except (OSError, ValueError):
        st = {"hist": [], "shown": 0}
    now = time.time()
    line = decide(c, st["hist"], per_pct_now(), now, st.get("shown", 0))
    if c["total"] > 0:
        st["hist"] = (st["hist"] + [c["total"]])[-HIST:]
    if line:
        st["shown"] = now
        os.makedirs(FLAGS, exist_ok=True)
        open(f"{FLAGS}/{sid}", "w", encoding="utf-8").write(line)
        try:
            with open(f"{HOME}/.claude/cost-guard.log", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%F %T')} [{sid[:8]}] {agent or '?'} {line}\n")
        except OSError:
            pass
    json.dump(st, open(sf + ".tmp", "w"))
    os.replace(sf + ".tmp", sf)


def calibrate(days):
    per_pct = per_pct_now()
    cut = time.time() - days * 86400
    files = [p for p in glob.glob(f"{HOME}/.claude/projects/*/*.jsonl") if os.path.getmtime(p) >= cut]
    turns = shown = 0
    ex = []
    for p in files:
        agent = agent_of(os.path.basename(p)[:-6]) or "?"
        hist, last, cur, cur_ts = [], 0, [], 0

        def flush():
            nonlocal hist, last, turns, shown
            if not cur:
                return
            c = turn_cost(cur)
            if c["total"] <= 0:
                return
            if cur_ts >= cut:
                turns += 1
                line = decide(c, hist, per_pct, cur_ts, last)
                if line:
                    shown += 1
                    last = cur_ts
                    ex.append((time.strftime("%m-%d %H:%M", time.localtime(cur_ts)), agent, line))
            hist = (hist + [c["total"]])[-HIST:]
        for l in open(p, encoding="utf-8", errors="replace"):
            try:
                o = json.loads(l)
            except ValueError:
                continue
            if is_prompt(o):
                flush()
                cur = []
                try:
                    cur_ts = time.mktime(time.strptime(o.get("timestamp", "")[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
                except ValueError:
                    cur_ts = 0
            cur.append(o)
        flush()
    print(f"units per 1% of the session: {per_pct}; turns in {days} days: {turns}; lines that would show: "
          f"{shown} ({100 * shown / max(turns, 1):.1f}%)")
    for e in ex[-14:]:
        print(" ", e[0], e[1], "|", e[2][:330])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:      # fail-open
        try:
            open(f"{HOME}/.claude/hook-errors.log", "a").write(f"{time.strftime('%FT%T')} cost-guard: {type(e).__name__}: {str(e)[:120]}\n")
        except OSError:
            pass
    sys.exit(0)
