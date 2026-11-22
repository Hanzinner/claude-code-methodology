#!/usr/bin/env python3
"""Settings shared by every mechanism: one KEY=VALUE file written by install.sh.

Lookup order for the file: $CLAUDE_METHODOLOGY_CONF (if set, it is the only one looked at), then $CLAUDE_METHODOLOGY_DIR/methodology.conf,
then <install dir>/methodology.conf (this file lives in <install dir>/lib/), then ~/.claude/methodology.conf.
An environment variable with the same name as a key beats the file (handy in tests).
The file is parsed, never sourced: a value can't run code.

Python:  from ccm_conf import conf;  conf("CCM_HUMAN_NAME")
Shell:   eval "$(python3 <install dir>/lib/ccm_conf.py --shell)"   → exports every CCM_* key

Importing this module also makes stdout/stderr UTF-8 when they are not (utf8_stdio below).
"""
import os, shlex, sys


def utf8_stdio():
    """stdout/stderr in UTF-8 when they are in something else. A Windows pipe or file gets the console code page
    (cp1251, cp1252), and print("→") there died with UnicodeEncodeError: check-install.py run straight from Git Bash.
    Every script that imports this module gets it; a script that does not calls it (or does the same two lines).
    Already UTF-8 (Linux, macOS, PYTHONUTF8=1) = nothing changes."""
    for s in (sys.stdout, sys.stderr):
        try:
            if (s.encoding or "").lower().replace("-", "").replace("_", "") != "utf8":
                s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):   # no stream, or not a text stream
            pass


utf8_stdio()


def home_follows_HOME():
    """One home for bash and Python: $HOME. Windows Python takes "~" from USERPROFILE and ignores HOME, while the bash
    scripts, Git Bash and every test (HOME=<temp dir>) go by HOME - so a test's Python wrote into the person's REAL
    ~/.claude (two test reminders stayed behind on a real machine). Where USERPROFILE exists (Windows) and HOME names
    another folder, USERPROFILE is set to HOME for this process and its children. Installed for real, the two are the
    same folder (install.sh writes by HOME, Python reads by USERPROFILE, and the install works) - nothing changes.
    On Windows only a HOME with a drive letter is followed (an unconverted /c/Users/x would mean C:\\c\\Users\\x).
    Linux and macOS have no USERPROFILE: nothing happens. lib/pyshim/sitecustomize.py does the same for scripts that
    do not import this module."""
    h, up = os.environ.get("HOME"), os.environ.get("USERPROFILE")
    if not h or up is None or (os.name == "nt" and not os.path.splitdrive(h)[0]) or not os.path.isabs(h):
        return
    if os.path.normcase(os.path.normpath(h)) != os.path.normcase(os.path.normpath(up)):
        os.environ["USERPROFILE"] = h


home_follows_HOME()

HERE = os.path.dirname(os.path.realpath(__file__))
INSTALL_DIR = os.path.dirname(HERE)
HOME = os.path.expanduser("~")

