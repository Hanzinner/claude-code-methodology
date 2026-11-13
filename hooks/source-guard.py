#!/usr/bin/env python3
"""source-guard — Stop detector: a "fact about the world" stated without a primary source.
Recurring mistake class: prices / taxes / eligibility rules taken from an aggregator or "my training data" instead of
the official site or document, then presented as fact.

A paragraph is a "fact about the world" when it has (a) money or a percentage next to a word like price / tax / salary /
rate / cost / rent / fine / pension / payment / duty / dose, or (b) a categorical claim in a state/legal context
("no country allows…", "by law", "mandatory/forbidden/impossible … visa/tax/law").
Flag unless the paragraph contains: a URL, `file:line`, "source", "according to", or a hedge (looks like / probably /
approximately / roughly / ~ / ≈ / not verified / as far as I know).
Quotes/code/`>` lines don't count (clean() of pause-guard). Logger: ~/.claude/source-hits.log + flag
~/.claude/source-guard-flags/<session_id> (finished hint, shown once on the next prompt).
`--calibrate [days]` runs over your own transcripts. Config: CCM_LANG_EXTRA ("uk" adds Ukrainian lists)."""
import glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402

UK = "uk" in conf("CCM_LANG_EXTRA", "")


def _clean(text):
    try:
        import importlib.util as U
        s = U.spec_from_file_location("pause_guard", os.path.join(HERE, "pause-guard.py"))
        m = U.module_from_spec(s); s.loader.exec_module(m)
        return m.clean(text)
    except Exception:
        return text


def rx(en, uk=""):
    return re.compile("|".join(f"(?:{p})" for p in (en, uk if UK else "") if p), re.I)


MONEY = rx(r"(\d[\d\s.,]*\s?(?:%|€|\$|£|₾|₴|percent\b|dollars|euros|pounds|USD|EUR|GEL|UAH|CAD|GBP))|((?:€|\$|£|₾)\s?\d)",
           r"(\d[\d\s.,]*\s?(?:грн|гривень|лар[іи]?|євро|доларів))")
MONEY_CTX = rx(r"\btax(?:es)?\b|salar|wage|(?:tax|interest|exchange|mortgage|hourly|flat) rate|\bcosts?\b|\bprice|\brent\b|\bfines?\b(?= of|:)|\bfined\b|penalt|pension|"
               r"payment|\bduty\b|\bdoses?\b|dosage|income|profit|discount|\bfees?\b|premium|subsid|allowance",
               r"пода[тк]|зарплат|ставк|вартіст|цін[аиі]|коштує|оренд|штраф|пенсі|виплат|мит[оа]|доз[аиу]|дохід|прибут|знижк|збір|внес[ок]")
# categorical — only in a state/legal context (a bare "forbidden / mandatory" is mostly technical text, i.e. noise)
CATEG = rx(r"\bno (?:country|government|bank|embassy|jurisdiction)\b|nowhere in the world|\bby law\b|under the law|"
           r"\b(?:mandatory|required|forbidden|prohibited|illegal|impossible|not allowed|not permitted)\b[^.\n]{0,40}\b(?:visa|residen\w+|citizen\w*|tax\w*|declaration|registration|immigration|laws?|embassy|passport|prescription|permit)\b",
           r"жодн(?:а|ої|ий) (?:країн|держав|закон|банк|уряд|посольств)|ніде в світі|за законом|"
           r"(?:обов['’]язков|заборонен|неможлив|не дозволя)\w*[^.\n]{0,40}(?:віз|резиден|громадян|податк|декларац|реєстрац|імігр|закон|посольств|паспорт|рецепт|лікар)")
SOURCE = rx(r"https?://|\b[\w./-]+\.\w{1,5}:\d+|\bsources?\b|according to|\bper the\b|as of \d|based on the (?:official|docs)|"
            r"looks like|seems|likely|probabl|approximat|roughly|ballpark|≈|~\s?\d|not (?:verified|checked)|haven't (?:verified|checked)|unverified|"
            r"as far as i (?:know|can tell)|my estimate|i (?:think|believe|guess)|\bmight\b|\bmaybe\b|possibly|perhaps|appears to",
            r"джерел|за даними|згідно з|за звітом|схоже|ймовірн|приблизн|орієнтовн|не перевіря|не певен|за моєю оцінк|здається|можливо|станом на \d")


def verdict(text):
    for p in re.split(r"\n\s*\n", _clean(text)):
        if SOURCE.search(p):
            continue
        mm = MONEY.search(p) if MONEY_CTX.search(p) else None
        m = mm or CATEG.search(p)
        if m:
            return m.group(0).strip(), p.strip()[:160]
    return None


def last_assistant(tp):
    a = ""
    try:
        with open(tp, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("type") == "assistant":
                    for c in (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content") or []:
                        if isinstance(c, dict) and c.get("type") == "text":
                            a = c["text"]
    except OSError:
        pass
    return a


def main():
    d = json.load(sys.stdin)
    if d.get("stop_hook_active"):
        return
    sid = d.get("session_id") or "unknown-" + time.strftime("%m%d-%H%M")
    v = verdict(last_assistant(d.get("transcript_path", "")))
    if not v:
        return
    home = os.path.expanduser("~")
    os.makedirs(f"{home}/.claude/source-guard-flags", exist_ok=True)
    with open(f"{home}/.claude/source-hits.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%F %T')} [{sid[:8]}] «{v[0]}» :: {v[1]}\n")
    with open(f"{home}/.claude/source-guard-flags/{sid}", "w", encoding="utf-8") as f:
        f.write(f"⚠️ [source-guard] Last turn you stated a fact about the world without a source: \"{v[0]}\" in: {v[1][:120]}. "
                "Name the primary source (URL of the official site or document) or say plainly \"looks like / not verified\" — "
                "don't present it as fact. (Taking an aggregator's number, or \"my data says\", instead of the official page is a recurring mistake.)")


def calibrate(days):
    cutoff, n, hits = time.time() - days * 86400, 0, []
    for tp in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        if os.path.getmtime(tp) < cutoff:
            continue
        with open(tp, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("type") != "assistant":
                    continue
                for c in (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "text":
                        n += 1
                        v = verdict(c["text"])
                        if v:
                            hits.append((os.path.basename(tp)[:8], v))
    print(f"— texts: {n}, hits: {len(hits)} ({100 * len(hits) / max(n, 1):.1f}%)")
    import random
    random.seed(1)
    for s, v in random.sample(hits, min(25, len(hits))):
        print(f"  [{s}] «{v[0]}» :: {v[1][:150].replace(chr(10), ' ')}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        calibrate(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
        sys.exit(0)
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
