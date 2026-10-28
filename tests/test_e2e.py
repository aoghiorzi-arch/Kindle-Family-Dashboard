"""End-to-end checks: a phone edit changes the next preview frame, and the frame matches the saved data.

The HTTP tests always run. The browser test drives the real phone UI with Playwright and is skipped
when Node or Playwright is not installed.
"""
import unittest, tempfile, threading, http.client, json, subprocess, shutil, os
from datetime import date
from pathlib import Path
from unittest.mock import patch
from PIL import ImageDraw
from app import server, store, auth, weather
from app.render import png_bytes

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT/'app'/'seed.json').read_text())
PASSWORD = 'family-demo-pass'

class Served(unittest.TestCase):
 def serve(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.db = Path(self.tmp.name)/'family.sqlite3'
  store.init_db(self.db)
  conn = store.connect(self.db)
  self.hh = store.create_household(conn, 'Test')
  store.create_user(conn, self.hh, 'sam', auth.hash_password(PASSWORD), 'admin')
  other = store.create_household(conn, 'Other')
  store.create_user(conn, other, 'mallory', auth.hash_password('another long pass'), 'admin')
  conn.close()
  self.httpd = server.make_server(self.db, port=0)
  self.port = self.httpd.server_address[1]
  threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
  self.addCleanup(self.stop)

 def stop(self):
  self.httpd.shutdown()
  self.httpd.server_close()
  self.tmp.cleanup()

 def request(self, method, path, body=None, headers=None):
  c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
  c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
   headers={'Content-Type': 'application/json', **(headers or {})})
  r = c.getresponse()
  raw = r.read()
  out = (r.status, raw)
  c.close()
  return out

 def sign_in(self, username=None, password=PASSWORD):
  c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
  c.request('POST', '/api/login', body=json.dumps({'username': username or 'sam', 'password': password}).encode(),
   headers={'Content-Type': 'application/json'})
  r = c.getresponse()
  raw = r.read()
  cookie = r.getheader('Set-Cookie').split(';')[0]
  c.close()
  self.assertEqual(r.status, 200, raw)
  return {'Cookie': cookie, 'X-CSRF-Token': json.loads(raw)['csrf'], 'Origin': f'http://127.0.0.1:{self.port}'}

 def frame(self, headers):
  status, raw = self.request('GET', '/frame.png', headers=headers)
  self.assertEqual(status, 200)
  return raw

class PhoneEditTest(Served):
 def setUp(self):
  self.serve()
  self.sam = self.sign_in()

 def expected_frame(self):
  """The frame the server should produce from the saved data, built independently of the request path."""
  conn = store.connect(self.db)
  try:
   block = weather.frame_weather(conn, self.hh, weather.FakeProvider(FIXTURE['weather']), 0, date.today().isoformat())
   return png_bytes(store.snapshot(conn, self.hh, date.today().isoformat(), block))
  finally:
   conn.close()

 def test_edits_change_the_next_frame_and_frame_matches_saved_data(self):
  before = self.frame(self.sam)
  status, _ = self.request('POST', '/api/shopping', {'title': 'Cheese'}, self.sam)
  self.assertEqual(status, 201)
  after_add = self.frame(self.sam)
  self.assertNotEqual(before, after_add)
  self.assertEqual(after_add, self.expected_frame())
  item = json.loads(self.request('GET', '/api/state', headers=self.sam)[1])['shopping'][0]['id']
  self.assertEqual(self.request('POST', f'/api/shopping/{item}/delete', {}, self.sam)[0], 200)
  self.assertEqual(self.frame(self.sam), before)

 def test_private_event_is_drawn_as_busy(self):
  self.assertEqual(self.request('POST', '/api/events', {'title': 'Secret surgery', 'time': '10:00', 'private': True}, self.sam)[0], 201)
  drawn = []
  original = ImageDraw.ImageDraw.text
  def capture(draw, xy, text, *args, **kwargs):
   drawn.append(str(text))
   return original(draw, xy, text, *args, **kwargs)
  with patch.object(ImageDraw.ImageDraw, 'text', capture):
   self.frame(self.sam)
  self.assertIn('Busy', drawn)
  self.assertNotIn('Secret surgery', drawn)

 def test_another_household_edit_does_not_change_this_preview(self):
  before = self.frame(self.sam)
  mallory = self.sign_in('mallory', 'another long pass')
  self.assertEqual(self.request('POST', '/api/shopping', {'title': 'Bread'}, mallory)[0], 201)
  self.assertEqual(self.frame(self.sam), before)

 def test_preview_needs_sign_in(self):
  self.assertEqual(self.request('GET', '/frame.png')[0], 401)

class BrowserEndToEndTest(Served):
 """Runs the browser scripts against one server: the phone edit path, then the admin settings path."""
 SCRIPTS = ['phone_edit.js', 'admin_calendar.js']

 def run_script(self, name, env):
  result = subprocess.run(['node', str(ROOT/'tests'/'e2e'/name)], env=env, capture_output=True, text=True, timeout=180)
  return result

 def test_browser_paths_through_the_real_pages(self):
  if shutil.which('node') is None:
   self.skipTest('node is not installed')
  self.serve()
  conn = store.connect(self.db)
  store.set_location(conn, self.hh, 51.5074, -0.1278, 'Europe/London')
  conn.close()
  env = {**os.environ, 'E2E_BASE': f'http://127.0.0.1:{self.port}', 'E2E_USER': 'sam', 'E2E_PASS': PASSWORD}
  npm = shutil.which('npm')
  if npm:
   global_root = subprocess.run([npm, 'root', '-g'], capture_output=True, text=True, timeout=30).stdout.strip()
   env['NODE_PATH'] = os.pathsep.join(filter(None, [global_root, env.get('NODE_PATH', '')]))
  for script in self.SCRIPTS:
   with self.subTest(script=script):
    result = self.run_script(script, env)
    if result.returncode == 77:
     self.skipTest('playwright is not installed')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == '__main__':
 unittest.main()
