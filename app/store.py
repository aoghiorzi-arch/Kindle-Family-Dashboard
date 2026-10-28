"""SQLite persistence for the Family Hub. Every item query is scoped to one household."""
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib, os, secrets, sqlite3, time
from . import content, secrets as storage_secrets

SCHEMA = """
CREATE TABLE IF NOT EXISTS households (
 id INTEGER PRIMARY KEY,
 name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY,
 household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member','admin')),
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 csrf_token TEXT NOT NULL,
 expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS shopping (
 id INTEGER PRIMARY KEY,
 household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 title TEXT NOT NULL,
 done INTEGER NOT NULL DEFAULT 0,
 created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY,
 household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 title TEXT NOT NULL,
 time TEXT NOT NULL DEFAULT '',
 private INTEGER NOT NULL DEFAULT 0,
 created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS locations (
 household_id INTEGER PRIMARY KEY REFERENCES households(id) ON DELETE CASCADE,
 lat REAL NOT NULL,
 lon REAL NOT NULL,
 tz TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS weather_cache (
 household_id INTEGER PRIMARY KEY REFERENCES households(id) ON DELETE CASCADE,
 fetched_at INTEGER NOT NULL,
 payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_tokens (
 id INTEGER PRIMARY KEY,
 household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 name TEXT NOT NULL,
 token_hash TEXT NOT NULL UNIQUE,
 scopes TEXT NOT NULL,
 created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
 created_at INTEGER NOT NULL,
 last_used_at INTEGER,
 revoked_at INTEGER
);
CREATE TABLE IF NOT EXISTS shortcut_requests (
 token_id INTEGER NOT NULL REFERENCES api_tokens(id) ON DELETE CASCADE,
 request_id TEXT NOT NULL,
 title TEXT NOT NULL,
 PRIMARY KEY(token_id, request_id)
);
CREATE TABLE IF NOT EXISTS calendar_events (
 id INTEGER PRIMARY KEY,
 household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 uid TEXT NOT NULL,
 day TEXT NOT NULL,
 time TEXT NOT NULL DEFAULT '',
 title TEXT NOT NULL,
 private INTEGER NOT NULL DEFAULT 0,
 source TEXT NOT NULL DEFAULT 'paste'
);
CREATE TABLE IF NOT EXISTS calendar_feeds (
 id INTEGER PRIMARY KEY,
 household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 label TEXT NOT NULL,
 url TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 last_attempt INTEGER,
 last_success INTEGER,
 last_error TEXT
);
CREATE TABLE IF NOT EXISTS calendar_sources (
 household_id INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 source TEXT NOT NULL,
 text TEXT NOT NULL,
 expanded_day TEXT,
 PRIMARY KEY(household_id, source)
);
CREATE INDEX IF NOT EXISTS calendar_household_day ON calendar_events(household_id, day);
CREATE INDEX IF NOT EXISTS shopping_household ON shopping(household_id);
CREATE INDEX IF NOT EXISTS events_household ON events(household_id);
"""

def default_db_path():
 return Path(os.environ.get('KFD_DB', Path(__file__).resolve().parent.parent/'data'/'family.sqlite3'))

class Connection(sqlite3.Connection):
 """One key snapshot per connection; never log or expose it."""
 cipher = None

def raw_connect(path):
 # Autocommit: each statement is its own transaction, so no explicit commits are needed.
 conn = sqlite3.connect(path, timeout=5, isolation_level=None, factory=Connection)
 conn.row_factory = sqlite3.Row
 conn.execute('PRAGMA foreign_keys=ON')
 return conn

def connect(path):
 conn = raw_connect(path)
 try:
  conn.cipher = storage_secrets.load_cipher(path)
  storage_secrets.verify(conn, conn.cipher)
  conn.execute('PRAGMA secure_delete=ON')
  return conn
 except Exception:
  conn.close()
  raise

def ensure_column(conn, table, column, definition):
 if column not in {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}:
  conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')

def init_db(path):
 Path(path).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
 # New database files are private even under a permissive process umask.
 try:
  fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
 except FileExistsError:
  pass
 else:
  os.close(fd)
 conn = raw_connect(path)
 try:
  if storage_secrets.marker(conn) is not None:
   storage_secrets.verify(conn, storage_secrets.load_cipher(path), allow_pending=True)
  conn.executescript(SCHEMA)
  # Databases created by earlier versions get newer columns added in place.
  ensure_column(conn, 'users', 'role', "TEXT NOT NULL DEFAULT 'member'")
  ensure_column(conn, 'calendar_events', 'source', "TEXT NOT NULL DEFAULT 'paste'")
  ensure_column(conn, 'calendar_feeds', 'refresh_enabled', 'INTEGER NOT NULL DEFAULT 0')
  ensure_column(conn, 'calendar_feeds', 'skipped_count', 'INTEGER NOT NULL DEFAULT 0')
  storage_secrets.initialize(conn, path)
 finally: conn.close()

