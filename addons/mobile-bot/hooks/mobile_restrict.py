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
                       r"|(^|/)\.(netrc|npmrc|pypirc|pgpass|git-credentials)$|(^|/)\.claude\.json", re.I)
# ~/.claude is closed as a whole except these: history, config backups and file snapshots can't be listed
CLAUDE_HOME = f"{HOME}/.claude"
CLAUDE_OK = (f"{HOME}/.claude/scripts", f"{HOME}/.claude/skills")
PROTECTED_RE = re.compile(r"/\.git(/|$)|/\.claude/(hooks|mobile-bot|settings|agents|commands|skills|rules|output-styles)"
                          r"|/secrets/|/CLAUDE(\.local)?\.md$")
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
    inside = lambda d: a == d or a.startswith(d + "/")
    if inside(CLAUDE_HOME) and not inside(ADDON) and not any(inside(k) for k in CLAUDE_OK):
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


# Flags are an ALLOWLIST too. A list of forbidden flags was bypassed by `sort -uo`, `sort --outp=`,
# `sort --compress-program=sh` (runs code), `uniq - OUT`, `grep -d recurse`, `date -f FILE`.
# GNU accepts flag clusters and abbreviated long options, so an unknown flag is refused and
# abbreviations are not accepted.
# tool: (letters without a value, letters taking a value, long without value, long with value)
FLAGS = {
    "ls":     ("alhtrSR1Fd", "", {"--all"}, set()),
    "grep":   ("inrlLcvwEFHhosx", "ABCmef", {"--recursive", "--ignore-case", "--line-number", "--count"},
               {"--regexp", "--file", "--include", "--exclude", "--exclude-dir"}),
    "cat":    ("nbsAETvet", "", set(), set()),
    "head":   ("qv", "nc", set(), {"--lines", "--bytes"}),
    "tail":   ("qv", "nc", set(), {"--lines", "--bytes"}),
    "wc":     ("lwcmL", "", set(), set()),
    "sort":   ("bdfgiMnrVuh", "kt", set(), set()),
    "uniq":   ("cdui", "fsw", set(), set()),
    "du":     ("hsac", "d", set(), {"--max-depth"}),
    "df":     ("hTi", "", set(), set()),
    "stat":   ("Lt", "c", set(), set()),
    "file":   ("biLz", "", set(), set()),
    "which":  ("a", "", set(), set()),
    "tree":   ("adfh", "LI", {"--noreport"}, set()),
    "date":   ("uR", "d", set(), set()),
    "pwd":    ("", "", set(), set()),
    "whoami": ("", "", set(), set()),
    "git":    ("ps", "n", {"--oneline", "--stat", "--shortstat", "--name-only", "--name-status", "--short",
                           "--porcelain", "--graph", "--all", "--decorate", "--cached", "--staged", "--no-color"},
               {"--since", "--until", "--author", "--grep", "--pretty", "--format"}),
}


def parse_args(head, args):
    """-> (operands, {flag: [values]}). An unknown flag is refused."""
    simple, val, lng, lngval = FLAGS[head]
    ops, vals, i, dd = [], {}, 0, False
    while i < len(args):
        a = args[i]; i += 1
        if dd or a == "-" or not a.startswith("-"):
            ops.append(a)
        elif a == "--":
            dd = True
        elif a.startswith("--"):
            name, eq, v = a.partition("=")
            if name in lng and not eq:
                vals.setdefault(name, [])
            elif name in lngval:
                if not eq:
                    if i >= len(args) or name in ("--pretty", "--format"):   # git takes these only with =
                        deny(f"{head} {name}: no value")
                    v = args[i]; i += 1
                vals.setdefault(name, []).append(v)
            else:
                deny(f"{head}: flag {name} is not allowed from mobile")
        elif re.fullmatch(r"-\d+", a) and head in ("head", "tail", "git"):
            pass
        else:
            for n, c in enumerate(a[1:], 1):
                if c in val:
                    v = a[n + 1:]
                    if not v:
                        if i >= len(args):
                            deny(f"{head} -{c}: no value")
                        v = args[i]; i += 1
                    vals.setdefault("-" + c, []).append(v)
                    break
                if c not in simple:
                    deny(f"{head}: flag -{c} is not allowed from mobile")
    return ops, vals


def check_args(argv):
    head, args = argv[0], argv[1:]
    if head == "echo":   # text only
        return
    if head == "git":
        args = args[1:]
    for a in args:      # the shell expands ~- and ~+ to OLDPWD/PWD; expanduser doesn't
        if a.startswith("~") and a != "~" and not a.startswith("~/"):
            deny(f"the form {a} is not allowed")
    if head not in FLAGS:   # our own scripts (OSM): no flag parsing, paths only
        for a in args:
            if not a.startswith("-") and is_secret(a):
                deny(f"argument in a secret zone ({absp(a)})")
        return
    ops, vals = parse_args(head, args)
    if head == "uniq" and len(ops) > 1:
        deny("uniq IN OUT writes a file")     # `-` is an operand too
    if head == "date":
        if any(not o.startswith("+") for o in ops):
            deny("date: only +FORMAT")
        return
    if head == "grep":
        files = vals.get("-f", []) + vals.get("--file", [])
        if not (files or vals.get("-e") or vals.get("--regexp")):
            ops = ops[1:]    # the first operand is the pattern
        ops = files + ops
    if head == "git":
        ops = ops + [o.split(":", 1)[1] for o in ops if ":" in o]   # HEAD:.env is a path too
    rec = (head in ("tree", "du")
           or (head == "grep" and "--recursive" in vals)
           or (head == "grep" and any(re.fullmatch(r"-[a-zA-Z]*r[a-zA-Z]*", x) for x in args))
           or (head == "ls" and any(re.fullmatch(r"-[a-zA-Z0-9]*[rR][a-zA-Z0-9]*", x) for x in args)))
    if rec and not ops:
        ops = ["."]     # no path given: a recursive tool walks the working dir
    for a in ops:
        if a != "-" and is_secret(a, recursive=rec):
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
