#!/usr/bin/env python3
"""mistakes-format-gate — keeps the mistakes journal machine-readable.

PreToolUse Write|Edit on the journal: the RESULTING file is checked (an Edit is simulated). Every NEW entry must be
    ## YYYY-MM-DD · <agent> · <gist>
    …
    **Status:** OPEN | ACCEPTED | MECHANIZED …
and must sit below the "## Entry format" section, not in the journal's header. Otherwise → deny with the template.
Old entries are never judged: someone else's bad entry doesn't block your edit.
PostToolUse Bash: a heredoc/sed write that touched the journal can't be predicted, so it is checked AFTER — your own
entries from the last 7 days that are off-format, or any entry in the header → a hint right away.
Why: a journal in four formats is a journal the review script half-reads (in the original swarm the open-mistakes
counter was wrong for a month), and an "insert before the first ## 20…" lands in the header when the header shows an
example line. Fail-open under hook-safe.sh.
Config: CCM_MISTAKES (journal path). Ukrainian headings (Статус / Як писати запис) are accepted too."""
import json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

TARGET = conf("CCM_MISTAKES")
HDR = re.compile(r"^## \d{4}-\d{2}-\d{2} · [^·\n]+ · \S.*$")
STATUS = re.compile(r"^\*\*(?:Status|Статус)[:.]\*\*\s*(OPEN|ACCEPTED|MECHANIZED)\b", re.M)
ANCHORS = ("## Entry format", "## Як писати запис")
TEMPLATE = ("## YYYY-MM-DD · <agent> · <what broke, one line>\n"
            "**What happened:** …\n**Why:** …\n**Fix:** …\n"
            "**Can it be made impossible:** …\n**Status:** OPEN | ACCEPTED | MECHANIZED (<path>)")


def blocks(text):
    """→ {heading: body up to the next '## '}"""
    out, cur, body = {}, None, []
    for line in text.split("\n"):
        if line.startswith("## "):
            if cur is not None:
                out[cur] = "\n".join(body)
            cur, body = line.rstrip(), []
        elif cur is not None:
            body.append(line)
    if cur is not None:
        out[cur] = "\n".join(body)
    return out


def misplaced(text):
    """entry headings (## 20…) above the "## Entry format" section, i.e. in the header"""
    out = []
    for line in text.split("\n"):
        if line.startswith(ANCHORS):
            return out
        if re.match(r"^## 20\d\d-", line):
            out.append(line.rstrip())
    return []                      # no anchor — can't judge, stay silent


def check(blocks_new, before=frozenset(), since=None):
    bad = []
    for h, body in blocks_new.items():
        if h in before or not re.match(r"^## \S*\d", h):
            continue  # old entry, or a service section (first word has no digit)
        if since and h[3:13] < since:
            continue
        if not HDR.match(h):
            bad.append(f"heading is off-format: \"{h[:90]}\"")
        elif not STATUS.search(body):
            bad.append(f"no **Status:** OPEN|ACCEPTED|MECHANIZED line in \"{h[:70]}\"")
    return bad


def my_name(sid):
    """agent name for this session (written by briefing-watchman), or '' — then all recent entries count"""
    try:
        return os.path.basename(open(os.path.expanduser(f"~/.claude/agent-identity/{sid}")).read().strip())
    except OSError:
        return ""


def post_bash(d):
    cmd = (d.get("tool_input") or {}).get("command", "") or ""
    if os.path.basename(TARGET) not in cmd:
        return
    try:
        cur = open(TARGET, encoding="utf-8").read()
    except OSError:
        return
    me = my_name(d.get("session_id", ""))
    mine = {h: b for h, b in blocks(cur).items() if not me or (h.split(" · ") + ["", ""])[1].strip() == me}
    bad = check(mine, since=time.strftime("%Y-%m-%d", time.localtime(time.time() - 7 * 86400)))
    bad += [f"entry in the header, above the entry-format section: \"{h[:70]}\" — move it below" for h in misplaced(cur)]
    if bad:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
            f"⚠ {os.path.basename(TARGET)} after your command: " + "; ".join(bad[:3]) +
            ". The review script can't see such an entry — fix it now. Template:\n" + TEMPLATE}}, ensure_ascii=False))


def main():
    d = json.load(sys.stdin)
    tool = d.get("tool_name")
    ti = d.get("tool_input") or {}
    if tool == "Bash" and d.get("hook_event_name") == "PostToolUse":
        return post_bash(d)
    if tool not in ("Edit", "Write") or os.path.realpath(ti.get("file_path", "") or "") != os.path.realpath(TARGET):
        return
    try:
        cur = open(TARGET, encoding="utf-8").read()
    except OSError:
        cur = ""
    if tool == "Write":
        new = ti.get("content", "") or ""
    else:
        old_s, new_s = ti.get("old_string", ""), ti.get("new_string", "")
        if old_s not in cur:
            return  # the Edit itself will fail with "not found"
        new = cur.replace(old_s, new_s) if ti.get("replace_all") else cur.replace(old_s, new_s, 1)
    bad = check(blocks(new), frozenset(blocks(cur)))
    mp_new, mp_cur = misplaced(new), misplaced(cur)
    if len(mp_new) > len(mp_cur):
        added = [h for h in mp_new if h not in mp_cur][:1] or mp_new[:1]
        bad.append(f"the entry would land in the header, above the entry-format section: {added}. "
                   "Put a new entry right AFTER that section, before the first entry")
    if not bad:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason":
            f"⛔ {os.path.basename(TARGET)}: " + "; ".join(bad[:3]) +
            ". The journal is read by a script — an off-format entry is invisible to it. Template:\n" + TEMPLATE}},
        ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(1)
