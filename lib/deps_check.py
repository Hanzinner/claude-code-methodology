#!/usr/bin/env python3
"""System commands the mechanisms call that a stock macOS, Git Bash on Windows (or a minimal Linux) does not have.

  python3 lib/deps_check.py              # all there: prints nothing; else one block: "missing: X — what stops" + "install: ..."
  python3 lib/deps_check.py --addon agent-browser   # also what that add-on needs (only when it is installed: an
                                                   # install without it must not be told to fetch Node and Chromium)
  python3 lib/deps_check.py --hook-bash  # the bash 4+ that hook commands should name by its full path, or nothing

Always exit 0: a missing command is a warning, never a reason to stop an install. install.sh prints the block at its
start, check-install.py in its report. Without these commands nothing fails loudly: a hook under hook-safe.sh exits 127
and fails open, a lock "times out" - so the person never learns why a mechanism is quiet.
Each "what stops" names the callers a grep of the repo finds (comments and parsers of command lines left out).

bash: a stock macOS has /bin/bash 3.2 (no ${x,,}, no mapfile, an empty "${a[@]}" is an error under set -u). The scripts
are kept bash-3.2-safe (tests/bash3-compat-test.sh), but they are run every day on bash 4+, and a construct that slips
through stops its hook without a word. So: where the bash that runs the hooks is older than 4 and a newer one exists
(Homebrew: /opt/homebrew/bin/bash, /usr/local/bin/bash), install.sh writes that one by its full path into the hook
commands (--hook-bash); none found -> a "missing:" line. Where /bin/bash and the bash in PATH are 4+ (Linux, Git Bash)
nothing changes. Tests: CCM_BASH_PROBE = the bashes hooks may run under (colon-separated; default /bin/bash and the
bash in PATH), CCM_BASH_CANDIDATES = where to look for a newer one (default the bash in PATH, then Homebrew's).
"""
import json, os, shutil, subprocess, sys
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
# setsid), so nothing stops without them. timeout has one too (lib/ccm_compat.sh: gtimeout, else perl - a stock macOS
# has perl), so it is missing only when all three are.
ALTERNATIVES = {"timeout": ("gtimeout", "perl")}
DEPS = (
    ("timeout",
     f"hooks/hook-safe.sh runs {_wrapped_hooks()} (every gate, hint and Stop guard) with a time limit: without "
     "timeout, gtimeout or perl they run with none, so one hung hook holds up every prompt; also stop-dispatch.sh, "
     "cross-review.sh, memory_consolidation.sh and the quota_status.py cron line",
     "coreutils", "coreutils", "brew names it gtimeout: put \"$(brew --prefix)/opt/coreutils/libexec/gnubin\" first in PATH",
     "it comes with Git for Windows: run install.sh and Claude Code from Git Bash"),
    ("readlink -f",
     "almost every hook and script finds its own folder with `readlink -f \"$0\"` (a stock macOS has it from 13 on): "
     "without it they look for lib/ in the wrong place and fail - the hooks silently (hook-safe.sh fails open)",
     None, "coreutils", "or update macOS to 13 or newer",
     "it comes with Git for Windows: run install.sh and Claude Code from Git Bash"),
    ("crontab",
     "every scheduled job install.sh sets up (reminders, supervisor, quota, blockers, chat backup, journal checks): "
     "install.sh prints the lines to add to your scheduler by hand; library_check.py does not see cron scripts",
     "cron", None, "",
     "Windows has no cron: add the jobs to Task Scheduler (install.sh prints them and a schtasks line for the reminders)"),
)


# what an add-on needs, in the DEPS shape; checked only for the add-ons named with --addon. agent-browser: install.sh
# fetches its engine with npm (install-engine.sh), and the engine drives a Chrome/Chromium over remote debugging -
# without one br has nothing to drive (setup-agent-browser.sh --browser-service starts it, or your own Chrome + CCM_BR_CDP).
_CHROMES = ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome")   # the names setup-agent-browser.sh looks for
ADDON_DEPS = {
    "agent-browser": (
        ("node", "agent-browser add-on: npm needs it to fetch the browser engine (install-engine.sh), so br has no engine",
         "nodejs", "node", "", "winget install OpenJS.NodeJS.LTS, then open a new Git Bash"),
        ("npm", "agent-browser add-on: install-engine.sh fetches the engine with npm pack - without it br has no engine",
         "npm", "node", "", "it comes with Node.js: winget install OpenJS.NodeJS.LTS"),
        ("chromium", "agent-browser add-on: the engine drives a Chrome/Chromium over remote debugging - without one br "
         "has nothing to drive (setup-agent-browser.sh --browser-service runs it headless; or your own Chrome + CCM_BR_CDP)",
         "chromium", None, "Google Chrome from google.com/chrome, or brew install --cask chromium",
         "install Google Chrome, start it with --remote-debugging-port and set CCM_BR_CDP"),
    ),
}
ALTERNATIVES["node"] = ("nodejs",)   # Debian's older package named the binary nodejs
ALTERNATIVES["chromium"] = _CHROMES[1:]


