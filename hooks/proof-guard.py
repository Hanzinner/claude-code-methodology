#!/usr/bin/env python3
"""proof-guard — "done" without proof.

Why: "done / works / fixed" backed by a cheap signal instead of a run was the most repeated mistake class in the
swarm this came from (20+ cases across 8+ agents). The written rule "done means with the output of a run" didn't
hold. v1 of this hook only looked for "no successful Bash in the turn" and was almost blind: 0 live hits in 5 days
while the journal kept gaining entries of that class. v2 (this one) looks at ORDER: what ran AFTER the last code edit.

A turn = everything after the last human prompt. It fires when ALL of these hold:
  1. the turn edited CODE (an extension from CODE_EXT, or anything under the installed hooks/scripts or settings.json),
     more than 3 changed lines in total — via Edit/Write, or via Bash that plainly writes a file (sed -i, tee,
     > / >> redirection, a Python heredoc with open(p, 'w'));
  2. the final text claims completion (CLAIM) in its first or last paragraph. Code blocks, quotes and `>` lines don't
     count, and neither do negated claims ("not done yet") — the same clean()/first_hit() as pause-guard;
  3. AFTER the LAST code edit nothing ran. A run = ANY Bash segment that is not just reading or syntax checking
     (lenient on purpose: it catches "zero runs", it doesn't judge test quality), or a subagent (Task/Agent) whose
     task mentions a test or the edited file. Not a run: bash -n, py_compile, ast.parse, node --check, chmod, ls,
     cat, grep, sed -n, head, tail, wc, cp, mv, diff, stat, echo, find, git diff/status/log/show, jq, sleep.
  Not fired when the last paragraph hands the check to the human ("check it on the hardware", "open the page") —
  hardware, visuals and portals are things the agent can't verify; saying so plainly is the legitimate path.

Shared documents (rules every agent follows: the coding standard, the methodology docs, CLAUDE.md) are critical
changes too: an edit of SHARED_DOCS (>3 lines) or of the briefings of >= 3 different agents + a claim + no successful
cross-review.sh run AFTER the last such edit → reason "docs". Catalogs and journals (LIBRARY, MISTAKES) are records,
not rules — not counted.

Code → BLOCK: the reply doesn't end until the agent runs what it changed, or says plainly what is left unverified and
who will verify it. One block per stop (stop_hook_active → no loop). In the original setup this was a detector first;
the block was switched on after a week of calibration showed 3 hits in 423 turns with code edits, all real.
Docs → no block: a log line + a flag (~/.claude/proof-guard-flags/<session_id>), surfaced on the next prompt.
Switch: PROOF_GUARD_BLOCK=0 (env or methodology.conf) → code hits are flagged like docs, never blocked.
Calibrate on your own transcripts first: `proof-guard.py --calibrate [days] [--samples N]`.

Config: PROOF_GUARD_BLOCK (default 1), CCM_SHARED_DOCS (comma-separated; default: the coding standard, DEV-METHODOLOGY,
PROJECT-WORK and PO-INTERFACE in the workspace, plus ~/.claude/CLAUDE.md), CCM_WORKSPACE (relative Bash paths are
resolved against it), CCM_AGENTS_DIR (briefings), CCM_HUMAN_NAME, CCM_LANG_EXTRA (contains "uk" → Ukrainian too).
"""
import glob, importlib.util, json, os, re, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
INSTALL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(INSTALL, "lib"))
sys.path.insert(0, os.path.join(INSTALL, "scripts"))
from ccm_conf import conf  # noqa: E402

_s = importlib.util.spec_from_file_location("pause_guard", os.path.join(HERE, "pause-guard.py"))
_pg = importlib.util.module_from_spec(_s); _s.loader.exec_module(_pg)
clean, first_hit = _pg.clean, _pg.first_hit   # one logic for "what doesn't count" + negation

UK = "uk" in conf("CCM_LANG_EXTRA", "")
HUMAN = conf("CCM_HUMAN_NAME", "the user")


def _join(*parts):
    return "|".join(f"(?:{p})" for p in parts if p)


# "works / passes" only as a claim about the result ("now works", "all green"), not a description ("the mode that works")
CLAIM_EN = (r"done|fixed|verified|proven|shipped|all green|it works|now works|works now|working now"
            r"|(?:now|all|everything)\s+(?:works|passes|green)")
CLAIM_UK = (r"готово|доведено|зелене світло|доїхал[оаи]|полагоджено|полагодив|полагодила|виправлено|виправив|зроблено"
            r"|(?:тепер|вже|все|усе|знову)\s+(?:працює|проходить|зелен\w*)")
