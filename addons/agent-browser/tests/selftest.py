#!/usr/bin/env python3
"""Self-check of br on a live agent browser. One fixture - one rule - one expected marker.
Run: br selftest. Last line: "selftest: N/N" and exit 0, or the list of failures and exit 1."""
import base64
import subprocess
import sys
from pathlib import Path

BR = str(Path(__file__).resolve().parent.parent / "br")

PAGE = """<!doctype html><meta charset=utf-8><title>fx</title><h1>Fixture A</h1>
<button onclick="document.title='clicked-go'">Go</button>
<button onclick="document.title='dup-1'">Dup</button><p>between</p><button onclick="document.title='dup-2'">Dup</button>
<form onsubmit="document.title='submitted:'+this.n.value;return false"><label>Name <input name=n></label></form>
<p id=long></p><script>document.getElementById('long').textContent='lorem '.repeat(400)</script>
<canvas id=c width=200 height=100 style="position:fixed;right:0;top:0;background:#ccc"
 onclick="document.title='canvas:'+event.isTrusted"></canvas>
<button style="margin-top:3000px;display:block" onclick="document.title='deep'">Deep</button>"""
URL = "data:text/html;base64," + base64.b64encode(PAGE.encode()).decode()


def br(*a, stdin=None):
    p = subprocess.run([BR, *a], capture_output=True, text=True, timeout=90, input=stdin)
    return p.returncode, p.stdout + p.stderr


def title():
    return br("js", "document.title")[1]


def fresh():
    br("open", URL)


results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(("  ok  " if ok else "  FAIL") + f" {name}" + ("" if ok else f" — {detail[:200]}"))


rc, out = br("health");                 check("health: browser answers", rc == 0 and "Chrome/" in out, out)
rc, out = br("open", URL);              check("open: page opened", rc == 0, out)
rc, out = br("text");                   check("text: heading visible", "Fixture A" in out and "untrusted" in out, out)
rc, out = br("text", "50");             check("text: long text is cut with a note", "cut:" in out, out)
rc, out = br("snap");                   check("snap: catalogue with labels", "ref=e" in out, out)
rc, out = br("click", "Go");            check("click: one match - action", rc == 0 and "clicked-go" in title(), out)
rc, out = br("click", "Dup");           check("click: two matches - code 2, no action", rc == 2 and "dup-" not in title(), f"rc={rc} {out}")
rc, out = br("click", "Dup", "--nth", "2"); check("click --nth: second chosen", rc == 0 and "dup-2" in title(), out)
rc, out = br("click", "Nope");          check("click: no match - code 3", rc == 3, f"rc={rc} {out}")
rc, out = br("click", "@");             check("click: empty label - refused", rc == 1, f"rc={rc} {out}")
fresh()
rc, out = br("click", "Deep");          check("click: element below the window", rc == 0 and "deep" in title(), out)
fresh()
rc, out = br("fill", "Name", "Ada Lovelace")
val = br("js", "document.querySelector('input').value")[1]
check("fill: text into a field by its label", rc == 0 and "Ada Lovelace" in val, out + val)
rc, out = br("key", "Enter");           check("key: Enter submits the form", "submitted:Ada Lovelace" in title(), out + title())
fresh()
w = int(br("js", "innerWidth")[1].split("\n")[1])
rc, out = br("xy", str(w - 100), "50"); check("xy: trusted click on a canvas without an element tree", rc == 0 and "canvas:true" in title(), out + title())
rc, out = br("xy", "99999", "5");       check("xy: point outside the window - refused", rc == 1, f"rc={rc} {out}")
shot = Path("/tmp/br-selftest.png"); shot.unlink(missing_ok=True)
rc, out = br("shot", str(shot));        check("shot: screenshot file written", rc == 0 and shot.exists() and shot.stat().st_size > 1000, out)
shot.unlink(missing_ok=True)
rc, out = br("open", "javascript:alert(1)"); check("open: dangerous scheme - refused", rc == 1, f"rc={rc} {out}")
# --- recipe runner: a one-off program on the same test page ---
import json
RECIPES = Path(BR).parent / "recipes"
steps_ok = [{"do": "open", "url": URL}, {"do": "click", "target": "Go"}, {"do": "js", "expr": "document.title + ':' + {who}"}]
rc, out = br("plan", "who=a\"b", stdin=json.dumps({"steps": steps_ok}))
check("plan: steps run, a parameter in js is a quoted string", rc == 0 and 'clicked-go:a"b' in out, f"rc={rc} {out}")
rc, out = br("plan", stdin=json.dumps({"steps": [{"do": "open", "url": URL}, {"do": "click", "target": "Nope"}]}))
check("plan: a failure names the step and shows page elements", rc == 3 and "step 2 «click»" in out and "ref=e" in out, f"rc={rc} {out}")
rc, out = br("plan", stdin=json.dumps({"steps": [{"do": "shell", "cmd": "id"}]}))
check("plan: action outside the list - refused", rc == 1 and "unknown action" in out, f"rc={rc} {out}")
rc, out = br("plan", stdin=json.dumps({"steps": [{"do": "open", "url": URL}]}))
check("plan: empty result - an error, not silence", rc == 3, f"rc={rc} {out}")
tmp = RECIPES / "zz.selftest.json"; tmp.unlink(missing_ok=True)
rc, out = br("plan", "--save", "zz.selftest", stdin=json.dumps({"steps": steps_ok[:2] + [{"do": "js", "expr": "document.title"}], "check": {"args": {}, "expect": "no-such-text"}}))
check("plan --save: failed control example - recipe not saved", rc == 1 and not tmp.exists(), f"rc={rc} {out}")
rc, out = br("plan", "--save", "zz.selftest", stdin=json.dumps({"steps": steps_ok[:2] + [{"do": "js", "expr": "document.title"}], "check": {"args": {}, "expect": "clicked-go"}}))
check("plan --save: example passed - recipe saved", rc == 0 and tmp.exists(), f"rc={rc} {out}")
rc, out = br("run", "zz.selftest");     check("run: saved recipe works", rc == 0 and "clicked-go" in out, f"rc={rc} {out}")
tmp.unlink(missing_ok=True)
rc, out = br("run", "no.such.recipe");     check("run: no such recipe - code 3", rc == 3, f"rc={rc} {out}")
br("open", "about:blank")

bad = [n for n, ok in results if not ok]
print(f"selftest: {len(results) - len(bad)}/{len(results)}")
sys.exit(1 if bad else 0)
