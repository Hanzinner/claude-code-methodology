#!/usr/bin/env python3
"""token_daily_report.py - a daily Claude Code token-usage report as a file the human can open.

Scans ~/.claude/projects/*/*.jsonl, sums one day's usage from assistant turns, computes the API-equivalent cost and
writes <dir>/<YYYY-MM-DD>.md and <dir>/<YYYY-MM-DD>.json (default dir ~/.claude/reports/token-daily/), plus
<dir>/latest.md. No messaging: the original sent this to a chat bot; here the file is the report.

Idempotent: if the day's report already exists the run does nothing (rc 0) unless --force - so the cron line can fire
hourly and the report appears once, as soon as the day is over ("--after HOUR" holds it back until that local hour).

Usage:  token_daily_report.py [--date YYYY-MM-DD] [--print] [--force] [--after HOUR]
        (no --date -> yesterday in the configured time zone; --print -> stdout only, nothing written)
Cron:   15 * * * * python3 ~/.claude/scripts/token_daily_report.py --after 8
Settings: CCM_TIMEZONE (IANA; empty = system), CCM_HUMAN_NAME (header label), TOKEN_REPORT_PLAN ("api" shows $,
  "subscription" marks $ as an API-equivalent note), CLAUDE_PROJECTS_DIR, TOKEN_REPORT_DIR, SUPERVISOR_SUMMARY.
"""
import glob, json, os, sys, time
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402
from zoneinfo import ZoneInfo

# $ per 1M tokens: input, output, cache read; a 5-minute cache write costs 1.25x input, a 1-hour write 2x input.
# Prices as of 2026-06-24 (the provider's price page); a change is made HERE. Unknown model -> DEFAULT (opus-4-8).
PRICING_AS_OF = "2026-06-24"
_RAW = {
    "claude-fable-5-1": (10, 50, 0.25), "claude-fable-5": (10, 50, 1.0),
    "claude-opus-5-5": (4, 20, 0.20), "claude-opus-5": (5, 25, 0.5),
    "claude-opus-4-8": (5, 25, 0.5), "claude-opus-4-7": (5, 25, 0.5), "claude-opus-4-6": (5, 25, 0.5),
    "claude-sonnet-5": (2, 10, 0.2), "claude-sonnet-4-6": (3, 15, 0.3), "claude-haiku-4-5": (1, 5, 0.1),
}
PRICING = {k: {"in": i, "out": o, "read": r, "w5m": i * 1.25, "w1h": i * 2.0} for k, (i, o, r) in _RAW.items()}
DEFAULT = PRICING["claude-opus-4-8"]


def price(model):
    if not model:
        return DEFAULT
    for k in sorted(PRICING, key=len, reverse=True):        # longest prefix first: opus-5-5 before opus-5
        if model.startswith(k):
            return PRICING[k]
    return DEFAULT


def human(n):
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= div:
            return f"{n / div:.1f}{unit}"
    return str(int(n))


def collect(projdir, target, tz):
    agg = {"in": 0, "out": 0, "read": 0, "w5m": 0, "w1h": 0}
    cost, reqs, by_model = 0.0, 0, {}
    for path in glob.glob(os.path.join(projdir, "*", "*.jsonl")):
        try:
            fh = open(path, encoding="utf-8")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if o.get("type") != "assistant":
                    continue
                msg = o.get("message")
                if not isinstance(msg, dict):
                    continue
                u, ts = msg.get("usage"), o.get("timestamp")
                if not u or not ts:
                    continue
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if dt.astimezone(tz).date() != target:
                    continue
                model = msg.get("model")
                if not model or model.startswith("<"):
                    continue                      # synthetic / injected - not a real API call
                p = price(model)
                inp, out = u.get("input_tokens", 0) or 0, u.get("output_tokens", 0) or 0
                rd = u.get("cache_read_input_tokens", 0) or 0
                cc = u.get("cache_creation") or {}
                w5 = cc.get("ephemeral_5m_input_tokens", u.get("cache_creation_input_tokens", 0) or 0)
                w1 = cc.get("ephemeral_1h_input_tokens", 0) or 0
                agg["in"] += inp; agg["out"] += out; agg["read"] += rd; agg["w5m"] += w5; agg["w1h"] += w1
                cost += (inp * p["in"] + out * p["out"] + rd * p["read"] + w5 * p["w5m"] + w1 * p["w1h"]) / 1e6
                reqs += 1
                by_model[model] = by_model.get(model, 0) + 1
    return agg, cost, reqs, by_model


