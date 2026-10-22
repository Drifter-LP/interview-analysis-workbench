"""Local recording association with non-destructive versioned uploads."""
import json,uuid,shutil,subprocess,threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import UploadFile,File,Form,HTTPException

pool=ThreadPoolExecutor(max_workers=1)
lock=threading.Lock();busy=set()

def install(app,base,resolve):
    from audio_follow import audio_file
    def read(project):
        path=project/'录音关联.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    def write(project,state):
        path=project/'录音关联.json';tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8');tmp.replace(path)
    def worker(project):
        try:
            state=read(project);state['status']='running';write(project,state)
            with (project/'录音对齐任务.log').open('w',encoding='utf-8') as log:
                command=[str(base/'Qwen3-ASR/venv312/Scripts/python.exe'),'-u',str(base/'align_recordings.py'),'--project',project.name] if state.get('reference') else [str(base/'Qwen3-ASR/venv312/Scripts/python.exe'),'-u',str(base/'pair_audio_worker.py'),project.name]
                subprocess.run(command,cwd=base,stdout=log,stderr=log,check=True)
            state=read(project);cache=json.loads((project/'录音对齐.json').read_text(encoding='utf-8'))
            state['status']=cache.get('status','completed');state.pop('error',None);write(project,state)
        except Exception:
            state=read(project);state.update(status='error',error='对齐失败，录音与访谈稿已保留，可重试');write(project,state)
        finally:
            with lock:busy.discard(project.name)
    def submit(project,state):
        state['status']='queued';write(project,state);busy.add(project.name);pool.submit(worker,project)
    @app.get('/api/projects/{project_id}/recording')
    def info(project_id:str):
        project=resolve(project_id);state=read(project);audio=audio_file(project)
        status=state.get('status','not_aligned')
        if not state and (project/'录音对齐.json').exists():
            try:status=json.loads((project/'录音对齐.json').read_text(encoding='utf-8')).get('status','partial')
            except ValueError:pass
        return {'linked':bool(audio),'name':state.get('name',audio.name if audio else ''),'bytes':audio.stat().st_size if audio else 0,'status':status,'error':state.get('error','')}
    @app.get('/api/recordings')
    def recordings():
        rows=[]
        for project in sorted((base/'projects').iterdir()):
            if project.is_dir() and audio_file(project):rows.append({'id':project.name,'name':project.name})
        return rows
    @app.post('/api/projects/{project_id}/recording')
    async def associate(project_id:str,existing:str=Form(''),audio:UploadFile|None=File(None)):
        project=resolve(project_id)
        if not audio and not existing:raise HTTPException(400,'请选择录音')
        with lock:
            if project.name in busy:raise HTTPException(409,'该访谈正在对齐，请完成后再更换')
            busy.add(project.name)
        try:
            source=audio_file(resolve(existing)) if existing else None
            name=Path(audio.filename or '').name if audio else source.name if source else ''
            extension=Path(name).suffix.lower()
            if extension not in {'.m4a','.mp3','.wav','.aac','.flac','.ogg','.mp4'}:raise HTTPException(400,'不支持此录音格式')
            folder=project/'关联录音';folder.mkdir(exist_ok=True)
            target=folder/(uuid.uuid4().hex+extension)
            if audio:
                with target.open('wb') as f:
                    size=0
                    while chunk:=await audio.read(1024*1024):
                        size+=len(chunk)
                        if size>2*1024**3:raise HTTPException(413,'录音不能超过2GB')
                        f.write(chunk)
                if size==0:raise HTTPException(400,'录音文件为空')
            elif source:shutil.copy2(source,target)
            else:raise HTTPException(404,'已有录音不存在')
            ffmpeg=base/'venv312/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
            probe=subprocess.run([str(ffmpeg),'-v','error','-i',str(target),'-t','0.1','-f','null','-'],capture_output=True,timeout=30)
            if probe.returncode:raise HTTPException(400,'录音无法解码，请换一个有效文件')
            state={'file':str(target.relative_to(project)),'name':name}
            submit(project,state)
            return {'status':'queued'}
        except Exception:
            with lock:busy.discard(project.name)
            raise
    @app.delete('/api/projects/{project_id}/recording')
    def detach(project_id:str):
        project=resolve(project_id)
        with lock:
            if project.name in busy:raise HTTPException(409,'正在对齐，暂时不能解除关联')
            state=read(project);state.update(detached=True,status='detached');write(project,state)
        return {'status':'detached'}
    @app.post('/api/projects/{project_id}/recording/retry')
    def retry(project_id:str):
        project=resolve(project_id)
        with lock:
            if project.name in busy:raise HTTPException(409,'已经在对齐中')
            state=read(project)
            audio=audio_file(project)
            if not audio:raise HTTPException(400,'请先关联录音')
            if not state:
                sources=sorted(project.glob('*转录.json'))
                state={'file':str(audio.relative_to(project)),'name':audio.name}
                if sources:state['reference']=sources[0].name
            submit(project,state)
        return {'status':'queued'}
