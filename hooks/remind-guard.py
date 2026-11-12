#!/usr/bin/env python3
"""remind-guard — Stop detector: the agent PROMISED to remind ("I'll remind you", "reminder set") but did not run
scripts/remind.py in that turn -> a flag; on the next prompt the agent is told: set it now and name the time.

Why: the hint on the human's words (remind-hint.sh) only catches known phrasings; the agent knows about the tool from
its rules and sets reminders itself. This branch is the safety net from the other side: a promise without a run is a
promise without a mechanism ("I'll remember" is a lie when nothing keeps it). A run that FAILED (rc != 0) is flagged too.
A detector, not a block. Flag: ~/.claude/remind-guard-flags/<session_id> (the finished hint text, shown by
surface-flags.sh once). Log: ~/.claude/remind-guard.log. Any error -> silent. Calibrate: --calibrate [days].
Not counted: quotes/code/`>` lines, negations ("can't set a reminder"), questions ("shall I set a reminder?"), a recap
of context ("I'll remind you that the rule applies from Monday" — retelling, not a promise).
Config: CCM_HUMAN_NAME, CCM_CLAUDE_DIR, CCM_LANG_EXTRA (contains "uk" -> Ukrainian promise phrases too)."""
import glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from ccm_conf import conf  # noqa: E402

UK = "uk" in conf("CCM_LANG_EXTRA", "")
HOME = os.path.expanduser("~")

_EN = (r"I(?:'ll| will| shall)\s+remind\s+(?:you|him|her|them|us)(?!\w)"
       r"|I(?:'ll| will)\s+(?:ping|nudge)\s+you\s+(?:at|in|on|tomorrow|later)"
       r"|(?:I(?:'ve| have|'m| am)?|we(?:'ve| have)?)\s+(?:just\s+|now\s+|already\s+)?(?:set|scheduled|created|setting|scheduling|creating)(?:\s+you|\s+myself)?\s+(?:a|an|the)\s+(?:reminder|timer)"
       r"|(?:reminder|timer)\s+(?:is\s+|has\s+been\s+|was\s+|'s\s+)?(?:now\s+)?(?:set|created|scheduled|in\s+place|queued)(?!\w)"
       r"|I(?:'ll| will)\s+(?:come|get)\s+back\s+to\s+(?:this|it|that)\s+(?:at|in|on|tomorrow|by)(?=\s)")
_UK = (r"нагадаю|нагадаємо|повернус[ья] до (?:цього|нього|неї|них) (?:о|об|через|завтра|в|у)(?=\s)"
       r"|нагадування (?:поставив|поставила|поставлено|поставлене|стоїть|встановлено|заведено)"
       r"|(?:поставив|поставила|ставлю|заводжу|завів) (?:собі )?нагадування")
PROMISE = re.compile(r"(?<!\w)(?:" + _EN + (("|" + _UK) if UK else "") + r")(?!\w)", re.I)
# a promise that is only a retelling: "I'll remind you: ..." / "I'll remind you that ..." ("нагадаю: …", "нагадаю, що …")
RETELL = re.compile(r"\s*(?::|,?\s*(?:again\s+)?that\b|,?\s*(?:the\s+)?rule\b" + (r"|,?\s*що\b|контекст|правило" if UK else "") + r")", re.I)
RETELL_START = re.compile(r"^(?:I(?:'ll| will| shall)\s+remind\s+(?:you|him|her|them|us)" + ("|нагадаю|нагадаємо" if UK else "") + r")$", re.I)
NEG = re.compile(r"(?:\bnot|n't|\bnever|\bno|\bwithout|\bnor" + ("|\\bне|без" if UK else "") + r")\s+(?:\w+\s+){0,3}$", re.I)
RUN = re.compile(r"(?:^|[;&|\n(]\s*|\bpython3?\s+)(?:\S*/)?remind\.py\s+(?!--)\S", re.M)
QUOTES = (r"```.*?```", r"`[^`\n]*`", r"\"[^\"\n]*\"", r"“[^”\n]*”", r"«[^»\n]*»")


def clean(text):
    """strip code, `>` quote lines and quoted spans — what the agent merely cites doesn't count"""
    text = re.sub(QUOTES[0], "", text, flags=re.S)
    if "```" in text:
        text = text[:text.index("```")]
    text = text.replace("**", "")
    text = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith(">"))
    for q in QUOTES[1:]:
        text = re.sub(q, "", text)
    return text


