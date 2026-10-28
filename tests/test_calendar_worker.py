import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from app import calendars, feeds, ics, store
from test_ics import calendar

TEXT = calendar('UID:daily\nDTSTART:20260101T090000\nRRULE:FREQ=DAILY\nSUMMARY:Family event')


class CalendarWorkerTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.db = Path(self.tmp.name)/'family.sqlite3'
  store.init_db(self.db)
  self.conn = store.connect(self.db)
  self.addCleanup(self.conn.close)
  self.hh = store.create_household(self.conn,'Test')
  store.set_location(self.conn,self.hh,51.5,-0.1,'Europe/London')
  self.now = int(datetime.fromisoformat('2026-10-28T12:00:00+00:00').timestamp())
  self.calls, self.fail = [], False
  def fetch(url):
   self.calls.append(url)
   if self.fail: raise OSError('secret URL must not appear')
   return TEXT
  self.service = calendars.CalendarService(self.db,fetch,lambda:self.now)

 def test_schedule_is_opt_in_persisted_and_throttled_after_restart(self):
  fid = store.add_feed(self.conn,self.hh,'Family','https://example.test/secret')
  self.service.tick()
  self.assertEqual(self.calls, [])
  store.set_feed_schedule(self.conn,self.hh,fid,True)
  self.service.tick()
  self.assertEqual(len(self.calls),1)
  self.now += feeds.REFRESH_SECONDS-1
  self.service.tick()
  self.assertEqual(len(self.calls),1)
  restarted = calendars.CalendarService(self.db,self.service.fetcher,lambda:self.now)
  restarted.tick()
  self.assertEqual(len(self.calls),1)
  self.now += 1
  restarted.tick()
  self.assertEqual(len(self.calls),2)
  store.set_feed_schedule(self.conn,self.hh,fid,False)
  self.now += feeds.REFRESH_SECONDS
  restarted.tick()
  self.assertEqual(len(self.calls),2)

 def test_failed_scheduled_refresh_preserves_events_and_uses_retry_interval(self):
  fid = store.add_feed(self.conn,self.hh,'Family','https://example.test/secret',True)
  self.service.tick()
  before = store.day_events(self.conn,self.hh,'2026-10-28')
  self.now += feeds.REFRESH_SECONDS
  self.fail = True
  self.service.tick()
  self.assertEqual(store.day_events(self.conn,self.hh,'2026-10-28'), before)
  row = store.list_feeds(self.conn,self.hh)[0]
  self.assertEqual(row['last_error'],'Could not refresh the feed')
  self.assertEqual(row['last_success'],self.now-feeds.REFRESH_SECONDS)
  self.service.tick()
  self.assertEqual(len(self.calls),2)

 def test_paste_window_extends_without_network_and_clear_stays_cleared(self):
  rows, _ = ics.parse_events(TEXT,'Europe/London','2026-10-28')
  store.replace_calendar(self.conn,self.hh,rows,TEXT,'2026-10-28')
  self.now += 40*86400
  today = store.household_today(self.conn,self.hh,self.now)
  self.assertEqual(store.day_events(self.conn,self.hh,today),[])
  self.service.tick()
  self.assertEqual(len(store.day_events(self.conn,self.hh,today)),1)
  self.assertEqual(self.calls,[])
  store.clear_calendar(self.conn,self.hh)
  self.now += 86400
  self.service.tick()
  self.assertEqual(store.calendar_count(self.conn,self.hh),0)
  self.assertFalse(store.replace_source_events(self.conn,self.hh,'paste',rows,TEXT,today,expected_text=TEXT))

 def test_cached_feed_series_extends_while_offline(self):
  fid = store.add_feed(self.conn,self.hh,'Family','https://example.test/secret',True)
  self.service.tick()
  self.fail = True
  self.now += 40*86400
  self.service.tick()
  today = store.household_today(self.conn,self.hh,self.now)
  self.assertEqual(len(store.day_events(self.conn,self.hh,today)),1)

 def test_delete_during_download_does_not_resurrect_source_or_events(self):
  fid = store.add_feed(self.conn,self.hh,'Family','https://example.test/secret')
  feed = store.get_feed(self.conn,self.hh,fid)
  def fetch(url):
   store.delete_feed(self.conn,self.hh,fid)
   return TEXT
  self.assertEqual(feeds.refresh(self.conn,self.hh,feed,fetch,'Europe/London',self.now),(False,'Feed or location changed; refresh again'))
  self.assertEqual(store.calendar_count(self.conn,self.hh),0)
  self.assertEqual(self.conn.execute('SELECT count(*) FROM calendar_sources').fetchone()[0],0)

 def test_stale_projection_cannot_overwrite_a_new_import(self):
  rows, _ = ics.parse_events(TEXT,'Europe/London','2026-10-28')
  store.replace_calendar(self.conn,self.hh,rows,TEXT,'2026-10-28')
  newer = calendar('UID:new\nDTSTART:20261028T140000\nSUMMARY:New')
  fresh, _ = ics.parse_events(newer,'Europe/London','2026-10-28')
  store.replace_calendar(self.conn,self.hh,fresh,newer,'2026-10-28')
  self.assertFalse(store.replace_source_events(self.conn,self.hh,'paste',rows,TEXT,'2026-10-29',expected_text=TEXT))
  self.assertEqual(store.day_events(self.conn,self.hh,'2026-10-28')[0]['title'],'New')

 def test_migrated_existing_feed_stays_manual(self):
  fid = store.add_feed(self.conn,self.hh,'Old feed','https://example.test/secret')
  self.conn.execute('ALTER TABLE calendar_feeds DROP COLUMN refresh_enabled')
  self.conn.execute('ALTER TABLE calendar_feeds DROP COLUMN skipped_count')
  store.init_db(self.db)
  self.service.tick()
  self.assertEqual(self.calls,[])
  self.assertEqual(store.get_feed(self.conn,self.hh,fid)['refresh_enabled'],0)

 def test_unsupported_feed_rules_are_reported_without_exposing_the_address(self):
  fid = store.add_feed(self.conn,self.hh,'Family','https://example.test/secret')
  text = calendar('UID:frequent\nDTSTART:20261028T090000\nRRULE:FREQ=SECONDLY')
  self.assertEqual(feeds.refresh(self.conn,self.hh,store.get_feed(self.conn,self.hh,fid),lambda url:text,'Europe/London',self.now),(True,None))
  self.assertEqual(store.list_feeds(self.conn,self.hh)[0]['skipped_count'],1)

 def test_timezone_change_cannot_publish_old_zone_projection(self):
  fid = store.add_feed(self.conn,self.hh,'Family','https://example.test/secret')
  def fetch(url):
   store.set_location(self.conn,self.hh,40.7,-74,'America/New_York')
   return TEXT
  ok,error = feeds.refresh(self.conn,self.hh,store.get_feed(self.conn,self.hh,fid),fetch,'Europe/London',self.now)
  self.assertFalse(ok)
  self.assertEqual(store.calendar_count(self.conn,self.hh),0)
