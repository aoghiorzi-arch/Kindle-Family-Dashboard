"""Authenticated calendar-field encryption and an independent, owner-only key file.

This protects a database-only copy, not a compromised running server or all household data.
Never regenerate a lost key: restore the matching key from a separate protected backup.
"""
import base64
import json
import os
from pathlib import Path
import stat
import sqlite3
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = 'kfd:v1:'
ERROR = 'Calendar storage is locked. Check the original key file and database; no data was reset.'


class StorageError(Exception):
 """Fixed messages only: never include keys, source text or feed addresses."""


def key_path(db_path):
 return Path(os.environ.get('KFD_KEY_FILE', str(Path(db_path).resolve()) + '.key'))


def load_cipher(db_path, create=False):
 path = key_path(db_path)
 try:
  if create:
   try:
    # Exclusive creation, no overwrite. The containing directory must already exist.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
   except FileExistsError:
    pass
   else:
    with os.fdopen(fd, 'wb') as file:
     file.write(os.urandom(32))
     file.flush()
     os.fsync(file.fileno())
  fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
  with os.fdopen(fd, 'rb') as file:
   info = os.fstat(file.fileno())
   if not stat.S_ISREG(info.st_mode): raise StorageError(ERROR)
   if os.name == 'posix' and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
    raise StorageError('Calendar key file must belong to this user and have owner-only permissions (chmod 600).')
   key = file.read(33)
  if len(key) != 32: raise StorageError(ERROR)
  return AESGCM(key)
 except OSError:
  raise StorageError(ERROR) from None


def context(kind, household_id=None, record=None):
 return json.dumps(['kfd', 1, kind, household_id, record], separators=(',', ':')).encode()


def seal(cipher, value, aad):
 nonce = os.urandom(12)
 return PREFIX + base64.b64encode(nonce + cipher.encrypt(nonce, value.encode(), aad)).decode('ascii')


def unseal(cipher, value, aad):
 try:
  if not isinstance(value, str) or not value.startswith(PREFIX): raise ValueError
  raw = base64.b64decode(value[len(PREFIX):], validate=True)
  if len(raw) < 28: raise ValueError
  return cipher.decrypt(raw[:12], raw[12:], aad).decode('utf-8')
 except (ValueError, InvalidTag, UnicodeError):
  raise StorageError(ERROR) from None


def marker(conn):
 if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='calendar_security'").fetchone() is None:
  return None
 row = conn.execute('SELECT proof,scrub_pending FROM calendar_security WHERE id=1').fetchone()
 if row is None: raise StorageError(ERROR)
 return row


def verify(conn, cipher, allow_pending=False):
 row = marker(conn)
 if row is None or unseal(cipher, row['proof'], context('key-check')) != 'calendar-storage-v1':
  raise StorageError(ERROR)
 if row['scrub_pending'] and not allow_pending:
  raise StorageError('Calendar migration cleanup is incomplete. Stop the server and run python3 -m app.manage init-db.')


def initialize(conn, db_path):
 """Run at offline startup, before requests/workers. Encryption commits all-or-nothing.

secure_delete + DELETE journaling + VACUUM clean SQLite's current logical files, not
old backups, storage snapshots, SSD blocks or filesystem copies. A pending marker
keeps the app locked if cleanup fails/interruption happens after encryption commits.
"""
 existing = marker(conn)
 if existing is None:
  # A missing metadata table must never trigger replacement of an encrypted key.
  for table, field in [('calendar_feeds', 'url'), ('calendar_sources', 'text')]:
   if conn.execute(f'SELECT 1 FROM {table} WHERE {field} LIKE ? LIMIT 1', (PREFIX + '%',)).fetchone():
    raise StorageError(ERROR)
 cipher = load_cipher(db_path, create=existing is None)
 if existing is not None:
  verify(conn, cipher, allow_pending=True)
 conn.execute('PRAGMA secure_delete=ON')
 if existing is None or existing['scrub_pending']:
  # Refuse conversion if another connection prevents leaving WAL mode.
  try:
   mode = conn.execute('PRAGMA journal_mode=DELETE').fetchone()[0]
  except sqlite3.OperationalError:
   raise StorageError('Stop all Family Hub processes before migrating calendar storage.') from None
  if mode != 'delete':
   raise StorageError('Stop all Family Hub processes before migrating calendar storage.')
 conn.execute('BEGIN IMMEDIATE')
 try:
  # Recheck after taking the writer lock (another startup may have just migrated).
  current = marker(conn)
  if current is not None:
   verify(conn, cipher, allow_pending=True)
  else:
   for row in conn.execute('SELECT id,household_id,url FROM calendar_feeds').fetchall():
    if row['url'].startswith(PREFIX): raise StorageError(ERROR)
    conn.execute('UPDATE calendar_feeds SET url=? WHERE id=?',
     (seal(cipher, row['url'], context('feed-url', row['household_id'], row['id'])), row['id']))
   for row in conn.execute('SELECT household_id,source,text FROM calendar_sources').fetchall():
    if row['text'].startswith(PREFIX): raise StorageError(ERROR)
    conn.execute('UPDATE calendar_sources SET text=? WHERE household_id=? AND source=?',
     (seal(cipher, row['text'], context('calendar-source', row['household_id'], row['source'])), row['household_id'], row['source']))
   conn.execute('CREATE TABLE calendar_security (id INTEGER PRIMARY KEY CHECK(id=1), proof TEXT NOT NULL, scrub_pending INTEGER NOT NULL)')
   conn.execute('INSERT INTO calendar_security VALUES(1,?,1)',
    (seal(cipher, 'calendar-storage-v1', context('key-check')),))
  # Validate every field before accepting an existing database, too.
  for row in conn.execute('SELECT id,household_id,url FROM calendar_feeds'):
   unseal(cipher, row['url'], context('feed-url', row['household_id'], row['id']))
  for row in conn.execute('SELECT household_id,source,text FROM calendar_sources'):
   unseal(cipher, row['text'], context('calendar-source', row['household_id'], row['source']))
  conn.execute('COMMIT')
 except Exception:
  conn.execute('ROLLBACK')
  raise
 if marker(conn)['scrub_pending']:
  conn.execute('VACUUM')
  conn.execute('UPDATE calendar_security SET scrub_pending=0 WHERE id=1')
 return cipher
