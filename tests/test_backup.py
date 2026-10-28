import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
from app import backup, store, secrets, ics, calendars
from datetime import datetime, timezone


class BackupTest(unittest.TestCase):
 def setUp(self):
  self.temp = tempfile.TemporaryDirectory()
  self.addCleanup(self.temp.cleanup)
  self.root = Path(self.temp.name)
  self.db = self.root/'live.sqlite3'
  self.env = patch.dict(os.environ, {'KFD_KEY_FILE': str(self.root/'original.key')})
  self.env.start()
  self.addCleanup(self.env.stop)
  store.init_db(self.db)
  self.conn = store.connect(self.db)
  self.addCleanup(self.conn.close)
  self.hh = store.create_household(self.conn, 'Test')
  uid = store.create_user(self.conn, self.hh, 'sam', 'hashed-password', 'admin')
  store.create_session(self.conn, uid, 3600)
  store.add_shopping(self.conn, self.hh, uid, 'Bread')
  self.fid = store.add_feed(self.conn, self.hh, 'Family', 'https://example.test/private-feed')
  self.conn.execute('INSERT INTO calendar_sources VALUES(?,?,?,?)', (self.hh, 'paste',
   secrets.seal(self.conn.cipher, 'BEGIN:VCALENDAR\r\nEND:VCALENDAR', secrets.context('calendar-source', self.hh, 'paste')), '2026-10-28'))

 def test_wal_snapshot_and_restore_with_separate_key(self):
  self.conn.execute('PRAGMA journal_mode=WAL')
  copied = backup.backup(self.db, self.root/'backup')
  store.add_shopping(self.conn, self.hh, None, 'After backup')
  restored = backup.restore(copied, self.root/'restored')
  conn = store.connect(restored)
  try:
   self.assertEqual([r['title'] for r in store.list_shopping(conn, self.hh)], ['Bread'])
   self.assertEqual(store.get_feed(conn, self.hh, self.fid)['url'], 'https://example.test/private-feed')
   source = conn.execute('SELECT text FROM calendar_sources').fetchone()[0]
   self.assertEqual(secrets.unseal(conn.cipher, source, secrets.context('calendar-source', self.hh, 'paste')), 'BEGIN:VCALENDAR\r\nEND:VCALENDAR')
   self.assertEqual(conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
   self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 1)
  finally: conn.close()
  self.assertEqual(list(copied.parent.iterdir()), [copied])
  if os.name == 'posix':
   self.assertEqual(restored.stat().st_mode & 0o777, 0o600)
   self.assertEqual(restored.parent.stat().st_mode & 0o777, 0o700)
  self.assertNotIn(b'private-feed', copied.read_bytes())

 def test_wrong_missing_and_tampered_data_never_publish(self):
  copied = backup.backup(self.db, self.root/'backup')
  key = self.root/'original.key'
  original = key.read_bytes()
  for value in (os.urandom(32), None):
   if value is None: key.unlink()
   else: key.write_bytes(value)
   with self.assertRaises(secrets.StorageError): backup.restore(copied, self.root/'restore')
   self.assertFalse((self.root/'restore').exists())
  key.write_bytes(original)
  key.chmod(0o600)
  self.conn.execute("UPDATE calendar_sources SET text='corrupted'")
  with self.assertRaises(secrets.StorageError): backup.backup(self.db, self.root/'bad')
  self.assertFalse((self.root/'bad').exists())
  self.assertFalse(list(self.root.glob('.kfd-recovery-*')))

 def test_refuses_overwrite_and_missing_source(self):
  target = self.root/'existing'
  target.mkdir()
  (target/'keep').write_text('unchanged')
  with self.assertRaises(ValueError): backup.backup(self.db, target)
  self.assertEqual((target/'keep').read_text(), 'unchanged')
  with self.assertRaises(ValueError): backup.restore(self.root/'missing', self.root/'restore')
  self.assertFalse((self.root/'missing').exists())

 def test_failed_publish_leaves_no_destination(self):
  with patch('app.backup.os.replace', side_effect=OSError('disk error')):
   with self.assertRaises(OSError): backup.backup(self.db, self.root/'failed')
  self.assertFalse((self.root/'failed').exists())

 def test_recovered_calendar_survives_restart_with_reset_credentials(self):
  text = 'BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:daily\nDTSTART:20261028T090000Z\nRRULE:FREQ=DAILY\nSUMMARY:Daily\nEND:VEVENT\nEND:VCALENDAR'
  store.set_location(self.conn, self.hh, 51.5, 0, 'Europe/London')
  rows, _ = ics.parse_events(text, 'Europe/London', '2026-10-28')
  store.replace_calendar(self.conn, self.hh, rows, text, '2026-10-28')
  uid = store.get_user(self.conn, 'sam')['id']
  plain = store.create_api_token(self.conn, self.hh, uid, 'Shortcut', ['shopping:add'])
  token = store.api_token_for_use(self.conn, plain)
  store.add_shortcut_shopping(self.conn, token, 'Milk', 'repeat')
  copied = backup.backup(self.db, self.root/'backup')
  restored = backup.restore(copied, self.root/'restored')
  store.init_db(restored)
  now = datetime(2026, 12, 10, tzinfo=timezone.utc).timestamp()
  def offline(url): raise AssertionError('Manual feeds must not download')
  calendars.CalendarService(restored, offline, clock=lambda: now).tick()
  conn = store.connect(restored)
  try:
   self.assertEqual(store.day_events(conn, self.hh, '2026-12-10')[0]['title'], 'Daily')
   self.assertIsNone(store.api_token_for_use(conn, plain))
   self.assertEqual(conn.execute('SELECT count(*) FROM shortcut_requests').fetchone()[0], 0)
   self.assertEqual(len(store.list_shopping(conn, self.hh)), 2)
  finally: conn.close()

 def test_cli_backup_restore_and_existing_destination(self):
  env = {**os.environ, 'KFD_DB': str(self.db)}
  for args in (['backup', str(self.root/'cli-backup')],
               ['restore', str(self.root/'cli-backup'/'family.sqlite3'), str(self.root/'cli-restore')]):
   result = subprocess.run([sys.executable, '-m', 'app.manage', *args], env=env, capture_output=True, text=True)
   self.assertEqual(result.returncode, 0, result.stderr)
  result = subprocess.run([sys.executable, '-m', 'app.manage', 'backup', str(self.root/'cli-backup')],
                          env=env, capture_output=True, text=True)
  self.assertNotEqual(result.returncode, 0)
  self.assertIn('Destination already exists', result.stderr)