CLAIM = re.compile(r"(?<![\w-])(" + _join(CLAIM_EN, CLAIM_UK if UK else "") + r")(?![\w-])", re.I)
# The check handed to the human (hardware, visuals, a portal: the agent can't verify those — the human gives the proof)
HANDOFF_EN = (r"(?<!\w)(?:run|try|check|open|click|test|look at)(?!\w)[^.?!\n]{0,80}"
              r"(?:yourself|on your|on the|in the|page|device|hardware|phone|browser|portal)"
              r"|on the hardware|in the portal|on your (?:machine|phone|device)")
HANDOFF_UK = (r"(?<!\w)(?:прожени|запусти|перевір|покрути|глянь|клацни|відкрий)(?!\w)[^.?!\n]{0,80}"
              r"|на залізі|у порталі|в порталі")
HANDOFF = re.compile(_join(HANDOFF_EN, HANDOFF_UK if UK else ""), re.I)
EDITS = ("Edit", "Write", "NotebookEdit", "MultiEdit")
# data/state (.json .yaml .toml) is not code: those were false hits on state files; settings.json stays via CRITICAL
CODE_EXT = (".py", ".sh", ".bash", ".js", ".ts", ".tsx", ".jsx", ".rs", ".html", ".htm", ".css", ".kql", ".ps1",
            ".service", ".timer", ".go", ".c", ".h")
CLAUDE_DIR = conf("CCM_CLAUDE_DIR", INSTALL).rstrip("/")
CRITICAL = tuple(sorted({f"{CLAUDE_DIR}/hooks/", f"{CLAUDE_DIR}/scripts/", f"{CLAUDE_DIR}/settings.json",
                         os.path.expanduser("~/.claude/hooks/"), os.path.expanduser("~/.claude/scripts/"),
                         os.path.expanduser("~/.claude/settings.json")}))
WORKSPACE = conf("CCM_WORKSPACE", os.path.expanduser("~/claude-projects")).rstrip("/")
AGENTS = (conf("CCM_AGENTS_DIR", "") or os.path.join(WORKSPACE, "Agents")).rstrip("/")


def _shared_docs():
    v = conf("CCM_SHARED_DOCS", "")
    if v:
        return tuple(os.path.expanduser(p.strip()) for p in v.split(",") if p.strip())
    std = conf("CCM_CODING_STANDARD", "") or os.path.join(WORKSPACE, "CODING-STANDARD.md")
    return (std, *(os.path.join(WORKSPACE, n) for n in ("DEV-METHODOLOGY.md", "PROJECT-WORK.md", "PO-INTERFACE.md")),
            os.path.expanduser("~/.claude/CLAUDE.md"))


SHARED_DOCS = _shared_docs()
BRIEF = re.compile(re.escape(AGENTS) + r"/(.+)/briefing\.md$")
BRIEFS_MASS = 3
# quotes optional: segments() (shlex) strips them; the interpreter may live in a venv (.venv/bin/python)
NOT_RUN = re.compile(r"^\s*(bash\s+-n|(?:\S*/)?python3?\s+-m\s+py_compile|(?:\S*/)?python3?\s+-c\s+['\"]?import\s+ast\b|node\s+--check|"
                     r"chmod|sleep|mkdir|touch|true|ls|cat|grep|command grep|rg|sed\s+-n|head|tail|wc|cp|mv|diff|stat|echo|printf|cd|find|jq|sort|uniq|cut|tr|"
                     r"git\s+(?:-C\s+\S+\s+)?(?:diff|status|log|show|ls-files|rev-parse|branch)|awk\s+'[^']*'\s+\S+$)\b")


def is_prompt(o):
    if o.get("type") != "user" or o.get("isMeta"):
        return False
    c = (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content")
    if isinstance(c, str):
        return bool(c.strip()) and not c.lstrip().startswith("<task-notification>")
    if isinstance(c, list):
        return not any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c)
    return False


def lines_changed(inp):
    if "content" in inp and "old_string" not in inp:           # Write
        return (inp.get("content") or "").count("\n") + 1
    old, new = inp.get("old_string") or "", inp.get("new_string") or ""
    return max(old.count("\n"), new.count("\n")) + 1


def is_doc(fp):
    return fp in SHARED_DOCS or bool(BRIEF.search(fp))


def is_code(fp):
    return fp.lower().endswith(CODE_EXT) or fp.startswith(CRITICAL)


