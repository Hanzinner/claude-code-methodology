#!/usr/bin/env python3
"""PreToolUse gate of the mobile bot. Called from mobile-restrict.sh, which is fail-closed.

Threat model: someone took over the Telegram account and is writing to the bot. The boundary
is held here, not by the model's good sense:
  Read/Grep/Glob - no secret zones (tokens, keys, session history, /proc env).
  Write/Edit     - only inside CLAUDE_MOBILE_BOT_ALLOW_PATHS, never secrets, .git or hook config.
  Bash           - an ALLOWLIST. No shell metacharacters outside quotes except the pipe; each
                   pipe segment must start with an allowed tool; path arguments stay out of
                   secret zones; write modes of the allowed tools are cut off.
The secret zones are a list of known names, so an unusual token file outside them stays readable:
keep real secrets out of the bot's reach (its own user, narrow working dir) and don't rely on this.
A plain `ls ~` still shows the NAMES in the home dir (.ssh, .config): accepted, contents stay shut.
Why an allowlist: our first version denied a list of metacharacters and was bypassed by a
newline, then by `<(...)`, `||` and `$VAR`. A shell has too many ways to write or execute to
enumerate them.
"""
import json, os, re, shlex, sys

HOME = os.path.realpath(os.path.expanduser("~"))
HERE = os.path.dirname(os.path.realpath(__file__))
ADDON = os.path.dirname(HERE)   # the bot and this gate: a gate the agent can rewrite is no gate
OSM = os.environ.get("OSM_NEARBY_SCRIPT") or os.path.join(os.path.dirname(HERE), "scripts", "osm-nearby.sh")
HEADS = {"ls", "grep", "cat", "head", "tail", "wc", "sort", "uniq", "du", "df", "stat", "file",
         "which", "echo", "tree", "date", "pwd", "whoami", "git", OSM}
GIT_OK = {"log", "status", "diff", "show"}
SECRET_DIRS = [f"{HOME}/.claude/secrets", f"{HOME}/.claude/projects", f"{HOME}/.ssh",
               f"{HOME}/.gnupg", f"{HOME}/.config", f"{HOME}/.aws", f"{HOME}/.docker", "/proc", "/etc/shadow", "/etc/gshadow",
               "/etc/sudoers", "/etc/sudoers.d"] + (["/root"] if HOME != "/root" else [])
SECRET_RE = re.compile(r"(\.pem|\.key|\.p12|\.pfx|\.kdbx|\.jks)$|(^|/)\.env(\.[^/]*)?$|credential"
                       r"|(^|/)id_(rsa|ed25519|ecdsa|dsa)|_ed25519$|(^|/)\.credentials"
                       r"|(^|/)\.(netrc|npmrc|pypirc|pgpass|git-credentials)$", re.I)
PROTECTED_RE = re.compile(r"/\.git(/|$)|/\.claude/(hooks|mobile-bot|settings)|/secrets/")
CWD = os.getcwd()


def deny(msg):
    print(f"BLOCKED by mobile-bot: {msg}", file=sys.stderr)
    sys.exit(2)


def absp(p):
    p = os.path.expanduser(p)
    return os.path.realpath(p if os.path.isabs(p) else os.path.join(CWD, p))


def is_secret(p, recursive=False):
    a = absp(p)
    if any(a == s or a.startswith(s + "/") for s in SECRET_DIRS):
        return True
    # A recursive read (grep -r, Grep, Glob, tree, ls -R) from an ANCESTOR of a zone walks into it.
    if recursive and any(s.startswith(a.rstrip("/") + "/") for s in SECRET_DIRS):
        return True
    return bool(SECRET_RE.search(a))


def refuse_send(p):
    """The bot's [SEND: path] is a read path too, so it asks here: one definition of "secret"."""
    return is_secret(p) or bool(PROTECTED_RE.search(absp(p)))


def split_unquoted(cmd):
    """Split on `|` outside quotes. Returns (segments, metacharacters seen outside quotes)."""
    segs, cur, meta, q, i = [], [], set(), None, 0
    while i < len(cmd):
        c = cmd[i]
        if q:
            cur.append(c)
            if c == q:
                q = None
            elif c == "\\" and q == '"' and i + 1 < len(cmd):
                cur.append(cmd[i + 1]); i += 1
        elif c in "'\"":
            q = c; cur.append(c)
        elif c == "\\" and i + 1 < len(cmd):
            cur.append(c); cur.append(cmd[i + 1]); i += 1
        elif c == "|":
            if i + 1 < len(cmd) and cmd[i + 1] == "|":
                meta.add("||"); i += 1
            segs.append("".join(cur)); cur = []
        elif c in ";&><(){}*?[":   # globs too: `.ss[h]` hides a path from us, the shell expands it back
            meta.add(c); cur.append(c)
        else:
            cur.append(c)
        i += 1
    if q:
        meta.add("unclosed quote")
    segs.append("".join(cur))
    return [s.strip() for s in segs], meta


