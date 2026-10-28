"""SQLite persistence for the Family Hub. Every item query is scoped to one household."""
from pathlib import Path
import hashlib, os, secrets, sqlite3, time

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
CREATE INDEX IF NOT EXISTS shopping_household ON shopping(household_id);
CREATE INDEX IF NOT EXISTS events_household ON events(household_id);
"""

def default_db_path():
 return Path(os.environ.get('KFD_DB', Path(__file__).resolve().parent.parent/'data'/'family.sqlite3'))

def connect(path):
 # Autocommit: each statement is its own transaction, so no explicit commits are needed.
 conn = sqlite3.connect(path, timeout=5, isolation_level=None)
 conn.row_factory = sqlite3.Row
 conn.execute('PRAGMA foreign_keys=ON')
 return conn

def init_db(path):
 Path(path).parent.mkdir(parents=True, exist_ok=True)
 conn = connect(path)
 try: conn.executescript(SCHEMA)
 finally: conn.close()

def hash_token(token):
 return hashlib.sha256(token.encode()).hexdigest()

def first_household_id(conn):
 row = conn.execute('SELECT id FROM households ORDER BY id LIMIT 1').fetchone()
 return row['id'] if row else None

def create_household(conn, name):
 return conn.execute('INSERT INTO households(name) VALUES(?)', (name,)).lastrowid

def create_user(conn, household_id, username, password_hash):
 try:
  cur = conn.execute('INSERT INTO users(household_id,username,password_hash,created_at) VALUES(?,?,?,?)',
   (household_id, username, password_hash, int(time.time())))
 except sqlite3.IntegrityError:
  raise ValueError('That username is already taken')
 return cur.lastrowid

def get_user(conn, username):
 return conn.execute('SELECT id,household_id,username,password_hash FROM users WHERE username=?', (username,)).fetchone()

def create_session(conn, user_id, max_age):
 now = int(time.time())
 conn.execute('DELETE FROM sessions WHERE expires_at<=?', (now,))
 token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
 conn.execute('INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES(?,?,?,?)',
  (hash_token(token), user_id, csrf, now + max_age))
 return token, csrf

def session_user(conn, token):
 if not token: return None
 row = conn.execute('''SELECT u.id user_id, u.household_id, u.username, s.csrf_token csrf, s.expires_at
  FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?''', (hash_token(token),)).fetchone()
 if row is None: return None
 if row['expires_at'] <= int(time.time()):
  delete_session(conn, token)
  return None
 return row

def delete_session(conn, token):
 conn.execute('DELETE FROM sessions WHERE token_hash=?', (hash_token(token),))

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

def get_location(conn, household_id):
 return conn.execute('SELECT lat,lon,tz FROM locations WHERE household_id=?', (household_id,)).fetchone()

def get_weather(conn, household_id):
 return conn.execute('SELECT fetched_at,payload FROM weather_cache WHERE household_id=?', (household_id,)).fetchone()

def put_weather(conn, household_id, fetched_at, payload):
 conn.execute('INSERT OR REPLACE INTO weather_cache(household_id,fetched_at,payload) VALUES(?,?,?)', (household_id, fetched_at, payload))

def snapshot(conn, household_id, today, fixture, weather):
 """Renderer input for one household. The quote still comes from the fixture until a content adapter exists."""
 return {
  'date': today,
  'weather': weather,
  'quote': fixture.get('quote', {}),
  'events': [{'title': r['title'], 'time': r['time'], 'private': bool(r['private'])} for r in list_events(conn, household_id)],
  'shopping': [{'title': r['title'], 'done': bool(r['done'])} for r in list_shopping(conn, household_id)],
 }
