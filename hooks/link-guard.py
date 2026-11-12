#!/usr/bin/env python3
"""link-guard — Stop detector of file paths that are not clickable links.

The harness doesn't let a hook rewrite the reply before it is shown (Stop fires after), and a block would produce a
second, duplicate reply. So: after the turn this detector looks for paths to EXISTING files written NOT as a link →
log + flag → surface-flags.sh shows it to the agent on the next prompt, with the ready-made link to copy.

Not clickable = a path in `backticks` or a bare absolute path in the text, if such a file really exists on disk.
Not counted: the contents of ```code blocks```, anything inside [name](path), backticks containing a space (that is a
command, not a path). Only FILES (folders, /dev/null, system binaries were noise in calibration).
A BARE file name with an extension in backticks (`ROADMAP.md`, `deploy.sh`) is looked up by file name in the
workspace (CCM_WORKSPACE; without .git/node_modules/.venv/__pycache__), <CCM_CLAUDE_DIR>/scripts and
<CCM_CLAUDE_DIR>/bin; if found, the flag carries the READY link [name](path) — the agent copies it instead of
thinking. Several matches → up to 3 variants. No block (it would make a duplicate reply).
Link format (clickable in the VS Code extension): [name](path from the workspace root), outside the workspace —
[name](/absolute/path), a line — #L12 / #L12-L20.
Log ~/.claude/link-hits.log, flag ~/.claude/link-guard-flags/<sid>."""
import json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

ROOT = os.environ.get("LINK_ROOT") or conf("CCM_WORKSPACE")
CLAUDE_DIR = conf("CCM_CLAUDE_DIR")
FENCE = re.compile(r"```.*?```", re.S)
MDLINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
TICK = re.compile(r"`([^`\n]+)`")
BARE = re.compile(r"(?<![\w/.`(\[])(/(?:home|root|etc|var|usr|opt|tmp)/[^\s`'\"<>()\[\],;«»]+)")
LINE_SUFFIX = re.compile(r"(:\d+(?:-\d+)?)$")
BARE_NAME = re.compile(r"^[\w][\w.+-]*\.(?:py|sh|md|json|jsonl|html|txt|log|service|js|css)$")
EXTRA_DIRS = (os.path.join(CLAUDE_DIR, "scripts"), os.path.join(CLAUDE_DIR, "bin"))
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".Trash"}
_INDEX = None


def by_name(name):
    """Paths of files with this name (the index is built once per run)."""
    global _INDEX
    if _INDEX is None:
        _INDEX = {}
        for top in (ROOT,) + EXTRA_DIRS:
            for dp, dns, fns in os.walk(top):
                dns[:] = [d for d in dns if d not in SKIP_DIRS]
                for f in fns:
                    _INDEX.setdefault(f, []).append(os.path.join(dp, f))
    return _INDEX.get(name, [])


def link(text):
    """A ready link from what the agent wrote in backticks / bare: inside the workspace — from its root, outside —
    absolute; "file:12" / "file:12-20" → #L12 / #L12-L20 (VS Code format)."""
    m = LINE_SUFFIX.search(text)
    path = LINE_SUFFIX.sub("", text)
    full = path if path.startswith("/") else os.path.join(ROOT, path)
    anchor = ""
    if m:
        a, _, b = m.group(1)[1:].partition("-")
        anchor = f"#L{a}" + (f"-L{b}" if b else "")
    rel = os.path.relpath(full, ROOT)
    target = rel if not rel.startswith("..") else full
    return f"[{os.path.basename(path)}{m.group(1) if m else ''}]({target}{anchor})"


def is_prompt(o):
    c = (o.get("message") or {}).get("content")
    return o.get("type") == "user" and not o.get("isMeta") and (isinstance(c, str) or (isinstance(c, list) and any(
        isinstance(x, dict) and x.get("type") == "text" for x in c)))


def tail_lines(tp):
    """Lines from the last human prompt to the end, reading the file backwards in growing blocks."""
    try:
        size = os.path.getsize(tp)
        f = open(tp, "rb")
    except OSError:
        return []
    with f:
        win = 2 * 1024 * 1024
        while True:
            start = max(0, size - win)
            f.seek(start)
            parts = f.read().split(b"\n")
            if start > 0:
                parts = parts[1:]
            lines = [p.decode("utf-8", "replace") for p in parts if p.strip()]
            for i in range(len(lines) - 1, -1, -1):
                if '"user"' not in lines[i] or '"tool_result"' in lines[i]:
                    continue
                try:
                    if is_prompt(json.loads(lines[i])):
                        return lines[i:]
                except ValueError:
                    continue
            if start == 0:
                return lines
            win *= 4


def last_turn_text(tp):
    """The assistant's text after the last real human message (the whole turn, not just the last block)."""
    texts = []
    for line in tail_lines(tp):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        c = (o.get("message") or {}).get("content")
        if o.get("type") == "user" and not o.get("isMeta"):
            if is_prompt(o):
                texts = []
        elif o.get("type") == "assistant" and isinstance(c, list):
            texts += [x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text"]
    return "\n".join(texts)


def exists(p):
    p = LINE_SUFFIX.sub("", p.strip().rstrip(".:"))
    if not p or len(p) > 400:
        return None
    cand = p if p.startswith("/") else os.path.join(ROOT, p)
    if os.path.isfile(cand) and not cand.startswith(("/dev/", "/proc/", "/sys/", "/usr/bin/", "/bin/", "/sbin/", "/usr/sbin/")):
        return p
    return None


def verdict(text):
    t = FENCE.sub(" ", text)
    t = MDLINK.sub(" ", t)
    bad = []
    for m in TICK.finditer(t):
        s = m.group(1)
        if " " in s or ("/" not in s and "." not in s):   # a command or a plain word
            continue
        if re.match(r"^[a-z]+://", s):
            continue
        p = exists(s)
        if p:
            bad.append(link(s))
        elif BARE_NAME.match(LINE_SUFFIX.sub("", s)):
            hits = sorted(by_name(LINE_SUFFIX.sub("", s)), key=len)
            suf = (LINE_SUFFIX.search(s) or [""])[0] if LINE_SUFFIX.search(s) else ""
            if len(hits) == 1:
                bad.append(link(hits[0] + suf))
            elif hits:
                bad.append(f"`{s}` — {len(hits)} matches: " + " / ".join(link(h + suf) for h in hits[:3]))
    t2 = TICK.sub(" ", t)
    for m in BARE.finditer(t2):
        p = exists(m.group(1))
        if p:
            bad.append(link(p))
    return list(dict.fromkeys(bad))


def main():
    d = json.load(sys.stdin)
    if d.get("stop_hook_active"):
        return
    sid = d.get("session_id") or ""
    if not sid or "/" in sid:
        return
    bad = verdict(last_turn_text(d.get("transcript_path", "")))
    if not bad:
        return
    home = os.path.expanduser("~")
    os.makedirs(f"{home}/.claude/link-guard-flags", exist_ok=True)
    with open(f"{home}/.claude/link-hits.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%F %T')} [{sid[:8]}] {len(bad)}: {' | '.join(bad[:5])}\n")
    body = "\n".join("   " + b for b in bad[:5])
    open(f"{home}/.claude/link-guard-flags/{sid}", "w", encoding="utf-8").write(
        "🔗 [link-guard] Last turn a file was NOT written as a link (backticks don't click). "
        "Ready links — copy these, where there are several variants pick yours:\n" + body +
        "\n   Rule: [name](path from the workspace root), outside the workspace — [name](/absolute/path), a line — #L12.")


if __name__ == "__main__":
    main()
