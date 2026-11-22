#!/usr/bin/env python3
"""The crontab block of install.sh as Windows Task Scheduler tasks, one task per line, named ccm-<job>.

    win_schedule.py plan|apply --target <install dir> --bash <bash.exe, Windows path> --env <lib/pyshim/env.sh> --home <HOME>
        (the crontab lines on stdin)
    win_schedule.py uninstall [--dry-run]

plan     prints the schtasks commands, runs nothing.
apply    writes one small job script per line into <install dir>/schedule/ccm-<job>.sh, creates (or replaces, /F) the
         task for each, and deletes the ccm-* tasks that are no longer in the block (a job switched off on a re-run).
uninstall deletes every ccm-* task of this Windows user.

Why a job script and not the command itself in /TR: schtasks takes at most 261 characters there, and a crontab line
with its full paths and redirections is longer and full of quotes. The task runs
    conhost.exe --headless "<bash.exe>" -l "<install dir>/schedule/ccm-<job>.sh"
conhost --headless: without it a console window flashes up every minute. bash -l: Git Bash's own PATH (coreutils).
The script sets HOME to the install-time home (MSYS2 may give a task /home/<user>, not the Windows profile) and sources
env.sh (python3 = the real Python), then runs the crontab command unchanged.
Python calls schtasks itself, with an argument list: Git Bash would turn "/Create" into a path (MSYS path conversion).
CCM_SCHTASKS = the command to call instead of schtasks (tests: a stand-in that only logs its arguments).
Schedules: * * * * * / */N -> every N minutes; M * * * * -> hourly at :M; M H * * * -> daily; M H * * D -> weekly;
@reboot -> at logon (Windows may ask for an elevated prompt for that one; refused = a warning, the rest stands).
One set of ccm-* tasks per Windows user: a second install (another scope) replaces the first one's tasks.
"""
import argparse, os, re, shlex, subprocess, sys

PREFIX = "ccm-"
DAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]


def schtasks():
    return shlex.split(os.environ.get("CCM_SCHTASKS", "")) or ["schtasks"]


def schedule(fields):
    """crontab time fields -> schtasks /SC ... arguments, or None when Task Scheduler has no plain equivalent."""
    if fields[0] == "@reboot":
        return ["/SC", "ONLOGON"]
    mi, h, dom, mon, dow = fields
    if (dom, mon) != ("*", "*"):
        return None
    if h == "*" and dow == "*":
        if mi == "*":
            return ["/SC", "MINUTE", "/MO", "1"]
        m = re.fullmatch(r"\*/(\d+)", mi)
        if m:
            return ["/SC", "MINUTE", "/MO", m.group(1)]
        if mi.isdigit():
            return ["/SC", "HOURLY", "/MO", "1", "/ST", f"00:{int(mi):02d}"]
        return None
    if mi.isdigit() and h.isdigit():
        st = ["/ST", f"{int(h):02d}:{int(mi):02d}"]
        if dow == "*":
            return ["/SC", "DAILY"] + st
        if dow.isdigit() and int(dow) <= 7:
            return ["/SC", "WEEKLY", "/D", DAYS[int(dow) % 7]] + st
    return None


def jobs(lines, target):
    """(name, schedule args, command, the line) for every crontab line; the name comes from the job's script."""
    out, seen = [], set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1 if line.startswith("@") else 5)
        if len(parts) < 2:
            continue
        fields, cmd = parts[:-1], parts[-1]
        sc = schedule(fields)
        paths = re.findall(re.escape(target) + r"/[^\s'\"]+", cmd)
        # the job is the last script on the line (not a log file it writes, not the bin/catchup-run that wraps it)
        paths = [p for p in paths if p.endswith((".py", ".sh"))] or [p for p in paths if "/bin/" in p] or paths
        base = os.path.splitext(os.path.basename(paths[-1]))[0] if paths else "job"
        name = PREFIX + re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
        if name in seen:   # the same script twice (trash-guard --measure, --clean): its first --option tells them apart
            opt = re.search(re.escape(paths[-1]) + r"['\"]?\s+--([a-z-]+)", cmd) if paths else None
            name += "-" + (opt.group(1) if opt else str(len(seen)))
        seen.add(name)
        out.append((name, sc, cmd, line))
    return out


