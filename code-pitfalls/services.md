# services

systemd, cron, network, DNS, watchdogs, logs, backups.


### A network or service change: "done" only after a rollback written first, a real reboot, and the self-check log read
- **Symptom:** the network change "works right now", the agent says done; after the next reboot the machine has no internet or DNS for an hour, and the human repairs it by hand.
- **Why:** "works now" and a dry run check what is easy to check, not what breaks: the startup path after a reboot (a saved config that refuses to load, a DNS setting that only applies at boot).
- **Right way:** (1) write the rollback before the change and test it; (2) pass a real reboot, or a service restart proven to repeat the startup path; (3) read the self-check log yourself afterwards: address, route, DNS, a request outward, every path the human uses (editor remote session, sites, LAN). On a Linux VM use `net-change` (`./install.sh --with-net-change`): it schedules the rollback before the change and rolls back by itself if a check fails. Before replacing a NAT or bridge, list what is attached to it (port forwards, static mappings).
- **Seen:** once, about 3 hours of outage for the human.
### A dead DNS server first in `resolv.conf`
- **Symptom:** a bot/client crash-loops on timeouts (hundreds of restarts) though the network "is up"; every connection takes ~5 s.
- **Why:** the first nameserver is unreachable → every resolve waits exactly its timeout (5 s) and the client's own timeout fires first.
- **Right way:** measure resolve and connect separately (`time getent hosts …`); remove the dead resolver from `/etc/resolv.conf` AND from the source that generates it (`/etc/network/interfaces`).
- **Seen:** once.

### A watchdog stays silent when it can't see the object
- **Symptom:** a watchdog exits `exit 0` for a month while the object is down or unreachable.
- **Why:** "can't look" was coded as "nothing happened" (`if value is None: return`). The silence of a blind watchdog is identical to health.
- **Right way:** signal both "the object is bad" and "I can't see the object": N consecutive ticks without contact → alert "watchdog is blind"; a successful read resets the counter. Who watches the watchdogs — a heartbeat.
- **Seen:** once.

### Configs keep the old address after a network change
- **Symptom:** SSH, watchdogs and aliases aim at a dead address; everything breaks quietly, one by one.
- **Why:** the address is scattered across configs, notes and `~/.ssh/config`; the move updated the network, not the mentions.
- **Right way:** after a network change `grep -r` the old address across configs, `~/.ssh/config` and docs, and migrate all of them; check the gateway with `ip route | grep default`.
- **Seen:** 2 times (one case: 17 mentions).

### A log without rotation
- **Symptom:** a service log grew to hundreds of MB.
- **Why:** a crash loop writes on every restart, logrotate isn't configured.
- **Right way:** logrotate with a size limit for every new service log file.
- **Seen:** once (440 MB).

