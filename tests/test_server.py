import unittest, tempfile, threading, http.client, json, io
from pathlib import Path
from PIL import Image
from app import server, store, auth

class ServerTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.db = Path(self.tmp.name)/'family.sqlite3'
  store.init_db(self.db)
  conn = store.connect(self.db)
  hh = store.create_household(conn, 'Test')
  store.create_user(conn, hh, 'alice', auth.hash_password('correct horse battery'))
  other = store.create_household(conn, 'Other')
  store.create_user(conn, other, 'mallory', auth.hash_password('another long pass'))
  conn.close()
  self.httpd = server.make_server(self.db, port=0)
  self.port = self.httpd.server_address[1]
  threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

 def tearDown(self):
  self.httpd.shutdown()
  self.httpd.server_close()
  self.tmp.cleanup()

 def request(self, method, path, body=None, headers=None):
  c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
  data = json.dumps(body).encode() if body is not None else None
  c.request(method, path, body=data, headers={'Content-Type': 'application/json', **(headers or {})})
  r = c.getresponse()
  raw = r.read()
  headers_out = {k: v for k, v in r.getheaders()}
  c.close()
  return r.status, headers_out, raw

 def login(self, username='alice', password='correct horse battery'):
  status, headers, raw = self.request('POST', '/api/login', {'username': username, 'password': password})
  self.assertEqual(status, 200, raw)
  cookie = headers['Set-Cookie'].split(';')[0]
  csrf = json.loads(raw)['csrf']
  return {'Cookie': cookie, 'X-CSRF-Token': csrf, 'Origin': f'http://127.0.0.1:{self.port}'}

 def test_pages_and_data_need_sign_in(self):
  self.assertEqual(self.request('GET', '/')[0], 200)
  self.assertEqual(self.request('GET', '/api/state')[0], 401)
  self.assertEqual(self.request('GET', '/frame.png')[0], 401)
  self.assertEqual(self.request('POST', '/api/shopping', {'title': 'Milk'})[0], 401)

 def test_security_headers_present(self):
  _, headers, _ = self.request('GET', '/')
  self.assertIn("default-src 'self'", headers['Content-Security-Policy'])
  self.assertEqual(headers['X-Frame-Options'], 'DENY')
  self.assertEqual(headers['Cache-Control'], 'no-store')

 def test_wrong_password_then_rate_limited(self):
  for _ in range(5):
   self.assertEqual(self.request('POST', '/api/login', {'username': 'alice', 'password': 'nope'})[0], 401)
  self.assertEqual(self.request('POST', '/api/login', {'username': 'alice', 'password': 'correct horse battery'})[0], 429)

 def test_unknown_user_gets_same_message(self):
  status, _, raw = self.request('POST', '/api/login', {'username': 'nobody', 'password': 'whatever long'})
  self.assertEqual(status, 401)
  self.assertEqual(json.loads(raw)['error'], 'Username or password is incorrect')

 def test_writes_need_csrf_token_and_same_origin(self):
  auth_headers = self.login()
  bad_csrf = {**auth_headers, 'X-CSRF-Token': 'wrong'}
  self.assertEqual(self.request('POST', '/api/shopping', {'title': 'Milk'}, bad_csrf)[0], 403)
  cross = {**auth_headers, 'Origin': 'http://evil.example'}
  self.assertEqual(self.request('POST', '/api/shopping', {'title': 'Milk'}, cross)[0], 403)
  self.assertEqual(self.request('POST', '/api/shopping', {'title': 'Milk'}, auth_headers)[0], 201)

 def test_input_validation(self):
  h = self.login()
  self.assertEqual(self.request('POST', '/api/shopping', {'title': '   '}, h)[0], 400)
  self.assertEqual(self.request('POST', '/api/events', {'title': 'Club', 'time': '25:99'}, h)[0], 400)
  self.assertEqual(self.request('POST', '/api/events', {'title': 'Club', 'time': '9:05'}, h)[0], 201)

 def test_household_isolation_over_http(self):
  alice, mallory = self.login(), self.login('mallory', 'another long pass')
  self.request('POST', '/api/shopping', {'title': 'Milk'}, alice)
  item_id = json.loads(self.request('GET', '/api/state', headers=alice)[2])['shopping'][0]['id']
  self.assertEqual(json.loads(self.request('GET', '/api/state', headers=mallory)[2])['shopping'], [])
  self.assertEqual(self.request('POST', f'/api/shopping/{item_id}/delete', {}, mallory)[0], 404)
  self.assertEqual(self.request('POST', f'/api/shopping/{item_id}/toggle', {}, mallory)[0], 404)
  self.assertEqual(len(json.loads(self.request('GET', '/api/state', headers=alice)[2])['shopping']), 1)

 def test_toggle_delete_and_event_flow(self):
  h = self.login()
  self.request('POST', '/api/shopping', {'title': 'Eggs'}, h)
  self.request('POST', '/api/events', {'title': 'Dentist', 'time': '09:00', 'private': True}, h)
  state = json.loads(self.request('GET', '/api/state', headers=h)[2])
  self.assertTrue(state['events'][0]['private'])
  self.assertEqual(self.request('POST', f"/api/shopping/{state['shopping'][0]['id']}/toggle", {}, h)[0], 200)
  self.assertTrue(json.loads(self.request('GET', '/api/state', headers=h)[2])['shopping'][0]['done'])
  self.assertEqual(self.request('POST', f"/api/events/{state['events'][0]['id']}/delete", {}, h)[0], 200)
  self.assertEqual(json.loads(self.request('GET', '/api/state', headers=h)[2])['events'], [])

 def test_frame_is_600x800_png(self):
  h = self.login()
  status, headers, raw = self.request('GET', '/frame.png', headers=h)
  self.assertEqual(status, 200)
  self.assertEqual(Image.open(io.BytesIO(raw)).size, (600, 800))

 def test_logout_invalidates_session(self):
  h = self.login()
  self.assertEqual(self.request('POST', '/api/logout', {}, h)[0], 200)
  self.assertEqual(self.request('GET', '/api/state', headers={'Cookie': h['Cookie']})[0], 401)

if __name__ == '__main__':
 unittest.main()
