#!/usr/bin/env bash
# offsite-backup add-on in a sandbox: a fake `restic` on PATH (logs its arguments, answers from env switches), temp HOME,
# no network (b2_usage.py talks to a local 127.0.0.1 stub). Covers env/keys loading, the backup run, prune gating,
# the supervisor checks, boot catch-up, and setup-offsite-backup.sh --dry-run. AB=<addon dir> tests another copy.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
AB=${AB:-$HERE/..}
T=$(mktemp -d) || exit 2; trap 'rm -rf "$T"; [ -n "${SRV:-}" ] && kill $SRV 2>/dev/null' EXIT
export HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_SECRETS_DIR="$T/sec" CCM_WORKSPACE="$T/ws" CCM_BACKUP_STATE="$T/state" CCM_CLAUDE_DIR="$T/cdir"
export MANIFEST_DIR="$T/manifest" FAKE_LOG="$T/restic.calls"
mkdir -p "$HOME/.claude" "$T/sec" "$T/ws" "$T/bin" "$T/state"; echo data > "$T/ws/f.txt"
cat > "$T/bin/restic" <<'F'
#!/bin/sh
echo "$*" >> "$FAKE_LOG"
case "$1" in
  snapshots) exit ${FAKE_SNAP_RC:-0} ;;
  backup) echo "snapshot abcd saved"; exit ${FAKE_BACKUP_RC:-0} ;;
  stats) echo '{"total_size": 5000000000}' ;;
  *) exit 0 ;;
esac
F
chmod +x "$T/bin/restic"; export PATH="$T/bin:$PATH"
FAKE_SAK=SECRETKEYVALUE   # through a variable: a secret scanner reads the literal assignment as a key
cat > "$T/sec/restic.env" <<E2
BACKUP_BACKEND=s3
S3_BUCKET=bkt
S3_ENDPOINT=https://s3.example.test/
AWS_ACCESS_KEY_ID=SECRETKEYID
AWS_SECRET_ACCESS_KEY=$FAKE_SAK
BACKUP_PATHS=$T/ws:$T/nonexistent
E2
chmod 600 "$T/sec/restic.env"; echo "pass" > "$T/sec/backup-passphrase.txt"; chmod 600 "$T/sec/backup-passphrase.txt"
cp "$AB/RECOVERY.md.template" "$AB/scripts/RECOVERY.md" 2>/dev/null; REC_MADE=$?
S="$AB/scripts"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

