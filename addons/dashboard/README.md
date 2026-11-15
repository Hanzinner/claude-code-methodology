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
* Run it however you run small services: a terminal, `tmux`, or a `systemd --user` unit with
  `ExecStart=/usr/bin/python3 %h/.claude/addons/dashboard/dashboard.py`. It writes nothing, so it ships no setup script.

`install.sh --with-dashboard` copies this folder to `<claude dir>/addons/dashboard/`; nothing else. No supervisor
entry: the page is started by hand and has no fixed port to probe.

Test: `tests/dashboard-test.py` (temp status dir, random localhost port).

What the live system's much bigger control panel does beyond this is described in `CONCEPT.md`.
