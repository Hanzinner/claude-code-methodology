#!/usr/bin/env python3
"""pause-guard — Stop gate against babysitting: "shall we call it a day?", "go get some rest", "pick this up tomorrow?".
The reflex creeps back into replies even when a written rule forbids it — text documents, it doesn't stop.
The human decides when to stop; the agent ends with the next step or the substance, not with a pause offer.

Two lists:
  PAT        wide  → the hit is only logged + flagged (shown to the agent on its next prompt, once)
  BLOCK_PAT  narrow → BLOCKS the reply, but only when the offer/wish sits in the FINAL paragraph
                      (where the agent closes with a question or a wish). Anywhere else → flag only.
Not matched: quotes ("…" “…” «…» `…`), code blocks, `>` quote lines, negated hits ("no need to call it a day").
Loop guard: stop_hook_active → flag only (the reply was already rewritten once after a block).
Calibrate against your own transcripts: `pause-guard.py --calibrate [days]`.
Stop branch, BLOCKING: it prints {"decision":"block",...}. Flag: ~/.claude/pause-guard-flags/<session_id> (finished hint).
Config: CCM_HUMAN_NAME (named in the block reason), CCM_LANG_EXTRA (contains "uk" → Ukrainian phrase lists too)."""
import glob, json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

UK = "uk" in conf("CCM_LANG_EXTRA", "")

# --- English: how an agent actually phrases a pause offer / wish -------------------------------------------------
_OFFER = r"(?:shall we|should we|do you want to|want to|wanna|would you like to|are you ready to|ready to|let's|let us|we could|we can|we should|why don't we|how about we)"
_WISH = r"(?:you (?:should|might want to|may want to|could|need to|ought to|deserve to|probably should)|why not|maybe|perhaps|time to|worth|let's|go and|go)"
_WHEN = r"(?:tomorrow|later today|later|next time|another time|in the morning|after (?:a |some )?(?:break|rest|sleep|lunch)|when you(?:'re| are) (?:rested|back|fresh))"
_BREAK = r"(?:a |some )?(?:short |quick |little |proper |good )?(?:break|breather|rest|nap)"

PAT_EN = (
    r"enough for (?:today|tonight|now|the day)|that(?:'s| is) (?:it|all) for (?:today|tonight|now)"
    r"|call it a (?:day|night|wrap)|(?:stop|pause|wrap up|break)(?: here)? for (?:today|tonight|the day|the night)"
    rf"|{_OFFER} (?:stop|pause|wrap up|call it|break|take {_BREAK}|rest)\b"
    rf"|(?:shall we|should we|do you want to|want to|would you like to|we can|we could|let's|I(?:'ll| can| will)) (?:pick (?:this|it|things) (?:back )?up|continue|resume|revisit|come back to (?:this|it)) (?:this |it |things )?{_WHEN}"
    r"|good (?:stopping|breaking|pausing) point|natural (?:stopping|breaking|pausing) point"
    rf"|{_WISH} (?:take|grab|have|get) {_BREAK}|time for {_BREAK}|(?:need|deserve) {_BREAK}"
    r"|(?:get|grab) some (?:rest|sleep|shut-?eye)|rest up|go (?:and )?rest|sleep well|sleep on it"
    r"|take care of yourself|look after yourself|(?:don't|do not) (?:stay up|overwork yourself|burn yourself out|push yourself)"
    r"|fresh (?:eyes|start|mind|head)s? (?:in the morning|tomorrow|after)|(?:with )?(?:a )?fresh (?:eyes|start) tomorrow"
    r"|how are you (?:feeling|holding up|doing)\b|how are you\?"
)
BLOCK_EN = (
    r"enough for (?:today|tonight|the day)|that(?:'s| is) (?:it|all) for (?:today|tonight)"
    r"|call it a (?:day|night)|(?:stop|pause|wrap up|break) here for (?:today|tonight|the day|the night)"
    rf"|{_OFFER} (?:stop|pause|wrap up|call it|break|take {_BREAK}|rest)\b[^.!?\n]{{0,25}}(?:for (?:today|tonight|now|the day)|here)"
    rf"|(?:shall we|should we|do you want to|want to|would you like to|we can|we could|let's|I(?:'ll| can| will)) (?:pick (?:this|it|things) (?:back )?up|continue|resume|revisit|come back to (?:this|it)) (?:this |it |things )?{_WHEN}"
    r"|good (?:stopping|breaking|pausing) point"
    rf"|{_WISH} (?:take|grab|have|get) {_BREAK}|time for {_BREAK}|you (?:probably )?(?:need|deserve) {_BREAK}"
    r"|(?:get|grab) some (?:rest|sleep|shut-?eye)|rest up|go (?:and )?rest|sleep well"
    r"|take care of yourself|look after yourself|(?:don't|do not) (?:stay up|overwork yourself|burn yourself out)"
    r"|fresh (?:eyes|start|mind|head) (?:in the morning|tomorrow)"
)
NEG_EN = r"(?:don't|do not|doesn't|never|no need to|not|isn't|aren't|without|no)"

