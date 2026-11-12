#!/usr/bin/env python3
"""releaser.py - one release queue for all projects: a program run by cron, not an agent.
Only for projects that have their own git repo (<workspace>/Project-<X>/.git). Per-project file release.toml:

  hq = "X-HQ"                    # the lead agent: letters about breakage go here
  test = "npm test"              # the gate: exit 0 = green
  deploy_test = "npm run build"  # optional: roll out to the test stand after the merge
  stands = ["test", "show"]      # for humans and dashboards
  links = ["node_modules"]       # optional: paths taken as read-only symlinks from the project dir (not in git)
  timeout_min = 30

Why it is built this way: two owners in one working tree break everything (the shared tree gets half-written
files, wrong owners, a gate that "fixed" something). So the gates and the deploy run as a SEPARATE system user
(default `releaser`) in its OWN clone, <state>/work/<Project>; that user physically cannot write into the shared
tree or the agents' worktrees. Root is not needed to run gates; what truly needs it (a service restart) is a
narrow sudoers line for ONE command that deploy_test calls (see setup-releaser.sh --sudo-cmd).
The only write into the shared tree: a green commit is fetched from the clone and fast-forwarded into master by
the tree's owner. Without that master does not move. The queue lives outside the tree: <state>/queue/<Project>/.

Cycle per project (flock: a slow project does not hold the rest): the oldest marker <branch>.ready {sha, agent,
summary} -> clone synced to origin/master -> merge sha -> test -> green: ff-only into master -> deploy_test ->
letter to the author, marker removed. Red: master untouched, <marker>.failed, one letter per sha+step; that sha is
not run again. Master moved during the gate -> the same marker is taken next pass, gates re-run.
Commands from release.toml run only after a root `approve` (anybody who can write the repo can edit the toml).
State of the last run per project: <state>/<Project>.json (dashboards, project_drift.py).

  releaser.py run [<project>]               - cron: all projects / one
  releaser.py approve <project>             - root only: show and allow the commands from the toml
  releaser.py ready <agent> "<what is done>" - from the agent's own worktree: put a marker on the committed HEAD
  releaser.py status                        - state of all projects
exit codes: 0 ok · 2 usage · 4 not found · 5 not root · 6 `ready` refused

Settings (methodology.conf or env): CCM_WORKSPACE, CCM_PROJECTS_GLOB (default Project-*), CCM_RELEASER_STATE
(default /var/lib/ccm-release), CCM_RELEASER_USER (default releaser), CCM_RELEASER_OWNER (owner of the shared
tree; default: the owner of the workspace folder), CCM_RELEASER_LOG, CCM_RELEASER_APPROVED, CCM_INBOX_POST.
Test: tests/releaser-test.sh
"""
import fcntl, glob, hashlib, json, os, pwd, re, shutil, signal, subprocess, sys, tempfile, time, tomllib

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf

os.environ["PATH"] = "/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"
REPO = conf("CCM_WORKSPACE")
GLOB = conf("CCM_PROJECTS_GLOB", "Project-*")
PREFIX = GLOB.split("*")[0]                                       # "Project-": short name = name without it
STATE = conf("CCM_RELEASER_STATE", "/var/lib/ccm-release")
LOG = conf("CCM_RELEASER_LOG", os.path.join(STATE, "releaser.log"))
APPROVED = conf("CCM_RELEASER_APPROVED", os.path.join(STATE, "approved-checks.json"))   # root only, 0600
POST = conf("CCM_INBOX_POST", os.path.join(HERE, "inbox_post.sh"))
RUN_USER = conf("CCM_RELEASER_USER", "releaser")                  # gates and deploy run as this user
SHA = re.compile(r"[0-9a-f]{40}")
UPLOAD = "/usr/bin/git -c safe.directory=* upload-pack"


def _owner():
    o = conf("CCM_RELEASER_OWNER", "")
    if o:
        return o
    try:
        return pwd.getpwuid(os.stat(REPO).st_uid).pw_name
    except (OSError, KeyError):
        return pwd.getpwuid(os.geteuid()).pw_name


OWNER = _owner()                                                  # owns the shared tree and writes into it


