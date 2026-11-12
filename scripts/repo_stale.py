#!/usr/bin/env python3
"""repo_stale.py - a reminder to the owner of a project's own repo: the daily auto-snapshot no longer commits the code
of such repos, so uncommitted work can sit there with no safety net. Uncommitted files older than CCM_STALE_HOURS
(default 24) -> a letter to the project lead (hq from release.toml, else <Name>-HQ), once a day per project.
Only a letter, commits nothing. Run hourly from cron; dedup through a state file. exit code is always 0.
Settings: CCM_WORKSPACE, CCM_PROJECTS_GLOB (default Project-*), CCM_RELEASER_STATE (default /var/lib/ccm-release),
CCM_RELEASER_OWNER (who runs git on the shared tree; default: owner of the workspace), CCM_INBOX_POST, CCM_STALE_HOURS.
Test: tests/repo-stale-test.sh
"""
import glob, json, os, pwd, shutil, subprocess, sys, time, tomllib

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf

REPO = conf("CCM_WORKSPACE")
GLOB = conf("CCM_PROJECTS_GLOB", "Project-*")
PREFIX = GLOB.split("*")[0]
POST = conf("CCM_INBOX_POST", os.path.join(HERE, "inbox_post.sh"))
STATE_DIR = conf("CCM_RELEASER_STATE", "/var/lib/ccm-release")
STATE = conf("CCM_STALE_STATE", os.path.join(STATE_DIR, "repo-stale.json"))
LOG = conf("CCM_STALE_LOG", os.path.join(STATE_DIR, "releaser.log"))
HOURS = int(conf("CCM_STALE_HOURS", "24"))


def _owner():
    o = conf("CCM_RELEASER_OWNER", "")
    if o:
        return o
    try:
        return pwd.getpwuid(os.stat(REPO).st_uid).pw_name
    except (OSError, KeyError):
        return pwd.getpwuid(os.geteuid()).pw_name


OWNER = _owner()


def git_cmd():
    if OWNER == pwd.getpwuid(os.geteuid()).pw_name:
        return ["/usr/bin/git", "-c", "safe.directory=*"]
    return [shutil.which("runuser") or "/usr/sbin/runuser", "-u", OWNER, "--", "/usr/bin/git", "-c", "safe.directory=*"]


def log(m):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %H:%M')} repo_stale: {m}\n")
    except OSError:
        pass


def stale_files(d):
    out = subprocess.run(git_cmd() + ["-C", d, "status", "--porcelain", "-z", "--untracked-files=all", "--no-renames"],
                         capture_output=True, timeout=120)
    if out.returncode:
        raise RuntimeError(out.stderr.decode("utf-8", "replace")[:200])
    now, old = time.time(), []
    for e in out.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if len(e) < 4:
            continue
        try:
            if now - os.path.getmtime(os.path.join(d, e[3:])) > HOURS * 3600:
                old.append(e[3:])
        except OSError:
            continue              # a deleted file: when - unknown
    return old


def hq_of(d):
    try:
        with open(os.path.join(d, "release.toml"), "rb") as f:
            hq = tomllib.load(f).get("hq")
        if hq:
            return hq
    except (OSError, ValueError):
        pass
    name = os.path.basename(d)
    return f"{name[len(PREFIX):] if name.startswith(PREFIX) else name}-HQ"


def main():
    try:
        told = json.load(open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        told = {}
    today, sent = time.strftime("%F"), 0
    for g in sorted(glob.glob(os.path.join(REPO, GLOB, ".git"))):
        d = os.path.dirname(g); name = os.path.basename(d)
        if told.get(name) == today:
            continue
        try:
            old = stale_files(d)
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            log(f"{name}: could not read the state: {e}"); continue
        if not old:
            continue
        safe = [f.encode("utf-8", "replace").decode() for f in old[:8]]
        p = subprocess.run([POST, hq_of(d)], input=f"- [ ] [{time.strftime('%F %H:%M')}] reminder · {name}: {len(old)} uncommitted files "
                           f"older than {HOURS} h; the auto-snapshot does not protect them, commit or remove them: {', '.join(safe)}\n",
                           text=True, capture_output=True, timeout=30)
        if p.returncode:
            log(f"{name}: letter to {hq_of(d)} not sent: {p.stderr[:200]}"); continue
        told[name] = today; sent += 1
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(told, open(tmp, "w")); os.replace(tmp, STATE)
    print(f"letters {sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
