#!/usr/bin/env python3
"""story_add.py <project> "<summary>" [--epic E7] [--from-human "<fragment>"] [--session SID] - add a numbered story.

Project-work rule 1a: a request or bug from the human gets a number at once, as a line in its project's ROADMAP.md.
The script takes the NEXT free number in the project's own format and appends
"- ⏳ **[code] summary** · from <human> <time> "<fragment>"". The number is chosen and the line written under
flock on ROADMAP.md.lock (two agents never get the same number); the write is atomic (tmp + os.replace, owner and
mode kept). The last line of output is the code itself: code=$(story_add.sh Shop "..." --epic E7 | tail -n1)
Why: numbers picked by hand collided (two agents took the same next number) and requests lived only in the chat.

The format comes from the story lines already in the ROADMAP:
  - "[E<n>.S<m>]" - epics. --epic E7 -> the line goes to the end of the "## EPIC 7 ..." section. Number: if S-numbers
    are already unique across the project (E5.S99, E4.S100) - project-wide max+1; otherwise max+1 within that epic.
    Mentions in text take a number too (a cancelled story, "E7.S8(a)"); gaps are never refilled.
    Without --epic -> the "## New" section with code "[S<n>]", n = max S across the project + 1 (the lead moves the
    line into an epic later; the number S<n> stays unique in the project).
  - "S<n> · ..." - the number is always project-wide max+1; --epic only picks the section.
No "## New" section -> it is created at the end of the file. No ROADMAP.md -> rc 4.
--from-human: the fragment must be in a message the human typed in this session (lib/human_quote.py); the line then
carries the time of that message and the fragment. Not found -> rc 2 and nothing is written.
rc: 0 written · 1 usage/write error · 2 --from-human: no such message · 3 no epic section / duplicated section ·
4 no ROADMAP. Section headings "## EPIC <n>" / "## New" (older "## ЕПІК <n>" / "## Нове" are recognized too).
Config: CCM_WORKSPACE, CCM_PROJECTS_GLOB, CCM_HUMAN_NAME, CCM_TIMEZONE (empty = system). Env overrides (tests):
STORY_ADD_REPO (workspace), CLAUDE_PROJECTS_DIR (transcripts), CLAUDE_CODE_SESSION_ID."""
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402
try:
    import fcntl
except ImportError:   # Windows: the same calls on msvcrt (lib/ccm_lock.py)
    import ccm_lock as fcntl
import human_quote  # noqa: E402
import ccm_fs  # noqa: E402  (chown: Windows Python has no os.chown)
import ccm_time  # noqa: E402  (CCM_TIMEZONE also without a zone database: Windows Python without tzdata)

REPO = os.environ.get("STORY_ADD_REPO") or conf("CCM_WORKSPACE")
PREFIX = conf("CCM_PROJECTS_GLOB", "Project-*").split("*")[0]

# A story line: "- ✅ **[E1.S1] ...", "- 🔮 [E3.S3] ...", "- **E1.S1 ...", "- ✅ **S1 · ..."
DEF_ES = re.compile(r"^\s*-\s+(?:\S+\s+)?(?:\*\*)?\[?E(\d+)\.S(\d+)(?!\d)", re.M)
DEF_S = re.compile(r"^\s*-\s+(?:\S+\s+)?(?:\*\*)?\[?S(\d+)(?![\w.])", re.M)
ANY_ES = re.compile(r"(?<![\w.])E(\d+)\.S(\d+)(?!\d)")
ANY_S = re.compile(r"(?<![\w.])S(\d+)(?![\w])")
SECTION_END = re.compile(r"^(?:#{1,2}\s|---\s*$)")
NEW_HEAD = re.compile(r"## (?:New|Нове)\s*")
EPIC_WORD = r"(?:EPIC|Epic|ЕПІК)"


def fail(msg, rc):
    print(f"⛔ {msg}")
    return rc


def section_insert_at(lines, head):
    """Index to insert at: right after the last non-empty line of the section."""
    end = len(lines)
    for k in range(head + 1, len(lines)):
        if SECTION_END.match(lines[k]):
            end = k
            break
    last = head
    for k in range(head + 1, end):
        if lines[k].strip():
            last = k
    return last + 1


def plan(text, epic):
    """(code to print, code in the line, epic number of the section or None for "New")."""
    es_defs = [(int(e), int(s)) for e, s in DEF_ES.findall(text)]
    s_defs = [int(s) for s in DEF_S.findall(text)]
    es_any = [(int(e), int(s)) for e, s in ANY_ES.findall(text)]
    max_all = max([s for _, s in es_any] + [int(s) for s in ANY_S.findall(text)] + [0])
    if es_defs or (not s_defs and epic is not None):
        if epic is None:
            n = max_all + 1
            return f"S{n}", f"[S{n}]", None
        # project-wide numbering = >=2 epics with stories and no S-number defined in two epics
        owners = {}
        for e, s in es_defs:
            owners.setdefault(s, set()).add(e)
        global_num = len({e for e, _ in es_defs}) >= 2 and all(len(v) == 1 for v in owners.values())
        if global_num:
            n = max_all + 1  # counting "[S<n>]" in "New" too: the number is unique across the project
        else:
            n = max([s for e, s in es_any if e == epic] + [0]) + 1
        return f"E{epic}.S{n}", f"[E{epic}.S{n}]", epic
    n = max_all + 1  # the S<n> format (or an empty ROADMAP without --epic)
    return f"S{n}", f"S{n} ·", epic