DEFAULTS = {
    "CCM_HUMAN_NAME": "the user",                     # who the agents work for; used in hints the agent reads
    "CCM_CLAUDE_DIR": INSTALL_DIR,                    # where hooks/, scripts/, lib/ were installed
    "CCM_WORKSPACE": os.path.join(HOME, "claude-projects"),   # root the agents work in (agent folders, journals)
    "CCM_AGENTS_DIR": "",                             # one folder per agent (briefing, inbox, todo); empty = <workspace>/Agents
    "CCM_TRASH_DIR": os.path.join(HOME, ".claude-trash"),   # "delete" = move here (not the desktop/macOS trash)
    "CCM_TRASH_DAYS": "14",
    "CCM_SECRETS_DIR": os.path.join(HOME, ".config", "claude-secrets"),   # keys live here, never in the workspace
    "CCM_TIMEZONE": "",                               # IANA name; empty = system time zone
    "CCM_GLOSSARY": "",                               # file of terms the human already knows (abbr-guard); empty = none
    "CCM_DRAFTING_GUIDE": "",                         # how the human writes outgoing messages (draft-guard); empty = none
    "CCM_MISTAKES": "",                               # mistakes journal; empty = <workspace>/MISTAKES.md
    "CCM_MEMORY_DIR": "",                             # memory (MEMORY.md + files); empty = autoMemoryDirectory in <claude dir>/settings.json, else <claude dir>/memory
    "CCM_EPISODIC_DIR": "",                           # "when did we do X" log; empty = <memory dir>/episodic
    "CCM_FORBIDDEN_SUBAGENT_MODELS": "",              # models subagents must not run on (fable-gate), comma-separated
    "CCM_SUBAGENT_DEFAULT_MODEL": "sonnet",
    "CCM_ALARM_SCRIPTS": "",                          # selfkill-gate: scripts that must be started as background tasks
    "CCM_COORDINATOR_PATTERN": "HQ|Coordinator|Orchestrator",  # order-capture-hint: sessions that hand out work
    "CCM_COST_UNITS_PER_PCT": "",                     # cost-guard: calibration of "1% of the session limit"
    "CCM_DRAFT_GUARD_SKIP": "",                       # draft-guard: agents whose English drafts are not checked
    "CCM_EXTERNAL_DIRS": "",                          # input-guard: workspace folders whose files come from outside
    "CCM_INPUT_GUARD_MUTE": os.path.join(HOME, ".claude", "input-guard-mute.txt"),
    "CCM_TRASH_LIMIT_GB": "3",                        # trash-guard: warn above this size
    "CCM_TRASH_BOARD": os.path.join(HOME, ".claude", "trash-guard", "board.md"),
    "CCM_PROJECTS_GLOB": "Project-*",                 # project folders in the workspace (one repo each)
    "CCM_ALARM_MODE_DIR": os.path.join(HOME, ".claude", "alarm-mode"),   # per-agent alarm mode: off/once/auto/always
    "CCM_WORK_GUARD_AGENTS": "",                      # file: agents that must not stop with open work; empty = guard off
    "CCM_STATUS_GUARD_AGENTS": "",                    # coordinators whose story-state claims need a source run; empty = off
    "CCM_RELEASER_STATE": "/var/lib/ccm-release",     # release queue state (only with install.sh --with-releaser)
    "CCM_SUPERVISOR_DIR": os.path.join(HOME, ".claude", "supervisor"),   # supervisor state, registry, summary
    "CCM_MECH_OWNER": "",                             # agent told when mechanism-code snapshots fail; empty = log only
    "CCM_STATS_OWNER": "",                            # agent told about stats findings; empty = files only
    "CCM_BACKUP_STATE": os.path.join(HOME, ".claude", "offsite-backup"),   # offsite-backup add-on: log, size and last-run markers
    "CCM_BACKUP_PATHS": "",                           # offsite-backup add-on: folders to back up, colon-separated; empty = ~/.claude, the workspace, ~/.ssh, the secrets dir
    "CCM_TG_OUTBOX": "/var/spool/ccm-tg-outbox",      # mobile-bot add-on: spool where agents drop answers for the phone
    "CCM_BR_CDP": "",                                 # agent-browser add-on: debugging endpoint of the browser (e.g. http://127.0.0.1:9333); empty = the add-on's default
    "CCM_WAITING_LINE": "1",                          # waiting-line hook: "waiting for you: N blockers" before the human's next message; 0 = off
    "CCM_WAITING_REPEAT_H": "4",                      # waiting-line: the same open blockers are shown again after this many hours
    "CCM_READER_PORT": "8001",                        # reader add-on: port of the document reader
    "CCM_READER_BIND": "127.0.0.1",                   # reader add-on: this machine only; anything else = every document readable with no password
    "CCM_READER_SHARED": "",                          # reader add-on: folder (under the workspace) agents put documents in for the human; empty = section hidden
    "CCM_READER_HIDE": "",                            # reader add-on: folder names hidden from the reader, comma-separated (dot-folders always are)
    "CCM_READER_SKIP": "",                            # reader add-on: file-name patterns left out of search, comma-separated
    "CCM_READER_STATE": os.path.join(HOME, ".claude", "reader"),   # reader add-on: last opened file + reader settings
    "CCM_LANG_EXTRA": "",                             # extra phrase lists the detectors also match (besides English)
}


