# dashboard - a minimal status page for your agents

With several agents in several terminal tabs you cannot tell at a glance who is working, who finished, and who is
waiting for your answer. Layer 2 ships `hooks/agent-status.py`, which writes one small file per agent:

```
~/.claude/agent-status/<agent>.json
{"agent": "...", "state": "WORKING|DONE|ASK", "ask": "<the question>", "session": "...", "updated": <unix>, "updated_iso": "..."}
```

`dashboard.py` is the smallest thing that turns those files into a page: one tile per agent, colour by state, how long
ago it changed, the question text for `ASK`, refresh every 5 s. Python standard library only, read-only.

```
python3 addons/dashboard/dashboard.py                 # http://127.0.0.1:8765/
python3 addons/dashboard/dashboard.py --print         # the same data as JSON, no server
python3 addons/dashboard/dashboard.py --port 9000 --stale-min 45
```

* A tile that says `WORKING` for longer than `--stale-min` (default 30) is shown as **stale**: the session most likely
  died before it could write `DONE`.
* `ASK` tiles sort first - they are the ones waiting for you.
* The page has **no login** and shows question text agents typed. It binds to localhost by default; to reach it from
  another device, put your own authenticating reverse proxy in front instead of changing `--bind` to `0.0.0.0`.
* `setup-dashboard.sh` keeps it running: a `systemd --user` unit `ccm-dashboard.service` (enabled and started), and
  `loginctl enable-linger` so it starts after a reboot and keeps running after you log out (no root; when linger needs
  root it prints the `sudo loginctl enable-linger <you>` line). `--port N`, `--dry-run`; `--uninstall` stops it and moves
  the unit file to the trash. Where there is no systemd (macOS, a container) it sets up nothing and prints how to
  start the page by hand.

`install.sh --with-dashboard` copies this folder to `<claude dir>/addons/dashboard/` and runs `setup-dashboard.sh`
(not for an install into a temp dir or with `--no-cron`: nothing is started in the background then). No supervisor
entry: the port can be changed, so there is no fixed one to probe.

Tests: `tests/dashboard-test.py` (temp status dir, random localhost port); the setup: `tests/install-addons-test.sh`
in the repo (stand-in systemctl and loginctl).
