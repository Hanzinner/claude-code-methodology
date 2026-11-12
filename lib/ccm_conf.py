#!/usr/bin/env python3
"""Settings shared by every mechanism: one KEY=VALUE file written by install.sh.

Lookup order for the file: $CLAUDE_METHODOLOGY_CONF (if set, it is the only one looked at), then $CLAUDE_METHODOLOGY_DIR/methodology.conf,
then <install dir>/methodology.conf (this file lives in <install dir>/lib/), then ~/.claude/methodology.conf.
An environment variable with the same name as a key beats the file (handy in tests).
The file is parsed, never sourced: a value can't run code.

Python:  from ccm_conf import conf;  conf("CCM_HUMAN_NAME")
Shell:   eval "$(python3 <install dir>/lib/ccm_conf.py --shell)"   → exports every CCM_* key
"""
import os, shlex, sys

HERE = os.path.dirname(os.path.realpath(__file__))
INSTALL_DIR = os.path.dirname(HERE)
HOME = os.path.expanduser("~")

DEFAULTS = {
    "CCM_HUMAN_NAME": "the user",                     # who the agents work for; used in hints the agent reads
    "CCM_CLAUDE_DIR": INSTALL_DIR,                    # where hooks/, scripts/, lib/ were installed
    "CCM_WORKSPACE": os.path.join(HOME, "claude-projects"),   # root the agents work in (agent folders, journals)
    "CCM_TRASH_DIR": os.path.join(HOME, ".claude-trash"),   # "delete" = move here (not the desktop/macOS trash)
    "CCM_TRASH_DAYS": "14",
    "CCM_SECRETS_DIR": os.path.join(HOME, ".config", "claude-secrets"),   # keys live here, never in the workspace
    "CCM_TIMEZONE": "",                               # IANA name; empty = system time zone
    "CCM_GLOSSARY": "",                               # file of terms the human already knows (abbr-guard); empty = none
    "CCM_DRAFTING_GUIDE": "",                         # how the human writes outgoing messages (draft-guard); empty = none
    "CCM_MISTAKES": "",                               # mistakes journal; empty = <workspace>/MISTAKES.md
    "CCM_EPISODIC_DIR": "",                           # "when did we do X" log; empty = <claude dir>/memory/episodic
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
        if not vals.get("CCM_EPISODIC_DIR"):
            vals["CCM_EPISODIC_DIR"] = os.path.join(vals["CCM_CLAUDE_DIR"], "memory", "episodic")
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
