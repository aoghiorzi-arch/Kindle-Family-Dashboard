# Sign-in with Cloudflare Access (ADR D2)

**Status:** code built and tested (75 Worker tests, including real signed tokens). **Not yet configured in Cloudflare.** The steps below are for the owner to carry out in the Cloudflare dashboard, since I cannot access your account from here.

## How it works

1. A family member opens the Hub's address. Cloudflare Access asks for their email, and sends a one-time code.
2. Access passes the request to the Worker with a signed assertion (`Cf-Access-Jwt-Assertion`).
3. The Worker checks the signature against the team's published keys, plus the audience, issuer, expiry and algorithm. Anything that fails is refused.
4. The verified email is matched to a member in the household. Unknown emails get `403 not_a_member`.
5. Writes still need the Origin check and a CSRF token. In this mode the CSRF token is derived from a server secret, so it changes when the Access session does.

Shortcut and display devices don't use Access. They use their own tokens, on paths that Access must bypass (below).

## Steps for the owner (Cloudflare dashboard)

1. **Create a Zero Trust team** (if you don't have one). Note the team domain, for example `yourfamily.cloudflareaccess.com`.
2. **Add a login method:** One-time PIN (email). Optionally add Google or Apple.
3. **Add a self-hosted application** for your Hub's hostname, for example `family.example`, covering the path `/*`. Copy its **Application Audience (AUD) tag**.
4. **Allow policy:** Action *Allow*, include the emails of the family members (or an email domain). Only these people can reach the Hub.
5. **Bypass policy for devices:** Action *Bypass*, Include *Everyone*, for these paths only:
   - `/api/shortcut/*` (Shortcut adds)
   - `/api/device/*` (display snapshot; token-protected)
6. **Set the Worker's configuration** in `infrastructure/cloudflare/wrangler.toml` or the dashboard:
   - `ACCESS_TEAM_DOMAIN` = your team domain (for example `yourfamily.cloudflareaccess.com`)
   - `ACCESS_AUD` = the AUD tag from step 3
   - `PUBLIC_ORIGIN` = `https://family.example`
7. **Set the CSRF secret** (never commit it): `wrangler secret put CSRF_SECRET`, then paste a long random value.
8. **Disable the `*.workers.dev` address** for the Worker, or route it through Access too. The Worker refuses requests without a valid assertion either way, but a single hostname is simpler to reason about.

## Bootstrap: the first admin

In production the members table starts empty, and only an admin can invite members. Create the household and the first admin once, with your own email:

```bash
wrangler d1 execute kfd --remote --command "
INSERT INTO households (id, name, timezone, created_at)
  VALUES ('<new-uuid>', '<Family name>', 'Europe/London', '<UTC time, e.g. 2026-10-30T09:00:00Z>');
INSERT INTO members (id, household_id, display_name, role, email, created_at)
  VALUES ('<new-uuid>', '<same household id>', '<Your name>', 'admin', '<your email>', '<UTC time>');"
```

Use fresh UUIDs for the IDs. After this, the admin invites everyone else from **Settings → Family members**. Each invitee signs in with the email address entered there.

## What members see

- **Not invited:** a valid Access login but no matching member row shows "Not a member yet".
- **Signing out** ends the Access session as well, by visiting Access's logout page.
- **Removing someone:** delete their Access policy entry, and remove or re-email their member row. Their session ends when the Access session does.

## Limits and notes

- **Member removal is not yet a screen.** Remove members with SQL, or add a removal endpoint.
- **Session length** is set by the Access policy, not by the Worker.
- **Local development** keeps the development sign-in, which is refused whenever Access is configured.
- **The Access sign-in path has not been run end to end in a browser.** The Worker's verification is tested with real signed tokens, but the browser sign-in flow through Cloudflare has to be checked after step 3 above.
- **Cloudflare's current free-tier limits** for Access were not checked from this session. Confirm them before inviting a large family.

## Rollback

Remove `ACCESS_TEAM_DOMAIN` and `ACCESS_AUD` from the Worker's configuration. The Worker falls back to the local sign-in, which is refused outside `ENVIRONMENT=local`, so production has no browser sign-in until Access is configured again.
