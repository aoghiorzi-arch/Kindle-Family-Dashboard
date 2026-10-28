# Apple Shortcuts quick-add (shopping)

This lets an iPhone Shortcut add an item to the Family Hub shopping list. It is part of P4 and works only with the local prototype for now.

## Before you start
- The Shortcut must be able to reach the Family Hub. A server on `127.0.0.1` is reachable only from the Mac itself, so this is for testing on the Mac. Real phone use needs HTTPS hosting, which is a later, separately approved step.
- Create a token in **Household settings → Shortcuts tokens** (admins only). Copy it immediately; it is shown once. If it is lost or leaked, revoke it and create a new one.

## What the token can do
- Add one shopping item to the household's list: `POST /api/shortcut/shopping` with JSON `{"title": "Milk"}`.
- It cannot read the list, use the web app, add events or change settings.
- Revoking it takes effect immediately.

## Shortcut steps
1. **Ask for Input** (text) → prompt "Item to add".
2. **Generate UUID** and save it as `Request ID`. Generate it once per intended addition; reuse it for every retry of that addition.
3. **Get Contents of URL**
   - URL: `https://YOUR-HOST/api/shortcut/shopping`
   - Method: POST
   - Headers: `Authorization` = `Bearer PASTE_TOKEN_HERE`, `Content-Type` = `application/json`
   - Request Body: JSON, with `title` set to the Ask for Input result and `request_id` set to `Request ID`.
4. **Show Notification** → "Added to shopping list" (optional).

Keep the token out of shared Shortcuts. Anyone who has the Shortcut can add items with it.

## Responses
- `201` — added.
- `200` — this request already succeeded; no extra item was added.
- `409` — this request ID was already used with a different title.
- `400` — the title is invalid, or request_id is not 1–128 letters, digits, hyphens or underscores.
- `401` — the token is wrong or revoked.
- `403` — the token no longer has shopping permission.
- `429` — the token has 5,000 saved request receipts. Existing matching retries still work; ask an administrator to replace the token for new requests. Do not remove `request_id` to work around the limit.
- `503` — the shopping write is temporarily unavailable. Keep the same request ID/title for a later retry.


Retry receipts persist across server restarts and are included in backups, scoped to each token. Deleting or completing an item does not erase its receipt. A new intended purchase, even with the same title, needs a new request ID. IDs are case-sensitive; titles are trimmed. Existing clients without `request_id` retain their original behaviour: each request adds an item. Receipts are retained for the lifetime of the token record; there is no time-based expiry. New keyed additions are bounded at 5,000 receipts per token, while prior replays still work at capacity.

Token identity, current scope/revocation and the write are checked together in one SQLite transaction. Revoked tokens cannot replay an old success, and a revocation that finishes before a waiting write acquires its transaction prevents that write. A write that acquired the transaction first may finish before revocation. Restoring a backup invalidates recovered sessions/tokens, clears receipts and pauses automatic feeds. Create a fresh token after recovery and review any pending queue before using the new token's separate request scope.

A phone offline queue is not implemented. A retrying Shortcut must retain its token, request ID and title itself; restart/offline behavior of the client still needs device testing. The existing JSON `request_id` and 201/200/409 response contract is unchanged; no new HTTP header is required.
