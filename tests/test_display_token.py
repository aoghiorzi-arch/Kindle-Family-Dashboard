import json
import sqlite3
import tempfile
from pathlib import Path
from app import backup, store
from test_e2e import Served

FRAME = '/api/display/frame.png'


class DisplayTokenTest(Served):
 def setUp(self):
  self.serve()
  self.admin = self.sign_in()
  self.token = self.make_token('Kindle')

 def make_token(self, name, kind='display', headers=None):
  status, raw = self.request('POST', '/api/tokens', {'name': name, 'kind': kind}, headers or self.admin)
  self.assertEqual(status, 201, raw)
  return json.loads(raw)['token']

 def get(self, token, path=FRAME, extra=None):
  headers = dict(extra or {})
  if token: headers['Authorization'] = 'Bearer ' + token
  return self.request('GET', path, headers=headers)

 def test_display_token_returns_png_and_unchanged_image_gets_304(self):
  status, raw = self.get(self.token)
  self.assertEqual(status, 200)
  self.assertTrue(raw.startswith(b'\x89PNG'))
  import http.client
  c = http.client.HTTPConnection('127.0.0.1', self.port)
  c.request('GET', FRAME, headers={'Authorization': 'Bearer ' + self.token})
  etag = c.getresponse().getheader('ETag'); c.close()
  c = http.client.HTTPConnection('127.0.0.1', self.port)
  c.request('GET', FRAME, headers={'Authorization': 'Bearer ' + self.token, 'If-None-Match': etag})
  r = c.getresponse(); body = r.read(); c.close()
  self.assertEqual((r.status, body), (304, b''))

 def test_edit_changes_display_image(self):
  before = self.get(self.token)[1]
  self.request('POST', '/api/shopping', {'title': 'Milk'}, self.admin)
  self.assertNotEqual(before, self.get(self.token)[1])

 def test_missing_wrong_and_query_string_tokens_are_refused(self):
  self.assertEqual(self.get(None)[0], 401)
  self.assertEqual(self.get('kfd_wrong')[0], 401)
  self.assertEqual(self.request('GET', f'{FRAME}?token={self.token}')[0], 401)
  self.assertEqual(self.request('GET', FRAME, headers={'Cookie': self.admin['Cookie']})[0], 401)

 def test_display_token_cannot_reach_anything_else(self):
  h = {'Authorization': 'Bearer ' + self.token}
  self.assertEqual(self.request('GET', '/api/state', headers=h)[0], 401)
  self.assertEqual(self.request('GET', '/frame.png', headers=h)[0], 401)
  self.assertEqual(self.request('POST', '/api/shortcut/shopping', {'title': 'Milk'}, h)[0], 403)
  self.assertEqual(self.request('POST', '/api/shopping', {'title': 'Milk'}, h)[0], 401)
  self.assertEqual(self.request('POST', '/api/tokens', {'name': 'x'}, h)[0], 401)

 def test_shortcut_token_cannot_read_display_image(self):
  shortcut = self.make_token('Phone', 'shortcut')
  self.assertEqual(self.get(shortcut)[0], 403)

 def test_unknown_token_kind_rejected(self):
  status, _ = self.request('POST', '/api/tokens', {'name': 'x', 'kind': 'admin'}, self.admin)
  self.assertEqual(status, 400)

 def test_household_scoping(self):
  other = self.sign_in('mallory', 'another long pass')
  other_token = self.make_token('Other kindle', headers=other)
  self.request('POST', '/api/shopping', {'title': 'Only Sam'}, self.admin)
  self.assertNotEqual(self.get(self.token)[1], self.get(other_token)[1])
  self.assertEqual(self.get(other_token)[1], self.request('GET', '/frame.png', headers=other)[1])

 def test_revocation_is_immediate_and_token_stored_hashed(self):
  self.assertEqual(self.get(self.token)[0], 200)
  state = json.loads(self.request('GET', '/api/state', headers=self.admin)[1])
  tid = state['tokens'][0]['id']
  self.assertEqual(self.request('POST', f'/api/tokens/{tid}/revoke', {}, self.admin)[0], 200)
  self.assertEqual(self.get(self.token)[0], 401)
  conn = sqlite3.connect(self.db)
  stored = [r[0] for r in conn.execute('SELECT token_hash FROM api_tokens')]
  conn.close()
  self.assertNotIn(self.token, stored)

 def test_member_cannot_create_display_token(self):
  conn = store.connect(self.db)
  from app import auth
  store.create_user(conn, self.hh, 'kid', auth.hash_password('kid long password'), 'member')
  conn.close()
  member = self.sign_in('kid', 'kid long password')
  self.assertEqual(self.request('POST', '/api/tokens', {'name': 'x', 'kind': 'display'}, member)[0], 403)

 def test_restore_invalidates_display_token(self):
  with tempfile.TemporaryDirectory() as tmp:
   snap = backup.backup(self.db, str(Path(tmp)/'snap'))
   restored = backup.restore(snap, str(Path(tmp)/'restored'), key_file=str(self.db) + '.key')
   conn = sqlite3.connect(restored)
   rows = conn.execute('SELECT revoked_at FROM api_tokens').fetchall()
   conn.close()
  self.assertTrue(rows and all(r[0] is not None for r in rows))
