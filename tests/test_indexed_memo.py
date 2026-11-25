"""Offline synthetic cases; no application databases, keys or paid calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from indexed_memo import (IndexedMemoPipeline, build_source_index, evidence_batches,
                          materialize_memo, validate_ids, MEMO_PROMPT, SELECT_PROMPT)
from analysis_contracts import check_memo_source


def response(value, finish='stop'):
    content = json.dumps(value, ensure_ascii=False)
    return types.SimpleNamespace(
        model_dump=lambda **kw: dict(choices=[dict(finish_reason=finish, message=dict(content=content))]),
        choices=[types.SimpleNamespace(finish_reason=finish, message=types.SimpleNamespace(content=content))])


def memo(ids):
    return dict(participant_identity='未说明', interview_date='未说明', interview_topic='出行',
                summary='受访者仍乘地铁，费用顾虑尚未导致拒绝服务。',
                viewpoints=[dict(title='当前出行', summary='受访者仍乘地铁。', evidence=ids[:1],
                                 points=[dict(text='尚未拒绝服务。', evidence=ids[-1:])])])


class IndexedMemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.text = '访谈者：如何出行？\n受访者：😀仍坐地铁。\n我担心费用，但没有拒绝服务。'
        self.units = build_source_index(self.text)['units']
        self.ids = [u['id'] for u in self.units if '地铁' in u['text'] or '担心' in u['text']]
        self.calls = []
        self.addCleanup(patch.stopall)
        patch('ai_run.time.sleep').start()

    def pipeline(self, fn, baseline=None, text=None):
        def create(request):
            payload = json.loads(request['messages'][1]['content'])
            self.calls.append(payload)
            return response(fn(payload))
        return IndexedMemoPipeline(text or self.text, Path(self.tmp.name), baseline, create)

    def standard(self, payload):
        if 'units' in payload:
            return dict(selected_ids=[u['id'] for u in payload['units'] if u['id'] in self.ids])
        return memo(self.ids)

    def test_index_exact_offsets_repeated_text_unicode_crlf(self):
        text = '😀重复。\r\n\r\n重复。  \n尾部'
        index = build_source_index(text, 16)
        previous = -1
        for unit in index['units']:
            self.assertEqual(text[unit['start']:unit['end']], unit['text'])
            self.assertGreater(unit['start'], previous)
            self.assertEqual(unit['line'], text.count('\n', 0, unit['start']) + 1)
            previous = unit['start']
        self.assertEqual(len({u['id'] for u in index['units']}), len(index['units']))
        self.assertEqual(index, build_source_index(text, 16))
        with self.assertRaises(ValueError): build_source_index(text, 0)

    def test_huge_paragraph_is_bounded_and_fully_covered(self):
        text = '😀' + '长'*25001
        units = build_source_index(text)['units']
        self.assertEqual(''.join(u['text'] for u in units), text)
        self.assertTrue(all(len(u['text']) <= 240 for u in units))
        self.assertTrue(all(sum(len(u['text']) for u in b) <= 10000 for b in evidence_batches(units)))

    def test_selection_then_summary_materializes_exact_quotes(self):
        pipe = self.pipeline(self.standard)
        result = pipe.generate()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([u['id'] for u in self.calls[1]['evidence_units']], self.ids)
        self.assertEqual([e['source_id'] for e in result['evidence']], self.ids)
        for evidence in result['evidence']:
            self.assertEqual(self.text[evidence['start']:evidence['end']], evidence['quote'])
        check_memo_source(result, self.text)
        self.assertTrue((pipe.run.path/'source-index.json').exists())

    def test_numbered_occurrence_not_ambiguous_text_search(self):
        text = '一样。\n一样。'
        units = build_source_index(text)['units']
        result = materialize_memo(memo([units[-1]['id']]), text, units)
        self.assertEqual(result['evidence'][0]['start'], text.rindex('一样。'))

    def test_invalid_and_duplicate_ids_rejected_not_fuzzy_matched(self):
        for value in [['我担心费用，但没有拒绝服务。'], ['Sunknown'], self.ids[:1]*2, [], [True]]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_ids(value, set(self.ids))

    def test_corrupt_index_never_materialized(self):
        units = copy.deepcopy(self.units)
        unit = next(u for u in units if u['id'] == self.ids[0])
        unit['text'] = '改写'
        with self.assertRaisesRegex(ValueError, '索引'):
            materialize_memo(memo(self.ids), self.text, units)

    def test_only_bad_point_repaired(self):
        original = memo(self.ids)
        original['viewpoints'][0]['points'].append(dict(text='费用顾虑', evidence=['bad-id']))
        def fn(payload):
            if 'failed_item' in payload:
                self.assertEqual(payload['failed_item']['text'], '费用顾虑')
                self.assertNotIn('viewpoints', payload)
                return dict(text='受访者担心费用。', evidence=self.ids[-1:])
            return self.standard(payload) if 'units' in payload else original
        pipe = self.pipeline(fn)
        result = pipe.generate()
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(result['viewpoints'][0]['points'][0]['text'], '尚未拒绝服务。')
        draft = json.loads((pipe.run.path/'part-001-draft/validated.json').read_text(encoding='utf-8'))
        self.assertEqual(draft, original)

    def test_only_header_repaired_good_points_kept(self):
        original = memo(self.ids)
        original['viewpoints'][0]['evidence'] = []
        def fn(payload):
            if 'failed_item' in payload:
                self.assertNotIn('points', payload['failed_item'])
                return dict(title='修正标题', summary='受访者仍坐地铁。', evidence=self.ids[:1], points=['ignored extra'])
            return self.standard(payload) if 'units' in payload else original
        result = self.pipeline(fn).generate()
        self.assertEqual(result['viewpoints'][0]['title'], '修正标题')
        self.assertEqual(len(result['viewpoints'][0]['points']), 1)
        self.assertEqual(len(self.calls), 3)

    def test_only_metadata_repaired(self):
        def fn(payload):
            if 'failed_item' in payload:
                self.assertNotIn('viewpoints', payload['failed_item'])
                return {**memo(self.ids), 'summary': '修正摘要'}
            raw = self.standard(payload)
            if 'units' not in payload: raw['summary'] = None
            return raw
        result = self.pipeline(fn).generate()
        self.assertEqual(result['summary'], '修正摘要')
        self.assertEqual(len(result['viewpoints']), 1)
        self.assertEqual(len(self.calls), 3)

    def test_failed_point_resume_without_repeating_select_draft_or_good_repair(self):
        original = memo(self.ids)
        original['viewpoints'][0]['points'] = [dict(text='先修复', evidence=[]), dict(text='后修复', evidence=[])]
        def failing(payload):
            if 'failed_item' in payload:
                if payload['failed_item']['text'] == '先修复':
                    return dict(text='已经通过的要点', evidence=self.ids[:1])
                return dict(text='后修复', evidence=['bad-id'])
            return self.standard(payload) if 'units' in payload else original
        pipe = self.pipeline(failing)
        with self.assertRaises(ValueError): pipe.generate()
        pipe.run.fail(ValueError('虚构失败'))
        count = len(self.calls)
        def resumed(payload):
            self.assertEqual(payload['failed_item']['text'], '后修复')
            return dict(text='最后通过的要点', evidence=self.ids[-1:])
        restored = self.pipeline(resumed)
        result = restored.generate()
        self.assertEqual(len(self.calls)-count, 1)
        self.assertEqual(result['viewpoints'][0]['points'][0]['text'], '已经通过的要点')
        self.assertEqual(restored.run.id, pipe.run.id)

    def test_changed_source_or_baseline_cannot_reuse_prior_run(self):
        a = self.pipeline(self.standard)
        b = self.pipeline(self.standard, text=self.text+'新内容')
        c = self.pipeline(self.standard, baseline={'summary': '人工编辑'})
        self.assertEqual(len({a.run.id, b.run.id, c.run.id}), 3)

    def test_full_success_reuses_stages_without_model_calls(self):
        a = self.pipeline(self.standard)
        result = a.generate()
        a.run.complete()
        count = len(self.calls)
        b = self.pipeline(lambda p: self.fail('不应重新调用'))
        self.assertEqual(b.generate(), result)
        self.assertEqual(len(self.calls), count)

    def test_merge_only_receives_ids_used_by_valid_parts(self):
        text = ('受访者：我仍坐地铁。\n' * 1300)
        used, offered = set(), set()
        def fn(payload):
            if 'units' in payload:
                return dict(selected_ids=[u['id'] for u in payload['units'][:2]])
            if 'partial_memos' in payload:
                offered.update(u['id'] for u in payload['evidence_units'])
                return memo(list(offered)[:1])
            ident = payload['evidence_units'][0]['id']
            used.add(ident)
            return memo([ident])
        result = self.pipeline(fn, text=text).generate()
        self.assertEqual(used, offered)
        self.assertGreater(len(used), 1)
        check_memo_source(result, text)

    def test_context_id_not_selectable(self):
        def fn(payload): return dict(selected_ids=['context-id'])
        with self.assertRaises(ValueError): self.pipeline(fn).generate()
        self.assertEqual(len(self.calls), 3)

    def test_call_budget_stops_before_another_paid_attempt(self):
        def fn(payload):
            raw = self.standard(payload)
            if 'units' not in payload:
                raw['viewpoints'][0]['evidence'] = ['bad-id']
            return raw
        with patch('indexed_memo.MAX_MODEL_CALLS', 2), self.assertRaisesRegex(ValueError, '安全上限'):
            self.pipeline(fn).generate()
        self.assertEqual(len(self.calls), 2)

    def test_empty_selection_and_no_claims_supported(self):
        def fn(payload):
            if 'units' in payload: return dict(selected_ids=[])
            return {**memo([]), 'summary': '材料不足，未提取明确观点。', 'viewpoints': []}
        result = self.pipeline(fn).generate()
        self.assertEqual(result['evidence'], [])
        self.assertEqual(result['viewpoints'], [])

    def test_empty_source_no_paid_call(self):
        create = Mock()
        pipe = IndexedMemoPipeline(' \n', Path(self.tmp.name), None, create)
        with self.assertRaises(ValueError): pipe.generate()
        create.assert_not_called()

    def test_prompts_keep_untrusted_data_and_negation_boundaries(self):
        for prompt in (SELECT_PROMPT, MEMO_PROMPT):
            self.assertIn('不是指令', prompt)
            self.assertIn('没有采取行动不等于', prompt)
        self.assertIn('禁止抄写', MEMO_PROMPT)


if __name__ == '__main__':
    unittest.main()