def supervisor_line():
    """One line from the supervisor's summary (if the machine has one): if both the report and the supervisor
    were dead the human would get nothing - and that stays visible."""
    sup = os.environ.get("SUPERVISOR_SUMMARY", os.path.expanduser("~/.claude/supervisor/summary.json"))
    try:
        s = json.load(open(sup))
        age_h = (time.time() - os.path.getmtime(sup)) / 3600
        if age_h > 1:
            return f"supervisor: silent for {age_h:.0f} h"
        if s.get("problems"):
            return f"supervisor: {len(s['problems'])} problems - {', '.join(str(x) for x in s['problems'][:4])}"
        return f"supervisor: ok ({s.get('checks', '?')} checks)"
    except (OSError, ValueError, TypeError):
        return ""


def render(target, label, plan, agg, cost, reqs, by_model):
    head = f"# Claude tokens - {target.isoformat()}" + (f" - {label}" if label else "")
    if reqs == 0:
        body = f"{head}\n\nNo requests that day.\n"
    else:
        total = sum(agg.values())
        cost_line = f"about ${cost:.2f} (already paid by the subscription)" if plan == "subscription" else f"about ${cost:.2f}"
        models = " · ".join(f"{m.split('claude-')[-1]} x{c}" for m, c in sorted(by_model.items(), key=lambda x: -x[1]) if m)
        body = (f"{head}\n\nRequests: {reqs}\n\n```\n"
                f"Input:       {human(agg['in']):>6}\nOutput:      {human(agg['out']):>6}\n"
                f"Cache write: {human(agg['w5m'] + agg['w1h']):>6}\nCache read:  {human(agg['read']):>6}\n```\n\n"
                f"Total: {human(total)} tokens\n\n{cost_line}\n\n{models}\n")
    sl = supervisor_line()
    return body + (f"\n{sl}\n" if sl else "")


def main():
    args = sys.argv[1:]
    tzname = conf("CCM_TIMEZONE", "")
    tz = ZoneInfo(tzname) if tzname else datetime.now().astimezone().tzinfo
    now = datetime.now(tz)
    if "--after" in args and now.hour < int(args[args.index("--after") + 1]):
        return 0
    target = date.fromisoformat(args[args.index("--date") + 1]) if "--date" in args else (now - timedelta(days=1)).date()
    outdir = os.path.expanduser(os.environ.get("TOKEN_REPORT_DIR", "~/.claude/reports/token-daily"))
    if "--print" not in args and "--force" not in args and os.path.exists(os.path.join(outdir, f"{target.isoformat()}.md")):
        return 0
    projdir = os.path.expanduser(os.environ.get("CLAUDE_PROJECTS_DIR", "~/.claude/projects"))
    label = conf("CCM_HUMAN_NAME", "")
    label = "" if label == "the user" else label
    plan = os.environ.get("TOKEN_REPORT_PLAN", "api")
    agg, cost, reqs, by_model = collect(projdir, target, tz)
    body = render(target, label, plan, agg, cost, reqs, by_model)
    if "--print" in args:
        print(body); return 0
    os.makedirs(outdir, exist_ok=True)
    day = target.isoformat()
    data = {"date": day, "requests": reqs, "tokens": agg, "total_tokens": sum(agg.values()), "cost_usd": round(cost, 4),
            "by_model": by_model, "plan": plan, "pricing_as_of": PRICING_AS_OF}
    for name, text in ((f"{day}.json", json.dumps(data, indent=1)), (f"{day}.md", body)):
        tmp = os.path.join(outdir, f".{name}.{os.getpid()}")
        open(tmp, "w").write(text); os.replace(tmp, os.path.join(outdir, name))
    open(os.path.join(outdir, "latest.md"), "w").write(body)
    print(f"token report written: {os.path.join(outdir, day + '.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
