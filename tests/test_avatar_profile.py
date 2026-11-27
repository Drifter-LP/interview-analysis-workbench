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
 def test_display_name_migrates_and_keeps_identity(self):
  before=self.store.data_root(self.user['id'])
  self.store.update_profile(self.user['id'],new_avatar='preset:ocean')
  with self.store.db(True) as db:db.execute('ALTER TABLE user_profiles DROP COLUMN display_name')
  store=Store(self.store.home)
  self.assertEqual(store.session(self.secret)['display_name'],'')
  store.update_profile(self.user['id'],new_display_name=' 奶龙大龙 ')
  logged_in=store.session(store.login('qa_owner','temporary-qa-password-123','127.0.0.1'))
  self.assertEqual(logged_in['display_name'],'奶龙大龙')
  self.assertEqual(logged_in['username'],'qa_owner')
  self.assertEqual(logged_in['avatar'],'preset:ocean')
  self.assertEqual(store.data_root(logged_in['id']),before)
  for bad in ('', '名'*33, '甲\n乙', '甲\u202e乙', 1):
   with self.assertRaises(SiteError):store.update_profile(self.user['id'],new_display_name=bad)
  self.assertEqual(store.session(self.secret)['display_name'],'奶龙大龙')
 def test_disabled_denied(self):
  with self.store.db(True) as db:db.execute('UPDATE users SET active=0 WHERE id=?',(self.user['id'],))
  with self.assertRaises(SiteError):self.store.update_profile(self.user['id'],new_avatar='preset:rose')
 def test_invite_and_register_beyond_eight(self):
  with self.store.db(True) as db:
   for n in range(9):
    db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',(f'fake{n}',f'fake{n}','!synthetic','user',1,80,0,time.time()+n))
  token=self.store.invite('ninth_plus',actor=self.user['id'])['token']
  session=self.store.redeem(token,'temporary-member-password-123')
  self.assertEqual(self.store.session(session)['username'],'ninth_plus')
  self.assertEqual(len(self.store.users()),11)
 def test_inactive_last_and_reactivation_restores_group(self):
  with self.store.db(True) as db:
   for n,active in enumerate((0,1,0,1)):
    db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',(f'fake{n}',f'fake{n}','!synthetic','user',active,80,0,time.time()+n))
  self.assertEqual([u['active'] for u in self.store.users()],[1,1,1,0,0])
  self.store.update_user(self.user['id'],'fake0',True,80)
  self.assertEqual([u['active'] for u in self.store.users()],[1,1,1,1,0])
 def test_invite_still_requires_admin(self):
  with self.assertRaises(SiteError):self.store.invite('not_allowed',actor='missing')
if __name__=='__main__':unittest.main()