def now():
    return time.strftime("%Y-%m-%d %H:%M")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{now()} {msg}\n")
    except OSError:
        pass


# ---- approvals: the set of commands root has looked at (a separate file the repo writers cannot edit) ----

def check_key(project_dir, cmd):
    return hashlib.sha256(f"{os.path.basename(project_dir)}\0{cmd}".encode()).hexdigest()


def load_approved():
    empty = {"checks": {}}
    try:
        st = os.stat(APPROVED)
        if st.st_uid != 0 or st.st_mode & 0o077:
            log(f"{APPROVED}: not root:0600 - treating every command as unapproved")
            return empty
        d = json.load(open(APPROVED, encoding="utf-8"))
        return {"checks": d.get("checks") or {}}
    except FileNotFoundError:
        return empty
    except (OSError, ValueError) as e:
        log(f"{APPROVED} unreadable: {e}")
        return empty


def update_approved(fn):
    os.makedirs(os.path.dirname(APPROVED), exist_ok=True)
    with open(APPROVED + ".lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        d = load_approved()
        fn(d)
        tmp = f"{APPROVED}.tmp{os.getpid()}"
        with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=0)
        os.replace(tmp, APPROVED)


# ---- running things as another user ----

def _me():
    return pwd.getpwuid(os.geteuid()).pw_name


def _as(user, argv):
    """argv as `user`: directly if that is already us, else through runuser (needs root)."""
    if user == _me():
        return argv
    return [shutil.which("runuser") or "/usr/sbin/runuser", "-u", user, "--", *argv]


def git_as(user, repo, *a):
    p = subprocess.run(_as(user, ["env", f"HOME={repo}", "/usr/bin/git", "-c", "safe.directory=*", "-C", repo, *a]),
                       capture_output=True, text=True, errors="replace", timeout=600, cwd="/")
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def shared(repo, *a):
    return git_as(OWNER, repo, *a)


