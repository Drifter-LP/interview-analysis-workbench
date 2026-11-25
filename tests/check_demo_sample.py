"""Run only against disposable data, without model calls or real accounts."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix='workbench-demo-smoke-',ignore_cleanup_errors=True) as temporary:
    os.environ['WORKBENCH_DATA_DIR']=temporary
    os.environ.pop('WORKBENCH_TEXT_ONLY',None)
    for name in ('projects','research_projects','research_project_files','temp','outputs'):
        (Path(temporary)/name).mkdir()
    import web_app
    result=web_app.load_demo_samples()
    assert result['loaded']
    ident=result['project']['id']
    text=web_app.transcript_path(ident).read_text(encoding='utf-8-sig')
    assert '虚构' in text
    assert not web_app.load_demo_samples()['loaded']
    import json
    codes=json.loads((web_app.project_dir(ident)/'manual-coding.json').read_text(encoding='utf-8'))['codes']
    assert len(codes)>0
    for code in codes:
        for ref in code['references']:
            assert text[ref['start']:ref['end']]==ref['quote']
    print('PASS: demo load, duplicate guard and original-text reference offsets')
    import logging
    logging.shutdown()
