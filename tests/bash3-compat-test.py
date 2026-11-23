#!/usr/bin/env python3
"""bash3-compat: the shell scripts that run on a person's machine stay runnable on a stock macOS - /bin/bash 3.2 and BSD
grep, sed, stat, date, mv, chmod; no timeout, flock, md5sum, sha256sum. Why: hooks run under hook-safe.sh, which fails
open - a hook that died at `${s,,}` ("bad substitution" on bash 3.2) or at `grep -P` (BSD grep has no -P) went quiet
without a word, and with it the agent's identity, briefing and letters. On Linux every one of these constructs works,
so only a lint catches them before a Mac does.

  1. no bash-4-only syntax: ${x,,} ${x^^} (outside a `# bash4-guarded` line), mapfile/readarray, declare/local -A or -n,
     coproc, |&, &>>, ${x@Q}, exec {fd}>, [[ -v, printf %(...)T, ${a[-1]}, shopt globstar/lastpipe, wait -n, $EPOCHSECONDS;
  2. an array that starts empty (x=()) and is never given a value list is not expanded as a bare "${x[@]}" in a script
     under `set -u` (bash 3.2: an error; the portable form is ${x[@]+"${x[@]}"});
  3. no GNU-only command form without its fallback on the same line (lib/ccm_compat.sh is the fallback layer itself,
     a few multi-line guards are listed in ALLOW with the reason);
  4. every file parses (bash -n) under each bash 3.x on this machine (/bin/bash on a Mac; CCM_BASH3=<path> adds one):
     the 3.2 parser differs (a `case` inside $(...), here-documents in a command substitution). On Linux there is
     none - the check says so and counts as passed;
  5. a script that calls a ccm_* function loads lib/ccm_compat.sh (directly or through inbox_lib.sh / backup-common.sh).

Scope: install.sh and the shell files under hooks/, scripts/, lib/, bin/, addons/ - not tests, and not the add-ons that
are Linux-only by design (mobile-bot: systemd + runuser; net-change: netplan/systemd, root) or the root-only release
queue setup (setup-releaser.sh: /etc/cron.d, useradd). REPO=<clone> (or CCM_REPO_DIR) checks another copy.
Last line: bash3-compat-test: N pass, M fail.
"""
import os, re, shutil, subprocess, sys