PATH_TOK = re.compile(r"[\w./~+-]+\.(?:py|sh|js|ts|rs|html|css|kql|md)")
REDIR = re.compile(r"(?:^|\s)(?:\d|&)?>>?\s*([^\s;|&]+)")


def norm(fp):
    """A relative path → from the workspace root (where sessions usually start)."""
    fp = fp.strip("'\"")
    if fp.startswith("~"):
        return os.path.expanduser(fp)
    return fp if fp.startswith("/") else os.path.normpath(os.path.join(WORKSPACE, fp))


HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1([^\n]*)\n(.*?)^\s*\2\s*$", re.S | re.M)


def segments(cmd):
    """The commands in a Bash line, respecting quotes (splitting on `|` tore `grep "a|b"` apart → a false "run")."""
    import shlex
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|\n")
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        return [s for s in re.split(r"&&|;|\|\|?|\n", cmd) if s.strip()]
    segs, cur = [], []
    for tk in toks:
        if tk and set(tk) <= set(";&|\n"):
            if cur:
                segs.append(" ".join(cur)); cur = []
        else:
            cur.append(tk)
    if cur:
        segs.append(" ".join(cur))
    return segs


def cmd_segments(cmd):
    """→ (segments, heredoc bodies). For write/run POSITIONS: a heredoc body is not commands (its `print(...)` is not a
    run) — it becomes a "<<HEREDOC<n>" marker on the command line; split by lines (shlex glued lines, and a `#` ate
    the following ones)."""
    bodies = []

    def mark(m):
        bodies.append(m.group(4))
        return f"<<HEREDOC{len(bodies) - 1}{m.group(3)}\n"
    flat, segs = HEREDOC.sub(mark, cmd), []
    for ln in flat.split("\n"):
        if ln.strip() and not ln.lstrip().startswith("#"):
            segs += segments(ln)
    return segs, bodies


def bash_writes(cmd):
    """→ [(segment no., absolute path)] of files Bash plainly WRITES: sed -i / tee (every path argument), > and >>
    (the target only), a Python heredoc p='…' + open(p,'w'|'a') (position = the command of its heredoc)."""
    (segs, bodies), out = cmd_segments(cmd), []
    for k, sg in enumerate(segs):
        toks = sg.split()
        if toks and (toks[0] == "sed" and any(t.startswith("-i") for t in toks[1:]) or toks[0] == "tee"):
            out += [(k, norm(t)) for t in toks[1:] if PATH_TOK.fullmatch(t)]
        for m in REDIR.finditer(sg):
            if PATH_TOK.fullmatch(m.group(1)):
                out.append((k, norm(m.group(1))))
    for m in re.finditer(r"(\w+)\s*=\s*['\"](\S+\.(?:py|sh|js|ts|rs|html|css|kql|md))['\"]", cmd):
        if re.search(r"open\(\s*" + re.escape(m.group(1)) + r"\b[^)]*,\s*['\"][wa]", cmd):
            hd = [i for i, b in enumerate(bodies) if m.group(2) in b]
            k = next((i for i, sg in enumerate(segs) if hd and f"HEREDOC{hd[0]}" in sg), len(segs))   # not found → at the end
            out.append((k, norm(m.group(2))))
    return out


def is_write_seg(sg):
    toks = sg.split()
    return bool(toks) and (toks[0] in ("sed", "tee") and (toks[0] == "tee" or any(t.startswith("-i") for t in toks))
                           or bool(REDIR.search(sg)) and not re.search(r">>?\s*/dev/null", sg))


def runs_after(b, last, pred):
    """Bash call b has a segment AFTER position `last` that satisfies pred."""
    for k, sg in enumerate(cmd_segments(b[1])[0]):
        if (b[0], k) > last and pred(sg):
            return True
    return False


def is_xreview(sg):
    toks = sg.split()
    # background wrappers: a review takes minutes, so it is often started as `setsid nohup … &`
    while len(toks) > 1 and (toks[0] in ("bash", "sh", "setsid", "nohup", "nice", "ionice", "timeout", "env")
                             or toks[0].startswith("-") or toks[0].isdigit() or re.fullmatch(r"\w+=\S*", toks[0])):
        toks = toks[1:]
    return bool(toks) and toks[0].endswith(("cross-review.sh", "cross_review.sh"))


