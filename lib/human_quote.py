#!/usr/bin/env python3
"""human_quote.py - did the human (the person in the tab) type this fragment, word for word, in this Claude Code session?

Shared by scripts/accept.py and scripts/story_add.py. Why: "accepted" and "the human asked for it" kept being written
from the agent's word; an agent's paraphrase of a "yes" is not a "yes". These scripts write nothing unless the
fragment is found in a message the HUMAN typed, read from the session transcript ~/.claude/projects/*/<sid>.jsonl.

A message of the HUMAN is:
  - a record type=="user" whose content is a string or type=="text" blocks (a record carrying a tool_result is not);
    not isMeta / isCompactSummary / isVisibleInTranscriptOnly / isVirtual / isSidechain;
    origin.kind, if present, is "human" (a task-notification or a peer agent is not); entrypoint != "sdk-cli"
    (that is `claude -p` / `claude -p --resume` started by a script or another agent, not the human);
  - an attachment type=="queued_command" with commandMode=="prompt": what the human typed while the agent was busy
    (in the transcript it is NOT a user record); peer / isMeta ones are not.
Machine text is cut out before matching: <system-reminder>, <command-...>, <local-command-...>, <task-notification>,
<bash-stdout/stderr>, <pasted_content> and <ide_...> (pasted or selected text is not the human's own words), messages
from other sessions/agents. A message starting with "[from agent: ..." (another agent speaking through the prompt) is
dropped whole.
Matching: casefold, quote marks removed, dashes and ellipsis unified, whitespace collapsed; the normalized fragment
must be at least 8 characters (a bare "ok" or "yes" proves nothing about WHAT was accepted).

Short form (find_short_reply; "yes" / "+" / "ok" - under 8 characters): found only if
  (a) it is a WHOLE message of the human (after normalizing and cutting trailing .,!?;: - an exact match), and
  (b) the last ASSISTANT message before it in the same branch (the parentUuid chain; the text blocks of one API
      message, not thinking / tool_use) names EVERY S-code asked for; no other message of the human in between.
  Otherwise the "yes" may have answered another question. Records without parentUuid (older format): file order.

CLI for a manual check: human_quote.py "<fragment>" [--session SID]  -> rc 0 found / 2 not found / 1 error.
Transcripts dir: env CLAUDE_PROJECTS_DIR (default ~/.claude/projects). Session: --session, else $CLAUDE_CODE_SESSION_ID."""
import glob
import json
import os
import re
import sys

MIN_LEN = 8

# Machine inserts inside user records: cut together with their content (a tag with attributes too).
_TAGS = ("system-reminder", "command-[\\w-]+", "local-command-[\\w-]+", "task-notification",
         "bash-stdout", "bash-stderr", "pasted_content", "cross-session-message", "agent-message",
         "user-prompt-submit-hook", "ide_[\\w-]+")  # ide_selection / ide_opened_file: text of a file from the IDE
_CUT = re.compile(r"<(%s)\b[^>]*>.*?</\1>" % "|".join(_TAGS), re.S)
# An unclosed tag (a truncated record): cut to the end, so machine text never counts as the human's words.
_CUT_OPEN = re.compile(r"<(?:%s)\b[^>]*>.*\Z" % "|".join(_TAGS), re.S)
_INTERRUPT = re.compile(r"\[Request interrupted by user[^\]]*\]")
_QUOTES = dict.fromkeys(map(ord, "«»\"“”„‟'‘’‚‛ʼ`´"), None)
_DASHES = {ord("—"): "-", ord("–"): "-", ord("…"): "..."}


class QuoteError(Exception):
    """The check cannot be done (no session, no transcript, fragment too short) - not the same as "not found"."""


def normalize(s):
    s = s.translate(_DASHES).translate(_QUOTES).casefold()
    return re.sub(r"\s+", " ", s).strip()


def clean(text):
    """The message text without machine inserts."""
    text = _CUT.sub("", text)
    text = _CUT_OPEN.sub("", text)
    text = _INTERRUPT.sub("", text)
    return text.strip()


