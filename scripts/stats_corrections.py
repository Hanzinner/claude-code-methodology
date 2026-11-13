#!/usr/bin/env python3
"""stats_corrections.py - collect the human's corrections of agents from every tab -> classes -> a verdict -> repeats show.

The problem: a correction lives only in the chat where it was said; the chat compacts - it is gone, nobody remembers,
the same mistake comes back. This script lifts corrections into one place.

Flow:
  1. The human's messages from TABS (UI sessions; not subagents, not `claude -p`) inside a window of days + context
     (the tail of the agent's previous answer).
  2. A cheap model (haiku, no tools, through claude_machine.py - it costs real tokens, uses YOUR claude login) in
     batches: is it a correction of the agent, what was wrong, which class. The model output is UNTRUSTED: only ids from
     our own input and a class from the registry are taken.
  3. <stats>/corrections/YYYY-MM-DD.jsonl - by the day of the message (no duplicates by uuid).
  4. The class registry (<stats>/corrections-classes.json, CORR_REGISTRY) - the verdict is set BY HAND:
     {"<class>": {"verdict": "one-off" | "mechanism" | "accepted", "mech": "...", "since": "YYYY-MM-DD", "note": "..."}}.
     New classes have no verdict.
  5. <stats>/corrections.json: RED = a class without a verdict, or a "mechanism" that repeated AFTER its `since`
     (the mechanism did not work). A "!rule" at the start of a message is always a correction.
Cron (daily is enough):  20 * * * * python3 ~/.claude/scripts/stats_corrections.py --days 3 --after 6
  (--after HOUR: not before that local hour, and once per day after a successful run). rc != 0 if a batch failed.
Letter: when a red class gets new corrections, ONE letter goes to the agent named in CCM_STATS_OWNER (empty = none).
Settings: STATS_DIR, CORR_MODEL (default haiku), CORR_REGISTRY, CLAUDE_BIN (used by claude_machine.py), CCM_TIMEZONE.
"""
import argparse, glob, json, os, re, subprocess, sys, time
from datetime import datetime

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import stats_collect as C  # noqa: E402  human_text, parse_file, agent_of: one definition of "the human's message"
from ccm_conf import conf  # noqa: E402

STATS = C.STATS
DAYDIR = f"{STATS}/corrections"
SEEN = f"{STATS}/.corrections-seen.json"
ALERTED = f"{STATS}/.corrections-alerted.json"      # ids the letter about which ALREADY went (rc 0)
STAMP = f"{STATS}/.corrections-last-ok"
REG = os.environ.get("CORR_REGISTRY", f"{STATS}/corrections-classes.json")
OUT = f"{STATS}/corrections.json"
TZ = C.TZ
MACHINE = os.path.join(HERE, "claude_machine.py")
POST = os.path.join(HERE, "inbox_post.sh")
BATCH = 40
MISS_OK = 0.1   # share of a batch the model may skip even after a retry without failing the run
MODEL = os.environ.get("CORR_MODEL", "haiku")

PROMPT = """You classify messages that a user ({human}) sent to AI agents. For EACH message decide:
- corr: true if the user CORRECTS the agent: the agent did the wrong thing / did it wrongly / did not do it / forgot /
  lied / left it half-done / asks needless questions / used a wrong tone - and the user points that out or is angry.
  Questions, new tasks, "go", "do it", answers to the agent's questions, personal topics - false. Swearing alone is not a sign.
- what: if corr - what exactly the agent did wrong, <=15 words, the gist without a quote. Otherwise "".
- cls: if corr - the error class VERBATIM one of this list: {classes}. None fits - "other". Not corr - "".
A new task, a request to check/search something, a clarification of wishes, an answer to the agent's question are NOT
corrections unless the user says the agent already did something wrong.

"agent before" is the tail of the agent's answer the user is reacting to.
Answer ONLY with a JSON array, one object per id: [{{"id": "...", "corr": true, "what": "...", "cls": "..."}}]

Messages:
{items}"""


def load(p, default):
    """No file -> default. A file that exists but is broken (the registry is edited by hand) -> fail loudly: a silent {}
    would turn every class into "other"."""
    if not os.path.exists(p):
        return default
    try:
        return json.load(open(p))
    except ValueError as e:
        print(f"BROKEN JSON {p}: {e} - fix it and rerun", file=sys.stderr)
        sys.exit(2)


