# Calendar storage and key handling

Feed addresses often act as credentials. The database now stores `calendar_feeds.url` and `calendar_sources.text` as versioned AES-256-GCM ciphertext using the pinned `cryptography` package. Each encryption uses a fresh random 12-byte nonce and a 128-bit authentication tag. Authenticated context includes field purpose, household and feed ID/source name: copying a ciphertext into a different row or household fails authentication. The primitive follows the [cryptography AESGCM interface](https://cryptography.io/en/50.0.2/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM).

This protects these fields in a database-only export/copy. Parsed event titles/UIDs, dates, labels, manual events, shopping items, locations and saved PNGs remain ordinary data. A running server can decrypt sources. Protect its account, disk and backups; this change does not make public hosting ready.

## Key file

The default key is the absolute database path plus `.key`, for example `data/family.sqlite3.key`. First initialization creates a random 32-byte binary key with exclusive creation, fsync and owner-only permissions. Existing files are never overwritten. On POSIX, files with another owner or group/other access are refused; final-component symlinks and non-regular files are refused. New database files are also owner-only. Existing database/directory permissions are not automatically changed; review them locally.

`KFD_KEY_FILE=/absolute/protected/path/calendar.key` selects another path. Its containing directory must already exist and be controlled by the server account. Set the same value for every server/management process. For an already encrypted database, move/copy the **original** key with mode 600 before changing this setting. Never point an encrypted database at a newly generated key.

Keys and databases belong in separate protected backups. Copying the entire default `data` folder includes both and removes the database-only separation. `data/` and `*.key` are git-ignored. Do not print, paste or commit keys. A missing/wrong/malformed key blocks startup/new connections; the app does not reset data, generate a replacement or fall back to plaintext. Restore the matching original key to recover. Existing connections retain their loaded key until closed.

## Upgrade/migration

1. Stop **all** old/new server and management processes. Keep a protected recovery copy of the pre-upgrade database; it contains plaintext and must be handled accordingly. This release does not automate that backup.
2. Install the pinned dependencies and choose key custody/path. Run `python3 -m app.manage init-db` with the same `KFD_DB`/`KFD_KEY_FILE` settings used by the server. Server startup and other setup commands also initialize storage, so migrate offline before launching them.
3. Initialization encrypts all existing feed addresses and saved sources in one SQLite transaction. IDs, labels, schedules, timestamps, parsed events and sessions are preserved. Older feeds retain manual refresh as their default.
4. Migration checkpoints/exits WAL mode, enables SQLite secure deletion, then vacuums after encryption commits. A pending-cleanup marker blocks normal connections until cleanup completes. If cleanup fails (for example, disk full), correct the cause and rerun `init-db`; it reuses the original key and resumes cleanup without double encryption.
5. Restart locally and check the calendar with fictional data. Keep the key independent of database exports. Existing old software must not be restarted against the migrated database.

Encryption failure before commit rolls back the fields/metadata together. Once encrypted, malformed or substituted fields fail closed; the web API emits a fixed 503 response, and maintenance logs fixed messages. Saved events are retained. Browser preview failure handling keeps its previous image. A lost key prevents new server connections even for non-calendar routes, rather than allowing partial writes with an uncertain key.

SQLite cleanup covers current logical database/journal files. It cannot erase old backups, filesystem snapshots, SSD remnants or copies made before migration. Protect or retire those separately. There is no automated key rotation, full-database encryption or backup/restore CLI in this batch. Those, HTTPS, production configuration and the soak test remain launch work.