# 1 env: s3 repo from restic.env, passphrase from CCM_SECRETS_DIR, no secret printed
out=$(bash -c "source '$S/restic-env.sh'; echo \"\$RESTIC_REPOSITORY|\$RESTIC_PASSWORD_FILE\"" 2>&1)
ok "1 restic-env: repo s3:<endpoint>/<bucket>, passphrase from CCM_SECRETS_DIR, no secret in output" '[ "$out" = "s3:https://s3.example.test/bkt|$T/sec/backup-passphrase.txt" ] && ! grep -q SECRETKEY <<<"$out"'
# 2 b2 backend
sed -i 's/^BACKUP_BACKEND=s3/BACKUP_BACKEND=b2/' "$T/sec/restic.env"; printf 'B2_BUCKET=bb\nB2_ACCOUNT_ID=i\nB2_ACCOUNT_KEY=k\n' >> "$T/sec/restic.env"
out=$(bash -c "source '$S/restic-env.sh'; echo \"\$RESTIC_REPOSITORY\"" 2>&1); ok "2 b2 backend -> b2:<bucket>:/restic" '[ "$out" = "b2:bb:/restic" ]'
# 3 missing keys -> clear failure
out=$(CCM_SECRETS_DIR="$T/empty" bash -c "source '$S/restic-env.sh'" 2>&1); rc=$?; ok "3 no restic.env -> rc 1 and a line naming the file" '[ $rc != 0 ] && grep -q "restic.env missing" <<<"$out"'
# 3b old passphrase location: fallback + warning
mkdir -p "$HOME/.claude/secrets"; mv "$T/sec/backup-passphrase.txt" "$HOME/.claude/secrets/"
out=$(bash -c "source '$S/restic-env.sh'; echo \"\$RESTIC_PASSWORD_FILE\"" 2>&1); ok "3b old passphrase path used with a WARNING" 'grep -q "WARNING: using the old passphrase" <<<"$out" && grep -q "$HOME/.claude/secrets/backup-passphrase.txt\$" <<<"$out"'
mv "$HOME/.claude/secrets/backup-passphrase.txt" "$T/sec/"
# 4 backup run (s3 backend: size via fake restic stats), done line, stamp, size, only existing paths
bash "$S/backup-restic.sh" > "$T/o" 2>&1; rc=$?
sed -i 's/^BACKUP_BACKEND=b2/BACKUP_BACKEND=s3/' "$T/sec/restic.env"
bash "$S/backup-restic.sh" > "$T/o" 2>&1; rc=$?
ok "4 backup run: rc 0, done line, stamp, size file, backup got the existing path only" '[ $rc = 0 ] && grep -q "=== restic backup done ===" "$T/state/backup.log" && [ -s "$T/state/last-success" ] && grep -q " 5000000000$" "$T/state/size" && grep -q "^backup .*$T/ws" "$FAKE_LOG" && ! grep -q nonexistent "$FAKE_LOG"'
ok "5 nothing is pruned without BACKUP_PRUNE=1" '! grep -q "^forget" "$FAKE_LOG" && grep -q "nothing is deleted" "$T/state/backup.log"'
echo "BACKUP_PRUNE=1" >> "$T/sec/restic.env"; : > "$FAKE_LOG"
bash "$S/backup-restic.sh" > "$T/o" 2>&1; ok "6 BACKUP_PRUNE=1 nightly run -> forget --prune with the keep counts" 'grep -q "^forget --keep-hourly 24 --keep-daily 7 --keep-weekly 4 --keep-monthly 3 --prune" "$FAKE_LOG"'
: > "$FAKE_LOG"; SKIP_PRUNE=1 bash "$S/backup-restic.sh" > "$T/o" 2>&1; ok "7 SKIP_PRUNE=1 hourly run -> no forget even with BACKUP_PRUNE=1" '! grep -q "^forget" "$FAKE_LOG" && grep -q "^backup" "$FAKE_LOG"'
# 8 failing restic backup: no done line appended, rc != 0
n=$(grep -c "backup done" "$T/state/backup.log"); FAKE_BACKUP_RC=1 bash "$S/backup-restic.sh" > "$T/o" 2>&1; rc=$?
ok "8 restic backup fails -> rc != 0 and no new done line" '[ $rc != 0 ] && [ "$(grep -c "backup done" "$T/state/backup.log")" = "$n" ]'
# 9 repo not initialised (rc 10) -> init
: > "$FAKE_LOG"; FAKE_SNAP_RC=10 bash "$S/backup-restic.sh" > "$T/o" 2>&1; ok "9 snapshots rc 10 -> restic init" 'grep -q "^init" "$FAKE_LOG"'
: > "$FAKE_LOG"; FAKE_SNAP_RC=1 bash "$S/backup-restic.sh" > "$T/o" 2>&1; rc=$?; ok "9b snapshots rc 1 (network etc.) -> no init, no backup" '[ $rc = 1 ] && ! grep -q "^init\|^backup" "$FAKE_LOG"'
# 10 last_ok_check
bash "$S/restic_last_ok_check.sh" > "$T/o" 2>&1; rc=$?; ok "10 last_ok_check: fresh success -> rc 0" '[ $rc = 0 ] && grep -q "last successful backup" "$T/o"'
old=$(date -d '5 hours ago' -Iseconds); printf '%s === restic backup done ===\n%s Fatal: storage cap exceeded\n' "$old" "$(date -Iseconds)" > "$T/state/backup.log"
bash "$S/restic_last_ok_check.sh" > "$T/o" 2>&1; rc=$?; ok "11 last_ok_check: success 5 h old, error after it -> rc 1 and the error quoted" '[ $rc = 1 ] && grep -q "storage hit its size cap" "$T/o"'
printf '%s some error only\n' "$(date -Iseconds)" > "$T/state/backup.log"
bash "$S/restic_last_ok_check.sh" > "$T/o" 2>&1; rc=$?; ok "11b a FRESH log with no success line -> rc 1 (log freshness proves nothing)" '[ $rc = 1 ]'
# 12 size check
echo "$(date +%s) 5000000000" > "$T/state/size"; : > "$T/state/size.hist"
bash "$S/restic_size_check.sh" > "$T/o" 2>&1; rc=$?; ok "12 size_check: 5 GB fresh -> rc 0" '[ $rc = 0 ]'
echo "$(date +%s) 9200000000" > "$T/state/size"; bash "$S/restic_size_check.sh" > "$T/o" 2>&1; rc=$?; ok "12b 9.2 GB -> rc 1" '[ $rc = 1 ]'
echo "$(( $(date +%s) - 36000 )) 5000000000" > "$T/state/size"; bash "$S/restic_size_check.sh" > "$T/o" 2>&1; rc=$?; ok "12c measurement 10 h old -> rc 1 stale" '[ $rc = 1 ] && grep -q stale "$T/o"'
echo "$(( $(date +%s) - 80000 )) 4000000000" > "$T/state/size.hist"; echo "$(date +%s) 5000000000" > "$T/state/size"; bash "$S/restic_size_check.sh" > "$T/o" 2>&1; rc=$?; ok "12d +1 GB in a day -> rc 1 (growth)" '[ $rc = 1 ] && grep -q "growing too fast" "$T/o"'
rm -f "$T/state/size"; bash "$S/restic_size_check.sh" > "$T/o" 2>&1; ok "12e no measurement -> rc 1" '[ $? = 1 ]'
# 13 catch-up
: > "$FAKE_LOG"; echo $(( $(date +%s) - 3600 )) > "$T/state/last-success"; bash "$S/backup-catchup.sh"; ok "13 catch-up: success 1 h ago -> no run" '! grep -q "^backup" "$FAKE_LOG"'
echo $(( $(date +%s) - 20000 )) > "$T/state/last-success"; bash "$S/backup-catchup.sh"; ok "13b catch-up: success 5 h ago -> runs, without prune" 'grep -q "^backup" "$FAKE_LOG" && ! grep -q "^forget" "$FAKE_LOG" && grep -q BOOT-CATCHUP "$T/state/backup.log"'
# 14 b2_usage against a local stub (no internet)
python3 - "$T" <<'P' &
import http.server, json, sys, threading
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _send(self,o): b=json.dumps(o).encode(); self.send_response(200); self.end_headers(); self.wfile.write(b)
    def do_GET(self): self._send({"authorizationToken":"t","apiInfo":{"storageApi":{"apiUrl":"http://127.0.0.1:%d"%self.server.server_port,"bucketId":"B"}}})
    def do_POST(self):
        n=int(self.headers.get("Content-Length",0)); body=json.loads(self.rfile.read(n))
        self._send({"files":[{"contentLength":100},{"contentLength":23}],"nextFileName":None})