def hash_token(token):
 return hashlib.sha256(token.encode()).hexdigest()

def first_household_id(conn):
 row = conn.execute('SELECT id FROM households ORDER BY id LIMIT 1').fetchone()
 return row['id'] if row else None

def create_household(conn, name):
 return conn.execute('INSERT INTO households(name) VALUES(?)', (name,)).lastrowid

def create_user(conn, household_id, username, password_hash, role='member'):
 try:
  cur = conn.execute('INSERT INTO users(household_id,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',
   (household_id, username, password_hash, role, int(time.time())))
 except sqlite3.IntegrityError:
  raise ValueError('That username is already taken')
 return cur.lastrowid

def get_user(conn, username):
 return conn.execute('SELECT id,household_id,username,password_hash,role FROM users WHERE username=?', (username,)).fetchone()

def list_members(conn, household_id):
 return conn.execute('SELECT id,username,role FROM users WHERE household_id=? ORDER BY id', (household_id,)).fetchall()

def create_session(conn, user_id, max_age):
 now = int(time.time())
 conn.execute('DELETE FROM sessions WHERE expires_at<=?', (now,))
 token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
 conn.execute('INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES(?,?,?,?)',
  (hash_token(token), user_id, csrf, now + max_age))
 return token, csrf

def session_user(conn, token):
 if not token: return None
 row = conn.execute('''SELECT u.id user_id, u.household_id, u.username, u.role, s.csrf_token csrf, s.expires_at
  FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?''', (hash_token(token),)).fetchone()
 if row is None: return None
 if row['expires_at'] <= int(time.time()):
  delete_session(conn, token)
  return None
 return row

def delete_session(conn, token):
 conn.execute('DELETE FROM sessions WHERE token_hash=?', (hash_token(token),))

def create_api_token(conn, household_id, user_id, name, scopes):
 """Returns the plain token once. Only its hash is stored."""
 token = 'kfd_' + secrets.token_urlsafe(32)
 conn.execute('INSERT INTO api_tokens(household_id,name,token_hash,scopes,created_by,created_at) VALUES(?,?,?,?,?,?)',
  (household_id, name, hash_token(token), ','.join(scopes), user_id, int(time.time())))
 return token

def api_token_for_use(conn, token):
 """The active token's household, scopes and creator, or None. Records the time of use."""
 if not token: return None
 row = conn.execute('SELECT id,household_id,scopes,created_by,revoked_at FROM api_tokens WHERE token_hash=?',
  (hash_token(token),)).fetchone()
 if row is None or row['revoked_at'] is not None: return None
 conn.execute('UPDATE api_tokens SET last_used_at=? WHERE id=?', (int(time.time()), row['id']))
 return row

def list_api_tokens(conn, household_id):
 return conn.execute('''SELECT id,name,scopes,created_at,last_used_at,revoked_at FROM api_tokens
  WHERE household_id=? ORDER BY id''', (household_id,)).fetchall()

def revoke_api_token(conn, household_id, token_id):
 return conn.execute('UPDATE api_tokens SET revoked_at=? WHERE id=? AND household_id=? AND revoked_at IS NULL',
  (int(time.time()), token_id, household_id)).rowcount == 1

def list_shopping(conn, household_id):
 return conn.execute('SELECT id,title,done FROM shopping WHERE household_id=? ORDER BY id', (household_id,)).fetchall()

def add_shopping(conn, household_id, user_id, title):
 return conn.execute('INSERT INTO shopping(household_id,title,created_by,created_at) VALUES(?,?,?,?)',
  (household_id, title, user_id, int(time.time()))).lastrowid

def toggle_shopping(conn, household_id, item_id):
 return conn.execute('UPDATE shopping SET done=1-done WHERE id=? AND household_id=?', (item_id, household_id)).rowcount == 1

def delete_shopping(conn, household_id, item_id):
 return conn.execute('DELETE FROM shopping WHERE id=? AND household_id=?', (item_id, household_id)).rowcount == 1

def list_events(conn, household_id):
 # Undated entries sort first, then by time of day.
 return conn.execute('''SELECT id,title,time,private FROM events WHERE household_id=?
  ORDER BY (time=''), time, id''', (household_id,)).fetchall()

