#!/usr/bin/env bash
# secret-scan: a URL parameter in DATA files is not a secret; in code it is. SS=<path> tests another copy.
# Fake values are assembled from parts - nothing in this file looks like a secret.
set -u
HERE=$(dirname "$(readlink -f "$0")")
SS=${SS:-$HERE/../bin/secret-scan}
export HOME=$(mktemp -d) CLAUDE_METHODOLOGY_CONF=/nonexistent
T=$(mktemp -d); trap 'rm -rf "$T" "$HOME"' EXIT
V="nP1G$(printf 'q%.0s' $(seq 22))"; K="to""ken"; A="api_""key"; P="pass""word"
pass=0; fail=0
ok() { "$SS" "$T/$2" >/dev/null 2>&1; rc=$?; if [ "$rc" = "$3" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1 (rc $rc, expected $3)"; fi; }
printf '{"url":"https://x.ca/apply?%s=%s&src=a"}\n' "$K" "$V" > "$T/d.jsonl";      ok "1 ?token= in .jsonl (collected data) -> clean" d.jsonl 0
printf '{"url":"https://x.ca/a?x=1&amp;%s=%s"}\n' "$K" "$V" > "$T/e.json";          ok "2 &amp;token= in .json -> clean" e.json 0
printf 'u = "https://api.x/v1?%s=%s"\n' "$A" "$V" > "$T/c.py";                       ok "3 ?api_key= in CODE (.py) -> secret" c.py 1
printf 'URL=https://api.x/v1?%s=%s\n' "$K" "$V" > "$T/s.sh";                        ok "4 ?token= in .sh -> secret" s.sh 1
printf 'x,%s=%s\n' "$P" "$V" > "$T/f.csv";                                          ok "5 password= in data WITHOUT ?/& before it -> secret" f.csv 1
printf '{"u":"https://a/b?%s=%s","n":"%s=%s"}\n' "$K" "$V" "$P" "$V" > "$T/m.jsonl"; ok "6 a line with both a URL parameter and a real assignment -> secret" m.jsonl 1
# -- code, not a secret (forms taken from real code lines)
TK="TO""KEN"; SC="SE""CRET"; PW="PASS""WORD"; R12="$(printf 'a1%.0s' $(seq 8))"
printf '    %s = "https://oauth2.googleapis.com/%s"\n' "$TK" "$K" > "$T/o.py";               ok "7 constant address without @ -> clean" o.py 0
printf 'class X{constructor(t,e){this.%s=t,this.mode=e,this.bitCount=n}}\n' "$K" > "$T/q.js"; ok "8 minified JS with commas -> clean" q.js 0
printf 'SESSION_%s = os.environ.get("SESSION_%s") or secrets.%s_urlsafe(32)\n' "$SC" "$SC" "$K" > "$T/m.py"; ok "9 expression with parentheses -> clean" m.py 0
printf 'const %s = location.pathname.split("/").pop();\n' "$K" > "$T/v.html";            ok "10 expression in JS -> clean" v.html 0
# real ones stay red
printf '%s="%s"\n' "$PW" "$R12" > "$T/r1.sh";                                             ok "11 PASSWORD=\"16 letters/digits\" -> secret" r1.sh 1
printf '%s: sk_%s\n' "$A" "$R12" > "$T/r2.yml";                                           ok "12 api_key: sk_… -> secret" r2.yml 1
printf 'SERVICE_%s=%s7\n' "$PW" "$(printf 'b2%.0s' $(seq 7))" > "$T/r3.env";                ok "13 SERVICE_PASSWORD without quotes -> secret" r3.env 1
printf '%s=eyJ%s.eyJ%s.%s\n' "$K" "$R12" "$R12" "$R12" > "$T/r4.sh";                      ok "14 token=JWT (dots are not an expression) -> secret" r4.sh 1
printf '%s = "https://bob:%s@db.x/q"\n' "$K" "$R12" > "$T/r5.py";                         ok "15 token = \"https://user:pass@…\" — the address exception does not hide a login -> secret" r5.py 1
# service key formats
L="$(printf 'Zz9%.0s' $(seq 8))"
printf 'k = "%s_live_%s"\n' "sk" "$L" > "$T/k1.py";        ok "16 Stripe sk_live_ -> secret" k1.py 1
printf 'k = "%s_test_%s"\n' "rk" "$L" > "$T/k2.py";        ok "17 Stripe rk_test_ -> secret" k2.py 1
printf 'w = "%s_%s"\n' "whsec" "$L" > "$T/k3.py";          ok "18 webhook whsec_ -> secret" k3.py 1
printf 'g = "%s-%s"\n' "GOCSPX" "$L" > "$T/k4.py";         ok "19 Google OAuth GOCSPX- -> secret" k4.py 1
printf 'r = "%s_%s_%s"\n' "re" "Ab12Cd" "$L" > "$T/k5.py"; ok "20 Resend re_… -> secret" k5.py 1
printf 'm = re_compile_pattern(x)\n' > "$T/k6.py";        ok "21 re_compile… (identifier) -> clean" k6.py 0

printf 'LoadCredential=%s:/etc/example/tunnel-%s\n' "$K" "$K" > "$T/k7.service"; ok "22 file path in the value -> clean" k7.service 0
printf 'f"Set a new %s:\\n{link}\\n\\nThe link"\n' "$P" > "$T/k8.py"; ok "23 f-string with a {variable} -> clean" k8.py 0
printf '%s=/%s\n' "$K" "$V" > "$T/k9.env"; ok "24 value starting with / and no second / -> secret" k9.env 1
printf '%s=%s{x\n' "$P" "$V" > "$T/k10.env"; ok "25 unclosed brace in the value -> secret" k10.env 1

# --keys-only (code gate): skips assignments, still catches key formats, empty input -> rc 3
ko() { "$SS" --keys-only "$T/$2" >/dev/null 2>&1; rc=$?; if [ "$rc" = "$3" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1 (rc $rc, expected $3)"; fi; }
printf '%s = "%s"\n' "$TK" "$V" > "$T/n1.py"; ko "26 --keys-only: assignment -> clean" n1.py 0; ok "26b without the flag the same line -> secret" n1.py 1
printf '%s = "%s"; k = "%s_live_%s"\n' "$TK" "$V" "sk" "$L" > "$T/n2.py"; ko "27 --keys-only: assignment and key in one line -> secret" n2.py 1
ko "28 --keys-only: no such file - nothing seen -> rc 3" n3-missing.py 3
echo "secret-scan: $pass pass, $fail fail"; [ $fail = 0 ]
