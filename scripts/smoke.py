"""Stage A smoke check: clean temp install, fictional data, real server process, display client.

Proves: server starts and is healthy, a phone edit changes the authenticated image, the display client
caches it, unchanged polls are cheap, revocation is reported, and the server stops cleanly.
It does NOT touch a Kindle. Run: scripts/kfd smoke
"""
import http.client, json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PASSWORD = 'smoke-test-password'


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]


def call(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    c.request(method, path, json.dumps(body) if body is not None else None, {'Content-Type': 'application/json', **(headers or {})})
    r = c.getresponse(); data = r.read(); out = (r.status, dict(r.getheaders()), data); c.close()
    return out


def check(label, ok):
    print(('PASS ' if ok else 'FAIL ') + label, flush=True)
    if not ok: raise SystemExit(1)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = {**os.environ, 'KFD_DB': str(tmp/'family.sqlite3'), 'KFD_KEY_FILE': str(tmp/'family.key')}
        os.environ.update(env)
        from app import store, auth
        from display_client import client
        store.init_db(store.default_db_path())
        conn = store.connect(store.default_db_path())
        hh = store.create_household(conn, 'Smoke')
        store.create_user(conn, hh, 'sam', auth.hash_password(PASSWORD), 'admin')
        conn.close()
        port = free_port()
        server = subprocess.Popen([sys.executable, '-m', 'app.server', str(port)], cwd=ROOT, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(60):
                try:
                    if call(port, 'GET', '/healthz')[0] == 200: break
                except OSError: time.sleep(0.25)
            check('server healthy on loopback', call(port, 'GET', '/healthz')[0] == 200)
            status, headers, raw = call(port, 'POST', '/api/login', {'username': 'sam', 'password': PASSWORD})
            session = {'Cookie': headers['Set-Cookie'].split(';')[0], 'X-CSRF-Token': json.loads(raw)['csrf'],
                       'Origin': f'http://127.0.0.1:{port}'}
            token = json.loads(call(port, 'POST', '/api/tokens', {'name': 'Smoke display', 'kind': 'display'}, session)[2])['token']
            token_file = tmp/'display.token'; token_file.write_text(token); os.chmod(token_file, 0o600)
            cfg = client.load_config(_write(tmp/'client.json', {'server_url': f'http://127.0.0.1:{port}',
                                     'token_file': str(token_file), 'cache_dir': str(tmp/'cache')}))
            cache = client.Cache(cfg['cache_dir'])
            check('display client downloads the first image', client.check_once(cfg, cache) == 'updated')
            check('second poll is unchanged', client.check_once(cfg, cache) == 'unchanged')
            call(port, 'POST', '/api/shopping', {'title': 'Smoke-test milk'}, session)
            check('webpage edit reaches the cached display image', client.check_once(cfg, cache) == 'updated')
            check('display token cannot read the household state', call(port, 'GET', '/api/state', None,
                  {'Authorization': 'Bearer ' + token})[0] == 401)
            tid = json.loads(call(port, 'GET', '/api/state', None, session)[2])['tokens'][0]['id']
            call(port, 'POST', f'/api/tokens/{tid}/revoke', {}, session)
            try:
                client.check_once(cfg, cache); revoked = False
            except client.ClientError: revoked = True
            check('revoked token is refused and last image kept', revoked and cache.image.exists())
        finally:
            server.terminate()
            try: server.wait(10)
            except subprocess.TimeoutExpired: server.kill()
        check('server stopped', server.poll() is not None)
    print('Smoke check passed. This is host-side only: "ready for supervised Kindle connection", not "Kindle ready".')


def _write(path, obj):
    path.write_text(json.dumps(obj)); return path


if __name__ == '__main__':
    main()
