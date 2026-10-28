import json
from app import store
from test_e2e import Served


class ScheduleHTTPTest(Served):
 def setUp(self):
  self.serve()
  self.sam = self.sign_in()
  conn = store.connect(self.db)
  self.fid = store.add_feed(conn,self.hh,'Family','https://example.test/private')
  other = store.get_user(conn,'mallory')['household_id']
  self.other_fid = store.add_feed(conn,other,'Other','https://example.test/other')
  store.create_user(conn,self.hh,'jo',store.get_user(conn,'sam')['password_hash'])
  conn.close()

 def test_only_household_admin_can_enable_and_pause_own_feed(self):
  route = f'/api/feeds/{self.fid}/schedule'
  self.assertEqual(self.request('POST',route,{'enabled':True})[0],401)
  jo = self.sign_in('jo')
  self.assertEqual(self.request('POST',route,{'enabled':True},jo)[0],403)
  self.assertEqual(self.request('POST',route,{'enabled':True},{**self.sam,'X-CSRF-Token':'bad'})[0],403)
  self.assertEqual(self.request('POST',f'/api/feeds/{self.other_fid}/schedule',{'enabled':True},self.sam)[0],404)
  self.assertEqual(self.request('POST',route,{'enabled':'yes'},self.sam)[0],400)
  for enabled in (True,False):
   self.assertEqual(self.request('POST',route,{'enabled':enabled},self.sam)[0],200)
   state=json.loads(self.request('GET','/api/state',headers=self.sam)[1])
   self.assertEqual(state['feeds'][0]['refresh_enabled'],enabled)
   self.assertNotIn('/private',json.dumps(state))
