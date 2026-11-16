#!/usr/bin/env python3
"""code-pitfalls-hint — show already-paid-for lessons BEFORE touching code.

PreToolUse on Edit|Write: by the file's extension/path → inject ONLY the headings (### …) of the matching
code-pitfalls/<topic>.md plus its path. The bodies stay out of context; the agent opens the file if a heading looks
like its case. PreToolUse on Bash: flock/lock files → concurrency.md; git → git.md; ssh/scp/qemu → vm.md;
adb → android.md; a network/service change (netplan apply, ip … add/del/set, nmcli … modify/up/down, resolvectl dns,
systemctl restart networking/systemd-networkd/NetworkManager, a write into resolv.conf/netplan/interfaces) → services.md,
reading them (ip a, ip route show, systemctl status) stays silent. Edit|Write: .service/.timer and those network config
files → services.md; new text that takes a lock or spawns threads also gets concurrency.md.
Text inside a Bash command is not a command: heredoc bodies and quoted strings are cut before matching (an agent
writing a letter that mentions ssh got the vm lessons), except the argument of `bash -c "…"`, which IS a command.

With the headings come:
  - the coding standard's version and path (CCM_CODING_STANDARD) — the agent sees the standard changed without
    opening it;
  - under a project folder (CCM_PROJECTS_GLOB in the workspace), the project-work rules if the workspace has them;
  - for web files, the web playbook if the workspace has one.
Two more hints, independent of the topics:
  - an Edit/Write of a LIVE mechanism script (the installed hooks/ and scripts/, which cron or a hook may be running
    right now) → "write <file>.new → test → swap-live <file>.new". An in-place edit breaks a bash script mid-run.
  - an Edit/Write in a project (or of a live script) that a decision record mentions → the record's title, and the
    project's ARCHITECTURE.md if there is one: agents changed things "the convenient way" when a decision about that
    very thing already existed.
And one silent journal: issue-first. A code edit in a project without a task taken (scripts/take_task.sh) → a line in
~/.claude/issue-first.log. Nothing is shown and nothing is blocked: it is a detector at the calibration stage (measure
a few hundred turns, then decide whether to block). Writes via Bash count too — but only when the project path is
the TARGET of the write (> file, sed -i, tee, cp/mv, open(…,'w')), not any path mentioned: reading data/graph.json in a
heredoc was logged as 33 false "edits" before that rule.

Pitfall files are read at runtime, so agents append new lessons without anyone touching this hook.
Dedup: topic × session × hour (an O_EXCL marker in /tmp). Blocks nothing; fail-open (run it under hook-safe.sh).

Why: the same technical mistakes kept recurring across agents and projects — `pkill -f` killing its own shell, a
shared file written without a lock, a fixed `sleep` racing an event of variable length. Lessons written in a
postmortem are read by nobody at the moment they matter; a heading shown right before the edit is.

Config: CODE_PITFALLS_DIR (default <install>/code-pitfalls), CCM_CODING_STANDARD, CCM_WORKSPACE, CCM_PROJECTS_GLOB,
CCM_DECISIONS_DIR (default <workspace>/decisions), CPH_ISSUE_LOG, CPH_TASK_STATE (tests). Format of the pitfall
files: see code-pitfalls/README.md.
"""
import fnmatch, glob, json, os, re, sys, time, zlib

HERE = os.path.dirname(os.path.realpath(__file__))
INSTALL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(INSTALL, "lib"))
from ccm_conf import conf  # noqa: E402

