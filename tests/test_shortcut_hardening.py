from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4
from app import server, store
from test_e2e import Served


def write(conn, token, title, request_id=None):
 row = store.api_token_for_use(conn, token)
 return not store.add_shortcut_shopping(conn, row, title, request_id)


class ShortcutRetriesTest(unittest.TestCase):
 def setUp(self):
  self.tmp = tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.db = Path(self.tmp.name)/'family.sqlite3'
  store.init_db(self.db)
  self.conn = store.connect(self.db)
  self.addCleanup(self.conn.close)
  self.hh = store.create_household(self.conn, 'Family')
  self.other = store.create_household(self.conn, 'Other')
  self.user = store.create_user(self.conn, self.hh, 'sam', 'fixture', 'admin')
  self.token = store.create_api_token(self.conn, self.hh, self.user, 'Phone', ['shopping:add'])
  self.key = str(uuid4())

 def add(self, title='Milk', key=None, token=None):
  return write(self.conn, token or self.token, title, key or self.key)

 def test_repeat_and_restart_return_original_result_without_duplicate(self):
  self.assertFalse(self.add(' Milk '))
  self.assertTrue(self.add())
  self.conn.close()
  self.conn = store.connect(self.db)
  self.addCleanup(self.conn.close)
  self.assertTrue(self.add())
  self.assertEqual([r['title'] for r in store.list_shopping(self.conn, self.hh)], ['Milk'])
  self.assertEqual(self.conn.execute('SELECT count(*) FROM shortcut_requests').fetchone()[0], 1)

 def test_conflicting_title_does_not_change_original_item_or_receipt(self):
  self.add()
  with self.assertRaises(store.RequestConflict): self.add('Bread')
  self.assertEqual([r['title'] for r in store.list_shopping(self.conn, self.hh)], ['Milk'])
  self.assertTrue(self.add())

 def test_intentional_repeated_title_with_new_id_adds_another(self):
  self.add()
  self.assertFalse(self.add(key=str(uuid4())))
  self.assertEqual(len(store.list_shopping(self.conn, self.hh)), 2)

 def test_deleted_item_is_not_resurrected_by_retry(self):
  self.add()
  item = store.list_shopping(self.conn, self.hh)[0]['id']
  store.delete_shopping(self.conn, self.hh, item)
  self.assertTrue(self.add())
  self.assertEqual(store.list_shopping(self.conn, self.hh), [])

 def test_same_uuid_is_isolated_between_tokens_and_households(self):
  second = store.create_api_token(self.conn, self.hh, self.user, 'Second', ['shopping:add'])
  other = store.create_api_token(self.conn, self.other, None, 'Other', ['shopping:add'])
  for token in [self.token, second, other]: self.assertFalse(self.add(token=token))
  self.assertEqual(len(store.list_shopping(self.conn, self.hh)), 2)
  self.assertEqual(len(store.list_shopping(self.conn, self.other)), 1)

 def test_receipt_and_item_roll_back_together(self):
  with patch.object(store, 'add_shopping', side_effect=OSError('simulated write failure')):
   with self.assertRaises(OSError): self.add()
  self.assertEqual(self.conn.execute('SELECT count(*) FROM shortcut_requests').fetchone()[0], 0)
  self.assertEqual(store.list_shopping(self.conn, self.hh), [])
  self.assertFalse(self.add())

 def test_revocation_and_scope_are_rechecked_before_replay(self):
  self.add()
  token_id = store.list_api_tokens(self.conn, self.hh)[0]['id']
  store.revoke_api_token(self.conn, self.hh, token_id)
  for title in ['Milk', 'Bread']:
   with self.assertRaises(store.ShortcutError) as caught: self.add(title)
   self.assertEqual(caught.exception.status, 401)
  restricted = store.create_api_token(self.conn, self.hh, self.user, 'No shopping', ['events:add'])
  with self.assertRaises(store.ShortcutError) as caught: self.add(token=restricted)
  self.assertEqual(caught.exception.status, 403)
  self.assertEqual(len(store.list_shopping(self.conn, self.hh)), 1)

 def test_unkeyed_requests_remain_compatible_without_duplicate_protection(self):
  for i in range(2): self.assertFalse(write(self.conn, self.token, 'Milk'))
  self.assertEqual(len(store.list_shopping(self.conn, self.hh)), 2)
  self.assertEqual(self.conn.execute('SELECT count(*) FROM shortcut_requests').fetchone()[0], 0)

 def test_invalid_ids_or_titles_never_consume_a_receipt(self):
  for key in ['', 'not an id', 12, 'a'*129, '"'+self.key, self.key+'\n']:
   with self.subTest(key=key):
    with self.assertRaises(ValueError): write(self.conn, self.token, 'Milk', key)
  for title in ['', None, 123, 'x'*101]:
   with self.assertRaises(ValueError): self.add(title)
  self.assertEqual(self.conn.execute('SELECT count(*) FROM shortcut_requests').fetchone()[0], 0)
  self.assertEqual(store.list_shopping(self.conn, self.hh), [])




 def test_simultaneous_retries_create_one_item_across_connections(self):
  ready = threading.Barrier(8)
  def retry(i):
   conn = store.connect(self.db)
   try:
    ready.wait(timeout=5)
    return write(conn, self.token, 'Milk', self.key)
   finally: conn.close()
  with ThreadPoolExecutor(max_workers=8) as pool: results = list(pool.map(retry, range(8)))
  self.assertEqual(results.count(False), 1)
  self.assertEqual(results.count(True), 7)
  self.assertEqual(len(store.list_shopping(self.conn, self.hh)), 1)

 def test_concurrent_distinct_ids_preserve_every_intentional_add(self):
  ready = threading.Barrier(8)
  def add(i):
   conn = store.connect(self.db)
   try:
    ready.wait(timeout=5)
    return write(conn, self.token, f'Item {i}', str(uuid4()))
   finally: conn.close()
  with ThreadPoolExecutor(max_workers=8) as pool: results = list(pool.map(add, range(8)))
  self.assertEqual(results, [False]*8)
  self.assertEqual(len(store.list_shopping(self.conn, self.hh)), 8)

 def test_revoke_transaction_wins_against_a_waiting_request(self):
  token_id = store.list_api_tokens(self.conn, self.hh)[0]['id']
  self.conn.execute('BEGIN IMMEDIATE')
  store.revoke_api_token(self.conn, self.hh, token_id)
  started = threading.Event()
  def waiting():
   conn = store.connect(self.db)
   try:
    started.set()
    try: write(conn, self.token, 'Milk', self.key)
    except store.ShortcutError as exc: return exc.status
   finally: conn.close()
  with ThreadPoolExecutor(max_workers=1) as pool:
   result = pool.submit(waiting)
   try: self.assertTrue(started.wait(5))
   finally: self.conn.execute('COMMIT')
   self.assertEqual(result.result(timeout=5), 401)
  self.assertEqual(store.list_shopping(self.conn, self.hh), [])


 def test_bounded_capacity_allows_old_replays_and_a_new_token_scope(self):
  with patch.object(store, 'SHORTCUT_RECEIPT_LIMIT', 2):
   self.add()
   self.add(key=str(uuid4()))
   self.assertTrue(self.add())
   with self.assertRaises(store.ShortcutError) as caught: self.add(key=str(uuid4()))
   self.assertEqual(caught.exception.status, 429)
   token_id = store.list_api_tokens(self.conn, self.hh)[0]['id']
   store.revoke_api_token(self.conn, self.hh, token_id)
   replacement = store.create_api_token(self.conn, self.hh, self.user, 'Replacement', ['shopping:add'])
   self.assertFalse(self.add(token=replacement))

 def test_stale_authorized_row_is_rejected_after_revocation_or_scope_change(self):
  row = store.api_token_for_use(self.conn, self.token)
  self.conn.execute("UPDATE api_tokens SET scopes='events:add' WHERE id=?", (row['id'],))
  with self.assertRaises(store.ShortcutError) as caught: store.add_shortcut_shopping(self.conn, row, 'Milk', self.key)
  self.assertEqual(caught.exception.status, 403)
  store.revoke_api_token(self.conn, self.hh, row['id'])
  with self.assertRaises(store.ShortcutError) as caught: store.add_shortcut_shopping(self.conn, row, 'Milk', self.key)
  self.assertEqual(caught.exception.status, 401)
  self.assertEqual(store.list_shopping(self.conn, self.hh), [])


