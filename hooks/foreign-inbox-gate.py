#!/usr/bin/env python3
"""foreign-inbox-gate - PreToolUse Bash and Write|Edit: an inbox is written ONLY through inbox_post.sh / inbox_done.sh
(under a lock). Any `<agents dir>/**/inbox.md` - a foreign one AND your own.

Why: a bare read-modify-write without a lock wipes the letters that arrived in parallel (one agent lost a task for the
coordinator's other agent for 5.5 hours this way; 2 of 4 real losses were an agent closing ITS OWN inbox with a bare
Edit or a moving script), and it breaks the "## New" structure, so delivery then reports a false "not delivered".
  Edit/Write on an inbox.md under the agents dir -> deny (your own: "use inbox_done"; foreign: "use inbox_post").
  Bash that WRITES inbox.md -> deny: `>`/`>>`, `tee`, `sed -i`/`perl -i`, an interpreter heredoc (python/awk/perl/node/
  ruby) with open(...,'w'|'a') / write_text / .write( aimed at an inbox.md path. Exception: code that takes the same lock
  (`inbox.md.lock` / flock) - that is how inbox_post and inbox_done write.
  Bash `inbox_post.sh`/`inbox_done.sh` with the text in SINGLE quotes where an apostrophe inside a word ("don't",
  "l'été") closes the quote -> deny: the letter either does not go (a syntax error) or goes mangled. Use a heredoc.
Text that only MENTIONS the name (a template string, a message, a comment) is not a write: a path counts only when it
is a path-like string literal (no spaces, or starting with / ~ .), and the words of a quoted string or a heredoc body of
a non-interpreter command are never looked at.
Config: CCM_AGENTS_DIR, CCM_CLAUDE_DIR (the paths named in the deny text). Identity: ~/.claude/agent-identity/<session id>.
Fail-open under hook-safe.sh."""
import json, os, re, shlex, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

INBOX = re.compile(r"(^|/)inbox\.md$")
TOOLS = ("inbox_post.sh", "inbox_done.sh")
WRAP = {"sudo", "env", "nohup", "timeout", "nice", "ionice", "command", "exec", "xargs"}
WRITE_MARK = r"open\([^)]*['\"][wa]\+?['\"]|write_text|writeFileSync|appendFile"
# a PATH to inbox.md as a string literal: no whitespace inside, or an absolute/home/relative-dot path (may hold spaces).
# "template for inbox.md items" is text, not a path.
PATH_LIT = r"['\"](?:[^'\"\s]*|[/~.][^'\"\n]*)inbox\.md['\"]"


# ── a small shell lexer (same approach as sysfile-gate): quotes are single tokens, heredoc bodies are skipped ──
def lex(text):
    lx = shlex.shlex(text, posix=True, punctuation_chars=";&|()")
    lx.whitespace_split = True
    lx.commenters = "#"
    return list(lx)


def subst(tok, env):
    return re.sub(r"\$\{?(\w+)\}?", lambda m: env.get(m.group(1), m.group(0)), tok)


def strip_wrappers(toks):
    while toks:
        t = toks[0]
        if re.fullmatch(r"\w+=.*", t):
            toks = toks[1:]
        elif t in WRAP:
            toks = toks[1:]
            while toks and toks[0].startswith("-"):
                opt = toks[0]
                toks = toks[1:]
                if opt in ("-u", "-g", "-k", "-C", "-D") and toks:
                    toks = toks[1:]
            if t == "timeout" and toks and re.fullmatch(r"[\d.]+[smhd]?", toks[0]):
                toks = toks[1:]
        else:
            break
    return toks


def split_segments(toks, env=None):
    """command segments; VAR=value assignments are remembered and substituted (`f=.../inbox.md; echo x >> "$f"`)"""
    env = {} if env is None else env
    out, seg = [], []
    for t in toks + [";"]:
        if t and set(t) <= set(";&|()"):
            body = [x for x in seg if x not in ("export", "local", "readonly", "declare")]
            if body and all(re.fullmatch(r"\w+=.*", x) for x in body):
                for x in body:
                    k, _, v = x.partition("=")
                    env[k] = v
            else:
                out.append(strip_wrappers([subst(x, env) for x in seg]))
            seg = []
        else:
            seg.append(t)
    return out