REPO = os.path.abspath(os.environ.get("REPO") or os.environ.get("CCM_REPO_DIR")
                       or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKIP_DIRS = ("tests", "addons/mobile-bot", "addons/net-change", ".git")
SKIP_FILES = ("scripts/setup-releaser.sh",)

BASH4 = [
    (r"\$\{[A-Za-z_0-9@*]+(\[[^]]*\])?(\^\^?|,,?)", "${x,,} / ${x^^} (case change): ccm_lower in lib/ccm_compat.sh"),
    (r"(^|[;&|({]\s*|\s)(mapfile|readarray)\s", "mapfile/readarray: a `while IFS= read -r l; do a+=(\"$l\"); done` loop"),
    (r"\b(declare|local|typeset)\s+-[a-zA-Z]*[An]", "associative array / nameref (declare -A, -n)"),
    (r"(^|[;&|]\s*)coproc\b", "coproc"),
    (r"\|&", "|& : 2>&1 |"),
    (r"&>>", "&>> : >>f 2>&1"),
    (r"\$\{[^}]*@[QEPAaKkUuL]\}", "${x@Q} and other @ transformations"),
    (r"\bexec\s+\{[A-Za-z_]+\}[<>]|\{[A-Za-z_]+\}>&-", "exec {fd}> (dynamic file descriptors, bash 4.1)"),
    (r"\[\[\s+-v\s", "[[ -v (bash 4.2): [[ -n ${x+set} ]]"),
    (r"\bprintf\s[^|;]*%\([^)]*\)T", "printf %(...)T (bash 4.2): date"),
    (r"\$\{[A-Za-z_][A-Za-z_0-9]*\[-[0-9]+\]\}", "${a[-1]} (bash 4.3): ${a[${#a[@]}-1]}"),
    (r"\bshopt\s+-s\s+[^;#]*\b(globstar|lastpipe|inherit_errexit)\b", "shopt globstar/lastpipe/inherit_errexit (bash 4+)"),
    (r"\bwait\s+-n\b", "wait -n (bash 4.3)"),
    (r"\$\{?(EPOCHSECONDS|EPOCHREALTIME|BASHPID)\b", "$EPOCHSECONDS / $BASHPID (bash 4+/5): $(date +%s)"),
    (r";;&|;&\s*$", "case fall-through ;& / ;;& (bash 4)"),
    (r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7f]", "$VAR right before a non-ASCII char (bash 3.2 in UTF-8 reads its first byte as part of the name: 'MEMDIR\\xe2: unbound variable'): ${VAR}"),
]

# (pattern, a fallback on the same line that makes it fine, what to use instead)
GNU = [
    (r"\bgrep\s[^|;]*-[a-zA-Z]*P", r"HAVE_PCRE|grep -qP", "grep -P: BSD grep has none - sed, ccm_json_str or Python"),
    (r"\bstat\s+(-c|--format|--printf)\b", r"stat -f", "stat -c: ccm_mtime/ccm_fsize/ccm_owner/ccm_mode, or `|| stat -f`"),
    (r"\bdate\s[^|;)]*(-d\s|--date|-I)", r"type ccm_", "date -d / -Iseconds: ccm_epoch, ccm_date_at, ccm_now_iso"),
    (r"\b(sha256sum|sha1sum|md5sum)\b", r"command -v (sha256sum|md5sum)", "sha256sum/md5sum: ccm_sha256, ccm_md5"),
    (r"(^|[;&|(]\s*|\s)timeout\s+(-k\s+\S+\s+)?[0-9]", r"command -v timeout", "timeout: ccm_timeout (gtimeout, perl)"),
    (r"\bfind\s[^|;]*-printf\b", r"$^", "find -printf: BSD find has none"),
    (r"\bxargs\s[^|;]*-r\b", r"command -v", "xargs -r"),
    (r"\bmv\s+-T\b", r"mv --version|\|\|", "mv -T: BSD mv has none"),
    (r"\b(chmod|chown)\s+--reference", r"(chmod|chown) --version", "chmod/chown --reference: ccm_mode/ccm_owner"),
    (r"\breadlink\s+-[a-z]*[me]\b|\brealpath\s+-", r"$^", "readlink -m/-e, realpath -e: GNU only"),
    (r"\bsed\s+(-[a-zA-Z]*\s+)*-i(\s|$)", r"$^", "sed -i without a suffix: BSD sed needs -i ''"),
    (r"\bsed\s(?![^|]*\s-[a-zA-Z]*E)[^|]*'[^']*\\[?+|]", r"$^", "\\? \\+ \\| in a basic sed regex: GNU only (\\{0,1\\}, sed -E)"),
    (r"\bgrep\s[^|]*'[^']*\\[swSW]", r"$^", "\\s \\w in grep: [[:space:]] [[:alnum:]_]"),
    (r"LC_ALL=C\.UTF-8|LANG=C\.UTF-8", r"$^", "a hard C.UTF-8: ccm_utf8_locale (a Mac may lack it)"),
    (r"\bgetent\b", r"command -v getent", "getent: none on macOS"),
    (r"\btouch\s[^|;]*-d\s", r"$^", "touch -d '2 days ago': BSD touch takes only an ISO date - ccm_touch_ago"),
    (r"\bpaste\s+-[a-z]*s[a-z]*(\S*|\s+-d\s*\S+)\s*($|[|;)])", r"$^", "paste -s without a file: BSD paste needs \"-\" for stdin"),
    (r"(^|[;&|(]\s*|\s)setsid\s", r"command -v setsid", "setsid: none on macOS"),
    (r"(^|[;&|(]\s*|\s)flock\s+-", r"command -v flock", "flock: lib/ccm_lock.sh"),
]
# multi-line guards: (file, the pattern's text, why it is fine)
ALLOW = {
    ("scripts/memory_consolidation.sh", "find -printf"): "the next line takes the newest mtime from Python when it printed nothing",
    ("bin/catchup-run", "flock"): "under `if command -v flock`; the else is a mkdir lock",
    ("lib/ccm_lock.sh", "flock"): "the flock branch of the lock itself, under `if command -v flock`",
    ("addons/offsite-backup/scripts/backup-restic.sh", "flock"): "under `if command -v flock`; the elif is lib/ccm_lock.sh",
    ("addons/offsite-backup/scripts/backup-common.sh", "date -d"): "`type ccm_epoch || ...`: only where lib/ccm_compat.sh is missing",
    ("scripts/public_gate.sh", "grep -P"): "rx(): grep -P only when the HAVE_PCRE probe above it found a grep with -P, else Python",
}

pass_ = fail = 0


def ok(name, cond, detail=""):
    global pass_, fail
    if cond:
        pass_ += 1
    else:
        fail += 1
        print("FAIL:", name)
        if detail:
            print("\n".join("   " + l for l in detail.rstrip().split("\n")[:40]))


def shell_files():
    out = [p for p in [os.path.join(REPO, "install.sh")] if os.path.isfile(p)]   # an install dir has none
    for top in ("hooks", "scripts", "lib", "bin", "addons"):
        for root, dirs, files in os.walk(os.path.join(REPO, top)):
            rel = os.path.relpath(root, REPO).replace(os.sep, "/")
            dirs[:] = [d for d in dirs if f"{rel}/{d}" not in SKIP_DIRS and d not in ("tests", ".git", "__pycache__")]
            for f in files:
                p = os.path.join(root, f)
                if os.path.relpath(p, REPO).replace(os.sep, "/") in SKIP_FILES:
                    continue
                try:
                    first = open(p, encoding="utf-8", errors="replace").readline()
                except OSError:
                    continue
                if f.endswith(".sh") or (first.startswith("#!") and re.search(r"\b(ba)?sh\b", first) and "python" not in first):
                    out.append(p)
    return sorted(set(out))


def code_lines(path):
    """(number, raw line, code without a trailing comment) - comment-only lines and here-document bodies of a quoted
    marker (<<'X': text, not code) are left out"""
    out, hd = [], None
    for n, raw in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
        line = raw.rstrip("\n")
        if hd is not None:
            if line.strip() == hd:
                hd = None
            continue
        m = re.search(r"<<-?\s*'([A-Za-z_]+)'", line)
        if m:
            hd = m.group(1)
        if line.lstrip().startswith("#"):
            continue
        out.append((n, line, re.sub(r"\s#(\s.*|)$", "", line)))
    return out


files = shell_files()
ok("0 the scope is found (install.sh, hooks, scripts, lib)", len(files) > 40 and any(f.endswith("briefing-watchman.sh") for f in files),
   f"{len(files)} files")
rel = lambda p: os.path.relpath(p, REPO).replace(os.sep, "/")

# 1. bash-4 syntax
hits = []
for f in files:
    for n, raw, code in code_lines(f):
        if "bash4-guarded" in raw:
            continue
        for rx, why in BASH4:
            if re.search(rx, code):
                hits.append(f"{rel(f)}:{n}: {why}\n      {raw.strip()[:140]}")
ok("1 no bash-4-only syntax in the scripts a Mac runs with /bin/bash 3.2", not hits, "\n".join(hits))

# 2. empty arrays under set -u
hits = []
for f in files:
    lines = code_lines(f)
    text = "\n".join(c for _, _, c in lines)
    if not re.search(r"^\s*set\s+-[a-zA-Z]*u|set\s+-o\s+nounset", text, re.M):
        continue
    empty = set(re.findall(r"(?:^|[\s;(])([A-Za-z_][A-Za-z_0-9]*)=\(\s*\)", text, re.M))
    empty -= set(re.findall(r"(?:^|[\s;(])([A-Za-z_][A-Za-z_0-9]*)=\(\s*[^)\s]", text, re.M))   # also given a value list
    for n, raw, code in lines:
        for name in re.findall(r'(?<![+])"\$\{([A-Za-z_][A-Za-z_0-9]*)\[[@*]\]\}"', code):
            if name in empty:
                hits.append(f"{rel(f)}:{n}: \"${{{name}[@]}}\" of an array that starts empty -> ${{{name}[@]+\"${{{name}[@]}}\"}}\n      {raw.strip()[:140]}")
ok("2 no bare \"${a[@]}\" of a possibly empty array under set -u", not hits, "\n".join(hits))

# 3. GNU-only commands
hits = []
for f in files:
    r = rel(f)
    if r == "lib/ccm_compat.sh":
        continue
    for n, raw, code in code_lines(f):
        for rx, guard, why in GNU:
            if re.search(rx, code) and not re.search(guard, code):
                key = next((k for k in ALLOW if k[0] == r and k[1].split()[0] in code), None)
                if key:
                    continue
                hits.append(f"{r}:{n}: {why}\n      {raw.strip()[:140]}")
ok("3 no GNU-only command form without a fallback", not hits, "\n".join(hits))

# 5. a script that calls a lib/ccm_compat.sh function loads it (itself, or through a file that does)
COMPAT_FN = r"\bccm_(lower|mtime|fsize|owner|group|mode|epoch|date_at|now_iso|touch_ago|sha256|md5|timeout|utf8_locale|json_str)\b"
LOADS = r"ccm_compat\.sh|inbox_lib\.sh|backup-common\.sh|restic-env\.sh"
hits = [rel(f) for f in files if rel(f) != "lib/ccm_compat.sh"
        and re.search(COMPAT_FN, "\n".join(c for _, _, c in code_lines(f))) and not re.search(LOADS, open(f, encoding="utf-8", errors="replace").read())]
ok("5 every script that calls a ccm_* compat function loads lib/ccm_compat.sh", not hits, "\n".join(hits))
ok("5b lib/ccm_compat.sh is there",
   os.path.isfile(os.path.join(REPO, "lib", "ccm_compat.sh")))

# 4. bash -n under every bash 3.x here
olds = []
for b in dict.fromkeys(filter(None, ["/bin/bash", shutil.which("bash"), os.environ.get("CCM_BASH3")])):
    try:
        v = subprocess.run([b, "-c", 'echo "${BASH_VERSINFO[0]}"'], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        continue
    if v.isdigit() and int(v) < 4:
        olds.append(b)
if not olds:
    print("bash3-compat: no bash 3.x on this machine - the parse check runs on a Mac (/bin/bash 3.2) or with CCM_BASH3=<path>")
    ok("4 bash -n under bash 3.x (none here: skipped)", True)
for b in olds:
    bad = []
    for f in files:
        r = subprocess.run([b, "-n", f], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            bad.append(f"{rel(f)}: {(r.stderr or '').strip()[:300]}")
    ok(f"4 every file parses under {b} (bash 3.x)", not bad, "\n".join(bad))

print(f"bash3-compat-test: {pass_} pass, {fail} fail")
sys.exit(1 if fail else 0)
