import json
import os
import struct
import sys
import tempfile
import threading
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from display_client import client
from app import render
from test_e2e import Served


def chunk(kind, data):
 return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def png(w=600, h=800, shade=0):
 raw = b''.join(b'\x00' + bytes([shade]) * w for _ in range(h))
 return (client.PNG_SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 0, 0, 0, 0))
  + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


class Stub:
 """Scriptable image server."""
 def __init__(self):
  self.responses, self.requests = [], []
  stub = self
  class H(BaseHTTPRequestHandler):
   def log_message(self, *a): pass
   def do_GET(self):
    stub.requests.append((self.path, dict(self.headers)))
    status, body, headers = stub.responses.pop(0) if stub.responses else (500, b'', {})
    if status == 'drop':
     self.connection.close(); return
    self.send_response(status)
    for k, v in headers.items(): self.send_header(k, v)
    self.send_header('Content-Length', str(len(body)))
    self.end_headers(); self.wfile.write(body)
  self.httpd = HTTPServer(('127.0.0.1', 0), H)
  self.port = self.httpd.server_address[1]
  threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


class ClientTestBase(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
  self.root = Path(self.tmp.name)
  (self.root/'token').write_text('kfd_secret-token-value\n'); os.chmod(self.root/'token', 0o600)
  self.stub = Stub(); self.addCleanup(self.stub.httpd.shutdown)
  self.cfg = client.load_config(self.write_config())
  self.cache = client.Cache(self.cfg['cache_dir'])

 def write_config(self, **extra):
  cfg = {'server_url': f'http://127.0.0.1:{self.stub.port}', 'token_file': str(self.root/'token'),
   'cache_dir': str(self.root/'cache'), 'timeout': 2, **extra}
  (self.root/'config.json').write_text(json.dumps(cfg))
  return self.root/'config.json'


class ClientTest(ClientTestBase):
 def test_downloads_validates_caches_and_reports_change(self):
  seen = []
  self.stub.responses = [(200, png(), {'ETag': '"a"'})]
  self.assertEqual(client.check_once(self.cfg, self.cache, seen.append), 'updated')
  self.assertEqual(self.cache.image.read_bytes(), png())
  self.assertEqual(seen, [self.cache.image])
  self.assertEqual(self.stub.requests[0][1]['Authorization'], 'Bearer kfd_secret-token-value')
  self.assertNotIn('kfd_', self.stub.requests[0][0])

 def test_unchanged_uses_etag_and_does_not_redraw(self):
  seen = []
  self.stub.responses = [(200, png(), {'ETag': '"a"'}), (304, b'', {})]
  client.check_once(self.cfg, self.cache, seen.append)
  self.assertEqual(client.check_once(self.cfg, self.cache, seen.append), 'unchanged')
  self.assertEqual(self.stub.requests[1][1]['If-None-Match'], '"a"')
  self.assertEqual(len(seen), 1)

 def test_identical_pixels_with_new_etag_do_not_redraw(self):
  seen = []
  self.stub.responses = [(200, png(), {'ETag': '"a"'}), (200, png(), {'ETag': '"b"'})]
  client.check_once(self.cfg, self.cache, seen.append)
  self.assertEqual(client.check_once(self.cfg, self.cache, seen.append), 'unchanged')
  self.assertEqual(len(seen), 1)

 def test_new_image_replaces_cache_and_redraws(self):
  seen = []
  self.stub.responses = [(200, png(shade=0), {'ETag': '"a"'}), (200, png(shade=255), {'ETag': '"b"'})]
  client.check_once(self.cfg, self.cache, seen.append)
  self.assertEqual(client.check_once(self.cfg, self.cache, seen.append), 'updated')
  self.assertEqual(self.cache.image.read_bytes(), png(shade=255))
  self.assertEqual(len(seen), 2)

 def test_bad_downloads_keep_last_good_image(self):
  good = png()
  self.stub.responses = [(200, good, {'ETag': '"a"'})]
  client.check_once(self.cfg, self.cache)
  bad = [good[:-20], good[:100], b'not a png', png(w=601), good + b'x', b'', bytearray(good)]
  corrupt = bytearray(good); corrupt[60] ^= 0xff
  bad[-1] = bytes(corrupt)
  for body in bad:
   self.stub.responses = [(200, body, {'ETag': '"x"'})]
   with self.assertRaises(client.ClientError): client.check_once(self.cfg, self.cache)
   self.assertEqual(self.cache.image.read_bytes(), good)
  self.assertEqual(list(p.name for p in self.cache.dir.iterdir() if p.name.startswith('.tmp')), [])

 def test_oversized_download_refused(self):
  self.stub.responses = [(200, b'\x89PNG\r\n\x1a\n' + b'0' * (client.MAX_BYTES + 10), {})]
  with self.assertRaisesRegex(client.ClientError, 'too large'): client.check_once(self.cfg, self.cache)

 def test_auth_failures_and_server_errors(self):
  for status in (401, 403):
   self.stub.responses = [(status, b'{}', {})]
   with self.assertRaisesRegex(client.ClientError, 'token') as ctx: client.check_once(self.cfg, self.cache)
   self.assertNotIn('secret-token', str(ctx.exception))
  self.stub.responses = [(503, b'', {})]
  with self.assertRaisesRegex(client.ClientError, '503'): client.check_once(self.cfg, self.cache)

 def test_redirect_is_not_followed_and_token_not_forwarded(self):
  other = Stub(); self.addCleanup(other.httpd.shutdown)
  self.stub.responses = [(302, b'', {'Location': f'http://127.0.0.1:{other.port}/x'})]
  with self.assertRaises(client.ClientError): client.check_once(self.cfg, self.cache)
  self.assertEqual(other.requests, [])

 def test_connection_drop_and_refused_connection(self):
  self.stub.responses = [('drop', b'', {})]
  with self.assertRaisesRegex(client.ClientError, 'reach'): client.check_once(self.cfg, self.cache)
  self.stub.httpd.shutdown(); self.stub.httpd.server_close()
  with self.assertRaisesRegex(client.ClientError, 'reach'): client.check_once(self.cfg, self.cache)

 def test_corrupt_cache_with_304_triggers_refetch(self):
  self.stub.responses = [(200, png(), {'ETag': '"a"'})]
  client.check_once(self.cfg, self.cache)
  self.cache.image.write_bytes(b'garbage')
  self.stub.responses = [(200, png(), {'ETag': '"a"'})]
  self.assertEqual(client.check_once(self.cfg, self.cache), 'updated')
  self.assertEqual(self.cache.image.read_bytes(), png())
  self.assertNotIn('If-None-Match', self.stub.requests[-1][1])

 def test_config_and_token_safety(self):
  with self.assertRaises(client.ClientError): client.load_config(self.write_config(server_url='http://hub.example.test'))
  with self.assertRaises(client.ClientError): client.load_config(self.write_config(server_url='https://u:p@hub.example.test'))
  client.load_config(self.write_config(server_url='https://hub.example.test:8443'))
  os.chmod(self.root/'token', 0o644)
  with self.assertRaisesRegex(client.ClientError, 'chmod'): client.read_token(self.root/'token')

 def test_run_loop_backoff_recovery_and_interval(self):
  good = png()
  self.stub.responses = [(503, b'', {}), (503, b'', {}), (503, b'', {}), (200, good, {'ETag': '"a"'}), (304, b'', {})]
  sleeps, logs = [], []
  def stop(): return len(sleeps) >= 5
  client.run(self.cfg, stop=stop, sleep=sleeps.append, log=logs.append, rng=lambda: 0.5)
  self.assertEqual(sleeps, [30, 60, 120, 300, 300])
  self.assertEqual(self.cache.image.read_bytes(), good)
  self.assertTrue(all('secret' not in line for line in logs))

 def test_backoff_is_capped(self):
  self.stub.responses = []
  sleeps = []
  client.run(self.cfg, stop=lambda: len(sleeps) >= 12, sleep=sleeps.append, log=lambda m: None, rng=lambda: 0.5)
  self.assertEqual(max(sleeps), 1800)

 def test_validator_accepts_the_real_renderer_output(self):
  import json as j
  fixture = j.loads((Path(__file__).resolve().parent.parent/'app'/'seed.json').read_text())
  client.validate_png(render.png_bytes(fixture))


class ClientAgainstServerTest(Served):
 def test_phone_edit_reaches_cached_image_and_revocation_is_reported(self):
  self.serve()
  admin = self.sign_in()
  token = json.loads(self.request('POST', '/api/tokens', {'name': 'K', 'kind': 'display'}, admin)[1])['token']
  with tempfile.TemporaryDirectory() as tmp:
   t = Path(tmp)/'token'; t.write_text(token); os.chmod(t, 0o600)
   p = Path(tmp)/'c.json'
   p.write_text(json.dumps({'server_url': f'http://127.0.0.1:{self.port}', 'token_file': str(t), 'cache_dir': str(Path(tmp)/'cache')}))
   cfg = client.load_config(p); cache = client.Cache(cfg['cache_dir'])
   self.assertEqual(client.check_once(cfg, cache), 'updated')
   self.assertEqual(client.check_once(cfg, cache), 'unchanged')
   self.request('POST', '/api/shopping', {'title': 'Milk'}, admin)
   self.assertEqual(client.check_once(cfg, cache), 'updated')
   before = cache.image.read_bytes()
   tid = json.loads(self.request('GET', '/api/state', headers=admin)[1])['tokens'][0]['id']
   self.request('POST', f'/api/tokens/{tid}/revoke', {}, admin)
   with self.assertRaisesRegex(client.ClientError, 'token'): client.check_once(cfg, cache)
   self.assertEqual(cache.image.read_bytes(), before)