def commands(cmd):
    """-> token lists of commands; heredoc bodies skipped; quotes may span lines"""
    kept, skip = [], None
    for line in cmd[:6000].splitlines()[:150]:
        if skip is not None:
            if line.strip() == skip:
                skip = None
            continue
        if "<<" in line:
            mk = line.split("<<")[-1].strip().lstrip("-").strip("'\"")
            if mk and mk.replace("_", "").isalnum():
                skip = mk
        kept.append(line)
    out = []
    try:
        out = split_segments(lex(" ;\n".join(kept)), {})
    except ValueError:  # unclosed quotes - fall back to line-by-line
        env = {}
        for line in kept:
            try:
                out += split_segments(lex(line), env)
            except ValueError:
                continue
    return [t for t in out if t]


# ── does a piece of interpreter code WRITE inbox.md? ──
def writes_inbox(code):
    """a write to inbox.md itself: on the same line as the path literal, or through a variable holding that path
    (a false positive once: a script READ inbox.md and wrote to box.md, and the gate cut it)"""
    # a variable = the path string itself (or Path(...)), not `t=open(path).read()` - that is content
    vars_ = set(re.findall(r"(\w+)\s*=\s*(?:Path\(\s*)?[rbfu]?" + PATH_LIT, code))
    for line in code.splitlines():
        if not re.search(WRITE_MARK, line):
            continue
        if re.search(PATH_LIT, line) and not re.search(r"inbox\.md\.lock", line):
            return True
        if any(re.search(r"\b" + re.escape(v) + r"\b", line) for v in vars_):
            return True
    return False


def bash_writes_inbox(cmd):
    """-> a description of the violation or None"""
    if "inbox.md" not in cmd:
        return None
    for toks in commands(cmd):
        head = toks[0].rsplit("/", 1)[-1]
        if head in TOOLS:
            continue
        for i, tk in enumerate(toks):
            m = re.fullmatch(r"(?:\d|&)?>>?(.*)", tk)
            if m:  # >file or > file
                target = m.group(1) or (toks[i + 1] if i + 1 < len(toks) else "")
                if INBOX.search(target.strip("'\"")):
                    return f"redirect `{tk}` into {target}"
        if head == "tee" and any(INBOX.search(a) for a in toks[1:]):
            return "tee into inbox.md"
        if head in ("sed", "perl") and any(x.startswith("-i") or x.startswith("-pi") for x in toks[1:]) \
                and any(INBOX.search(a) for a in toks[1:]):
            return f"{head} -i on inbox.md"
    # interpreter heredoc bodies (python/awk/perl/node/ruby) that write an inbox.md file
    lines, i = cmd.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", line)
        if m and re.search(r"\b(python3?|awk|perl|node|ruby)\b", line):
            end = m.group(1); body = []
            i += 1
            while i < len(lines) and lines[i].strip() != end:
                body.append(lines[i]); i += 1
            b = "\n".join(body)
            if "inbox.md" in b and not re.search(r"inbox\.md\.lock|flock", b) and writes_inbox(b):
                return "a heredoc script writes inbox.md without the lock"
        i += 1
    if re.search(r"python3?\s+-c\s", cmd) and re.search(r"open\([^)]*inbox\.md[^)]*['\"][wa]", cmd):
        return "python -c writes inbox.md"
    return None


LETTER = re.compile(r"[^\W\d_]")


