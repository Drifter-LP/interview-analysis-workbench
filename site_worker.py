"""Private loopback worker. Never expose its port to a public network."""
import os
from pathlib import Path
import uvicorn
from site_ai_guard import install

root = Path(os.environ['WORKBENCH_DATA_DIR'])
if not os.environ.get('SITE_WORKER_SECRET'):
    raise RuntimeError('缺少内部访问凭据，拒绝启动')
for name in ('projects', 'research_projects', 'research_project_files', 'temp', 'outputs'):
    (root / name).mkdir(parents=True, exist_ok=True)
install()
from web_app import app

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ['SITE_WORKER_PORT']), access_log=False)

