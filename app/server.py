"""Local Family Hub server. Serves on loopback only: there is no HTTPS yet, so do not expose it beyond this machine."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlparse
from pathlib import Path
import json, re, sys, time, threading
from . import store, auth, weather, validate, ics, feeds, frames

ROOT = Path(__file__).resolve().parent
FIXTURE = json.loads((ROOT/'seed.json').read_text())
INDEX = (ROOT/'index.html').read_bytes()
APP_JS = (ROOT/'static'/'app.js').read_bytes()
COOKIE = 'kfd_session'
SESSION_SECONDS = 14*86400
SHORTCUT_SCOPE = 'shopping:add'  # the only scope a Shortcuts token can get
ITEM_ROUTE = re.compile(r'^/api/(shopping|events)/(\d+)/(toggle|delete)$')
TOKEN_REVOKE = re.compile(r'^/api/tokens/(\d+)/revoke$')
FEED_ROUTE = re.compile(r'^/api/feeds/(\d+)/(refresh|delete)$')
ADMIN_ONLY = ('/api/members', '/api/location', '/api/tokens')
CALENDAR_LIMIT = 300_000  # bytes; a family calendar export is much larger than other requests
SECURITY_HEADERS = {
 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
 'X-Content-Type-Options': 'nosniff',
 'X-Frame-Options': 'DENY',
 'Referrer-Policy': 'no-referrer',
 'Cache-Control': 'no-store',
}

def session_cookie(token):
 return f'{COOKIE}={token}; Max-Age={SESSION_SECONDS}; Path=/; HttpOnly; SameSite=Strict'

def clear_cookie():
 return f'{COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict'

def make_handler(db_path, limiter, provider, fetcher, frame_service):
 class Handler(BaseHTTPRequestHandler):
  server_version = 'FamilyHub'

  def log_message(self, fmt, *args):
   pass

  def send_bytes(self, status, body, ctype, extra=None):
   self.send_response(status)
   self.send_header('Content-Type', ctype)
   self.send_header('Content-Length', str(len(body)))
   for name, value in {**SECURITY_HEADERS, **(extra or {})}.items():
    self.send_header(name, value)
   self.end_headers()
   self.wfile.write(body)

  def send_json(self, status, obj, extra=None):
   self.send_bytes(status, json.dumps(obj).encode(), 'application/json', extra)

  def send_error_json(self, status, message):
   self.send_json(status, {'error': message})

  def read_json(self, limit=4096):
   length = int(self.headers.get('Content-Length') or 0)
   if not 0 <= length <= limit: raise ValueError('Invalid body size')
   if length == 0: return {}
   payload = json.loads(self.rfile.read(length))
   if not isinstance(payload, dict): raise ValueError('Body must be a JSON object')
   return payload

  def same_origin(self):
   # Browsers send Origin on cross-site POSTs; refuse any that do not match this server.
   origin = self.headers.get('Origin')
   return origin is None or origin == f"http://{self.headers.get('Host')}"

  def current(self, conn):
   morsel = SimpleCookie(self.headers.get('Cookie', '')).get(COOKIE)
   return store.session_user(conn, morsel.value if morsel else None)

  def do_GET(self):
   path = urlparse(self.path).path
   if path == '/': return self.send_bytes(200, INDEX, 'text/html; charset=utf-8')
   if path == '/static/app.js': return self.send_bytes(200, APP_JS, 'application/javascript; charset=utf-8')
   conn = store.connect(db_path)
   try:
    user = self.current(conn)
    if user is None: return self.send_error_json(401, 'Sign in required')
    if path == '/api/state': return self.send_json(200, self.state(conn, user))
    if path == '/frame.png':
     hh = user['household_id']
     frame = frame_service.refresh(conn, hh)
     if frame is None: return self.send_error_json(503, 'Preview unavailable. Please try again shortly.')
     body, digest, stale = frame
     extra = {'ETag': f'"{digest}"', 'X-Frame-Stale': 'true' if stale else 'false'}
     if self.headers.get('If-None-Match') == extra['ETag']:
      return self.send_bytes(304, b'', 'image/png', extra)
     return self.send_bytes(200, body, 'image/png', extra)
    return self.send_bytes(404, b'Not found', 'text/plain; charset=utf-8')
   finally:
    conn.close()

  def do_POST(self):
   path = urlparse(self.path).path
   conn = store.connect(db_path)
   try:
    payload = self.read_json(CALENDAR_LIMIT if path.startswith('/api/calendar') else 4096)
    if path.startswith('/api/shortcut/'): return self.shortcut(conn, path, payload)
    if not self.same_origin(): return self.send_error_json(403, 'Cross-origin request refused')
    if path == '/api/login': return self.login(conn, payload)
    user = self.current(conn)
    if user is None: return self.send_error_json(401, 'Sign in required')
    if self.headers.get('X-CSRF-Token') != user['csrf']:
     return self.send_error_json(403, 'Missing or invalid CSRF token')
    if path == '/api/logout': return self.logout(conn)
    if path in ADMIN_ONLY or path.startswith(('/api/calendar', '/api/feeds')) or TOKEN_REVOKE.match(path):
     if user['role'] != 'admin': return self.send_error_json(403, 'Admins only')
    return self.change(conn, user, path, payload)
   except ValueError as exc:
    return self.send_error_json(400, str(exc))
   finally:
    conn.close()

  def login(self, conn, payload):
   username = str(payload.get('username', '')).strip()
   password = str(payload.get('password', ''))
   key = username.lower()
   if limiter.blocked(key):
    return self.send_error_json(429, 'Too many attempts. Try again in a few minutes.')
   user = store.get_user(conn, username)
   verified = auth.verify_password(password, user['password_hash'] if user else auth.DUMMY_HASH)
   if user is None or not verified:
    limiter.record_failure(key)
    return self.send_error_json(401, 'Username or password is incorrect')
   limiter.reset(key)
   token, csrf = store.create_session(conn, user['id'], SESSION_SECONDS)
   return self.send_json(200, {'user': user['username'], 'csrf': csrf}, {'Set-Cookie': session_cookie(token)})

  def logout(self, conn):
   morsel = SimpleCookie(self.headers.get('Cookie', '')).get(COOKIE)
   if morsel: store.delete_session(conn, morsel.value)
   return self.send_json(200, {'ok': True}, {'Set-Cookie': clear_cookie()})

  def shortcut(self, conn, path, payload):
   """Bearer-token routes for Apple Shortcuts. Cookies and CSRF do not apply: the token is sent explicitly."""
   header = self.headers.get('Authorization', '')
   token = header[7:] if header.startswith('Bearer ') else ''
   row = store.api_token_for_use(conn, token)
   if row is None: return self.send_error_json(401, 'Invalid or revoked token')
   if path != '/api/shortcut/shopping': return self.send_error_json(404, 'Not found')
   if SHORTCUT_SCOPE not in row['scopes'].split(','): return self.send_error_json(403, 'Token lacks shopping:add')
   store.add_shopping(conn, row['household_id'], row['created_by'], validate.clean_title(payload.get('title')))
   return self.send_json(201, {'ok': True})

  def state(self, conn, user):
   hh = user['household_id']
   state = {
    'user': user['username'],
    'role': user['role'],
    'csrf': user['csrf'],
    'shopping': [{'id': r['id'], 'title': r['title'], 'done': bool(r['done'])} for r in store.list_shopping(conn, hh)],
    'events': [{'id': r['id'], 'title': r['title'], 'time': r['time'], 'private': bool(r['private'])} for r in store.list_events(conn, hh)],
    'members': [{'username': r['username'], 'role': r['role']} for r in store.list_members(conn, hh)],
   }
   if user['role'] == 'admin':
    loc = store.get_location(conn, hh)
    state['location'] = dict(loc) if loc else None
    state['calendar'] = {'events': store.calendar_count(conn, hh)}
    state['feeds'] = [{'id': r['id'], 'label': r['label'], 'host': feeds.host_of(r['url']),
     'last_success': r['last_success'], 'last_error': r['last_error']} for r in store.list_feeds(conn, hh)]
    state['tokens'] = [{'id': r['id'], 'name': r['name'], 'scopes': r['scopes'], 'created_at': r['created_at'],
     'last_used_at': r['last_used_at'], 'revoked': r['revoked_at'] is not None} for r in store.list_api_tokens(conn, hh)]
   return state

  def change(self, conn, user, path, payload):
   hh, uid = user['household_id'], user['user_id']
   if path == '/api/shopping':
    store.add_shopping(conn, hh, uid, validate.clean_title(payload.get('title')))
    return self.send_json(201, {'ok': True})
   if path == '/api/events':
    store.add_event(conn, hh, uid, validate.clean_title(payload.get('title')), validate.clean_time(payload.get('time', '')),
     payload.get('private') is True)
    return self.send_json(201, {'ok': True})
   if path == '/api/members':
    username = validate.clean_username(payload.get('username'))
    password = validate.clean_password(payload.get('password'))
    role = validate.clean_role(payload.get('role', 'member'))
    store.create_user(conn, hh, username, auth.hash_password(password), role)
    return self.send_json(201, {'ok': True})
   if path == '/api/location':
    lat, lon, tz = validate.clean_location(payload.get('lat'), payload.get('lon'), payload.get('tz'))
    store.set_location(conn, hh, lat, lon, tz)
    return self.send_json(200, {'ok': True})
   if path == '/api/tokens':
    name = validate.clean_title(payload.get('name'), limit=40)
    token = store.create_api_token(conn, hh, uid, name, [SHORTCUT_SCOPE])
    # The plain token is returned only here; it cannot be shown again.
    return self.send_json(201, {'token': token, 'name': name, 'scope': SHORTCUT_SCOPE})
   if path == '/api/calendar':
    if store.get_location(conn, hh) is None:
     raise ValueError('Set the location first, so event times match your time zone')
    text = payload.get('ics')
    if not isinstance(text, str) or not text.strip(): raise ValueError('Paste the calendar (.ics) text')
    events, skipped = ics.parse_events(text, store.get_location(conn, hh)['tz'])
    store.replace_calendar(conn, hh, events)
    return self.send_json(200, {'imported': len(events), 'skipped': skipped})
   if path == '/api/feeds':
    loc = store.get_location(conn, hh)
    if loc is None: raise ValueError('Set the location first, so event times match your time zone')
    if store.feed_count(conn, hh) >= feeds.MAX_FEEDS:
     raise ValueError(f'A household can have up to {feeds.MAX_FEEDS} calendar feeds')
    label = validate.clean_title(payload.get('label'), limit=40)
    url = feeds.validate_url(payload.get('url'))
    feed_id = store.add_feed(conn, hh, label, url)
    ok, error = feeds.refresh(conn, hh, store.get_feed(conn, hh, feed_id), fetcher, loc['tz'], int(time.time()))
    return self.send_json(201, {'id': feed_id, 'ok': ok, 'error': error})
   match = FEED_ROUTE.match(path)
   if match:
    feed_id, action = int(match.group(1)), match.group(2)
    if action == 'delete':
     if not store.delete_feed(conn, hh, feed_id): return self.send_error_json(404, 'Not found')
     return self.send_json(200, {'ok': True})
    feed = store.get_feed(conn, hh, feed_id)
    loc = store.get_location(conn, hh)
    if feed is None or loc is None: return self.send_error_json(404, 'Not found')
    ok, error = feeds.refresh(conn, hh, feed, fetcher, loc['tz'], int(time.time()))
    return self.send_json(200, {'ok': ok, 'error': error})
   if path == '/api/calendar/clear':
    store.clear_calendar(conn, hh)
    return self.send_json(200, {'ok': True})
   match = TOKEN_REVOKE.match(path)
   if match:
    if not store.revoke_api_token(conn, hh, int(match.group(1))): return self.send_error_json(404, 'Not found')
    return self.send_json(200, {'ok': True})
   match = ITEM_ROUTE.match(path)
   if match:
    kind, item_id, action = match.group(1), int(match.group(2)), match.group(3)
    if kind == 'shopping' and action == 'toggle': found = store.toggle_shopping(conn, hh, item_id)
    elif kind == 'shopping' and action == 'delete': found = store.delete_shopping(conn, hh, item_id)
    elif kind == 'events' and action == 'delete': found = store.delete_event(conn, hh, item_id)
    else: found = False
    if not found: return self.send_error_json(404, 'Not found')
    return self.send_json(200, {'ok': True})
   return self.send_error_json(404, 'Not found')

 return Handler

class QuietServer(ThreadingHTTPServer):
 def serve_forever(self, poll_interval=0.5):
  stop = threading.Event()
  worker = threading.Thread(target=self.frame_service.run, args=(stop,), daemon=True)
  worker.start()
  try:
   super().serve_forever(poll_interval)
  finally:
   stop.set()
   worker.join()

 def handle_error(self, request, client_address):
  # A browser cancelling an image request mid-download is normal; do not print a traceback for it.
  if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)): return
  super().handle_error(request, client_address)

def make_server(db_path, port=8765, host='127.0.0.1', provider=None, fetcher=None, clock=time.time):
 provider = provider or weather.FakeProvider(FIXTURE['weather'])
 fetcher = fetcher or feeds.fetch_https
 frame_service = frames.FrameService(db_path, provider, clock)
 server = QuietServer((host, port), make_handler(db_path, auth.LoginLimiter(), provider, fetcher, frame_service))
 server.frame_service = frame_service
 return server

def main():
 db_path = store.default_db_path()
 store.init_db(db_path)
 port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
 server = make_server(db_path, port)
 print(f'Family Hub (local only): http://127.0.0.1:{port} — database {db_path} (Ctrl-C to stop)', flush=True)
 server.serve_forever()

if __name__ == '__main__':
 main()