def apostrophe_break(cmd):
    """inbox_post/inbox_done with the text in SINGLE quotes where an apostrophe between two letters ("don't", a
    Ukrainian "п'ять") closes the quote: an odd count -> a syntax error and no letter; an even count -> the letter
    goes mangled, the apostrophes gone (3 broadcasts in one day). Heredoc bodies are not looked at - an apostrophe is
    safe there. The proper escape `'..'"'"'..'` is fine (a quote follows the apostrophe, not a letter)."""
    if not re.search(r"inbox_(post|done)\.sh", cmd):
        return None
    out, end = [], None
    for ln in cmd.split("\n"):
        if end is not None:
            if ln.strip() == end:
                end = None
            continue
        out.append(ln)
        m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", ln)
        if m:
            end = m.group(1)
    c, state, i = "\n".join(out), None, 0
    while i < len(c):
        ch = c[i]
        if state is None:
            if ch == "\\":
                i += 2; continue
            if ch in "'\"":
                state = ch
        elif state == "'":
            if ch == "'":
                if i > 0 and LETTER.match(c[i - 1]) and i + 1 < len(c) and LETTER.match(c[i + 1]):
                    return c[max(0, i - 12):i + 12].replace("\n", " ")
                state = None
        else:
            if ch == "\\":
                i += 2; continue
            if ch == '"':
                state = None
        i += 1
    return None


def identity(sid):
    try:
        return open(os.path.expanduser(f"~/.claude/agent-identity/{sid}"), encoding="utf-8").read().strip().rstrip("/")
    except OSError:
        return ""


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}, ensure_ascii=False))


def main():
    d = json.load(sys.stdin)
    scripts = os.path.join(conf("CCM_CLAUDE_DIR"), "scripts")
    agents = os.path.normpath(conf("CCM_AGENTS_DIR")) + os.sep
    if d.get("tool_name") == "Bash":
        cmd = (d.get("tool_input") or {}).get("command") or ""
        ap = apostrophe_break(cmd[:20000])
        if ap:
            deny(f"⛔ An apostrophe closes the single quotes (\"…{ap}…\") - the letter either does not go (a syntax "
                 "error) or goes mangled. Put the text of the letter in a heredoc: "
                 f"`{scripts}/inbox_post.sh <agent> <<'EOF'` newline text newline `EOF` (apostrophes and backticks are safe there).")
            return
        why = bash_writes_inbox(cmd[:8000])
        if why:
            deny(f"⛔ inbox.md is not written from Bash ({why}) - only under the lock: write a letter -> "
                 f"`{scripts}/inbox_post.sh <agent> \"<text>\"`; close an item -> "
                 f"`{scripts}/inbox_done.sh <agent> \"<substring>\"`. A structural repair: a python script with flock on "
                 "`<inbox>.md.lock` (like inbox_post).")
        return
    if d.get("tool_name") not in ("Edit", "Write"):
        return
    fp = os.path.normpath((d.get("tool_input") or {}).get("file_path", "") or "")
    if not (fp.startswith(agents) and os.path.basename(fp) == "inbox.md"):
        return
    me = identity(d.get("session_id") or "")
    owner = os.path.basename(os.path.dirname(fp))
    if me and os.path.normpath(os.path.dirname(fp)) == os.path.normpath(me):
        # your OWN inbox too: 2 of 4 lost letters were an agent closing its own inbox with a bare Edit or a moving
        # script, bypassing the lock
        deny("⛔ Your own inbox is not edited with Edit/Write either - other agents write into it in parallel. "
             f"Close an item -> `{scripts}/inbox_done.sh {owner} \"<substring of the item>\" [\"entry for Processed\"]` "
             "(under the lock, one item at a time). Moving it into your todo -> add it to the todo first, then inbox_done.")
        return
    deny(f"⛔ A foreign inbox ({owner}) is not edited with Edit/Write - only under the lock: write a letter -> "
         f"`{scripts}/inbox_post.sh {owner} \"<text>\"`; close an item (if it really is yours) -> "
         f"`{scripts}/inbox_done.sh {owner} \"<substring>\"`. Reason: a bare Edit wipes letters that arrived in parallel.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # do not swallow silently: trace -> stderr, rc=1 -> hook-safe.sh writes hook-errors.log (fail-open)
        import traceback; traceback.print_exc(); sys.exit(1)
