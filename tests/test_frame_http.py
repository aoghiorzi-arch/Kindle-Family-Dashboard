import http.client
import json
import threading
from unittest.mock import patch
from app import auth, render, server, store
from test_e2e import Served


class FrameHTTPTest(Served):
 def setUp(self):
  self.serve()
  self.headers = self.sign_in()

 def get_frame(self, extra=None):
  c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
  c.request('GET', '/frame.png', headers={**self.headers, **(extra or {})})
  r = c.getresponse()
  result = r.status, dict(r.getheaders()), r.read()
  c.close()
  return result

 def test_conditional_request_returns_304_but_edit_returns_new_image(self):
  status, headers, before = self.get_frame()
  self.assertEqual(status, 200)
  match = {'If-None-Match': headers['ETag']}
  self.assertEqual(self.get_frame(match)[::2], (304, b''))
  self.request('POST', '/api/shopping', {'title': 'Milk'}, self.headers)
  status, after_headers, after = self.get_frame(match)
  self.assertEqual(status, 200)
  self.assertNotEqual(before, after)
  self.assertNotEqual(headers['ETag'], after_headers['ETag'])

 def test_persistence_and_last_good_frame_survive_server_restart(self):
  self.request('POST', '/api/shopping', {'title': 'Survives restart'}, self.headers)
  before = self.get_frame()[2]
  self.httpd.shutdown()
  self.httpd.server_close()
  self.httpd = server.make_server(self.db, port=0)
  self.port = self.httpd.server_address[1]
  with patch.object(render, 'png_bytes', side_effect=ValueError('render failed')):
   threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
   status, headers, body = self.get_frame()
  self.assertEqual(status, 200)
  self.assertEqual(headers['X-Frame-Stale'], 'true')
  self.assertEqual(body, before)
  state = json.loads(self.request('GET', '/api/state', headers=self.headers)[1])
  self.assertEqual(state['shopping'][0]['title'], 'Survives restart')
  self.assertEqual(self.get_frame()[1]['X-Frame-Stale'], 'false')

 def test_failed_first_frame_returns_503_and_cannot_bypass_auth(self):
  self.get_frame()
  # A household created now cannot have been rendered by the start-up worker pass, so it has no cached frame.
  conn = store.connect(self.db)
  new = store.create_household(conn, 'Fresh')
  store.create_user(conn, new, 'trent', auth.hash_password('fresh long pass'), 'admin')
  conn.close()
  self.headers = self.sign_in('trent', 'fresh long pass')
  # Only Sam has a cached frame. Mallory must never receive it on a failure.
  with patch.object(render, 'png_bytes', side_effect=ValueError('render failed')):
   status, _, body = self.get_frame()
  self.assertEqual(status, 503)
  self.assertIn('Preview unavailable', json.loads(body)['error'])
  self.assertEqual(self.request('GET', '/frame.png')[0], 401)
