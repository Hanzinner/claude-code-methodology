# net-change - change the network config, roll back by itself unless it is proven good

The classic way to lock yourself out of a remote machine: edit the network config, restart networking, the new
config is wrong, the SSH session dies, and nobody is there to undo it. `net-change` makes the undo happen without
you: it schedules the rollback **before** the change, so even if the change kills your connection, the machine
repairs itself in a few minutes. Optional add-on, off by default. Linux with systemd, root.

```
sudo net-change --dry-run -- <command>        # show what it would snapshot, run, restart and check
sudo net-change --wait 5 -- <command>         # e.g. -- sed -i s/old/new/ /etc/netplan/50-cloud-init.yaml
```

## How it works

1. takes a lock (one run at a time) and **snapshots** the config files/dirs (`CCM_NETCHANGE_FILES`) - if the snapshot
   fails, the change is not made;
2. **schedules the rollback first**, as a transient systemd timer (`systemd-run --on-active=<wait>min`). The rollback
   script is a self-contained file in the snapshot folder, so systemd runs it even if `net-change` and your session
   are gone;
3. runs **your command**, then **restarts the network stack** - a restart that fails counts as a failure (the config
   was not parsed; the running state is still the old one and would not survive a reboot);
4. **checks** that the network works: default gateway answers, a name resolves, optionally one TCP endpoint
   (put the host you SSH in from in `CCM_NETCHANGE_CHECK_TCP`, so "my own way in" is part of "good"). Three tries;
5. green -> stops the timer and verifies the rollback did not fire meanwhile -> **accepted** (exit 0). Red or any
   failure -> rolls back now (directories are restored whole, so files the change created disappear too), restarts the
   network, runs the optional rescue script (exit 1).

Exit codes: 0 accepted - 1 rolled back - 2 usage - 3 not started (lock, snapshot, scheduler, not root).
Log: `/var/log/net-change.log`; snapshots stay in `/var/lib/net-change/<time>-<pid>/` (nothing is deleted).

## Which network stack

Auto-detected, in this order: **netplan** (`netplan apply`), **NetworkManager**, **systemd-networkd**,
**ifupdown** (`/etc/network/interfaces` -> `systemctl restart networking`). The default snapshot covers the config
locations of all four plus `resolv.conf`, `hosts`, `dhcpcd.conf`; missing paths are recorded as absent (so a rollback
removes them if the change created them). Anything else: set `CCM_NETCHANGE_RESTART` and `CCM_NETCHANGE_FILES`.
`--dry-run` prints what was detected.

## Limits - read these

* Only **files** roll back. Runtime changes (`ip addr add`, iptables, `nft`) are not undone - put them in config.
* `--no-restart` skips the restart; the log then says plainly that surviving a reboot was NOT verified.
* The check proves the machine can reach its gateway/DNS/endpoint, not that your service works. Use
  `CCM_NETCHANGE_CHECK` for your own test (exit 0 = good).
* `--wait` must be at least `CCM_NETCHANGE_MIN_WAIT` (3 min): restart plus three checks take ~2 min and the timer must
  not outrun them. If it does, the log says ROLLED BACK, never ACCEPTED.
* A cloud-init or DHCP-managed machine may rewrite config at boot; that is outside what this tool sees.
* Keep a console / out-of-band way in anyway. This is a seat belt, not a second car.

## Settings

All optional; environment or `methodology.conf`: `CCM_NETCHANGE_FILES`, `_RESTART`, `_CHECK`, `_CHECK_HOST`
(example.com), `_CHECK_TCP`, `_RESCUE` (script run after a rollback, e.g. re-add a static address), `_STATE`, `_LOG`,
`_MIN_WAIT`, `_SETTLE` (5 s), `_RETRY_S` (10 s), `_SCHED` (`systemd`; `none` is for tests only).

## Install

`install.sh --with-net-change` copies this folder to `<claude dir>/addons/net-change/`; the system part is
`sudo setup-net-change.sh [--dry-run]` (links `net-change` into `/usr/local/bin`, creates the state dir;
`--uninstall` removes the link and keeps the state). The supervisor check in `supervisor-checks.json` warns if a
rollback timer is left pending.

## Tests

`tests/net-change-test.sh` - sandbox: configs in a temp dir, "the network is up" is a flag file, restart and rescue
are fakes; the real network is never touched. `NC_SYSTEMD=1` adds ~70 s of cases with real transient systemd timers
(they only roll back files in the temp dir): killed wrapper, timer outrunning the check, another run's rollback pending.
