import http.client
import json
import threading
from app import server
from test_e2e import Served, PASSWORD

PUBLIC = 'https://hub.example.test:8443'
HOST = 'hub.example.test:8443'


class ProxyServed(Served):
 """The app behind a TLS proxy: the proxy forwards the public Host header over loopback."""
 def setUp(self):
  self.serve()
  self.httpd.shutdown(); self.httpd.server_close()
  self.httpd = server.make_server(self.db, port=0, public_origin=PUBLIC)
  self.port = self.httpd.server_address[1]
  threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

 def call(self, method, path, body=None, headers=None, host=HOST):
  c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
  c.putrequest(method, path, skip_host=True)
  c.putheader('Host', host)
  data = json.dumps(body).encode() if body is not None else None
  for k, v in {'Content-Type': 'application/json', **(headers or {})}.items(): c.putheader(k, v)
  c.putheader('Content-Length', str(len(data or b'')))
  c.endheaders(data)
  r = c.getresponse(); raw = r.read(); out = (r.status, dict(r.getheaders()), raw); c.close()
  return out

 def login(self):
  return self.call('POST', '/api/login', {'username': 'sam', 'password': PASSWORD}, {'Origin': PUBLIC})


class NetworkBoundaryTest(ProxyServed):
 def test_cookie_is_secure_and_hsts_sent_behind_proxy(self):
  status, headers, _ = self.login()
  self.assertEqual(status, 200)
  self.assertIn('Secure', headers['Set-Cookie'])
  self.assertIn('HttpOnly', headers['Set-Cookie'])
  self.assertIn('max-age', headers['Strict-Transport-Security'])

 def test_login_with_plaintext_or_foreign_origin_is_refused(self):
  for origin in (f'http://{HOST}', 'https://evil.example', f'http://127.0.0.1:{self.port}'):
   status, _, _ = self.call('POST', '/api/login', {'username': 'sam', 'password': PASSWORD}, {'Origin': origin})
   self.assertEqual(status, 403, origin)

 def test_unexpected_host_is_refused_on_every_route(self):
  for path in ('/', '/healthz', '/frame.png', '/api/display/frame.png'):
   self.assertEqual(self.call('GET', path, host='evil.example')[0], 421, path)
  self.assertEqual(self.call('POST', '/api/login', {}, host=f'127.0.0.1:{self.port}')[0], 421)

 def test_display_endpoint_works_with_public_host_and_token(self):
  _, headers, raw = self.login()
  cookie = headers['Set-Cookie'].split(';')[0]
  csrf = json.loads(raw)['csrf']
  status, _, raw = self.call('POST', '/api/tokens', {'name': 'K', 'kind': 'display'},
   {'Cookie': cookie, 'X-CSRF-Token': csrf, 'Origin': PUBLIC})
  token = json.loads(raw)['token']
  status, _, body = self.call('GET', '/api/display/frame.png', headers={'Authorization': 'Bearer ' + token})
  self.assertEqual((status, body[:4]), (200, b'\x89PNG'))

 def test_healthz_reveals_nothing(self):
  status, _, raw = self.call('GET', '/healthz')
  self.assertEqual((status, json.loads(raw)), (200, {'ok': True}))


class BindingTest(Served):
 def setUp(self): self.serve()

 def test_non_loopback_binding_and_bad_public_origins_are_refused(self):
  for host in ('0.0.0.0', '192.168.1.20', '::'):
   with self.assertRaises(ValueError): server.make_server(self.db, port=0, host=host)
  for origin in ('http://hub.example.test', 'https://u:p@hub.example.test', 'https://hub.example.test/path', 'hub.example.test'):
   with self.assertRaises(ValueError): server.make_server(self.db, port=0, public_origin=origin)

 def test_loopback_mode_rejects_foreign_host_header(self):
  c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
  c.putrequest('GET', '/healthz', skip_host=True); c.putheader('Host', 'evil.example'); c.endheaders()
  self.assertEqual(c.getresponse().status, 421); c.close()
  self.assertEqual(self.request('GET', '/healthz')[0], 200)

 def test_cookie_has_no_secure_flag_on_loopback_http(self):
  c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
  c.request('POST', '/api/login', json.dumps({'username': 'sam', 'password': PASSWORD}), {'Content-Type': 'application/json'})
  r = c.getresponse(); r.read()
  self.assertNotIn('Secure', r.getheader('Set-Cookie'))