# --- Ukrainian (CCM_LANG_EXTRA=uk) -------------------------------------------------------------------------------
PAT_UK = (
    r"досить на (?:сьогодні|нині)|на сьогодні досить|чи ?пауз|паркуєм"
    r"|продовжимо (?:завтра|пізніше|іншим разом)|добра точка зупин|відпочин"
    r"|як ти\?|на цьому (?:все|зупин)|висплись|на ранок свіжими"
    r"|завтра з новими силами|бережи себе|не засиджуйся"
)
BLOCK_UK = (
    r"досить на (?:сьогодні|нині)|на сьогодні досить|(?:чи|може|зробимо|зробити) пауз[аиу]?\s*(?:[?.]|$)"
    r"|продовжимо (?:завтра|пізніше|іншим разом)|добра точка (?:для )?зупин"
    r"|(?:іди|піди|варто|час|треба) (?:б )?відпоч|відпочинь|відпочивай"
    r"|висплись|на ранок свіжими|завтра з новими силами|бережи себе|не засиджуйся"
)
NEG_UK = r"(?:не|ні|ще не|вже не)"


def _join(*parts):
    return "|".join(f"(?:{p})" for p in parts if p)


PAT = re.compile(_join(PAT_EN, PAT_UK if UK else ""), re.I)
BLOCK_PAT = re.compile(_join(BLOCK_EN, BLOCK_UK if UK else ""), re.I)
QUOTES = [r"«[^»\n]*»", r"“[^”\n]*”", r"\"[^\"\n]*\"", r"`[^`\n]*`"]
NEG = re.compile(r"(?:^|[\s,(])" + _join(NEG_EN, NEG_UK if UK else "") + r"\s+(?:\S+\s+)?$", re.I)


def clean(text):
    """strip code blocks, `>` quote lines and quoted spans — what the agent merely cites doesn't count"""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    if "```" in text:  # unclosed block (cut off / forgot to close) — the tail is code too
        text = text[:text.index("```")]
    text = text.replace("**", "")
    text = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith(">"))
    for q in QUOTES:
        text = re.sub(q, "", text)
    return text


def negated(text, start):
    """the match is negated: a negation up to 1 word before it in the same sentence ("no need to call it a day")"""
    head = re.split(r"[.!?\n]", text[max(0, start - 40):start])[-1]
    return bool(NEG.search(head))


def first_hit(pat, text):
    for m in pat.finditer(text):
        if not negated(text, m.start()):
            return m.group(0)
    return None


def last_para(text):
    paras = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return paras[-1] if paras else ""


def verdict(text):
    """→ (action, match): ('block'|'flag'|None, str)"""
    t = clean(text)
    h = first_hit(BLOCK_PAT, last_para(t))
    if h:
        return "block", h
    h = first_hit(PAT, t)
    return ("flag", h) if h else (None, "")


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
                    for c in (o.get("message") or {}).get("content") or []:
                        if isinstance(c, dict) and c.get("type") == "text":
                            a = c["text"]
    except OSError:
        pass
    return a


def main():
    d = json.load(sys.stdin)
    sid = d.get("session_id") or "unknown-" + time.strftime("%m%d-%H%M")
    action, hit = verdict(last_assistant(d.get("transcript_path", "")))
    if not action:
        return
    if d.get("stop_hook_active"):
        action = "flag"  # already rewritten once after a block — don't spin a loop
    home = os.path.expanduser("~")
    os.makedirs(f"{home}/.claude", exist_ok=True)
    with open(f"{home}/.claude/pause-guard.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%F %T')} [{sid[:8]}] pause reflex ({action}): «{hit}»\n")
    who = conf("CCM_HUMAN_NAME", "the user")
    if action == "block":
        print(json.dumps({"decision": "block", "reason":
            f"⛔ pause-guard: your final paragraph offers a pause / rest (\"{hit}\"). Rewrite the ending: finish with the "
            f"next step or with the substance, with no offer to stop. {who} will say when to stop."}, ensure_ascii=False))
        return
    os.makedirs(f"{home}/.claude/pause-guard-flags", exist_ok=True)
    with open(f"{home}/.claude/pause-guard-flags/{sid}", "w", encoding="utf-8") as f:
        f.write(f"⚠️ [pause-guard] Last turn you offered a pause or babysat (\"{hit}\"). Don't repeat it: "
                f"{who} decides when to stop. End with the next step or the substance.")


def calibrate(days):
    cutoff = time.time() - days * 86400
    n = 0
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
                for c in (o.get("message") or {}).get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "text":
                        n += 1
                        a, h = verdict(c["text"])
                        if a == "block":
                            print(f"BLOCK [{os.path.basename(tp)[:8]}] «{h}» :: "
                                  + last_para(clean(c["text"]))[:220].replace("\n", " "))
    print(f"— texts: {n}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        calibrate(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
        sys.exit(0)
    try:
        main()
    except Exception:
        # not swallowed silently: trace to stderr + rc=1 → the dispatcher logs it. The reply is not blocked.
        import traceback
        traceback.print_exc()
        sys.exit(1)