def add_event(conn, household_id, user_id, title, when, private):
 return conn.execute('INSERT INTO events(household_id,title,time,private,created_by,created_at) VALUES(?,?,?,?,?,?)',
  (household_id, title, when, int(private), user_id, int(time.time()))).lastrowid

def delete_event(conn, household_id, item_id):
 return conn.execute('DELETE FROM events WHERE id=? AND household_id=?', (item_id, household_id)).rowcount == 1

def set_location(conn, household_id, lat, lon, tz):
 conn.execute('INSERT OR REPLACE INTO locations(household_id,lat,lon,tz) VALUES(?,?,?,?)', (household_id, lat, lon, tz))
 conn.execute('UPDATE calendar_sources SET expanded_day=NULL WHERE household_id=?', (household_id,))

def get_location(conn, household_id):
 return conn.execute('SELECT lat,lon,tz FROM locations WHERE household_id=?', (household_id,)).fetchone()

def get_weather(conn, household_id):
 return conn.execute('SELECT fetched_at,payload FROM weather_cache WHERE household_id=?', (household_id,)).fetchone()

def put_weather(conn, household_id, fetched_at, payload):
 conn.execute('INSERT OR REPLACE INTO weather_cache(household_id,fetched_at,payload) VALUES(?,?,?)', (household_id, fetched_at, payload))

def household_today(conn, household_id, now=None):
 """Today's date in the household's time zone when a location is set, otherwise the server's date."""
 loc = get_location(conn, household_id)
 tz = ZoneInfo(loc['tz']) if loc else None
 return (datetime.fromtimestamp(now, tz) if now is not None else datetime.now(tz)).date().isoformat()

def replace_source_events(conn, household_id, source, rows, text=None, expanded_day=None, expected_text=None, expected_tz=None):
 """Atomic source replacement. A concurrent delete/edit cannot be resurrected by a worker."""
 conn.execute('BEGIN IMMEDIATE')
 try:
  if expected_tz is not None:
   location = get_location(conn, household_id)
   if location is None or location['tz'] != expected_tz:
    conn.execute('ROLLBACK')
    return False
  if source.startswith('feed:') and get_feed(conn, household_id, int(source[5:])) is None:
   conn.execute('ROLLBACK')
   return False
  if expected_text is not None:
   current = conn.execute('SELECT text FROM calendar_sources WHERE household_id=? AND source=?',
    (household_id, source)).fetchone()
   if current is None or source_text(conn, household_id, source, current['text']) != expected_text:
    conn.execute('ROLLBACK')
    return False
  conn.execute('DELETE FROM calendar_events WHERE household_id=? AND source=?', (household_id, source))
  conn.executemany('INSERT INTO calendar_events(household_id,uid,day,time,title,private,source) VALUES(?,?,?,?,?,?,?)',
   [(household_id, r['uid'], r['day'], r['time'], r['title'], int(r['private']), source) for r in rows])
  if text is not None:
   conn.execute('INSERT OR REPLACE INTO calendar_sources(household_id,source,text,expanded_day) VALUES(?,?,?,?)',
    (household_id, source, storage_secrets.seal(conn.cipher, text,
     storage_secrets.context('calendar-source', household_id, source)), expanded_day))
  else:
   conn.execute('DELETE FROM calendar_sources WHERE household_id=? AND source=?', (household_id, source))
  conn.execute('COMMIT')
  return True
 except Exception:
  conn.execute('ROLLBACK')
  raise

def replace_calendar(conn, household_id, rows, text=None, expanded_day=None):
 return replace_source_events(conn, household_id, 'paste', rows, text, expanded_day)

def calendar_count(conn, household_id):
 return conn.execute('SELECT COUNT(*) n FROM calendar_events WHERE household_id=?', (household_id,)).fetchone()['n']

def clear_calendar(conn, household_id):
 replace_calendar(conn, household_id, [])

def source_text(conn, household_id, source, encrypted):
 return storage_secrets.unseal(conn.cipher, encrypted,
  storage_secrets.context('calendar-source', household_id, source))

def decrypted_feed(conn, household_id, row):
 if row is None: return None
 result = dict(row)
 result['url'] = storage_secrets.unseal(conn.cipher, row['url'],
  storage_secrets.context('feed-url', household_id, row['id']))
 return result

def list_feeds(conn, household_id):
 return [decrypted_feed(conn, household_id, row) for row in conn.execute('''SELECT id,label,url,last_attempt,last_success,last_error,refresh_enabled,skipped_count FROM calendar_feeds
  WHERE household_id=? ORDER BY id''', (household_id,)).fetchall()]

def get_feed(conn, household_id, feed_id):
 return decrypted_feed(conn, household_id, conn.execute('SELECT id,label,url,refresh_enabled,last_attempt FROM calendar_feeds WHERE id=? AND household_id=?',
  (feed_id, household_id)).fetchone())

