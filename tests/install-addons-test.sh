#!/usr/bin/env bash
# install.sh and its add-on flags on a machine like a fresh server reached over ssh:
#  - claude sits in ~/.local/bin, which a non-login shell's PATH lacks -> install.sh still finds it;
#  - --with-agent-browser without node, npm and a Chrome/Chromium -> a "missing:" line for each, with the install hint;
#    without that flag not a word about them (lib/deps_check.py --addon);
#  - --with-dashboard -> a systemd --user unit for dashboard.py, enabled and started, and linger turned on; where linger
#    needs root the exact sudo line; where there is no systemd (macOS, a container) the install goes on and says how to
#    start the page by hand. addons/dashboard/setup-dashboard.sh itself: re-run, dry run, no user manager, --uninstall.
# systemctl and loginctl are stand-ins that only log (CCM_SYSTEMCTL / CCM_LOGINCTL): nothing on this machine is enabled.
# A fake bin dir links every command on PATH except claude, node, npm, the Chromes, systemctl, loginctl. Temp HOMEs.
# INSTALL=<path to install.sh> tests another copy (its folder must be a whole clone). Last line: install-addons-test: N pass, M fail.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
if [[ -z "${INSTALL:-}" ]]; then
  for c in "${CCM_REPO_DIR:-}" "$HERE/.."; do
    [[ -n "$c" && -f "$c/install.sh" && -f "$c/check-install.py" ]] && { INSTALL="$c/install.sh"; break; }
  done
fi
[[ -n "${INSTALL:-}" ]] || { echo "install-addons-test: SKIP (no clone with install.sh: set CCM_REPO_DIR=<clone> - nothing was tested)"; exit 0; }
REPO=$(cd "$(dirname "$INSTALL")" && pwd)
T=$(mktemp -d) && [[ -d "$T" && "$T" != / ]] || { echo "install-addons-test: no temp dir" >&2; exit 2; }
trap 'rm -rf "$T"' EXIT   # the temp dir this test made
for v in $(compgen -e | grep -e '^CCM_' -e '^CLAUDE_METHODOLOGY_' -e '^XDG_'); do unset "$v"; done   # this machine's settings would beat the test's
unset TAVILY_API_KEY EXA_API_KEY
export CCM_TEST=1
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | tail -25 | sed "s/^/   /"; fi; }
ME=$(id -un)

fakebin() {  # fakebin <dir> <names to leave out...> - a symlink to every other command on PATH (first one wins, as in PATH)
  local dir="$1" d f n dirs; shift; mkdir -p "$dir"
  local skip=" $* "
  IFS=: read -ra dirs <<<"$PATH"
  for d in "${dirs[@]}"; do
    [[ -d "$d" ]] || continue
    for f in "$d"/*; do
      n=${f##*/}
      [[ -f "$f" && -x "$f" && ! -e "$dir/$n" ]] || continue
      case "$skip" in *" $n "*) continue ;; esac
      ln -s "$f" "$dir/$n"
    done
  done
}
fakebin "$T/bin" claude node nodejs npm chromium chromium-browser google-chrome google-chrome-stable systemctl loginctl
# a CI Mac has Google Chrome.app: deps_check looks for app bundles here instead, so "no browser" holds on any machine
mkdir -p "$T/noapps"; export CCM_MAC_APPS="$T/noapps"

# stand-ins: every call goes to a log; $T/no-manager = no user manager; $T/linger-fails = enable-linger refused
mkdir -p "$T/fake"
cat > "$T/fake/systemctl" <<EOF
#!/bin/sh
echo "\$*" >> "$T/systemctl.log"
case "\$*" in
  *show-environment*) [ -e "$T/no-manager" ] && exit 1; echo "HOME=/x"; exit 0 ;;
  *is-active*) echo active ;;
esac
exit 0
EOF
cat > "$T/fake/loginctl" <<EOF
#!/bin/sh
echo "\$*" >> "$T/loginctl.log"
case "\$1" in
  show-user) [ -e "$T/linger-on" ] && echo yes || echo no ;;
  enable-linger) [ -e "$T/linger-fails" ] && { echo "Access denied" >&2; exit 1; }; touch "$T/linger-on" ;;