def verdict(turn):
    """-> reason or None. turn = {"text": all assistant text of the turn, "bash": [(idx, command, ok)]}"""
    t = clean(turn.get("text") or "")
    for m in PROMISE.finditer(t):
        if NEG.search(t[max(0, m.start() - 30):m.start()]):
            continue
        if RETELL_START.match(m.group(0)) and RETELL.match(t[m.end():m.end() + 14]):
            continue
        if "?" in t[m.end():m.end() + 80].split("\n")[0].split(".")[0]:
            continue
        break
    else:
        return None
    runs = [b for b in turn.get("bash") or [] if RUN.search(str(b[1]))]     # a set-up run, not a cat/grep of the script
    if any(len(b) < 3 or b[2] for b in runs):
        return None
    return f"\"{m.group(0)}\" — but remind.py {'failed' if runs else 'was not run'} in that turn"


def is_prompt(o):
    """a human message that opens a turn (not a tool result, not a service row)"""
    if o.get("type") != "user" or o.get("isMeta") or o.get("isCompactSummary"):
        return False
    c = (o.get("message") or {}).get("content")
    if isinstance(c, str):
        return bool(c.strip())
    return isinstance(c, list) and bool(c) and not any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c)


def build_turn(rows):
    """rows: JSON lines of ONE turn (from the prompt on) -> {"text": all assistant text, "bash": [(idx, cmd, ok)]}.
    ALL text blocks count: a promise said before tool calls was seen by the human too."""
    text, bash, ids = [], [], {}
    for line in rows:
        if '"assistant"' not in line and '"tool_result"' not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        c = (o.get("message") or {}).get("content")
        if not isinstance(c, list):
            continue
        for x in c:
            if not isinstance(x, dict):
                continue
            if o.get("type") == "assistant":
                if x.get("type") == "text":
                    text.append(x.get("text") or "")
                elif x.get("type") == "tool_use" and x.get("name") == "Bash":
                    ids[x.get("id")] = len(bash)
                    bash.append([len(bash), (x.get("input") or {}).get("command") or "", True])   # no result yet = assume ok
            elif x.get("type") == "tool_result" and x.get("tool_use_id") in ids:
                bash[ids[x["tool_use_id"]]][2] = not x.get("is_error")
    return {"text": "\n\n".join(text), "bash": [tuple(b) for b in bash]}


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    d = json.loads(raw)
    sid = d.get("session_id") or "x"
    from transcript_tail import lines
    rows = lines(d.get("transcript_path") or "", is_prompt)
    if not rows:
        return
    v = verdict(build_turn(rows))
    if not v:
        return
    ident = ""
    try:
        ident = os.path.basename(open(f"{HOME}/.claude/agent-identity/{sid}").read().strip().rstrip("/"))
    except OSError:
        pass
    ident = ident or "<your-agent-name>"
    tool = os.path.join(conf("CCM_CLAUDE_DIR", ""), "scripts", "remind.py")
    who = conf("CCM_HUMAN_NAME", "the user")
    os.makedirs(f"{HOME}/.claude/remind-guard-flags", exist_ok=True)
    with open(f"{HOME}/.claude/remind-guard-flags/{sid}", "w", encoding="utf-8") as f:
        f.write(f"⏰ [remind-guard] Last turn: {v[:200]}. A promise without a mechanism. Set it NOW: `{tool} {ident} <when> "
                f"\"<what, with context>\"` (15m · 2h · 3d · 18:30 · a date) and tell {who} the time the command printed. "
                "If no reminder is needed, say so plainly.")
    with open(f"{HOME}/.claude/remind-guard.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%F %T')} [{sid[:8]}] {v}\n")


def calibrate(days):
    cut = time.time() - days * 86400
    n, hits = 0, []
    for tp in glob.glob(f"{HOME}/.claude/projects/*/*.jsonl"):
        if os.path.getmtime(tp) < cut:
            continue
        cur = []
        for line in open(tp, encoding="utf-8", errors="replace"):
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if is_prompt(o):
                if cur:
                    n += 1
                    v = verdict(build_turn(cur))
                    if v:
                        hits.append((os.path.basename(tp)[:8], v))
                cur = []
            cur.append(line)
    print(f"turns {n}, hits {len(hits)} ({100 * len(hits) / max(n, 1):.2f}%), sessions {len({h[0] for h in hits})}")
    for h in hits[:25]:
        print(" ", h[0], h[1])


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
            calibrate(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
        else:
            main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