s=http.server.HTTPServer(("127.0.0.1",0),H); open(sys.argv[1]+"/port","w").write(str(s.server_port)); s.serve_forever()
P
SRV=$!; for i in 1 2 3 4 5 6 7 8 9 10; do [ -s "$T/port" ] && break; sleep 0.3; done
out=$(B2_ACCOUNT_ID=i B2_ACCOUNT_KEY=k B2_AUTH_URL="http://127.0.0.1:$(cat "$T/port")/auth" python3 -I "$S/b2_usage.py" 2>&1); ok "14 b2_usage sums contentLength over the listing (stub): 123" '[ "$out" = 123 ]'
out=$(B2_ACCOUNT_ID=i B2_ACCOUNT_KEY=k B2_AUTH_URL="http://127.0.0.1:1/x" python3 -I "$S/b2_usage.py" 2>&1); rc=$?; ok "14b b2_usage: unreachable -> rc != 0, message" '[ $rc != 0 ] && grep -q "^b2_usage:" <<<"$out"'
# 15 setup --dry-run
before=$(crontab -l 2>/dev/null | md5sum)
bash "$AB/setup-offsite-backup.sh" --dry-run > "$T/o" 2>&1; rc=$?
ok "15 setup --dry-run: rc 0, shows copy, cron block with both lines, @reboot, writes nothing" '[ $rc = 0 ] && grep -q "dry run" "$T/o" && grep -q "17 0-2,4-23 \* \* \* SKIP_PRUNE=1" "$T/o" && grep -q "17 3 \* \* \* PATH" "$T/o" && grep -q "@reboot sleep 180" "$T/o" && [ ! -e "$T/cdir/scripts/backup" ] && [ "$before" = "$(crontab -l 2>/dev/null | md5sum)" ]'
bash "$AB/setup-offsite-backup.sh" --dry-run --schedule nightly --hour 2 > "$T/o" 2>&1; ok "15b nightly schedule: only the nightly line + @reboot" '! grep -q SKIP_PRUNE "$T/o" && grep -q "17 2 \* \* \* PATH" "$T/o"'
bash "$AB/setup-offsite-backup.sh" --dry-run --hour 0 > "$T/o" 2>&1; ok "15c hour 0 -> hourly lines cover 1-23" 'grep -q "17 1-23 \* \* \* SKIP_PRUNE=1" "$T/o"'
mkdir -p "$T/nobin"; for c in bash python3 dirname readlink awk grep sed mkdir cp cat stat date uname crontab env sh; do p=$(command -v $c) && ln -sf "$p" "$T/nobin/$c"; done
PATH="$T/nobin" bash "$AB/setup-offsite-backup.sh" --dry-run --no-cron > "$T/o" 2>&1; ok "16 no restic -> --dry-run only warns, mentions the install" 'grep -q "restic is NOT installed" "$T/o"' 
PATH="$T/nobin" bash "$AB/setup-offsite-backup.sh" --no-cron --no-copy > "$T/o" 2>&1; rc=$?; ok "16b no restic, real run -> rc 3" '[ $rc = 3 ]'
bash "$AB/setup-offsite-backup.sh" --bogus > "$T/o" 2>&1; ok "17 unknown flag -> rc 2" '[ $? = 2 ]'
bash "$AB/setup-offsite-backup.sh" --dry-run --uninstall > "$T/o" 2>&1; ok "17b uninstall --dry-run -> rc 0, changes nothing" '[ $? = 0 ] && [ "$before" = "$(crontab -l 2>/dev/null | md5sum)" ]'
# 18 supervisor json shape
python3 - "$AB/supervisor-checks.json" > "$T/o" 2>&1 <<'P'
import json,sys
cs=json.load(open(sys.argv[1]))["checks"]
assert len(cs)==2 and all(c["kind"]=="cmd" and c.get("only_if_exists") and "__CLAUDE_DIR__" in c["cmd"] for c in cs)
P
ok "18 supervisor-checks.json: 2 cmd checks, each with only_if_exists" '[ $? = 0 ]'
[ $REC_MADE = 0 ] && rm -f "$AB/scripts/RECOVERY.md"
echo "offsite-backup: $pass pass, $fail fail"; [ $fail = 0 ]
