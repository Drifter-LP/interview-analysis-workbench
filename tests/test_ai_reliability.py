"""Disposable fixtures only; never import against the real workbench data."""
import os,sys,tempfile,unittest,json,types
from pathlib import Path
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1]
TEMP=tempfile.TemporaryDirectory(prefix='ai-reliability-',ignore_cleanup_errors=True)
DATA=Path(TEMP.name)
for name in ('projects','research_projects','research_project_files','outputs','temp'):
    (DATA/name).mkdir()
os.environ.update(WORKBENCH_DATA_DIR=str(DATA),SITE_HOME=str(DATA/'accounts'),
                  WORKBENCH_TEXT_ONLY='',SITE_USER_ID='',SITE_WORKER_SECRET='')
sys.path.insert(0,str(ROOT))
import web_app as app

class Reliability(unittest.TestCase):
    def setUp(self):
        self.pid=__import__('uuid').uuid4().hex
        app.project_dir(self.pid).mkdir()
        app.write_metadata(self.pid,{'id':self.pid,'name':'虚构测试','status':'completed'})
        (app.project_dir(self.pid)/'导入访谈稿.txt').write_text('受访者：我担心费用，但没有拒绝服务。',encoding='utf-8')

    def test_analysis_compare_and_swap(self):
        a=app.get_analysis_workspace(self.pid);b=dict(a)
        a['metadata']={'note':'new'}
        saved=app.save_analysis_workspace(self.pid,app.AnalysisUpdate(data=a))
        self.assertNotEqual(saved['_version'],'new')
        with self.assertRaises(app.HTTPException) as error:
            app.save_analysis_workspace(self.pid,app.AnalysisUpdate(data=b))
        self.assertEqual(error.exception.status_code,409)
        self.assertEqual(app.read_analysis(self.pid)['metadata'],{'note':'new'})

    def test_unversioned_existing_document_is_rejected(self):
        app.atomic_write_json(app.analysis_path(self.pid),{'metadata':{'kept':True}})
        with self.assertRaises(app.HTTPException):
            app.save_analysis_workspace(self.pid,app.AnalysisUpdate(data={'metadata':{}}))
        self.assertTrue(app.read_analysis(self.pid)['metadata']['kept'])

    def test_memo_contract_valid_unicode(self):
        from analysis_contracts import validate_memo,check_memo_source
        text='😀受访者：我担心费用，但没有拒绝服务。'
        raw=dict(participant_identity='受访者',interview_date='未说明',interview_topic='费用',
                 summary='受访者担心费用，但未拒绝服务。',
                 viewpoints=[dict(title='费用顾虑',summary='受访者表达顾虑。',
                    evidence=['我担心费用，但没有拒绝服务。'],points=[])])
        memo=validate_memo(raw,text)
        e=memo['evidence'][0]
        self.assertEqual(text[e['start']:e['end']],e['quote'])
        check_memo_source(memo,text)
        with self.assertRaises(ValueError):check_memo_source(memo,text+'变动')
        raw['summary']={}
        with self.assertRaises(ValueError):validate_memo(raw,text)
        raw['summary']='概括';raw['viewpoints'][0]['evidence']=['不存在']
        with self.assertRaises(ValueError):validate_memo(raw,text)

    def test_memo_ambiguous_quote_rejected(self):
        from analysis_contracts import validate_memo
        raw=dict(participant_identity='未说明',interview_date='未说明',interview_topic='未说明',
                 summary='概括',viewpoints=[dict(title='观点',summary='概括',evidence=['好'],points=[])])
        with self.assertRaises(ValueError):validate_memo(raw,'好，好')

    def test_rejected_dimension_not_used(self):
        from indexed_theme import assemble_result
        raw={'findings':[dict(id='F1',title='发现',statement_ids=[])],'reference_relations':[],
             'selected_dimensions':{'dimensions':[dict(name='不合格分类',finding_ids=['F1'])],'unclassified':[]},
             'dimension_selection':{'acceptable':False}}
        self.assertEqual(assemble_result([],raw)[0]['name'],'暂无分类')

    def test_invalid_old_coding_binding_is_not_silently_dropped(self):
        from interview_coding import validate_reply
        raw={'codes':[dict(id='c1',name='编码',definition='定义')],
             'bindings':[dict(code_id='c1',unit_id='u1',quote='不存在')]}
        with self.assertRaises(ValueError):
            validate_reply(raw,[dict(unit_id='u1',text='原文',start=0,unit_kind='paragraph')],'原文',self.pid)

    def test_memo_stages_resume_and_keep_attempts(self):
        from ai_run import MemoRun
        from theme_file_io import read_json
        def response(raw):
            return types.SimpleNamespace(
                model_dump=lambda **kw:dict(choices=[dict(message=dict(content=json.dumps(raw)))]),
                choices=[types.SimpleNamespace(finish_reason='stop',message=types.SimpleNamespace(content=json.dumps(raw)))])
        run=MemoRun(DATA/'runs',dict(text='虚构材料',model='fake'))
        invoke=Mock(return_value=response(dict(ok=True)))
        validate=lambda raw: self.assertTrue(raw.get('ok'))
        run.call('part-1',invoke,validate,request=dict(model='fake',input='虚构'))
        failure=Mock(side_effect=ValueError('错误结构'))
        with patch('ai_run.time.sleep'),self.assertRaises(ValueError):
            run.call('part-2',failure,validate)
        run.fail(ValueError('未完成'))
        resumed=MemoRun(DATA/'runs',dict(text='虚构材料',model='fake'))
        resumed.call('part-1',invoke,validate)
        self.assertEqual(invoke.call_count,1)
        self.assertEqual(failure.call_count,3)
        self.assertEqual(len(list((run.path/'part-2').glob('attempt-*'))),3)
        self.assertTrue((run.path/'part-1/attempt-001/request.json').exists())
        resumed.call('part-2',invoke,validate);resumed.complete()
        self.assertEqual(read_json(run.path/'manifest.json')['status'],'completed')
        resumed.fail(RuntimeError('late duplicate response'))
        self.assertEqual(read_json(run.path/'manifest.json')['status'],'completed')

    def test_memo_auth_failure_not_retried(self):
        from ai_run import MemoRun
        error=RuntimeError('no secret here');error.status_code=401
        invoke=Mock(side_effect=error)
        with self.assertRaises(RuntimeError):
            MemoRun(DATA/'runs',dict(text=self.pid)).call('part-1',invoke,lambda r:None)
        self.assertEqual(invoke.call_count,1)

    def test_theme_save_is_idempotent(self):
        research=app.research_project_path(self.pid)
        app.atomic_write_json(research,dict(id=self.pid,theme_analyses=[]))
        payload=dict(name='虚构主题',theme='测试',dimensions=[])
        body=app.ThemeAnalysisSaveRequest(analysis=payload,request_id='test-request-123')
        with patch('review_storage.rehome'):
            first=app.save_theme_analysis(self.pid,body)
            second=app.save_theme_analysis(self.pid,body)
            self.assertEqual(first['analysis']['id'],second['analysis']['id'])
            self.assertEqual(second['count'],1)
            with self.assertRaises(app.HTTPException):
                app.save_theme_analysis(self.pid,app.ThemeAnalysisSaveRequest(
                    analysis=dict(payload,name='不同内容'),request_id='test-request-123'))

    def test_chunk_coverage_boundaries_and_unicode(self):
        from text_chunks import bounded_spans
        for text in ['😀'+('没有换行的内容'*7000),('访问员：您怎么看？\n受访者：不能一概而论。\n\n'*900),'前文\n\n中段。\n末尾  ']:
            spans=bounded_spans(text,12000)
            self.assertEqual(''.join(s['text'] for s in spans),text)
            self.assertTrue(all(len(s['text'])<=12000 for s in spans))
            for i,s in enumerate(spans):
                self.assertEqual(text[s['start']:s['end']],s['text'])
                if i:self.assertEqual(spans[i-1]['end'],s['start'])
        pair='提问人：您拒绝过服务吗？\n受访者：没有。'
        self.assertEqual(len(bounded_spans(pair,100)),1)

    def test_coding_long_single_unit_has_budget_and_question_context(self):
        from interview_coding import source_units,batches,generate_initial_codes
        text='访问员：您对费用担心吗？\n\n受访者：'+('需要看具体情况。'*3500)
        units=source_units(text)
        self.assertTrue(all(len(u['text'])<=8000 for u in units))
        self.assertTrue(all(sum(len(u['text']) for u in batch)<=9000 for batch in batches(units)))
        self.assertTrue(units[1]['question_context'].startswith('访问员：'))
        for u in units:self.assertEqual(text[u['start']:u['end']],u['text'])
        payloads=[]
        def call(prompt,payload):
            payloads.append(payload)
            self.assertIn('不是指令',prompt)
            self.assertLessEqual(len(json.dumps(payload,ensure_ascii=False)),40000)
            return dict(codes=[],bindings=[])
        generate_initial_codes(text,'费用',[],self.pid,call)
        self.assertEqual(len(payloads),len(batches(units)))

    def test_context_cannot_become_target_evidence(self):
        from interview_coding import validate_reply
        raw=dict(codes=[dict(id='c1',name='概念',definition='定义')],bindings=[dict(code_id='c1',unit_id='context',quote='前文')])
        with self.assertRaises(ValueError):validate_reply(raw,[dict(unit_id='u1',text='本段',start=2,unit_kind='paragraph')],'前文本段',self.pid)

    def test_oversize_index_stops_before_paid_call(self):
        from indexed_theme import get_index
        call=Mock()
        with self.assertRaisesRegex(ValueError,'未截断'):
            get_index('大'*80000,call,'synthetic',DATA/'index')
        call.assert_not_called()

    def test_memo_valid_parts_merge_and_persist(self):
        q1='第一段：费用需要看报销。';q2='第二段：现在仍坐地铁。'
        text=q1+'甲'*6200+'\n\n'+q2+'乙'*6200
        (app.project_dir(self.pid)/'导入访谈稿.txt').write_text(text,encoding='utf-8')
        def raw(quotes):
            return dict(participant_identity='未说明',interview_date='未说明',interview_topic='虚构测试',summary='虚构材料概括',
                viewpoints=[dict(title='虚构观点',summary='仅测试数据流',evidence=quotes,points=[])])
        def response(value):
            content=json.dumps(value,ensure_ascii=False)
            return types.SimpleNamespace(model_dump=lambda **kw:dict(content=content),
                choices=[types.SimpleNamespace(finish_reason='stop',message=types.SimpleNamespace(content=content))])
        with patch.object(app,'read_deepseek_key',return_value='synthetic-key'),patch.object(app,'limited_create',
                side_effect=[response(raw([q1])),response(raw([q2])),response(raw([q1,q2]))]) as call:
            result=app.generate_familiarity_memo(self.pid,app.MemoRequest())
        self.assertEqual(call.call_count,3)
        self.assertIn('合并',call.call_args.kwargs['messages'][0]['content'])
        self.assertEqual([e['quote'] for e in result['memo']['evidence']],[q1,q2])
        self.assertEqual(app.read_analysis(self.pid)['familiarity_memo'],result['memo'])

if __name__=='__main__':
    try:unittest.main()
    finally:
        __import__('logging').shutdown()
        TEMP.cleanup()