def save(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    json.dump(obj, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def assistant_text(d):
    if d.get("type") != "assistant":
        return None
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list):
        t = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
        return t.strip() or None
    return None


def human_session(p):
    """A human's tab, not a machine `claude -p`: collect's `ui` also catches background calls with a vscode entrypoint
    (reviewers). A human leaves origin=human or UI traces (mode / custom-title / agent-name). The mark is not on every
    message - hence per session."""
    for line in open(p, errors="replace"):
        if '"kind":"human"' in line.replace(" ", "") or '"type":"mode"' in line or \
                '"type":"custom-title"' in line or '"type":"agent-name"' in line:
            return True
    return False


def harvest(since, seen):
    """-> a list of the human's messages from tabs after `since` that we have not seen yet."""
    got, out = set(), []
    for src in C.SRC:
        for p in glob.glob(f"{src}/*/*.jsonl"):
            if os.path.getmtime(p) < since:
                continue
            meta = C.parse_file(p)
            if not meta["ui"] or meta["parent"] or not human_session(p):
                continue
            agent = C.agent_of(meta) or "unnamed"
            last_a = ""
            for line in open(p, errors="replace"):
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                a = assistant_text(d)
                if a:
                    last_a = a
                    continue
                h = C.human_text(d)
                x = C.ts(d.get("timestamp", "")) if d.get("timestamp") else None
                u = d.get("uuid")
                # `got`: the same message in several files of a session (resume/fork copies history) - 103 duplicates once
                if h is None or not x or x < since or not u or u in seen or u in got:
                    continue
                got.add(u)
                out.append({"id": u, "ts": x, "agent": agent, "sid": meta["sid"][:8], "text": h[:600], "ctx": last_a[-400:]})
    return sorted(out, key=lambda r: r["ts"])


def classify(batch, classes):
    items = "\n".join(json.dumps({"id": r["id"], "agent before": r["ctx"], "human message": r["text"]},
                                 ensure_ascii=False) for r in batch)
    prompt = PROMPT.format(human=conf("CCM_HUMAN_NAME", "the user"), classes=json.dumps(classes, ensure_ascii=False), items=items)
    try:
        res = subprocess.run([sys.executable, MACHINE, "corrections", "-p", "--model", MODEL, "--tools", "", "--strict-mcp-config",
                              "--output-format", "text"], input=prompt, capture_output=True, text=True,
                             timeout=600, env={**os.environ, "CCM_MACHINE_SESSION": "1"}, cwd=os.path.expanduser("~"))
    except (subprocess.TimeoutExpired, OSError) as e:
        return None, f"model call: {e}"
    m = re.search(r"\[.*\]", res.stdout, re.S)
    if res.returncode != 0 or not m:
        return None, f"rc={res.returncode}, no JSON: {res.stdout[:200]!r} {res.stderr[:200]!r}"
    try:
        arr = json.loads(m.group(0))
    except ValueError as e:
        return None, f"JSON: {e}"
    ids = {r["id"] for r in batch}
    got = {}
    for o in arr:   # untrusted model output: only our ids, only the fields we need
        if isinstance(o, dict) and o.get("id") in ids:
            got[o["id"]] = {"corr": bool(o.get("corr")), "what": str(o.get("what", ""))[:200],
                            "cls": str(o.get("cls", ""))[:60].strip()}
    return got, None


def is_mechanism(v):
    return str(v or "").lower() in ("mechanism", "механізм")


def aggregate(reg):
    rows = []
    for f in sorted(glob.glob(f"{DAYDIR}/*.jsonl")):
        for line in open(f):
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    uniq = {}
    for r in rows:
        uniq.setdefault(r.get("id") or id(r), r)   # duplicates written before the uuid dedupe are not counted twice
    corr = [r for r in uniq.values() if r.get("corr")]
    by = {}
    for r in corr:
        by.setdefault(r.get("cls") or "no class", []).append(r)
    classes = []
    for k, rs in by.items():
        v = reg.get(k, {})
        since = v.get("since")
        since_ts = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=TZ).timestamp() if since else None
        after = [r for r in rs if since_ts and r["ts"] >= since_ts]
        verdict = v.get("verdict")
        red = (verdict is None) or (is_mechanism(verdict) and bool(after))
        classes.append({"cls": k, "n": len(rs), "agents": sorted({r["agent"] for r in rs}),
                        "last": max(r["ts"] for r in rs), "verdict": verdict, "mech": v.get("mech"),
                        "since": since, "repeat_after_mech": len(after) if is_mechanism(verdict) else 0,
                        "red": red, "_ids": [{"id": r.get("id")} for r in rs],
                        "examples_all": [{"ts": r["ts"]} for r in rs],
                        "examples": [{"ts": r["ts"], "agent": r["agent"], "what": r["what"], "text": r["text"][:200]}
                                     for r in sorted(rs, key=lambda r: -r["ts"])[:5]]})
    classes.sort(key=lambda c: (not c["red"], -c["repeat_after_mech"], -c["n"]))
    days = {}
    for r in rows:
        d = datetime.fromtimestamp(r["ts"], TZ).strftime("%Y-%m-%d")
        a = days.setdefault(d, {"all": 0, "corr": 0})
        a["all"] += 1
        a["corr"] += bool(r.get("corr"))
    return {"generated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"), "days": days, "classes": classes,
            "total": len(corr), "red": sum(c["red"] for c in classes)}


