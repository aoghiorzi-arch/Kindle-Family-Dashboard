-- Phase 5 sign-in: Cloudflare Access identifies a person by email. Members are matched on it.
-- Email is optional for local development accounts; production members must have one.

ALTER TABLE members ADD COLUMN email TEXT CHECK (email IS NULL OR length(email) BETWEEN 3 AND 254);
CREATE UNIQUE INDEX members_email ON members (lower(email)) WHERE email IS NOT NULL;
