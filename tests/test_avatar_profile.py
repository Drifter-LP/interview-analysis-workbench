import sys,tempfile,unittest,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from site_store import Store,SiteError
class ProfileTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=Store(Path(self.tmp.name)/'accounts')
  self.root=Path(self.tmp.name)/'legacy';self.root.mkdir()
  self.store.attach_existing('qa_owner',self.root)
  self.secret=self.store.redeem(self.store.invite('qa_owner',bootstrap=True)['token'],'temporary-qa-password-123')
  self.user=self.store.session(self.secret)
 def test_admin_rename_keeps_data_and_session(self):
  before=self.store.data_root(self.user['id'])
  self.store.update_profile(self.user['id'],new_username='renamed_owner',new_avatar='preset:ocean')
  self.assertEqual(self.store.data_root(self.user['id']),before)
  self.assertEqual(self.store.session(self.secret)['avatar'],'preset:ocean')
  self.assertEqual(self.store.session(self.secret)['username'],'renamed_owner')
 def test_invalid_avatar_rolls_back_name(self):
  with self.assertRaises(SiteError):self.store.update_profile(self.user['id'],new_username='changed',new_avatar='javascript:bad')
  self.assertEqual(self.store.session(self.secret)['username'],'qa_owner')
 def test_disabled_denied(self):
  with self.store.db(True) as db:db.execute('UPDATE users SET active=0 WHERE id=?',(self.user['id'],))
  with self.assertRaises(SiteError):self.store.update_profile(self.user['id'],new_avatar='preset:rose')
if __name__=='__main__':unittest.main()
