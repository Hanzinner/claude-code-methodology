#!/usr/bin/env bash
# net-change in a SANDBOX: configs live in a temp dir, "the network is up" is a flag file, restart and rescue are fakes.
# The real network is never touched. NC=path tests another copy. NC_SYSTEMD=1 adds ~70 s of tests with real transient
# systemd timers (they only roll back files in the temp dir). Last line: net-change-test: N pass, M fail.
set -u
NC=${NC:-$(dirname "$(readlink -f "$0")")/../net-change}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
pass=0; fail=0
nc() { "$NC" "$@" >>"$T/out" 2>&1; }
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; tail -5 "$T/log" 2>/dev/null; tail -5 "$T/out" 2>/dev/null; fi; }
CFG="$T/etc/interfaces"; RES="$T/etc/resolv.conf"; NEWF="$T/etc/new.conf"; DIR="$T/etc/interfaces.d"
fresh() { rm -rf "$DIR" "$T/state"; mkdir -p "$T/etc" "$DIR"; printf 'iface eth0 inet static\n  address 10.0.0.10/24\n' > "$CFG"; printf 'nameserver 1.1.1.1\n' > "$RES"; rm -f "$NEWF" "$T/rescued"; : > "$T/log"; touch "$T/net-up"; }
# "the network works" while the config has the right address and resolv.conf is not empty; the restart "applies" it
export CCM_NETCHANGE_MIN_WAIT=1 CCM_NETCHANGE_FILES="$CFG $RES $NEWF $DIR" CCM_NETCHANGE_STATE="$T/state" CCM_NETCHANGE_LOG="$T/log" \
       CCM_NETCHANGE_SCHED=none CCM_NETCHANGE_SETTLE=0 CCM_NETCHANGE_RETRY_S=0 CCM_NETCHANGE_RESCUE="$T/rescue.sh" \
       CLAUDE_METHODOLOGY_CONF=/nonexistent HOME="$T/home" \
       CCM_NETCHANGE_RESTART="grep -q 10.0.0.10 $CFG && grep -q nameserver $RES && touch $T/net-up || rm -f $T/net-up; echo restart >> $T/restarts" \
       CCM_NETCHANGE_CHECK="test -e $T/net-up"
BRK="sed -i 's/10.0.0.10/192.168.100.10/' $CFG"   # breaks the address
printf '#!/bin/bash\necho rescue >> %s/rescued\n' "$T" > "$T/rescue.sh"; chmod +x "$T/rescue.sh"

fresh; nc --wait 1 -- bash -c "echo '# a comment' >> $CFG"; rc=$?
ok "1 harmless change -> rc 0, accepted AFTER a restart" '[ $rc = 0 ] && grep -q "AFTER a network restart" "$T/log" && grep -q comment "$CFG"'

fresh; nc --wait 1 -- bash -c "$BRK"; rc=$?
ok "2 broken address -> rc 1, rolled back, config as before" '[ $rc = 1 ] && grep -q "10.0.0.10" "$CFG" && ! grep -q 192.168 "$CFG"'
ok "2b log says rollback and that the network is back" 'grep -q "ROLLBACK" "$T/log" && grep -q "ROLLED BACK: the network is back" "$T/log"'
ok "2c the rescue script was called after the rollback" '[ -s "$T/rescued" ]'

fresh; nc --wait 1 -- bash -c ": > $RES"; rc=$?
ok "3 empty resolv.conf -> rollback, DNS back" '[ $rc = 1 ] && grep -q "nameserver 1.1.1.1" "$RES"'

fresh; nc --wait 1 -- bash -c "echo x > $NEWF; $BRK"; rc=$?
ok "4 change created a NEW file and broke the network -> rollback removes the new file" '[ $rc = 1 ] && [ ! -e "$NEWF" ]'

fresh; nc --wait 1 -- false; rc=$?
ok "5 change command failed -> rc 1, rollback" '[ $rc = 1 ] && grep -q "the change command failed" "$T/log"'

fresh; nc --wait 1 --no-restart -- true; rc=$?
ok "6 --no-restart -> rc 0 but the log says honestly: reboot-survival NOT verified" '[ $rc = 0 ] && grep -q "NOT verified" "$T/log"'

nc -- ; ok "7 no command -> rc 2" '[ $? = 2 ]'

