#!/usr/bin/env python3
"""strawman-guard — Stop detector for the strawman and for assertions about the human that nobody gave.
The cheapest fake of disagreement is not nitpicking a word but swapping the position: restate the human's view in a
weaker version → knock down your own restatement → hand them their own idea back as "the better target".
A written rule that appeals to self-checking is weak by construction (the agent has no access to its own generation
process); this detector looks at the WRITTEN text from outside.

Signatures (a flag needs ALL THREE for the first one):
  1) attribution ("your goal is", "you want", "what you're really asking") +
     negation nearby ("wrong", "actually", "the real goal", …) + NO verbatim quote of the last user message
     (check: 5-word n-grams of the normalised user text as substrings of the reply);
  2) fake fork: "your call / pick one / option A … option B" NEXT TO the agent's own admission that the question is
     already (nearly) decided or settled by an existing rule;
  3) STATE OF THE HUMAN stated flatly: "you didn't know / don't like / didn't notice", "you find it hard / boring"
     with no hedge ("?", "maybe", "probably") and the human never said it themselves;
  4) RISK IN THE 2ND PERSON: "your weak spot / risk / red flag" when the human didn't ask about risks. A regex cannot
     know whether the risk is in the data: the flag is a question to the agent — is it in the data, or added so there
     is something to rescue? Added → remove it.
Logger, not a blocker: ~/.claude/strawman-guard.log + a flag per session ~/.claude/strawman-guard-flags/<session_id>
(finished hint text, shown once on the next prompt).
Config: CCM_HUMAN_NAME, CCM_LANG_EXTRA ("uk" adds the Ukrainian lists)."""
import json, os, re, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402

UK = "uk" in conf("CCM_LANG_EXTRA", "")
WHO = conf("CCM_HUMAN_NAME", "the user")


def rx(en, uk=""):
    return re.compile("|".join(f"(?:{p})" for p in (en, uk if UK else "") if p), re.I)


# --- 1) attribution + negation, no quote -------------------------------------------------------------------------
ATTRIB = rx(
    r"\byour (?:real |actual |underlying )?(?:goal|aim|thesis|assumption|idea|logic|premise|claim)\b(?: here)? (?:is|was|seems)"
    r"|\byou(?:'re| are) (?:really |actually |essentially )?(?:assuming|claiming|trying to|suggesting|proposing|implying|arguing)\b"
    r"|\byou (?:want to|mean|believe that|think that|assume that|seem to (?:want|mean|think|believe))\b"
    r"|what you(?:'re| are) (?:really |actually )?(?:asking|after|saying|getting at)"
    # a paraphrase in quotes + a verdict right next to it — what the real strawman looked like
    r"|[\"“][^\"”\n]{8,90}[\"”][^.!\n]{0,45}(?:wrong|misguided|unachievable|incorrect|not the (?:real )?goal)",
    # Ukrainian
    r"тво(?:я|є|ї) (?:ціль|теза|припущення|ідея|логіка)|ти (?:виходиш з того|хочеш|маєш на увазі|пропонуєш|вважаєш, що|припускаєш)"
    r"|«[^»]{8,90}»[^.!\n]{0,45}(?:хибн|недосяжн|неправильн|не ціль)")
NEGATE = rx(
    r"\bwrong\b|misguided|\bincorrect|not quite|\bactually\b|the real (?:goal|issue|question|point|target)|unachievable|unrealistic"
    r"|a (?:better|stronger) (?:goal|framing|target|question)|more accurately|isn't (?:really )?the (?:goal|point)|the (?:better|right) (?:goal|target)",
    r"хибн|не зовсім|насправді|але ціль|недосяжн|неправильн|правильніше|сильніша ціль")
ASKCHECK = rx(
    r"do i understand (?:you )?(?:right|correctly)|am i (?:reading|understanding) (?:you )?(?:right|correctly)"
    r"|if i understand (?:you )?(?:right|correctly)|correct me if|is that (?:right|what you mean)\?",
    r"правильно розумію|чи я вірно|чи правильно я")
