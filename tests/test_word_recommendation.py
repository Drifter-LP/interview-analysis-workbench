import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from word_cooccurrence import register_word_cooccurrence


class WordRecommendationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.transcript = root / 'sample.txt'
        text = '受访者：测试材料。'
        self.transcript.write_text(text, encoding='utf-8')
        self.project = root / 'project.json'
        self.project.write_text(json.dumps({'name': '测试项目', 'interview_ids': ['interview']}), encoding='utf-8')
        app = FastAPI()
        register_word_cooccurrence(app, lambda pid: self.project, lambda tid: self.transcript,
                                   lambda: 'isolated-model-placeholder', None, None)
        self.path = root / 'word_cooccurrence' / 'project.json'
        self.data = {'revision': 7, 'confirmed': True, 'status': 'words', 'step': 3,
                     'interviews': [{'id': 'interview', 'hash': hashlib.sha256(text.encode()).hexdigest(), 'issues': []}],
                     'candidates': [{'word': '社区', 'blocks': 2}, {'word': '服务', 'blocks': 1}],
                     'selected_words': ['社区']}
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, content, finish='stop', raw=None):
        before = self.path.read_bytes()
        reply = raw if raw is not None else {'choices': [{'finish_reason': finish, 'message': {'content': content}}]}
        with patch.dict(os.environ, {'SITE_USER_ID': ''}), patch('word_cooccurrence.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(reply).encode())) as model, self.assertLogs('workbench.backend', level='INFO') as captured:
            response = self.client.post('/api/research-projects/project/word-cooccurrence/recommend', json={'revision': 7})
        model.assert_called_once()
        self.assertEqual(self.path.read_bytes(), before)
        event = json.loads(captured.records[-1].getMessage())
        self.assertNotIn('内部模拟理由', captured.records[-1].getMessage())
        return response, event

    def test_mixed_rows_preserve_whitelist_and_existing_selection(self):
        response, event = self.post(json.dumps({'recommendations': [
            {'word': ['社区'], 'reason': '内部模拟理由'}, {'word': '不存在', 'reason': '内部模拟理由'},
            {'word': '服务', 'reason': ' '}, {'word': '服务', 'reason': ' 内部模拟理由 '},
            {'word': '服务', 'reason': '重复'}, {'word': '社区', 'reason': '用于人工核对'}]}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r['word'] for r in response.json()['recommendations']], ['服务', '社区'])
        self.assertEqual(response.json()['skipped_count'], 4)
        self.assertEqual(event['event'], 'word_recommendation_validated')
        self.assertEqual(event['accepted_count'], 2)

    def test_distinguishes_unusable_responses_without_retrying(self):
        cases = [
            ('{"recommendations": [', 'length', None, 'truncated', '截断'),
            ('not JSON 内部模拟理由', 'stop', None, 'invalid_json', '格式'),
            ('{}', 'stop', None, 'invalid_list', '列表'),
            ('{"recommendations": []}', 'stop', None, 'empty_list', '合格'),
            ('{"recommendations":[{"word":"候选表外","reason":"内部模拟理由"}]}', 'stop', None, 'no_valid_rows', '合格'),
            ('{}', 'stop', {'choices': []}, 'invalid_envelope', '结构'),
        ]
        for content, finish, raw, kind, message in cases:
            with self.subTest(kind=kind):
                response, event = self.post(content, finish, raw)
                self.assertEqual(response.status_code, 502)
                self.assertIn(message, response.json()['detail'])
                self.assertEqual(event['failure_kind'], kind)


if __name__ == '__main__':
    unittest.main()
