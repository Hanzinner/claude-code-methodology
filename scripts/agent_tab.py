#!/usr/bin/env python3
"""agent_tab.py <agent> [--json] - the live tab of an agent, for SendMessage: its name (to=...) and busy/idle state.
Why: several agents already wake each other with SendMessage, but every one invented its own way to find the tab
(a name written in a briefing goes stale with the first new tab; `pgrep -f <session id>` finds itself).
Logic: identity (~/.claude/agent-identity/<session id> -> the agent's folder; an old name is matched through the
folder's .aliases) -> ~/.claude/sessions/*.json with that sessionId (or name = the agent's name) -> a live pid whose
process start time equals the recorded procStart (so a REUSED pid is not taken for the session).
Prints "<name>\t<idle|busy>" per live tab, idle first; none -> "no live tab", rc 1.
--json -> [{"name","status","pid","sessionId"}].
Config: CCM_AGENTS_DIR. Env AGENT_TAB_IDENT / AGENT_TAB_SESSIONS / AGENT_TAB_AGENTS override the directories (tests)."""
import glob, json, os, subprocess, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

HOME = os.path.expanduser("~")
IDENT = os.environ.get("AGENT_TAB_IDENT", os.path.join(HOME, ".claude", "agent-identity"))
SESS = os.environ.get("AGENT_TAB_SESSIONS", os.path.join(HOME, ".claude", "sessions"))
AGENTS = os.environ.get("AGENT_TAB_AGENTS") or conf("CCM_AGENTS_DIR")


def names(agent):
    """the agent's name + its old names from .aliases (after a rename)"""
    out = {agent.lower()}
    for p in [f"{AGENTS}/{agent}/.aliases"] + glob.glob(f"{AGENTS}/*/{agent}/.aliases"):
        try:
            out |= {l.strip().lower() for l in open(p, encoding="utf-8") if l.strip() and not l.startswith("#")}
        except OSError:
            pass
    return out


def alive(d):
    """the process exists AND is the same one (start time matches). Linux: /proc start time; elsewhere: ps."""
    try:
        pid = int(d["pid"])
    except (KeyError, TypeError, ValueError):
        return False
    try:
        return open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[19] == str(d.get("procStart"))
    except (OSError, IndexError):
        pass
    if os.path.isdir("/proc"):
        return False                      # Linux, and the process is gone
    try:                                  # no /proc (macOS): the pid exists - the best that can be checked
        os.kill(pid, 0)
        return bool(subprocess.run(["ps", "-p", str(pid), "-o", "pid="], capture_output=True, text=True, timeout=3).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def tabs(agent):
    want = names(agent)
    sids = set()
    for f in glob.glob(f"{IDENT}/*"):
        try:
            if os.path.basename(open(f).read().strip().rstrip("/")).lower() in want:
                sids.add(os.path.basename(f))
        except OSError:
            pass
    out = []
    for f in glob.glob(f"{SESS}/*.json"):
        try:
            d = json.load(open(f))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or not alive(d):
            continue
        n = str(d.get("name") or "")
        if d.get("sessionId") in sids or n.lower() in want or any(n.lower().startswith(w + " ") for w in want):
            out.append({"name": n, "status": "busy" if d.get("status") == "busy" else "idle",
                        "pid": d.get("pid"), "sessionId": d.get("sessionId")})
    return sorted(out, key=lambda t: (t["status"] != "idle", t["name"]))


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(a) != 1:
        print("agent_tab.py <agent> [--json]", file=sys.stderr); return 2
    t = tabs(a[0])
    if "--json" in sys.argv:
        print(json.dumps(t, ensure_ascii=False))
    elif t:
        print("\n".join(f"{x['name']}\t{x['status']}" for x in t))
    else:
        print("no live tab")
    return 0 if t else 1


if __name__ == "__main__":
    sys.exit(main())
