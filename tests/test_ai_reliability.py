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

if __name__=='__main__':
    try:unittest.main()
    finally:
        __import__('logging').shutdown()
        TEMP.cleanup()
