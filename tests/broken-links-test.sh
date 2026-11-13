#!/usr/bin/env bash
# broken_links.py: fixable / orphan / ignored links. BL=<path> tests another copy.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" HANZ_TEST=1 CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_AGENTS_DIR="$T/Agents"; mkdir -p "$HOME" "$T/ws"
printf "#!/bin/sh\necho \"\$1|\${2:-\$(cat)}\" >> %s/letters\n" "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/letters"; export CCM_INBOX_POST="$T/post"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | sed "s/^/   /"; fi; }
BL=${BL:-$HERE/../scripts/broken_links.py}
W="$T/ws"; mkdir -p "$W/a" "$W/b" "$W/skipme"
echo x > "$W/b/target.md"; echo x > "$W/ok.md"
cat > "$W/a/doc.md" <<'EOT'
[fine](../ok.md) [moved](old/target.md) [gone](nothing-here.md) [web](https://x.y/z.md) [anchor](../ok.md#sec)
`[inline](example.md)`
```
[block](example2.md)
```
EOT
echo '[x](missing.md)' > "$W/skipme/s.md"
out=$(python3 "$BL" 2>&1)
ok "1 a moved file -> a ready fix with the relative path" 'echo "$out" | grep -q "a/doc.md :: old/target.md -> ../b/target.md"'
ok "2 a vanished file -> orphan with 0 candidates" 'echo "$out" | grep -q "nothing-here.md.*0 candidates"'
ok "3 fine links, URL, anchor, inline code, code block -> not reported" '! echo "$out" | grep -qE "ok.md|x.y|example"'
ok "4 skip folder is reported by default (key empty)" 'echo "$out" | grep -q "skipme/s.md"'
out=$(CCM_BROKEN_LINKS_SKIP=skipme/ python3 "$BL" 2>&1)
ok "5 CCM_BROKEN_LINKS_SKIP hides it" '! echo "$out" | grep -q "skipme"'
out=$(CCM_BROKEN_LINKS_SKIP=skipme/ python3 "$BL" --all 2>&1)
ok "6 --all shows it again" 'echo "$out" | grep -q "skipme/s.md"'
rm "$W/a/doc.md" "$W/skipme/s.md"; echo '[ok](../ok.md)' > "$W/a/d.md"; out=$(python3 "$BL" 2>&1)
ok "7 clean corpus -> broken: 0" 'echo "$out" | grep -q "broken: 0"'
echo "broken-links: $pass pass, $fail fail"; [ $fail = 0 ]
