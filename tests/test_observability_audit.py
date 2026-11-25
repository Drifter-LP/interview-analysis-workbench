"""Request context survives batch threads, worker rejection and response streams."""
import asyncio
import json
import unittest
from unittest.mock import patch
from backend_observability import RequestTrackingMiddleware, request_id, setup_request_tracking
from interview_facts import ordered_parallel
from fastapi import FastAPI
from fastapi.testclient import TestClient
from site_boundary import protect_worker


class ObservabilityAuditTests(unittest.TestCase):
    def test_parallel_calls_keep_request_id(self):
        token = request_id.set('batch-request-123')
        try:
            self.assertEqual(ordered_parallel(lambda _: request_id.get(), range(4)),
                             ['batch-request-123'] * 4)
        finally:
            request_id.reset(token)

    def exercise_stream(self, fail=False):
        messages = []
        async def application(scope, receive, send):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'first', 'more_body': True})
            self.assertEqual(request_id.get(), 'stream-request-123')
            if fail:
                raise RuntimeError('synthetic stream failure')
            await send({'type': 'http.response.body', 'body': b'last', 'more_body': False})
        async def send(message):
            messages.append(message)
        async def receive():
            return {'type': 'http.request', 'body': b''}
        scope = {'type': 'http', 'method': 'GET', 'headers': [(b'x-request-id', b'stream-request-123')]}
        with self.assertLogs('workbench.backend', level='INFO') as capture:
            middleware = RequestTrackingMiddleware(application, 'test')
            if fail:
                with self.assertRaises(RuntimeError):
                    asyncio.run(middleware(scope, receive, send))
            else:
                asyncio.run(middleware(scope, receive, send))
        events = [json.loads(line[line.index('{'):]) for line in capture.output]
        self.assertEqual(request_id.get(), '')
        self.assertIn((b'x-request-id', b'stream-request-123'), messages[0]['headers'])
        return events

    def test_success_logged_after_stream_completed(self):
        events = self.exercise_stream()
        self.assertEqual(events[-1]['event'], 'request_finished')
        self.assertTrue(events[-1]['body_complete'])

    def test_stream_failure_never_logged_as_success(self):
        events = self.exercise_stream(fail=True)
        self.assertEqual(events[-1]['event'], 'request_failed')
        self.assertEqual(events[-1]['request_id'], 'stream-request-123')
        self.assertNotIn('request_finished', [event['event'] for event in events])

    def test_boundary_rejection_has_request_id(self):
        app = FastAPI()
        with patch.dict('os.environ', {'SITE_WORKER_SECRET': 'synthetic-private-worker',
                                      'WORKBENCH_TEXT_ONLY': '1'}), \
             patch('site_boundary.Path.exists', return_value=False):
            protect_worker(app)
        setup_request_tracking(app, 'worker')
        with TestClient(app) as client:
            response = client.get('/api/projects', headers={'X-Request-ID': 'boundary-request-123'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers['X-Request-ID'], 'boundary-request-123')


if __name__ == '__main__':
    unittest.main()
