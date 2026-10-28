# Supervised home-network pilot: security boundary (A3)

**Status: designed and unit-tested at the application layer. TLS termination itself has not been exercised here (no proxy installed); verify on the real machine before any real household use.** No public hosting, no port forwarding, no internet exposure.

## Architecture
```
phone / Kindle ──HTTPS (LAN only)──▶ Caddy on the server computer ──HTTP, 127.0.0.1──▶ Family Hub
```
- The app never listens on a network interface: `make_server` rejects non-loopback hosts. There is no plaintext path to edit endpoints from the network.
- A TLS-terminating reverse proxy on the same computer faces the LAN. Template: `deploy/Caddyfile.example` (Caddy, `tls internal`, LAN-only `remote_ip`, headers excluded from logs). **Unverified template.**
- Set `KFD_PUBLIC_ORIGIN=https://<name>:<port>` (see `deploy/kfd.env.example`). Then the app:
  - marks session cookies `Secure` (plus `HttpOnly`, `SameSite=Strict`) and sends HSTS;
  - accepts only that exact `Origin` for writes (CSRF check stays on) and only that `Host` (421 otherwise, defeating DNS rebinding); loopback mode likewise accepts only `127.0.0.1`/`localhost` hosts;
  - serves the display endpoint only with a valid scoped bearer token.

## Phone
Reach it by name over the LAN (router DNS entry or per-device hosts override); install the proxy's local CA certificate on the phone (Caddy: `data/caddy/pki/authorities/local/root.crt`; iOS: install profile, then enable full trust). Sign in with the member's password. Away from home the phone cannot connect; remote access is a Stage C decision (VPN such as Tailscale or hosted VPS, with separate approval).

## Firewall scope
Allow inbound only the proxy port (e.g. 8443/tcp) from the home subnet; nothing to 8765 (it is loopback-bound anyway). No router port-forwarding. Prefer a DHCP reservation so the server's address is stable.

## Kindle transport — UNRESOLVED until Stage B
Old Kindle firmware may lack modern TLS (TLS 1.2/1.3, current cipher suites, SNI) and cannot trust a private CA without installing it on the device. Options to evaluate with the real device, in this order:
1. Kindle's own client with the CA certificate installed and TLS 1.2 enabled on the proxy.
2. A small local relay/proxy on the LAN that the Kindle can reach, with the token still scoped read-only.
3. If neither is safe, stop and propose a different architecture for review.

Never disable certificate verification, never expose edit endpoints over plaintext, never put the token in a URL. The display token is the only credential on the device and grants read-only access to one image.

## Pre-exposure checks (run on the real machine)
1. `curl --cacert ca.pem https://<name>:8443/healthz` → `{"ok": true}`; `http://<name>:…` fails.
2. Login response `Set-Cookie` contains `Secure`; HSTS header present.
3. `curl -H 'Host: other' …` → 421; request from outside the LAN range → 403.
4. Display token: image works; `/api/state` → 401; revoked → 401.
5. `nmap`/`ss -ltn`: only the proxy listens on the LAN; 8765 only on 127.0.0.1.