def feed_count(conn, household_id):
 return conn.execute('SELECT COUNT(*) n FROM calendar_feeds WHERE household_id=?', (household_id,)).fetchone()['n']

def add_feed(conn, household_id, label, url, refresh_enabled=False):
 conn.execute('BEGIN IMMEDIATE')
 try:
  feed_id = conn.execute("INSERT INTO calendar_feeds(household_id,label,url,created_at,refresh_enabled) VALUES(?,?,'',?,?)",
   (household_id, label, int(time.time()), int(refresh_enabled))).lastrowid
  encrypted = storage_secrets.seal(conn.cipher, url, storage_secrets.context('feed-url', household_id, feed_id))
  conn.execute('UPDATE calendar_feeds SET url=? WHERE id=?', (encrypted, feed_id))
  conn.execute('COMMIT')
  return feed_id
 except Exception:
  conn.execute('ROLLBACK')
  raise

def delete_feed(conn, household_id, feed_id):
 """Removes the feed and its events. Returns False when the feed is not this household's."""
 if get_feed(conn, household_id, feed_id) is None: return False
 conn.execute('BEGIN')
 try:
  conn.execute("DELETE FROM calendar_events WHERE household_id=? AND source=?", (household_id, f'feed:{feed_id}'))
  conn.execute('DELETE FROM calendar_feeds WHERE id=? AND household_id=?', (feed_id, household_id))
  conn.execute('DELETE FROM calendar_sources WHERE household_id=? AND source=?', (household_id, f'feed:{feed_id}'))
  conn.execute('COMMIT')
 except Exception:
  conn.execute('ROLLBACK')
  raise
 return True

def set_feed_result(conn, feed_id, now, error, skipped=0):
 if error is None:
  conn.execute('UPDATE calendar_feeds SET last_attempt=?, last_success=?, last_error=NULL, skipped_count=? WHERE id=?', (now, now, skipped, feed_id))
 else:
  conn.execute('UPDATE calendar_feeds SET last_attempt=?, last_error=? WHERE id=?', (now, error, feed_id))

def replace_feed_events(conn, household_id, feed_id, rows, text=None, expanded_day=None, expected_tz=None):
 return replace_source_events(conn, household_id, f'feed:{feed_id}', rows, text, expanded_day, expected_tz=expected_tz)

def set_feed_schedule(conn, household_id, feed_id, enabled):
 return conn.execute('UPDATE calendar_feeds SET refresh_enabled=? WHERE id=? AND household_id=?',
  (int(enabled), feed_id, household_id)).rowcount == 1

def day_events(conn, household_id, day):
 """Manual entries (shown every day until removed) plus imported entries for this day, in time order."""
 items = [{'title': r['title'], 'time': r['time'], 'private': bool(r['private'])} for r in list_events(conn, household_id)]
 items += [{'title': r['title'], 'time': r['time'], 'private': bool(r['private'])} for r in conn.execute(
  'SELECT title,time,private FROM calendar_events WHERE household_id=? AND day=?', (household_id, day)).fetchall()]
 return sorted(items, key=lambda e: (e['time'] == '', e['time']))

def snapshot(conn, household_id, today, weather):
 """Renderer input for one household on one date."""
 return {
  'date': today,
  'weather': weather,
  'quote': content.verse_for(today),
  'events': day_events(conn, household_id, today),
  'shopping': [{'title': r['title'], 'done': bool(r['done'])} for r in list_shopping(conn, household_id)],
 }



class RequestConflict(ValueError):
 pass


def add_shortcut_shopping(conn, token, title, request_id=None):
 """Retain receipts for the token lifetime, including after an item is deleted."""
 if request_id is None:
  add_shopping(conn, token['household_id'], token['created_by'], title)
  return True
 if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128 or any(
   c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in request_id):
  raise ValueError('request_id must contain 1–128 letters, digits, hyphens or underscores')
 conn.execute('BEGIN IMMEDIATE')
 try:
  previous = conn.execute('SELECT title FROM shortcut_requests WHERE token_id=? AND request_id=?',
   (token['id'], request_id)).fetchone()
  if previous is not None:
   if previous['title'] != title: raise RequestConflict('request_id was already used for a different title')
   created = False
  else:
   add_shopping(conn, token['household_id'], token['created_by'], title)
   conn.execute('INSERT INTO shortcut_requests VALUES(?,?,?)', (token['id'], request_id, title))
   created = True
  conn.execute('COMMIT')
  return created
 except Exception:
  conn.execute('ROLLBACK')
  raise
