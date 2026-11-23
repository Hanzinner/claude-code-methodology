#!/usr/bin/env bash
# rename_agent.sh <old> <new> [--apply] - rename an agent with one command. Without --apply it changes NOTHING and prints the plan.
# Why a script: renames done by hand kept forgetting the same things - a todo file under the old name (the watchman then created
# a second one next to it), the agent's alarm mode file (the setting was lost), its line in the work-guard list, the owner in a
# project's OWNERS / ROADMAP header, mentions in the team's briefings.
#   1. folder <agents dir>/[<group>/]<old> -> <new>; the old name goes into <new>/.aliases (inbox_resolve, work-guard,
#      briefing-watchman and agent_tab resolve by it); old-style <old>-agent-TODO.md / <old>-human-TODO.md -> <new>-...
#   2. session identities (~/.claude/agent-identity/*, content = the folder) -> the new folder; alarm mode <old> -> <new>;
#      live tabs and a listening inbox_wait.sh -> a warning
#   3. the work-guard list (CCM_WORK_GUARD_AGENTS), `hq =` in <project>/release.toml, the row in AGENTS.md - edited
#   4. live mentions: <project>/OWNERS and FILE-OWNERSHIP.md, the "> Lead:" header of <project>/ROADMAP.md, every agent's
#      briefing.md (group folders too), the todo files of the agent and its team. History is NOT rewritten: lines marked [D]
#      (a recorded decision), the closed sections ("## Processed", "## Done", "## Closed"), the rest of ROADMAP, decisions/,
#      MISTAKES*, episodic/, *.log/*.jsonl and inboxes stay as they are; the plan lists them under "4b. Kept as history".
#      Replacement is by whole word: the boundary is anything but a letter, digit, _ or dash ("Bid-Ops" leaves "Bid-OpsX" and
#      "Bid-Ops-Legacy" alone; the exception is <old>-agent-TODO / <old>-human-TODO, files renamed in step 1)
#   5. a letter (scripts/inbox_post.sh) only to the project team: the agent belongs to project X if it is X's lead (hq= in
#      release.toml or "> Lead:" in ROADMAP) or the old or new name starts with "X-" (new_project.sh names teams that way);
#      team = the lead(s) + folders "X-*" + the renamed agent itself. Outside projects there are no letters.
# Live sessions: briefing-watchman rewrites an identity through .aliases on the next prompt by itself, but many mechanisms
# read the identity between prompts - so step 2 rewrites it at once. The tab's context still holds the old paths -> restart it.
# rc: 0 · 2 usage · 4 refused (new exists / old missing / not an agent folder / ambiguous / new name is someone's alias) ·
#     5 a step failed half-way (what was done is marked with a check mark in the output) · 6 all done, but a letter didn't arrive.
# Settings (methodology.conf or env): CCM_WORKSPACE, CCM_AGENTS_DIR, CCM_PROJECTS_GLOB, CCM_ALARM_MODE_DIR,
# CCM_WORK_GUARD_AGENTS (empty = step skipped), CCM_LANG_EXTRA ("uk" also reads the Ukrainian markers [Р], "Штаб:", "## Оброблено").
# Under CCM_TEST=1 (or HANZ_TEST=1) CCM_WORKSPACE must come from the environment: a test never touches the real workspace.
# Test: tests/rename-agent-test.sh
set -Eeuo pipefail
HERE=$(dirname "$(readlink -f "$0")")
. "$HERE/../lib/ccm_compat.sh"   # ccm_utf8_locale: a stock macOS may have no C.UTF-8
LC_ALL=$(ccm_utf8_locale); export LC_ALL PYTHONIOENCODING=utf-8

usage() { echo "rename_agent.sh <old> <new> [--apply] - without --apply only the plan (changes nothing)" >&2; exit 2; }
apply=0; pos=()
for a in "$@"; do
    case "$a" in
        --apply) apply=1 ;;
        -h|--help) echo "rename_agent.sh <old> <new> [--apply] - rename an agent (folder, identities, alarm mode, lists, mentions, letters to the team)"; exit 0 ;;
        -*) echo "unknown flag $a" >&2; exit 2 ;;
        *) pos+=("$a") ;;
    esac
