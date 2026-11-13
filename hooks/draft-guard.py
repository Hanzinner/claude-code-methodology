#!/usr/bin/env python3
"""draft-guard — Stop branch: the reply contains an English draft of a message written in the human's name, with
signs of filler → a flag; on the next prompt surface-flags.sh tells the agent to go through the draft against the
human's drafting-style guide (CCM_DRAFTING_GUIDE; empty = a generic hint without the file).

Why: agents drafting messages for a human tend to produce filler — staccato sentences, boilerplate, a question
nobody can answer — and the human then edits the same paragraph six times. Calibrated on 30 days (33,896 text blocks):
418 drafts. Chosen variant (signs a+b+c+d):
  (a) >= 3 short sentences (<= 7 words) in a row;  (b) >= 2 stamps (attached, let me know, please see, double-checked,
  verified, just wanted to);  (c) a question mark;  (d) the same NUMBER twice (names don't count — a tenant name
  repeats naturally in a closing note, that was 38% of the drafts).
A draft = a blockquote (>) or a ``` code block with English text of >= 2 sentences that is not code/log.
Agents listed in CCM_DRAFT_GUARD_SKIP (comma-separated; e.g. an agent whose quotes are prompts for an image
generator, not letters) are ignored. Once per draft (crc32 of its text). A hint, not a block.
Log ~/.claude/draft-guard.log, flag ~/.claude/draft-guard-flags/<sid>. Fail-open under hook-safe.sh."""
import json, os, re, sys, time, zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

HOME = os.path.expanduser("~")
SKIP_AGENTS = {a.strip() for a in (os.environ.get("CCM_DRAFT_GUARD_SKIP") or conf("CCM_DRAFT_GUARD_SKIP", "") or "").split(",") if a.strip()}
CYR = re.compile(r"[а-яіїєґА-ЯІЇЄҐ]")
CODEISH = re.compile(r"[{};=<>|$\\]|^\s*(let|where|def|import|curl|git|sudo|SELECT|\|)|\b\w+\(\)|https?://|^\d{4}-\d\d-\d\d", re.M)
STAMP = re.compile(r"\b(attached|let me know|please see|double-checked|verified|just wanted to)\b", re.I)


def drafts(text):
    out = [m.group(1) for m in re.finditer(r"```[a-z]*\n(.*?)```", text, re.S)]
    cur = []
    for l in text.split("\n"):
        if l.lstrip().startswith(">"):
            cur.append(l.lstrip()[1:].strip())
        elif cur:
            out.append("\n".join(cur))
            cur = []
    if cur:
        out.append("\n".join(cur))
    res = []
    for d in out:
        d = d.strip()
        if len(d) < 40 or len(CYR.findall(d)) > 0.1 * len(d) or len(CODEISH.findall(d)) >= 2:
            continue
        sents = [s for s in re.split(r"(?<=[.!?])\s+|\n+", d) if len(s.split()) >= 2]
        if len(sents) >= 2 and sum(c.isalpha() for c in d) > 0.6 * len(d):
            res.append((d, sents))
    return res


def signs(d, sents):
    s, run, best = [], 0, 0
    for x in sents:
        run = run + 1 if len(x.split()) <= 7 else 0
        best = max(best, run)
    if best >= 3:
        s.append(f"{best} short sentences in a row")
    st = STAMP.findall(d)
    if len(st) >= 2:
        s.append("stamps: " + ", ".join(sorted({x.lower() for x in st})))
    if "?" in d:
        s.append("contains a question")
    nums = re.findall(r"(?<![\w.])\d[\d,.]*\d(?![\w.])|(?<![\w.])\d(?![\w.])", d)
    rep = sorted({n for n in nums if nums.count(n) >= 2 and len(n) >= 2})
    if rep:
        s.append("a number twice: " + ", ".join(rep[:3]))
    return s


def agent_of(sid):
    try:
        return os.path.basename(open(f"{HOME}/.claude/agent-identity/{sid}").read().strip().rstrip("/"))
    except OSError:
        return ""


def is_prompt(o):
    if o.get("type") != "user" or o.get("isMeta"):
        return False
    c = (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content")
    if isinstance(c, str):
        return bool(c.strip())
    return isinstance(c, list) and not any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c)


def last_reply(tp):
    """The turn's final assistant text block (the last turn that has any) — reads only the tail of the file."""
    try:
        size = os.path.getsize(tp)
        f = open(tp, "rb")
    except OSError:
        return ""
    with f:
        win = 2 * 1024 * 1024
        while True:
            start = max(0, size - win)
            f.seek(start)
            parts = f.read().split(b"\n")
            if start > 0:
                parts = parts[1:]
            rows = []
            for p in parts:
                try:
                    rows.append(json.loads(p))
                except ValueError:
                    continue
            idx = [i for i, o in enumerate(rows) if is_prompt(o)]
            if idx or start == 0:
                text = ""
                for o in rows[idx[-1] + 1 if idx else 0:]:
                    c = (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content")
                    if o.get("type") == "assistant" and isinstance(c, list):
                        for x in c:
                            if isinstance(x, dict) and x.get("type") == "text":
                                text = x.get("text") or ""
                return text
            win *= 4


def hint(msg):
    guide = conf("CCM_DRAFTING_GUIDE", "")
    name = conf("CCM_HUMAN_NAME", "the user")
    base = (f"✍️ [draft-guard] Last turn you wrote a draft for {name} to send, with signs of filler — {msg}. "
            f"Before {name} sends it, go through the draft sentence by sentence: what does the reader DO with each one "
            "(nothing — cut it); for a question — what will you do with the answer and who can answer it. ")
    if guide:
        base += f"Use the gate at the top of {guide}. "
    return base + "Give the corrected version, no explanations."


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    d = json.loads(raw)
    sid = d.get("session_id") or "x"
    if agent_of(sid) in SKIP_AGENTS:
        return
    found = []
    for dr, sents in drafts(last_reply(d.get("transcript_path") or "")):
        sg = signs(dr, sents)
        if sg:
            found.append((dr, sg))
    if not found:
        return
    st = f"{HOME}/.claude/draft-guard"
    os.makedirs(st, exist_ok=True)
    seen_p = f"{st}/{sid}"
    try:
        seen = set(open(seen_p).read().split())
    except OSError:
        seen = set()
    new = [(dr, sg) for dr, sg in found if f"{zlib.crc32(dr.encode()):08x}" not in seen]
    if not new:
        return
    with open(seen_p, "a") as f:
        for dr, _ in new:
            f.write(f"{zlib.crc32(dr.encode()):08x}\n")
    dr, sg = new[0]
    msg = f"draft \"{' '.join(dr.split())[:70]}…\": {'; '.join(sg)}"
    os.makedirs(f"{HOME}/.claude/draft-guard-flags", exist_ok=True)
    open(f"{HOME}/.claude/draft-guard-flags/{sid}", "w", encoding="utf-8").write(hint(msg))
    with open(f"{HOME}/.claude/draft-guard.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%F %T')} [{sid[:8]}] {agent_of(sid) or '?'}: {msg}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