def _chrome():
    if any(shutil.which(c) for c in _CHROMES):
        return True
    # a Mac has the browser as an app bundle, not on PATH
    return sys.platform == "darwin" and any(os.path.isdir(f"/Applications/{a}.app") for a in ("Google Chrome", "Chromium"))


def on_windows():
    return sys.platform == "win32" or bool(os.environ.get("MSYSTEM"))   # MSYSTEM: set by Git Bash (MINGW64)


def _readlink_f():
    if sys.platform != "darwin":   # GNU readlink (Linux) and Git Bash have -f; only a macOS before 13 lacks it
        return True
    try:
        return subprocess.run(["readlink", "-f", "/"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


PROBES = {"readlink -f": _readlink_f,   # a command that exists but may lack the option the scripts use
          "chromium": _chrome}


def missing(addons=()):
    want = DEPS + tuple(d for a in addons for d in ADDON_DEPS.get(a, ()))
    return [d for d in want if not (PROBES[d[0]]() if d[0] in PROBES
                                    else any(shutil.which(c) for c in (d[0],) + ALTERNATIVES.get(d[0], ())))]


def _paths(var, default):
    v = os.environ.get(var)
    return [p for p in (v.split(":") if v is not None else default) if p]


def bash_major(path):
    """the major version of the bash at path, or None (not there / not a bash)"""
    try:
        r = subprocess.run([path, "-c", 'echo "${BASH_VERSINFO[0]}"'], capture_output=True, text=True, timeout=10,
                           stdin=subprocess.DEVNULL)
        return int(r.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def old_hook_bashes():
    """[(path, major)] of the bashes hooks may run under that are older than 4"""
    out = []
    for p in dict.fromkeys(_paths("CCM_BASH_PROBE", ["/bin/bash", shutil.which("bash") or ""])):
        m = bash_major(p)
        if m is not None and m < 4:
            out.append((p, m))
    return out


def newer_bash():
    """the first bash 4+ among the candidates (its path as found: a Homebrew link survives upgrades), or "" """
    for p in dict.fromkeys(_paths("CCM_BASH_CANDIDATES", [shutil.which("bash") or "", "/opt/homebrew/bin/bash",
                                                          "/usr/local/bin/bash"])):
        if (bash_major(p) or 0) >= 4:
            return os.path.abspath(p)
    return ""


def hook_bash():
    """the bash install.sh should write into the hook commands: "" when the hooks' bash is already 4+ (Linux,
    Git Bash) or when there is no newer one (then block() names it)"""
    if on_windows() or not old_hook_bashes():
        return ""
    return newer_bash()


def bash_dep():
    """a DEPS-shaped entry when the hooks would run under bash < 4 and no newer bash exists, else None"""
    if on_windows():
        return None
    old = old_hook_bashes()
    if not old or newer_bash():
        return None
    which = ", ".join(f"{p} is {m}.x" for p, m in old)
    return ("bash 4+",
            f"{which} (a stock macOS) and no newer bash was found: the hooks and scripts are kept bash-3.2-safe, but "
            "they are run every day on bash 4+ - a construct that slips through (${x,,}, mapfile, an empty \"${a[@]}\" "
            "under set -u) stops its hook without a word (hook-safe.sh fails open: no briefing, no letters, no gate). "
            "After installing it re-run ./install.sh: the hook commands then start that bash by its full path",
            None, "bash coreutils", "coreutils: GNU date, stat, timeout - the branch of each script that runs everywhere else", "")


def block(addons=()):
    """lines to print; [] when nothing is missing. addons: names from ADDON_DEPS whose needs are checked too"""
    miss = missing(addons)
    b = bash_dep()
    if b:
        miss.append(b)
    if not miss:
        return []
    lines = [f"missing: {cmd} — {why}" for cmd, why, *_ in miss]
    if on_windows():
        lines += [f"install (Windows, {cmd}): {win}" for cmd, *_, win in miss]
        return lines
    apt = " ".join(dict.fromkeys(d[2] for d in miss if d[2]))
    brew = " ".join(dict.fromkeys(w for d in miss if d[3] for w in d[3].split()))
    notes = "; ".join(d[4] for d in miss if d[4])
    lines.append("install: " + " / ".join(x for x in (f"apt install {apt}" if apt else "", f"brew install {brew}" if brew else "") if x)
                 + (f" ({notes})" if notes else ""))
    return lines


if __name__ == "__main__":
    if sys.argv[1:] == ["--hook-bash"]:
        hb = hook_bash()
        if hb:
            print(hb)
        sys.exit(0)
    args, addons = sys.argv[1:], []
    if args[:1] in (["-h"], ["--help"]):
        print("\n\n".join(__doc__.split("\n\n")[:2])); sys.exit(0)
    while args[:1] == ["--addon"] and len(args) >= 2:
        addons.append(args[1]); args = args[2:]
    if args or any(a not in ADDON_DEPS for a in addons):
        # a typo must not look like "nothing missing"; still exit 0 (never a reason to stop an install)
        print(f"deps_check.py: usage: [--addon {'|'.join(ADDON_DEPS)}]... | --hook-bash (got {' '.join(sys.argv[1:])})")
        sys.exit(0)
    out = block(addons)
    if out:
        print("\n".join(out))
    sys.exit(0)
