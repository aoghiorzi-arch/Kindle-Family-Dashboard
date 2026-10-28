"""Local frame lifecycle: periodic generation and household-scoped last-good PNGs.

No feed downloads or device access. Frame files contain family information and live
beside the database; they are never exposed as a public static directory.
"""
import hashlib
import io
import logging
import threading
import time
from pathlib import Path
from PIL import Image
from . import render, store, weather

CHECK_SECONDS = 60
LOG = logging.getLogger(__name__)


def verified_png(body):
 with Image.open(io.BytesIO(body)) as image:
  if image.format != 'PNG' or image.size != (render.W, render.H):
   raise ValueError('Invalid frame')
  image.verify()
 return body


class FrameService:
 def __init__(self, db_path, provider, clock=time.time):
  self.db_path, self.provider, self.clock = db_path, provider, clock
  path = Path(db_path)
  self.directory = path.parent / (path.name + '.frames')
  self.lock = threading.Lock()

 def path(self, household_id):
  return self.directory / f'{int(household_id)}.png'

 def refresh(self, conn, household_id):
  """Returns (PNG, content hash, stale). Failure never replaces a verified frame."""
  with self.lock:
   path = self.path(household_id)
   try:
    now = int(self.clock())
    today = store.household_today(conn, household_id, now)
    block = weather.frame_weather(conn, household_id, self.provider, now, today)
    conn.execute('BEGIN')
    try:
     data = store.snapshot(conn, household_id, today, block)
    finally:
     conn.execute('ROLLBACK')
    body = verified_png(render.png_bytes(data))
    if not path.exists() or path.read_bytes() != body:
     render.atomic_write(path, body)
    stale = False
   except Exception:
    # Never log exception text: it may contain private calendar or family data.
    LOG.warning('Frame refresh failed; retaining the last verified image')
    try:
     body = verified_png(path.read_bytes())
    except Exception:
     return None
    stale = True
   return body, hashlib.sha256(body).hexdigest(), stale

 def refresh_all(self):
  conn = store.connect(self.db_path)
  try:
   for row in conn.execute('SELECT id FROM households ORDER BY id').fetchall():
    self.refresh(conn, row['id'])
  finally:
   conn.close()

 def run(self, stop):
  while not stop.is_set():
   try:
    self.refresh_all()
   except Exception:
    LOG.warning('Frame check failed; retrying on the next interval')
   stop.wait(CHECK_SECONDS)
