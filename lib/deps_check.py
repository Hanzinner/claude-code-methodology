#!/usr/bin/env python3
"""System commands the mechanisms call that a stock macOS, Git Bash on Windows (or a minimal Linux) does not have.

  python3 lib/deps_check.py     # all there: prints nothing; else one block: "missing: X — what stops" + "install: ..."

Always exit 0: a missing command is a warning, never a reason to stop an install. install.sh prints the block at its
start, check-install.py in its report. Without these commands nothing fails loudly: a hook under hook-safe.sh exits 127
and fails open, a lock "times out" - so the person never learns why a mechanism is quiet.
Each "what stops" names the callers a grep of the repo finds (comments and parsers of command lines left out).
"""
import json, os, shutil, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "."))
try:
    import ccm_conf  # noqa: E402,F401  (on import: UTF-8 output where the console code page is cp1251/cp1252)
except ImportError:   # a copy of this script without lib/ next to it
    pass

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def _wrapped_hooks():
    """'N of the M hooks in settings.json' from the template (only in a clone; an install dir has no template)"""
    try:
        t = json.load(open(os.path.join(REPO, "settings.template.json"), encoding="utf-8"))
        cmds = [h.get("command", "") for gs in t["hooks"].values() for g in gs for h in g.get("hooks", [])]
        return f"{sum('hook-safe.sh' in c for c in cmds)} of the {len(cmds)} hook commands in settings.json"
    except (OSError, ValueError, KeyError, AttributeError):
        return "almost every hook in settings.json"


# (command, what stops working without it, apt package, brew package or None, note for macOS, how on Windows/Git Bash)
# flock and setsid are not here: every caller has a fallback (lib/ccm_lock.sh / ccm_lock.py, a reader started without
# setsid), so nothing stops without them.
DEPS = (
    ("timeout",
     f"hooks/hook-safe.sh runs {_wrapped_hooks()} (every gate, hint and Stop guard): without it each exits 127 and "
     "fails open, so they are all silently off; also stop-dispatch.sh, cross-review.sh, memory_consolidation.sh "
     "and the quota_status.py cron line",
     "coreutils", "coreutils", "brew names it gtimeout: put \"$(brew --prefix)/opt/coreutils/libexec/gnubin\" first in PATH",
     "it comes with Git for Windows: run install.sh and Claude Code from Git Bash"),
    ("crontab",
     "every scheduled job install.sh sets up (reminders, supervisor, quota, blockers, chat backup, journal checks): "
     "install.sh prints the lines to add to your scheduler by hand; library_check.py does not see cron scripts",
     "cron", None, "",
     "Windows has no cron: add the jobs to Task Scheduler (install.sh prints them and a schtasks line for the reminders)"),
)


def on_windows():
    return sys.platform == "win32" or bool(os.environ.get("MSYSTEM"))   # MSYSTEM: set by Git Bash (MINGW64)


def missing():
    return [d for d in DEPS if shutil.which(d[0]) is None]


def block():
    """lines to print; [] when nothing is missing"""
    miss = missing()
    if not miss:
        return []
    lines = [f"missing: {cmd} — {why}" for cmd, why, *_ in miss]
    if on_windows():
        lines += [f"install (Windows, {cmd}): {win}" for cmd, *_, win in miss]
        return lines
    apt = " ".join(dict.fromkeys(d[2] for d in miss))
    brew = " ".join(dict.fromkeys(d[3] for d in miss if d[3]))
    notes = "; ".join(d[4] for d in miss if d[4])
    lines.append(f"install: apt install {apt}" + (f" / brew install {brew}" if brew else "") + (f" ({notes})" if notes else ""))
    return lines


if __name__ == "__main__":
    out = block()
    if out:
        print("\n".join(out))
    sys.exit(0)