def run(argv, dry):
    print("  " + subprocess.list2cmdline(argv))   # as cmd.exe / PowerShell take it (Windows quoting, not POSIX)
    if dry:
        return 0
    r = subprocess.run(argv, capture_output=True, text=True)
    if r.returncode:
        print(f"  ! {argv[1]} {argv[3] if len(argv) > 3 else ''}: rc {r.returncode} {(r.stderr or r.stdout).strip()[:300]}", file=sys.stderr)
    return r.returncode


def ours():
    """names of this user's ccm-* tasks (schtasks /Query /FO CSV /NH: "\\name","next run","status")"""
    r = subprocess.run(schtasks() + ["/Query", "/FO", "CSV", "/NH"], capture_output=True, text=True)
    names = set()
    for row in (r.stdout or "").splitlines():
        first = row.split(",", 1)[0].strip().strip('"').lstrip("\\")
        if first.lower().startswith(PREFIX):
            names.add(first)
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["plan", "apply", "uninstall"])
    ap.add_argument("--target"); ap.add_argument("--bash"); ap.add_argument("--env"); ap.add_argument("--home")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.action == "uninstall":
        names = sorted(ours())
        print(f"Task Scheduler: removing {len(names)} ccm-* task(s)")
        bad = sum(run(schtasks() + ["/Delete", "/TN", n, "/F"], a.dry_run) != 0 for n in names)
        return 1 if bad else 0
    target = a.target.rstrip("/")
    todo = jobs(sys.stdin.read().splitlines(), target)
    jobdir = f"{target}/schedule"
    dry = a.action == "plan"
    if not dry:
        os.makedirs(jobdir, exist_ok=True)
    print(("Task Scheduler - would run (install.sh --schedule-windows registers them):" if dry
           else "Task Scheduler: registering the scheduled jobs as ccm-* tasks"))
    bad = 0
    for name, sc, cmd, line in todo:
        if sc is None:
            print(f"  ! {name}: no Task Scheduler equivalent for \"{line[:60]}\" - not registered", file=sys.stderr)
            bad += 1
            continue
        if sc[1] == "ONLOGON":   # "@reboot sleep N && <cmd>": the logon trigger takes the wait as its delay
            m = re.match(r"sleep (\d+) && (.*)", cmd)
            if m:
                s = int(m.group(1)); cmd = m.group(2); sc = sc + ["/DELAY", f"{s // 60:04d}:{s % 60:02d}"]
        job = f"{jobdir}/{name}.sh"
        if not dry:
            with open(job, "w", encoding="utf-8", newline="\n") as f:
                f.write("#!/usr/bin/env bash\n"
                        f"# {name}: written by install.sh --schedule-windows from the crontab line:\n# {line}\n"
                        f"export HOME={shlex.quote(a.home)}\n"
                        f". {shlex.quote(a.env)} 2>/dev/null\n"
                        f"{cmd}\n")
        tr = f'conhost.exe --headless "{a.bash}" -l "{job}"'
        if len(tr) > 261:
            print(f"  ! {name}: the task command is {len(tr)} characters, schtasks takes 261 - not registered", file=sys.stderr)
            bad += 1
            continue
        bad += run(schtasks() + ["/Create", "/F", "/TN", name, "/TR", tr] + sc, dry) != 0
    if not dry:   # a job that left the block (switched off on this run) leaves Task Scheduler too
        for n in sorted(ours() - {j[0] for j in todo}):
            bad += run(schtasks() + ["/Delete", "/TN", n, "/F"], False) != 0
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