### Cron gives a minimal `PATH`
- **Symptom:** a script works by hand, fails under cron; fixing one binary just moves the failure to the next.
- **Why:** cron provides `/usr/bin:/bin`; `~/.cargo/bin`, `/usr/sbin`, `/usr/local/bin` (where the git wrapper lives!) are missing. A manual "live" run from your own shell never goes through cron's path.
- **Right way:** set `PATH` explicitly in the script (with `/usr/local/bin` first, so the wrapper isn't bypassed); accept it by a run from cron itself.
- **Seen:** once (a release runner never built even once).

### A cron repeats a no-op or a failure forever and spams
- **Symptom:** every 5 minutes the same heavy work (a ~4 min build) or the same FAIL in an inbox ×10.
- **Why:** the input marker isn't removed when the action is already done/impossible; failure messages aren't deduplicated.
- **Right way:** idempotency at the input (already in master → NO-OP, remove the marker, tell the author); FAIL dedup by a `sha|reason` fingerprint.
- **Seen:** 2 times.

### A killed process left a lock in an external system
- **Symptom:** the main job runs, but a tail step (nightly `restic prune`) fails for 11 days with `repository is already locked` — and nobody sees it.
- **Why:** a killed restic process left the lock in the cloud repo, not on the VM; a failing tail step doesn't alarm.
- **Right way:** `restic unlock` before prune (removes only stale locks). Wider: when you kill a process, immediately ask "what did it hold and WHERE" (locks, temp files in other systems); failure of any step → an alert, not a line deep in a log.
- **Seen:** once.

### The service listens only on the LAN address
- **Symptom:** `curl` to localhost → refused → "service is down", though it is alive.
- **Why:** the service is bound to a specific network address, not to loopback.
- **Right way:** before declaring a channel dead, `ss -ltnp | grep <port>` and knock at the address it actually listens on.
- **Seen:** once.

### Infrastructure chosen by name, not by config
- **Symptom:** a file was put into a "sync" folder and never arrived; then a loop over blocked workaround channels.
- **Why:** a `Sync/` folder looked like a channel, but the sync config doesn't contain it (dead for months).
- **Right way:** before using a channel (folder, port, service, alias), one command that proves it is alive (for Syncthing: grep `<folder … path=…>` in `config.xml`).
- **Seen:** once.

### A firewall is stronger than the rule — it cuts the wrong ones
- **Symptom:** a ban meant for agent sessions broke a deploy robot.
- **Why:** a rule about SESSIONS was implemented with `nft`, which sees only PACKETS and can't tell an agent from a cron; an "exception for a file" is also invisible to a packet filter.
- **Right way:** a tool of the same granularity as the rule: about sessions → a hook (cron scripts have no hooks and pass by construction); about files → something that sees files.
- **Seen:** once.

### WireGuard: interface name = config name
- **Symptom:** the kill-switch cuts the tunnel itself.
- **Why:** the rules were written for `wg0`, but `wg-quick@<name>` creates an interface called `<name>`.
- **Right way:** use the config name in iptables/ip rule; check with `ip link` after `wg-quick up`.
- **Seen:** once.

### Files created by root are unreachable to automation under another user
- **Symptom:** crons/services under a regular user silently fail on write; thousands of root-owned files.
- **Why:** agents run as root → every new file is root-owned, `umask 022` → the other user can't write; a `chown -R` patch on two folders left the rest full of holes.
- **Right way:** ACL inheritance on the tree root: `setfacl -R -m u:<user>:rwX -m d:u:<user>:rwX <tree>` (a new root outside the covered ones needs its own). A patch on one folder is a signal the class is still open. "My logs are clean" ≠ "the swarm is clean" — measure where it hurts. The git side: see [git.md](git.md).
- **Seen:** once.

### Restarting a web service while a person is on the page = "the site glitches"
- **Symptom:** a person clicks a button — no response or the page "reloads"; the service log shows a restart in exactly those minutes.
- **Why:** deploy without looking whether anyone is using it right now.
- **Right way:** before a restart check the last HUMAN request in the access log (`/var/log/nginx/access.log`, filtered by the client IP; `grep -v HeadlessChrome` isn't enough — your own curl gets in too); less than 2 minutes ago — wait. Compute the time WITH the time zone: `datetime.strptime(t, "%d/%b/%Y:%H:%M:%S %z")` against `datetime.now(timezone.utc)`. `date -d` without the zone on a VM at +04 gave "quiet for 8 h" at a real 90 s — and a restart in the middle of clicks. And don't `location.reload()` after UI actions — move the DOM on the client.
- **Seen:** once.

### State sync at service start overwrites changes made another way
- **Symptom:** after every restart a service "restores" its state on another machine (a pause flag etc.) and wipes what was set there by hand or by another agent.
- **Why:** "what I already applied" lives in a process variable (`last = None`) → the new process considers everything unapplied and pushes state.
- **Right way:** mirror the CHANGE, not the state: keep the version/hash of the last applied on disk; the first start only remembers. And one source of truth for the flag.
- **Seen:** once.

### A service runs from the developer's working directory — unfinished work reaches people past the deploy gate
- **Symptom:** a deploy script with tests exists, but a person sees a half-built page / a timer runs unreleased code.
- **Why:** the server reads static files from disk on every request, a oneshot timer imports code on every run, `Restart=on-failure` picks up whatever is on disk — the "gate" guards only a manual restart.
- **Right way:** services and timers run from a release copy (`WorkingDirectory=…/live`, a symlink to the release tree, switched only by the deploy script after tests); rollback = the symlink back.
- **Seen:** once.

### The trash directory is owned by root (755) — a process under a regular user can't `mv` into it
- **Symptom:** a script that cleans up "into the trash" fails with Permission denied when run via `runuser -u <user>`.
- **Why:** the directory was created by root; the user has no write access.
- **Right way:** run such steps as root and `chown` the created entry afterward; check with `runuser -u <user> -- test -w <trash dir>`.
- **Seen:** once.

### rsync through `rrsync` (a forced ssh command): the destination must be a DIRECTORY with a trailing slash
- **Symptom:** `rsync -t file host:app/.code-sha` (or `--mkpath … host:app/state/file`) through a key with `command="rrsync /srv/x"` fails with "delete_file: unlink(4) failed: Operation not permitted … could not make way for new regular file: 4", rc 23. Locally (no ssh) the same call works, so a hermetic test is blind to it.
- **Why:** rrsync rewrites path arguments; a file path as a destination is handled differently than by a plain rsync server.
- **Right way:** always target a directory: `rsync file host:app/state/` (name taken from the source), `--mkpath` only for directories. A missing source on the remote side through rrsync is **rc 12** "No such file or directory" (not 23 as locally) — check "no file" against both codes. Verify with a run through a real ssh+rrsync, not a test with a local directory.
- **Seen:** once.

### sshd in a container refuses a key login: "User X not allowed because account is locked"
- **Symptom:** key login to a container user fails although the key is right; the sshd log says the account is locked.
- **Why:** `useradd` without a password puts `!` in shadow = locked account; sshd with `UsePAM no` (the container default) refuses even a valid key.
- **Right way:** `usermod -p '*' <user>` — no password, but the account is not locked.
- **Seen:** once.

### A container's launcher lives in code that arrives later — the container loops on restart with rc 2
- **Symptom:** compose `command: sh deploy/run-on-code.sh`, but the code appears in the volume only after the first sync → "no such file", and `restart: unless-stopped` keeps looping.
- **Right way:** launchers and workers are `COPY`-ed into the image (`/opt/…`) and WAIT for the code (a `.code-sha` marker); they are not part of it.
- **Seen:** once.
