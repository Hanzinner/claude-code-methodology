#!/usr/bin/env python3
"""Self-register the current Claude Code session as a named agent.

Writes (name → sid) into the registry so other sessions can dial this one
via call_agent.sh. Typically invoked by the /register-as skill.
"""
import json, os, sys, fcntl, datetime, pathlib

CLAUDE_DIR = pathlib.Path(os.environ.get("CLAUDE_METHODOLOGY_DIR", os.path.expanduser("~/.claude")))
REGISTRY = CLAUDE_DIR / "agent-registry.json"


def main():
    if len(sys.argv) != 2:
        print("usage: register_agent.py <name>", file=sys.stderr)
        sys.exit(2)
    name = sys.argv[1].strip().lower()
    if not name or not all(c.isalnum() or c in "-_" for c in name):
        print(f"invalid name: {name!r} (use a-z 0-9 - _)", file=sys.stderr)
        sys.exit(2)

    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        print("CLAUDE_CODE_SESSION_ID not set — run inside a Claude Code session", file=sys.stderr)
        sys.exit(1)
    cwd = os.environ.get("PWD") or os.getcwd()
    user = os.environ.get("USER", "unknown")
    now = datetime.datetime.now().isoformat(timespec="seconds")

    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.touch(exist_ok=True)

    with open(REGISTRY, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            raw = f.read().strip()
            reg = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            print(f"registry corrupted at {REGISTRY} — aborting", file=sys.stderr)
            sys.exit(1)

        prev = reg.get(name)
        reg[name] = {"sid": sid, "cwd": cwd, "user": user, "registered_at": now}

        f.seek(0)
        f.truncate()
        json.dump(reg, f, indent=2, ensure_ascii=False)
        f.write("\n")

    if prev and prev.get("sid") != sid:
        print(f"OK: '{name}' re-registered. Was sid={prev['sid']}, now sid={sid}")
    else:
        print(f"OK: '{name}' registered with sid={sid}")
    print(f"   cwd: {cwd}")
    print(f"   registry: {REGISTRY}")


if __name__ == "__main__":
    main()
