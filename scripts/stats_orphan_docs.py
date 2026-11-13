#!/usr/bin/env python3
"""stats_orphan_docs.py - documents in an agent's folder that the agent itself does not know about: mentioned neither
in its briefing nor in its task lists.

Why: agents write documents into their folder and forget them, and never read them again - and after a compaction such
a document does not exist for the agent (it does not know it wrote it). On the original machine 43% of 204 agent
documents were mentioned nowhere an agent reads from at start.

Once a day: for each agent (a folder with briefing.md) finds .md files missing from its INDEX (briefing.md + *TODO*.md of
that folder). A document is COVERED if the index contains its name (with or without .md, a whole word of >= 5 chars) OR
the name of the subfolder it lies in, with a slash ("notes/", "archive/") - one line per archive folder is enough.
Uncovered and older than MIN_AGE_D days -> ONE letter to the agent (not more often than every REPEAT_D days, and only if
the list changed or the term passed): "add a line 'when X - read Y' or move it into an archive subfolder with a line".
Agents listed in the paused file are skipped. Writes <stats>/orphan-docs.json. `--dry` - no letters.
Cron (daily):  45 * * * * python3 ~/.claude/scripts/stats_orphan_docs.py
Settings: STATS_DIR (default ~/.claude/stats) · CCM_AGENTS_DIR · STATS_PAUSED (default <stats>/paused-agents.txt, one
agent name per line, '#' comments) · letters through the installed inbox_post.sh.
"""
import glob, hashlib, json, os, re, subprocess, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
STATS = os.path.expanduser(os.environ.get("STATS_DIR", "~/.claude/stats"))
AGENTS = conf("CCM_AGENTS_DIR", "") or os.path.join(conf("CCM_WORKSPACE", os.path.expanduser("~/claude-projects")), "Agents")
OUT = f"{STATS}/orphan-docs.json"
STATE = f"{STATS}/.orphan-docs-sent.json"
PAUSED = os.environ.get("STATS_PAUSED", f"{STATS}/paused-agents.txt")
POST = os.path.join(HERE, "inbox_post.sh")
MIN_AGE_D, REPEAT_D, SHOW = 2, 7, 12
SKIP_NAMES = {"briefing.md", "inbox.md", "README.md"}
SKIP_DIRS = {"consolidation", "tests", "node_modules", "__pycache__", ".git", "_deprecated"}


def is_index(name):
    return name == "briefing.md" or "TODO" in name.upper()


def agent_dirs(root):
    return sorted(os.path.dirname(b) for b in glob.glob(f"{root}/**/briefing.md", recursive=True)
                  if "_deprecated" not in b)


def scan(d, all_agents, now):
    """-> (documents in total, [(relative path, age in days)] of the uncovered ones)."""
    index = ""
    for f in glob.glob(f"{d}/*.md"):
        if is_index(os.path.basename(f)):
            index += open(f, encoding="utf-8", errors="replace").read() + "\n"
    total, orphans = 0, []
    for base, dirs, files in os.walk(d):
        # do not enter service folders or the folders of NESTED agents (they have their own briefing and letter)
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")
                   and os.path.join(base, x) not in all_agents]
        for n in files:
            if not n.endswith(".md") or n in SKIP_NAMES or is_index(n) or n.startswith("briefing-"):
                continue
            total += 1
            p = os.path.join(base, n)
            rel = os.path.relpath(p, d)
            stem = os.path.splitext(n)[0]   # the name without .md - only as a whole word, not shorter than 5 chars ('a', 'log' occur in any text)
            covered = n in index or (len(stem) >= 5 and re.search(r"(?<![\w-])" + re.escape(stem) + r"(?![\w-])", index) is not None)
            parts = rel.split(os.sep)[:-1]
            covered = covered or any(f"{x}/" in index for x in parts)
            if not covered:
                orphans.append((rel, (now - os.path.getmtime(p)) / 86400))
    return total, sorted(orphans, key=lambda x: -x[1])


def load(p, default):
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return default


def main(argv):
    dry = "--dry" in argv
    now = time.time()
    try:
        paused = [l.strip() for l in open(PAUSED, encoding="utf-8") if l.strip() and not l.startswith("#")]
    except OSError:
        paused = []
    dirs = agent_dirs(AGENTS)
    alld = set(dirs)
    sent = load(STATE, {})
    report, fails, letters, tot, orph = {}, 0, 0, 0, 0
    for d in dirs:
        name = os.path.basename(d)
        rel_agent = os.path.relpath(d, AGENTS)
        if any(rel_agent.startswith(p) or name.startswith(p) for p in paused):
            continue
        total, orphans = scan(d, alld, now)
        tot += total; orph += len(orphans)
        if not total:
            continue
        report[name] = {"docs": total, "orphans": [{"path": r, "age_d": round(a)} for r, a in orphans]}
        old = [(r, a) for r, a in orphans if a >= MIN_AGE_D]
        if not old or dry:
            continue
        sig = hashlib.sha1("\n".join(sorted(r for r, _ in old)).encode()).hexdigest()[:12]
        prev = sent.get(name) or {}
        if prev.get("sig") == sig and now - prev.get("ts", 0) < REPEAT_D * 86400:
            continue
        if now - prev.get("ts", 0) < 86400:      # not more often than once a day even if the list changed
            continue
        shown = "; ".join(f"{r} ({a:.0f} d)" for r, a in old[:SHOW]) + (f"; ... {len(old) - SHOW} more" if len(old) > SHOW else "")
        txt = (f"orphan_docs - your folder has {len(old)} documents you will not know about after a compaction: they are in "
               f"neither the briefing nor the TODO: {shown}. For each, one of two: (a) a line in the briefing "
               f"'when X comes up - read <file>'; (b) archive - move it into a subfolder (rename-ref keeps links) and put ONE line "
               f"per folder in the briefing '<folder>/ - what is in it, find by search'. Not needed - to the trash. Full list: {OUT}")
        try:
            rc = subprocess.run([POST, name, txt], capture_output=True, timeout=30).returncode
        except Exception:
            rc = 1
        if rc == 0:
            sent[name] = {"sig": sig, "ts": now}; letters += 1
        else:
            fails += 1
            print(f"letter to {name} did not go rc={rc}", file=sys.stderr)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + f".{os.getpid()}.tmp"
    json.dump({"ts": now, "docs": tot, "orphans": orph, "agents": report}, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, OUT)
    if not dry:
        tmp = STATE + f".{os.getpid()}.tmp"
        json.dump(sent, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, STATE)
    print(f"orphan_docs: agents {len(report)}, documents {tot}, uncovered {orph} ({orph * 100 // max(tot, 1)}%); letters {letters}, failed {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
