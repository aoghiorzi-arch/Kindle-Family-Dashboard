"""Storage failures must not expose secrets, reset data or publish partial migrations."""
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch
from app import store, secrets as storage_secrets

URL = 'https://example.test/calendar/unique-feed-secret-981ab.ics'
TEXT = 'BEGIN:VCALENDAR\r\nDESCRIPTION:unique-source-secret-72ef\r\nEND:VCALENDAR'


class CalendarSecretsTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.db = Path(self.tmp.name)/'family.sqlite3'
  self.addCleanup(patch.stopall)
  patch.dict(os.environ).start()
  os.environ.pop('KFD_KEY_FILE', None)
  store.init_db(self.db)
  self.conn = store.connect(self.db)
  self.addCleanup(self.conn.close)
  self.hh = store.create_household(self.conn, 'Test')

 def populate(self):
  fid = store.add_feed(self.conn, self.hh, 'Family', URL, True)
  store.replace_calendar(self.conn, self.hh, [], TEXT, '2026-10-28')
  return fid

 def test_encrypted_on_disk_and_in_sql_dump_with_private_random_key(self):
  fid = self.populate()
  dump = '\n'.join(self.conn.iterdump())
  self.assertNotIn(URL, dump)
  self.assertNotIn(TEXT, dump)
  self.assertNotIn(b'unique-feed-secret', self.db.read_bytes())
  self.assertNotIn(b'unique-source-secret', self.db.read_bytes())
  self.assertEqual(store.get_feed(self.conn, self.hh, fid)['url'], URL)
  row = self.conn.execute('SELECT text FROM calendar_sources').fetchone()
  self.assertEqual(store.source_text(self.conn, self.hh, 'paste', row['text']), TEXT)
  key = storage_secrets.key_path(self.db)
  self.assertEqual(len(key.read_bytes()), 32)
  if os.name == 'posix':
   self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
   self.assertEqual(stat.S_IMODE(self.db.stat().st_mode), 0o600)
  self.assertNotIn(key.read_bytes().hex(), dump)

 def test_repeated_values_use_distinct_ciphertexts_and_restart_keeps_same_key(self):
  self.populate()
  first = self.conn.execute('SELECT text FROM calendar_sources').fetchone()[0]
  key = storage_secrets.key_path(self.db).read_bytes()
  store.replace_calendar(self.conn, self.hh, [], TEXT, '2026-10-28')
  second = self.conn.execute('SELECT text FROM calendar_sources').fetchone()[0]
  self.assertNotEqual(first, second)
  store.init_db(self.db)
  self.assertEqual(storage_secrets.key_path(self.db).read_bytes(), key)
  restarted = store.connect(self.db)
  try: self.assertEqual(store.list_feeds(restarted, self.hh)[0]['url'], URL)
  finally: restarted.close()

 def test_missing_key_never_regenerates_or_changes_database(self):
  self.populate()
  storage_secrets.key_path(self.db).unlink()
  before = self.db.read_bytes()
  for operation in [lambda:store.connect(self.db), lambda:store.init_db(self.db)]:
   with self.assertRaises(storage_secrets.StorageError): operation()
  self.assertFalse(storage_secrets.key_path(self.db).exists())
  self.assertEqual(self.db.read_bytes(), before)

 def test_wrong_or_malformed_key_never_changes_database(self):
  self.populate()
  before = self.db.read_bytes()
  for key in [os.urandom(32), b'bad']:
   storage_secrets.key_path(self.db).write_bytes(key)
   with self.assertRaises(storage_secrets.StorageError): store.init_db(self.db)
   self.assertEqual(self.db.read_bytes(), before)

 def test_unsafe_key_permissions_and_symlink_are_rejected(self):
  if os.name != 'posix': self.skipTest('POSIX permissions')
  key = storage_secrets.key_path(self.db)
  key.chmod(0o644)
  with self.assertRaisesRegex(storage_secrets.StorageError, 'owner-only'): store.connect(self.db)
  key.chmod(0o600)
  original = key.with_suffix('.original')
  key.rename(original)
  key.symlink_to(original)
  with self.assertRaises(storage_secrets.StorageError): store.connect(self.db)

 def test_ciphertext_is_bound_to_its_household_row_and_purpose(self):
  fid = self.populate()
  other = store.create_household(self.conn, 'Other')
  fid2 = store.add_feed(self.conn, self.hh, 'Second', URL)
  fid3 = store.add_feed(self.conn, other, 'Other', URL)
  ciphertext = self.conn.execute('SELECT url FROM calendar_feeds WHERE id=?', (fid,)).fetchone()[0]
  for target, household in [(fid2, self.hh), (fid3, other)]:
   self.conn.execute('UPDATE calendar_feeds SET url=? WHERE id=?', (ciphertext, target))
   with self.assertRaises(storage_secrets.StorageError): store.get_feed(self.conn, household, target)
  self.conn.execute('UPDATE calendar_sources SET text=?', (ciphertext,))
  with self.assertRaises(storage_secrets.StorageError):
   store.source_text(self.conn, self.hh, 'paste', ciphertext)

 def test_tampering_and_plaintext_in_encrypted_database_fail_closed(self):
  fid = self.populate()
  ciphertext = self.conn.execute('SELECT url FROM calendar_feeds WHERE id=?', (fid,)).fetchone()[0]
  for broken in [URL, ciphertext[:25] + '!' + ciphertext[26:], ciphertext[:-8] + 'AAAAAA==']:
   self.conn.execute('UPDATE calendar_feeds SET url=? WHERE id=?', (broken, fid))
   with self.assertRaises(storage_secrets.StorageError) as caught:
    store.get_feed(self.conn, self.hh, fid)
   self.assertNotIn(URL, str(caught.exception))
   with self.assertRaises(storage_secrets.StorageError): store.init_db(self.db)

 def test_explicit_external_key_and_matching_database_copy_can_reopen(self):
  self.populate()
  external = Path(self.tmp.name)/'external.key'
  shutil.copyfile(storage_secrets.key_path(self.db), external)
  external.chmod(0o600)
  restored = Path(self.tmp.name)/'restored.sqlite3'
  shutil.copyfile(self.db, restored)
  with patch.dict(os.environ, {'KFD_KEY_FILE': str(external)}):
   store.init_db(restored)
   conn = store.connect(restored)
   try: self.assertEqual(store.list_feeds(conn, self.hh)[0]['url'], URL)
   finally: conn.close()
  self.assertFalse(Path(str(restored)+'.key').exists())

 def test_missing_metadata_does_not_create_a_replacement_key(self):
  self.populate()
  self.conn.execute('DROP TABLE calendar_security')
  storage_secrets.key_path(self.db).unlink()
  with self.assertRaises(storage_secrets.StorageError): store.init_db(self.db)
  self.assertFalse(storage_secrets.key_path(self.db).exists())


class LegacyCalendarMigrationTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.db = Path(self.tmp.name)/'old.sqlite3'
  self.env = patch.dict(os.environ)
  self.env.start()
  self.addCleanup(self.env.stop)
  os.environ.pop('KFD_KEY_FILE', None)
  conn = sqlite3.connect(self.db)
  conn.executescript(store.SCHEMA)
  conn.execute("INSERT INTO households VALUES(1,'Old family')")
  conn.execute("INSERT INTO calendar_feeds(id,household_id,label,url,created_at) VALUES(7,1,'Family',?,1)", (URL,))
  conn.execute("INSERT INTO calendar_sources VALUES(1,'paste',?,'2026-10-28')", (TEXT,))
  conn.execute("INSERT INTO calendar_events(household_id,uid,day,title,private) VALUES(1,'id','2026-10-28','Busy event',1)")
  conn.commit()
  conn.close()

 def test_legacy_migration_preserves_events_ids_and_manual_schedule_and_scrubs_raw_source(self):
  self.assertIn(b'unique-source-secret', self.db.read_bytes())
  store.init_db(self.db)
  conn = store.connect(self.db)
  try:
   feed = store.get_feed(conn, 1, 7)
   self.assertEqual((feed['url'], feed['refresh_enabled']), (URL, 0))
   self.assertEqual(store.day_events(conn, 1, '2026-10-28')[0]['title'], 'Busy event')
   self.assertEqual(conn.execute('SELECT scrub_pending FROM calendar_security').fetchone()[0], 0)
  finally: conn.close()
  for suffix in ['', '-wal', '-journal']:
   path = Path(str(self.db)+suffix)
   if path.exists():
    self.assertNotIn(b'unique-feed-secret', path.read_bytes())
    self.assertNotIn(b'unique-source-secret', path.read_bytes())

 def test_encryption_failure_rolls_back_all_fields_and_can_retry(self):
  real_seal = storage_secrets.seal
  calls = []
  def fail_second(*args):
   calls.append(1)
   if len(calls) == 2: raise OSError('simulated write failure')
   return real_seal(*args)
  with patch.object(storage_secrets, 'seal', fail_second):
   with self.assertRaises(OSError): store.init_db(self.db)
  conn = sqlite3.connect(self.db)
  try:
   self.assertEqual(conn.execute('SELECT url FROM calendar_feeds').fetchone()[0], URL)
   self.assertEqual(conn.execute('SELECT text FROM calendar_sources').fetchone()[0], TEXT)
   self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='calendar_security'").fetchone())
  finally: conn.close()
  key = storage_secrets.key_path(self.db).read_bytes()
  store.init_db(self.db)
  self.assertEqual(storage_secrets.key_path(self.db).read_bytes(), key)

 def test_cleanup_failure_locks_app_until_retry_and_does_not_reencrypt(self):
  original = store.Connection.execute
  def fail_vacuum(conn, query, *args, **kwargs):
   if query == 'VACUUM': raise sqlite3.OperationalError('simulated disk full')
   return original(conn, query, *args, **kwargs)
  with patch.object(store.Connection, 'execute', fail_vacuum):
   with self.assertRaises(sqlite3.OperationalError): store.init_db(self.db)
  with self.assertRaisesRegex(storage_secrets.StorageError, 'cleanup'): store.connect(self.db)
  conn = sqlite3.connect(self.db)
  ciphertext = conn.execute('SELECT url FROM calendar_feeds').fetchone()[0]
  conn.close()
  store.init_db(self.db)
  conn = store.connect(self.db)
  try: self.assertEqual(conn.execute('SELECT url FROM calendar_feeds').fetchone()[0], ciphertext)
  finally: conn.close()

 def test_wal_legacy_database_is_checkpointed_before_conversion(self):
  conn = sqlite3.connect(self.db)
  conn.execute('PRAGMA journal_mode=WAL')
  conn.execute('UPDATE calendar_sources SET text=?', (TEXT+'\nDESCRIPTION:wal-secret-482ac',))
  conn.commit()
  conn.close()
  store.init_db(self.db)
  for suffix in ['', '-wal', '-journal']:
   path = Path(str(self.db)+suffix)
   if path.exists(): self.assertNotIn(b'wal-secret-482ac', path.read_bytes())
