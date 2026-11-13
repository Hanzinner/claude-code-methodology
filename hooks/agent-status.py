#!/usr/bin/env python3
"""agent-status - writes what an agent is doing to a plain local file that any dashboard can read.
  PostToolUse (matcher *)  -> WORKING   (it just called a tool = busy)
  Stop (detector branch)   -> the last reply has "ASK:" -> ASK <text>;  otherwise -> DONE (turn finished, free)
The agent writes only "ASK: <question>" itself (that is meaning, not an event); everything else is caught by the hooks - the
status is a hook, not the agent's discipline. Why: with several agents in several tabs the human cannot tell at a glance who is
working, who is done and who is waiting for an answer.
File: ~/.claude/agent-status/<agent>.json   {"agent","state":"WORKING|DONE|ASK","ask","session","updated" (unix),"updated_iso"}
written atomically. <agent> = folder name from ~/.claude/agent-identity/<session_id>; no identity -> silent exit (the hook
runs on every session). Left out of the port: the live version also kept WORKING while a "loop flag" of the original
dashboard existed - that file belongs to one machine's dashboard; here any loop can set the state by writing the same file.
Config: none (state dir is ~/.claude/agent-status; env CCM_AGENT_STATUS_DIR overrides)."""
import json, os, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
HOME = os.path.expanduser("~")
OUT = os.environ.get("CCM_AGENT_STATUS_DIR", f"{HOME}/.claude/agent-status")


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        return
    sid = d.get("session_id", "")
    ev = d.get("hook_event_name", "")
    try:
        agent = os.path.basename(open(f"{HOME}/.claude/agent-identity/{sid}").read().strip().rstrip("/"))
    except OSError:
        return
    if not agent or ev not in ("PostToolUse", "Stop"):
        return
    state, ask = "WORKING", ""
    if ev == "Stop":
        txt = ""
        try:
            from transcript_tail import lines
            for line in lines(d.get("transcript_path", ""), lambda o: o.get("type") == "assistant",
                              need='"assistant"', skip=None):
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if o.get("type") == "assistant":
                    for c in ((o.get("message") if isinstance(o.get("message"), dict) else {}).get("content") or []):
                        if isinstance(c, dict) and c.get("type") == "text":
                            txt = c["text"]
        except Exception:
            pass
        if "ASK:" in txt:
            state, ask = "ASK", txt.split("ASK:", 1)[1].strip().split("\n")[0][:200]
        else:
            state = "DONE"
    try:
        os.makedirs(OUT, exist_ok=True)
        f = os.path.join(OUT, f"{agent}.json")
        tmp = f + f".tmp{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"agent": agent, "state": state, "ask": ask, "session": sid, "updated": int(time.time()),
                       "updated_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, fh, ensure_ascii=False)
        os.replace(tmp, f)
    except OSError:
        pass


if __name__ == "__main__":
    main()
