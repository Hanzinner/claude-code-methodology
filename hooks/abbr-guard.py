#!/usr/bin/env python3
"""abbr-guard — Stop detector for unexpanded abbreviations. Rule: expand an abbreviation on first use, "ABC (what it
is)", until it has become familiar in the conversation.

Abbreviation = 2-5 capital Latin letters (no digits — those are ids/formulas; Roman numerals don't count).
Familiar when: (a) it is in the "## CONFIRMED" section of the glossary file (CCM_GLOSSARY; empty = no glossary);
(b) the human used it themselves in this session, or >= 3 times in the last 120 days (`--build-vocab`, a cron job);
(c) it was already expanded in this session — "ABC (…)", "… (ABC)", "ABC stands for …"; (d) it is on the built-in
whitelist of common ones (OK, AI, PDF, …). Code blocks, `…`, "…", `>` lines don't count (shared clean() of pause-guard).
Logger: ~/.claude/abbr-hits.log + flag ~/.claude/abbr-guard-flags/<session_id> (finished hint, shown once next prompt).
Modes: no args = Stop detector (JSON on stdin); `--build-vocab` = cron (writes ~/.claude/abbr-user-vocab.json);
`--calibrate [days]` = run over your own transcripts.
Config: CCM_GLOSSARY, CCM_HUMAN_NAME."""
import glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402


def _clean(text):
    try:
        import importlib.util as U
        s = U.spec_from_file_location("pause_guard", os.path.join(HERE, "pause-guard.py"))
        m = U.module_from_spec(s); s.loader.exec_module(m)
        return m.clean(text)
    except Exception:
        return text


WHITE = {"OK", "AI", "PDF", "USB", "TV", "VS", "PS", "ID", "UTC", "EDT", "PM", "AM", "CEO",
         "CTO", "COO", "USA", "US", "EU", "UK", "GB", "MB", "KB", "TB", "GHZ", "FAQ", "TODO",
         "DONE", "LIVE", "OPEN", "FAIL", "PASS", "NB", "CV", "IT", "HR", "QA", "HQ", "VPN",
         "CLAIM", "WAIT", "NOTE", "STOP", "READ", "WRITE", "ALL", "NEW", "OLD", "YES", "NO"}  # + words in caps
ABBR = re.compile(r"(?<![\w/.-])([A-Z]{2,5})(?![\w/-]|\.\w)")  # no digits (E4, COM1, SO4); not a file name (README.md)
VOCAB = os.path.expanduser("~/.claude/abbr-user-vocab.json")  # what the human wrote >= 3 times in 120 days
CURRENCY = {"EUR", "USD", "GEL", "UAH", "GBP", "CAD", "PLN", "CHF", "BTC"}


def confirmed():
    g = conf("CCM_GLOSSARY", "")
    if not g:
        return set()
    try:
        t = open(g, encoding="utf-8").read()
    except OSError:
        return set()
    sec = t.split("## CONFIRMED", 1)[-1].split("\n## ", 1)[0]
    return set(re.findall(r"\b[A-Z][A-Z0-9]{1,5}\b", sec))


def user_vocab():
    try:
        return set(json.load(open(VOCAB)))
    except (OSError, ValueError):
        return set()


def build_vocab(days=120, min_uses=3):
    """cron: abbreviations the human wrote in their own prompts (system-reminder blocks stripped)"""
    cnt = {}
    for tp in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        if os.path.getmtime(tp) < time.time() - days * 86400:
            continue
        users, _ = session(tp)
        for u in users:
            u = re.sub(r"<system-reminder>.*?</system-reminder>", "", u, flags=re.S)
            for tok in set(ABBR.findall(u)):
                cnt[tok] = cnt.get(tok, 0) + 1
    known = sorted(k for k, v in cnt.items() if v >= min_uses)
    os.makedirs(os.path.dirname(VOCAB), exist_ok=True)
    tmp = VOCAB + ".tmp"
    json.dump(known, open(tmp, "w")); os.replace(tmp, VOCAB)
    print(f"abbr vocab: {len(known)} abbreviations → {VOCAB}")


def expanded(tok, text):
    e = re.escape(tok)
    return bool(re.search(e + r"\s*\(", text) or re.search(r"\(\s*" + e + r"\s*\)", text)
                or re.search(e + r"\s+(?:stands for|is short for|means)\b|(?:short for|stands for)\s+" + e, text))


def session(tp):
    """→ (the human's texts, the assistant's texts) in order"""
    users, asst = [], []
    try:
        f = open(tp, encoding="utf-8", errors="replace")
    except OSError:
        return users, asst
    with f:
        for line in f:
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            c = (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content")
            if o.get("type") == "user" and not o.get("isMeta"):
                if isinstance(c, str):
                    users.append(c)
                elif isinstance(c, list):
                    users += [x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text"]
            elif o.get("type") == "assistant" and isinstance(c, list):
                for x in c:
                    if isinstance(x, dict) and x.get("type") == "text":
                        asst.append(x["text"])
    return users, asst


def verdict(text, users, prev_asst, known):
    t = _clean(text)
    seen_u = " ".join(users)
    seen_a = " ".join(prev_asst)
    bad = []
    for tok in dict.fromkeys(ABBR.findall(t)):
        if tok in known or tok in WHITE or tok in CURRENCY or re.fullmatch(r"[IVXLC]+", tok):  # Roman numerals
            continue
        if re.search(r"(?<![\w])" + re.escape(tok) + r"(?![\w])", seen_u):
            continue
        if expanded(tok, t) or expanded(tok, seen_a):
            continue
        bad.append(tok)
    return bad


def main():
    d = json.load(sys.stdin)
    if d.get("stop_hook_active"):
        return
    sid = d.get("session_id") or "unknown-" + time.strftime("%m%d-%H%M")
    users, asst = session(d.get("transcript_path", ""))
    if not asst:
        return
    bad = verdict(asst[-1], users, asst[:-1], confirmed() | user_vocab())
    if not bad:
        return
    home = os.path.expanduser("~")
    os.makedirs(f"{home}/.claude/abbr-guard-flags", exist_ok=True)
    with open(f"{home}/.claude/abbr-hits.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%F %T')} [{sid[:8]}] {', '.join(bad[:8])}\n")
    who = conf("CCM_HUMAN_NAME", "the user")
    with open(f"{home}/.claude/abbr-guard-flags/{sid}", "w", encoding="utf-8") as f:
        f.write(f"⚠️ [abbr-guard] Last turn you used abbreviations without expanding them: {', '.join(bad[:8])[:120]}. Rule: expand an "
                f"abbreviation on first use, \"ABC (what it is)\", unless it is in the glossary or {who} uses it themselves.")


def calibrate(days):
    known = confirmed() | user_vocab()
    cutoff, n, hits, cnt = time.time() - days * 86400, 0, 0, {}
    for tp in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        if os.path.getmtime(tp) < cutoff:
            continue
        users, asst = session(tp)
        for i, a in enumerate(asst):
            n += 1
            b = verdict(a, users, asst[:i], known)
            if b:
                hits += 1
                for x in b:
                    cnt[x] = cnt.get(x, 0) + 1
    print(f"— texts: {n}, with a hit: {hits} ({100 * hits / max(n, 1):.1f}%)")
    print("top:", sorted(cnt.items(), key=lambda kv: -kv[1])[:40])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--build-vocab":
        build_vocab(); sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        calibrate(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
        sys.exit(0)
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
