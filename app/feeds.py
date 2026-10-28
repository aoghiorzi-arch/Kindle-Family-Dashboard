"""Read-only calendar subscriptions (iCalendar feeds over HTTPS).

Guards against server-side request forgery:
- https only, standard port, no login in the address, no redirects followed;
- the host name must resolve to a public address, and the connection is made to that exact address
  (so a second DNS answer cannot redirect it to an internal host);
- responses are capped in size and time.
The feed address is secret, so it is never returned to clients or written to error messages.
"""
import http.client, ipaddress, socket, ssl, urllib.parse
from . import ics, store

MAX_BYTES = 2_000_000
TIMEOUT = 10
MAX_FEEDS = 3

class FeedError(Exception):
 """A message that is safe to show: it never contains the feed address."""

def validate_url(url):
 if not isinstance(url, str) or len(url) > 2048:
  raise ValueError('Feed address must be an https:// address up to 2048 characters')
 parts = urllib.parse.urlsplit(url.strip())
 if parts.scheme != 'https' or not parts.hostname:
  raise ValueError('Feed address must start with https://')
 if parts.username or parts.password:
  raise ValueError('Feed address must not contain a login')
 if parts.port not in (None, 443):
  raise ValueError('Feed address must use the standard https port')
 literal = ip_literal(parts.hostname)
 if literal is not None and not literal.is_global:
  raise ValueError('Feed address must be a public internet address')
 # A host name is checked against DNS when the feed is fetched.
 return url.strip()

def ip_literal(host):
 try:
  return ipaddress.ip_address(host)
 except ValueError:
  return None

def host_of(url):
 return urllib.parse.urlsplit(url).hostname or ''

def public_address(hostname):
 try:
  infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
 except OSError:
  raise FeedError('Could not find the feed host')
 addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
 if not addresses or any(not address.is_global for address in addresses):
  raise FeedError('Feed host does not resolve to a public address')
 return addresses[0]

class PinnedHTTPSConnection(http.client.HTTPSConnection):
 """Connects to a fixed, already-checked address while keeping the host name for certificate checks."""
 def __init__(self, hostname, address):
  super().__init__(hostname, timeout=TIMEOUT, context=ssl.create_default_context())
  self.address = address

 def connect(self):
  sock = socket.create_connection((str(self.address), 443), TIMEOUT)
  self.sock = self._context.wrap_socket(sock, server_hostname=self.host)

def fetch_https(url):
 """Downloads the feed text. Raises FeedError with a fixed, safe message on any failure."""
 try:
  url = validate_url(url)
 except ValueError as exc:
  raise FeedError(str(exc))
 parts = urllib.parse.urlsplit(url)
 address = public_address(parts.hostname)
 connection = PinnedHTTPSConnection(parts.hostname, address)
 path = (parts.path or '/') + (f'?{parts.query}' if parts.query else '')
 try:
  connection.request('GET', path, headers={'Accept': 'text/calendar', 'User-Agent': 'FamilyHub'})
  response = connection.getresponse()
  if response.status != 200:
   raise FeedError(f'Feed answered with HTTP {response.status}; redirects are not followed')
  body = response.read(MAX_BYTES + 1)
 except FeedError:
  raise
 except (OSError, http.client.HTTPException, ssl.SSLError):
  raise FeedError('Could not download the feed')
 finally:
  connection.close()
 if len(body) > MAX_BYTES:
  raise FeedError('Feed is too large')
 return body.decode('utf-8', errors='replace')

def refresh(conn, household_id, feed, fetcher, tz, now):
 """Downloads one feed and replaces its events. On failure the last good events are kept."""
 try:
  events, _ = ics.parse_events(fetcher(feed['url']), tz)
 except FeedError as exc:
  store.set_feed_result(conn, feed['id'], now, str(exc))
  return False, str(exc)
 except ValueError:
  store.set_feed_result(conn, feed['id'], now, 'Feed could not be read as a calendar')
  return False, 'Feed could not be read as a calendar'
 store.replace_feed_events(conn, household_id, feed['id'], events)
 store.set_feed_result(conn, feed['id'], now, None)
 return True, None
