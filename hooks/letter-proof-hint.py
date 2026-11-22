#!/usr/bin/env python3
"""letter-proof-hint — a result number in a letter to another agent that is not in the tool output → a hint.

Why: an agent writes the letter in the same call as the run, or right after it, and takes the number from how many
cases there SHOULD be ("test 21/21" while the output said 20/20; "6/6" while it said 5/5). It happened twice in one
week in the original swarm. proof-guard watches the final answer; nothing watched the letters.

PreToolUse on Bash (a call of inbox_post.sh: the letter is the arguments after the addressee, plus heredoc bodies) and
on SendMessage (tool_input.message): pulls the RESULT CLAIMS out of the letter - "N/M" next to a word like
test/pass/case/green/check, "N pass|ok|PASS|green", "M fail|FAIL|red" - and looks for each one in what did NOT come
from the agent in the last WINDOW bytes of the transcript: tool output, letters and hints delivered by hooks, the
human's messages (a number retold from someone else's report arrives by a hook, not as a tool_result). Not found →
the hint "the number is not from the output: check it before sending" + a line in ~/.claude/letter-proof-hits.log.
Not a block: the hint fires before the letter goes; `--calibrate [days]` replays the letters of your transcripts so
you can see how often it would fire before you decide anything stronger.

Proof of a claim (lenient on purpose - it catches "no such number in the output", not a format; on the original
history exact patterns gave 63% false hits: "pages not PASS: 0 of 11" honestly reads as 11/11):
  N/M, N pass, M fail ← the number(s) in any RESULT LINE of the output (a line with pass/ok/fail/test/✓/"of"…);
                        for N/M - M and N in one line (N == M: M is enough)
  "rc N" in a letter is not a claim: in letters it almost always describes an intent ("rc 3 means it could not measure").
A number quoted in «…» / “…” / "…" is someone else's and is not a claim.
Fail-open under hook-safe.sh. Config: CCM_LANG_EXTRA ("uk" adds the Ukrainian words); env LETTER_PROOF_WINDOW (bytes)."""
import json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

UK = "uk" in conf("CCM_LANG_EXTRA", "")
WINDOW = int(os.environ.get("LETTER_PROOF_WINDOW") or 6 * 1024 * 1024)
LOG = os.path.expanduser("~/.claude/letter-proof-hits.log")


def alt(en, uk):
    return en + ("|" + uk if UK else "")


# --- lexicon: English always, Ukrainian with CCM_LANG_EXTRA=uk -----------------------------------------------------
CTX = r"(?:" + alt(r"test\w*|pass\w*|PASS|fail\w*|FAIL|cases?\b|green\b|checks?\b|ok\b|OK\b",
                   r"тест\w*|кейс\w*|зелен\w*|червон\w*|перевір\w*|прогін|прогон\w*") + r")"
UNIT = r"(?:" + alt(r"tests?|cases?|checks?|cells?|pages?", r"тест\w*|кейс\w*|перевір\w*|комір\w*|сторін\w*") + r")\s+"
PASS_W = alt(r"pass(?:ed)?|PASS(?:ED)?|ok|OK|green|tests?\s+green", r"зелен\w*|тест\w*\s+зелен\w*")
FAIL_W = alt(r"fail(?:ed)?|FAIL(?:ED)?|red", r"червон\w*")
NOT_COUNT = alt(r"px|width|×|\bx\d", r"ширин")                   # screen widths next to a fraction
HTTP_CTX = alt(r"HTTP|status|code|curl", r"статус|код")             # HTTP codes next to a fraction
# A line of output "about a result": only in such lines is a number looked for. Output formats differ ("0 of 11",
# "PASS: 16 cells", "11 pass, 0 fail"), so the proof is the NUMBER in a result line, not an exact pattern.
RESULT_LINE = re.compile(alt(r"pass|ok\b|fail|green|test|✓|✗|rc\s*[=:]|exit(?:ed with)? code|problems|broken|missing|"
                             r"check|cells?|\d\s+of\s+\d",
                             r"зелен|червон|провал|тест|проблем|перевір|комір|\d\s+з\s+\d"), re.I)
