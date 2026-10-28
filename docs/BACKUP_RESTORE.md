# Backup and restore

Backups are explicit local commands; no automatic schedule or remote upload is configured.
Run them from the repository root with the application's Python environment.

## Make a backup

```bash
KFD_DB=/path/to/family.sqlite3 python3 -m app.manage backup /protected/backups/2026-10-28
```

The parent directory must exist and the destination directory must not exist. The command uses SQLite's backup API to capture a consistent committed snapshot, including WAL data, and validates database integrity, foreign keys and encrypted calendar fields. It publishes a private directory containing `family.sqlite3` only after verification. It never initializes or migrates the source. Complete the calendar encryption migration before backing up.

**Preserve the matching key separately.** By default the source key is beside the live database (`family.sqlite3.key`); `KFD_KEY_FILE` overrides that location. Copy this key to separate protected storage with owner-only permissions (600). This command deliberately does not bundle it with the database. A backup without its matching key is not recoverable. A key from another installation will fail verification.

The database still contains readable household records, password hashes and token hashes. Keep backups private and use encrypted storage. Protect both the snapshot and the separate key. SQLite snapshots exclude saved PNG frames, which regenerate, and application code/fonts, which come from the repository. Sessions, tokens and retry receipts are included in snapshots. **Restore clears sessions, revokes recovered API tokens and clears their retry receipts** to avoid reviving credentials from an old snapshot. All automatic feeds are paused until deliberately re-enabled.

Check a snapshot without restoring, migrating or changing its records:

```bash
python3 -m app.manage verify-backup /protected/backups/2026-10-28/family.sqlite3 --key-file /protected/keys/original.key
```

Copy and verification each have a 30-second work budget; database files/snapshots are capped at 256 MiB. A busy source can time out, so retry after writes settle. Checks require this version's expected tables/columns, reject views/triggers/virtual tables and pending encryption cleanup, and authenticate every encrypted field. Structural consistency and the calendar key match do not authenticate every ordinary field or establish forensic disk integrity. Snapshots use Python's [SQLite backup API](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup), with committed WAL data included.

## Restore and test

Stop the Family Hub before switching it to a restored database. Restore always creates a **new** directory; it cannot overwrite the existing database or its key.

```bash
KFD_KEY_FILE=/protected/keys/original.key python3 -m app.manage restore /protected/backups/2026-10-28/family.sqlite3 /protected/recovered
KFD_KEY_FILE=/protected/keys/original.key KFD_DB=/protected/recovered/family.sqlite3 python3 -m app.manage init-db
KFD_KEY_FILE=/protected/keys/original.key KFD_DB=/protected/recovered/family.sqlite3 python3 -m app.server
```

Keep the key environment setting for every subsequent command/server start, or place the matching key at the default path with permissions 600. Restore also accepts `--key-file /protected/keys/original.key` after the destination; the key is never copied or regenerated. Stop the old server before switching database paths.

Sign in with an existing password, inspect shopping/events and private-event masking, verify offline calendar recurrence and generate a fresh preview. Issue fresh Shortcuts tokens and update clients deliberately. Every feed starts with automatic downloads paused; inspect and re-enable them explicitly. Labels, URLs, cached sources/events and refresh history are retained. Password changes after the snapshot are absent from it, so review/reset old passwords locally before using an old recovery copy. A replacement token has a new retry scope; inspect an old offline queue rather than blindly replaying it.

On handled failures staging files are removed and an existing destination is never overwritten, including dangling symlinks and destination-creation races. A process/host crash can leave a private `.kfd-recovery-*` staging directory; remove it after checking no command still uses it. If filesystem sync fails after publication, a complete destination may already exist; verify it instead of deleting it blindly. Keep the original installation until recovery acceptance. Actual-machine recovery/key custody, scheduled off-machine copies, retention, key rotation and a soak test remain launch work.