def _blocks_text(content):
    """str | [{type:text}] -> text; None for a tool_result or non-text content."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_result":
            return None
        if b.get("type") == "text":
            parts.append(b.get("text") or "")
    return "\n".join(parts) if parts else None


def _origin_ok(origin):
    return not isinstance(origin, dict) or origin.get("kind") in (None, "human")


def human_text(rec):
    """(text, timestamp) if the record is a message of the human, else None."""
    t = rec.get("type")
    if t == "user":
        if any(rec.get(k) for k in ("isMeta", "isCompactSummary", "isVisibleInTranscriptOnly",
                                    "isVirtual", "isSidechain")):
            return None
        if not _origin_ok(rec.get("origin")) or rec.get("entrypoint") == "sdk-cli":
            return None
        txt = _blocks_text((rec.get("message") or {}).get("content"))
        ts = rec.get("timestamp")
    elif t == "attachment":
        a = rec.get("attachment") or {}
        if a.get("type") != "queued_command" or a.get("commandMode") != "prompt":
            return None
        if a.get("isMeta") or rec.get("isMeta") or rec.get("isSidechain") or not _origin_ok(a.get("origin")):
            return None
        txt = _blocks_text(a.get("prompt"))
        ts = a.get("timestamp") or rec.get("timestamp")
    else:
        return None
    if not txt:
        return None
    txt = clean(txt)
    if not txt or txt.startswith("[from agent:"):
        return None
    return txt, ts


def transcripts(session_id, projects_dir=None):
    pd = projects_dir or os.environ.get("CLAUDE_PROJECTS_DIR") or os.path.expanduser("~/.claude/projects")
    # no glob metacharacters in the id: a session id is a uuid
    if not re.fullmatch(r"[0-9A-Za-z_-]+", session_id or ""):
        raise QuoteError(f"odd session id: {session_id!r}")
    return sorted(glob.glob(os.path.join(pd, "*", f"{session_id}.jsonl")))


def _session_files(session_id, projects_dir):
    sid = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        raise QuoteError("no session: $CLAUDE_CODE_SESSION_ID is not set and no --session given")
    files = transcripts(sid, projects_dir)
    if not files:
        raise QuoteError(f"transcript of session {sid} not found")
    return files


def is_short(fragment):
    """The fragment is under MIN_LEN after normalizing - its only way in is find_short_reply."""
    return len(normalize(fragment or "")) < MIN_LEN


def whole(text):
    """A whole message for the short form: normalized, trailing punctuation cut ("..." from an ellipsis too)."""
    return normalize(text or "").rstrip(".,!?;: ")


def code_re(code):
    """An S-code as a word of its own: S9 is not found inside E7.S9 or S90 (the same idea as the ROADMAP check)."""
    return re.compile(r"(?<![0-9A-Za-z.])" + re.escape(code) + r"(?![0-9])", re.I)


def excerpt(text, codes, n=200):
    """Up to n characters of the assistant's question - a window around the first code it names (that is the proof)."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= n:
        return t
    m = None
    for c in codes:
        m = code_re(c).search(t)
        if m:
            break
    start = max(0, min((m.start() if m else len(t)) - n // 2, len(t) - n))
    return ("…" if start else "") + t[start:start + n] + ("…" if start + n < len(t) else "")


def find_quote(fragment, session_id=None, projects_dir=None):
    """(the whole message, its timestamp) of the LAST human message containing the fragment, or None.
    QuoteError when the check cannot be done."""
    frag = normalize(fragment or "")
    if len(frag) < MIN_LEN:
        raise QuoteError(f"fragment shorter than {MIN_LEN} characters after normalizing: {frag!r}")
    files = _session_files(session_id, projects_dir)
    hit = None
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:  # by \n, not splitlines(): a U+2028 inside a JSON string would split the record
                if '"user"' not in line and "queued_command" not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                r = human_text(rec)
                if r and frag in normalize(r[0]):
                    hit = r  # keep the last one: a fresh "yes" matters more than an old one
    return hit


def _assistant_text(rec):
    """Text of an assistant record the human could see ('' - only thinking / tool_use);
    None - not an assistant record of the main branch."""
    if rec.get("type") != "assistant" or rec.get("isSidechain"):
        return None
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") == "text")


def _load_nodes(path):
    """Transcript -> (nodes, uuid -> index). A node: [kind H/A/O, has a parentUuid key, parentUuid, text, message.id, ts].
    Only the minimum is kept: a transcript can be tens of MB."""
    nodes, idx = [], {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:  # by \n, not splitlines(): a U+2028 inside a JSON string would split the record
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            h = human_text(rec)
            if h:
                kind, text, ts = "H", h[0], h[1]
            else:
                a = _assistant_text(rec)
                kind, text, ts = ("A", a, rec.get("timestamp")) if a is not None else ("O", None, None)
            mid = (rec.get("message") or {}).get("id") if kind == "A" else None
            if rec.get("uuid"):
                idx[rec["uuid"]] = len(nodes)
            nodes.append([kind, "parentUuid" in rec, rec.get("parentUuid"), text, mid, ts])
    return nodes, idx


def _prev(nodes, idx, i):
    n = nodes[i]
    if n[1]:  # has parentUuid - walk the branch; a broken chain (compact, another file) = None
        return idx.get(n[2]) if n[2] else None
    return i - 1 if i > 0 else None


def _question_before(nodes, idx, i):
    """Text of the last assistant message before the human's message i in its branch, or None
    (the chain broke, or another message of the human came first)."""
    j, steps = _prev(nodes, idx, i), 0
    while j is not None and steps < 200000:
        steps += 1
        kind, _, _, text, mid, _ = nodes[j]
        if kind == "H":
            return None
        if kind == "A" and text:
            parts = [text]
            k = _prev(nodes, idx, j)
            # the other text blocks of the same API message (each block is a record of its own)
            while mid and k is not None and nodes[k][0] == "A" and nodes[k][4] == mid and steps < 200000:
                steps += 1
                if nodes[k][3]:
                    parts.append(nodes[k][3])
                k = _prev(nodes, idx, k)
            return "\n".join(reversed(parts))
        j = _prev(nodes, idx, j)
    return None


def find_short_reply(fragment, codes, session_id=None, projects_dir=None):
    """A short answer of the human ("yes", "+", "ok") to an assistant question naming the S-codes `codes`.
    -> {"hit": {"quote", "ts", "question"} | None - the LAST whole message == fragment before which the assistant
         named EVERY code;
        "replies": [{"ts", "question" (None - no assistant message before it)}] - every whole message == fragment
         (to explain a refusal)}.
    QuoteError when the check cannot be done (no session / transcript, empty fragment, no codes)."""
    want = whole(fragment)
    if not want:
        raise QuoteError(f"empty fragment after normalizing: {fragment!r}")
    codes = [c for c in (codes or []) if c]
    if not codes:
        raise QuoteError("a short answer without an S-code cannot be checked: nothing to match the question against")
    pats = [code_re(c) for c in codes]
    hit, replies = None, []
    for f in _session_files(session_id, projects_dir):
        nodes, idx = _load_nodes(f)
        for i, n in enumerate(nodes):
            if n[0] != "H" or whole(n[3]) != want:
                continue
            q = _question_before(nodes, idx, i)
            replies.append({"ts": n[5], "question": q})
            if q is not None and all(p.search(q) for p in pats):
                hit = {"quote": n[3], "ts": n[5], "question": q}  # keep the last one: a fresh "yes" matters more
    return {"hit": hit, "replies": replies}


def main(argv):
    args, sid = [], None
    it = iter(argv)
    for a in it:
        if a == "--session":
            sid = next(it, None)
        else:
            args.append(a)
    if len(args) != 1:
        print(__doc__)
        return 1
    try:
        r = find_quote(args[0], sid)
    except QuoteError as e:
        print(f"⛔ {e}")
        return 1
    if not r:
        print("⛔ the human did not type this in this session")
        return 2
    print(f"✅ {r[1]}: {r[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
