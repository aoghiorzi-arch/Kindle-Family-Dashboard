import unittest, inspect
from app import ics

def calendar(*events):
 return 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\n' + ''.join(f'BEGIN:VEVENT\r\n{e}\r\nEND:VEVENT\r\n' for e in events) + 'END:VCALENDAR\r\n'

class IcsTest(unittest.TestCase):
 def test_utc_time_becomes_household_time(self):
  events, skipped = ics.parse_events(calendar('UID:1\r\nDTSTART:20261028T120000Z\r\nSUMMARY:Lunch'), 'Europe/London')
  self.assertEqual(events, [{'uid': '1', 'day': '2026-10-28', 'time': '12:00', 'title': 'Lunch', 'private': False}])
  self.assertEqual(skipped, 0)

 def test_tzid_is_converted(self):
  events, _ = ics.parse_events(calendar('UID:2\r\nDTSTART;TZID=America/New_York:20261028T090000\r\nSUMMARY:Call'), 'Europe/London')
  self.assertEqual(events[0]['time'], '13:00')

 def test_floating_time_uses_household_zone(self):
  events, _ = ics.parse_events(calendar('UID:3\r\nDTSTART:20261028T091500\r\nSUMMARY:School'), 'Europe/London')
  self.assertEqual(events[0]['time'], '09:15')

 def test_unknown_tzid_falls_back_to_household_zone(self):
  events, _ = ics.parse_events(calendar('UID:4\r\nDTSTART;TZID=Mars/Olympus:20261028T091500\r\nSUMMARY:X'), 'Europe/London')
  self.assertEqual(events[0]['time'], '09:15')

 def test_all_day_event_has_no_time(self):
  events, _ = ics.parse_events(calendar('UID:5\r\nDTSTART;VALUE=DATE:20261028\r\nSUMMARY:Birthday'), 'Europe/London')
  self.assertEqual((events[0]['day'], events[0]['time']), ('2026-10-28', ''))

 def test_folded_and_escaped_summary(self):
  events, _ = ics.parse_events(calendar('UID:6\r\nDTSTART:20261028T100000\r\nSUMMARY:Dentist\\, Dr\r\n  Lee\\nRoom 2'), 'Europe/London')
  self.assertEqual(events[0]['title'], 'Dentist, Dr Lee Room 2')

 def test_private_and_confidential_are_marked_private(self):
  text = calendar('UID:7\r\nDTSTART:20261028T100000\r\nSUMMARY:A\r\nCLASS:PRIVATE',
                  'UID:8\r\nDTSTART:20261028T110000\r\nSUMMARY:B\r\nCLASS:CONFIDENTIAL',
                  'UID:9\r\nDTSTART:20261028T120000\r\nSUMMARY:C\r\nCLASS:PUBLIC')
  self.assertEqual([e['private'] for e in ics.parse_events(text, 'Europe/London')[0]], [True, True, False])

 def test_recurring_cancelled_and_unreadable_are_skipped(self):
  text = calendar('UID:10\r\nDTSTART:20261028T100000\r\nRRULE:FREQ=DAILY\r\nSUMMARY:Daily',
                  'UID:11\r\nDTSTART:20261028T100000\r\nRECURRENCE-ID:20261027T100000\r\nSUMMARY:Moved',
                  'UID:12\r\nDTSTART:20261028T100000\r\nSTATUS:CANCELLED\r\nSUMMARY:Off',
                  'UID:13\r\nDTSTART:notadate\r\nSUMMARY:Broken',
                  'UID:14\r\nSUMMARY:No start')
  events, skipped = ics.parse_events(text, 'Europe/London')
  self.assertEqual(events, [])
  self.assertEqual(skipped, 5)

 def test_too_many_events_is_refused(self):
  text = calendar(*[f'UID:{i}\r\nDTSTART:20261028T100000\r\nSUMMARY:E{i}' for i in range(ics.MAX_EVENTS + 1)])
  with self.assertRaises(ValueError):
   ics.parse_events(text, 'Europe/London')

 def test_module_never_fetches_urls(self):
  source = inspect.getsource(ics)
  self.assertNotIn('urllib', source)
  self.assertNotIn('http', source.lower().replace('https://', ''))

if __name__ == '__main__':
 unittest.main()
