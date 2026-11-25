"""Real disposable SQLite tests for password, quotas and guest leases."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import time
import unittest
from site_store import Store, SiteError, password_hash, check_password
import site_guests as guests


class AccountStorageAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='workbench-account-audit-')
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        guests.initialize(self.store)
        with self.store.db(True) as db:
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',
                       ('member', 'member', '!synthetic', 'member', 1, 1, 0, time.time()))

    def test_password_hash_salt_and_validation(self):
        first = password_hash('temporary-password-123')
        second = password_hash('temporary-password-123')
        self.assertNotEqual(first, second)
        self.assertTrue(check_password('temporary-password-123', first))
        self.assertFalse(check_password('wrong-password-123', first))
        self.assertFalse(check_password('temporary-password-123', 'invalid'))
        with self.assertRaises(SiteError):
            password_hash('short')

    def test_daily_quota_reservation_is_atomic(self):
        def reserve(_):
            try:
                return self.store.reserve('member', 'offline-model', 10)
            except SiteError as error:
                return error.status
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(reserve, range(6)))
        self.assertEqual(sum(isinstance(r, str) for r in results), 1)
        self.assertEqual(results.count(429), 5)
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT calls FROM usage').fetchone()[0], 1)

    def test_disabled_account_denied_before_charge(self):
        with self.store.db(True) as db:
            db.execute("UPDATE users SET active=0 WHERE id='member'")
        with self.assertRaises(SiteError) as caught:
            self.store.reserve('member', 'offline-model', 10)
        self.assertEqual(caught.exception.status, 403)
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM calls').fetchone()[0], 0)

    def test_guest_lease_conflict_and_token_checked_release(self):
        secret = guests.create(self.store, '127.0.0.1')
        ident = self.store.session(secret)['id']
        lease = guests.acquire(self.store, ident)
        with self.assertRaises(SiteError) as caught:
            guests.acquire(self.store, ident)
        self.assertEqual(caught.exception.status, 409)
        guests.release(self.store, ident, 'wrong-token')
        with self.assertRaises(SiteError):
            guests.acquire(self.store, ident)
        guests.release(self.store, ident, lease)
        self.assertNotEqual(guests.acquire(self.store, ident), lease)

    def test_guest_upload_limit_failure_preserves_counters(self):
        secret = guests.create(self.store, '127.0.0.1')
        ident = self.store.session(secret)['id']
        guests.uploads(self.store, ident, 5, 100)
        with self.assertRaises(SiteError) as caught:
            guests.uploads(self.store, ident, 1, 100)
        self.assertEqual(caught.exception.status, 413)
        with self.store.db() as db:
            row = db.execute('SELECT files,bytes FROM guests WHERE user_id=?', (ident,)).fetchone()
            self.assertEqual(tuple(row), (5, 100))

    def test_finish_is_idempotent(self):
        ident = self.store.reserve('member', 'offline-model', 10)
        self.store.finish(ident, 5)
        self.store.finish(ident, 99)
        with self.store.db() as db:
            self.assertEqual(tuple(db.execute('SELECT calls,tokens FROM usage').fetchone()), (1, 5))

    def test_name_normalization_never_overwrites_concurrent_update(self):
        import json
        from unittest.mock import patch
        import interview_names
        home = Path(self.temp.name)
        projects, research, files = home/'projects', home/'research', home/'files'
        research.mkdir(); files.mkdir()
        source = projects/'sample'; source.mkdir(parents=True)
        meta = source/'project.json'
        meta.write_text(json.dumps({'id':'sample','name':'old','extra':0}), encoding='utf-8')
        (source/'导入访谈稿.txt').write_text('synthetic', encoding='utf-8')
        def concurrent_save(records):
            current = json.loads(meta.read_text(encoding='utf-8'))
            current['extra'] = 99
            meta.write_text(json.dumps(current), encoding='utf-8')
            return {'w:sample':'renamed'}
        with patch.object(interview_names, 'assignments', side_effect=concurrent_save):
            with self.assertRaises(SiteError) as caught:
                interview_names.normalize_names(projects,research,files,home/'backup',lambda *args:None)
        self.assertEqual(caught.exception.status,409)
        self.assertEqual(json.loads(meta.read_text(encoding='utf-8'))['extra'],99)


if __name__ == '__main__':
    unittest.main()
