#!/usr/bin/env python3
"""Is the reader up? Asks it on its own port (CCM_READER_PORT / CCM_READER_BIND from methodology.conf).
rc 0 = it answers; rc 1 = it does not (one line: where it asked, how to start it, where its log is).
--wait N: keep asking for up to N seconds (install.sh, right after starting it). Used by the supervisor too."""
import json, os, sys, time, urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.realpath(os.path.join(HERE, "..", "..", "lib")))
try:
    from ccm_conf import conf
except ImportError:
    def conf(key):
        return os.environ.get(key, "")

port = conf("CCM_READER_PORT") or "8001"
bind = conf("CCM_READER_BIND") or "127.0.0.1"
host = "127.0.0.1" if bind in ("0.0.0.0", "::", "localhost") else bind
url = f"http://{'[' + host + ']' if ':' in host else host}:{port}/api/last"
wait = float(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 0
end = time.time() + wait
while True:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            if r.status == 200 and "path" in json.loads(r.read().decode("utf-8")):
                print(f"reader answers: {url}")
                sys.exit(0)
            err = f"HTTP {r.status}, not the reader"
    except Exception as e:
        err = str(e)[:120]
    if time.time() >= end:
        break
    time.sleep(0.5)
print(f"reader does not answer at {url} ({err}). Start it: python3 {HERE}/reader-server.py "
      f">> ~/.claude/logs/reader.log 2>&1 &   (it starts by itself after a reboot from the crontab line install.sh added)")
sys.exit(1)
