"""Consistent database snapshots and non-destructive, offline recovery."""
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from . import store, secrets


def validate(conn, cipher):
 secrets.verify(conn, cipher)
 if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
  raise ValueError('Database integrity check failed')
 if conn.execute('PRAGMA foreign_key_check').fetchone() is not None:
  raise ValueError('Database foreign key check failed')
 for row in conn.execute('SELECT id,household_id,url FROM calendar_feeds'):
  secrets.unseal(cipher, row['url'], secrets.context('feed-url', row['household_id'], row['id']))
 for row in conn.execute('SELECT household_id,source,text FROM calendar_sources'):
  secrets.unseal(cipher, row['text'], secrets.context('calendar-source', row['household_id'], row['source']))


def snapshot(source, destination, cipher, restore=False):
 """Publish a new private directory only after the snapshot passes validation.

The matching key is deliberately kept separate. SQLite backup includes committed
WAL data. Restore clears browser sessions; frames regenerate on startup.
"""
 source, destination = Path(source), Path(destination)
 if not source.is_file(): raise ValueError('Source database does not exist')
 if destination.exists(): raise ValueError('Destination already exists; choose a new directory')
 stage = Path(tempfile.mkdtemp(prefix='.kfd-recovery-', dir=destination.parent))
 try:
  db = stage/'family.sqlite3'
  fd = os.open(db, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
  os.close(fd)
  # Read-only opening prevents accidentally creating or migrating the source.
  src = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)
  dst = store.raw_connect(db)
  try:
   src.backup(dst)
   dst.execute('PRAGMA journal_mode=DELETE')
   validate(dst, cipher)
   if restore:
    dst.execute('PRAGMA secure_delete=ON')
    dst.execute('DELETE FROM sessions')
  finally:
   src.close()
   dst.close()
  with db.open('rb') as file: os.fsync(file.fileno())
  # mkdir reserves the destination without ever replacing an existing path.
  destination.mkdir(mode=0o700)
  try:
   os.replace(db, destination/'family.sqlite3')
  except Exception:
   destination.rmdir()
   raise
 finally:
  shutil.rmtree(stage)
 return destination/'family.sqlite3'


def backup(db, destination):
 return snapshot(db, destination, secrets.load_cipher(db))


def restore(db, destination):
 return snapshot(db, destination, secrets.load_cipher(db), restore=True)
