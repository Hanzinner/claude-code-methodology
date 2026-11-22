#!/usr/bin/env python3
"""System commands the mechanisms call that a stock macOS (or a minimal Linux) does not have.

  python3 lib/deps_check.py     # all there: prints nothing; else one block: "missing: X — what stops" + "install: ..."

Always exit 0: a missing command is a warning, never a reason to stop an install. install.sh prints the block at its
start, check-install.py in its report. Without these commands nothing fails loudly: a hook under hook-safe.sh exits 127
and fails open, a lock "times out" - so the person never learns why a mechanism is quiet.
Each "what stops" names the callers a grep of the repo finds (comments and parsers of command lines left out).
"""
import json, os, shutil, sys

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def _wrapped_hooks():
    """'N of the M hooks in settings.json' from the template (only in a clone; an install dir has no template)"""
    try:
        t = json.load(open(os.path.join(REPO, "settings.template.json"), encoding="utf-8"))
        cmds = [h.get("command", "") for gs in t["hooks"].values() for g in gs for h in g.get("hooks", [])]
        return f"{sum('hook-safe.sh' in c for c in cmds)} of the {len(cmds)} hook commands in settings.json"
    except (OSError, ValueError, KeyError, AttributeError):
        return "almost every hook in settings.json"


# (command, what stops working without it, apt package, brew package or None, note for macOS)
DEPS = (
    ("timeout",
     f"hooks/hook-safe.sh runs {_wrapped_hooks()} (every gate, hint and Stop guard): without it each exits 127 and "
     "fails open, so they are all silently off; also stop-dispatch.sh, cross-review.sh, memory_consolidation.sh "
     "and the quota_status.py cron line",
     "coreutils", "coreutils", "brew names it gtimeout: put \"$(brew --prefix)/opt/coreutils/libexec/gnubin\" first in PATH"),
    ("flock",
     "claim.sh (the swarm lock), episodic_append.sh (the episodic journal), wt_deliver.sh (worktree delivery), "
     "memory_consolidation.sh and the quota_status.py cron line (the quota file stays empty); "
     "inbox_post.sh / inbox_done.sh and catchup-run fall back to a slower mkdir lock",
     "util-linux", "flock", ""),
    ("setsid",
     "install.sh --with-reader cannot start the reader right away (its crontab line starts it after a reboot)",
     "util-linux", None, "macOS: start the reader by hand, python3 <dir>/addons/reader/reader-server.py &"),
    ("crontab",
     "every scheduled job install.sh sets up (reminders, supervisor, quota, blockers, chat backup, journal checks): "
     "install.sh prints the lines to add to your scheduler by hand; library_check.py does not see cron scripts",
     "cron", None, ""),
)


def missing():
    return [d for d in DEPS if shutil.which(d[0]) is None]


def block():
    """lines to print; [] when nothing is missing"""
    miss = missing()
    if not miss:
        return []
    lines = [f"missing: {cmd} — {why}" for cmd, why, *_ in miss]
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
