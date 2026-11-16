#!/usr/bin/env python3
"""Lint: a shell temp dir taken with mktemp -d must be checked before it is used.

  sandbox_guard_lint.py FILE...      # prints FILE:LINE: text for every unchecked one; rc 1 if any, 0 if none

Why: `T=$(mktemp -d)` with mktemp missing (a test that trims PATH) leaves T empty, and "$T/bin/rsync" is /bin/rsync -
a test run as root overwrote the system rsync this way. `set -u` does not help (T is set, just empty).
Checked = one of: `|| <anything but true or :>` right after it on the line (exit, return, { … }, a function that exits); a `-d "$T"` / `-n "$T"` test on the same or next line;
`set -e` (any -e… form) earlier in the file. `local T=$(mktemp -d)` hides the failure even under set -e, so for a `local`
only the first two count.
"""
import re, sys

ASSIGN = re.compile(r"(?:^|[\s;&(])(local\s+|declare\s+(?:-\w+\s+)*)?(\w+)=\$\(\s*mktemp\s+-d\b[^)]*\)(.*)$")
SET_E = re.compile(r"^\s*set\s+-[a-zA-Z]*e[a-zA-Z]*\b|^\s*set\s+-o\s+errexit\b")


def check(path):
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    except OSError as e:
        return [f"{path}:0: unreadable ({e})"]
    out, set_e = [], False
    for i, l in enumerate(lines):
        if SET_E.search(l):
            set_e = True
        s = l.lstrip()
        if s.startswith("#"):
            continue
        m = ASSIGN.search(l)
        if not m:
            continue
        local, var, rest = m.group(1), m.group(2), m.group(3)
        near = l + "\n" + (lines[i + 1] if i + 1 < len(lines) else "")
        tested = re.search(r"-[dn]\s+\"?\$\{?" + var + r"\b", near)
        caught = re.match(r"\s*\|\|\s*(?!true\b|:)[\w{]", rest)     # || exit / return / { … } / a function that exits; not || true
        if tested or caught or (set_e and not local):
            continue
        out.append(f"{path}:{i + 1}: {s[:120]}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__.strip().split("\n\n")[1]); sys.exit(2)
    bad = [b for f in sys.argv[1:] for b in check(f)]
    print("\n".join(bad)) if bad else None
    sys.exit(1 if bad else 0)
