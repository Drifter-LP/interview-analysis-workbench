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

if __name__=='__main__':
    try:unittest.main()
    finally:
        __import__('logging').shutdown()
        TEMP.cleanup()
