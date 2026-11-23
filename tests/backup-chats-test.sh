#!/usr/bin/env bash
# backup-chats.sh: a real copy lands in <backup>/<date>/<label>/; an rsync failure -> FAIL line, rc 1, and the older
# copies are NOT swept (a failing backup must not also delete the good ones); rsync rc 24 (a file vanished mid-copy)
# is normal. BC=<path> tests another copy. Sandbox: temp HOME, a stub rsync where needed.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/../lib/ccm_compat.sh"   # ccm_touch_ago: BSD touch -d takes no "2 days ago"
BC=${BC:-$HERE/../scripts/backup-chats.sh}
T=$(mktemp -d) && [[ -d "$T" && "$T" != / ]] || { echo "no temp dir (mktemp missing?) - refusing to run: every path below would land in /" >&2; exit 2; }
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/p/a" "$T/bin" "$T/b/2020-01-01"; echo '{}' > "$T/p/a/s.jsonl"; ccm_touch_ago 63072000 "$T/b/2020-01-01"
export HOME=$T BACKUP_DIR=$T/b CLAUDE_PROJECTS_DIRS=$T/p
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1 :: ${3:-}"; fi; }
stub() { printf '#!/bin/sh\nexit %s\n' "$1" > "$T/bin/rsync"; chmod +x "$T/bin/rsync"; }

stub 23
o=$(PATH=$T/bin:$PATH bash "$BC" 2>&1); rc=$?
ok "1 rsync fails (rc 23) -> rc 1 and a FAIL line, no 'backup:' line" '[[ $rc == 1 && "$o" == *"FAIL rsync"* && "$o" != *"backup:"* ]]' "rc=$rc $o"
ok "2 ...and the 2-year-old copy is kept (no retention sweep)" '[[ -d $T/b/2020-01-01 ]]'
stub 24
o=$(PATH=$T/bin:$PATH bash "$BC" 2>&1); rc=$?
ok "3 rsync rc 24 (file vanished) -> success line, rc 0" '[[ $rc == 0 && "$o" == *"backup:"* ]]' "rc=$rc $o"
ok "4 default RETENTION_DAYS=0 -> nothing deleted, the 2-year-old copy stays" '[[ -d $T/b/2020-01-01 ]]'
mkdir -p "$T/b/notes"; ccm_touch_ago 63072000 "$T/b/notes"
o=$(PATH=$T/bin:$PATH RETENTION_DAYS=365 bash "$BC" 2>&1); rc=$?
ok "4b RETENTION_DAYS=365 (install --enable-cleanup) -> the old day-folder goes, a non-date folder stays" '[[ ! -d $T/b/2020-01-01 && -d $T/b/notes ]]'
rm -f "$T/bin/rsync"
if command -v rsync >/dev/null; then
  o=$(bash "$BC" 2>&1); rc=$?
  ok "5 a real rsync -> the transcript is in today's folder" '[[ $rc == 0 && -n $(find "$T/b/$(date +%F)" -name s.jsonl) ]]' "rc=$rc $o"
else   # a minimal machine without rsync: the backup must say FAIL, not "backup:"
  o=$(bash "$BC" 2>&1); rc=$?
  ok "5 no rsync on this machine -> FAIL (rc 127), never a success line" '[[ $rc == 1 && "$o" == *"rc=127"* && "$o" != *"backup:"* ]]' "rc=$rc $o"
fi
echo "backup-chats: $pass pass, $fail fail"; (( fail == 0 ))