CLAUDE_DIR = conf("CCM_CLAUDE_DIR", INSTALL).rstrip("/")
ROOT = os.environ.get("CODE_PITFALLS_DIR") or os.path.join(CLAUDE_DIR, "code-pitfalls")
WS = conf("CCM_WORKSPACE", os.path.expanduser("~/claude-projects")).rstrip("/")
STANDARD = conf("CCM_CODING_STANDARD", "") or os.path.join(WS, "CODING-STANDARD.md")
PROJECT_WORK = os.path.join(WS, "PROJECT-WORK.md")
WEB_PLAYBOOK = os.path.join(WS, "WEB-playbook.md")
DECISIONS = conf("CCM_DECISIONS_DIR", "") or os.path.join(WS, "decisions")
PGLOB = conf("CCM_PROJECTS_GLOB", "Project-*")
LIVE_DIRS = (f"{CLAUDE_DIR}/hooks/", f"{CLAUDE_DIR}/scripts/")
ISSUE_LOG = os.environ.get("CPH_ISSUE_LOG", os.path.expanduser("~/.claude/issue-first.log"))
TASK_STATE = os.environ.get("CPH_TASK_STATE", os.path.expanduser("~/.claude/task-taken"))
CYCLE = ("The change cycle: three failed fixes of one spot → search how others do it; "
         "\"done\" only with the output of a run.")


def project_of(path):
    """→ (project folder name, path up to and including it) when path lies in a project of the workspace, or its git
    worktree (<workspace>-wt/<agent>/<project>/…); else (None, None)."""
    for root in (WS + "/", WS + "-wt/"):
        if not path.startswith(root):
            continue
        parts = path[len(root):].split("/")
        if root.endswith("-wt/"):
            parts = parts[1:]   # <agent>/
            pre = path[:len(root)] + path[len(root):].split("/")[0] + "/"
        else:
            pre = root
        if len(parts) > 1 and fnmatch.fnmatch(parts[0], PGLOB):
            return parts[0], pre + parts[0]
    return None, None


def topics_for_file(fp):
    t = []
    low = fp.lower()
    ext = os.path.splitext(low)[1]
    if ext == ".sh" or "/cron" in low:
        t.append("shell")
    if ext == ".py":
        t.append("python")
    if ext in (".html", ".htm", ".js", ".css"):
        t.append("web")
    if ext in (".ps1", ".psm1", ".cmd", ".bat"):
        t.append("windows")
    if ext in (".service", ".timer") or low.startswith(NET_FILES):
        t.append("services")
    if fp.startswith(LIVE_DIRS) or "/.claude/hooks/" in low or "/.claude/scripts/" in low \
            or low.endswith("/settings.json") or low.endswith("/settings.local.json"):
        t.append("hooks")
    if t:
        t.append("verification")   # any code change: how to prove it works
    return t


CONCURRENCY = re.compile(r"\bflock\b|\bfcntl\b|O_EXCL|\.lock\b|\bthreading\b|\bmultiprocessing\b")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", re.S | re.M)
DASH_C = re.compile(r"(\s-c\s+)(['\"])(.*?)\2", re.S)
QUOTED = re.compile(r"'[^'\n]*'|\"(?:[^\"\\\n]|\\.)*\"")


# network and service changes: the commands that change them and the files that hold the config. Reading them
# (`ip a`, `ip route show`, `systemctl status`, `resolvectl status`, `nmcli dev status`) stays silent.
NET_FILES = ("/etc/resolv.conf", "/etc/netplan/", "/etc/network/interfaces", "/etc/systemd/network/", "/etc/systemd/resolved.conf")
NET_CMD = re.compile(
    r"(?:^|[\s;&|(])(?:"
    r"netplan\s+(?:apply|try)\b"
    r"|ip\s+(?:-\S+\s+)*(?:a|ad|addr|address|r|ro|route|l|li|link|n|neigh|rule)\s+(?:add|del|delete|change|replace|set|flush|append)\b"
    r"|nmcli\b[^;&|\n]*\s(?:modify|mod|up|down|delete|del|add|reload)\b"
    r"|resolvectl\s+(?:dns|domain|default-route|revert|llmnr|mdns|dnssec|dnsovertls)\b"
    r"|systemctl\s+(?:-\S+\s+)*(?:restart|stop|reload|try-restart|reload-or-restart|disable|mask|kill)\s+"
    r"(?:[^;&|\n]*\s)?(?:networking|systemd-networkd|NetworkManager|systemd-resolved)(?:\.service)?\b"
    r"|service\s+(?:networking|network-manager|NetworkManager|systemd-networkd)\s+(?:restart|stop|reload)\b"
    r"|ifdown\b|ifup\b)")
