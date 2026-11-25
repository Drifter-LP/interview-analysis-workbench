"""Isolated gateway checks: no lifespan, subprocesses, real accounts or network."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi.testclient import TestClient


class GatewayAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('_gateway_audit_isolated', root / 'site_app.py')
        cls.gateway = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.gateway
        with patch.dict(os.environ, {'SITE_HOME': cls.temp.name, 'SITE_ALLOW_HTTP': '1',
                                     'SITE_ORIGIN': 'http://127.0.0.1:8765'}):
            spec.loader.exec_module(cls.gateway)

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop('_gateway_audit_isolated', None)
        cls.temp.cleanup()

    def setUp(self):
        self.g = self.gateway
        # Not entering TestClient deliberately avoids startup cleanup/janitor.
        self.client = TestClient(self.g.app, base_url=self.g.ORIGIN)
        self.addCleanup(self.client.close)

    def test_anonymous_and_expired_logout_repeat_without_body(self):
        for cookie in ('', 'expired-session'):
            self.client.cookies.set(self.g.COOKIE, cookie)
            for _ in range(2):
                response = self.client.post('/auth/logout', headers={'Origin': self.g.ORIGIN})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'ok': True})
                cookies = response.headers.get_list('set-cookie')
                self.assertTrue(any(self.g.COOKIE in c and 'Max-Age=0' in c for c in cookies))
                self.assertTrue(any(self.g.PENDING in c and 'Max-Age=0' in c for c in cookies))

    def test_logout_rejects_missing_or_foreign_origin(self):
        for headers in ({}, {'Origin': 'https://attacker.invalid'}):
            self.assertEqual(self.client.post('/auth/logout', headers=headers).status_code, 403)

    def test_authenticated_logout_requires_csrf(self):
        user = {'id': 'test-user', 'role': 'member', 'csrf': 'csrf-value'}
        with patch.object(self.g.store, 'session', return_value=user):
            self.assertEqual(self.client.post('/auth/logout', headers={'Origin': self.g.ORIGIN}).status_code, 403)
            self.assertEqual(self.client.post('/auth/logout', headers={
                'Origin': self.g.ORIGIN, 'X-CSRF-Token': user['csrf']}).status_code, 200)

    def test_health_uses_readonly_sqlite_and_never_starts_worker(self):
        connect = self.g.sqlite3.connect
        with patch.object(self.g.sqlite3, 'connect', wraps=connect) as probe, \
                patch.object(self.g, 'worker', side_effect=AssertionError('must not start')):
            response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertIn('?mode=ro', probe.call_args.args[0])
        self.assertTrue(probe.call_args.kwargs['uri'])

    def test_health_missing_database_is_503_without_creation(self):
        missing = Path(self.temp.name) / 'missing.sqlite3'
        with patch.object(self.g.store, 'path', missing):
            response = self.client.get('/health', headers={'Cookie': self.g.COOKIE + '=expired'})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['checks']['accounts'])
        self.assertFalse(missing.exists())

    def test_health_disk_and_known_dead_worker_fail(self):
        for free, processes, check in ((0, {}, 'disk'),
                (10**12, {'test': (Mock(poll=Mock(return_value=1)), 1, None, '')}, 'workers')):
            with patch.object(self.g.shutil, 'disk_usage', return_value=Mock(free=free)), \
                    patch.object(self.g, 'workers', processes):
                response = self.client.get('/health')
            self.assertEqual(response.status_code, 503)
            self.assertFalse(response.json()['checks'][check])

    def test_request_id_validation_and_security_response(self):
        for supplied in ('audit-request_123', 'bad value', 'x' * 100, 'bad\tvalue'):
            response = self.client.get('/auth/me', headers={'X-Request-ID': supplied})
            self.assertEqual(response.status_code, 401)
            ident = response.headers['x-request-id']
            self.assertRegex(ident, r'^[A-Za-z0-9_-]{8,64}$')
            self.assertEqual(ident == supplied, supplied == 'audit-request_123')

    def test_proxy_forwards_correlation_and_logs_upstream_error(self):
        captured = []
        async def respond(request):
            captured.append(request.headers['x-request-id'])
            return httpx.Response(503, content=b'busy')
        upstream = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        user = {'id': 'test-user', 'role': 'member', 'csrf': 'csrf'}
        with patch.object(self.g.store, 'session', return_value=user), \
                patch.object(self.g.store, 'data_root', return_value=(Path(self.temp.name), True)), \
                patch.object(self.g, 'worker', new=AsyncMock(return_value=1234)), \
                patch.object(self.g, 'workers', {'test-user': (None, 1234, None, 'secret')}), \
                patch.object(self.g.httpx, 'AsyncClient', return_value=upstream), \
                self.assertLogs('workbench.backend', level='INFO') as logs:
            response = self.client.get('/api/status', headers={'X-Request-ID': 'proxy-audit_123'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['x-request-id'], 'proxy-audit_123')
        self.assertEqual(captured, ['proxy-audit_123'])
        self.assertTrue(any('gateway_upstream_error' in line for line in logs.output))


    def test_guest_transfer_copy_failure_rolls_back_files_and_state(self):
        import asyncio
        import time
        from types import SimpleNamespace
        g = self.g
        with tempfile.TemporaryDirectory(prefix='guest-transfer-audit-') as temporary:
            home = Path(temporary)
            store = g.Store(home)
            g.guests.initialize(store)
            with store.db(True) as db:
                db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',
                           ('target', 'target', '!synthetic', 'member', 1, 80, 0, time.time()))
            guest_secret = g.guests.create(store, '127.0.0.1')
            source = store.session(guest_secret)
            source_root, _ = store.data_root(source['id'])
            project = source_root / 'projects' / 'synthetic'
            project.mkdir(parents=True)
            (project / 'sample.txt').write_text('synthetic', encoding='utf-8')
            target_root, _ = store.data_root('target')
            target_root.mkdir(parents=True)
            request = SimpleNamespace(state=SimpleNamespace(user={'id': 'target', 'role': 'member'}),
                                      cookies={g.PENDING: guest_secret})
            def fail_copy(src, dest):
                dest.mkdir(parents=True)
                (dest / 'partial.txt').write_text('partial', encoding='utf-8')
                raise OSError('simulated copy failure')
            with patch.object(g, 'store', store), patch.object(g, 'HOME', home), \
                 patch.object(g, 'worker_lock', asyncio.Lock()), \
                 patch.object(g, 'stop_worker', AsyncMock()), \
                 patch.object(g.shutil, 'copytree', side_effect=fail_copy):
                with self.assertRaises(OSError):
                    asyncio.run(g.guest_transfer(request))
            self.assertTrue((project / 'sample.txt').is_file())
            self.assertFalse((target_root / 'projects' / 'synthetic').exists())
            with store.db() as db:
                self.assertEqual(db.execute('SELECT state FROM guests WHERE user_id=?',
                                            (source['id'],)).fetchone()[0], 'active')
                self.assertEqual(db.execute('SELECT count(*) FROM guest_transfers').fetchone()[0], 0)
            self.assertIsNotNone(store.session(guest_secret))


if __name__ == '__main__':
    unittest.main()
