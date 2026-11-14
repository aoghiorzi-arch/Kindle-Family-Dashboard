#!/usr/bin/env bash
# Pre-exposure checks for the TLS proxy. Usage: scripts/lan-check.sh https://192.168.1.139:8443 /path/to/caddy-root.crt
# Run from any machine on the LAN (the phone-side CA must be the same file). Prints PASS/FAIL; exits 1 on any FAIL.
set -u
ORIGIN="${1:?origin, e.g. https://192.168.1.139:8443}"; CA="${2:?path to the proxy CA certificate (PEM)}"
HOSTPORT="${ORIGIN#https://}"; HOST="${HOSTPORT%%:*}"
fail=0
check() { if [ "$2" = ok ]; then echo "PASS $1"; else echo "FAIL $1"; fail=1; fi; }

body=$(curl -sS --max-time 8 --cacert "$CA" "$ORIGIN/healthz" 2>/dev/null)
[ "$body" = '{"ok": true}' ] && r=ok || r=bad; check "HTTPS /healthz returns ok with the proxy CA (got: ${body:-nothing})" $r

curl -sS --max-time 8 "$ORIGIN/healthz" >/dev/null 2>&1 && r=bad || r=ok; check "HTTPS without the CA is refused (certificate really needed)" $r

hdr=$(curl -sS --max-time 8 --cacert "$CA" -D - -o /dev/null "$ORIGIN/healthz" 2>/dev/null)
echo "$hdr" | grep -qi '^strict-transport-security:' && r=ok || r=bad; check "HSTS header present" $r

code=$(curl -sS --max-time 8 --cacert "$CA" -o /dev/null -w '%{http_code}' "$ORIGIN/api/display/frame.png" 2>/dev/null)
[ "$code" = 401 ] && r=ok || r=bad; check "display endpoint without token is 401 (got $code)" $r

code=$(curl -sS --max-time 8 --cacert "$CA" -o /dev/null -w '%{http_code}' "$ORIGIN/api/state" 2>/dev/null)
[ "$code" = 401 ] && r=ok || r=bad; check "state endpoint without sign-in is 401 (got $code)" $r

# A wrong Host is either refused (4xx) or answered with an empty body by the proxy without reaching the app.
out=$(curl -sS --max-time 8 --cacert "$CA" -H 'Host: evil.example' -w '\n%{http_code}' "$ORIGIN/healthz" 2>/dev/null)
code="${out##*$'\n'}"; body="${out%$'\n'*}"
if [ "$code" = 000 ] || [ "${code#4}" != "$code" ] || ! echo "$body" | grep -q 'ok'; then r=ok; else r=bad; fi
check "wrong Host header never reaches the app (got $code)" $r

curl -sS --max-time 5 "http://$HOST:8765/healthz" >/dev/null 2>&1 && r=bad || r=ok; check "app port 8765 is not reachable from the network" $r

[ "$fail" = 0 ] && echo "All checks passed." || { echo "Some checks failed."; exit 1; }