_NF = "(?:" + "|".join(re.escape(p) for p in NET_FILES) + r")[^\s;&|]*"
NET_WRITE = re.compile(r"(?:(?<![0-9&])>{1,2}\s*|\btee\s+(?:-a\s+)?|\bsed\s+-i\S*\s[^;&|\n]*?)" + _NF
                       + r"|\b(?:cp|mv|install|ln)\b[^;&|\n]*\s" + _NF + r"\s*(?=$|[;&|\n])", re.M)   # cp/mv/ln: only the LAST argument (a backup copy FROM it is the right move)


def net_change(cmd):
    """a command that changes the network or a network service, or writes one of its config files"""
    return bool(NET_CMD.search(strip_text(cmd)) or NET_WRITE.search(HEREDOC.sub(" ", cmd)))


def strip_text(cmd):
    """Heredoc bodies and quoted strings are TEXT, not commands. Except `-c "…"` (bash/sh/su/runuser -c): unwrapped."""
    cmd = HEREDOC.sub(" ", cmd)
    cmd = DASH_C.sub(lambda m: m.group(1) + m.group(3), cmd)
    return QUOTED.sub(" ", cmd)


def topics_for_cmd(cmd):
    t = ["services"] if net_change(cmd) else []   # first: the costliest lesson
    cmd = strip_text(cmd)
    if CONCURRENCY.search(cmd):
        t.append("concurrency")
    if re.search(r"(^|[\s;&|(])git\s", cmd):
        t.append("git")
    if re.search(r"(^|[\s;&|(])(ssh|scp)\s|qemu-", cmd):
        t.append("vm")
    if re.search(r"(^|[\s;&|(])adb(\.exe)?\s", cmd):
        t.append("android")
    return t



def headings(topic):
    try:
        with open(os.path.join(ROOT, f"{topic}.md"), encoding="utf-8") as f:
            return [l[4:].strip() for l in f if l.startswith("### ")]
    except OSError:
        return []