fresh; CCM_NETCHANGE_RESTART="false" nc --wait 1 -- true; rc=$?
ok "R1 network restart failed -> NOT accepted, rollback, rc 1" '[ $rc = 1 ] && grep -q "network restart failed" "$T/log" && ! grep -q "ACCEPTED" "$T/log"'
fresh; nc --wait 1 -- bash -c "echo 'iface eth0 inet dhcp' > $DIR/eth0; $BRK"; rc=$?
ok "R2 new file INSIDE a directory (interfaces.d) -> rollback removes it" '[ $rc = 1 ] && [ ! -e "$DIR/eth0" ] && [ -d "$DIR" ]'
fresh; CCM_NETCHANGE_STATE=/proc/nc-nope nc --wait 1 -- bash -c "$BRK"; rc=$?
ok "R4 snapshot failed -> rc 3, change NOT applied" '[ $rc = 3 ] && grep -q 10.0.0.10 "$CFG"'
fresh; mkdir -p "$T/state"; exec 8>"$T/state/.lock"; flock -n 8
nc --wait 1 -- bash -c "$BRK"; rc=$?; exec 8>&-
ok "R5 another run holds the lock -> rc 3, change NOT applied" '[ $rc = 3 ] && grep -q 10.0.0.10 "$CFG"'
fresh; CCM_NETCHANGE_MIN_WAIT=3 nc --wait 1 -- true; rc=$?
ok "R3a --wait below the minimum -> rc 2" '[ $rc = 2 ]'
nc --wait abc -- true; ok "R3b --wait not a number -> rc 2" '[ $? = 2 ]'
fresh; CCM_NETCHANGE_RESTART="grep -q \"10.0.0.10\" '$CFG' && touch '$T/net-up' || rm -f '$T/net-up'" nc --wait 1 -- bash -c "$BRK"; rc=$?
ok "R6 quotes in the restart command do not break the rollback script" '[ $rc = 1 ] && grep -q 10.0.0.10 "$CFG"'
fresh; nc --wait 1 -- bash -c 'sleep 600 >/dev/null 2>&1 &'; r1=$?
nc --wait 1 -- true; r2=$?; pkill -f '^sleep 600$' 2>/dev/null
ok "R8 a background process of the change does not hold the lock -> the next run passes" '[ $r1 = 0 ] && [ $r2 = 0 ]'
fresh; nc --wait 08 -- true; ok "R9 --wait 08 (leading zero) -> not an octal error, rc 0" '[ $? = 0 ]'

# --dry-run: prints the plan, changes nothing, needs no stack
fresh; out=$("$NC" --dry-run --wait 7 -- bash -c "$BRK"); rc=$?
ok "D1 --dry-run -> rc 0, shows plan, config untouched, nothing snapshotted" '[ $rc = 0 ] && echo "$out" | grep -q "timer after 7 min" && echo "$out" | grep -q "restart  : grep" && grep -q 10.0.0.10 "$CFG" && [ ! -d "$T/state" ]'
out=$(CCM_NETCHANGE_CHECK="" CCM_NETCHANGE_CHECK_TCP=10.0.0.1:22 "$NC" --dry-run -- true)
ok "D2 --dry-run shows the default check with the TCP endpoint" 'echo "$out" | grep -q "default (gateway, DNS, TCP 10.0.0.1:22)"'
out=$(CCM_NETCHANGE_RESTART="" "$NC" --dry-run -- true); ok "D3 --dry-run with no stack detected is still rc 0 and says what to set" '[ $? = 0 ] && echo "$out" | grep -q "restart  :"'
# the shipped script is English
ok "E1 no Cyrillic in the script or this test" '! grep -qP "[\x{0400}-\x{04FF}]" "$NC" "$0"'

# setup script: --dry-run only, sandboxed paths
SU=$(dirname "$NC")/setup-net-change.sh; mkdir -p "$T/bin"
out=$(NC_BIN_DIR="$T/bin" NC_STATE_DIR="$T/st" "$SU" --dry-run 2>&1); rc=$?
ok "U1 setup --dry-run prints the link and state dir, writes nothing" '[ $rc = 0 ] && echo "$out" | grep -q "ln -s" && [ -z "$(ls "$T/bin")" ] && [ ! -d "$T/st" ]'
out=$(NC_BIN_DIR="$T/bin" "$SU" --uninstall --dry-run 2>&1); ok "U2 setup --uninstall --dry-run keeps the state" '[ $? = 0 ] && echo "$out" | grep -q Kept'
"$SU" --bogus >/dev/null 2>&1; ok "U3 setup: unknown option -> rc 2" '[ $? = 2 ]'

if [[ "${NC_SYSTEMD:-0}" == 1 ]]; then
    fresh
    CCM_NETCHANGE_SCHED=systemd CCM_NETCHANGE_CHECK="sleep 300" setsid "$NC" --wait 1 -- bash -c "$BRK" >/dev/null 2>&1 &
    w=$!; sleep 4
    for c in $(ps -eo pid=,ppid= | awk -v p=$w '$2==p{print $1}'); do kill -9 "$c"; done; kill -9 "$w"
    for i in $(seq 1 12); do grep -q 10.0.0.10 "$CFG" && break; sleep 10; done
    ok "S1 wrapper killed -> the systemd timer rolled the config back by itself" 'grep -q 10.0.0.10 "$CFG" && grep -q ROLLBACK "$T/log"'
    fresh
    CCM_NETCHANGE_SCHED=systemd CCM_NETCHANGE_SETTLE=75 nc --wait 1 -- bash -c "$BRK"; rc=$?
    ok "S2 timer outran the check -> rc 1 and ROLLED BACK, not ACCEPTED" '[ $rc = 1 ] && grep -q "ROLLED BACK" "$T/log" && ! grep -q "ACCEPTED" "$T/log"'
    fresh
    systemd-run --unit=net-change-rollback-testhold --on-active=10min /bin/true >/dev/null 2>&1
    CCM_NETCHANGE_SCHED=systemd nc --wait 1 -- bash -c "$BRK"; rc=$?
    systemctl stop net-change-rollback-testhold.timer >/dev/null 2>&1
    ok "S3 someone else's rollback is pending -> rc 3, change NOT applied" '[ $rc = 3 ] && grep -q 10.0.0.10 "$CFG"'
fi
echo "net-change-test: $pass pass, $fail fail"; [ $fail = 0 ]
