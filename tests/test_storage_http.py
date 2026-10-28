"""Key failures have a stable HTTP response without leaking server details."""
from app import store, secrets as storage_secrets
from test_e2e import Served


class StorageHTTPTest(Served):
 def setUp(self):
  self.serve()
  self.headers = self.sign_in()

 def test_lost_key_returns_safe_503_without_recreating_it(self):
  key = storage_secrets.key_path(self.db)
  original = key.read_bytes()
  key.unlink()
  try:
   for method, path, payload in [('GET', '/api/state', None), ('GET', '/frame.png', None),
                                  ('POST', '/api/shopping', {'title':'Bread'})]:
    status, body = self.request(method, path, payload, self.headers)
    self.assertEqual(status, 503)
    self.assertNotIn(str(key).encode(), body)
    self.assertFalse(key.exists())
  finally:
   key.write_bytes(original)
   key.chmod(0o600)
  self.assertEqual(self.request('GET', '/api/state', headers=self.headers)[0], 200)

 def test_bad_ciphertext_never_reaches_response_or_resets_events(self):
  conn = store.connect(self.db)
  try:
   store.add_event(conn, self.hh, None, 'Existing event', '09:00', True)
   fid = store.add_feed(conn, self.hh, 'Family', 'https://example.test/do-not-leak-secret-891')
   conn.execute('UPDATE calendar_feeds SET url=? WHERE id=?', ('corrupt-private-source-817', fid))
  finally: conn.close()
  status, body = self.request('GET', '/api/state', headers=self.headers)
  self.assertEqual(status, 503)
  self.assertNotIn(b'corrupt-private-source', body)
  conn = store.connect(self.db)
  try: self.assertEqual(store.list_events(conn, self.hh)[0]['title'], 'Existing event')
  finally: conn.close()