RW = r"(?:" + alt(r"pass\w*|PASS\w*|ok\b|OK\b|fail\w*|FAIL\w*|green|tests?\b|✓|✗|Ran\b|problems|broken|missing|"
                  r"checks?\b|cells?\b|pages?\b|\bof\b",
                  r"зелен\w*|червон\w*|провал\w*|тест\w*|проблем\w*|перевір\w*|комір\w*|сторін\w*|\bз\b") + r")"

FRAC = re.compile(r"(?<![\w./:-])(\d{1,4})\s*/\s*(\d{1,4})(?![\w./:-])")
PASSN = re.compile(r"(?<![\w./:-])(\d{1,4})\s+(?:" + UNIT + r")?(" + PASS_W + r")(?!\w)")
FAILN = re.compile(r"(?<![\w./:-])(\d{1,4})\s+(?:" + UNIT + r")?(" + FAIL_W + r")(?!\w)")
HTTP = {200, 201, 204, 301, 302, 304, 307, 308, 400, 401, 403, 404, 405, 409, 410, 422, 429, 500, 502, 503, 504}
WIDTHS = {320, 360, 375, 390, 414, 768, 800, 1024, 1100, 1280, 1366, 1440, 1920}
QUOTED = re.compile(r"«[^»\n]*»|“[^”\n]*”|\"[^\"\n]{0,200}\"")


def claims(text):
    """→ [(kind, a, b, shown)] result claims in the letter's text."""
    t = QUOTED.sub(" ", text)
    out = []
    for m in FRAC.finditer(t):
        a, b = int(m.group(1)), int(m.group(2))
        near = t[max(0, m.start() - 40):m.end() + 40]
        if (0 < b <= 2000 and a <= b and re.search(CTX, near, re.I) and not re.search(r"\d\s*/\s*\d+\s*/\s*\d", near)
                and not ({a, b} <= WIDTHS | {0} and b in WIDTHS) and not re.search(NOT_COUNT, near)
                and not ({a, b} <= HTTP or 100 <= a < 600 and 100 <= b < 600 and re.search(HTTP_CTX, near, re.I))
                and not (m.group(1).startswith("0") and len(m.group(1)) > 1)):   # "0026/0027" - numbers, not a count
            out.append(("frac", a, b, m.group(0)))
    for m in PASSN.finditer(t):
        if not (m.group(1).startswith("0") and len(m.group(1)) > 1):   # "0059 PASS" - a decision number, not a count
            out.append(("pass", int(m.group(1)), None, m.group(0)))
    for m in FAILN.finditer(t):
        if not (m.group(1).startswith("0") and len(m.group(1)) > 1):
            out.append(("fail", int(m.group(1)), None, m.group(0)))
    seen, uniq = set(), []
    for c in out:
        if c[:3] not in seen:
            seen.add(c[:3]); uniq.append(c)
    return uniq


def _n(n):
    return rf"(?<![\d.,/:-]){n}(?![\d])"


def near_word(l, num):
    """num stands within 30 characters of a result word in line l."""
    for m in re.finditer(_n(num), l):
        if re.search(RW, l[max(0, m.start() - 30):m.end() + 30], re.I):
            return True
    return False


def supported(c, lines):
    kind, a, b, _ = c
    if kind == "frac":
        for l in lines:
            if re.search(rf"{_n(a)}\s*/\s*{_n(b)}", l):
                return True
            # "0 of 11" / "not PASS: 0 of 11" / "11 pass, 0 fail" - both numbers close (≤40 chars) and a result word
            for m in re.finditer(_n(b), l):
                win = l[max(0, m.start() - 40):m.end() + 40]
                if re.search(RW, win, re.I) and (a == b or re.search(_n(a), win) or re.search(_n(b - a), win)):
                    return True
        return False
    return any(near_word(l, a) for l in lines)


def result_lines(ev):
    return [l for l in ev.split("\n") if RESULT_LINE.search(l)]


def strings(o, out):
    if isinstance(o, str):
        out.append(o)
    elif isinstance(o, dict):
        for v in o.values():
            strings(v, out)
    elif isinstance(o, list):
        for v in o:
            strings(v, out)


