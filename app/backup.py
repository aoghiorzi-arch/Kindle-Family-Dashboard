"""Consistent database snapshots and non-destructive, offline recovery."""
import os
from pathlib import Path
import shutil
import tempfile
from contextlib import closing
from . import backups, secrets


def validate(conn, cipher):
 backups.validate_database(conn, cipher)


def snapshot(source, destination, cipher, restore=False):
 """Publish a new private directory only after the snapshot passes validation.

The matching key is deliberately kept separate. SQLite backup includes committed
WAL data. Restore clears browser sessions, revokes tokens and pauses feeds.
"""
 source, destination = Path(source), Path(destination)
 if not source.is_file(): raise ValueError('Source database does not exist')
 if os.path.lexists(destination): raise ValueError('Destination already exists; choose a new directory')
 stage = Path(tempfile.mkdtemp(prefix='.kfd-recovery-', dir=destination.parent))
 try:
  db = stage/'family.sqlite3'
  with closing(backups.read_database(source)) as src:
   backups.publish_snapshot(src, db, cipher, restoring=restore)
  # mkdir reserves the destination without ever replacing an existing path.
  destination.mkdir(mode=0o700)
  try:
   os.replace(db, destination/'family.sqlite3')
   if os.name == 'posix':
    for folder in (destination, destination.parent):
     fd = os.open(folder, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
     try: os.fsync(fd)
     finally: os.close(fd)
  except Exception:
   # A complete file may already have been published if a later fsync failed.
   if not (destination/'family.sqlite3').exists(): destination.rmdir()
   raise
 finally:
  shutil.rmtree(stage)
 return destination/'family.sqlite3'


def backup(db, destination):
 return snapshot(db, destination, secrets.load_cipher(db))


def restore(db, destination, key_file=None):
 return snapshot(db, destination, secrets.load_cipher(db, path=key_file), restore=True)
