# Portable stand-ins for GNU-only commands and bash-4-only syntax (sourced, never run). A stock macOS has /bin/bash 3.2
# and BSD stat, date, grep, md5, no sha256sum and no timeout; a script that called the GNU form there failed - and a
# hook under hook-safe.sh fails open, so a whole mechanism went quiet without a word.
#
# Rule: where the GNU command exists (Linux, Git Bash, a Mac with coreutils first in PATH) each function runs exactly
# what the scripts ran before; the fallback runs only where it is missing. Every function is safe under bash 3.2 and
# under `set -eu` (no ${x,,}, no mapfile, no empty "${a[@]}").
#
#   ccm_lower <text>              -> the text in lower case, non-ASCII letters too (${x,,} on bash 4+)
#   ccm_mtime <file>              -> modification time, epoch seconds          (stat -c %Y | stat -f %m)
#   ccm_fsize <file>              -> size in bytes                            (stat -c %s | stat -f %z)
#   ccm_owner <file> / ccm_group  -> owner / group name                       (stat -c %U | stat -f %Su)
#   ccm_mode <file>               -> permission bits in octal, e.g. 600       (stat -c %a | stat -f %Lp)
#   ccm_epoch <date>              -> epoch seconds of "2026-11-24", "2026-11-24 10:00", "2026-11-24T10:00:00+02:00",
#                                    "@1700000000", "yesterday" (date -d | python3); local time when no offset
#   ccm_date_at <epoch> [+fmt]    -> that moment formatted                    (date -d @N | date -r N)
#   ccm_now_iso                   -> 2026-11-24T10:00:00+02:00                (date -Iseconds | date +%Y-%m-%dT%H:%M:%S%z)
#   ccm_sha256 [file]             -> hex digest of the file or of stdin       (sha256sum | shasum -a 256 | python3)
#   ccm_md5 [file]                -> hex digest of the file or of stdin       (md5sum | md5 -q | python3)
#   ccm_timeout [-k K] <s> cmd... -> runs cmd with a time limit, 124 on timeout (timeout | gtimeout | perl | no limit)
#   ccm_utf8_locale               -> a UTF-8 locale this machine has: C.UTF-8, else en_US.UTF-8
#   ccm_json_str <key>            -> the first "key": "value" string of the JSON on stdin (what grep -oP '"k"\s*:\s*"\K[^"]+' gave)

ccm_lower() {
    if [ "${BASH_VERSINFO[0]:-0}" -ge 4 ]; then eval 'printf "%s" "${1,,}"'; return 0; fi   # bash4-guarded
    # bash 3.2: ASCII through tr; a non-ASCII byte -> python3 (tr does not lower-case multibyte letters)
    if printf '%s' "$1" | LC_ALL=C grep -q '[^ -~]' 2>/dev/null && command -v python3 >/dev/null 2>&1; then
        printf '%s' "$1" | python3 -c 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read().decode("utf-8", "surrogateescape").lower().encode("utf-8", "surrogateescape"))'
    else
        printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
    fi
}

_ccm_gnu_stat() { [ -n "${_CCM_GNU_STAT:-}" ] || { stat --version >/dev/null 2>&1 && _CCM_GNU_STAT=1 || _CCM_GNU_STAT=0; }; [ "$_CCM_GNU_STAT" = 1 ]; }
ccm_mtime() { if _ccm_gnu_stat; then stat -c %Y "$1"; else stat -f %m "$1"; fi; }
ccm_fsize() { if _ccm_gnu_stat; then stat -c %s "$1"; else stat -f %z "$1"; fi; }
ccm_owner() { if _ccm_gnu_stat; then stat -c %U "$1"; else stat -f %Su "$1"; fi; }
ccm_group() { if _ccm_gnu_stat; then stat -c %G "$1"; else stat -f %Sg "$1"; fi; }
ccm_mode()  { if _ccm_gnu_stat; then stat -c %a "$1"; else stat -f %Lp "$1"; fi; }

