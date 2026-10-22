"""Researcher-led review. AI suggestions and human revisions remain separate."""
import json,time,uuid,logging
from pathlib import Path
from fastapi import HTTPException
from pydantic import BaseModel
from statement_comparison import prepare
from review_storage import PROJECT_LOCK, atomic_json, indexes, read_record, store

CALL_LOG_DIR=Path(__file__).resolve().parent/'outputs'/'finding-review-calls'

def write_call_log(record):
    CALL_LOG_DIR.mkdir(parents=True,exist_ok=True)
    (CALL_LOG_DIR/(record['call_id']+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')

def write_call_artifact(call_id,name,value):
    directory=CALL_LOG_DIR/call_id
    directory.mkdir(parents=True,exist_ok=True)
    (directory/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

class ReviewValidationError(ValueError):
    def __init__(self,message,**details):
        super().__init__(message)
        self.details=details

class ReviewRequest(BaseModel):
    dimension_index:int
    finding_index:int
    resume_call_id:str|None=None

class SaveRequest(ReviewRequest):
    review:dict

class TitleRequest(ReviewRequest):
    title:str
    previous_title:str

def validate_suggestions(raw,rows):
    allowed={r['id'] for r in rows};seen=set()
    if not isinstance(raw,dict):raise ReviewValidationError('核查结果必须是JSON对象',field='root')
    items=raw.get('items')
    if not isinstance(items,list):raise ReviewValidationError('核查结果items必须是数组',field='items')
    for index,item in enumerate(items,1):
        def fail(message,field):
            raise ReviewValidationError(f'第{index}条核查结果：{message}',item_index=index,field=field,item=item)
        if not isinstance(item,dict):fail('必须是对象','item')
        sid=item.get('statement_id')
        if not isinstance(sid,str) or sid not in allowed:fail(f'表述编号无效（{str(sid)[:80]}）','statement_id')
        if sid in seen:fail(f'表述编号重复（{sid}）','statement_id')
        category=item.get('category')
        if not isinstance(category,str) or category not in {'support','counter','condition','uncertain'}:fail(f'分类无效（{str(category)[:80]}）','category')
        if not isinstance(item.get('reason'),str):fail('理由reason必须是文字','reason')
        seen.add(sid)
    return items

def install(app,project_path,read_key,files_dir=None):
    def archive_dir(path):
        return Path(files_dir) if files_dir is not None else path.parent / 'research_project_files'
    def load(pid,aid,body):
        path=project_path(pid)
        if not path.exists():raise HTTPException(404,'项目不存在')
        project=json.loads(path.read_text(encoding='utf-8'))
        analysis=next((a for a in project.get('theme_analyses',[]) if a.get('id')==aid),None)
        if not analysis:raise HTTPException(404,'分析不存在')
        try:
            if body.dimension_index<0 or body.finding_index<0:raise IndexError()
            finding=analysis['dimensions'][body.dimension_index]['findings'][body.finding_index]
        except (IndexError,KeyError):raise HTTPException(400,'发现不存在')
        return path,project,analysis,finding

    @app.put('/api/research-projects/{pid}/theme-analyses/{aid}/finding-title')
    def edit_title(pid:str,aid:str,body:TitleRequest):
        with PROJECT_LOCK:
            path,project,analysis,finding=load(pid,aid,body)
            title=body.title.strip()
            if not title or len(title)>1000:raise HTTPException(400,'发现文字不能为空或超过1000字')
            if finding['title']!=body.previous_title:raise HTTPException(409,'该发现已被修改，请刷新后再编辑')
            if title!=finding['title']:
                finding.setdefault('title_history',[]).append({'title':finding['title'],'changed_at':time.time()})
                finding['title']=title
                analysis['updated_at']=project['updated_at']=time.time()
                atomic_json(path,project)
            return {'title':title}

    @app.post('/api/research-projects/{pid}/theme-analyses/{aid}/finding-review')
    def review(pid:str,aid:str,body:ReviewRequest):
        _,_,analysis,finding=load(pid,aid,body)
        _,rows=prepare(analysis)
        key=read_key()
        if not key:raise HTTPException(400,'未配置DeepSeek密钥')
        from openai import OpenAI
        from finding_review_pipeline import run
        if body.resume_call_id and (len(body.resume_call_id)!=32 or any(c not in '0123456789abcdef' for c in body.resume_call_id)):
            raise HTTPException(400,'核查编号无效')
        try:
            result=run(CALL_LOG_DIR,dict(project_id=pid,analysis_id=aid,
                dimension_index=body.dimension_index,finding_index=body.finding_index),
                analysis.get('theme',''),finding['title'],rows,
                OpenAI(api_key=key,base_url='https://api.deepseek.com',timeout=120,max_retries=0),
                resume=body.resume_call_id)
            return {'review':result}
        except (ValueError,FileNotFoundError) as exc:
            raise HTTPException(409,'无法继续核查：请确认原发现及材料未改变，或重新开始核查') from exc

    @app.get('/api/research-projects/{pid}/theme-analyses/{aid}/finding-review/saved')
    def saved(pid:str,aid:str,dimension_index:int,finding_index:int,storage_key:str=''):
        path,_,analysis,_=load(pid,aid,ReviewRequest(dimension_index=dimension_index,finding_index=finding_index))
        history=[r for r in indexes(analysis) if r.get('dimension_index')==dimension_index and r.get('finding_index')==finding_index]
        if storage_key:
            selected=next((r for r in reversed(history) if r.get('storage_key')==storage_key),None)
            if selected is None:raise HTTPException(404,'该发现没有对应的核查记录')
        else:
            selected=history[-1] if history else None
        if selected is None:return {'review':None,'history':[]}
        if selected.get('storage_key'):
            try:record=read_record(archive_dir(path),path.stem,aid,selected['storage_key'])
            except (OSError,ValueError) as exc:
                raise HTTPException(500,'已保存核查档案读取失败；记录未删除，请检查档案完整性') from exc
        else:
            record=next(r for r in reversed(analysis.get('finding_reviews',[])) if r.get('dimension_index')==dimension_index and r.get('finding_index')==finding_index)
        return {'review':record,'history':history}

    @app.post('/api/research-projects/{pid}/theme-analyses/{aid}/finding-review/save')
    def save(pid:str,aid:str,body:SaveRequest):
        with PROJECT_LOCK:
            path,project,analysis,finding=load(pid,aid,body)
            record={**body.review,'dimension_index':body.dimension_index,'finding_index':body.finding_index,'original_title':finding['title'],'saved_at':time.time()}
            entry=store(archive_dir(path),path.stem,aid,record)
            analysis.setdefault('finding_review_index',[]).append(entry)
            project['updated_at']=record['saved_at']
            atomic_json(path,project)
            return {'review':record,'index':entry}