esac
exit 0
EOF
chmod +x "$T/fake/systemctl" "$T/fake/loginctl"
export CCM_SYSTEMCTL="$T/fake/systemctl" CCM_LOGINCTL="$T/fake/loginctl"

inst() {  # inst <home> <flags...> - the install as a person runs it over ssh: no questions, PATH without ~/.local/bin
  local h="$1"; shift
  HOME="$h" PATH="$T/bin" "$BASH" "$INSTALL" --user --yes --no-cron --no-verify --name tester --workspace "$h/ws" --timezone UTC "$@" 2>&1
}

# ---- one install: claude only in ~/.local/bin, agent-browser without its tools, dashboard with systemd ----
mkdir -p "$T/h1/.local/bin"
printf '#!/bin/sh\n[ "$1" = --version ] && echo "9.9.9 (Claude Code)"\nexit 0\n' > "$T/h1/.local/bin/claude"; chmod +x "$T/h1/.local/bin/claude"
out=$(inst "$T/h1" --with-dashboard --with-agent-browser); rc=$?
ok "1 install with --with-dashboard --with-agent-browser: exit 0 (rc=$rc)" '[ $rc = 0 ] && [ -f "$T/h1/.claude/settings.json" ]'
ok "2 claude only in ~/.local/bin, not in PATH -> found" 'grep -q "claude CLI found: 9.9.9" <<<"$out" && ! grep -q "claude CLI not found" <<<"$out"'
ok "3 no node/npm/Chromium -> a 'missing:' line for each, naming the add-on" \
   'grep -q "^ *missing: node — agent-browser" <<<"$out" && grep -q "^ *missing: npm — agent-browser" <<<"$out" && grep -q "^ *missing: chromium — agent-browser" <<<"$out"'
ok "4 ... and the install line has the packages (apt nodejs npm chromium, brew node)" \
   'l=$(grep "^ *install: apt install" <<<"$out"); grep -q "nodejs" <<<"$l" && grep -q " npm" <<<"$l" && grep -q "chromium" <<<"$l" && grep -q "brew install.* node" <<<"$l"'
ok "5 the end repeats them" 'grep "Missing system commands:" <<<"$out" | grep -q "node npm chromium"'
U="$T/h1/.config/systemd/user/ccm-dashboard.service"
ok "6 a systemd --user unit for dashboard.py on 127.0.0.1:8765, wanted by default.target" \
   '[ -f "$U" ] && grep -q "^ExecStart=\"/.*python3*\" \"$T/h1/.claude/addons/dashboard/dashboard.py\" --port 8765$" "$U" && grep -q "^WantedBy=default.target$" "$U"'
ok "7 daemon-reload, enable, restart (a new unit) - all --user" \
   'grep -qx -- "--user daemon-reload" "$T/systemctl.log" && grep -qx -- "--user enable ccm-dashboard.service" "$T/systemctl.log" && grep -qx -- "--user restart ccm-dashboard.service" "$T/systemctl.log"'
ok "8 linger turned on for this user" 'grep -qx "enable-linger $ME" "$T/loginctl.log" && grep -q "enable-linger $ME - it runs after a reboot" <<<"$out"'
ok "9 says it runs and where" 'grep -q "dashboard: running as ccm-dashboard.service - http://127.0.0.1:8765/" <<<"$out"'

# ---- setup-dashboard.sh on its own (the installed copy) ----
SD="$T/h1/.claude/addons/dashboard/setup-dashboard.sh"
sd() { HOME="$T/h1" PATH="$T/bin" bash "$SD" "$@" 2>&1; }
: > "$T/systemctl.log"; before=$(cat "$U")
out=$(sd --python python3); rc=$?
ok "10 re-run: unit unchanged, start (not restart), linger already on (rc=$rc)" \
   '[ $rc = 0 ] && grep -q "already up to date" <<<"$out" && grep -qx -- "--user start ccm-dashboard.service" "$T/systemctl.log" && ! grep -q restart "$T/systemctl.log" && grep -q "linger already on" <<<"$out" && [ "$(cat "$U")" = "$before" ]'
