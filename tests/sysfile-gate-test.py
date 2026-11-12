#!/usr/bin/env python3
"""sysfile-gate: destructive commands on system paths -> deny (1), everything else passes (0).
Runs the repo copy; SF=<path> tests another one. Sandbox: temp HOME, no config file."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SF = os.environ.get("SF", os.path.join(HERE, "..", "hooks", "sysfile-gate.py"))
ENV = {**os.environ, "HOME": tempfile.mkdtemp(prefix="sf-test-"), "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "HANZ_TEST": "1"}
C = [
    ("rm -f /dev/null", 1), ("sudo rm -f /dev/null", 1), ("sudo -n rm /dev/null", 1),
    ("sudo -u root timeout -k 3 10 rm /dev/null", 1), ("mv /dev/null /tmp/x", 1),
    ("cp foo /dev/null", 1), ("ln -sf x /etc/resolv.conf", 1), ("sed -i s/a/b/ /etc/hosts", 1),
    ("rm -rf /etc/nginx", 1), ("dd if=/dev/zero of=/dev/sda bs=1M", 1), ("cd /tmp && rm -f /boot/vmlinuz", 1),
    ("echo a; rm /dev/null", 1), ("ls\nrm -f /dev/null", 1), ("(cd /; rm /dev/null)", 1),
    ("ls >/dev/null 2>&1", 0), ("echo x | tee /dev/null", 0), ("rm -f /etc/nginx/sites-enabled/old", 0),
    ("cp a /etc/nginx/sites-available/x", 0), ("grep -r foo /etc/ 2>/dev/null", 0),
    ("mv /tmp/a /tmp/b 2>/dev/null", 0), ("cat <<'EOF'\nrm -f /dev/null\nEOF", 0), ("git status", 0),
    ("adb shell rm /data/x", 0), ("echo 'rm -f /dev/null' > notes.txt", 0),
    ("dd if=/dev/zero of=/tmp/f bs=1M count=1", 0), ("chmod 666 /dev/kvm", 0),
    ('post.sh A "text: the target only; sed/perl -i. Does NOT touch `>/dev/null`, `tee /dev/null`" 2>&1 | tail -1', 0),
    ('post.sh A "line 1; rm -f /dev/null\nline 2; mv /dev/null x" | tail -1', 0),
    # variables
    ('f=/dev/gate-var-livetest; rm -f "$f"', 1), ("f=/dev/x\nrm -f $f", 1),
    ('export T=/etc/hosts; sed -i s/a/b/ "$T"', 1), ("D=/boot; rm -rf ${D}/vmlinuz", 1),
    ('tmp=$(mktemp /tmp/x.XXXX); rm -f "$tmp"', 0), ('f=/tmp/a; rm -f "$f"', 0), ('rm -f "$unknown"', 0),
    ('stderr_tmp=/dev/null; [ "$stderr_tmp" != /dev/null ] && rm -f "$stderr_tmp"', 1),
    ('post.sh A "f=/dev/x; rm -f \\"$f\\""', 0),
]
bad = 0
for c, e in C:
    r = subprocess.run([sys.executable, SF], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": c}}),
                       capture_output=True, text=True, env=ENV)
    g = 1 if '"deny"' in r.stdout else 0
    if g != e or r.returncode:
        bad += 1
        print("FAIL", "deny" if g else "pass", f"rc={r.returncode}", "|", c.replace("\n", "⏎")[:90])
print(f"sysfile-gate: {len(C) - bad} pass, {bad} fail")
sys.exit(1 if bad else 0)