def grep_paths(args):
    """grep's path arguments: everything but the pattern, which -e or the first positional gives."""
    paths, pattern_given, positional, take = [], False, [], None
    for a in args:
        if take:
            if take == "f": paths.append(a)
            pattern_given = True     # -f FILE supplies the pattern too; positionals are then paths
            take = None
        elif a in ("--regexp", "--file"):
            take = a[2]
        elif a.startswith("--regexp="):
            pattern_given = True
        elif a.startswith("--") and "=" in a:
            paths.append(a.split("=", 1)[1])
        elif a.startswith("-") and not a.startswith("--") and len(a) > 1:
            cut = next((n for n, c in enumerate(a) if c in "ef"), None)   # -ie PAT, -if FILE, -fFILE
            if cut is not None:
                rest = a[cut + 1:]
                if a[cut] == "f" and rest:
                    paths.append(rest)
                pattern_given = pattern_given or bool(rest)
                take = None if rest else a[cut]
        elif not a.startswith("--") or a == "--":
            positional.append(a)
    return paths + (positional if pattern_given else positional[1:])


def check_args(argv):
    if argv[0] == "echo":   # text only
        return
    flags = [x for x in argv[1:] if x.startswith("-")]
    rec = (argv[0] in ("tree", "du")
           or (argv[0] in ("grep", "ls") and any(f in ("--recursive", "-R", "-r", "--dereference-recursive")
                                                  or (not f.startswith("--") and ("r" in f or "R" in f)) for f in flags)))
    if argv[0] == "grep":
        args = grep_paths(argv[1:])
    else:
        args = []
        for a in argv[1:]:
            if a.startswith("-") and "=" in a:
                a = a.split("=", 1)[1]
            elif a.startswith("-") and not a.startswith("--"):
                # value glued to short flags (-rf/path): from its first / or ~
                a = a[min((n for n in (a.find("/"), a.find("~")) if n >= 0), default=len(a)):]
            if a and not a.startswith("-"):
                args.append(a)
    if rec and not [a for a in args if a]:
        args = ["."]    # no path given: a recursive tool walks the working dir
    for a in args:
        if a and is_secret(a, recursive=rec):
            deny(f"argument in a secret zone ({absp(a)})")


def check_bash(cmd):
    if not cmd.strip():
        deny("empty command")
    if re.search(r"[\n\r]", cmd):
        deny("multi-line command")   # for a shell a newline separates commands, like `;`
    if re.search(r"[$`]", cmd):
        deny("variables and substitutions ($, `) are not allowed, even in quotes")
    segs, meta = split_unquoted(cmd)
    if "||" in meta or "unclosed quote" in meta or any(s == "" for s in segs):
        deny(f"chaining or broken syntax ({', '.join(sorted(meta)) or 'empty segment'})")
    if meta:
        deny(f"metacharacters outside quotes are not allowed ({' '.join(sorted(meta))}); only the pipe is")
    for seg in segs:
        try:
            argv = shlex.split(seg)
        except ValueError as e:
            deny(f"could not parse a segment: {e}")
        head = argv[0]
        if head not in HEADS:
            deny(f"'{head}' is not on the mobile allowlist")
        if head == "git" and (len(argv) < 2 or argv[1] not in GIT_OK or any(x.startswith("--output") for x in argv)):
            deny("git from mobile: only log/status/diff/show, no options before the subcommand, no --output")
        if head == "sort" and any(x == "--output" or x.startswith(("--output=", "-o")) for x in argv[1:]):
            deny("sort -o writes a file")
        if head == "tree" and any(x.startswith(("-o", "--output")) for x in argv[1:]):
            deny("tree -o writes a file")
        if head == "uniq" and len([x for x in argv[1:] if not x.startswith("-")]) > 1:
            deny("uniq IN OUT writes a file")
        if head == "date" and any(x == "--set" or x.startswith(("--set=", "-s")) for x in argv[1:]):
            deny("date -s changes the clock")
        check_args(argv)


def check_write(p):
    if not p:
        deny("empty file_path")
    a = absp(p)
    if is_secret(a) or PROTECTED_RE.search(a) or a == ADDON or a.startswith(ADDON + "/"):
        deny(f"protected path ({a})")
    for prefix in os.environ.get("CLAUDE_MOBILE_BOT_ALLOW_PATHS", "").split(":"):
        if prefix and (a == absp(prefix) or a.startswith(absp(prefix) + "/")):
            return
    deny(f"{a} is outside CLAUDE_MOBILE_BOT_ALLOW_PATHS")


def main():
    global CWD
    d = json.load(sys.stdin)
    CWD = d.get("cwd") or CWD
    tool, ti = d.get("tool_name", ""), d.get("tool_input", {}) or {}
    if tool == "Bash":
        check_bash(ti.get("command", ""))
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        check_write(ti.get("file_path") or ti.get("notebook_path", ""))
    elif tool in ("Read", "Grep", "Glob"):
        for k in ("file_path", "path", "notebook_path"):
            if ti.get(k) and is_secret(ti[k], recursive=tool in ("Grep", "Glob")):
                deny(f"read from a secret zone ({absp(ti[k])})")
        if tool in ("Grep", "Glob") and not ti.get("path") and is_secret(".", recursive=True):
            deny("search from an ancestor of a secret zone; give a narrower path")
        pat = ti.get("pattern", "")
        if tool == "Glob" and (pat.startswith(("/", "~")) or ".." in pat):
            deny("Glob: relative patterns only")
    sys.exit(0)


if os.environ.get("CLAUDE_MOBILE_BOT") == "1":
    main()