def conf_file():
    if "CLAUDE_METHODOLOGY_CONF" in os.environ:          # explicit = final: a missing file means "no file", no fallback
        p = os.environ["CLAUDE_METHODOLOGY_CONF"]
        return p if os.path.isfile(p) else None
    for p in (
              os.environ.get("CLAUDE_METHODOLOGY_DIR") and os.path.join(os.environ["CLAUDE_METHODOLOGY_DIR"], "methodology.conf"),
              os.path.join(INSTALL_DIR, "methodology.conf"),
              os.path.join(HOME, ".claude", "methodology.conf")):
        if p and os.path.isfile(p):
            return p
    return None


def memory_dir(claude_dir):
    """Where Claude Code's own auto memory reads and writes: autoMemoryDirectory in settings.local.json / settings.json
    of the install dir (~ expanded, as Claude does); without it Claude would use ~/.claude/projects/<cwd>/memory/,
    which install.sh avoids by setting it. Fallback when neither file sets it: <claude dir>/memory."""
    import json
    for name in ("settings.local.json", "settings.json"):
        try:
            v = json.load(open(os.path.join(claude_dir, name), encoding="utf-8")).get("autoMemoryDirectory")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(v, str) and v.strip():
            v = v.strip()
            return os.path.join(HOME, v[2:]) if v.startswith("~/") else v
    return os.path.join(claude_dir, "memory")


def memory_dir_set(claude_dir):
    """(memory folder, True when the person set autoMemoryDirectory to somewhere else than <claude dir>/memory).
    Compared by Python itself (normcase + normpath): on Windows memory_dir() gives C:/x/.claude\\memory, and a string
    compare with the shell's C:/x/.claude/memory said "set by the person", so install.sh never wrote the setting.
    On Windows the folder comes back with / (Git Bash and Python both read it)."""
    d = memory_dir(claude_dir)
    norm = lambda p: os.path.normcase(os.path.normpath(p))
    return (d.replace("\\", "/") if os.name == "nt" else d), norm(d) != norm(os.path.join(claude_dir, "memory"))


def _parse(path):
    out = {}
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return out
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        try:
            v = " ".join(shlex.split(v, comments=True))
        except ValueError:
            v = v.strip()
        out[k] = v
    return out


_cache = None


def load():
    global _cache
    if _cache is None:
        f = conf_file()
        vals = dict(DEFAULTS)
        if f:
            vals.update(_parse(f))
        for k in list(vals):
            if k in os.environ:
                vals[k] = os.environ[k]
        if not vals.get("CCM_MISTAKES"):
            vals["CCM_MISTAKES"] = os.path.join(vals["CCM_WORKSPACE"], "MISTAKES.md")
        if not vals.get("CCM_AGENTS_DIR"):
            vals["CCM_AGENTS_DIR"] = os.path.join(vals["CCM_WORKSPACE"], "Agents")
        if not vals.get("CCM_MEMORY_DIR"):   # CLAUDE_MEMORY_DIR: the older name the memory hooks read; still honoured
            vals["CCM_MEMORY_DIR"] = os.environ.get("CLAUDE_MEMORY_DIR") or memory_dir(vals["CCM_CLAUDE_DIR"])
        vals["CCM_MEMORY_DIR"] = vals["CCM_MEMORY_DIR"].rstrip("/") or "/"
        if not vals.get("CCM_EPISODIC_DIR"):
            vals["CCM_EPISODIC_DIR"] = os.path.join(vals["CCM_MEMORY_DIR"], "episodic")
        _cache = vals
    return _cache


def conf(key, default=None):
    v = os.environ[key] if key in os.environ else load().get(key)   # env beats the file for any key, listed or not
    return default if v in (None, "") and default is not None else v


if __name__ == "__main__":
    if sys.argv[1:2] == ["--shell"]:
        for k, v in load().items():
            print(f"export {k}={shlex.quote(v)}")
    elif sys.argv[1:2] == ["--file"]:
        print(conf_file() or "")
    elif sys.argv[1:]:
        print(conf(sys.argv[1], ""))
    else:
        for k, v in load().items():
            print(f"{k}={v}")
