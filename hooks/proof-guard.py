#!/usr/bin/env python3
"""proof-guard — "done" without proof.

Stop hook. If the final reply of a turn claims completion ("done", "works",
"fixed", "verified", "shipped"…), the turn edited code, and yet NO Bash call in
that turn succeeded → log it and drop a flag file, so the next turn can be told
"you declared done without running anything". A detector, not a block.

Why: "done / works / proven" backed by a cheap signal instead of a run was the
single most repeated mistake class in the swarm this came from (20+ cases across
8+ agents). The written rule "done means with the output of a run" didn't hold.

A turn = everything after the last human prompt. Not counted: text in code
blocks, inline code, quotes and `>` lines, negated claims ("not done yet"), and
turns that only edited prose (.md/.txt — there, "done" IS the result) or edited
nothing at all (pure conversation).

Calibrate against your own transcripts before trusting it:
  proof-guard.py --calibrate [days]
(The original — same logic, different language's keywords — calibrated to 3 hits
in 3,915 turns over 30 days, after the prose/no-edit exclusions. Re-measure yours.)
"""
import glob, json, os, re, sys, time

CLAIM = re.compile(r"(?<![\w-])(done|works|working now|fixed|verified|proven|shipped|all green)(?![\w-])", re.I)
NEGATION = re.compile(r"\b(not|isn't|isnt|aren't|no longer|never|nothing|hasn't|haven't|wasn't|until)\b[^.!?\n]{0,25}$", re.I)
EDITS = ("Edit", "Write", "NotebookEdit")
PROSE = (".md", ".txt")


def clean(text):
    """Drop what shouldn't count: fenced code, inline code, quotes, blockquote lines."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"[\"“«][^\"”»\n]*[\"”»]", " ", text)
    return "\n".join(l for l in text.split("\n") if not l.lstrip().startswith(">"))


def first_hit(p):
    for m in CLAIM.finditer(p):
        if not NEGATION.search(p[:m.start()]):
            return m.group(1)
    return None


def is_prompt(o):
    if o.get("type") != "user" or o.get("isMeta"):
        return False
    c = (o.get("message") or {}).get("content")
    if isinstance(c, str):
        return bool(c.strip())
    if isinstance(c, list):
        return not any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c)
    return False


def turns(tp):
    """→ list of turns: (last assistant text, bash_ok, bash_total, code_edits)"""
    out, text, bash_ids, ok, total, edits = [], "", set(), 0, 0, 0

    def flush():
        if text:
            out.append((text, ok, total, edits))
    try:
        f = open(tp, encoding="utf-8", errors="replace")
    except OSError:
        return out
    with f:
        for line in f:
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if is_prompt(o):
                flush()
                text, bash_ids, ok, total, edits = "", set(), 0, 0, 0
                continue
            c = (o.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for x in c:
                if not isinstance(x, dict):
                    continue
                if o.get("type") == "assistant":
                    if x.get("type") == "text":
                        text = x["text"]
                    elif x.get("type") == "tool_use" and x.get("name") == "Bash":
                        bash_ids.add(x.get("id"))
                    elif x.get("type") == "tool_use" and x.get("name") in EDITS:
                        fp = ((x.get("input") or {}).get("file_path") or "").lower()
                        if not fp.endswith(PROSE):
                            edits += 1
                elif x.get("type") == "tool_result" and x.get("tool_use_id") in bash_ids:
                    total += 1
                    ok += 0 if x.get("is_error") else 1
    flush()
    return out


def verdict(text, ok, edits):
    """A claim in the first or last paragraph + code was edited + no successful run."""
    if ok or not edits:
        return None
    paras = [p for p in re.split(r"\n\s*\n", clean(text).strip()) if p.strip()]
    for p in paras[:1] + paras[-1:]:
        h = first_hit(p)
        if h:
            return h
    return None


def main():
    d = json.load(sys.stdin)
    if d.get("stop_hook_active"):
        return
    sid = d.get("session_id") or "unknown-" + time.strftime("%m%d-%H%M")
    ts = turns(d.get("transcript_path", ""))
    if not ts:
        return
    text, ok, total, edits = ts[-1]
    hit = verdict(text, ok, edits)
    if not hit:
        return
    home = os.path.expanduser("~")
    os.makedirs(f"{home}/.claude/proof-flags", exist_ok=True)
    with open(f"{home}/.claude/proof-hits.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%F %T')} [{sid[:8]}] '{hit}' code_edits={edits}, bash ok={ok}/{total}\n")
    open(f"{home}/.claude/proof-flags/{sid}", "w").write(hit)


def calibrate(days):
    cutoff, n, hits = time.time() - days * 86400, 0, 0
    for tp in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        if os.path.getmtime(tp) < cutoff:
            continue
        for text, ok, total, edits in turns(tp):
            n += 1
            h = verdict(text, ok, edits)
            if h:
                hits += 1
                print(f"HIT [{os.path.basename(tp)[:8]}] '{h}' edits={edits} ok={ok}/{total} :: "
                      + clean(text)[-200:].replace("\n", " "))
    print(f"— turns: {n}, hits: {hits}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        calibrate(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
        sys.exit(0)
    try:
        main()
    except Exception:
        # trace to stderr + rc=1 → stop-dispatch.sh logs it; the reply is never blocked
        import traceback; traceback.print_exc(); sys.exit(1)
