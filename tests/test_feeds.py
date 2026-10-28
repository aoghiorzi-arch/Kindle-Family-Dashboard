import unittest, tempfile, threading, http.client, json
from pathlib import Path
from unittest.mock import patch
from PIL import ImageDraw
from app import server, store, auth, feeds, ics

FEED_URL = 'https://calendar.example.test/family.ics'
FEED_TEXT = '\r\n'.join(['BEGIN:VCALENDAR',
 'BEGIN:VEVENT', 'UID:f1', 'DTSTART:{day}T120000Z', 'SUMMARY:Clinic visit', 'CLASS:PRIVATE', 'END:VEVENT',
 'BEGIN:VEVENT', 'UID:f2', 'DTSTART:{day}T090000Z', 'SUMMARY:School run', 'END:VEVENT',
 'END:VCALENDAR'])

class FakeFetcher:
 """Stands in for the network. Records what it was asked for and can be made to fail."""
 def __init__(self):
  self.body, self.error, self.urls = None, None, []

 def __call__(self, url):
  self.urls.append(url)
  if self.error: raise feeds.FeedError(self.error)
  return self.body

class UrlRulesTest(unittest.TestCase):
 def test_accepts_public_https(self):
  self.assertEqual(feeds.validate_url(FEED_URL), FEED_URL)

 def test_refuses_unsafe_addresses(self):
  for url in ['http://calendar.example.test/a.ics', 'https://user:pw@calendar.example.test/a.ics',
              'https://calendar.example.test:8443/a.ics', 'https://127.0.0.1/a.ics', 'https://10.0.0.5/a.ics',
              'https://169.254.169.254/latest', 'https://[::1]/a.ics', 'file:///etc/passwd', 'https://', 'x' * 3000]:
   with self.subTest(url=url[:40]):
    with self.assertRaises(ValueError):
     feeds.validate_url(url)

 def test_refuses_non_text(self):
  with self.assertRaises(ValueError):
   feeds.validate_url(None)

 def test_fetch_refuses_internal_addresses_without_connecting(self):
  for url in ['https://127.0.0.1/a.ics', 'https://169.254.169.254/latest']:
   with self.subTest(url=url):
    with patch.object(feeds.socket, 'create_connection', side_effect=AssertionError('must not connect')):
     with self.assertRaises(feeds.FeedError):
      feeds.fetch_https(url)

 def test_host_is_shown_without_the_secret_path(self):
  self.assertEqual(feeds.host_of('https://calendar.example.test/private/SECRET-TOKEN.ics'), 'calendar.example.test')

class FeedStoreTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.db = Path(self.tmp.name)/'f.sqlite3'
  store.init_db(self.db)
  self.conn = store.connect(self.db)
  self.hh = store.create_household(self.conn, 'Test')
  store.set_location(self.conn, self.hh, 51.5074, -0.1278, 'Europe/London')
  self.fetcher = FakeFetcher()
  self.fetcher.body = FEED_TEXT.format(day='20261028')

 def tearDown(self):
  self.conn.close()
  self.tmp.cleanup()

 def refresh(self, feed_id):
  feed = store.get_feed(self.conn, self.hh, feed_id)
  return feeds.refresh(self.conn, self.hh, feed, self.fetcher, 'Europe/London', 1000)

 def test_failed_refresh_keeps_last_good_events_and_records_error(self):
  fid = store.add_feed(self.conn, self.hh, 'Family', FEED_URL)
  self.assertEqual(self.refresh(fid), (True, None))
  self.assertEqual(len(store.day_events(self.conn, self.hh, '2026-10-28')), 2)
  self.fetcher.error = 'Could not download the feed'
  self.assertEqual(self.refresh(fid), (False, 'Could not download the feed'))
  self.assertEqual(len(store.day_events(self.conn, self.hh, '2026-10-28')), 2)
  row = store.list_feeds(self.conn, self.hh)[0]
  self.assertEqual(row['last_error'], 'Could not download the feed')
  self.assertEqual(row['last_success'], 1000)

 def test_unreadable_or_oversized_feed_is_reported_not_stored(self):
  fid = store.add_feed(self.conn, self.hh, 'Family', FEED_URL)
  self.fetcher.body = 'BEGIN:VCALENDAR\r\n' + 'BEGIN:VEVENT\r\nDTSTART:20261028T100000\r\nSUMMARY:E\r\nEND:VEVENT\r\n' * (ics.MAX_EVENTS + 1) + 'END:VCALENDAR'
  ok, error = self.refresh(fid)
  self.assertFalse(ok)
  self.assertEqual(store.day_events(self.conn, self.hh, '2026-10-28'), [])

 def test_feed_events_survive_paste_import_and_clear(self):
  fid = store.add_feed(self.conn, self.hh, 'Family', FEED_URL)
  self.refresh(fid)
  store.replace_calendar(self.conn, self.hh, [{'uid': 'p', 'day': '2026-10-28', 'time': '08:00', 'title': 'Pasted', 'private': False}])
  store.clear_calendar(self.conn, self.hh)
  titles = [e['title'] for e in store.day_events(self.conn, self.hh, '2026-10-28')]
  self.assertIn('School run', titles)
  self.assertNotIn('Pasted', titles)

 def test_deleting_a_feed_removes_only_its_events(self):
  fid = store.add_feed(self.conn, self.hh, 'Family', FEED_URL)
  self.refresh(fid)
  store.replace_calendar(self.conn, self.hh, [{'uid': 'p', 'day': '2026-10-28', 'time': '08:00', 'title': 'Pasted', 'private': False}])
  self.assertTrue(store.delete_feed(self.conn, self.hh, fid))
  self.assertEqual([e['title'] for e in store.day_events(self.conn, self.hh, '2026-10-28')], ['Pasted'])

 def test_other_households_cannot_see_or_delete_a_feed(self):
  fid = store.add_feed(self.conn, self.hh, 'Family', FEED_URL)
  other = store.create_household(self.conn, 'Other')
  self.assertIsNone(store.get_feed(self.conn, other, fid))
  self.assertFalse(store.delete_feed(self.conn, other, fid))

class FeedHttpTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.db = Path(self.tmp.name)/'f.sqlite3'
  store.init_db(self.db)
  conn = store.connect(self.db)
  self.hh = store.create_household(conn, 'Test')
  store.create_user(conn, self.hh, 'sam', auth.hash_password('family-demo-pass'), 'admin')
  store.create_user(conn, self.hh, 'jo', auth.hash_password('family-demo-pass'), 'member')
  store.set_location(conn, self.hh, 51.5074, -0.1278, 'Europe/London')
  self.today = store.household_today(conn, self.hh).replace('-', '')
  conn.close()
  self.fetcher = FakeFetcher()
  self.fetcher.body = FEED_TEXT.format(day=self.today)
  self.httpd = server.make_server(self.db, port=0, fetcher=self.fetcher)
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

 def add_feed(self, label='Family', url=FEED_URL, headers=None):
  return self.request('POST', '/api/feeds', {'label': label, 'url': url}, headers or self.sam)

 def state(self):
  return self.request('GET', '/api/state', headers=self.sam)[1].decode()

 def drawn_on_frame(self):
  drawn = []
  original = ImageDraw.ImageDraw.text
  def capture(draw, xy, text, *args, **kwargs):
   drawn.append(str(text))
   return original(draw, xy, text, *args, **kwargs)
  with patch.object(ImageDraw.ImageDraw, 'text', capture):
   self.assertEqual(self.request('GET', '/frame.png', headers=self.sam)[0], 200)
  return drawn

 def test_adding_a_feed_syncs_and_shows_todays_events_privately(self):
  status, raw = self.add_feed()
  self.assertEqual((status, json.loads(raw)['ok']), (201, True))
  drawn = self.drawn_on_frame()
  self.assertIn('Busy', drawn)
  self.assertIn('School run', drawn)
  self.assertNotIn('Clinic visit', drawn)

 def test_feed_address_is_never_returned_to_clients(self):
  secret = 'https://calendar.example.test/private/SECRET-TOKEN-123.ics'
  self.fetcher.error = 'Could not download the feed'
  self.add_feed(url=secret)
  self.assertNotIn('SECRET-TOKEN-123', self.state())
  self.assertIn('calendar.example.test', self.state())

 def test_failed_sync_is_reported_and_keeps_last_good_events(self):
  self.add_feed()
  self.fetcher.error = 'Could not download the feed'
  feed_id = json.loads(self.state())['feeds'][0]['id']
  status, raw = self.request('POST', f'/api/feeds/{feed_id}/refresh', {}, self.sam)
  self.assertEqual((status, json.loads(raw)), (200, {'ok': False, 'error': 'Could not download the feed'}))
  self.assertIn('School run', self.drawn_on_frame())
  self.assertIn('Could not download the feed', self.state())

 def test_members_cannot_manage_feeds(self):
  jo = self.sign_in('jo')
  self.assertEqual(self.add_feed(headers=jo)[0], 403)
  self.assertNotIn('feeds', json.loads(self.request('GET', '/api/state', headers=jo)[1]))

 def test_feed_must_be_public_https_and_needs_a_location(self):
  self.assertEqual(self.add_feed(url='https://127.0.0.1/a.ics')[0], 400)
  self.assertEqual(self.add_feed(url='http://calendar.example.test/a.ics')[0], 400)
  conn = store.connect(self.db)
  conn.execute('DELETE FROM locations')
  conn.close()
  self.assertEqual(self.add_feed()[0], 400)

 def test_at_most_three_feeds_and_delete_removes_events(self):
  for n in range(3):
   self.assertEqual(self.add_feed(label=f'Feed {n}')[0], 201)
  self.assertEqual(self.add_feed(label='Fourth')[0], 400)
  feed_id = json.loads(self.state())['feeds'][0]['id']
  self.assertEqual(self.request('POST', f'/api/feeds/{feed_id}/delete', {}, self.sam)[0], 200)
  self.assertEqual(len(json.loads(self.state())['feeds']), 2)
  self.assertEqual(self.request('POST', f'/api/feeds/{feed_id}/refresh', {}, self.sam)[0], 404)

if __name__ == '__main__':
 unittest.main()