def run_cmd(cmd, cwd, timeout):
    """-> (rc, output tail). Own process group: a timeout kills the children too. rc 124 = timeout."""
    with tempfile.TemporaryFile() as out:
        p = subprocess.Popen(_as(RUN_USER, ["env", f"HOME={cwd}", "bash", "-c", cmd]), cwd=cwd, stdout=out,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            rc = p.wait(timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL); p.wait(); rc = 124
        out.seek(0, 2); out.seek(max(0, out.tell() - 1500))
        return rc, " ".join(out.read().decode("utf-8", "replace").split())[-700:]


def post(who, text):
    if not who:
        return
    try:
        p = subprocess.run([POST, who], input=f"- [ ] [{now()}] releaser · {text}\n", text=True, capture_output=True, timeout=30)
        if p.returncode:
            log(f"letter to {who} not sent: {p.stderr[:200]}")
    except (OSError, subprocess.SubprocessError) as e:
        log(f"letter to {who} not sent: {e}")


class Project:
    def __init__(self, toml_path):
        self.dir = os.path.dirname(toml_path)
        self.name = os.path.basename(self.dir)
        self.short = self.name[len(PREFIX):] if self.name.startswith(PREFIX) else self.name
        with open(toml_path, "rb") as f:
            self.c = tomllib.load(f)
        if not os.path.exists(os.path.join(self.dir, ".git")):
            raise ValueError("no repo of its own: the releaser works only with <Project>/.git")
        self.queue = os.path.join(STATE, "queue", self.name)
        self.work = os.path.join(STATE, "work", self.name)
        self.timeout = int(self.c.get("timeout_min", 30)) * 60
        self.hq = self.c.get("hq", "")

    def commands(self):
        return [self.c[k] for k in ("test", "deploy_test") if self.c.get(k)]

    def key(self, cmd):
        return check_key(self.dir, f"release:{RUN_USER}:{cmd}")

    def unapproved(self):
        ok = load_approved()["checks"]
        return [c for c in self.commands() if self.key(c) not in ok]

    def markers(self):
        """oldest first"""
        return sorted(glob.glob(os.path.join(self.queue, "*.ready")), key=lambda m: (os.path.getmtime(m), m))


def read_marker(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def failed_fp(marker):
    try:
        return open(marker + ".failed", encoding="utf-8").read().split("\n")[1]
    except (OSError, IndexError):
        return ""


def save_state(p, result, **kw):
    try:
        tmp = os.path.join(STATE, f".{p.name}.tmp{os.getpid()}")
        json.dump({"project": p.name, "at": now(), "ts": int(time.time()), "result": result, **kw},
                  open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.chmod(tmp, 0o644); os.replace(tmp, os.path.join(STATE, f"{p.name}.json"))
    except OSError as e:
        log(f"{p.name}: state not written: {e}")


def fail(p, marker, sha, agent, step, why):
    """master was not touched. One letter per sha+step: a repeat without changes does not spam."""
    log(f"{p.name} RED {os.path.basename(marker)} {sha[:9]} [{step}]: {why[:300]}")
    fp = f"{sha}|{step}"
    told = failed_fp(marker) == fp
    with open(marker + ".failed", "w", encoding="utf-8") as f:
        f.write(f"{now()}\n{fp}\n{why}\n")
    save_state(p, "red", marker=os.path.basename(marker), sha=sha, agent=agent, step=step, detail=why[-400:])
    if not told:
        post(agent or p.hq, f"{p.short}: {os.path.basename(marker)} {sha[:9]} NOT merged ({step}), master unchanged. {why[-400:]}")


def drop_marker(marker, sha):
    """only if that sha is still there: the author may have put a new one during the run"""
    if read_marker(marker).get("sha") == sha:
        os.remove(marker)
    if os.path.exists(marker + ".failed"):
        os.remove(marker + ".failed")


def rgit(p, *a):
    return git_as(RUN_USER, p.work, *a)


def sync_copy(p):
    """the releaser's clone on a fresh origin/master, no traces of the previous run. RuntimeError = infrastructure, not the author's fault."""
    if not os.path.exists(os.path.join(p.work, ".git")):
        os.makedirs(p.work, exist_ok=True)
        if RUN_USER != _me():
            shutil.chown(p.work, user=RUN_USER)
        rc, _, err = rgit(p, "clone", "-q", "--no-hardlinks", "--no-checkout", "-u", UPLOAD, p.dir, ".")
        if rc:
            raise RuntimeError(f"clone: {err[:300]}")
        for k, v in (("remote.origin.uploadpack", UPLOAD), ("user.name", "Releaser"), ("user.email", "releaser@localhost")):
            rgit(p, "config", k, v)
    for a in (("fetch", "-q", "--prune", "origin", "+refs/heads/*:refs/remotes/origin/*"),
              ("merge", "--abort"), ("checkout", "-q", "-f", "--detach", "refs/remotes/origin/master"), ("clean", "-qfdx")):
        rc, _, err = rgit(p, *a)
        if rc and a[0] != "merge":
            raise RuntimeError(f"{a[0]}: {err[:300]}")


def ff_master(p, new):
    """-> None | "RETRY" | reason. Only the owner writes into the shared tree; a lock on the repo against snapshots and parallel delivery."""
    with open(os.path.join(STATE, f".{p.name}.ff.lock"), "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        rc, _, err = shared(p.dir, "fetch", "-q", "--upload-pack", UPLOAD, p.work, new)
        if rc:
            return f"could not fetch the commit from the releaser's clone: {err[:300]}"
        rc, _, err = shared(p.dir, "merge", "-q", "--ff-only", new)
    if rc == 0:
        return None
    if "index.lock" in err or shared(p.dir, "merge-base", "--is-ancestor", "master", new)[0]:
        return "RETRY"                                       # master moved during the gate: gates again on the new one
    return f"master did not accept the fast-forward: {err[:300]}"


def do_merge(p):
    for marker in p.markers():
        d = read_marker(marker)
        sha, agent = str(d.get("sha", "")), str(d.get("agent", ""))
        if not SHA.fullmatch(sha):
            fail(p, marker, sha or "none", agent, "marker", "the marker has no full sha")
            continue
        if failed_fp(marker).startswith(sha + "|"):
            continue                                         # this sha is already red: wait for a new one
        if shared(p.dir, "cat-file", "-e", f"{sha}^{{commit}}")[0]:
            fail(p, marker, sha, agent, "marker", "no such commit in the repo")
            continue
        if shared(p.dir, "merge-base", "--is-ancestor", sha, "master")[0] == 0:
            drop_marker(marker, sha); log(f"{p.name} already in master: {sha[:9]}")
            continue
        return release_one(p, marker, sha, agent, str(d.get("summary", "")))
    return None


def release_one(p, marker, sha, agent, summary):
    name = os.path.basename(marker)
    log(f"{p.name} START {name} {sha[:9]} ({agent})")
    msg = f"release: {name[:-6]} {sha[:9]} ({agent})\n\n{summary}"
    try:
        sync_copy(p)
        if rgit(p, "cat-file", "-e", f"{sha}^{{commit}}")[0]:
            return fail(p, marker, sha, agent, "marker", "the commit is not on a branch: the releaser's clone cannot see it")
        rc, out, err = rgit(p, "merge", "-q", "--no-ff", "--no-edit", "-m", msg, sha)
        if rc:
            rgit(p, "merge", "--abort")
            return fail(p, marker, sha, agent, "conflict", f"conflict with master: {(out or err)[:300]}")
        for l in p.c.get("links", []):
            if os.path.isabs(l) or ".." in l.split("/"):     # the toml is not approved as a whole: paths only inside the project
                log(f"{p.name}: links '{l}' is outside the project - skipped"); continue
            if os.path.exists(os.path.join(p.dir, l)) and not os.path.lexists(os.path.join(p.work, l)):
                os.symlink(os.path.join(p.dir, l), os.path.join(p.work, l))
        rc, tail = run_cmd(p.c["test"], p.work, p.timeout)
        if rc:
            return fail(p, marker, sha, agent, "gate", f"`{p.c['test']}` rc={rc}: {tail}")
        _, new, _ = rgit(p, "rev-parse", "HEAD")
        why = ff_master(p, new)
        if why == "RETRY":
            log(f"{p.name} {name}: master busy or moved during the gate - next pass")
            return save_state(p, "retry", marker=name, sha=sha, agent=agent)
        if why:
            return fail(p, marker, sha, agent, "ff", why)
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        log(f"{p.name} ERROR {name}: {e}")
        return save_state(p, "error", marker=name, sha=sha, agent=agent, detail=str(e)[:400])
    drop_marker(marker, sha)
    dep = p.c.get("deploy_test")
    if dep:
        rc, tail = run_cmd(dep, p.work, p.timeout)
        if rc:
            log(f"{p.name} master {new[:9]}, stand NOT updated rc={rc}: {tail[:300]}")
            save_state(p, "deploy_red", sha=sha, head=new, agent=agent, step="stand", detail=tail[-400:])
            post(agent, f"{p.short}: {sha[:9]} is already in master, but the roll-out to the stand failed (rc={rc}): {tail[-300:]}")
            post(p.hq, f"{p.short}: master {new[:9]}, roll-out to the stand failed (rc={rc}), author {agent}")
            return None
    log(f"{p.name} GREEN {name} {sha[:9]} -> master {new[:9]}")
    save_state(p, "green", sha=sha, head=new, agent=agent)
    post(agent, f"{p.short}: {sha[:9]} green, master {new[:9]}" + (", stand updated" if dep else ""))
    return None


def run_project(p):
    with open(os.path.join(STATE, f".{p.name}.lock"), "w") as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return                                           # the previous pass is still running
        if not p.markers():
            return
        try:
            pwd.getpwnam(RUN_USER)
        except KeyError:
            log(f"{p.name}: user {RUN_USER} does not exist - running nothing")
            return save_state(p, "error", detail=f"user {RUN_USER} does not exist")
        bad = p.unapproved()
        if bad:
            log(f"{p.name}: commands not approved {bad}")
            told = os.path.join(STATE, f".{p.name}.told")
            fp = check_key(p.dir, "\0".join(bad))
            if not os.path.exists(told) or open(told).read() != fp:
                post(p.hq, f"{p.short}: new commands in release.toml, not running them (they run without a human). "
                           f"Check the file, then `releaser.py approve {p.short}` as root")
                open(told, "w").write(fp)
            return save_state(p, "unapproved", detail="; ".join(bad)[:400])
        if not p.c.get("test"):
            return save_state(p, "error", detail="release.toml has no test")
        do_merge(p)


def projects(only=None):
    for path in sorted(glob.glob(os.path.join(REPO, GLOB, "release.toml"))):
        name = os.path.basename(os.path.dirname(path))
        if only and name not in (only, f"{PREFIX}{only}"):
            continue
        yield path


def cmd_run(only):
    """every project in its own process: a 15-minute gate of one does not hold the others"""
    for sub in ("queue", "work"):
        os.makedirs(os.path.join(STATE, sub), exist_ok=True)
    try:
        os.chmod(STATE, 0o755); os.chmod(os.path.join(STATE, "work"), 0o755)
    except OSError:
        pass
    kids = []
    for path in projects(only):
        pid = os.fork()
        if pid == 0:
            rc = 0
            try:
                run_project(Project(path))
            except Exception as e:                           # one project's broken toml does not take down the rest
                log(f"{path}: {type(e).__name__}: {e}"); rc = 1
            os._exit(rc)
        kids.append(pid)
    return max([os.waitstatus_to_exitcode(os.waitpid(k, 0)[1]) for k in kids] or [0])


def cmd_approve(only):
    if os.geteuid() != 0:
        print("only root can approve"); return 5
    paths = list(projects(only))
    if not paths:
        print(f"no release.toml in {only}"); return 4
    try:
        p = Project(paths[0])
    except ValueError as e:
        print(f"refused: {e}"); return 6
    for c in p.commands():
        update_approved(lambda d: d["checks"].__setitem__(p.key(c), {"project": p.name, "cmd": c, "user": RUN_USER, "at": now()}))
        print(f"approved, will run as {RUN_USER}: {c}")
        log(f"{p.name} APPROVED as {RUN_USER}: {c}")
    return 0


def cmd_ready(agent, summary):
    here = os.getcwd()
    rc, common, _ = shared(here, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if rc:
        print("refused: this is not a git repo"); return 6
    _, branch, _ = shared(here, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "master":
        print("refused: you are on master; the marker is put from your own worktree"); return 6
    name = os.path.basename(os.path.dirname(common))        # <Project>/.git for the repo itself and for its worktree
    src = next(iter(projects(name)), None)
    if not src:
        print(f"refused: {name}: no release.toml or no repo of its own, the releaser does not know this project"); return 6
    p = Project(src)
    _, dirty, _ = shared(here, "status", "--porcelain")
    if dirty:
        print(f"{dirty[:600]}\nMARKER NOT PLACED: the uncommitted files above would not be delivered"); return 6
    _, sha, _ = shared(here, "rev-parse", "HEAD")
    os.makedirs(p.queue, exist_ok=True)
    m = os.path.join(p.queue, re.sub(r"[^\w-]", "-", branch) + ".ready")
    tmp = m + ".tmp"
    json.dump({"branch": branch, "sha": sha, "agent": agent, "summary": summary,
               "ready_at": now()}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, m)
    print(f"ok {m} -> {sha}: the result comes as a letter, keep working")
    return 0


def cmd_status():
    for path in projects():
        name = os.path.basename(os.path.dirname(path))
        try:
            s = json.load(open(os.path.join(STATE, f"{name}.json"), encoding="utf-8"))
            print(f"{name}: {s['result']} {s['at']} {s.get('detail', '')[:120]}")
        except (OSError, ValueError):
            print(f"{name}: no runs yet")
    return 0


def main(a):
    if a[:1] == ["run"] and len(a) <= 2:
        return cmd_run(a[1] if len(a) == 2 else None)
    if a[:1] == ["approve"] and len(a) == 2:
        return cmd_approve(a[1])
    if a[:1] == ["ready"] and len(a) == 3:
        return cmd_ready(a[1], a[2])
    if a == ["status"]:
        return cmd_status()
    print(__doc__)
    return 2


if __name__ == "__main__":
    if sys.argv[1:2] != ["ready"]:
        os.chdir("/")                                       # cron starts in /root, closed to other users
    sys.exit(main(sys.argv[1:]))
