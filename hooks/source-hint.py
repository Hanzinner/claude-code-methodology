#!/usr/bin/env python3
"""source-hint — PostToolUse on web search (mcp__search__search, WebSearch): a query about LAW (visa, residency, tax,
quota, permit, eligibility) → a hint "state who-is-eligible lists only from an official page you opened yourself" plus the
official addresses found in the results.

Why: an agent once presented a row from a consultancy's table as the headline finding ("country X is in the programme")
— the official site doesn't list it. Checking the reply text afterwards (source-guard) doesn't catch it: agents rarely
write URLs. The mistake happens at search time, so the hint comes at search time. In a 30-day calibration the official
site WAS in the results for almost every legal query — the problem is which page the agent opened, not the results.
Once per 30 min per session (a series of searches = one hint). Any error → silent.
Config: CCM_HUMAN_NAME, CCM_LANG_EXTRA ("uk" adds Ukrainian query terms)."""
import json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

UK = "uk" in conf("CCM_LANG_EXTRA", "")
_JUR_EN = (r"\bvisas?\b|residen|citizen|immigr|emigr|permit|\bPR\b|quota|\btax|eligib|work.?holiday|express entry|LMIA|asylum|"
           r"green card|blue card|entry requirements?|customs duty")
_JUR_UK = r"віз[аиуі]\b|візов|резиден|громадян|імігр|іммігр|квот|податк|ВНЖ|посвідк|притулок"
JUR = re.compile(_JUR_EN + (("|" + _JUR_UK) if UK else ""), re.I)
URL = re.compile(r"https?://([\w.-]+)(/[^\s\"'<>)\]\\]*)?")      # no «\»: the response arrives as a JSON string, a literal \n follows the address
GOV = re.compile(r"(\.gov(\.|$)|\.gc\.ca$|(^|\.)canada\.ca$|\.gouv\.|europa\.eu$|\.go\.\w+$|\.admin\.ch$|\.bund\.de$|(^|\.)rs\.ge$|"
                 r"parliament|legislation|laws-lois|uscis|\.gob\.|\.govt\.|\.gv\.at$|overheid\.nl$)", re.I)
EVERY = 1800


def hint(query, result_text):
    """→ hint text or None (the query is not about law)."""
    if not JUR.search(query or ""):
        return None
    gov, other = [], []
    for m in URL.finditer(result_text or ""):
        host = m.group(1).lower().rstrip(".")
        (gov if GOV.search(host) else other).append((host, m.group(0).rstrip(".,;")))
    seen, gu = set(), []
    for h, u in gov:
        if u not in seen:
            seen.add(u); gu.append(u)
    oh = sorted({h for h, _ in other})[:4]
    who = conf("CCM_HUMAN_NAME", "the user")
    head = (f"⚖️ [source-hint] A query about law (visa / status / tax / quota). Who is eligible, thresholds, country lists — state them to {who} "
            "ONLY from an official page you opened yourself (WebFetch) and where you saw the line; consultancy and aggregator tables go "
            "stale for years (once a table row said \"country X is in the programme\" — the official site did not list it). ")
    if gu:
        return head + "Official in the results: " + " · ".join(gu[:3]) + ". Not opened — write \"looks like\", not \"is\"."
    return head + f"There are NO official pages in these results (found: {', '.join(oh) or '—'}) — find the official one with a separate search; until then it is a hypothesis, say \"looks like\"."


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    d = json.loads(raw)
    if d.get("tool_name") not in ("mcp__search__search", "WebSearch"):
        return
    h = hint(str((d.get("tool_input") or {}).get("query") or ""), json.dumps(d.get("tool_response"), ensure_ascii=False))
    if not h:
        return
    sid = d.get("session_id") or "x"
    st = os.path.expanduser("~/.claude/source-hint")
    os.makedirs(st, exist_ok=True)
    mp = f"{st}/{sid}"
    try:
        if time.time() - os.path.getmtime(mp) < EVERY:
            return
    except OSError:
        pass
    open(mp, "w").write(str(int(time.time())))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": h}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