def weekly_line(agg, now=None):
    """One line per ISO week: corrections over 7 days, repeats after a mechanism, the top classes. -> (tag, line) or None.
    The original appended it to the human's TODO; here it goes into the output JSON ("weekly")."""
    now = now or time.time()
    wk = datetime.fromtimestamp(now, TZ).strftime("%G-W%V")
    rows = [(c, [e for e in c["examples_all"] if e["ts"] >= now - 7 * 86400]) for c in agg["classes"]]
    rows = [(c, es) for c, es in rows if es]
    if not rows:
        return None
    n = sum(len(es) for _, es in rows)
    rep = sum(c["repeat_after_mech"] for c, _ in rows)
    top = sorted(rows, key=lambda x: -len(x[1]))[:3]
    tag = f"[corrections {wk}]"
    return tag, (f"{tag} {n} corrections of agents this week; repeats after a mechanism: {rep}" + (" (!)" if rep else "")
                 + " · most frequent: " + ", ".join(f"\"{c['cls']}\" {len(es)}x" for c, es in top))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=2, help="window back, days (messages not yet seen)")
    ap.add_argument("--dry", action="store_true", help="only count the messages, no model call")
    ap.add_argument("--after", type=int, default=None, help="not before this local hour; once per day after a successful run")
    a = ap.parse_args()
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    if a.after is not None and not a.dry:
        if datetime.now(TZ).hour < a.after:
            return 0
        try:
            if open(STAMP).read().strip() == today:
                return 0
        except OSError:
            pass
    seen = set(load(SEEN, []))
    reg = load(REG, {})
    msgs = harvest(time.time() - a.days * 86400, seen)
    print(f"human messages from tabs in {a.days:g} days, new: {len(msgs)}")
    if a.dry:
        return 0
    fails = 0
    classes = sorted(reg)   # the fixed class list is kept by a human in the registry; the model only chooses from it
    for i in range(0, len(msgs), BATCH):
        b = msgs[i:i + BATCH]
        got, err = classify(b, classes)
        if got is None:
            fails += 1
            print(f"BATCH {i // BATCH + 1}: {err}", file=sys.stderr)
            continue
        miss = [r for r in b if r["id"] not in got]
        if miss:    # the model skipped part of the batch (1-2 of 40 a day) - ONE retry of the skipped ones only
            got2, _ = classify(miss, classes)
            got.update(got2 or {})
            miss = [r for r in b if r["id"] not in got]
        if miss:    # still missing: they stay not-seen (the next run takes them); a failure only if it is not a few
            print(f"BATCH {i // BATCH + 1}: the model skipped {len(miss)} of {len(b)} even after a retry", file=sys.stderr)
            if len(miss) > MISS_OK * len(b):
                fails += 1
        by_day = {}
        for r in b:
            if r["id"] not in got:
                continue
            r.update(got[r["id"]])
            if r["text"].lstrip().startswith("!rule"):
                r["corr"] = True
                r["cls"] = r["cls"] or "!rule"
            if r["corr"] and r["cls"] not in classes + ["!rule"]:
                r["cls"] = "other"      # model output outside the list is not a new class
            by_day.setdefault(datetime.fromtimestamp(r["ts"], TZ).strftime("%Y-%m-%d"), []).append(r)
            seen.add(r["id"])
        os.makedirs(DAYDIR, exist_ok=True)
        for d, rs in by_day.items():
            with open(f"{DAYDIR}/{d}.jsonl", "a") as f:
                for r in rs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        save(SEEN, sorted(seen))
    agg = aggregate(reg)
    # recall, not only capture: new corrections in a class without a verdict / a repeat after a mechanism -> a letter
    owner = conf("CCM_STATS_OWNER", "")
    alerted = set(load(ALERTED, []))   # not "new this run": a letter that did not go is repeated next time
    hot = [c for c in agg["classes"] if c["red"] and any(x.get("id") not in alerted for x in c.get("_ids", []))]
    if hot and owner:
        txt = ("corrections - new corrections without a verdict: " +
               " · ".join(f"\"{c['cls']}\" {c['n']}x" + (f" (!{c['repeat_after_mech']} after the mechanism)" if c["repeat_after_mech"] else "")
                          for c in hot[:6]) +
               f" -> set a verdict in {REG} (one-off / mechanism + since / accepted + note); report: {OUT}")
        try:
            rc = subprocess.run([POST, owner, txt], capture_output=True, timeout=30).returncode
        except (OSError, subprocess.TimeoutExpired):
            rc = 1
        if rc:
            print(f"letter to {owner} did not go: rc={rc}", file=sys.stderr)
            fails += 1
        else:
            save(ALERTED, sorted(alerted | {x["id"] for c in hot for x in c.get("_ids", [])}))
    wl = weekly_line(agg)
    if wl:
        agg["weekly"] = wl[1]
    for c in agg["classes"]:
        c.pop("_ids", None)
        c.pop("examples_all", None)
    save(OUT, agg)
    if not fails:
        open(STAMP, "w").write(today)
    print(f"corrections in total {agg['total']}, classes {len(agg['classes'])}, red {agg['red']}; batches with an error {fails} -> {OUT}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