def turns(tp, tail=False):
    """→ list of turns: dict(text, edits[(pos, path, lines)], bash[(seq, cmd, ok)], agents, docs)"""
    out, cur, seq, pending = [], None, 0, {}

    def new():
        return {"text": "", "edits": [], "bash": [], "agents": [], "docs": []}
    if tail:   # live mode: only the last turn (transcript_tail); calibration reads the whole file
        from transcript_tail import lines as tail_lines
        src = tail_lines(tp, is_prompt)
    else:
        try:
            src = open(tp, encoding="utf-8", errors="replace").read().split("\n")
        except OSError:
            return out
    for line in src:
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(o, dict):
            continue
        if is_prompt(o):
            if cur and cur["text"]:
                out.append(cur)
            cur = new(); pending = {}
            continue
        if cur is None:
            cur = new()
        c = (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content")
        if not isinstance(c, list):
            continue
        for x in c:
            if not isinstance(x, dict):
                continue
            seq += 1
            if o.get("type") == "assistant":
                if x.get("type") == "text":
                    cur["text"] = x.get("text") or ""
                elif x.get("type") == "tool_use" and x.get("name") in EDITS:
                    inp = x.get("input") or {}
                    fp = inp.get("file_path") or ""
                    if is_code(fp):
                        cur["edits"].append(((seq, 0), fp, lines_changed(inp)))
                    elif is_doc(fp):
                        cur["docs"].append(((seq, 0), fp, lines_changed(inp)))
                elif x.get("type") == "tool_use" and x.get("name") in ("Task", "Agent"):
                    # a run by a subagent: its task mentions a test or the edited file — counted, leniently
                    cur["agents"].append(((seq, 0), json.dumps(x.get("input") or {}, ensure_ascii=False)))
                elif x.get("type") == "tool_use" and x.get("name") == "Bash":
                    cmd = (x.get("input") or {}).get("command") or ""
                    pending[x.get("id")] = (seq, cmd)
                    # Edits via Bash — only the plain write forms (a general "path mentioned" heuristic caught
                    # paths quoted in text: 45% false). Position = (seq, segment no.): a write and a run in one call
                    # are told apart by their order. `mv X.new X` is an install, not an edit.
                    for k, fp in bash_writes(cmd):
                        if is_code(fp):
                            cur["edits"].append(((seq, k), fp, 5))
                        elif is_doc(fp):
                            cur["docs"].append(((seq, k), fp, 5))
            elif x.get("type") == "tool_result" and x.get("tool_use_id") in pending:
                s, cmd = pending.pop(x.get("tool_use_id"))
                cur["bash"].append((s, cmd, not x.get("is_error")))
    if cur and cur["text"]:
        out.append(cur)
    return out


def is_run(cmd):
    """A run = at least one segment that is NOT just reading / syntax."""
    segs = segments(cmd)
    return bool(segs) and not all(NOT_RUN.match(s.strip()) for s in segs)


def claim_of(t):
    paras = [p for p in re.split(r"\n\s*\n", clean(t["text"]).strip()) if p.strip()]
    for p in paras[:1] + paras[-1:]:
        c = first_hit(CLAIM, p)
        if c:
            return c, paras
    return None, paras


def verdict(t):
    """→ None | (claim, reason). A reason starting with "docs" = a shared document edited without a cross-review."""
    return code_verdict(t) or docs_verdict(t)


def docs_verdict(t):
    docs = t.get("docs") or []
    shared = [d for d in docs if d[1] in SHARED_DOCS and d[2] > 0]
    briefs = {BRIEF.search(d[1]).group(1) for d in docs if BRIEF.search(d[1])}
    if sum(d[2] for d in shared) <= 3 and len(briefs) < BRIEFS_MASS:
        return None
    claim, _ = claim_of(t)
    if not claim:
        return None
    # "after" = after the last CRITICAL edit: recapping one's own briefing after the review doesn't raise the flag
    crit = list(shared) + ([d for d in docs if BRIEF.search(d[1])] if len(briefs) >= BRIEFS_MASS else [])
    last = max(d[0] for d in crit)
    # a review = a SUCCESSFUL cross-review.sh run AFTER the last critical edit, not the word mentioned.
    # Coverage: EVERY edited shared doc is in some review; briefings — one review touching a briefing, or a --git diff.
    revs = [sg for b in t["bash"] if b[2] for k, sg in enumerate(cmd_segments(b[1])[0])
            if (b[0], k) > last and is_xreview(sg)]
    need = {os.path.basename(d[1]) for d in shared}
    docs_ok = all(any(n in r for r in revs) for n in need)
    briefs_ok = len(briefs) < BRIEFS_MASS or any("briefing.md" in r or "--git" in r for r in revs)
    if revs and docs_ok and briefs_ok:
        return None
    what = ", ".join(sorted({os.path.basename(d[1]) for d in shared})) or f"briefings of {len(briefs)} agents"
    return claim, f"docs: a shared rules document ({what}) edited with no cross-review after it"


def code_verdict(t):
    edits = t["edits"]
    if not edits or sum(e[2] for e in edits) <= 3:
        return None
    claim, paras = claim_of(t)
    if not claim:
        return None
    if paras and HANDOFF.search(paras[-1]):
        return None   # the check was handed to the human on purpose — legitimate
    last = max(e[0] for e in edits)
    names = {os.path.basename(e[1]) for e in edits}
    runs = [b for b in t["bash"] if runs_after(b, last, lambda sg: not NOT_RUN.match(sg.strip()) and not is_write_seg(sg))]
    runs += [a for a in t["agents"] if a[0] > last and (re.search(r"test|тест|прогін|прожени", a[1], re.I)
                                                          or any(n in a[1] for n in names))]
    if not runs:
        return claim, "nothing ran after the last code edit"
    return None


def main():
    d = json.load(sys.stdin)
    if d.get("stop_hook_active"):
        return
    sid = d.get("session_id") or "unknown-" + time.strftime("%m%d-%H%M")
    ts = turns(d.get("transcript_path", ""), tail=True)
    if not ts:
        return
    v = verdict(ts[-1])
    if not v:
        return
    claim, why = v
    home = os.path.expanduser("~")
    t = ts[-1]
    os.makedirs(f"{home}/.claude", exist_ok=True)
    with open(f"{home}/.claude/proof-hits.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%F %T')} [{sid[:8]}] '{claim}' {why}; code edits {len(t['edits'])}, bash {len(t['bash'])}\n")
    if not why.startswith("docs") and str(conf("PROOF_GUARD_BLOCK", "1")) == "1":
        files = ", ".join(sorted({os.path.basename(e[1]) for e in t["edits"]})[:4])
        print(json.dumps({"decision": "block", "reason":
              f"proof-guard: you said '{claim}' after editing code ({files}), but ran nothing AFTER the last edit. "
              "Run what you changed (its test, or the script itself) and show the output — then claim it. If you "
              f"can't be the one to run it (hardware, {HUMAN}, another agent), say so plainly: what exactly is "
              "unverified and who will verify it — and drop the word."}, ensure_ascii=False))
        return
    flags = f"{home}/.claude/proof-guard-flags"
    os.makedirs(flags, exist_ok=True)
    if why.startswith("docs"):
        msg = (f"[proof-guard] Last turn you said '{claim}' after editing a shared rules document with no "
               "cross-review after the edit. A rule every agent follows is a critical change: run "
               "scripts/cross-review.sh on the edited document now and report what it found.")
    else:
        msg = (f"[proof-guard] Last turn you said '{claim}' after editing code, but nothing ran after the last "
               f"edit. Run it now and show the output, or tell {HUMAN} what is unverified.")
    with open(f"{flags}/{sid}", "w", encoding="utf-8") as f:
        f.write(msg + "\n")


def calibrate(days, samples=0):
    import random
    cutoff, n, code_turns, hits, ex = time.time() - days * 86400, 0, 0, 0, []
    seen = set()
    for tp in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
        if os.path.getmtime(tp) < cutoff:
            continue
        for t in turns(tp):
            k = (t["text"], len(t["edits"]), tuple(b[1] for b in t["bash"][-3:]))
            if k in seen:      # the same session in several transcript files
                continue
            seen.add(k)
            n += 1
            code_turns += bool(t["edits"])
            v = verdict(t)
            if v:
                hits += 1
                ex.append((os.path.basename(tp)[:8], v[0], clean(t["text"])[-220:].replace("\n", " "),
                           [os.path.basename(e[1]) for e in t["edits"]][:4], [b[1][:70] for b in t["bash"]][-3:]))
    random.seed(7)
    for e in random.sample(ex, min(samples, len(ex))):
        print(f"HIT [{e[0]}] '{e[1]}' edits={e[3]} last bash={e[4]}\n     … {e[2]}")
    print(f"— turns: {n}, with code edits: {code_turns}, hits: {hits}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        days = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 30
        smp = int(sys.argv[sys.argv.index("--samples") + 1]) if "--samples" in sys.argv else 0
        calibrate(days, smp)
        sys.exit(0)
    try:
        main()
    except Exception:
        # trace to stderr + rc=1 → stop-dispatch.sh logs it; the reply is never blocked by a crash
        import traceback; traceback.print_exc(); sys.exit(1)
