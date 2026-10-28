# Display ⇄ server contract (A1)

The display is read-only. Its only application credential is a **display token**.

## Credential
- Admins create it in **Household settings → Tokens → Display (read picture only)**, or `POST /api/tokens {"name": "...", "kind": "display"}`. The value is shown once (`kfd_…`).
- Scope `display:read`. Stored server-side only as a SHA-256 hash. Bound to one household.
- Revoke it in the same screen; effect is immediate. Restoring a backup revokes every token (PR #6), so create a new one afterwards.
- Send it only as `Authorization: Bearer <token>`. Never in a URL (a `?token=` query is ignored and returns 401). The server does not log requests.
- A display token cannot: read `/api/state`, use the session-only `/frame.png`, add shopping via Shortcuts (403), create/revoke tokens, or reach another household. A Shortcuts token gets 403 on the display endpoint.

## Endpoint
`GET /api/display/frame.png` (HTTPS in any non-loopback setup; see `NETWORK_PILOT.md`)

| Response | Meaning |
|---|---|
| `200` + PNG (600×800) | New image. Headers: `ETag: "<sha256>"`, `X-Frame-Stale: true` if the server is serving its last good frame after a render failure. |
| `304` | Send `If-None-Match` with the last ETag; pixels unchanged, do not redraw. |
| `401` | Missing, wrong or revoked token. |
| `403` | Token is valid but lacks `display:read`. |
| `421` | Unexpected `Host` header. |
| `503` | No frame available yet; keep showing the old image. |

`GET /healthz` is unauthenticated and returns only `{"ok": true}`.

## Client rules (see `display_client/`)
Poll about every 5 minutes; redraw only when the image hash changes; keep the old image on any failure; back off exponentially (30 s → 30 min cap, with jitter); never follow redirects; verify TLS.
