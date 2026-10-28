import subprocess
import unittest
from unittest.mock import patch
from app import ics
from test_ics import calendar


class RecurrenceTest(unittest.TestCase):
 def parse(self, *entries, today='2026-10-28', tz='Europe/London'):
  return ics.parse_events(calendar(*entries), tz, today)

 def test_daily_count_and_until_are_respected(self):
  rows, skipped = self.parse('UID:a\nDTSTART:20261028T090000\nRRULE:FREQ=DAILY;COUNT=3\nSUMMARY:Daily')
  self.assertEqual([r['day'] for r in rows], ['2026-10-28','2026-10-29','2026-10-30'])
  self.assertEqual(skipped, 0)
  rows, _ = self.parse('UID:b\nDTSTART:20261027T090000Z\nRRULE:FREQ=DAILY;UNTIL=20261029T090000Z')
  self.assertEqual([r['day'] for r in rows], ['2026-10-28','2026-10-29'])

 def test_weekly_local_time_survives_bst_transition(self):
  rows, _ = self.parse('UID:a\nDTSTART;TZID=Europe/London:20260322T090000\nRRULE:FREQ=WEEKLY;COUNT=3', today='2026-03-22')
  self.assertEqual([(r['day'],r['time']) for r in rows], [('2026-03-22','09:00'),('2026-03-29','09:00'),('2026-04-05','09:00')])

 def test_weekdays_interval_and_monthly_bysetpos(self):
  rows, _ = self.parse('UID:a\nDTSTART:20261026T090000\nRRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;COUNT=6')
  self.assertEqual([r['day'] for r in rows], ['2026-10-28','2026-11-09','2026-11-11','2026-11-23','2026-11-25'])
  rows, _ = self.parse('UID:b\nDTSTART:20260130T090000\nRRULE:FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1')
  self.assertEqual([r['day'] for r in rows], ['2026-10-30'])

 def test_all_day_yearly_and_rdate(self):
  rows, _ = self.parse('UID:a\nDTSTART;VALUE=DATE:20241028\nRRULE:FREQ=YEARLY\nRDATE;VALUE=DATE:20261101\nSUMMARY:Birthday')
  self.assertEqual([(r['day'],r['time']) for r in rows], [('2026-10-28',''),('2026-11-01','')])

 def test_exdate_and_moved_instance_replace_original(self):
  rows, _ = self.parse('UID:a\nDTSTART:20261028T090000\nRRULE:FREQ=DAILY;COUNT=4\nEXDATE:20261029T090000\nSUMMARY:Original',
   'UID:a\nRECURRENCE-ID:20261030T090000\nDTSTART:20261030T140000\nSUMMARY:Moved')
  self.assertEqual([(r['day'],r['time'],r['title']) for r in rows],
   [('2026-10-28','09:00','Original'),('2026-10-30','14:00','Moved'),('2026-10-31','09:00','Original')])

 def test_cancelled_instance_and_cancelled_series(self):
  rows, _ = self.parse('UID:a\nDTSTART:20261028T090000\nRRULE:FREQ=DAILY;COUNT=3',
   'UID:a\nRECURRENCE-ID:20261029T090000\nDTSTART:20261029T090000\nSTATUS:CANCELLED')
  self.assertEqual([r['day'] for r in rows], ['2026-10-28','2026-10-30'])
  rows, _ = self.parse('UID:b\nDTSTART:20261028T090000\nRRULE:FREQ=DAILY\nSTATUS:CANCELLED')
  self.assertEqual(rows, [])

 def test_private_series_remains_private_when_exception_omits_class(self):
  rows, _ = self.parse('UID:a\nDTSTART:20261028T090000\nRRULE:FREQ=DAILY;COUNT=2\nCLASS:PRIVATE\nSUMMARY:Secret',
   'UID:a\nRECURRENCE-ID:20261029T090000\nDTSTART:20261029T100000\nSUMMARY:Moved secret')
  self.assertEqual(len(rows), 2)
  self.assertTrue(all(r['private'] for r in rows))

 def test_unbounded_series_has_a_finite_window(self):
  rows, _ = self.parse('UID:a\nDTSTART:20200101T090000\nRRULE:FREQ=DAILY')
  self.assertEqual(len(rows), ics.WINDOW_DAYS)
  self.assertEqual(rows[-1]['day'], '2026-11-27')

 def test_expansion_limit_and_worker_deadline_preserve_safe_error(self):
  text = calendar(*[f'UID:{i}\nDTSTART:20200101T090000\nRRULE:FREQ=DAILY' for i in range(17)])
  with self.assertRaises(ValueError): ics.parse_events(text, 'Europe/London', '2026-10-28')
  with patch.object(ics.subprocess, 'run', side_effect=subprocess.TimeoutExpired('worker', 6)):
   with self.assertRaisesRegex(ValueError, 'supported limits'):
    ics.parse_events('private calendar source', 'Europe/London')

 def test_html_and_oversized_sources_are_refused(self):
  with self.assertRaises(ValueError): ics.parse_events('<html>not a calendar</html>', 'Europe/London')
  with self.assertRaises(ValueError): ics.parse_events('x' * (ics.MAX_BYTES+1), 'Europe/London')
