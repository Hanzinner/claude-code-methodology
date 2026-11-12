#!/usr/bin/env python3
"""standard_version.py - the version of the coding standard file against the line "Standard: vN read ..." in an agent's briefing.

  standard_version.py current                      - the standard's version (a number)
  standard_version.py hint <agent folder> [state]  - the agent lags -> a hint with the changelog entries vN+1..vX; else silence.
                                                     State file (one per session): the same pair X:N already shown TODAY -> silence
                                                     (sessions live for months: "once per session" would mean "once forever",
                                                     and the text disappears with compaction).
  standard_version.py lag <agent folder>           - lags -> a line "read the changes first", exit 1; no -> silence, exit 0.

Why: a raw diff of the standard in a watch list showed every wording tweak to every coder, and an agent that skipped a
version saw only the last edit. The changelog says WHAT changed and what to do.
The standard file:   a header line "**Version: N ..." and a section "## Standard changelog" (or "## Changelog") with
entries "- **vN ..." (continuation lines indented, blank lines between paragraphs allowed).
The briefing line:   "Standard: vN read YYYY-MM-DD".
With "uk" in CCM_LANG_EXTRA the Ukrainian forms ("Версія", "Журнал змін стандарту", "Стандарт: vN прочитано") are read too.
Settings: CCM_CODING_STANDARD (path; default <workspace>/CODING-STANDARD.md), CCM_LANG_EXTRA.
Test: tests/standard-version-test.sh
"""
import os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf

STD = conf("CCM_CODING_STANDARD", os.path.join(conf("CCM_WORKSPACE"), "CODING-STANDARD.md"))
UK = "uk" in (conf("CCM_LANG_EXTRA", "") or "")
LINE_RE = re.compile(r"Standard:\s*v(\d+)\s+read" + (r"|Стандарт:\s*v(\d+)\s+прочитано" if UK else ""))
VER_RE = re.compile(r"\*\*Version:\s*(\d+)" + (r"|\*\*Версія:\s*(\d+)" if UK else ""))
HEAD_RE = re.compile(r"^## (?:Standard )?[Cc]hangelog[^\n]*$" + (r"|^## Журнал змін стандарту[^\n]*$" if UK else ""), re.M)
ENTRY_RE = re.compile(r"^- \*\*v(\d+)\b")


def first_int(m):
    return int(next(g for g in m.groups() if g))


def read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def current():
    s = read(STD)
    m = VER_RE.search(s or "")
    return first_int(m) if m else None


def agent_version(agent_dir):
    """(version, whether the line exists). No line -> v0: the agent never confirmed the standard."""
    m = LINE_RE.search(read(os.path.join(agent_dir, "briefing.md")) or "")
    return (first_int(m), True) if m else (0, False)


def journal(lo, hi):
    """Changelog entries with versions lo < v <= hi, with their continuation lines."""
    s = read(STD) or ""
    m = HEAD_RE.search(s)                              # from the start of a line: a mention in the text is not the section
    if not m:
        return []
    out, keep = [], False
    for ln in s[m.end():].splitlines()[1:]:
        if ln.startswith("## "):
            break
        if not ln.strip():
            continue                                   # a blank line between paragraphs of an entry is not the end of the entry
        m = ENTRY_RE.match(ln)
        if m:
            keep = lo < int(m.group(1)) <= hi
        elif not ln.startswith((" ", "\t")):
            keep = False                               # a "> ..." header line of the changelog
        if keep:
            out.append(ln)
    return out


def main(a):
    cmd = a[0] if a else ""
    x = current()
    if cmd == "current":
        if x is None:
            return 3
        print(x)
        return 0
    if cmd not in ("hint", "lag") or len(a) < 2:
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    if x is None:
        return 0   # the standard is unreadable -> silence (fail-open, like every hook)
    n, has = agent_version(a[1])
    if n >= x:
        return 0
    if cmd == "lag":
        print(f"You confirmed standard v{n}, the current one is v{x}: first read the changes (changelog at the bottom of {STD}) "
              f"and update the line \"Standard: v{x} read YYYY-MM-DD\" in your briefing - only then say \"done\".")
        return 1
    state = a[2] if len(a) > 2 else None
    pair = f"{x}:{n}:{time.strftime('%Y-%m-%d')}"
    if state and (read(state) or "").strip() == pair:
        return 0
    where = ("the line" if has else "the line (your briefing has none - add it)")
    print(f"[watchman] the coding standard is v{x}, you confirmed v{n}. Read the changes below "
          f"(for v0 - the whole standard: {STD}) and update {where} \"Standard: v{x} read YYYY-MM-DD\".")
    for ln in journal(n, x):
        print("  " + ln)
    if state:
        try:
            with open(state, "w") as f:
                f.write(pair)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