rm -f "$T/linger-on"; touch "$T/linger-fails"
out=$(sd --python python3); rc=$?
ok "11 linger refused without root -> exit 0 and the exact sudo line (rc=$rc)" '[ $rc = 0 ] && grep -q "Run once: sudo loginctl enable-linger $ME$" <<<"$out"'
rm -f "$T/linger-fails"
: > "$T/systemctl.log"
out=$(sd --python python3 --port 9001 --dry-run); rc=$?
ok "12 dry run: prints the new unit, changes nothing (rc=$rc)" \
   '[ $rc = 0 ] && grep -q "\[dry-run\] would write" <<<"$out" && grep -q -- "--port 9001" <<<"$out" && [ "$(cat "$U")" = "$before" ] && ! grep -qv "show-environment" "$T/systemctl.log"'
touch "$T/no-manager"; mkdir -p "$T/h4"
out=$(HOME="$T/h4" PATH="$T/bin" bash "$SD" 2>&1); rc=$?
ok "13 systemctl there but no user manager (container, no login session): exit 0, no unit, how to start by hand (rc=$rc)" \
   '[ $rc = 0 ] && grep -q "user manager is not reachable" <<<"$out" && grep -q "start it by hand: nohup " <<<"$out" && [ ! -e "$T/h4/.config/systemd/user/ccm-dashboard.service" ]'
rm -f "$T/no-manager"
: > "$T/systemctl.log"
out=$(HOME="$T/h1" PATH="$T/bin" CCM_TRASH_DIR="$T/trash" bash "$SD" --uninstall 2>&1); rc=$?
ok "14 --uninstall: disable --now, the unit moved to the trash, not deleted (rc=$rc)" \
   '[ $rc = 0 ] && grep -qx -- "--user disable --now ccm-dashboard.service" "$T/systemctl.log" && [ ! -e "$U" ] && ls "$T/trash"/ccm-dashboard.service.* >/dev/null 2>&1'

# ---- a machine without systemd (macOS, a container), no claude anywhere, no agent-browser ----
mkdir -p "$T/h2"
out=$(CCM_SYSTEMCTL="$T/none/systemctl" inst "$T/h2" --with-dashboard); rc=$?
ok "15 no systemd: the install goes on, exit 0, and says how to start the page by hand (rc=$rc)" \
   '[ $rc = 0 ] && grep -q "no systemd on this machine" <<<"$out" && grep -q "start it by hand: nohup .*dashboard.py --port 8765" <<<"$out" && [ ! -e "$T/h2/.config/systemd/user/ccm-dashboard.service" ]'
ok "16 without --with-agent-browser: not a word about node, npm, Chromium" '! grep -q -e "missing: node" -e "missing: npm" -e "missing: chromium" <<<"$out"'
ok "17 control: no claude in PATH or ~/.local/bin -> 'not found'" 'grep -q "claude CLI not found" <<<"$out"'

# a temp install dir without both stand-ins: nothing in the background, the command to do it is printed
mkdir -p "$T/h3"
out=$(CCM_LOGINCTL="" inst "$T/h3" --with-dashboard); rc=$?
ok "18 --no-cron / temp dir: the service is not set up, the setup command is printed (rc=$rc)" \
   '[ $rc = 0 ] && grep -q "dashboard not started (--no-cron" <<<"$out" && grep -q "setup-dashboard.sh" <<<"$out" && [ ! -e "$T/h3/.config/systemd/user/ccm-dashboard.service" ]'

# ---- lib/deps_check.py --addon on its own ----
mkdir -p "$T/tools"; for n in node npm chromium; do printf '#!/bin/sh\nexit 0\n' > "$T/tools/$n"; chmod +x "$T/tools/$n"; done
out=$(PATH="$T/tools:$T/bin" python3 "$REPO/lib/deps_check.py" --addon agent-browser 2>&1)
ok "19 deps_check --addon agent-browser with node, npm and chromium there -> no line about them" '! grep -q -e "missing: node" -e "missing: npm" -e "missing: chromium" <<<"$out"'
out=$(PATH="$T/bin" python3 "$REPO/lib/deps_check.py" --addon no-such-addon 2>&1); rc=$?
ok "20 an unknown add-on name is said, not taken for 'nothing missing'; still exit 0 (rc=$rc)" '[ $rc = 0 ] && grep -q "usage:" <<<"$out"'

echo "install-addons-test: $pass pass, $fail fail"; [ $fail = 0 ]
