#!/usr/bin/env python3
"""agent_listening.py <agent folder | path to inbox.md> - will the agent read a letter soon? Silent if yes.

Why: a coordinator told the human "started two agents", but one addressee had been idle for hours - inbox_post said
"delivered", which is true, and nobody read the letter. After delivery inbox_post now calls this script and the sender
sees one line:
  ⚠ <agent> is not listening: no alarm (inbox_wait), last activity 12:30 (95 min ago) - it will see the letter when its tab is woken
Listening = a live inbox_wait of the agent OR its session did something in the last QUIET_MIN minutes (the mid-turn
inbox hook shows the letter). The agent's session is found by identity (~/.claude/agent-identity/<session id> ->
the agent's folder); activity = the last timestamp INSIDE its transcript (NOT the file mtime: a night hygiene job that
rewrites session files stamps every sleeping agent with the same time).
rc is always 0: this is a hint to the sender, not a delivery check.
Env (tests): LISTEN_IDENT, LISTEN_ROOTS, LISTEN_WAIT (colon-separated dirs), LISTEN_QUIET_MIN, AGENT_TAB (the tab finder)."""
import calendar, glob, os, re, subprocess, sys, time

HOME = os.path.expanduser("~")
IDENT = os.environ.get("LISTEN_IDENT", os.path.join(HOME, ".claude", "agent-identity")).split(":")
ROOTS = os.environ.get("LISTEN_ROOTS", os.path.join(HOME, ".claude", "projects")).split(":")
WAIT = os.environ.get("LISTEN_WAIT", os.path.join(HOME, ".claude", "inbox-wait")).split(":")
QUIET = int(os.environ.get("LISTEN_QUIET_MIN", "5")) * 60


def last_ts(tp):
    try:
        with open(tp, "rb") as f:
            f.seek(0, 2); f.seek(max(0, f.tell() - 256 * 1024)); tail = f.read().decode("utf-8", "replace")
    except OSError:
        return 0
    m = re.findall(r'"timestamp"\s*:\s*"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)', tail)
    if not m:
        return 0
    return max(calendar.timegm(time.strptime(x, "%Y-%m-%dT%H:%M:%S")) for x in m)   # transcripts stamp UTC


def pid_alive(p):
    try:
        os.kill(int(p), 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False


def main():
    if len(sys.argv) < 2:
        return 0
    t = os.path.normpath(sys.argv[1])
    agent_dir = os.path.dirname(t) if t.endswith(".md") else t
    agent = os.path.basename(agent_dir)
    for w in WAIT:
        try:
            p = open(f"{w}/{agent}").read().strip()
        except OSError:
            continue
        if p.isdigit() and pid_alive(p):
            return 0
    last = 0
    for d in IDENT:
        for f in glob.glob(f"{d}/*"):
            try:
                if os.path.basename(open(f).read().strip().rstrip("/")) != agent:
                    continue
            except OSError:
                continue
            sid = os.path.basename(f)
            for r in ROOTS:
                for tp in glob.glob(f"{r}/*/{sid}.jsonl"):
                    last = max(last, last_ts(tp))
    now = time.time()
    if last and now - last < QUIET:
        return 0
    when = (f"last activity {time.strftime('%d.%m %H:%M' if now - last > 86400 else '%H:%M', time.localtime(last))} "
            f"({int((now - last) // 60)} min ago)") if last else "no session of it found"
    # a ready tab name: the sender does not have to search (agent_tab.py is next to this script)
    try:
        r = subprocess.run([os.environ.get("AGENT_TAB", os.path.join(os.path.dirname(os.path.realpath(__file__)), "agent_tab.py")), agent],
                           capture_output=True, text=True, timeout=3)
        tab = r.stdout.split("\t")[0].strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        tab = None
    here = os.path.dirname(os.path.realpath(__file__))
    how = (f"If urgent, wake it: SendMessage to=\"{tab}\" (short \"letter in inbox\"; the content is in the letter)." if tab else
           "No live tab - if urgent, tell the human to open it." if tab == "" else
           f"If urgent, wake it with SendMessage (the tab: {here}/agent_tab.py {agent}); no tab - tell the human.")
    print(f"⚠ {agent} is not listening: no alarm (inbox_wait), {when} - it will see the letter when its tab is woken. {how}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
