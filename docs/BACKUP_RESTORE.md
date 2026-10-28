# Backup and restore

Backups are explicit local commands; no automatic schedule or remote upload is configured.
Run them from the repository root with the application's Python environment.

## Make a backup

```bash
KFD_DB=/path/to/family.sqlite3 python3 -m app.manage backup /protected/backups/2026-10-28
```

The parent directory must exist and the destination directory must not exist. The command uses SQLite's backup API to capture a consistent committed snapshot, including WAL data, and validates database integrity, foreign keys and encrypted calendar fields. It publishes a private directory containing `family.sqlite3` only after verification. It never initializes or migrates the source. Complete the calendar encryption migration before backing up.

**Preserve the matching key separately.** By default the source key is beside the live database (`family.sqlite3.key`); `KFD_KEY_FILE` overrides that location. Copy this key to separate protected storage with owner-only permissions (600). This command deliberately does not bundle it with the database. A backup without its matching key is not recoverable. A key from another installation will fail verification.

The database still contains readable household records, password hashes and token hashes. Keep backups private and use encrypted storage. Protect both the snapshot and the separate key. SQLite snapshots exclude saved PNG frames, which regenerate, and application code/fonts, which come from the repository. Browser sessions are included in backups but removed from restored copies. Shortcuts tokens and retry receipts are preserved.

## Restore and test

Stop the Family Hub before switching it to a restored database. Restore always creates a **new** directory; it cannot overwrite the existing database or its key.

```bash
KFD_KEY_FILE=/protected/keys/original.key python3 -m app.manage restore /protected/backups/2026-10-28/family.sqlite3 /protected/recovered
KFD_KEY_FILE=/protected/keys/original.key KFD_DB=/protected/recovered/family.sqlite3 python3 -m app.manage init-db
KFD_KEY_FILE=/protected/keys/original.key KFD_DB=/protected/recovered/family.sqlite3 python3 -m app.server
```

Keep the key environment setting for every subsequent command/server start, or place the matching key at the default path with permissions 600. Sign in again, inspect shopping/events, verify calendar recurrence and generate a preview. Restore preserves automatic feed refresh settings, so starting the server can resume previously enabled downloads. For an offline rehearsal, inspect the database without starting the server or keep the network disconnected.

On verification or write failure no completed backup is reported. An interrupted run may leave a `.kfd-recovery-*` staging directory or an empty destination; choose a new destination for a retry. Keep the original installation until the recovered copy has been checked. These commands verify logical SQLite and encryption consistency; they do not guarantee recovery from failing storage. Rehearse recovery periodically using protected copies of both files.
