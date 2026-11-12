#!/usr/bin/env python3
"""sysfile-gate - PreToolUse Bash: destructive commands on system files -> deny.
Why: an agent running as root executed `rm -f /dev/null`; a plain file replaced the device and git/ssh stopped
working for every user on the machine for 25 minutes.

Deny when a command's target is under /dev/, /boot/, /proc/, /sys/ or is a critical /etc file (passwd, shadow,
group, gshadow, sudoers, fstab, hosts, hostname, resolv.conf), or `rm -r` of a whole first-level /etc/<dir>:
  rm/unlink/shred/truncate/mv/rmdir - any argument;  cp/install/ln/dd(of=) - the target only;  sed -i / perl -i - files.
Does NOT touch redirections (`>/dev/null`, `2>&1`) or `tee /dev/null` - they do not replace the device.
Ordinary /etc edits (nginx, systemd, cron) are free. VAR=path assignments are tracked and substituted
(`f=/dev/x; rm -f "$f"` is caught); quoted text and heredoc bodies are not commands.
Fail-open (run it under hook-safe.sh). Config: CCM_HUMAN_NAME in the deny text."""
import json, os, re, shlex, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

PROT_DIRS = ("/dev/", "/boot/", "/proc/", "/sys/")
PROT_ETC = {"/etc/" + f for f in ("passwd", "shadow", "group", "gshadow", "sudoers",
                                   "fstab", "hosts", "hostname", "resolv.conf")}
WRAP = {"sudo", "env", "nohup", "timeout", "nice", "ionice", "command", "exec", "xargs"}

def protected(p, recursive=False):
    p = p.strip("'\"")
    if p in ("/dev", "/boot", "/proc", "/sys", "/etc", "/"):
        return True
    if p.startswith(PROT_DIRS) or p in PROT_ETC:
        return True
    if recursive and re.fullmatch(r"/etc/[^/]+/?", p):
        return True
    return False

def lex(text):
    """shlex with ; & | ( ) as separators OUTSIDE quotes (false positive: a `;` inside quoted message text split
    "sed/perl -i ... /dev/null" into a separate "command")"""
    lx = shlex.shlex(text, posix=True, punctuation_chars=";&|()")
    lx.whitespace_split = True
    lx.commenters = "#"
    return list(lx)

def split_segments(toks, env=None):
    """command segments; VAR=path assignments are remembered and substituted later
    (`f=/dev/x; rm -f "$f"` used to slip through)"""
    env = {} if env is None else env
    out, seg = [], []
    for t in toks + [";"]:
        if t and set(t) <= set(";&|()"):
            body = [x for x in seg if x not in ("export", "local", "readonly", "declare")]
            if body and all(re.fullmatch(r"\w+=.*", x) for x in body):
                for x in body:  # pure assignment: remember it (value is already unquoted by shlex)
                    k, _, v = x.partition("=")
                    env[k] = v
            else:
                out.append(strip_wrappers([subst(x, env) for x in seg]))
            seg = []
        else:
            seg.append(t)
    return out

def subst(tok, env):
    """$VAR / ${VAR} -> value from env (known ones only; $(...) is left alone)"""
    return re.sub(r"\$\{?(\w+)\}?", lambda m: env.get(m.group(1), m.group(0)), tok)

def commands(cmd):
    """-> token lists of commands; heredoc bodies skipped; quotes may span lines"""
    kept, skip = [], None
    for line in cmd[:6000].splitlines()[:150]:
        if skip is not None:
            if line.strip() == skip:
                skip = None
            continue
        if "<<" in line:
            mk = line.split("<<")[-1].strip().lstrip("-").strip("'\"")
            if mk and mk.replace("_", "").isalnum():
                skip = mk
        kept.append(line)
    out = []
    try:
        # a newline is a separator; inside quotes ';' is just text
        out = split_segments(lex(" ;\n".join(kept)), {})
    except ValueError:  # unclosed quote - fall back to line-by-line parsing
        env = {}
        for line in kept:
            try:
                out += split_segments(lex(line), env)
            except ValueError:
                continue
    return [t for t in out if t]

def strip_wrappers(toks):
    """`sudo -u hanz timeout 5 FOO=1 rm …` → `rm …`"""
    while toks:
        t = toks[0]
        if re.fullmatch(r"\w+=.*", t):
            toks = toks[1:]
        elif t in WRAP:
            toks = toks[1:]
            while toks and toks[0].startswith("-"):
                opt = toks[0]
                toks = toks[1:]
                if opt in ("-u", "-g", "-k", "-C", "-D") and toks:  # option with a value (sudo -u, timeout -k)
                    toks = toks[1:]
            if t == "timeout" and toks and re.fullmatch(r"[\d.]+[smhd]?", toks[0]):
                toks = toks[1:]
        else:
            break
    return toks

def check(toks):
    head = toks[0].rsplit("/", 1)[-1]
    args = [t for t in toks[1:] if not t.startswith("-")]
    flags = "".join(t for t in toks[1:] if t.startswith("-") and not t.startswith("--"))
    rec = "r" in flags.lower() or "--recursive" in toks
    if head in ("rm", "unlink", "shred", "truncate", "mv", "rmdir"):
        hits = [a for a in args if protected(a, rec)]
    elif head in ("cp", "install", "ln"):
        hits = [args[-1]] if len(args) >= 2 and protected(args[-1]) else []
    elif head == "dd":
        hits = [t[3:] for t in toks[1:] if t.startswith("of=") and protected(t[3:])]
    elif head in ("sed", "perl") and any(t == "-i" or t.startswith("-i") or t.startswith("-pi")
                                        for t in toks[1:]):
        hits = [a for a in args[1:] if protected(a)]
    else:
        hits = []
    return (head, hits[0]) if hits else None

def main():
    d = json.load(sys.stdin)
    if d.get("tool_name") != "Bash":
        return
    cmd = (d.get("tool_input") or {}).get("command", "") or ""
    if not re.search(r"/(dev|boot|proc|sys|etc)\b", cmd):
        return  # fast exit
    for toks in commands(cmd):
        hit = check(toks)
        if hit:
            who = conf("CCM_HUMAN_NAME")
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason":
                    f"⛔ sysfile-gate: `{hit[0]}` on the system path `{hit[1]}`. "
                    "A real incident: `rm -f /dev/null` put git/ssh out of action for 25 minutes. "
                    "An agent does not modify system devices, the bootloader or critical /etc files - "
                    f"describe what is needed and ask {who} to run it (a ready command + what they should see)."}},
                ensure_ascii=False))
            return

if __name__ == "__main__":
    try:
        main()
    except Exception:
        # do not swallow silently: trace -> stderr, rc=1 -> hook-safe.sh logs it (fail-open)
        import traceback; traceback.print_exc(); sys.exit(1)