done
[[ ${#pos[@]} -eq 2 ]] || usage
old=${pos[0]}; new=${pos[1]}
valid() { [[ -n "$1" && ${#1} -le 60 && "$1" != */* && "$1" != .* && "$1" != _* && "$1" != *[[:cntrl:]]* \
             && "$1" != [[:space:]]* && "$1" != *[[:space:]] ]]; }
valid "$old" && valid "$new" || { echo "name: no \"/\", no control characters, no spaces at the ends, not starting with \".\" or \"_\", <= 60 characters" >&2; exit 2; }
[[ "$old" != "$new" ]] || { echo "old and new are the same" >&2; exit 2; }
# a test that writes into the live workspace is a known class of mistake: under the test flag the root must be explicit
if [[ "${CCM_TEST:-${HANZ_TEST:-}}" == 1 && -z "${CCM_WORKSPACE:-}" ]]; then
    echo "CCM_TEST=1: set CCM_WORKSPACE (the real workspace is off limits in a test)" >&2; exit 2
fi
eval "$(python3 "$HERE/../lib/ccm_conf.py" --shell)"
REPO=$CCM_WORKSPACE
AG=$CCM_AGENTS_DIR
GLOB=${CCM_PROJECTS_GLOB:-Project-*}
IDENT="$HOME/.claude/agent-identity"
SESS="$HOME/.claude/sessions"
MODE_DIR=$CCM_ALARM_MODE_DIR
WGA=${CCM_WORK_GUARD_AGENTS:-}
POST="$HERE/inbox_post.sh"
UK=0; [[ ",${CCM_LANG_EXTRA:-}," == *uk* ]] && UK=1

shopt -s nullglob
cands=()
for d in "$AG/$old" "$AG"/*/"$old"; do
    [[ "$d" == "$AG/_"*/* ]] && continue          # _deprecated/, _example-agent/ and other non-agents
    [[ -d "$d" && ! -L "$d" ]] && cands+=("$d")
done
[[ ${#cands[@]} -gt 0 ]] || { echo "no agent \"$old\" (looked in $AG/$old and $AG/*/$old)" >&2; exit 4; }
[[ ${#cands[@]} -eq 1 ]] || { echo "\"$old\" is ambiguous: ${cands[*]#$REPO/} - rename by hand" >&2; exit 4; }
old_dir=${cands[0]}
[[ -f "$old_dir/briefing.md" ]] || { echo "${old_dir#$REPO/} is not an agent folder (no briefing.md); a group folder is not renamed by this script" >&2; exit 4; }
for d in "$AG/$new" "$AG"/*/"$new"; do
    if [[ -e "$d" || -L "$d" ]]; then echo "${d#$REPO/} already exists - doing nothing" >&2; exit 4; fi
done
# the new name is already another agent's alias -> the resolvers (inbox, identity) would become ambiguous
clash=$(AG="$AG" OLD_DIR="$old_dir" NEW="$new" python3 -c '
import glob, os
E = os.environ
for a in sorted(glob.glob(E["AG"] + "/*/.aliases") + glob.glob(E["AG"] + "/*/*/.aliases")):
    if os.path.dirname(a) == E["OLD_DIR"]: continue
    if E["NEW"].lower() in {l.split("#")[0].strip().lower() for l in open(a, encoding="utf-8", errors="replace")}:
        print(os.path.dirname(a)); break')
[[ -z "$clash" ]] || { echo "\"$new\" is already an alias of agent ${clash#$REPO/} (.aliases) - pick another name" >&2; exit 4; }
new_dir="$(dirname "$old_dir")/$new"

step="preparation"
trap 'rc=$?; echo "FAILED at step \"$step\" (rc=$rc). What was done is marked with a check mark above; the folder may already be ${new_dir#$REPO/} - running the script again will refuse (rc 4), finish the unmarked items by hand." >&2; exit 5' ERR

if (( apply )); then
    step="1. folder"
    # -T: never INTO a folder that appeared meanwhile. BSD mv (macOS) has no -T: there the same check by hand
    if mv --version >/dev/null 2>&1; then mv -T -- "$old_dir" "$new_dir"
    else
        if [[ -e "$new_dir" ]]; then echo "$new_dir appeared meanwhile - not moving into it" >&2; false; fi
        mv -- "$old_dir" "$new_dir"
    fi
    echo "MODE --apply: $old -> $new"
else
    echo "DRY RUN: nothing changed. To apply: rename_agent.sh '$old' '$new' --apply"
fi
step="steps 1-5 (python)"
export MODE=$( (( apply )) && echo apply || echo plan ) OLD="$old" NEW="$new" OLD_DIR="$old_dir" NEW_DIR="$new_dir" \
       REPO AG GLOB IDENT SESS MODE_DIR WGA POST UK CCM_LIB="$HERE/../lib"
rc=0
python3 -u - <<'PY' || rc=$?
import glob, json, os, re, subprocess, sys, tempfile, time
E = os.environ
sys.path.insert(0, E["CCM_LIB"])
import ccm_fs  # noqa: E402  (chown: Windows Python has none; replace: waits out a file held open on Windows)
apply = E["MODE"] == "apply"
old, new, REPO, AG, GLOB = E["OLD"], E["NEW"], E["REPO"], E["AG"], E["GLOB"]
UK = E["UK"] == "1"
old_dir, new_dir = E["OLD_DIR"], E["NEW_DIR"]
cur = new_dir if apply else old_dir            # where the folder is now: with --apply bash has already moved it
OK = "  ✓" if apply else ""
today = time.strftime("%F")
PREFIX = GLOB.split("*", 1)[0]


def rel(p):
    return os.path.relpath(p, REPO) if p.startswith(REPO + "/") else p


def keep_owner(path, st):
    ccm_fs.chown(path, st.st_uid, st.st_gid)   # not root and the file is someone else's (or Windows): it keeps our ownership


def write(path, text):
    """atomically; owner, group and mode as the old file had (the temp file is ours, we clean it up ourselves)"""
    st = os.stat(path)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".rename-agent.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.chmod(tmp, st.st_mode & 0o7777)
        keep_owner(tmp, st)
        ccm_fs.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def agents():
    """folder name -> path, only folders with briefing.md; the renamed one under its CURRENT name and place"""
    out = {}
    for b in sorted(glob.glob(AG + "/*/briefing.md") + glob.glob(AG + "/*/*/briefing.md")):
        d = os.path.dirname(b)
        if any(part.startswith("_") for part in os.path.relpath(d, AG).split(os.sep)):
            continue
        out.setdefault(os.path.basename(d), d)
    return out


W = r"[\w-]"   # \w in str is Unicode: Cyrillic is a "letter" too
RX = re.compile(rf"(?<!{W}){re.escape(old)}(?:(?!{W})|(?=-(?:agent|human)-TODO))")

# ── 1. folder ──────────────────────────────────────────────────────────────────────────────────────────
print("== 1. Agent folder")
print(f"   {rel(old_dir)}/ -> {rel(new_dir)}/{OK}")
al = os.path.join(cur, ".aliases")
have = set()
if os.path.isfile(al):
    have = {l.split("#")[0].strip().lower() for l in read(al).splitlines()}
if old.lower() in have:
    print(f"   .aliases: \"{old}\" already there")
else:
    print(f"   .aliases: + {old}{OK}")
    if apply:
        if os.path.isfile(al):
            t = read(al)
            write(al, t + ("" if t.endswith("\n") or not t else "\n") + old + "\n")
        else:
            st = os.stat(cur)
            with open(al, "w", encoding="utf-8") as f:
                f.write(f"# old names of this folder (rename_agent.sh {today})\n{old}\n")
            keep_owner(al, st)
            os.chmod(al, 0o664)
for suf in ("-agent-TODO.md", "-human-TODO.md"):
    src, dst = os.path.join(cur, old + suf), os.path.join(cur, new + suf)
    if not os.path.lexists(src):
        continue
    if os.path.lexists(dst):
        print(f"   ! {old + suf}: {new + suf} already exists next to it - keeping both, merge them by hand")
        continue
    print(f"   {old + suf} -> {new + suf}{OK}")
    if apply:
        os.rename(src, dst)

# ── 2. identities, alarm mode, live tabs ──────────────────────────────────────────────────────────────────
print("== 2. Sessions and alarm")
sids = []
for f in sorted(glob.glob(E["IDENT"] + "/*")):
    try:
        c = read(f).strip()
    except (OSError, UnicodeDecodeError):
        continue
    if c and os.path.normpath(c) == os.path.normpath(old_dir):
        sids.append(os.path.basename(f))
        if apply:
            write(f, new_dir + "\n")
print(f"   identity: {len(sids)} session(s) -> {rel(new_dir)}{OK if sids else ''}")


def alive(s):
    """the same process: /proc start time (Linux). No /proc (macOS): the pid exists - the best that can be checked
    there (agent_tab.py does the same); before, every tab looked dead and the restart warning never came."""
    try:
        return open(f"/proc/{s['pid']}/stat").read().rsplit(")", 1)[1].split()[19] == str(s.get("procStart"))
    except (OSError, IndexError, KeyError, TypeError):
        pass
    if os.path.isdir("/proc") or os.name == "nt":
        return False
    try:
        pid = int(s["pid"])
        return pid > 0 and bool(subprocess.run(["ps", "-p", str(pid), "-o", "pid="], capture_output=True, text=True,
                                               timeout=3).stdout.strip())
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
        return False


live = []
for f in glob.glob(E["SESS"] + "/*.json"):
    try:
        s = json.load(open(f))
    except (OSError, ValueError):
        continue
    if not isinstance(s, dict) or not alive(s):
        continue
    n = str(s.get("name") or "").lower()
    if s.get("sessionId") in sids or n == old.lower() or n.startswith(old.lower() + " "):
        live.append(f"{s.get('name') or s.get('sessionId')} (pid {s.get('pid')}, {s.get('status') or '?'})")
listen = []
procs = []   # (pid, argv as bytes)
for p in glob.glob("/proc/[0-9]*/cmdline"):
    try:
        procs.append((p.split("/")[2], open(p, "rb").read().split(b"\0")))
    except OSError:
        continue
if not os.path.isdir("/proc") and os.name != "nt":   # macOS: the process list from ps (argv split on spaces)
    try:
        for ln in subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True, timeout=5).stdout.split(b"\n"):
            w = ln.split()
            if len(w) > 1:
                procs.append((w[0].decode(), w[1:] + [b""]))
    except (OSError, subprocess.SubprocessError):
        pass
for pid, argv in procs:
    for i, a in enumerate(argv[:-1]):
        if a.endswith(b"inbox_wait.sh") and argv[i + 1].decode("utf-8", "replace") == old:
            listen.append(pid)
for t in live:
    print(f"   ! live tab: {t}. After step 2 the hooks (work-guard, inbox_wait, the watchman) see the new folder, but the"
          f" tab's context still holds the old paths .../{old}/ - writing to them creates a ghost folder. Better restart the"
          f" tab (open it with the name \"{new}\") or tell it: \"you were renamed to {new}, folder {rel(new_dir)}\".")
if listen:
    print(f"   ! inbox_wait.sh \"{old}\" is listening (pid {', '.join(listen)}) - restart it with \"{new}\" after the rename")
mo, mn = os.path.join(E["MODE_DIR"], old), os.path.join(E["MODE_DIR"], new)
if os.path.lexists(mo):
    m = (read(mo).split() or ["?"])[0]
    if os.path.lexists(mn):
        print(f"   ! alarm mode: both {old} ({m}) and {new} exist - the new one applies, the old one is left alone")
    else:
        print(f"   alarm mode: {old} -> {new} ({m}){OK}")
        if apply:
            os.rename(mo, mn)
else:
    print("   alarm mode: no file (auto applies) - nothing")

# ── the project team (for steps 4 and 5) ──────────────────────────────────────────────────────────────────
LEAD_HDR = "(?:Lead|Штаб)" if UK else "Lead"
ags = agents()
names_now = set(ags)                 # in the plan the old name is still here, with --apply the new one
me_now = new if apply else old
projects, team = [], set()
for p in sorted(glob.glob(os.path.join(REPO, GLOB, ""))):
    X = os.path.basename(p.rstrip("/"))[len(PREFIX):]
    hqs = set()
    try:
        m = re.search(r'^\s*hq\s*=\s*"([^"]+)"', read(p + "release.toml"), re.M)
        if m:
            hqs.add(m.group(1))
    except (OSError, UnicodeDecodeError):
        pass
    try:
        for l in read(p + "ROADMAP.md").splitlines()[:15]:
            m = re.match(rf"^> {LEAD_HDR}: ([^.,;(]+?)\s*[.,;(]", l)
            if m:
                hqs.add(m.group(1).strip())
                break
    except (OSError, UnicodeDecodeError):
        pass
    if old in hqs or old.startswith(X + "-") or new.startswith(X + "-"):
        projects.append(X)
        members = {h for h in hqs if h in names_now or h == old} | {a for a in names_now if a.startswith(X + "-")}
        team |= {new if a in (old, me_now) else a for a in members}
if projects:
    team.add(new)

# ── 3. swarm lists ─────────────────────────────────────────────────────────────────────────────────────────
print("== 3. Swarm lists (edited by the script)")
wga = E["WGA"]
if not wga:
    print("   work-guard list: CCM_WORK_GUARD_AGENTS not set - skipped")
elif os.path.isfile(wga):
    t = read(wga)
    lines = t.splitlines(keepends=True)
    hit = [i for i, l in enumerate(lines) if l.strip() == old]
    if hit:
        print(f"   {wga}: line(s) {', '.join(str(i + 1) for i in hit)}: {old} -> {new}{OK}")
        if apply:
            for i in hit:
                lines[i] = lines[i].replace(old, new)
            write(wga, "".join(lines))
    else:
        print(f"   {wga}: no \"{old}\" - nothing")
else:
    print(f"   ! {wga} does not exist")
hq_rx = re.compile(rf'^(\s*hq\s*=\s*"){re.escape(old)}(")', re.M)
for rt in sorted(glob.glob(os.path.join(REPO, GLOB, "release.toml"))):
    t = read(rt)
    if hq_rx.search(t):
        print(f'   {rel(rt)}: hq = "{new}"{OK}')
        if apply:
            write(rt, hq_rx.sub(lambda m: m.group(1) + new + m.group(2), t))
reg = os.path.join(REPO, "AGENTS.md")
ag_rel = rel(AG)
path_rx = re.compile(rf"({re.escape(ag_rel)}/(?:[^/|`\s]+/)?){re.escape(old)}/")
name_rx = re.compile(rf"^\|(\s*)(\*\*)?{re.escape(old)}(\*\*)?(\s*)\|")
if os.path.isfile(reg):
    lines = read(reg).splitlines(keepends=True)
    rows = [i for i, l in enumerate(lines) if l.startswith("|") and (name_rx.match(l) or path_rx.search(l))]
    for i in rows:
        l = path_rx.sub(lambda m: m.group(1) + new + "/", lines[i])
        if name_rx.match(l):
            l = name_rx.sub(lambda m: f"|{m.group(1)}{m.group(2) or ''}{new}{m.group(3) or ''} (renamed from {old} on {today}){m.group(4)}|", l, 1)
        else:
            print(f"   ! {rel(reg)}:{i + 1}: the name in this row is not \"{old}\" - only the path changed, check the name yourself")
        print(f"   {rel(reg)}:{i + 1}: {old} -> {new}{OK}")
        lines[i] = l
    if not rows:
        print(f"   ! {rel(reg)}: no row for \"{old}\" - add a row for \"{new}\" yourself")
    elif apply:
        write(reg, "".join(lines))
else:
    print(f"   ! {rel(reg)} does not exist")

# ── 4. mentions ─────────────────────────────────────────────────────────────────────────────────────────
print("== 4. Whole-word mentions" + (" - replacing" if apply else " - shown only (--apply replaces them)"))
files = sorted(glob.glob(os.path.join(REPO, GLOB, "ROADMAP.md")) + glob.glob(os.path.join(REPO, GLOB, "FILE-OWNERSHIP.md"))
               + glob.glob(os.path.join(REPO, GLOB, "OWNERS")))
files += [b for a, b in sorted((n, os.path.join(d, "briefing.md")) for n, d in ags.items())]
todo_owners = {me_now} | {me_now if a == new else a for a in team}
for a in sorted(todo_owners):
    if a in ags:
        files += sorted(glob.glob(ags[a] + "/*TODO*.md"))
# History is not rewritten: [D] lines, closed sections, in ROADMAP everything but the "Lead:" header.
# decisions/, MISTAKES*.md, episodic/, *.log/*.jsonl, inboxes are not in the file list at all (HIST_PATH is the safety net).
HIST_PATH = re.compile(r"(^|/)(decisions|episodic)/|(^|/)MISTAKES[^/]*\.md$|\.(log|jsonl)$|(^|/)inbox\.md$")
DEC = re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*)?\[" + ("[DР]" if UK else "D") + r"\]")
HQ_LINE = re.compile(rf"^\s*(?:>\s*)?(?:\*\*)?{LEAD_HDR}(?:\*\*)?\s*:")
CLOSED = re.compile(r"(processed|done|closed" + ("|оброблено" if UK else "") + r")(\s*$|\s*[(\-—:·])")


def live_lines(f, lines):
    """per line: True - live (replace), False - history (keep)"""
    roadmap, done, out = os.path.basename(f) == "ROADMAP.md", False, []
    for l in lines:
        if l.startswith("## "):
            done = bool(CLOSED.match(l[3:].strip().lower()))
        if done or DEC.match(l):
            out.append(False)
        elif roadmap:
            out.append(bool(HQ_LINE.match(l)))
        else:
            out.append(True)
    return out


def snip(l, m):
    a = max(0, m.start() - 50)
    return ("…" if a else "") + l[a:a + 130].strip() + ("…" if len(l) > a + 130 else "")


seen, nfiles, nmen, hist = set(), 0, 0, []
for f in files:
    if f in seen or HIST_PATH.search(rel(f)):
        continue
    seen.add(f)
    if os.path.islink(f):
        if RX.search(read(f)):
            print(f"   ! {rel(f)} is a symlink - left alone (edit its target)")
        continue
    try:
        t = read(f)
    except (OSError, UnicodeDecodeError) as e:
        print(f"   ! {rel(f)}: could not read ({e.__class__.__name__}) - skipped")
        continue
    if not RX.search(t):
        continue
    lines = t.splitlines(keepends=True)
    n = 0
    for i, (l, live) in enumerate(zip(lines, live_lines(f, lines))):
        m = RX.search(l)
        if not m:
            continue
        if not live:
            hist.append(f"   {rel(f)}:{i + 1}: {snip(l.rstrip(), m)}")
            continue
        n += len(RX.findall(l))
        if apply:
            lines[i] = RX.sub(new, l)
        else:
            print(f"   {rel(f)}:{i + 1}: {snip(l.rstrip(), m)}")
    if not n:
        continue
    nfiles += 1
    nmen += n
    if apply:
        write(f, "".join(lines))
        print(f"   {rel(f)}: {n} replaced{OK}")
print(f"   total: {nmen} live mention(s) in {nfiles} file(s)" + (" replaced" if apply else ""))
print(f"== 4b. Kept as history ({len(hist)} line(s): [D], closed sections, ROADMAP outside the \"Lead:\" header)")
if apply:
    print("   unchanged" if hist else "   none")
else:
    print("\n".join(hist) if hist else "   none")
if not team:
    print(f"   team todo files: the agent is outside {GLOB} - only its own todo files")

# ── 5. letters ─────────────────────────────────────────────────────────────────────────────────────────
print("== 5. Letters to the team")
bad = 0
if not projects:
    print(f"   the agent is outside {GLOB} - no letters")
else:
    text = (f"Agent {old} was renamed to {new} ({today}, rename_agent.sh). Folder: {rel(new_dir)}/; the old name is in .aliases "
            f"(letters and alarms addressed to \"{old}\" still arrive). Live mentions (OWNERS, the \"Lead:\" header, briefings, "
            f"the team's todo files) were replaced as whole words ({nmen} in {nfiles} files); history ([D] lines, journals, "
            f"ROADMAP) was left as it was. Use {new} in new entries.")
    print(f"   project(s): {', '.join(PREFIX + p for p in projects)}; to: {', '.join(sorted(team))}")
    if not apply:
        print(f"   text: {text}")
    for a in sorted(team):
        if not apply:
            continue
        r = subprocess.run([E["POST"], a], input=text, text=True, capture_output=True)
        if r.returncode:
            bad += 1
            print(f"   ! the letter to {a} did not arrive (rc {r.returncode}): {(r.stderr or r.stdout).strip()[:200]}")
        else:
            print(f"   -> {a}{OK}")
if apply:
    print(f"done {old} -> {new}: folder {rel(new_dir)}, identities {len(sids)}, mentions {nmen}, letters {len(team) - bad}/{len(team)}")
sys.exit(6 if bad else 0)
PY
[[ $rc -eq 0 || $rc -eq 6 ]] || false
exit $rc
