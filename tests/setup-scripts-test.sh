#!/usr/bin/env bash
# setup-releaser.sh and setup-git-guard.sh: --dry-run changes nothing, real refusals work. git-guard user-scope install is
# exercised for real in a temp HOME (it only creates a symlink there). SR=, SG=<path> test other copies.
set -u
HERE=$(dirname "$(readlink -f "$0")")
SR=${SR:-$HERE/../scripts/setup-releaser.sh}; SG=${SG:-$HERE/../scripts/setup-git-guard.sh}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_RELEASER_STATE="$T/state" CCM_RELEASER_USER=ccm-test-releaser-$$
mkdir -p "$HOME" "$T/ws"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; sed 's/^/   /' "$T/out" 2>/dev/null | tail -8; fi; }
before=$(find /etc/sudoers.d /etc/cron.d -type f 2>/dev/null | sort | xargs -r md5sum; getent passwd | wc -l)
bash "$SR" --dry-run --owner "$(id -un)" --sudo-cmd /usr/bin/systemctl --cron > "$T/out" 2>&1; rc=$?
ok "1 releaser --dry-run -> rc 0, announces every change" '[ $rc = 0 ] && grep -q "dry run" "$T/out" && grep -q "useradd --system" "$T/out" && grep -q "NOPASSWD: /usr/bin/systemctl" "$T/out" && grep -q "/etc/cron.d/ccm-releaser" "$T/out"'
after=$(find /etc/sudoers.d /etc/cron.d -type f 2>/dev/null | sort | xargs -r md5sum; getent passwd | wc -l)
ok "1b dry run changed nothing: no user, no state dir, no sudoers/cron files" '[ "$before" = "$after" ] && [ ! -e "$T/state" ] && ! id "$CCM_RELEASER_USER" >/dev/null 2>&1'
bash "$SR" --dry-run --owner "$(id -un)" --cron > "$T/out" 2>&1; ok "1c the cron lines carry the three jobs" 'grep -q "releaser.py run" "$T/out" && grep -q "project_drift.py" "$T/out" && grep -q "repo_stale.py" "$T/out" && grep -q "\*/5 \* \* \* \*" "$T/out"'
bash "$SR" --dry-run --owner "$(id -un)" > "$T/out" 2>&1; ok "1d without --cron: prints the lines to add, writes none" 'grep -q "cron not installed" "$T/out"'
bash "$SR" --dry-run --owner "$(id -un)" --sudo-cmd 'systemctl restart *' > "$T/out" 2>&1; rc=$?; ok "2 a wildcard / relative sudo command -> rc 2" '[ $rc = 2 ]'
bash "$SR" --dry-run --owner no-such-user-$$ > "$T/out" 2>&1; rc=$?; ok "2b unknown owner -> rc 2" '[ $rc = 2 ]'
if [ "$(id -u)" != 0 ]; then bash "$SR" > "$T/out" 2>&1; rc=$?; ok "3 real run without root -> rc 5 and a clear line" '[ $rc = 5 ] && grep -q "must run as root" "$T/out"'; else pass=$((pass+1)); fi
bash "$SR" --bogus > "$T/out" 2>&1; ok "3b unknown flag -> rc 2" '[ $? = 2 ]'
# git-guard setup, user scope, real run in the temp HOME
D="$T/h/.local/bin"
bash "$SG" --dry-run > "$T/out" 2>&1; ok "4 git-guard --dry-run creates nothing" '[ ! -e "$D/git" ] && grep -q "ln -s" "$T/out"'
bash "$SG" --rc-file "$T/h/.bashrc" > "$T/out" 2>&1; ok "5 install: symlink to the guard, rc block appended when DIR is not first in PATH" '[ -L "$D/git" ] && [ "$(readlink -f "$D/git")" = "$(readlink -f "$HERE/../bin/git-guard")" ] && grep -q "ccm git-guard" "$T/h/.bashrc"'
bash "$SG" --rc-file "$T/h/.bashrc" > "$T/out" 2>&1; ok "5b idempotent: second run changes nothing, block not duplicated" '[ "$(grep -c ">>> ccm git-guard" "$T/h/.bashrc")" = 1 ] && grep -q "already points" "$T/out"'
out=$(PATH="$D:$PATH" bash -c 'type -a git | head -1'); ok "5c with DIR first in PATH the wrapper is the first git" '[[ "$out" == *"$D/git"* ]]'
out=$(cd "$T/ws" && git init -q . && PATH="$D:$PATH" CCM_REAL_GIT= git --version); ok "5d the installed symlink works as git (finds the real one)" '[[ "$out" == "git version"* ]]'
rm "$D/git"; echo "#!/bin/sh" > "$D/git"; bash "$SG" > "$T/out" 2>&1; rc=$?; ok "6 an existing foreign git in DIR is not overwritten -> rc 2" '[ $rc = 2 ] && grep -q "refusing to overwrite" "$T/out" && [ ! -L "$D/git" ]'
rm "$D/git"; bash "$SG" --rc-file "$T/h/.bashrc" > /dev/null 2>&1; bash "$SG" --uninstall --rc-file "$T/h/.bashrc" > "$T/out" 2>&1
ok "7 uninstall removes the symlink and the rc block" '[ ! -e "$D/git" ] && ! grep -q "ccm git-guard" "$T/h/.bashrc"'
if [ "$(id -u)" != 0 ]; then bash "$SG" --system > "$T/out" 2>&1; ok "8 --system without root -> rc 5" '[ $? = 5 ]'; else pass=$((pass+1)); fi
echo "setup-scripts: $pass pass, $fail fail"; [ $fail = 0 ]
