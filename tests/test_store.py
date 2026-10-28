import unittest, tempfile, json
from pathlib import Path
from app import store, auth

class StoreTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.db = Path(self.tmp.name)/'family.sqlite3'
  store.init_db(self.db)
  conn = store.connect(self.db)
  self.hh = store.create_household(conn, 'Test')
  self.other = store.create_household(conn, 'Other')
  self.alice = store.create_user(conn, self.hh, 'alice', auth.hash_password('correct horse battery'))
  self.mallory = store.create_user(conn, self.other, 'mallory', auth.hash_password('another long pass'))
  conn.close()
  self.conn = store.connect(self.db)

 def tearDown(self):
  self.conn.close()
  self.tmp.cleanup()

 def test_password_is_hashed_and_verified(self):
  stored = auth.hash_password('correct horse battery')
  self.assertNotIn('correct horse', stored)
  self.assertTrue(auth.verify_password('correct horse battery', stored))
  self.assertFalse(auth.verify_password('wrong guess', stored))
  self.assertFalse(auth.verify_password('anything', 'not-a-hash'))

 def test_usernames_are_case_insensitive_and_unique(self):
  with self.assertRaises(ValueError):
   store.create_user(self.conn, self.hh, 'ALICE', auth.hash_password('another long pass'))

 def test_usernames_are_validated(self):
  self.assertTrue(auth.valid_username('sam.j_2'))
  self.assertFalse(auth.valid_username('a'))
  self.assertFalse(auth.valid_username('bad name'))

 def test_items_are_scoped_to_household(self):
  item = store.add_shopping(self.conn, self.hh, self.alice, 'Milk')
  self.assertFalse(store.toggle_shopping(self.conn, self.other, item))
  self.assertFalse(store.delete_shopping(self.conn, self.other, item))
  self.assertEqual([r['title'] for r in store.list_shopping(self.conn, self.other)], [])
  self.assertTrue(store.toggle_shopping(self.conn, self.hh, item))
  self.assertTrue(bool(store.list_shopping(self.conn, self.hh)[0]['done']))

 def test_event_delete_is_scoped(self):
  event = store.add_event(self.conn, self.hh, self.alice, 'Dentist', '09:00', False)
  self.assertFalse(store.delete_event(self.conn, self.other, event))
  self.assertTrue(store.delete_event(self.conn, self.hh, event))

 def test_data_survives_reopening_the_database(self):
  store.add_shopping(self.conn, self.hh, self.alice, 'Bread')
  self.conn.close()
  self.conn = store.connect(self.db)
  self.assertEqual([r['title'] for r in store.list_shopping(self.conn, self.hh)], ['Bread'])

 def test_sessions_store_only_a_hash_and_expire(self):
  token, csrf = store.create_session(self.conn, self.alice, 3600)
  raw = self.conn.execute('SELECT token_hash FROM sessions').fetchone()['token_hash']
  self.assertNotEqual(raw, token)
  user = store.session_user(self.conn, token)
  self.assertEqual((user['username'], user['household_id'], user['csrf']), ('alice', self.hh, csrf))
  expired, _ = store.create_session(self.conn, self.alice, -1)
  self.assertIsNone(store.session_user(self.conn, expired))
  store.delete_session(self.conn, token)
  self.assertIsNone(store.session_user(self.conn, token))

 def test_snapshot_feeds_renderer_shape(self):
  store.add_event(self.conn, self.hh, self.alice, 'Secret', '10:00', True)
  store.add_shopping(self.conn, self.hh, self.alice, 'Eggs')
  fixture = json.loads((Path(__file__).resolve().parents[1]/'app'/'seed.json').read_text())
  frame = store.snapshot(self.conn, self.hh, '2026-10-28', fixture['weather'])
  self.assertEqual(frame['events'], [{'title': 'Secret', 'time': '10:00', 'private': True}])
  self.assertEqual(frame['shopping'], [{'title': 'Eggs', 'done': False}])
  self.assertEqual(frame['date'], '2026-10-28')

class LimiterTest(unittest.TestCase):
 def test_blocks_after_limit_and_expires_window(self):
  now = [0.0]
  limiter = auth.LoginLimiter(max_failures=2, window=60, clock=lambda: now[0])
  limiter.record_failure('sam'); limiter.record_failure('sam')
  self.assertTrue(limiter.blocked('sam'))
  self.assertFalse(limiter.blocked('other'))
  now[0] = 61
  self.assertFalse(limiter.blocked('sam'))

if __name__ == '__main__':
 unittest.main()