def once(mark):
    """True the first time this marker is taken (O_EXCL: parallel tool calls can't both pass)."""
    try:
        os.close(os.open(mark, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        return False


# `git reset --soft main` to squash your own commits, when main has moved since you branched: HEAD becomes the new main,
# the files stay from the old base - the next commit silently reverts the commits others merged meanwhile
# (code-pitfalls/git.md). Points to the merge-base instead; a hash, HEAD~N or $(...) is left alone.
GIT_RESET_SOFT = re.compile(r"\bgit\b[^;&|\n]*\breset\s+(?:-q\s+)?--soft\s+(?:-q\s+)?(?!HEAD\b|[0-9a-f]{7,40}\b|\$\()([\w./-]+)")


def git_reset_hint(cmd, sid, hour):
    m = GIT_RESET_SOFT.search(cmd)
    if not m or not once(f"/tmp/cph-{sid}-gitreset-{hour}"):
        return ""
    b = m.group(1)
    return (f"`reset --soft {b}`: if {b} moved after you branched, HEAD becomes the new {b} while your files stay from the "
            f"old base - the next commit silently reverts the commits merged meanwhile. To squash your own commits: "
            f"`git reset --soft $(git merge-base HEAD {b})`. Before handing over: `git diff --stat {b}...HEAD` - only your files?\n")


def live_script_hint(tool, ti, sid, hour):
    """An Edit/Write of a LIVE mechanism script → change it via swap-live. A hint, not a block; once per file × hour."""
    if tool not in ("Edit", "Write"):
        return ""
    fp = ti.get("file_path", "") or ""
    if not fp.startswith(LIVE_DIRS) or fp.endswith(".new") or not os.path.isfile(fp):
        return ""
    if not once(f"/tmp/cph-{sid}-live-{zlib.crc32(fp.encode()):08x}-{hour}"):   # crc32, not hash(): stable across runs
        return ""
    return (f"{os.path.basename(fp)} is a LIVE script (cron or a hook may be running it right now): an in-place edit "
            f"breaks bash mid-run. Write {fp}.new → test it → `swap-live {fp}.new` (syntax check, permissions, "
            "atomic mv).\n")


def decisions_line(fp, sid, hour):
    """Edit/Write → decision records that mention this file or its project, + the project's ARCHITECTURE.md.
    Titles only; once per project × hour."""
    proj, pre = project_of(fp)
    base = os.path.basename(fp)
    if not proj and not fp.startswith(LIVE_DIRS):
        return ""
    hits = []
    for f in sorted(glob.glob(os.path.join(DECISIONS, "[0-9]*.md")), reverse=True):
        if os.path.basename(f).startswith("0000"):
            continue   # the template
        try:
            t = open(f, encoding="utf-8", errors="replace").read(20000)
        except OSError:
            continue
        if re.search(r"\*\*Status:\*\*\s*(?:replaced|cancel|superseded)|\*\*Статус:\*\*\s*скасован", t, re.I):
            continue
        if base in t or (proj and proj in t):
            hits.append(f"{os.path.basename(f)} — {t.split(chr(10), 1)[0].lstrip('# ').strip()[:110]}")
    arch = os.path.join(pre, "ARCHITECTURE.md") if proj else ""
    if not hits and not (arch and os.path.isfile(arch)):
        return ""
    if not once(f"/tmp/cph-{sid}-adr-{zlib.crc32((proj or base).encode()):08x}-{hour}"):
        return ""
    out = "There is a decision about this — check it before changing:\n" + "".join(f"   {DECISIONS}/{h}\n" for h in hits[:4])
    if arch and os.path.isfile(arch):
        out += f"   {arch} — how it is built and why\n"
    return out


TESTS = re.compile(r"/tests?(_v2)?/")


def issue_first_log(fp, sid_full, via="Edit"):
    """A code edit in a project without a task taken → one line in the journal. Shows nothing, blocks nothing."""
    proj, _ = project_of(fp)
    if not proj or fp.endswith(".md") or TESTS.search(fp):
        return
    try:
        taken = open(os.path.join(TASK_STATE, sid_full), encoding="utf-8").read().split()
    except OSError:
        taken = []
    state = f"task {taken[1]}" if len(taken) > 1 and taken[0] == proj else ("other project " + taken[0] if taken else "no task")
    try:
        agent = os.path.basename(open(os.path.expanduser(f"~/.claude/agent-identity/{sid_full}")).read().strip())
    except OSError:
        agent = "?"
    try:
        os.makedirs(os.path.dirname(ISSUE_LOG), exist_ok=True)
        with open(ISSUE_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')}\t{agent}\t{sid_full[:8]}\t{proj}\t{state}\t{fp}\t{via}\n")
    except OSError:
        pass


# Bash write TARGETS only (a path merely mentioned — read by json.load in a heredoc — is not an edit)
_TARGETS = [
    re.compile(r"(?<![0-9&])>{1,2}\s*([^\s;&|)<>]+)"),                                   # > file, >> file
    re.compile(r"\bsed\s+-i\S*\s+(?:-e\s+)?(?:'[^']*'|\"[^\"]*\"|\S+)\s+([^;&|\n]+)"),     # sed -i 'script' files
    re.compile(r"\btee\s+(?:-a\s+)?([^\s;&|]+)"),
    re.compile(r"\b(?:cp|mv|install)\b[^;&|\n]*\s([^\s;&|]+)\s*(?=$|[;&|\n])", re.M),       # the last argument: where to
    re.compile(r"open\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][wax]"),                          # python open(path, 'w')
    re.compile(r"Path\(\s*['\"]([^'\"]+)['\"]\s*\)\.write_"),
]


def bash_write_target(cmd, cwd):
    """The project path a Bash command WRITES to (redirection target, sed -i, tee, cp/mv, open(…,'w')); else ''."""
    for rx in _TARGETS:
        for m in rx.finditer(cmd):
            for t in m.group(1).split():
                t = t.rstrip(".,:").strip("'\"`").rstrip(".,:")
                if not t or t.startswith(("&", "/dev/", "/proc/", "-")):   # scratch under /tmp is outside the workspace anyway
                    continue
                full = t if t.startswith("/") else os.path.normpath(os.path.join(cwd or WS, t))
                if project_of(full)[0] and not full.endswith(".md") and not TESTS.search(full):
                    return full
    return ""


def standard_line():
    try:
        ver = re.search(r"\*\*(?:Version|Версія):\s*(\d+)", open(STANDARD, encoding="utf-8").read(4096)).group(1)
    except (OSError, AttributeError):
        return ""
    return f"Coding standard v{ver} → {STANDARD} (\"done\" only with the output of a run; what changed — the changelog at the bottom).\n"


def project_line(tool, ti, cwd):
    if not os.path.isfile(PROJECT_WORK):
        return ""
    where = [ti.get("file_path") or ""] if tool in ("Edit", "Write") else [cwd]
    return f"Work in a project → {PROJECT_WORK} (the task path, stands, releases).\n" if any(project_of(w.rstrip("/") + "/x")[0] for w in where if w) else ""


def main():
    d = json.load(sys.stdin)
    tool = d.get("tool_name")
    ti = d.get("tool_input") or {}
    if tool in ("Edit", "Write"):
        fp = ti.get("file_path", "") or ""
        if os.path.abspath(fp).startswith(os.path.abspath(ROOT) + os.sep):
            return  # editing the pitfalls themselves
        topics = topics_for_file(fp)
        new_text = (ti.get("new_string") or ti.get("content") or "")[:20000]
        if CONCURRENCY.search(new_text) and not fp.lower().endswith((".md", ".txt")):
            topics.insert(0, "concurrency")
    elif tool == "Bash":
        topics = topics_for_cmd((ti.get("command") or "")[:4000])
    else:
        return
    sid_full = d.get("session_id") or "x"
    sid = sid_full[:8]
    hour = time.strftime("%d%H")
    blocks = []
    for tp in topics:
        hs = headings(tp)
        if not hs or not once(f"/tmp/cph-{sid}-{tp}-{hour}"):
            continue
        blocks.append(os.path.join(ROOT, f"{tp}.md") + " — " + " · ".join(hs))
        if tp == "web" and os.path.isfile(WEB_PLAYBOOK):
            blocks.append(f"The swarm's recipe and experience for sites → {WEB_PLAYBOOK} (read before a new site or a "
                          "big change; learned something → append 1-5 lines at the bottom)")
    extra = live_script_hint(tool, ti, sid, hour)
    if tool == "Bash":
        extra = git_reset_hint((ti.get("command") or "")[:4000], sid, hour) + extra
        tgt = bash_write_target((ti.get("command") or "")[:4000], d.get("cwd") or "")
        if tgt:
            issue_first_log(tgt, sid_full, "Bash")
    else:
        fp = ti.get("file_path", "") or ""
        issue_first_log(fp, sid_full)
        extra = decisions_line(fp, sid, hour) + extra
    if not blocks:
        if extra:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": extra}},
                             ensure_ascii=False))
        return
    ctx = (standard_line()
           + "[code pitfalls] Before this action — headings of lessons already paid for. "
           "If one looks like your case, open the file and read that entry in full. "
           "Stepped on a new one? Append it at the bottom.\n"
           + project_line(tool, ti, d.get("cwd") or "") + "\n".join(blocks) + "\n" + CYCLE + ("\n" + extra if extra else ""))
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "additionalContext": ctx}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # don't swallow it: trace → stderr, rc=1 → hook-safe.sh writes hook-errors.log (fail-open)
        import traceback; traceback.print_exc(); sys.exit(1)
