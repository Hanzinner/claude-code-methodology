#!/usr/bin/env bash
# swap-live: mode copied from the live file, syntax checked before the swap, live file intact on failure. SL=<path> tests another copy.
set -u
HERE=$(dirname "$(readlink -f "$0")")
SL=${SL:-$HERE/../bin/swap-live}
export HOME=$(mktemp -d) CLAUDE_METHODOLOGY_CONF=/nonexistent
T=$(mktemp -d); trap 'rm -rf "$T" "$HOME"' EXIT
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

printf '#!/usr/bin/env python3\nprint(1)\n' > "$T/h.py"; chmod 755 "$T/h.py"
printf 'print(2)\n' > "$T/h.py.new"; chmod 644 "$T/h.py.new"          # as after open(p+'.new','w')
"$SL" "$T/h.py.new" >/dev/null 2>&1; rc=$?
ok "py: 644 .new -> live file stays 755"        '[ $rc = 0 ] && [ "$(stat -c %a "$T/h.py")" = 755 ]'
ok "py: content is new, .new is gone"              'grep -q "print(2)" "$T/h.py" && [ ! -e "$T/h.py.new" ]'

printf 'print(\n' > "$T/h.py.new"; "$SL" "$T/h.py.new" >/dev/null 2>&1; rc=$?
ok "py: syntax error -> rc 1, live file intact" '[ $rc = 1 ] && grep -q "print(2)" "$T/h.py"'

printf '#!/bin/bash\necho a\n' > "$T/s.sh"; chmod 750 "$T/s.sh"
printf '#!/bin/bash\nif then\n' > "$T/s.sh.new"; "$SL" "$T/s.sh.new" >/dev/null 2>&1; rc=$?
ok "sh: bash -n failure -> rc 1, live file intact"   '[ $rc = 1 ] && grep -q "echo a" "$T/s.sh"'
printf '#!/bin/bash\necho b\n' > "$T/s.sh.new"; "$SL" "$T/s.sh.new" >/dev/null 2>&1
ok "sh: mode 750 carried over"                 '[ "$(stat -c %a "$T/s.sh")" = 750 ] && grep -q "echo b" "$T/s.sh"'

printf '#!/usr/bin/env bash\necho x\n' > "$T/tool"; chmod 755 "$T/tool"
printf '#!/usr/bin/env bash\nfi\n' > "$T/tool.new"; "$SL" "$T/tool.new" >/dev/null 2>&1; rc=$?
ok "no extension, bash shebang -> bash -n check" '[ $rc = 1 ] && grep -q "echo x" "$T/tool"'

"$SL" "$T/nope" >/dev/null 2>&1; ok "not .new -> rc 2" '[ $? = 2 ]'
printf 'import sys\nif len(sys.argv) < 9:\n    return\n' > "$T/h.py.new"; "$SL" "$T/h.py.new" >/dev/null 2>&1; rc=$?
ok "py: return outside a function (only a full compile catches it) -> rc 1, live file intact" '[ $rc = 1 ] && grep -q "print(2)" "$T/h.py"'
printf 'x\n' > "$T/real.sh"; ln -s "$T/real.sh" "$T/link.sh"; printf '#!/bin/bash\necho n\n' > "$T/link.sh.new"
"$SL" "$T/link.sh.new" >/dev/null 2>&1; rc=$?
ok "live file is a symlink -> rc 1, link and target intact" '[ $rc = 1 ] && [ -L "$T/link.sh" ] && grep -qx x "$T/real.sh"'
printf '#!/usr/bin/env python3\nprint(1)\n' > "$T/fresh.py.new"; chmod 644 "$T/fresh.py.new"; "$SL" "$T/fresh.py.new" >/dev/null 2>&1
ok "new script with a shebang (no live file, .new 644) -> executable" '[ -x "$T/fresh.py" ]'
printf '{"a": 1}\n' > "$T/data.json.new"; "$SL" "$T/data.json.new" >/dev/null 2>&1
ok "new file without a shebang -> mode as is (not executable)" '[ -e "$T/data.json" ] && [ ! -x "$T/data.json" ]'
echo "swap-live: $pass pass, $fail fail"; [ $fail = 0 ]