_ccm_gnu_date() { [ -n "${_CCM_GNU_DATE:-}" ] || { date --version >/dev/null 2>&1 && _CCM_GNU_DATE=1 || _CCM_GNU_DATE=0; }; [ "$_CCM_GNU_DATE" = 1 ]; }
ccm_epoch() {
    if _ccm_gnu_date; then date -d "$1" +%s; return; fi
    python3 - "$1" <<'PY'
import datetime, re, sys, time
s = sys.argv[1].strip()
if s.startswith("@") and re.fullmatch(r"@-?\d+", s):
    print(s[1:]); sys.exit(0)
day = datetime.date.today()
if s in ("today", "now"):
    print(int(time.time()) if s == "now" else int(time.mktime(day.timetuple()))); sys.exit(0)
if s == "yesterday":   # GNU date: this time of day, one day back
    print(int(time.time()) - 86400); sys.exit(0)
try:
    d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00").replace(" UTC", "+00:00"))
except ValueError:
    sys.exit(1)
print(int(d.timestamp()))   # no offset in the text -> local time (TZ respected), as date -d
PY
}
ccm_date_at() {   # ccm_date_at <epoch> [+format]
    local e="$1"; shift
    if _ccm_gnu_date; then date -d "@$e" "$@"; else date -r "$e" "$@"; fi
}
ccm_now_iso() {
    if _ccm_gnu_date; then date -Iseconds; return; fi
    local t; t=$(date +%Y-%m-%dT%H:%M:%S%z)
    printf '%s:%s\n' "${t%??}" "${t#"${t%??}"}"   # +0200 -> +02:00, the form date -Iseconds prints
}

ccm_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum ${1+"$1"} | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then shasum -a 256 ${1+"$1"} | awk '{print $1}'
    else python3 -c 'import hashlib,sys; f=open(sys.argv[1],"rb") if len(sys.argv)>1 else sys.stdin.buffer; print(hashlib.sha256(f.read()).hexdigest())' ${1+"$1"}; fi
}
ccm_md5() {
    if command -v md5sum >/dev/null 2>&1; then md5sum ${1+"$1"} | awk '{print $1}'
    elif command -v md5 >/dev/null 2>&1; then md5 -q ${1+"$1"}
    else python3 -c 'import hashlib,sys; f=open(sys.argv[1],"rb") if len(sys.argv)>1 else sys.stdin.buffer; print(hashlib.md5(f.read()).hexdigest())' ${1+"$1"}; fi
}

# The perl branch (a stock macOS has /usr/bin/perl) does what timeout does: the command is a child, stdin passes
# through, after <s> seconds TERM, a second later KILL, exit 124; else the child's own exit code (128+N on a signal).
ccm_timeout() {
    local k=""
    if [ "${1:-}" = -k ]; then k="$2"; shift 2; fi
    if command -v timeout >/dev/null 2>&1; then
        if [ -n "$k" ]; then timeout -k "$k" "$@"; else timeout "$@"; fi
    elif command -v gtimeout >/dev/null 2>&1; then
        if [ -n "$k" ]; then gtimeout -k "$k" "$@"; else gtimeout "$@"; fi
    elif command -v perl >/dev/null 2>&1; then
        perl -e '
            my $t = shift @ARGV; my $pid = fork();
            die "fork: $!\n" unless defined $pid;
            if ($pid == 0) { exec { $ARGV[0] } @ARGV; exit 127; }
            $SIG{ALRM} = sub { kill "TERM", $pid; sleep 1; kill "KILL", $pid; waitpid($pid, 0); exit 124; };
            alarm $t; waitpid($pid, 0); my $s = $?;
            exit($s & 127 ? 128 + ($s & 127) : $s >> 8);' "$@"
    else
        shift; "$@"   # no way to limit the time here: run it anyway (deps_check.py names what is missing)
    fi
}

ccm_utf8_locale() {
    local all; all=$(locale -a 2>/dev/null) || { echo C.UTF-8; return 0; }
    if printf '%s\n' "$all" | grep -qiE '^c\.utf-?8$'; then echo C.UTF-8
    elif printf '%s\n' "$all" | grep -qiE '^en_US\.utf-?8$'; then echo en_US.UTF-8
    else echo C.UTF-8; fi
}

ccm_json_str() {   # the FIRST match, as grep -o | head -1 gave; grep -o is in BSD grep too, -P is not
    grep -o "\"$1\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | head -1 | sed 's/^[^:]*:[[:space:]]*"//; s/"$//'
}
