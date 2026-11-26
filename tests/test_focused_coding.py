"""Disposable synthetic pipeline tests: no credentials, network or production data."""
import tempfile
import unittest
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import ai_coding_demo as coding


class FocusedCodingTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.source = self.root / 'transcript.txt'
        self.text = '受访者：我会比较交通费用，再决定是否参加活动。'
        self.source.write_text(self.text, encoding='utf8')
        self.project = self.root / 'research.json'
        self.project.write_text('{"interview_ids":["t"]}')
        self.stack.enter_context(patch('indexed_theme.read_qwen_key', return_value='synthetic-not-a-key'))
        self.stack.enter_context(patch('openai.OpenAI', return_value=MagicMock()))
        self.stack.enter_context(patch('indexed_theme.get_index', return_value=({}, True, {})))
        unit = {'unit_id': 'u1', 'text': self.text, 'start': 0, 'end': len(self.text)}
        self.stack.enter_context(patch.object(coding, 'make_units', return_value=([[unit]], 'synthetic-index')))
        self.calls = []
        self.fail = False
        def response(client, **kwargs):
            self.calls.append(kwargs)
            if self.fail: raise ValueError('synthetic failure')
            return {'codes': [{'name': '衡量交通成本', 'definition': '比较出行费用以决定参与',
                'reason': '原文明确比较交通费用', 'focus_tag': '出行成本',
                'references': [{'unit_id': 'u1', 'quote': '比较交通费用', 'occurrence': 1}]}]}
        self.stack.enter_context(patch('theme_model_io.request_json', side_effect=response))
        app = FastAPI()
        coding.register(app, lambda p: self.project, lambda t: self.source,
                        lambda t: {}, self.root / 'files')
        self.client = TestClient(app)
        self.base = '/api/research-projects/p/ai-coding/t'

    def get(self): return self.client.get(self.base).json()
    def start_run(self, **body):
        r = self.client.post(self.base + '/run', json=body)
        self.assertEqual(r.status_code, 200, r.text)
        for _ in range(100):
            d = self.get()
            if d['runs'][-1]['status'] != 'running': return d
            time.sleep(.05)
        self.fail('synthetic worker did not finish')

    def test_explore_legacy_default(self):
        d = self.start_run()
        self.assertEqual(d['runs'][0]['status'], 'completed')
        self.assertEqual(self.calls[-1]['prompt'], coding.PROMPT)
        self.assertNotIn('research_focus', self.calls[-1]['payload'])
        self.assertEqual(d['codes'][0]['coding_mode'], 'explore')
        self.assertEqual(d['codes'][0]['references'][0]['validation'], 'valid')

    def test_focus_payload_and_append_only(self):
        old = self.start_run()['codes'][0]
        d = self.start_run(mode='focused', focus_question='如何决定参加活动？', focus_dimensions=['出行成本'])
        self.assertEqual(self.calls[-1]['prompt'], coding.FOCUSED_PROMPT)
        self.assertEqual(self.calls[-1]['payload']['research_focus']['dimensions'], ['出行成本'])
        self.assertEqual(d['codes'][0], old)
        self.assertEqual(len(d['codes']), 2)
        self.assertEqual(d['codes'][1]['focus_label'], '出行成本')

    def test_resume_uses_original_focus(self):
        self.fail = True
        d = self.start_run(mode='focused', focus_question='原研究问题')
        self.assertIn(d['runs'][-1]['status'], ('failed', 'partial'))
        self.fail = False
        d = self.start_run(resume_run_id=d['runs'][-1]['id'], mode='explore', focus_question='不应替换')
        self.assertEqual(self.calls[-1]['payload']['research_focus']['question'], '原研究问题')
        self.assertEqual(len(d['codes']), 1)
        self.assertEqual(d['runs'][-1]['status'], 'completed')

    def test_bulk_accept_only_selected_mode(self):
        self.start_run()
        d = self.start_run(mode='focused', focus_dimensions=['出行成本'])
        r = self.client.post(self.base + '/accept-all', json={'confirmed': True, 'revision': d['revision'], 'coding_mode': 'focused'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['accepted_count'], 1)
        self.assertEqual([c['status'] for c in self.get()['codes']], ['pending', 'accepted'])

    def test_invalid_focus_does_not_start(self):
        for body in ({'mode':'focused'}, {'mode':'wrong'}, {'mode':'focused','focus_question':123},
                     {'mode':'focused','focus_question':'a'*301}, {'mode':'focused','focus_dimensions':[{}]},
                     {'mode':'focused','focus_dimensions':['a']*9}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(self.base + '/run', json=body).status_code, 400)
        self.assertEqual(self.get()['runs'], [])
        self.assertEqual(self.calls, [])

    def test_fabricated_quote_not_acceptable(self):
        units = [{'unit_id':'u1','text':self.text,'start':0}]
        reply = {'codes':[{'name':'测试','definition':'测试','reason':'测试',
                          'references':[{'unit_id':'u1','quote':'不存在的引文','occurrence':1}]}]}
        code = coding.validate_codes(reply, units, self.text)[0]
        self.assertEqual(code['references'][0]['validation'], 'needs_resolution')


if __name__ == '__main__': unittest.main()
