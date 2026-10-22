"""Start the local-only Windows workbench with empty, untracked data folders."""
from pathlib import Path
import uvicorn

def main():
    root=Path(__file__).resolve().parent
    for name in ('projects','research_projects','research_project_files','temp','outputs'):
        (root/name).mkdir(exist_ok=True)
    uvicorn.run('web_app:app',host='127.0.0.1',port=8765,app_dir=str(root))

if __name__=='__main__':main()