def tz():
    return ccm_time.zone(conf("CCM_TIMEZONE", ""))  # None = system zone (also when the name can't be loaded: one warning)


def build_line(code_in_line, summary, quote):
    line = f"- ⏳ **{code_in_line} {summary}**"
    if quote:
        when = datetime.datetime.fromisoformat(quote[1].replace("Z", "+00:00")).astimezone(tz())
        line += f" · from {conf('CCM_HUMAN_NAME', 'the user')} {when:%Y-%m-%d %H:%M} \"{quote[0]}\""
    return line


def write_atomic(path, text):
    st = os.stat(path)
    tmp = os.path.join(os.path.dirname(path), f".{os.path.basename(path)}.story_add.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        ccm_fs.chown(tmp, st.st_uid, st.st_gid)  # not root (or Windows): the owner can't be kept as is; the mode still is
        os.chmod(tmp, st.st_mode & 0o7777)
        ccm_fs.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)  # this run's own tmp, never someone else's file
        raise


def main(argv):
    args, epic, frag, sid = [], None, None, None
    it = iter(argv)
    for a in it:
        if a == "--epic":
            v = next(it, "") or ""
            m = re.fullmatch(r"[Ee]?(\d+)", v.strip())
            if not m:
                return fail(f"--epic: expected E7 or 7, got {v!r}", 1)
            epic = int(m.group(1))
        elif a == "--from-human":
            frag = next(it, None)
            if frag is None:
                return fail("--from-human without a fragment", 1)
        elif a == "--session":
            sid = next(it, None)
        elif a.startswith("--"):
            return fail(f"unknown option {a}\n{__doc__}", 1)
        else:
            args.append(a)
    if len(args) != 2:
        print(__doc__)
        return 1
    proj, summary = args
    proj = proj[len(PREFIX):] if PREFIX and proj.startswith(PREFIX) else proj
    name = PREFIX + proj
    summary = re.sub(r"\s+", " ", summary).strip()
    if not summary:
        return fail("empty summary", 1)
    rm = os.path.realpath(os.path.join(REPO, name, "ROADMAP.md"))  # a symlink is followed, not overwritten
    if not os.path.isfile(rm):
        return fail(f"no {name}/ROADMAP.md - a project without one creates it first "
                    f"(scripts/new_project.sh for a new project, or write it by hand)", 4)

    quote = None
    if frag is not None:  # checked before the lock: not found -> nothing is touched
        try:
            hit = human_quote.find_quote(frag, sid)
        except human_quote.QuoteError as e:
            return fail(str(e), 1)
        if not hit:
            return fail(f"{conf('CCM_HUMAN_NAME', 'the user')} did not type this in this session - story not added", 2)
        quote = (re.sub(r"\s+", " ", frag).strip(), hit[1])

    lock = rm + ".lock"
    st = os.stat(rm)
    with open(lock, "a") as lf:
        try:  # the lock file gets the ROADMAP's owner, so the other user of the workspace can open it too
            ccm_fs.chown(lock, st.st_uid, st.st_gid)
            os.chmod(lock, 0o664)
        except OSError:
            pass
        fcntl.flock(lf, fcntl.LOCK_EX)
        with open(rm, encoding="utf-8") as f:
            text = f.read()
        code, code_in_line, sec = plan(text, epic)
        line = build_line(code_in_line, summary, quote)
        lines = text.split("\n")
        if sec is None:
            heads = [i for i, l in enumerate(lines) if NEW_HEAD.fullmatch(l)]
            label = "## New"
            if len(heads) > 1:
                return fail(f"section \"## New\" appears twice in {rm} - merge them by hand", 3)
        else:
            heads = [i for i, l in enumerate(lines) if re.match(rf"## {EPIC_WORD} {sec}(?!\d)", l)]
            label = f"## EPIC {sec}"
            if len(heads) != 1:
                have = ", ".join(re.findall(rf"^## {EPIC_WORD} (\d+)", text, re.M)) or "none"
                what = "no section" if not heads else "several sections"
                return fail(f"{what} \"{label} ...\" in {name}/ROADMAP.md (epics: {have}); "
                            f"without --epic the line goes to \"## New\"", 3)
        if heads:
            at = section_insert_at(lines, heads[0])
            lines[at:at] = [line]
            new = "\n".join(lines)
        else:  # no "## New" yet - at the end of the file
            new = text.rstrip("\n") + f"\n\n## New\n{line}\n"
        write_atomic(rm, new)
        with open(rm, encoding="utf-8") as f:  # check what landed on disk
            got = f.read().split("\n").count(line)
    if got != 1:
        return fail(f"after the write the line is there {got} time(s) - check {rm}", 1)
    print(f"✅ {name}: added {code} in \"{label}\": {line}")
    print(code)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
