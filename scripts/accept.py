#!/usr/bin/env python3
"""accept.py <project> <S-code> "<the human's words, verbatim>" [--session SID] - record "accepted by the human".

Accepted = the human's "yes" in the chat, checked by a script, not the agent's word. The agent gives a fragment of what
the human typed; the script looks for it in a message of the HUMAN in this session's transcript (lib/human_quote.py)
and appends to <project>/ACCEPTED.jsonl: {story, quote (the whole message), ts (of the message), sid, agent, at}.
Not found -> rc 2, nothing written. scripts/story_status.py shows the record as the story's "accepted" stage.
Short form ("yes", "+", "ok" - under 8 characters): only a WHOLE message of the human that is a word of agreement
(YES_EN; YES_UK too when CCM_LANG_EXTRA has "uk"), and the last assistant message before it must name this S-code
(human_quote.find_short_reply) - otherwise the "yes" may have answered another question, and a whole "no" is not a
"yes". The record then also has short_form: true and question (up to 200 characters of the assistant's question).
Why: stories were marked accepted on "the human liked it" retold by an agent; nobody could point at the words.
<project>: "Shop" or "Project-Shop" (folder matching CCM_PROJECTS_GLOB). The S-code must be in <project>/ROADMAP.md
(same check as take_task.sh); a new request gets its number with story_add.sh first.
rc: 0 written (or already there) · 1 usage error / the check cannot be done · 2 no such message (or a short one that
does not answer a question naming the code, or is not a word of agreement) · 4 no project/ROADMAP/story.
Config: CCM_WORKSPACE, CCM_PROJECTS_GLOB, CCM_HUMAN_NAME, CCM_LANG_EXTRA.
Env overrides (tests): ACCEPT_REPO (workspace), CLAUDE_PROJECTS_DIR
(transcripts, default ~/.claude/projects), ACCEPT_IDENTITY_DIR (default ~/.claude/agent-identity), CLAUDE_CODE_SESSION_ID."""
import datetime
import fcntl
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402
import human_quote  # noqa: E402

REPO = os.environ.get("ACCEPT_REPO") or conf("CCM_WORKSPACE")
PREFIX = conf("CCM_PROJECTS_GLOB", "Project-*").split("*")[0]
IDENT = os.environ.get("ACCEPT_IDENTITY_DIR") or os.path.expanduser("~/.claude/agent-identity")
WHO = conf("CCM_HUMAN_NAME", "the user")

# Short form: a whole message of the human counts as acceptance only if it is one of these (after human_quote.whole:
# casefold, trailing .,!?;: cut). A whole "no" to "Accept E7.S9?" is an answer to the question, not a "yes".
YES_EN = {"yes", "y", "yep", "yeah", "sure", "ok", "okay", "+", "+1", "go", "accept", "agreed", "lgtm", "👍", "✅"}
YES_UK = {"так", "ок", "окей", "да", "го", "давай", "приймаю", "згоден", "угу", "ага"}
YES = YES_EN | (YES_UK if "uk" in conf("CCM_LANG_EXTRA", "") else set())


def agent_name(sid):
    """The agent's folder name from the identity file the watchman writes; "unknown" without one."""
    try:
        with open(os.path.join(IDENT, sid), encoding="utf-8") as f:
            v = f.read().strip()
    except OSError:
        return "unknown"
    return os.path.basename(v.rstrip("/")) or "unknown"


