#!/usr/bin/env python3
"""verify_prompt — the ready task for a checking subagent (the verify skill).

  verify_prompt.py [--sid SID] [--note "what changed and what should work"] <changed file or project folder>…

Prints the prompt for Agent(model: sonnet): the session id (for the report), the project's gate from release.toml
(`test`, if there is one; run from the project root, as the releaser does), the changed files and what to do with them.
The subagent runs every check through proof_report.py, so proof-guard sees the FACT of a run (commands and exit
codes), not the word "test" in a task. Project: the nearest folder up from each path that holds a release.toml."""
import os, re, shlex, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "../lib"))
try:
    import ccm_conf  # noqa: E402,F401  (on import: UTF-8 output where the console code page is cp1251/cp1252)
except ImportError:   # a copy of this script without lib/ next to it
    pass

try:
    import tomllib
except ImportError:  # python < 3.11
    tomllib = None

HERE = os.path.dirname(os.path.realpath(__file__))
REPORT = os.path.join(HERE, "proof_report.py")


def project_root(p):
    d = os.path.abspath(p)
    d = d if os.path.isdir(d) else os.path.dirname(d)
    while True:
        if os.path.isfile(os.path.join(d, "release.toml")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return ""
        d = up


def gate(root):
    f = os.path.join(root, "release.toml")
    try:
        if tomllib:
            return (tomllib.load(open(f, "rb")).get("test") or "").strip()
        m = re.search(r'^test\s*=\s*"(.*)"\s*$', open(f, encoding="utf-8").read(), re.M)
        return m.group(1).replace('\\"', '"') if m else ""
    except Exception:
        return ""


def main(argv):
    sid, note, paths = os.environ.get("CLAUDE_CODE_SESSION_ID", ""), "", []
    i = 0
    while i < len(argv):
        if argv[i] == "--sid" and i + 1 < len(argv):
            sid = argv[i + 1]; i += 2
        elif argv[i] == "--note" and i + 1 < len(argv):
            note = argv[i + 1]; i += 2
        else:
            paths.append(argv[i]); i += 1
    if not sid:
        print("verify_prompt: no session id (--sid or CLAUDE_CODE_SESSION_ID)", file=sys.stderr); return 2
    if not paths:
        print(__doc__, file=sys.stderr); return 2
    rep = f"{shlex.quote(REPORT)} run --sid {shlex.quote(sid)} --"
    roots = sorted({r for r in (project_root(p) for p in paths) if r})
    lines = [
        "You check a change. You do NOT edit code and make no decisions: you run checks and report honestly.",
        "Run every check command ONLY like this (it writes the report proof-guard reads):",
        f"  {rep} '<command>'",
        "Reading files to work out what to run is fine with the usual tools.",
        "",
        "Changed files / folders:",
        *[f"  - {os.path.abspath(p)}" for p in paths],
    ]
    if note:
        lines += ["", f"What changed and what should work (the author's words): {note}"]
    for r in roots:
        g = gate(r)
        if g:
            lines += ["", f"The gate of project {os.path.basename(r)} (release.toml -> test), run from the project root:",
                      f"  {rep} {shlex.quote(f'cd {shlex.quote(r)} && {g}')}"]
        else:
            lines += ["", f"Project {os.path.basename(r)}: release.toml has no test command - find the tests of the changed files."]
    lines += [
        "",
        "Then the tests of the changed files themselves, if the gate does not cover them: look for tests/<name>-test.*,",
        "tests/test_<name>.py, or a test file that mentions the changed file (grep). No test - run the changed script the",
        "safest way (--help, --dry-run, with CCM_TEST=1); run nothing live (messages, deploys, cron).",
        "",
        "Answer in up to 10 lines: each command run -> rc and the key output line (the PASS/FAIL count copied from the",
        "output, not from what you expected). Look for the count in the FULL output (grep -E 'Ran [0-9]+ tests|passed|failed|",
        "PASS|FAIL|OK'), not with tail: Python unittest writes \"Ran N tests\" to stderr and it gets lost in the last lines.",
        "The last line exactly: SUMMARY: all rc 0 | RED: <what>. Fix nothing.",
    ]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
