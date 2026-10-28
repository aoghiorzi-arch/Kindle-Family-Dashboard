import unittest, tempfile, threading, http.client, json, sqlite3
from pathlib import Path
from app import server, store, auth

class AdminTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.db = Path(self.tmp.name)/'family.sqlite3'
  store.init_db(self.db)
  conn = store.connect(self.db)
  self.hh = store.create_household(conn, 'Test')
  store.create_user(conn, self.hh, 'sam', auth.hash_password('family-demo-pass'), 'admin')
  store.create_user(conn, self.hh, 'jo', auth.hash_password('family-demo-pass'), 'member')
  other = store.create_household(conn, 'Other')
  store.create_user(conn, other, 'mallory', auth.hash_password('another long pass'), 'admin')
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
  c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
   headers={'Content-Type': 'application/json', **(headers or {})})
  r = c.getresponse()
  raw = r.read()
  out = (r.status, {k: v for k, v in r.getheaders()}, raw)
  c.close()
  return out

 def login(self, username, password='family-demo-pass'):
  status, headers, raw = self.request('POST', '/api/login', {'username': username, 'password': password})
  self.assertEqual(status, 200, raw)
  return {'Cookie': headers['Set-Cookie'].split(';')[0], 'X-CSRF-Token': json.loads(raw)['csrf'],
   'Origin': f'http://127.0.0.1:{self.port}'}

 def state(self, headers):
  return json.loads(self.request('GET', '/api/state', headers=headers)[2])

 def test_members_cannot_use_admin_routes(self):
  jo = self.login('jo')
  self.assertEqual(self.request('POST', '/api/members', {'username': 'new', 'password': 'long enough pass'}, jo)[0], 403)
  self.assertEqual(self.request('POST', '/api/location', {'lat': 1, 'lon': 1, 'tz': 'UTC'}, jo)[0], 403)
  self.assertEqual(self.request('POST', '/api/tokens', {'name': 'x'}, jo)[0], 403)
  self.assertNotIn('tokens', self.state(jo))
  self.assertNotIn('location', self.state(jo))

 def test_admin_adds_member_who_can_sign_in(self):
  sam = self.login('sam')
  self.assertEqual(self.request('POST', '/api/members', {'username': 'ava', 'password': 'a long pass 1', 'role': 'member'}, sam)[0], 201)
  self.login('ava', 'a long pass 1')
  usernames = [m['username'] for m in self.state(sam)['members']]
  self.assertIn('ava', usernames)

 def test_member_input_rules(self):
  sam = self.login('sam')
  self.assertEqual(self.request('POST', '/api/members', {'username': 'jo', 'password': 'long enough pass'}, sam)[0], 400)
  self.assertEqual(self.request('POST', '/api/members', {'username': 'ok', 'password': 'short'}, sam)[0], 400)
  self.assertEqual(self.request('POST', '/api/members', {'username': 'ok', 'password': 'long enough pass', 'role': 'owner'}, sam)[0], 400)

 def test_location_saved_and_validated(self):
  sam = self.login('sam')
  self.assertEqual(self.request('POST', '/api/location', {'lat': 51.5, 'lon': -0.1, 'tz': 'Europe/London'}, sam)[0], 200)
  self.assertEqual(self.state(sam)['location'], {'lat': 51.5, 'lon': -0.1, 'tz': 'Europe/London'})
  self.assertEqual(self.request('POST', '/api/location', {'lat': 95, 'lon': 0, 'tz': 'UTC'}, sam)[0], 400)
  self.assertEqual(self.request('POST', '/api/location', {'lat': 0, 'lon': 0, 'tz': 'Nowhere/City'}, sam)[0], 400)

 def test_shortcut_token_adds_shopping_only(self):
  sam = self.login('sam')
  status, _, raw = self.request('POST', '/api/tokens', {'name': "Sam's iPhone"}, sam)
  self.assertEqual(status, 201)
  token = json.loads(raw)['token']
  self.assertTrue(token.startswith('kfd_'))
  bearer = {'Authorization': f'Bearer {token}'}
  self.assertEqual(self.request('POST', '/api/shortcut/shopping', {'title': 'Eggs'}, bearer)[0], 201)
  self.assertEqual([i['title'] for i in self.state(sam)['shopping']], ['Eggs'])
  # The token gives no access to the web API or other routes.
  self.assertEqual(self.request('GET', '/api/state', headers=bearer)[0], 401)
  self.assertEqual(self.request('POST', '/api/shortcut/events', {'title': 'x'}, bearer)[0], 404)
  self.assertEqual(self.request('POST', '/api/shortcut/shopping', {'title': '  '}, bearer)[0], 400)

 def test_token_is_shown_once_and_not_listed_in_plain(self):
  sam = self.login('sam')
  token = json.loads(self.request('POST', '/api/tokens', {'name': 'Phone'}, sam)[2])['token']
  listed = json.dumps(self.state(sam)['tokens'])
  self.assertNotIn(token, listed)
  self.assertEqual(self.state(sam)['tokens'][0]['name'], 'Phone')
  check = sqlite3.connect(self.db)
  raw = check.execute('SELECT token_hash FROM api_tokens').fetchall()
  check.close()
  self.assertNotIn(token, str(raw))

 def test_revoked_token_stops_working(self):
  sam = self.login('sam')
  token = json.loads(self.request('POST', '/api/tokens', {'name': 'Old phone'}, sam)[2])['token']
  token_id = self.state(sam)['tokens'][0]['id']
  bearer = {'Authorization': f'Bearer {token}'}
  self.assertEqual(self.request('POST', f'/api/tokens/{token_id}/revoke', {}, sam)[0], 200)
  self.assertEqual(self.request('POST', '/api/shortcut/shopping', {'title': 'Milk'}, bearer)[0], 401)
  self.assertTrue(self.state(sam)['tokens'][0]['revoked'])

 def test_bad_or_missing_tokens_are_refused(self):
  self.assertEqual(self.request('POST', '/api/shortcut/shopping', {'title': 'Milk'})[0], 401)
  self.assertEqual(self.request('POST', '/api/shortcut/shopping', {'title': 'Milk'}, {'Authorization': 'Bearer nope'})[0], 401)

 def test_cannot_revoke_another_households_token(self):
  sam = self.login('sam')
  mallory = self.login('mallory', 'another long pass')
  self.request('POST', '/api/tokens', {'name': 'Sam'}, sam)
  token_id = self.state(sam)['tokens'][0]['id']
  self.assertEqual(self.request('POST', f'/api/tokens/{token_id}/revoke', {}, mallory)[0], 404)
  self.assertFalse(self.state(sam)['tokens'][0]['revoked'])

 def test_token_from_another_household_cannot_see_sams_items(self):
  sam = self.login('sam')
  mallory = self.login('mallory', 'another long pass')
  token = json.loads(self.request('POST', '/api/tokens', {'name': 'M'}, mallory)[2])['token']
  self.request('POST', '/api/shortcut/shopping', {'title': 'Bread'}, {'Authorization': f'Bearer {token}'})
  self.assertEqual(self.state(sam)['shopping'], [])

class MigrationTest(unittest.TestCase):
 def test_old_database_gains_role_column(self):
  with tempfile.TemporaryDirectory() as tmp:
   path = Path(tmp)/'old.sqlite3'
   old = sqlite3.connect(path)
   old.executescript("""CREATE TABLE households (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
    CREATE TABLE users (id INTEGER PRIMARY KEY, household_id INTEGER NOT NULL REFERENCES households(id),
     username TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL, created_at INTEGER NOT NULL);
    INSERT INTO households(id,name) VALUES(1,'Old');
    INSERT INTO users(household_id,username,password_hash,created_at) VALUES(1,'sam','x',0);""")
   old.commit()
   old.close()
   store.init_db(path)
   conn = store.connect(path)
   self.assertEqual(conn.execute('SELECT role FROM users WHERE username=?', ('sam',)).fetchone()['role'], 'member')
   conn.close()

if __name__ == '__main__':
 unittest.main()
