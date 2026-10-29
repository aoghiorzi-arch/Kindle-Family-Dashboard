# Family Hub Shortcut: Add to Family Shopping List

This Shortcut adds a spoken or typed item to the family list. It contains **no secrets in this repository**. Each phone gets its own token, which you create in the Hub.

## Before you start

1. A household admin signs in to the Hub on a computer or phone and opens **Settings → Devices**.
2. Choose **Add a device**. Name it after the phone (for example "Alex's iPhone"), choose **Shortcut (add items only)**, and select **Create device**.
3. Copy the token now. It is shown once. A Shortcut token can add items only. It cannot read the list, read the display snapshot, or manage devices.

## Steps (in the Shortcuts app)

| # | Action | Settings |
|---|---|---|
| 1 | **Ask for Input** | Type: Text. Prompt: "What do we need?" |
| 2 | **Get Contents of URL** | URL: `https://YOUR-HUB-ADDRESS/api/shopping`. Method: POST. Headers: `Content-Type` = `application/json`; `Authorization` = `Bearer YOUR-TOKEN`. Request body: JSON with one field, `title`, set to the **Provided Input** variable from step 1. |
| 3 | **Get Dictionary Value** | Key: `item` (from the response) |
| 4 | **Show Notification** | Text: "Added to the family list." |

Replace `YOUR-HUB-ADDRESS` and `YOUR-TOKEN` on your own phone only. Do not put the token in the URL. The Hub ignores tokens in query strings.

## What the responses mean

| Status | Meaning | What to do |
|---|---|---|
| 201 | Added | Nothing |
| 400 | The title is empty, longer than 60 characters, or contains control characters | Say the item again, shorter |
| 401 | The token is wrong or was revoked | Create a new token for this phone and update the Shortcut |
| 403 | The token is not a Shortcut token | Use a token created with "Shortcut" as the type |
| 413 or 415 | The request body is too large or the content type is wrong | Check the Headers and body settings |

Show the status code during setup to confirm each path. Remove the debug step once it works.

## Keeping the token safe

- **Do not share the Shortcut.** An exported Shortcut contains its token. If you share one, revoke that device in **Settings → Devices** right away.
- **Rotate after loss.** If a phone is lost or sold, revoke its device. Rotating a token (**Rotate token**) stops the old one at once.
- **Storage on the phone is not verified.** This guide does not claim that Shortcuts keeps the token in the Keychain. Treat the token as a password and check how your iOS version stores it before relying on it.
- **One token per phone,** so one lost phone does not affect the others.

## Not included yet

- "Show the family list" needs a read permission this token type does not have. It is planned as a separate, optional token type.
- Marking an item complete from the Shortcut is planned after the core flow works.
- Repeated submissions are not yet de-duplicated. If a request is retried, an item can be added twice.
