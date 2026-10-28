"""Portable display-client core: fetch the household frame, validate it, cache it atomically.

Standard library only. UNVERIFIED ON KINDLE HARDWARE: rendering, sleep/wake and startup hooks are supplied
by the caller (`on_new_image`) and are chosen in Stage B once the exact device is known.

The token is read from a file, sent only in an Authorization header, and never logged.
"""
import hashlib, http.client, json, os, random, ssl, struct, tempfile, time, zlib
from pathlib import Path
from urllib.parse import urlparse

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
WIDTH, HEIGHT = 600, 800
FRAME_PATH = '/api/display/frame.png'
MAX_BYTES = 1_000_000  # frames are a few tens of KB; refuse anything absurd
LOOPBACK = {'127.0.0.1', 'localhost', '::1'}


class ClientError(Exception):
    """Expected failure; the message never contains the token."""


def load_config(path):
    raw = json.loads(Path(path).read_text())
    cfg = {'interval': 300, 'timeout': 20, 'backoff_start': 30, 'backoff_max': 1800, 'ca_file': None, **raw}
    for key in ('server_url', 'token_file', 'cache_dir'):
        if not isinstance(cfg.get(key), str) or not cfg[key]: raise ClientError(f'Config needs {key}')
    parsed = urlparse(cfg['server_url'])
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.path not in ('', '/'):
        raise ClientError('server_url must be a bare http(s) origin')
    if parsed.scheme == 'http' and parsed.hostname not in LOOPBACK:
        raise ClientError('Plain http is only allowed for a loopback server; use https')
    return cfg


def read_token(path):
    p = Path(path)
    if os.name == 'posix' and p.stat().st_mode & 0o077:
        raise ClientError('Token file must not be readable by other users (chmod 600)')
    token = p.read_text().strip()
    if not token: raise ClientError('Token file is empty')
    return token


def validate_png(body):
    """Raise ClientError unless body is a complete, CRC-correct 600x800 PNG."""
    if len(body) > MAX_BYTES: raise ClientError('Image too large')
    if not body.startswith(PNG_SIGNATURE): raise ClientError('Not a PNG')
    pos, seen_ihdr, seen_idat, size = len(PNG_SIGNATURE), False, False, None
    while pos + 12 <= len(body):
        length, kind = struct.unpack('>I4s', body[pos:pos + 8])
        data = body[pos + 8:pos + 8 + length]
        crc = body[pos + 8 + length:pos + 12 + length]
        if len(data) != length or len(crc) != 4: raise ClientError('Truncated PNG')
        if zlib.crc32(kind + data) & 0xffffffff != struct.unpack('>I', crc)[0]: raise ClientError('Corrupt PNG')
        if kind == b'IHDR':
            if pos != len(PNG_SIGNATURE) or length != 13: raise ClientError('Bad PNG header')
            size, seen_ihdr = struct.unpack('>II', data[:8]), True
        elif not seen_ihdr: raise ClientError('Bad PNG header')
        elif kind == b'IDAT': seen_idat = True
        elif kind == b'IEND':
            if pos + 12 + length != len(body): raise ClientError('Trailing data after PNG')
            if not seen_idat: raise ClientError('PNG has no image data')
            if size != (WIDTH, HEIGHT): raise ClientError('Unexpected image size')
            return body
        pos += 12 + length
    raise ClientError('Truncated PNG')


class Cache:
    """Last-good image plus its validators. Replaced atomically; a failure never touches it."""
    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.image, self.meta = self.dir / 'frame.png', self.dir / 'frame.json'

    def _atomic(self, path, data):
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix='.tmp-')
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try: os.unlink(tmp)
            except OSError: pass
            raise

    def current(self):
        """(etag, sha256) of a cached image that still validates, else (None, None)."""
        try:
            body = validate_png(self.image.read_bytes())
            meta = json.loads(self.meta.read_text())
            digest = hashlib.sha256(body).hexdigest()
            return (meta.get('etag') if meta.get('sha256') == digest else None), digest
        except (OSError, ValueError, ClientError):
            return None, None

    def store(self, body, etag):
        self._atomic(self.image, body)
        self._atomic(self.meta, json.dumps({'etag': etag, 'sha256': hashlib.sha256(body).hexdigest()}).encode())


class NoRedirect(Exception): pass


def fetch(cfg, token, etag=None):
    """One conditional GET. Returns ('unchanged', None, None) or ('image', body, etag). No redirects are followed."""
    u = urlparse(cfg['server_url'])
    port = u.port or (443 if u.scheme == 'https' else 80)
    if u.scheme == 'https':
        ctx = ssl.create_default_context(cafile=cfg['ca_file'])  # verification stays on
        conn = http.client.HTTPSConnection(u.hostname, port, timeout=cfg['timeout'], context=ctx)
    else:
        conn = http.client.HTTPConnection(u.hostname, port, timeout=cfg['timeout'])
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'image/png'}
    if etag: headers['If-None-Match'] = etag
    try:
        conn.request('GET', FRAME_PATH, headers=headers)
        r = conn.getresponse()
        if r.status == 304: return 'unchanged', None, None
        if r.status in (401, 403): raise ClientError('Server refused the display token (revoked or wrong)')
        if r.status != 200: raise ClientError(f'Server returned HTTP {r.status}')
        length = r.getheader('Content-Length')
        if length is not None and (not length.isdigit() or int(length) > MAX_BYTES): raise ClientError('Image too large')
        body = r.read(MAX_BYTES + 1)
        return 'image', validate_png(body), r.getheader('ETag')
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        raise ClientError(f'Could not reach server ({type(exc).__name__})') from None
    finally:
        conn.close()


def check_once(cfg, cache, on_new_image=None):
    """Poll once. Returns 'unchanged' or 'updated'; raises ClientError on failure with the cache untouched."""
    token = read_token(cfg['token_file'])
    etag, old_digest = cache.current()
    kind, body, new_etag = fetch(cfg, token, etag)
    if kind == 'unchanged' and old_digest is not None: return 'unchanged'
    if kind == 'unchanged':  # server says unchanged but our copy is gone/corrupt: refetch unconditionally
        kind, body, new_etag = fetch(cfg, token, None)
    if hashlib.sha256(body).hexdigest() == old_digest:
        if new_etag != etag: cache.store(body, new_etag)
        return 'unchanged'
    cache.store(body, new_etag)
    if on_new_image: on_new_image(cache.image)
    return 'updated'


def run(cfg, on_new_image=None, stop=lambda: False, sleep=time.sleep, log=print, rng=random.random):
    """Poll forever: `interval` seconds on success, exponential backoff with jitter on failure."""
    cache, failures = Cache(cfg['cache_dir']), 0
    while not stop():
        try:
            result = check_once(cfg, cache, on_new_image)
            failures = 0
            log(f'check ok: {result}')
            delay = cfg['interval']
        except ClientError as exc:
            failures += 1
            delay = min(cfg['backoff_max'], cfg['backoff_start'] * 2 ** (failures - 1)) * (0.75 + rng() * 0.5)
            log(f'check failed ({exc}); keeping last good image; retry in {int(delay)}s')
        if stop(): break
        sleep(delay)
