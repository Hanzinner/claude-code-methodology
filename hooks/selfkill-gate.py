#!/usr/bin/env python3
"""selfkill-gate (PreToolUse Bash). Keeps an agent from killing its own session, and from launching a "wait alarm"
in a way the harness cannot see.
1) `pkill -f` -> deny (several agents killed their own shell with it: the pattern matches the agent's own command
   line). `pgrep -f` -> a hint + a counter log (`until ! pgrep -f X` waited forever because it saw itself).
2) Remote: `ssh host 'pkill -f X'` / `pgrep -f X` on an ssh line. The remote `bash -c` carries the pattern in its own
   cmdline, so pkill kills your own ssh session (exit 255) and pgrep sees itself. Allowed when the pattern has a
   character class (`[q]emu`) - then it does not match itself.
3) Alarm scripts (names listed in CCM_ALARM_SCRIPTS, default none = rule off): launching one with `&` / disown /
   nohup / setsid -> deny. The harness only watches processes it started itself (`run_in_background: true`); a detached
   alarm fires into the void and nobody is woken.
Performance: scan <= 6 KB, tokenise per segment, no star-groups in regexes (an older version hung 20 s on big heredocs
through lazy-regex backtracking). Quoted text and heredoc bodies are not commands, so a message that merely mentions
`pkill -f` is not blocked. Fail-open.
Config: CCM_ALARM_SCRIPTS (comma-separated script base names)."""
import json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

REMOTE = ("ssh", "ssh.exe", "plink")


def heredoc_marker(line):
    m = line.split("<<")[-1].strip().strip("-").strip("'\"")
    return m if m and m.replace("_", "").isalnum() else None


def remote_selfkill(cmd):
    """an ssh line with pkill/pgrep -f without a character class -> description, else None"""
    skip_until = None
    for line in cmd[:6000].splitlines()[:120]:
        if skip_until is not None:
            if line.strip() == skip_until:
                skip_until = None
            continue
        if "<<" in line:
            skip_until = heredoc_marker(line)
        toks = line.split()
        if not any(t.strip("'\"(") in REMOTE for t in toks):
            continue
        for i, t in enumerate(toks):
            if t.strip("'\";(") in ("pkill", "pgrep") and "-f" in toks[i + 1:i + 3]:
                if "[" not in " ".join(toks[i + 1:i + 4]):
                    return " ".join(toks[i:i + 3])
    return None


def segments(cmd):
    """first tokens of every command segment (no regex bombs); heredoc bodies skipped"""
    out, skip_until = [], None
    for line in cmd[:6000].splitlines()[:120]:
        if skip_until is not None:
            if line.strip() == skip_until:
                skip_until = None
            continue
        if "<<" in line:
            skip_until = heredoc_marker(line)
        for chunk in line.replace("&&", ";").replace("||", ";").replace("|", ";").split(";"):
            toks = chunk.strip().split()
            if toks:
                out.append(toks[:8])
    return out


def hint(text):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}},
                     ensure_ascii=False))


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}, ensure_ascii=False))


QUOTED = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?.*?^\1$|'[^']*'|\"(?:[^\"\\]|\\.)*\"", re.S | re.M)
DETACH = re.compile(r"\b(?:disown|nohup|setsid)\b|(?<![&>|<0-9])&(?![&>])")


def code_only(cmd):
    """the text without quoted strings and heredocs: words in a message or comment are not a command"""
    return QUOTED.sub(" ", cmd)


def alarm_regex():
    names = [n.strip() for n in conf("CCM_ALARM_SCRIPTS", "").split(",") if n.strip()]
    if not names:
        return None
    return re.compile(r"(?:^|[;&|(\s])(?:\S*/)?(?:" + "|".join(re.escape(n) for n in names) + r")(?:\s|$)")


def main():
    d = json.load(sys.stdin)
    if d.get("tool_name") != "Bash":
        return
    cmd = (d.get("tool_input") or {}).get("command", "") or ""
    alarm = alarm_regex()
    if alarm and alarm.search(cmd[:4000]):
        bare = code_only(cmd[:4000])
        if alarm.search(bare) and DETACH.search(bare):
            deny("⛔ selfkill-gate: an alarm script must be started with run_in_background: true (no `&`, disown, "
                 "nohup, setsid). The harness does not watch a detached process: the message arrives and nobody "
                 "wakes you. Call Bash with run_in_background: true and the plain command.")
            return
    if "pkill" not in cmd and "pgrep" not in cmd:
        return                                  # fast exit for most commands
    hit = remote_selfkill(cmd)
    if hit:
        deny(f"⛔ selfkill-gate (remote): `{hit}` on an ssh line - the remote shell carries this pattern in its own "
             "cmdline, so pkill kills YOUR OWN ssh session (exit 255) and pgrep sees itself. "
             "Use a character class in the pattern: `pkill -f '[d]ocker pull'`, or kill by PID.")
        return
    for toks in segments(cmd):
        head = toks[0]
        if head == "pkill" and "-f" in toks[1:]:
            deny("⛔ selfkill-gate: `pkill -f` also matches YOUR OWN process/shell (several agents already killed "
                 "themselves this way). Kill by PID (`PID=$!; kill $PID`), or `pgrep -f <pattern> | grep -v $$` and "
                 "kill the listed ones, or use an anchor that is not in your own command line.")
            return
        if "pgrep" in toks and head != "pgrep":        # `until ! pgrep -f X`, `while pgrep -f X`, `if pgrep ...`
            toks = toks[toks.index("pgrep"):]; head = "pgrep"
        if head == "pgrep" and "-f" in toks[1:]:
            try:
                with open(os.path.expanduser("~/.claude/selfkill-pgrep.log"), "a") as f:
                    f.write(time.strftime("%F %T") + " " + " ".join(toks)[:120] + "\n")
            except OSError:
                pass
            pat = next((t for t in toks[1:] if not t.startswith("-")), "")
            if pat and not re.search(r"\[[^\]]+\]", pat):
                hint("💡 selfkill-gate: `pgrep -f " + pat[:40] + "` also sees YOUR OWN shell (its command line holds "
                     "the same pattern) - in a loop like `until ! pgrep -f ...` that is an endless wait. Use "
                     "`pgrep -x <name>` or a character class that is not in your own line: "
                     "`pgrep -f '[" + pat[:1] + "]" + pat[1:40] + "'`.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
