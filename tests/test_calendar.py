import unittest, tempfile, threading, http.client, json
from pathlib import Path
from unittest.mock import patch
from PIL import ImageDraw
from app import server, store, auth

class CalendarTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.db = Path(self.tmp.name)/'family.sqlite3'
  store.init_db(self.db)
  conn = store.connect(self.db)
  self.hh = store.create_household(conn, 'Test')
  store.create_user(conn, self.hh, 'sam', auth.hash_password('family-demo-pass'), 'admin')
  store.create_user(conn, self.hh, 'jo', auth.hash_password('family-demo-pass'), 'member')
  store.set_location(conn, self.hh, 51.5074, -0.1278, 'Europe/London')
  self.today = store.household_today(conn, self.hh)
  conn.close()
  self.httpd = server.make_server(self.db, port=0)
  self.port = self.httpd.server_address[1]
  threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
  self.sam = self.sign_in('sam')

 def tearDown(self):
  self.httpd.shutdown()
  self.httpd.server_close()
  self.tmp.cleanup()

 def sign_in(self, username):
  c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
  c.request('POST', '/api/login', body=json.dumps({'username': username, 'password': 'family-demo-pass'}).encode(),
   headers={'Content-Type': 'application/json'})
  r = c.getresponse()
  raw = r.read()
  cookie = r.getheader('Set-Cookie').split(';')[0]
  c.close()
  return {'Cookie': cookie, 'X-CSRF-Token': json.loads(raw)['csrf'], 'Origin': f'http://127.0.0.1:{self.port}'}

 def request(self, method, path, body=None, headers=None):
  c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
  c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
   headers={'Content-Type': 'application/json', **(headers or {})})
  r = c.getresponse()
  raw = r.read()
  c.close()
  return r.status, raw

 def ics(self, *events):
  body = 'BEGIN:VCALENDAR\r\n' + ''.join(f'BEGIN:VEVENT\r\n{e}\r\nEND:VEVENT\r\n' for e in events) + 'END:VCALENDAR\r\n'
  return {'ics': body}

 def today_stamp(self):
  return self.today.replace('-', '') + 'T100000'

 def drawn_on_frame(self):
  drawn = []
  original = ImageDraw.ImageDraw.text
  def capture(draw, xy, text, *args, **kwargs):
   drawn.append(str(text))
   return original(draw, xy, text, *args, **kwargs)
  with patch.object(ImageDraw.ImageDraw, 'text', capture):
   self.assertEqual(self.request('GET', '/frame.png', headers=self.sam)[0], 200)
  return drawn

 def test_import_needs_location_admin_and_text(self):
  conn = store.connect(self.db)
  store.create_household(conn, 'No location')
  conn.close()
  jo = self.sign_in('jo')
  self.assertEqual(self.request('POST', '/api/calendar', self.ics(f'UID:1\r\nDTSTART:{self.today_stamp()}\r\nSUMMARY:X'), jo)[0], 403)
  self.assertEqual(self.request('POST', '/api/calendar', {'ics': '   '}, self.sam)[0], 400)

 def test_import_counts_and_replaces_previous_import(self):
  status, raw = self.request('POST', '/api/calendar', self.ics(
   f'UID:1\r\nDTSTART:{self.today_stamp()}\r\nSUMMARY:Pickup',
   'UID:2\r\nDTSTART:20300101T100000\r\nSUMMARY:Far away'), self.sam)
  self.assertEqual((status, json.loads(raw)), (200, {'imported': 2, 'skipped': 0}))
  self.assertEqual(json.loads(self.request('GET', '/api/state', headers=self.sam)[1])['calendar'], {'events': 2})
  self.request('POST', '/api/calendar', self.ics(f'UID:3\r\nDTSTART:{self.today_stamp()}\r\nSUMMARY:Only one'), self.sam)
  self.assertEqual(json.loads(self.request('GET', '/api/state', headers=self.sam)[1])['calendar'], {'events': 1})

 def test_only_todays_imported_events_reach_the_display_and_private_is_busy(self):
  self.request('POST', '/api/calendar', self.ics(
   f'UID:1\r\nDTSTART:{self.today_stamp()}\r\nSUMMARY:Secret clinic\r\nCLASS:PRIVATE',
   'UID:2\r\nDTSTART:20300101T100000\r\nSUMMARY:Future party'), self.sam)
  drawn = self.drawn_on_frame()
  self.assertIn('Busy', drawn)
  self.assertNotIn('Secret clinic', drawn)
  self.assertNotIn('Future party', drawn)

 def test_clear_removes_imported_events(self):
  self.request('POST', '/api/calendar', self.ics(f'UID:1\r\nDTSTART:{self.today_stamp()}\r\nSUMMARY:Pickup'), self.sam)
  self.assertEqual(self.request('POST', '/api/calendar/clear', {}, self.sam)[0], 200)
  self.assertEqual(json.loads(self.request('GET', '/api/state', headers=self.sam)[1])['calendar'], {'events': 0})

 def test_oversized_import_is_refused(self):
  big = {'ics': 'x' * 310_000}
  self.assertEqual(self.request('POST', '/api/calendar', big, self.sam)[0], 400)

if __name__ == '__main__':
 unittest.main()
