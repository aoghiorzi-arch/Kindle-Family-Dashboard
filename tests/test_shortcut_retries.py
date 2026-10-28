from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from app import store
from test_e2e import Served


class ShortcutRetriesTest(Served):
 def setUp(self):
  self.serve()
  conn = store.connect(self.db)
  try:
   uid = store.get_user(conn, 'sam')['id']
   self.token = store.create_api_token(conn, self.hh, uid, 'Test', ['shopping:add'])
   self.other = store.create_api_token(conn, self.hh, uid, 'Other', ['shopping:add'])
  finally: conn.close()

 def post(self, title='Milk', request_id='request-1', token=None):
  return self.request('POST', '/api/shortcut/shopping', {'title': title, 'request_id': request_id},
   {'Authorization': 'Bearer ' + (token or self.token)})

 def count(self):
  conn = store.connect(self.db)
  try: return len(store.list_shopping(conn, self.hh))
  finally: conn.close()

 def test_retry_conflict_and_deleted_item(self):
  self.assertEqual(self.post()[0], 201)
  status, body = self.post()
  self.assertEqual(status, 200)
  self.assertTrue(json.loads(body)['duplicate'])
  self.assertEqual(self.post(title='Bread')[0], 409)
  self.assertEqual(self.count(), 1)
  conn = store.connect(self.db)
  try: conn.execute('DELETE FROM shopping')
  finally: conn.close()
  self.assertEqual(self.post()[0], 200)
  self.assertEqual(self.count(), 0)

 def test_parallel_retry_and_token_scope(self):
  with ThreadPoolExecutor(max_workers=4) as pool:
   statuses = list(pool.map(lambda _: self.post()[0], range(4)))
  self.assertEqual(sorted(statuses), [200, 200, 200, 201])
  self.assertEqual(self.count(), 1)
  self.assertEqual(self.post(token=self.other)[0], 201)
  self.assertEqual(self.post(request_id='new-request')[0], 201)
  self.assertEqual(self.count(), 3)

 def test_invalid_ids_legacy_and_revocation(self):
  for key in ('', 'a'*129, 'a b', 42, ['bad']):
   self.assertEqual(self.post(request_id=key)[0], 400)
  self.assertEqual(self.count(), 0)
  self.assertEqual(self.post(request_id=None)[0], 201)
  self.assertEqual(self.post(request_id=None)[0], 201)
  self.assertEqual(self.post()[0], 201)
  conn = store.connect(self.db)
  try:
   row = store.api_token_for_use(conn, self.token)
   store.revoke_api_token(conn, self.hh, row['id'])
  finally: conn.close()
  self.assertEqual(self.post()[0], 401)

 def test_insert_failure_rolls_back_item_and_receipt(self):
  conn = store.connect(self.db)
  try:
   token = store.api_token_for_use(conn, self.token)
   conn.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON shortcut_requests BEGIN SELECT RAISE(ABORT, 'failure'); END")
   with self.assertRaises(sqlite3.IntegrityError): store.add_shortcut_shopping(conn, token, 'Milk', 'r')
   self.assertEqual(conn.execute('SELECT COUNT(*) FROM shopping').fetchone()[0], 0)
   conn.execute('DROP TRIGGER fail_receipt')
   self.assertTrue(store.add_shortcut_shopping(conn, token, 'Milk', 'r'))
  finally: conn.close()
