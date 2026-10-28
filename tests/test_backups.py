"""Real snapshots, failed recovery and offline restart with separate key custody."""
from concurrent.futures import ThreadPoolExecutor
import json
import http.client
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from app import auth, backups, calendars, frames, server, store, weather
from app import secrets as storage_secrets

ROOT = Path(__file__).resolve().parents[1]
TEXT = 'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:family-series\r\nDTSTART:20261028T090000Z\r\nRRULE:FREQ=DAILY\r\nSUMMARY:Family walk\r\nEND:VEVENT\r\nEND:VCALENDAR'
URL = 'https://example.test/private/backup-secret-19.ics'
PASSWORD = 'backup fixture password'
PASSWORD_HASH = auth.hash_password(PASSWORD)


class BackupTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.directory = Path(self.tmp.name)
  self.db = self.directory/'family.sqlite3'
  self.env = patch.dict(os.environ)
  self.env.start()
  self.addCleanup(self.env.stop)
  os.environ.pop('KFD_KEY_FILE', None)
  store.init_db(self.db)
  self.key = storage_secrets.key_path(self.db)
  self.conn = store.connect(self.db)
  self.addCleanup(self.conn.close)
  self.hh = store.create_household(self.conn, 'Family')
  self.other = store.create_household(self.conn, 'Other')
  self.user = store.create_user(self.conn, self.hh, 'sam', PASSWORD_HASH, 'admin')
  self.session, _ = store.create_session(self.conn, self.user, 3600)
  self.token = store.create_api_token(self.conn, self.hh, self.user, 'Phone', ['shopping:add'])
  store.add_shortcut_shopping(self.conn, store.api_token_for_use(self.conn, self.token), 'Milk', '12345678-1234-1234-1234-123456789abc')
  store.add_shopping(self.conn, self.other, None, 'Other bread')
  store.set_location(self.conn, self.hh, 51.5, -0.1, 'Europe/London')
  self.fid = store.add_feed(self.conn, self.hh, 'Calendar', URL, True)
  store.replace_feed_events(self.conn, self.hh, self.fid, [], TEXT, '2026-10-28')
  self.snapshot = self.directory/'snapshot.sqlite3'
  self.restored = self.directory/'restored.sqlite3'

 def snapshot_db(self):
  backups.backup(self.db, self.snapshot)

 def restored_connection(self):
  # A recovery target uses the original external key; no adjacent copy is created.
  os.environ['KFD_KEY_FILE'] = str(self.key)
  store.init_db(self.restored)
  conn = store.connect(self.restored)
  self.addCleanup(conn.close)
  return conn

 def test_backup_is_verified_private_consistent_and_excludes_key_and_frames(self):
  frame_dir = Path(str(self.db)+'.frames')
  frame_dir.mkdir()
  (frame_dir/'1.png').write_bytes(b'fixture')
  self.snapshot_db()
  backups.verify(self.snapshot, self.key)
  self.assertFalse(Path(str(self.snapshot)+'.key').exists())
  self.assertFalse(Path(str(self.snapshot)+'.frames').exists())
  self.assertNotIn(URL.encode(), self.snapshot.read_bytes())
  self.assertNotIn(b'BEGIN:VCALENDAR', self.snapshot.read_bytes())
  if os.name == 'posix': self.assertEqual(stat.S_IMODE(self.snapshot.stat().st_mode), 0o600)
  conn = sqlite3.connect(self.snapshot)
  try:
   self.assertEqual(conn.execute('SELECT count(*) FROM shopping').fetchone()[0], 2)
   self.assertEqual(conn.execute('SELECT count(*) FROM shortcut_requests').fetchone()[0], 1)
   self.assertEqual(conn.execute('SELECT count(*) FROM sessions').fetchone()[0], 1)
  finally: conn.close()

 def test_restore_preserves_households_and_sources_invalidates_credentials_pauses_feeds(self):
  self.snapshot_db()
  before = self.db.read_bytes()
  backups.restore(self.snapshot, self.restored, self.key)
  self.assertEqual(self.db.read_bytes(), before)
  self.assertFalse(Path(str(self.restored)+'.key').exists())
  conn = self.restored_connection()
  self.assertEqual([r['title'] for r in store.list_shopping(conn, self.hh)], ['Milk'])
  self.assertEqual([r['title'] for r in store.list_shopping(conn, self.other)], ['Other bread'])
  self.assertIsNone(store.session_user(conn, self.session))
  self.assertIsNone(store.api_token_for_use(conn, self.token))
  self.assertEqual(conn.execute('SELECT count(*) FROM shortcut_requests').fetchone()[0], 0)
  feed = store.get_feed(conn, self.hh, self.fid)
  self.assertEqual((feed['url'], feed['refresh_enabled']), (URL, 0))
  raw = conn.execute('SELECT source,text FROM calendar_sources').fetchone()
  self.assertEqual(store.source_text(conn, self.hh, raw['source'], raw['text']), TEXT)
  self.assertIsNotNone(store.session_user(self.conn, self.session))
  self.assertIsNotNone(store.api_token_for_use(self.conn, self.token))

 def test_offline_recurring_calendar_and_new_frame_work_after_restore(self):
  self.snapshot_db()
  backups.restore(self.snapshot, self.restored, self.key)
  conn = self.restored_connection()
  now = 1793448000  # 31 October 2026, beyond the saved expansion day
  calls = []
  service = calendars.CalendarService(self.restored, lambda url:calls.append(url), lambda:now)
  service.tick()
  today = store.household_today(conn, self.hh, now)
  self.assertEqual(store.day_events(conn, self.hh, today)[0]['title'], 'Family walk')
  self.assertEqual(calls, [])
  fixture = json.loads((ROOT/'app'/'seed.json').read_text())
  result = frames.FrameService(self.restored, weather.FakeProvider(fixture['weather']), lambda:now).refresh(conn, self.hh)
  self.assertIsNotNone(result)
  self.assertTrue(result[0].startswith(b'\x89PNG'))
  self.assertFalse(result[2])

 def test_restored_server_allows_password_login_but_rejects_old_sessions_and_tokens(self):
  self.snapshot_db()
  backups.restore(self.snapshot, self.restored, self.key)
  self.restored_connection()
  httpd = server.make_server(self.restored, port=0)
  threading.Thread(target=httpd.serve_forever, daemon=True).start()
  try:
   def request(method, path, payload=None, headers=None):
    conn = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=5)
    conn.request(method, path, body=json.dumps(payload).encode() if payload else None,
     headers={'Content-Type':'application/json', **(headers or {})})
    result = conn.getresponse()
    out = result.status, result.read()
    conn.close()
    return out
   self.assertEqual(request('GET', '/api/state', headers={'Cookie':server.COOKIE+'='+self.session})[0], 401)
   self.assertEqual(request('POST', '/api/shortcut/shopping', {'title':'Bread'}, {'Authorization':'Bearer '+self.token})[0], 401)
   self.assertEqual(request('POST', '/api/login', {'username':'sam', 'password':PASSWORD})[0], 200)
  finally:
   httpd.shutdown()
   httpd.server_close()

 def test_backup_in_wal_mode_includes_committed_wal_writes(self):
  self.conn.execute('PRAGMA journal_mode=WAL')
  store.add_shopping(self.conn, self.hh, self.user, 'Committed WAL item')
  self.assertTrue(Path(str(self.db)+'-wal').exists())
  self.snapshot_db()
  backups.verify(self.snapshot, self.key)
  conn = sqlite3.connect(self.snapshot)
  try: self.assertEqual(conn.execute("SELECT count(*) FROM shopping WHERE title='Committed WAL item'").fetchone()[0], 1)
  finally: conn.close()

 def test_snapshot_remains_consistent_during_transactions_from_another_connection(self):
  self.conn.execute('PRAGMA journal_mode=WAL')
  stop, ready = threading.Event(), threading.Event()
  def writer():
   conn = store.connect(self.db)
   try:
    for i in range(100):
     conn.execute('BEGIN IMMEDIATE')
     store.add_shopping(conn, self.hh, self.user, f'pair-a-{i}')
     store.add_shopping(conn, self.hh, self.user, f'pair-b-{i}')
     conn.execute('COMMIT')
     ready.set()
     if stop.is_set(): break
   finally: conn.close()
  with ThreadPoolExecutor(max_workers=1) as pool:
   future = pool.submit(writer)
   self.assertTrue(ready.wait(5))
   try: self.snapshot_db()
   finally: stop.set()
   future.result(timeout=10)
  conn = sqlite3.connect(self.snapshot)
  try:
   a = conn.execute("SELECT count(*) FROM shopping WHERE title LIKE 'pair-a-%'").fetchone()[0]
   b = conn.execute("SELECT count(*) FROM shopping WHERE title LIKE 'pair-b-%'").fetchone()[0]
   self.assertGreater(a, 0)
   self.assertEqual(a, b)
  finally: conn.close()

 def test_existing_or_symlink_destinations_are_never_overwritten(self):
  self.snapshot_db()
  original = self.snapshot.read_bytes()
  with self.assertRaises(backups.BackupError): backups.backup(self.db, self.snapshot)
  self.assertEqual(self.snapshot.read_bytes(), original)
  with self.assertRaises(backups.BackupError): backups.restore(self.snapshot, self.db, self.key)
  link = self.directory/'dangling.sqlite3'
  link.symlink_to(self.directory/'missing-target')
  with self.assertRaises(backups.BackupError): backups.restore(self.snapshot, link, self.key)
  self.assertTrue(link.is_symlink())
  self.assertFalse((self.directory/'missing-target').exists())

 def test_missing_or_wrong_key_fails_without_output_or_replacement(self):
  self.snapshot_db()
  missing = self.directory/'missing.key'
  wrong = self.directory/'wrong.key'
  wrong.write_bytes(os.urandom(32))
  wrong.chmod(0o600)
  for key in [missing, wrong]:
   with self.assertRaises(backups.BackupError): backups.verify(self.snapshot, key)
   with self.assertRaises(backups.BackupError): backups.restore(self.snapshot, self.restored, key)
   self.assertFalse(self.restored.exists())
  self.assertFalse(missing.exists())
  self.assertFalse(list(self.directory.glob('.kfd-snapshot-*')))

 def test_corrupt_snapshot_is_rejected_without_touching_source(self):
  self.snapshot.write_bytes(b'not a database')
  before = self.db.read_bytes()
  with self.assertRaises(backups.BackupError): backups.restore(self.snapshot, self.restored, self.key)
  self.assertEqual(self.db.read_bytes(), before)
  self.assertFalse(self.restored.exists())

 def test_tampered_source_foreign_key_error_and_trigger_are_rejected(self):
  self.snapshot_db()
  conn = sqlite3.connect(self.snapshot)
  try:
   conn.execute('UPDATE calendar_feeds SET url=?', ('private-corrupted-secret',))
   conn.commit()
   with self.assertRaises(backups.BackupError) as caught: backups.verify(self.snapshot, self.key)
   self.assertNotIn('private-corrupted-secret', str(caught.exception))
  finally: conn.close()
  self.snapshot.unlink()
  self.snapshot_db()
  conn = sqlite3.connect(self.snapshot)
  try:
   conn.execute('UPDATE shopping SET household_id=999')
   conn.commit()
   with self.assertRaises(backups.BackupError): backups.verify(self.snapshot, self.key)
   conn.execute('UPDATE shopping SET household_id=1')
   conn.execute("CREATE TRIGGER poison AFTER DELETE ON sessions BEGIN DELETE FROM shopping; END")
   conn.commit()
   with self.assertRaises(backups.BackupError): backups.restore(self.snapshot, self.restored, self.key)
   self.assertFalse(self.restored.exists())
  finally: conn.close()

 def test_failure_and_destination_creation_race_leave_no_partial_snapshot(self):
  def failed_copy(*args): raise sqlite3.OperationalError('private underlying diagnostic')
  with patch.object(backups, 'copy_database', failed_copy):
   with self.assertRaises(backups.BackupError) as caught: self.snapshot_db()
  self.assertNotIn('private underlying', str(caught.exception))
  self.assertFalse(self.snapshot.exists())
  self.assertFalse(list(self.directory.glob('.kfd-snapshot-*')))
  def race(source, target):
   Path(target).write_bytes(b'other writer won')
   raise FileExistsError
  with patch.object(backups.os, 'link', race):
   with self.assertRaises(backups.BackupError): self.snapshot_db()
  self.assertEqual(self.snapshot.read_bytes(), b'other writer won')
  self.assertFalse(list(self.directory.glob('.kfd-snapshot-*')))

 def test_deadline_and_size_limits_fail_without_publishing(self):
  for option in [('DEADLINE_SECONDS', -1), ('MAX_DATABASE_BYTES', 1)]:
   with patch.object(backups, *option):
    with self.assertRaises(backups.BackupError): self.snapshot_db()
   self.assertFalse(self.snapshot.exists())

 def test_cli_backup_verify_restore_and_failure_exit_codes(self):
  env = {**os.environ, 'KFD_DB':str(self.db)}
  cli_dir = self.directory/'cli-snapshot'
  cli_copy = cli_dir/'family.sqlite3'
  commands = [
   ['backup', str(cli_dir)],
   ['verify-backup', str(cli_copy), '--key-file', str(self.key)],
   ['restore', str(cli_copy), str(self.directory/'cli-restore'), '--key-file', str(self.key)],
  ]
  for args in commands:
   result = subprocess.run([sys.executable,'-m','app.manage',*args],cwd=ROOT,env=env,capture_output=True,text=True,timeout=10)
   self.assertEqual(result.returncode, 0, result.stderr)
  failed = subprocess.run([sys.executable,'-m','app.manage',*commands[0]],cwd=ROOT,env=env,capture_output=True,text=True,timeout=10)
  self.assertNotEqual(failed.returncode, 0)
  self.assertNotIn('Traceback', failed.stderr)

 def test_missing_database_never_creates_an_empty_database_or_key(self):
  missing = self.directory/'missing.sqlite3'
  with self.assertRaises(backups.BackupError): backups.backup(missing, self.snapshot)
  self.assertFalse(missing.exists())
  self.assertFalse(storage_secrets.key_path(missing).exists())
  self.assertFalse(self.snapshot.exists())