def evidence_of(raw):
    """Text NOT from the agent in a piece of transcript: tool output, letters and hints from hooks, the human's
    messages. The agent's own text is never proof (it would prove the number by having written it)."""
    parts = []
    for line in raw.split("\n"):
        if not line or '"type":"assistant"' in line[:400] or '"type": "assistant"' in line[:400]:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if not isinstance(o, dict) or o.get("type") == "assistant":
            continue
        out = []
        strings(o.get("message") or {}, out)
        strings(o.get("attachment") or {}, out)
        strings(o.get("toolUseResult") or {}, out)
        parts.append("\n".join(out))
    return "\n".join(parts)


def evidence(tp):
    try:
        with open(tp, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - WINDOW))
            return evidence_of(f.read().decode("utf-8", "replace"))
    except OSError:
        return ""


HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)^\s*\2\s*$", re.S | re.M)


def letter_of(tool, ti):
    """The letter's text. Bash: the arguments of inbox_post.sh after the addressee (shlex removes the command's own
    quotes - otherwise QUOTED would cut the whole letter out as "…") + heredoc bodies."""
    if tool == "Bash":
        cmd = ti.get("command") or ""
        if "inbox_post" not in cmd:
            return ""
        import shlex
        bodies = [m.group(3) for m in HEREDOC.finditer(cmd)]
        flat = HEREDOC.sub(" ", cmd)
        parts = []
        for seg in re.split(r"\n|&&|;", flat):
            if "inbox_post" not in seg:
                continue
            try:
                toks = shlex.split(seg[seg.index("inbox_post"):])
            except ValueError:
                toks = seg[seg.index("inbox_post"):].split()
            parts += toks[2:]          # [script, addressee, …text]
        return "\n".join(parts + bodies)
    if tool == "SendMessage":
        m = ti.get("message")
        return m if isinstance(m, str) else json.dumps(m, ensure_ascii=False) if m else ""
    return ""


def verdict(letter, ev):
    lines = result_lines(ev)
    return [c[3] for c in claims(letter) if not supported(c, lines)]


def main():
    d = json.load(sys.stdin)
    letter = letter_of(d.get("tool_name"), d.get("tool_input") or {})
    if not letter or not claims(letter):
        return
    bad = verdict(letter, evidence(d.get("transcript_path") or ""))
    if not bad:
        return
    sid = (d.get("session_id") or "x")[:8]
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')} [{sid}] {d.get('tool_name')} not in output: {' | '.join(bad)[:300]}\n")
    except OSError:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
        f"🔢 [letter-proof] The letter has a result number that is not in the tool output of this stretch: "
        f"{' · '.join(bad[:5])}. The usual cause: the number came from intent (how many there should be), not from "
        "a line of output. Check it against the output and fix the letter BEFORE sending - or say where the number "
        "comes from (someone else's report, an older run)."}}, ensure_ascii=False))


def calibrate(days):
    """Every inbox_post / SendMessage call in the history → proof = the WINDOW bytes before it in the same file."""
    import glob
    cutoff, n, with_claims, hits, ex = time.time() - days * 86400, 0, 0, 0, []
    for tp in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        if os.path.getmtime(tp) < cutoff:
            continue
        try:
            raw = open(tp, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        pos = 0
        for line in raw.split("\n"):
            pos += len(line) + 1
            if '"tool_use"' not in line or ("inbox_post" not in line and "SendMessage" not in line):
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            for x in ((o.get("message") if isinstance(o.get("message"), dict) else {}).get("content") or []):
                if not (isinstance(x, dict) and x.get("type") == "tool_use"):
                    continue
                letter = letter_of(x.get("name"), x.get("input") or {})
                if not letter:
                    continue
                n += 1
                if not claims(letter):
                    continue
                with_claims += 1
                bad = verdict(letter, evidence_of(raw[max(0, pos - WINDOW):pos]))
                if bad:
                    hits += 1
                    ex.append((os.path.basename(tp)[:8], bad[:4]))
    for e in ex[-40:]:
        print("HIT", e[0], e[1])
    print(f"- letters: {n}, with result claims: {with_claims}, not proven by output: {hits}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--calibrate"]:
        calibrate(int(sys.argv[2]) if len(sys.argv) > 2 else 14)
        sys.exit(0)
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(1)
