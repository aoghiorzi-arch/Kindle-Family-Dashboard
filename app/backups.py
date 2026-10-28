"""Consistent database snapshots and recovery to a new path, with separate key custody."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from . import secrets as storage_secrets

DEADLINE_SECONDS = 30
MAX_DATABASE_BYTES = 256 * 1024 * 1024
TABLE_COLUMNS = {
 'households': {'id', 'name'},
 'users': {'id', 'household_id', 'username', 'password_hash', 'role', 'created_at'},
 'sessions': {'token_hash', 'user_id', 'csrf_token', 'expires_at'},
 'shopping': {'id', 'household_id', 'title', 'done', 'created_by', 'created_at'},
 'events': {'id', 'household_id', 'title', 'time', 'private', 'created_by', 'created_at'},
 'locations': {'household_id', 'lat', 'lon', 'tz'},
 'weather_cache': {'household_id', 'fetched_at', 'payload'},
 'api_tokens': {'id', 'household_id', 'name', 'token_hash', 'scopes', 'created_by', 'created_at', 'last_used_at', 'revoked_at'},
 'calendar_events': {'id', 'household_id', 'uid', 'day', 'time', 'title', 'private', 'source'},
 'calendar_feeds': {'id', 'household_id', 'label', 'url', 'created_at', 'last_attempt', 'last_success', 'last_error', 'refresh_enabled', 'skipped_count'},
 'calendar_sources': {'household_id', 'source', 'text', 'expanded_day'},
 'calendar_security': {'id', 'proof', 'scrub_pending'},
 'shortcut_requests': {'token_id', 'request_id', 'title'},
}


class BackupError(Exception):
 """Safe operational messages; underlying exceptions may contain private paths/schema."""


def read_database(path):
 path = Path(path).resolve()
 if not path.is_file() or path.stat().st_size > MAX_DATABASE_BYTES:
  raise BackupError('Database is missing or exceeds the 256 MiB recovery limit.')
 conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1, isolation_level=None)
 conn.row_factory = sqlite3.Row
 conn.execute('PRAGMA trusted_schema=OFF')
 conn.execute('PRAGMA query_only=ON')
 return conn


def validate_database(conn, cipher):
 """Only this app's table format, without executable views/triggers/virtual tables."""
 deadline = time.monotonic() + DEADLINE_SECONDS
 conn.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
 try:
  schema = conn.execute("SELECT name,type,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'").fetchall()
  if any(r['type'] not in ('table', 'index') or 'VIRTUAL TABLE' in (r['sql'] or '').upper() for r in schema):
   raise BackupError('Unsupported database schema; backup was not accepted.')
  if {r['name'] for r in schema if r['type'] == 'table'} != set(TABLE_COLUMNS):
   raise BackupError('Unsupported database version; use the matching app version and migrate offline first.')
  for table, columns in TABLE_COLUMNS.items():
   if {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')} != columns:
    raise BackupError('Unsupported database version; backup was not accepted.')
  if conn.execute('PRAGMA integrity_check(1)').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchone() is not None:
   raise BackupError('Database integrity checks failed; backup was not accepted.')
  storage_secrets.verify(conn, cipher)
  for row in conn.execute('SELECT id,household_id,url FROM calendar_feeds'):
   if not isinstance(row['url'], str) or len(row['url']) > 4096: raise BackupError('Calendar field exceeds the recovery limit.')
   storage_secrets.unseal(cipher, row['url'], storage_secrets.context('feed-url', row['household_id'], row['id']))
  for row in conn.execute('SELECT household_id,source,text FROM calendar_sources'):
   if not isinstance(row['text'], str) or len(row['text']) > 3_000_000: raise BackupError('Calendar field exceeds the recovery limit.')
   storage_secrets.unseal(cipher, row['text'], storage_secrets.context('calendar-source', row['household_id'], row['source']))
 finally:
  conn.set_progress_handler(None, 0)


def copy_database(source, destination):
 deadline = time.monotonic() + DEADLINE_SECONDS
 page_size = source.execute('PRAGMA page_size').fetchone()[0]
 def progress(status, remaining, total):
  if time.monotonic() > deadline: raise BackupError('Database snapshot timed out; retry after writes settle.')
  if total * page_size > MAX_DATABASE_BYTES: raise BackupError('Database exceeds the 256 MiB recovery limit.')
 source.backup(destination, pages=128, progress=progress, sleep=0.05)
 destination.execute('PRAGMA trusted_schema=OFF')
 destination.execute('PRAGMA foreign_keys=ON')
 destination.execute('PRAGMA secure_delete=ON')
 destination.execute('PRAGMA journal_mode=DELETE')


def publish_snapshot(source, destination, cipher, restoring=False):
 target = Path(destination).absolute()
 if os.path.lexists(target): raise BackupError('Destination already exists; choose a new path. Nothing was overwritten.')
 if not target.parent.is_dir(): raise BackupError('Create a private destination directory first.')
 # Sibling temporary file + hard link gives atomic publication without overwriting a race winner.
 fd, name = tempfile.mkstemp(prefix='.kfd-snapshot-', dir=target.parent)
 temporary = Path(name)
 os.close(fd)
 try:
  with closing(sqlite3.connect(temporary, isolation_level=None)) as output:
   output.row_factory = sqlite3.Row
   copy_database(source, output)
   validate_database(output, cipher)
   if restoring:
    output.execute('BEGIN IMMEDIATE')
    try:
     output.execute('DELETE FROM sessions')
     output.execute('UPDATE api_tokens SET revoked_at=? WHERE revoked_at IS NULL', (int(time.time()),))
     output.execute('DELETE FROM shortcut_requests')
     output.execute('UPDATE calendar_feeds SET refresh_enabled=0')
     output.execute('COMMIT')
    except Exception:
     output.execute('ROLLBACK')
     raise
    output.execute('VACUUM')
    validate_database(output, cipher)
  with temporary.open('rb') as file: os.fsync(file.fileno())
  os.link(temporary, target)
  if os.name == 'posix':
   directory = os.open(target.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
   try: os.fsync(directory)
   finally: os.close(directory)
  return target
 finally:
  for suffix in ['', '-wal', '-shm', '-journal']:
   Path(str(temporary) + suffix).unlink(missing_ok=True)


def backup(db_path, destination):
 """No initialization, key creation, frame copy or server shutdown is needed."""
 try:
  cipher = storage_secrets.load_cipher(db_path)
  with closing(read_database(db_path)) as source:
   return publish_snapshot(source, destination, cipher)
 except (OSError, sqlite3.Error, storage_secrets.StorageError):
  raise BackupError('Backup failed. Check the database, original key and destination; no existing file was overwritten.') from None


def verify(backup_path, key_file):
 try:
  cipher = storage_secrets.load_cipher(backup_path, path=key_file)
  with closing(read_database(backup_path)) as conn:
   conn.execute('BEGIN')
   validate_database(conn, cipher)
 except (OSError, sqlite3.Error, storage_secrets.StorageError):
  raise BackupError('Verification failed. Check the backup and matching original key; no data was changed.') from None


def restore(backup_path, destination, key_file):
 """Validate a copy; invalidate recovered credentials and pause network refresh."""
 try:
  cipher = storage_secrets.load_cipher(backup_path, path=key_file)
  with closing(read_database(backup_path)) as source:
   return publish_snapshot(source, destination, cipher, restoring=True)
 except (OSError, sqlite3.Error, storage_secrets.StorageError):
  raise BackupError('Restore failed. Check the backup, original key and new destination; no existing file was overwritten.') from None
