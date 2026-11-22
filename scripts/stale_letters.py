#!/usr/bin/env python3
"""stale_letters.py <agent> - my urgent letters that lie unread with an addressee whose tab is alive.

Why: in the original swarm a coordinator waited 6 hours for a sleeping agent with an urgent letter in its inbox; its
own alarm woke it 7 times, and it never woke the addressee, though the addressee's session was alive the whole time.
The alarm (inbox_wait.sh), on a link with no letters, calls this script: for each of MY letters from the send log
(~/.claude/inbox-sent.log, written by inbox_post.sh) that is marked urgent (🖐, URGENT, a priority 90-100 like "M·90")
and still stands in the addressee's "New" section longer than MIN_AGE minutes, while the addressee has a live tab
(agent_tab.py) → a line "your letter to <agent> has lain N min, the tab is alive → SendMessage to=<tab>".
None → silence. It sends nothing itself: waking someone is the agent's decision.
Config: CCM_AGENTS_DIR, CCM_LANG_EXTRA ("uk" also counts the Ukrainian mark ТЕРМІНОВО).
Test overrides: STALE_SENT_LOG, STALE_AGENTS_DIR, STALE_AGENT_TAB (a command instead of agent_tab.py), STALE_MIN_AGE (min)."""
import json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402

LOG = os.environ.get("STALE_SENT_LOG") or os.path.expanduser("~/.claude/inbox-sent.log")
AGENTS = os.environ.get("STALE_AGENTS_DIR") or conf("CCM_AGENTS_DIR")
TAB = os.environ.get("STALE_AGENT_TAB") or f"{sys.executable} {os.path.join(HERE, 'agent_tab.py')}"
MIN_AGE = int(os.environ.get("STALE_MIN_AGE") or 10)
UK = "uk" in conf("CCM_LANG_EXTRA", "")
URGENT = re.compile(r"🖐|URGENT|" + (r"ТЕРМІНОВ|" if UK else "") + r"(?<![\w])[A-Z]{1,2}·(?:9\d|100)(?!\d)")
# The inbox's "new" section, in the order inbox_lib.sh looks for it (the template says "## New"; older inboxes "## Нові").
NEW_HDRS = ("## New candidates", "## Нові кандидати", "## New", "## Нові")


def new_items(inbox):
    try:
        lines = open(inbox, encoding="utf-8").read().split("\n")
    except OSError:
        return ""
    hdr = next((h for h in NEW_HDRS if h in lines), None)
    if not hdr:
        return ""
    out, on = [], False
    for l in lines:
        if l == hdr:
            on = True
        elif l.startswith("## "):
            on = False
        elif on and l.startswith("- [ ]"):
            out.append(l)
    return "\n".join(out)


def inbox_of(agent):
    p = os.path.join(AGENTS, agent, "inbox.md")
    if os.path.isfile(p):
        return p
    hits = [os.path.join(r, "inbox.md") for r, d, f in os.walk(AGENTS) if os.path.basename(r) == agent and "inbox.md" in f]
    return hits[0] if hits else ""


def tab(agent):
    try:
        out = subprocess.run([*TAB.split(), agent, "--json"], capture_output=True, text=True, timeout=10).stdout
        rows = json.loads(out or "[]")
        return rows[0] if rows else None
    except Exception:
        return None


def main(me):
    now, seen, out = time.time(), set(), []
    try:
        rows = [l.rstrip("\n").split("\t") for l in open(LOG, encoding="utf-8", errors="replace")]
    except OSError:
        return 0
    for r in rows[-500:]:
        if len(r) < 4 or r[1] != me or not URGENT.search(r[3]):
            continue
        try:
            ts = float(r[0])
        except ValueError:
            continue
        to, head = r[2], r[3]
        age = (now - ts) / 60
        if age < MIN_AGE or age > 24 * 60 or (to, head) in seen:
            continue
        seen.add((to, head))
        key = re.sub(r"^- \[ \] \[[^\]]*\]\s*", "", head)[:60]
        if not key or key not in new_items(inbox_of(to)):
            continue                       # already read (moved out of "New") or not found
        t = tab(to)
        if not t:
            continue                       # no live tab - nothing to wake; inbox_post already says "not listening"
        out.append(f"📮 your urgent letter to {to} has lain unread for {int(age)} min, its tab is alive "
                   f"({t.get('status')}) → SendMessage to=\"{t.get('name')}\" (short: \"a letter in your inbox\"; "
                   "the content is in the letter)")
    if out:
        print("\n".join(out[:5]))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__); sys.exit(2 if len(sys.argv) < 2 else 0)
    try:
        sys.exit(main(sys.argv[1]))
    except Exception as e:      # the alarm must not fail because of a hint
        print(f"stale_letters: {e}", file=sys.stderr); sys.exit(0)