# --- 2) fake fork ------------------------------------------------------------------------------------------------
FORK = rx(
    r"\byour (?:call|decision|choice)\b|you decide|pick one|(?:it'?s |the choice is )up to you|the choice is yours|option a\b.{0,40}option b\b|decision: a/b",
    r"тво(?:є|ї) рішення|обери|а чи б|вибір за тобою|рішення[: ]+а/б|варіант а.{0,40}варіант б")
RESOLVED = rx(
    r"(?:already|mostly|basically|practically|effectively|pretty much) (?:decided|settled|resolved)|follows (?:directly )?from (?:the|your|that) (?:rule|principle)"
    r"|no decision (?:is )?needed|the rule already|obvious answer|answered by the rule",
    r"(?:майже|вже|уже|фактично) виріш|само (?:собою|випливає)|не потребує рішення|правило вже|випливає з (?:принципу|правила)|очевидн(?:ий|а) відповідь")
# --- 3) state of the human ---------------------------------------------------------------------------------------
STATE = rx(
    r"\byou (?:just |still |then |simply |clearly )?(?:didn't|did not|don't|do not|never|haven't|have not) (?:know|knew|realize|realise|notice|like|consider|think|understand|remember|see|care)\b"
    r"|\byou (?:find|found) it (?:hard|difficult|boring|scary|uncomfortable|tedious)\b|\bit(?:'s| is) (?:hard|difficult|boring|scary) for you\b"
    r"|\byou(?:'re| are) (?:just |simply )?(?:afraid|scared|lazy|bored|indifferent|uncomfortable)\b",
    r"\bти (?:просто |ще |тоді |цього |про це |сам |сама )?не (?:знав|знала|любиш|помітив|помітила|врахував|врахувала|"
    r"подумав|подумала|розумієш|пам['’]ятаєш|бачив|бачила)\b"
    r"|\bтобі (?:буде |було |зараз )?(?:важко|складно|лінь|страшно|нецікаво|некомфортно|байдуже)\b")
HEDGE = rx(r"\?|\b(?:if|maybe|perhaps|probably|possibly|seems?|looks like|suspect|guess|presumably|might|may|could|assume|apparently)\b",
           r"\?|\bчи\b|\bякщо\b|можлив|схоже|мабуть|ймовірн|напевно|здається|припуска")
# --- 4) risk in the 2nd person -----------------------------------------------------------------------------------
_R = r"(?:risk|red[- ]flag|weak (?:spot|point)|weakness|vulnerabilit\w+|danger|blind spot)"
RISK = rx(
    rf"\b(?:your|you have|you've got)\s+(?:[\w'-]+\s+){{0,3}}{_R}"
    rf"|\b{_R}s?\s+(?:for|to|in) you(?:r\b|\b)|\byou(?:'re| are) (?:at|taking|running) (?:a )?(?:risk|danger)",
    r"(?:тв(?:ій|оя|оє|ої|оєму|оїй|ого)|у тебе|тобі|для тебе)[^.!?\n]{0,70}(?:ризик|ред-флаг|червон\w+ прапор|слабк\w+ місц|слабкіст|вразлив|діра\b|дірк|небезпе)"
    r"|(?:ризик|ред-флаг|червон\w+ прапор|слабк\w+ місц|слабкіст|діра\b)[^.!?\n]{0,70}(?:тв(?:ій|оя|оє|ої)|у тебе|тобі|для тебе|попливеш)")
RISK_NEG = rx(
    r"without (?:any )?(?:risk|weakness)|not (?:a |an )?(?:risk|weakness|weak spot|red[- ]flag)|no (?:real |obvious )?(?:risk|weakness|red[- ]flag)|isn't (?:a |an )?(?:risk|weakness)|not at risk",
    r"без (?:жодн\w+ )?(?:ризик|слабк)|не (?:є )?(?:ризик|слабк|дір|ред-флаг)|нема\w* (?:ризик|слабк|дір)|жодн\w+ (?:ризик|слабк)")
USER_RISK = rx(
    r"\brisk|danger|problem|weak|what'?s wrong|downside|drawback|assess|evaluate|review|should i\b|red[- ]?flag|vulnerab|security|what do you think|critique|audit|concern",
    r"ризик|небезпе|проблем|слаб|що не так|мінус|недолік|оціни|перевір|чи варто|ред.?флаг|вразлив|безпек|що думаєш|критик|рев['’]ю|аудит")