def append_jsonl(path, rec, key):
    """Append one line under flock; a record with the same key is already there -> False (no duplicate)."""
    new = not os.path.exists(path)
    with open(path, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        if new:
            # a new file in the project folder gets the folder's owner, so jobs running as that user can read it
            os.chmod(path, 0o664)
            try:
                st = os.stat(os.path.dirname(path))
                os.chown(path, st.st_uid, st.st_gid)
            except OSError:
                pass  # not root: the file stays ours
        fh.seek(0)
        for line in fh.read().split("\n"):
            try:
                old = json.loads(line)
            except ValueError:
                continue
            if isinstance(old, dict) and tuple(old.get(k) for k in key) == tuple(rec.get(k) for k in key):
                return False
        fh.seek(0, os.SEEK_END)
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return True


def short_reply(frag, code, sid):
    """Short form -> (message, ts, the assistant's question), or None with the reason for the refusal printed."""
    res = human_quote.find_short_reply(frag, [code], sid)
    if res["hit"]:
        h = res["hit"]
        if human_quote.whole(h["quote"]) not in YES:
            print(f"⛔ \"{h['quote']}\" is not a word of agreement (the short form is accepted only as: "
                  f"{', '.join(sorted(YES))}). \"Accepted\" {code} not written. Give a verbatim fragment of the message "
                  f"of at least {human_quote.MIN_LEN} characters, or ask {WHO} again.")
            return None
        return h["quote"], h["ts"], h["question"]
    shown = human_quote.whole(frag)
    ask = (f"What to do: ask {WHO} again, naming the code in the question itself (e.g. \"Do you accept {code} - ...?\"), "
           f"and run accept.py again after the answer - or give a verbatim fragment of the message of at least "
           f"{human_quote.MIN_LEN} characters.")
    if not res["replies"]:
        print(f"⛔ \"{shown}\" is under {human_quote.MIN_LEN} characters - taken only as a WHOLE message of {WHO}, and "
              f"there is no whole \"{shown}\" in this session (only inside a longer message, or not typed by {WHO}). "
              f"\"Accepted\" {code} not written.\n{ask}")
        return None
    last = res["replies"][-1]
    if last["question"] is None:
        why = "there is no message of yours right before it (or another message of theirs is in between)"
    else:
        why = (f"your last message before it does not name {code}: "
               f"\"{human_quote.excerpt(last['question'], [code], 160)}\"")
    print(f"⛔ {WHO} typed \"{shown}\" ({last['ts']}), but {why} - it may have answered another question. "
          f"\"Accepted\" {code} not written.\n{ask}")
    return None


def main(argv):
    args, sid = [], None
    it = iter(argv)
    for a in it:
        if a == "--session":
            sid = next(it, None)
        else:
            args.append(a)
    if len(args) != 3:
        print(__doc__)
        return 1
    proj, code, frag = args
    proj = proj[len(PREFIX):] if PREFIX and proj.startswith(PREFIX) else proj
    code = code.strip().upper()
    if not re.fullmatch(r"(?:E\d+\.)?S\d+", code):
        print(f"⛔ odd S-code {code!r} (expected E7.S2 or S68)")
        return 1
    name = PREFIX + proj
    pd = os.path.join(REPO, name)
    rm = os.path.join(pd, "ROADMAP.md")
    if not os.path.isfile(rm):
        print(f"⛔ no {rm}")
        return 4
    with open(rm, encoding="utf-8") as f:
        text = f.read()
    # the same test as take_task.sh: the code stands alone or in brackets
    if not re.search(r"(?:\[|[^0-9A-Za-z])" + re.escape(code) + r"(?:[^0-9]|\])", text):
        print(f"⛔ story {code} is not in {rm} - add it (story_add.sh) or take an existing one")
        return 4
    sid = sid or os.environ.get("CLAUDE_CODE_SESSION_ID")
    extra = {}
    try:
        if human_quote.is_short(frag):
            r = short_reply(frag, code, sid)
            if r is None:
                return 2
            quote, ts, question = r
            extra = {"short_form": True, "question": human_quote.excerpt(question, [code])}
        else:
            hit = human_quote.find_quote(frag, sid)
            if not hit:
                print(f"⛔ {WHO} did not type this in this session - \"accepted\" not written")
                return 2
            quote, ts = hit
    except human_quote.QuoteError as e:
        print(f"⛔ {e}")
        return 1
    rec = {"story": code, "quote": quote, "ts": ts, "sid": sid, "agent": agent_name(sid),
           "at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), **extra}
    out = os.path.join(pd, "ACCEPTED.jsonl")
    if append_jsonl(out, rec, ("story", "ts", "sid")):
        print(f"✅ {name} {code} accepted by {WHO} ({ts}): \"{quote[:200]}\" -> {out}")
    else:
        print(f"✅ {name} {code}: this message ({ts}) is already recorded in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
