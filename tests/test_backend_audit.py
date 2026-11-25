"""Offline backend regressions. Discovery launches a disposable subprocess.

Run: python tests/test_backend_audit.py
No application imports occur in the parent, including during unittest discovery.
"""
import io
import json
import os
import socket
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from unittest.mock import Mock, patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
ISOLATED = __name__ == '__main__' and '--isolated' in sys.argv


class BackendAuditSubprocess(unittest.TestCase):
    def test_isolated_backend_audit(self):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), '--isolated'],
            cwd=REPO, capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=120,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout + result.stderr)


def isolated_main():
    # Keep every fixture, model cache and account root out of the shared repo.
    with tempfile.TemporaryDirectory(prefix='backend-audit-', ignore_cleanup_errors=True) as root, ExitStack() as stack:
        root = Path(root)
        stack.enter_context(patch.dict(os.environ, {
            'WORKBENCH_DATA_DIR': str(root), 'SITE_DATA_DIR': str(root / 'accounts'),
            'SITE_USER_ID': '', 'SITE_WORKER_SECRET': '', 'WORKBENCH_TEXT_ONLY': '',
            'DEEPSEEK_API_KEY': '', 'OPENAI_API_KEY': '',
            'MODELSCOPE_CACHE': str(root / 'models'), 'HF_HOME': str(root / 'hf'),
            'TEMP': str(root / 'temp'), 'TMP': str(root / 'temp'),
        }))
        for name in ('projects', 'research_projects', 'research_project_files', 'temp', 'outputs'):
            (root / name).mkdir()
        sys.path.insert(0, str(REPO))
        # Do not even stat the real .site-data/enabled.json during import.
        exists = Path.exists
        boundary_checks = []

        def isolated_exists(path):
            if '.site-data' in path.parts:
                boundary_checks.append(str(path))
                return False
            return exists(path)

        stack.enter_context(patch.object(Path, 'exists', isolated_exists))
        # Windows asyncio builds an internal loopback socketpair. Permit only
        # that stdlib operation, not arbitrary loopback or external connections.
        socket_state = threading.local()
        original_pair, original_connect = socket.socketpair, socket.socket.connect

        def internal_pair(*args, **kwargs):
            socket_state.internal = True
            try:
                return original_pair(*args, **kwargs)
            finally:
                socket_state.internal = False

        def offline_connect(sock, address):
            if not getattr(socket_state, 'internal', False):
                raise AssertionError('Network forbidden')
            return original_connect(sock, address)

        stack.enter_context(patch('socket.socketpair', internal_pair))
        stack.enter_context(patch('socket.socket.connect', offline_connect))
        stack.enter_context(patch('socket.create_connection', side_effect=AssertionError('Network forbidden')))
        fake_openai = types.ModuleType('openai')
        fake_openai.OpenAI = Mock(side_effect=AssertionError('Unconfigured model call'))
        stack.enter_context(patch.dict(sys.modules, {'openai': fake_openai}))
        import web_app as web
        import backend_storage as storage
        import backend_observability as tracking
        from site_store import SiteError
        from fastapi import HTTPException, UploadFile
        from fastapi.testclient import TestClient
        stack.enter_context(patch.object(web, 'read_deepseek_key', return_value='offline-test-only'))

        class Audit(unittest.TestCase):
            def setUp(self):
                self.directory = Path(tempfile.mkdtemp(dir=root, prefix='case-'))
                self.patches = ExitStack()
                self.addCleanup(self.patches.close)
                for attr, name in (('PROJECTS_DIR', 'projects'), ('RESEARCH_PROJECTS_DIR', 'research_projects'), ('RESEARCH_FILES_DIR', 'research_project_files')):
                    path = self.directory / name
                    path.mkdir()
                    self.patches.enter_context(patch.object(web, attr, path))
                web.project_dir('sample').mkdir()
                web.write_metadata('sample', {'id': 'sample', 'name': 'test'})
                self.transcript = web.project_dir('sample') / '导入访谈稿.txt'
                self.transcript.write_text('受访者：基层医院需要完善服务。', encoding='utf-8-sig')
                self.client = TestClient(web.app)
                self.addCleanup(self.client.close)

            def corrupt(self):
                path = web.analysis_path('sample')
                raw = b'{"codes": [unfinished\xff'
                path.write_bytes(raw)
                return path, raw

            def assert_preserved(self, path, raw):
                self.assertEqual(path.read_bytes(), raw)
                backups = list(path.parent.glob(path.name + '.corrupt-*.bak'))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_bytes(), raw)

            def test_import_isolated_before_boundary_check(self):
                self.assertTrue(boundary_checks)
                self.assertEqual(web.APP_DIR, root.resolve())

            def test_corrupt_analysis_never_silently_empties(self):
                path, raw = self.corrupt()
                for _ in range(2):
                    with self.assertRaises(SiteError) as caught:
                        web.read_analysis('sample')
                    self.assertEqual(caught.exception.status, 409)
                    self.assert_preserved(path, raw)

            def test_corrupt_workspace_save_refuses_overwrite(self):
                path, raw = self.corrupt()
                response = self.client.put('/api/projects/sample/analysis-workspace', json={'data': {'codes': []}})
                self.assertEqual(response.status_code, 409, response.text)
                self.assert_preserved(path, raw)

            def test_document_rejects_non_objects_and_invalid_utf8(self):
                path = self.directory / 'document.json'
                for raw in (b'[]', b'null', b'"text"', b'\xff', b'{'):
                    with self.subTest(raw=raw):
                        path.write_bytes(raw)
                        with self.assertRaises(SiteError) as caught:
                            storage.read_json_document(path)
                        self.assertEqual(caught.exception.status, 409)
                        self.assertEqual(path.read_bytes(), raw)

            def test_json_round_trip(self):
                path = self.directory / 'nested' / 'document.json'
                data = {'name': '研究资料', 'codes': [1]}
                storage.atomic_write_json(path, data)
                self.assertEqual(storage.read_json_document(path), data)

            def test_metadata_replace_interruption_preserves_original(self):
                path = web.metadata_path('sample')
                original = path.read_bytes()
                with patch('theme_file_io.os.replace', side_effect=OSError('simulated disk failure')) as replace:
                    with self.assertRaises(OSError):
                        web.write_metadata('sample', {'name': 'new'})
                replace.assert_called_once()
                self.assertEqual(path.read_bytes(), original)

            def test_text_replace_interruption_preserves_original(self):
                path = self.directory / 'text.txt'
                path.write_bytes(b'original')
                with patch.object(storage.os, 'replace', side_effect=OSError('interrupted')):
                    with self.assertRaises(OSError):
                        storage.atomic_write_text(path, 'new')
                self.assertEqual(path.read_bytes(), b'original')
                self.assertEqual(list(path.parent.glob('text.txt.*.tmp')), [])

            def test_text_atomic_success_preserves_encoding(self):
                path = self.directory / 'text.txt'
                storage.atomic_write_text(path, '中文\r\n内容', encoding='utf-16')
                self.assertEqual(path.read_bytes().decode('utf-16'), '中文\r\n内容')

            def test_locked_document_reentrant_no_lost_updates(self):
                path = self.directory / 'counter.json'
                storage.atomic_write_json(path, {'count': 0})
                barrier = threading.Barrier(8)

                @storage.locked_document(lambda values: values['path'])
                def increment(path):
                    # Nested read/write locks must reuse the same RLock.
                    data = storage.read_json_document(path)
                    time.sleep(0.002)
                    data['count'] += 1
                    storage.atomic_write_json(path, data)

                def worker(_):
                    barrier.wait(timeout=5)
                    for _ in range(5):
                        increment(path=path)

                with ThreadPoolExecutor(max_workers=8) as pool:
                    list(pool.map(worker, range(8)))
                self.assertEqual(storage.read_json_document(path)['count'], 40)

            def test_different_document_locks_are_independent(self):
                barrier = threading.Barrier(2)

                @storage.locked_document(lambda values: values['path'])
                def mutate(path):
                    barrier.wait(timeout=3)

                with ThreadPoolExecutor(max_workers=2) as pool:
                    list(pool.map(mutate, [self.directory / 'a', self.directory / 'b']))

            def test_parallel_open_and_rename_preserve_both_fields(self):
                path = web.research_project_path('research')
                storage.atomic_write_json(path, {'id': 'research', 'name': 'old', 'extra': [1]})
                original_write = web.atomic_write_json

                def delayed_write(path, data):
                    time.sleep(0.02)
                    original_write(path, data)

                with patch.object(web, 'atomic_write_json', side_effect=delayed_write), ThreadPoolExecutor(max_workers=2) as pool:
                    opened = pool.submit(web.mark_research_project_opened, 'research')
                    renamed = pool.submit(web.rename_research_project, 'research', web.DisplayNameRequest(name='new'))
                    opened.result(timeout=5)
                    renamed.result(timeout=5)
                data = storage.read_json_document(path)
                self.assertEqual(data['name'], 'new')
                self.assertIn('last_opened_at', data)
                self.assertEqual(data['extra'], [1])

            def test_txt_utf16_and_gb18030(self):
                text = '访谈记录：基层医院𠀀'
                for encoding in ('utf-16', 'utf-16-be', 'gb18030'):
                    with self.subTest(encoding=encoding):
                        raw = text.encode(encoding)
                        if encoding == 'utf-16-be':
                            raw = b'\xfe\xff' + raw
                        upload = UploadFile(filename='sample.txt', file=io.BytesIO(raw))
                        self.assertEqual(web.read_uploaded_transcript(upload), text)

            def test_docx_expansion_limit_413(self):
                content = io.BytesIO()
                with zipfile.ZipFile(content, 'w', zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('word/document.xml', b'x' * (20 * 1024 * 1024 + 1))
                content.seek(0)
                with patch.dict(os.environ, {'SITE_USER_ID': 'offline-user'}):
                    with self.assertRaises(HTTPException) as caught:
                        web.read_uploaded_transcript(UploadFile(filename='bomb.docx', file=content))
                self.assertEqual(caught.exception.status_code, 413)

            def test_path_traversal_400(self):
                for resolver in (web.project_dir, web.research_project_path):
                    for value in ('../escape', '../../escape', 'nested/escape', str(self.directory / 'outside')):
                        with self.subTest(resolver=resolver.__name__, value=value):
                            with self.assertRaises(HTTPException) as caught:
                                resolver(value)
                            self.assertEqual(caught.exception.status_code, 400)

            def model(self, **kwargs):
                client = Mock()
                client.chat.completions.create.side_effect = AssertionError('Unexpected model call')
                self.patches.enter_context(patch.object(fake_openai, 'OpenAI', return_value=client))
                return client

            def memo_response(self, content, finish_reason='stop'):
                return types.SimpleNamespace(choices=[types.SimpleNamespace(
                    finish_reason=finish_reason,
                    message=types.SimpleNamespace(content=content))])

            def assert_memo_rejected_without_save(self, content, finish_reason):
                self.model()
                path = web.analysis_path('sample')
                # Cover failure both before any analysis exists and when a
                # completed memo already exists, including the merge response.
                for existing in (False, True):
                    for stage in ('part', 'merge'):
                        with self.subTest(existing=existing, stage=stage):
                            path.unlink(missing_ok=True)
                            if existing:
                                storage.atomic_write_json(path, {'codes': [{'name': 'keep'}], 'familiarity_memo': {'summary': 'keep'}})
                            original = path.read_bytes() if existing else None
                            metadata = web.metadata_path('sample').read_bytes()
                            text = '受访者：基层医院需要完善服务。'
                            if stage == 'merge':
                                text = '甲' * 6500 + '\n\n' + '乙' * 6500
                            self.transcript.write_text(text, encoding='utf-8-sig')
                            failed = self.memo_response(content, finish_reason)
                            responses = ([self.memo_response('{}'), self.memo_response('{}'), failed]
                                         if stage == 'merge' else [failed])
                            with patch.object(web, 'limited_create', side_effect=responses) as create, patch.object(web, 'atomic_write_json', wraps=web.atomic_write_json) as save:
                                response = self.client.post('/api/projects/sample/familiarity-memo', json={'refresh': True})
                            self.assertEqual(response.status_code, 502, response.text)
                            self.assertEqual(create.call_count, len(responses))
                            save.assert_not_called()
                            if existing:
                                self.assertEqual(path.read_bytes(), original)
                            else:
                                self.assertFalse(path.exists())
                            self.assertEqual(web.metadata_path('sample').read_bytes(), metadata)
                            self.assertEqual(self.transcript.read_text(encoding='utf-8-sig'), text)

            def test_memo_truncated_length_502_no_save(self):
                # Valid JSON must still be rejected if completion was truncated.
                self.assert_memo_rejected_without_save('{"summary":"partial"}', 'length')

            def test_memo_invalid_json_stop_502_no_save(self):
                self.assert_memo_rejected_without_save('{"summary": unfinished', 'stop')

            def test_generation_conflict_preserves_concurrent_edit(self):
                self.model()
                path = web.analysis_path('sample')
                original = {'codes':[{'id':'keep'}], 'familiarity_memo':{'summary':'old'}}
                for kind in ('memo','source'):
                    with self.subTest(kind=kind):
                        storage.atomic_write_json(path, original)
                        self.transcript.write_text('受访者：原稿。', encoding='utf-8-sig')
                        def concurrent_edit(client, **kwargs):
                            if kind == 'memo':
                                storage.atomic_write_json(path, {'codes':[{'id':'keep'}], 'familiarity_memo':{'summary':'manual'}})
                            else:
                                self.transcript.write_text('受访者：人工修改后的稿件。', encoding='utf-8-sig')
                            return self.memo_response(json.dumps({'summary':'model','viewpoints':[]}))
                        with patch.object(web, 'limited_create', side_effect=concurrent_edit):
                            response = self.client.post('/api/projects/sample/familiarity-memo', json={})
                        self.assertEqual(response.status_code,409,response.text)
                        saved = storage.read_json_document(path)
                        self.assertEqual(saved['codes'],[{'id':'keep'}])
                        self.assertEqual(saved['familiarity_memo']['summary'], 'manual' if kind=='memo' else 'old')

            def test_valid_memo_saves_exact_evidence_offsets(self):
                self.model()
                text = '访谈者：请介绍情况。\n\n受访者：基层医院需要完善服务。我们希望加强人员培训。'
                self.transcript.write_text(text, encoding='utf-8-sig')
                quote, second = '基层医院需要完善服务。', '我们希望加强人员培训。'
                payload = {'summary': '讨论服务与培训', 'viewpoints': [{
                    'title': '完善服务', 'summary': '需要服务和培训',
                    'evidence': [quote, '模型虚构引文'],
                    'points': [{'text': '培训', 'evidence': [second, quote]}],
                }]}
                path = web.analysis_path('sample')
                storage.atomic_write_json(path, {'codes': [{'name': 'keep'}]})
                with patch.object(web, 'limited_create', return_value=self.memo_response(json.dumps(payload))) as create:
                    response = self.client.post('/api/projects/sample/familiarity-memo', json={'refresh': True})
                self.assertEqual(response.status_code, 200, response.text)
                create.assert_called_once()
                memo = response.json()['memo']
                saved = storage.read_json_document(path)
                self.assertEqual(saved['familiarity_memo'], memo)
                self.assertEqual(saved['codes'], [{'name': 'keep'}])
                self.assertEqual(memo['summary'], payload['summary'])
                self.assertEqual(len(memo['evidence']), 2)
                evidence = {item['number']: item for item in memo['evidence']}
                self.assertEqual({item['quote'] for item in evidence.values()}, {quote, second})
                for item in evidence.values():
                    self.assertEqual(item['start'], text.index(item['quote']))
                    self.assertEqual(item['end'], item['start'] + len(item['quote']))
                    self.assertEqual(text[item['start']:item['end']], item['quote'])
                viewpoint = memo['viewpoints'][0]
                self.assertEqual([evidence[n]['quote'] for n in viewpoint['evidence']], [quote])
                self.assertEqual([evidence[n]['quote'] for n in viewpoint['points'][0]['evidence']], [second, quote])

            def test_gpu_missing_nvidia_returns_none(self):
                web.gpu_name.cache_clear()
                self.addCleanup(web.gpu_name.cache_clear)
                with patch.dict(os.environ, {'WORKBENCH_GPU_NAME': ''}), patch.object(web.subprocess, 'run', side_effect=FileNotFoundError('nvidia-smi unavailable')) as run:
                    self.assertIsNone(web.gpu_name())
                    self.assertIsNone(web.gpu_name())
                run.assert_called_once()
                self.assertEqual(run.call_args.args[0][0], 'nvidia-smi')

            def test_configured_gpu_respected_without_subprocess(self):
                web.gpu_name.cache_clear()
                self.addCleanup(web.gpu_name.cache_clear)
                with patch.dict(os.environ, {'WORKBENCH_GPU_NAME': '  Offline configured GPU  '}), patch.object(web.subprocess, 'run', side_effect=AssertionError('Configured GPU must not probe')) as run:
                    self.assertEqual(web.gpu_name(), 'Offline configured GPU')
                run.assert_not_called()

            def test_corrupt_research_listing_logs_and_preserves(self):
                path = web.research_project_path('broken')
                raw = b'{"name": unfinished'
                path.write_bytes(raw)
                healthy = web.research_project_path('healthy')
                storage.atomic_write_json(healthy, {'id': 'healthy', 'name': 'keep'})
                before = healthy.read_bytes()
                with self.assertLogs('workbench.backend', level='WARNING') as logs:
                    result = web.research_project_list([], False)
                self.assertEqual([item['id'] for item in result], ['healthy'])
                events = [json.loads(record.getMessage()) for record in logs.records]
                self.assertTrue(any(event['event'] == 'research_listing_failed' for event in events))
                self.assertEqual(path.read_bytes(), raw)
                self.assertEqual(healthy.read_bytes(), before)

            def test_corrupt_interview_listing_logs_and_preserves(self):
                directory = web.project_dir('broken')
                directory.mkdir()
                path = directory / 'project.json'
                raw = b'{"name": unfinished'
                path.write_bytes(raw)
                healthy = web.metadata_path('sample')
                before = healthy.read_bytes()
                with self.assertLogs('workbench.backend', level='WARNING') as logs:
                    result = web.list_projects()
                self.assertEqual([item['id'] for item in result], ['sample'])
                events = [json.loads(record.getMessage()) for record in logs.records]
                self.assertTrue(any(event['event'] == 'interview_listing_failed' for event in events))
                self.assertEqual(path.read_bytes(), raw)
                self.assertEqual(healthy.read_bytes(), before)

            def test_ai_quota_status_429_preserves_analysis(self):
                for endpoint, payload in (('coding-suggestions', {}), ('familiarity-memo', {'refresh': True}), ('familiarity-summary', None)):
                    with self.subTest(endpoint=endpoint):
                        path = web.analysis_path('sample')
                        storage.atomic_write_json(path, {'codes': [], 'familiarity_memo': {'summary': 'existing', 'viewpoints': []}})
                        original = path.read_bytes()
                        client = self.model()
                        client.chat.completions.create.side_effect = SiteError('quota exhausted', 429)
                        with patch.object(web, 'limited_create', side_effect=SiteError('quota exhausted', 429)):
                            response = self.client.post('/api/projects/sample/' + endpoint, json=payload)
                        self.assertEqual(response.status_code, 429, response.text)
                        self.assertEqual(path.read_bytes(), original)

            def test_optimize_quota_stops_without_retry_or_final_save(self):
                client = self.model()
                client.chat.completions.create.side_effect = SiteError('quota exhausted', 429)
                original = self.transcript.read_bytes()
                metadata = web.metadata_path('sample').read_bytes()
                with patch.object(web.time, 'sleep', side_effect=AssertionError('Must not retry quota')):
                    response = self.client.post('/api/projects/sample/optimize-transcript?punctuation_mode=full')
                self.assertEqual(response.status_code, 429, response.text)
                client.chat.completions.create.assert_called_once()
                self.assertEqual(self.transcript.read_bytes(), original)
                self.assertEqual(web.metadata_path('sample').read_bytes(), metadata)
                self.assertFalse((self.transcript.parent / 'DeepSeek自动校订稿.txt').exists())

            def test_suggestion_length_and_punctuation_invariant(self):
                text = '春' * 81 + '基层服务A1'
                self.transcript.write_text(text, encoding='utf-8-sig')
                client = self.model()
                responses = [
                    [{'from': '春' * 81, 'to': '夏'}, {'from': '基层', 'to': '基层' + '秋' * 80}],
                    [{'from': '基层服务A1', 'to': '基层服务B2'}, {'from': '基层服务A1', 'to': '基层，服务A1。'}],
                ]

                def create(**kwargs):
                    units = json.loads(kwargs['messages'][1]['content'])['units']
                    suggestions = responses.pop(0)
                    return types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason='stop', message=types.SimpleNamespace(content=json.dumps({'units': [{**u, 'suggestions': suggestions} for u in units]})))], usage=None)

                client.chat.completions.create.side_effect = create
                result = web.optimize_transcript('sample', punctuation_mode='full')
                self.assertEqual(result['text'], '春' * 81 + '基层，服务A1。')
                records = json.loads((self.transcript.parent / 'DeepSeek修改记录.json').read_text(encoding='utf-8'))['changes']
                self.assertEqual(sum(bool(r['applied']) for r in records), 1)
                self.assertEqual(sum('80' in r.get('skip_reason', '') for r in records), 2)

            def test_request_id_corrupt_status_and_context_reset(self):
                self.corrupt()
                response = self.client.get('/api/projects/sample/analysis-workspace', headers={'X-Request-ID': 'audit-request-123'})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.headers['X-Request-ID'], 'audit-request-123')
                self.assertEqual(response.json()['request_id'], 'audit-request-123')
                self.assertEqual(tracking.request_id.get(), '')
                other = self.client.get('/api/projects/sample/analysis-workspace', headers={'X-Request-ID': 'bad id!'})
                self.assertRegex(other.headers['X-Request-ID'], r'^[a-f0-9]{32}$')

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Audit)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    if ISOLATED:
        sys.exit(isolated_main())
    unittest.main(verbosity=2)
