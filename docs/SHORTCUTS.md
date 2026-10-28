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
2. **Get Contents of URL**
   - URL: `https://YOUR-HOST/api/shortcut/shopping`
   - Method: POST
   - Headers: `Authorization` = `Bearer PASTE_TOKEN_HERE`, `Content-Type` = `application/json`
   - Request Body: JSON, with `title` set to the Ask for Input result.
3. **Show Notification** → "Added to shopping list" (optional).

Keep the token out of shared Shortcuts. Anyone who has the Shortcut can add items with it.

## Responses
- `201` — added.
- `400` — the title is blank or longer than 100 characters.
- `401` — the token is wrong or revoked.