def _clean(text):
    """strip code/quotes the same way pause-guard does (shared clean()); fall back to the raw text"""
    try:
        import importlib.util as U
        s = U.spec_from_file_location("pause_guard", os.path.join(HERE, "pause-guard.py"))
        m = U.module_from_spec(s); s.loader.exec_module(m)
        return m.clean(text)
    except Exception:
        return text


def sentences(t):
    return re.split(r"(?<=[.!?…])\s+|\n+", t)


def check_state_risk(user_text, asst_text):
    """signatures 3 and 4 → reason or None. Quotes/code don't count."""
    t = _clean(asst_text)
    ul = user_text.lower()
    for s in sentences(t):
        m = STATE.search(s)
        if m and not HEDGE.search(s):
            w = m.group(0).lower()
            stem = w.split("не ")[-1][:5] if "не " in w else w.split()[-1][:4]
            if stem not in ul:
                return (f"state of the human: \"{m.group(0)}\" stated flatly. Where is the data that {WHO} knows/feels this? "
                        "It is not in their words — make it a question (\"did you know?\") or remove it")
    if not USER_RISK.search(user_text):
        for s in sentences(t):
            m = RISK.search(s)
            if m and not RISK_NEG.search(s):
                return (f"risk in the 2nd person: \"{m.group(0)[:70]}\", and {WHO} did not ask about risks. Is the risk IN THE DATA "
                        "(quote the fact), or added so there is something to rescue? Added — remove it")
    return None


def norm(t):
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def ngrams(t, n=5):
    w = norm(t).split()
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def last_texts(transcript):
    """(last user text, last assistant text)"""
    u = a = ""
    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("type") == "user":
                    c = (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content")
                    if isinstance(c, str) and not c.startswith("<"):
                        u = c
                    elif isinstance(c, list):
                        t = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
                        if t.strip() and not t.lstrip().startswith("<"):
                            u = t
                elif o.get("type") == "assistant":
                    for cc in (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content") or []:
                        if isinstance(cc, dict) and cc.get("type") == "text":
                            a = cc["text"]
    except OSError:
        pass
    return u, a


def check(user_text, asst_text):
    """→ (kind, reason) or None; kind = 'strawman' | 'state'"""
    if not user_text or not asst_text:
        return None
    if FORK.search(asst_text) and RESOLVED.search(asst_text):
        return "strawman", (f"fake fork: \"{FORK.search(asst_text).group(0)}\" next to "
                            f"\"{RESOLVED.search(asst_text).group(0)}\" (a settled question inflated into a choice)")
    if ATTRIB.search(asst_text) and NEGATE.search(asst_text) and not ASKCHECK.search(asst_text):
        na = norm(asst_text)
        if not any(g in na for g in ngrams(user_text)):  # a verbatim quote = an honest restatement
            return "strawman", f"attribution (\"{ATTRIB.search(asst_text).group(0)}\") + negation with no verbatim quote of the user's text"
    r = check_state_risk(user_text, asst_text)
    return ("state", r) if r else None


def main():
    d = json.load(sys.stdin)
    sid = d.get("session_id", "")
    u, a = last_texts(d.get("transcript_path", ""))
    res = check(u, a)
    if not res:
        return
    kind, reason = res
    home = os.path.expanduser("~")
    os.makedirs(f"{home}/.claude/strawman-guard-flags", exist_ok=True)
    with open(f"{home}/.claude/strawman-guard.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{sid[:8]}] {reason}\n")
    text = f"⚠️ [strawman-guard] Last turn: {reason[:260]}."
    if kind == "strawman":
        text += (f" Rule: when you object to {WHO}'s position, quote it VERBATIM, an exact fragment of their message; no exact "
                 "quote — no objection. Don't attribute goals (\"your logic\", \"you're assuming…\") without a quote next to it.")
    with open(f"{home}/.claude/strawman-guard-flags/{sid}", "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # fail-open, but not silent: trace → stderr, rc=1 → the dispatcher logs it (the reply is never blocked)
        import traceback
        traceback.print_exc()
        sys.exit(1)
