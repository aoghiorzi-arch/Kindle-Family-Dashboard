"""Local calendar maintenance, independent of the frame renderer and request threads."""
import logging
import time
from . import feeds, ics, store, secrets as storage_secrets

LOG = logging.getLogger(__name__)
CHECK_SECONDS = 60


class CalendarService:
 def __init__(self, db_path, fetcher, clock=time.time):
  self.db_path, self.fetcher, self.clock = db_path, fetcher, clock

 def tick(self, stop=None):
  conn = store.connect(self.db_path)
  try:
   now = int(self.clock())
   for hh in conn.execute('SELECT id FROM households ORDER BY id').fetchall():
    if stop is not None and stop.is_set(): break
    household_id = hh['id']
    location = store.get_location(conn, household_id)
    if location is None: continue
    today = store.household_today(conn, household_id, now)
    for source in conn.execute('SELECT source,text,expanded_day FROM calendar_sources WHERE household_id=?',
                               (household_id,)).fetchall():
     if stop is not None and stop.is_set(): break
     if source['expanded_day'] == today: continue
     try:
      text = store.source_text(conn, household_id, source['source'], source['text'])
      rows, _ = ics.parse_events(text, location['tz'], today)
      store.replace_source_events(conn, household_id, source['source'], rows,
       text, today, expected_text=text, expected_tz=location['tz'])
     except (ValueError, storage_secrets.StorageError):
      LOG.warning('Calendar expansion failed; retaining saved events')
    for feed in store.list_feeds(conn, household_id):
     if stop is not None and stop.is_set(): break
     if not feed['refresh_enabled']: continue
     feeds.refresh(conn, household_id, feed, self.fetcher, location['tz'], now, scheduled=True)
  finally:
   conn.close()

 def run(self, stop):
  while not stop.is_set():
   try: self.tick(stop)
   except Exception:
    LOG.warning('Calendar maintenance failed; retrying on the next interval')
   stop.wait(CHECK_SECONDS)