class ShortcutHTTPTest(Served):
 def setUp(self):
  self.serve()
  headers = self.sign_in()
  status, body = self.request('POST', '/api/tokens', {'name':'Phone'}, headers)
  self.assertEqual(status, 201)
  self.token = json.loads(body)['token']
  self.key = str(uuid4())

 def shortcut(self, title='Milk', key=None):
  conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
  body = json.dumps({'title':title, 'request_id':key or self.key}).encode()
  conn.putrequest('POST', '/api/shortcut/shopping')
  conn.putheader('Authorization', 'Bearer '+self.token)
  conn.putheader('Content-Type', 'application/json')
  conn.putheader('Content-Length', str(len(body)))
  conn.endheaders(body)
  result = conn.getresponse()
  out = result.status, dict(result.getheaders()), result.read()
  conn.close()
  return out

 def test_http_replays_same_status_and_body_and_conflicts_on_new_title(self):
  first, second = self.shortcut(), self.shortcut()
  self.assertEqual(first[0], 201)
  self.assertEqual(second[0], 200)
  self.assertFalse(json.loads(first[2])['duplicate'])
  self.assertTrue(json.loads(second[2])['duplicate'])
  self.assertEqual(self.shortcut('Bread')[0], 409)
  conn = store.connect(self.db)
  try: self.assertEqual(len(store.list_shopping(conn, self.hh)), 1)
  finally: conn.close()

 def test_invalid_request_ids_are_rejected_without_changes(self):
  self.assertEqual(self.shortcut(key='not an id')[0], 400)
  self.assertEqual(self.shortcut(key=['bad'])[0], 400)
  conn = store.connect(self.db)
  try: self.assertEqual(store.list_shopping(conn, self.hh), [])
  finally: conn.close()

 def test_retry_receipt_survives_http_server_restart(self):
  self.assertEqual(self.shortcut()[0], 201)
  self.httpd.shutdown()
  self.httpd.server_close()
  self.httpd = server.make_server(self.db, port=0)
  self.port = self.httpd.server_address[1]
  threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
  replay = self.shortcut()
  self.assertEqual(replay[0], 200)
  self.assertTrue(json.loads(replay[2])['duplicate'])

 def test_busy_database_returns_retryable_error_with_no_partial_insert(self):
  with patch.object(store, 'add_shortcut_shopping', side_effect=store.sqlite3.OperationalError('private failure')):
   status, _, body = self.shortcut()
  self.assertEqual(status, 503)
  self.assertNotIn(b'private failure', body)
  self.assertEqual(self.shortcut()[0], 201)
