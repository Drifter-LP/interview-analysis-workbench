"""Single-transcript open coding: immutable source snapshots, append-only AI runs."""
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid
from fastapi import HTTPException
from theme_file_io import read_json, write_json, file_lock
from interview_coding import source_units

PROMPT = '''你是质性访谈开放式编码助手，不撰写纪要、主题发现或理论模型。
只依据units中的逐字原文，为有研究意义的具体行动、经验、认知、情绪、评价和情境提出初步编码。
名称简短具体，定义说明具体含义及边界。不要每句话生成一个编码，不根据关键词机械归类，不为寒暄口头语强行编码，不要求覆盖所有原文。
同一种含义复用一致名称与定义；含义不同不能因词语相同就合并。同一片段可有多个编码，同一编码可有多处引用。已有编码仅供参考，允许新增，不修改已有编码。
提问只作为语境，不将提问者假设当作受访者观点；含义不明保持谨慎。保留否定、条件、主体和表达性质，不虚构事实或解释，不建多级编码树。
每处引用必须是某个unit内部连续逐字原文，禁止改写、拼接和省略号替换。occurrence是该quote在指定unit中从左到右的第几次逐字出现，从1开始，用于消除重复引文歧义。不要估计全篇字符位置，程序按unit及精确quote恢复并验证范围。
只输出JSON对象：{"codes":[{"name":"编码名称","definition":"说明","reason":"建议理由","references":[{"unit_id":"u1","quote":"逐字引文","occurrence":1}]}]}。
references不可为空，reason简要说明为何该原文支持这个编码；同含义多个片段合在一个code内。无可靠建议时codes为空。'''

def digest(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()
def now(): return time.time()
def uid(): return uuid.uuid4().hex

def bulk_acceptable(code,d):
    if code.get('origin')!='ai' or code.get('status')!='pending' or code.get('deleted_at') or code.get('source_hash')!=d['current_hash']:return False
    text=d['sources'][d['current_hash']]['text'];refs=code.get('references',[])
    return bool(refs) and all(r.get('validation')=='valid' and type(r.get('start')) is int and type(r.get('end')) is int and 0<=r['start']<r['end']<=len(text) and text[r['start']:r['end']]==r.get('quote') for r in refs)

def make_units(text, cache_dir, limit=5000, require_index=False):
    """Reuse validated indexes without building or mutating them; never lose skipped text."""
    from indexed_theme import cache_path, validate_index
    ranges=[];policy='source-paragraphs'
    p=cache_path(cache_dir,digest(text))
    if p.exists():
        try:
            cached=read_json(p)
            if cached.get('source_hash')!=digest(text): raise ValueError('hash')
            index=validate_index(cached['index'],text.splitlines());offsets=[0]
            for line in text.splitlines(keepends=True):offsets.append(offsets[-1]+len(line))
            cursor=0
            for block in index['blocks']:
                start,end=offsets[block['start']-1],offsets[block['end']]
                if cursor<start:ranges.append((cursor,start))
                ranges.append((start,end));cursor=end
            if cursor<len(text):ranges.append((cursor,len(text)))
            policy='shared-topic-index'
        except (ValueError,KeyError,IndexError):
            if require_index:raise
            ranges=[];policy='source-paragraphs (index unavailable)'
    if require_index and not ranges:raise ValueError('共享话题索引未准备完成，不启动编码')
    if not ranges:ranges=[(u['start'],u['end']) for u in source_units(text)]
    units=[]
    for start,end in ranges:
        while start<end:
            stop=min(start+limit,end)
            if stop<end:
                cut=text.rfind('\n',start+limit//2,stop)
                if cut>start:stop=cut+1
            if text[start:stop].strip():units.append({'unit_id':'u'+str(len(units)+1),'start':start,'end':stop,'text':text[start:stop]})
            start=stop
    batches=[];batch=[];size=0
    for unit in units:
        if batch and size+len(unit['text'])>limit:batches.append(batch);batch=[];size=0
        batch.append(unit);size+=len(unit['text'])
    if batch:batches.append(batch)
    return batches,policy

def validate_codes(reply, units, text):
    if not isinstance(reply,dict) or not isinstance(reply.get('codes'),list):raise ValueError('输出缺少codes数组')
    mapping={u['unit_id']:u for u in units};result=[]
    for item in reply['codes']:
        if not isinstance(item,dict) or any(not isinstance(item.get(k),str) or not item[k].strip() for k in ('name','definition','reason')):raise ValueError('编码缺少名称、说明或理由')
        if not isinstance(item.get('references'),list) or not item['references']:raise ValueError('编码缺少引用')
        refs=[]
        for raw in item['references']:
            ref={'id':uid(),'unit_id':raw.get('unit_id') if isinstance(raw,dict) else None,'quote':raw.get('quote') if isinstance(raw,dict) else None,'start':None,'end':None,'validation':'needs_resolution'}
            unit=mapping.get(ref['unit_id']);quote=ref['quote'];occ=raw.get('occurrence') if isinstance(raw,dict) else None
            offsets=[];cursor=0
            if unit and isinstance(quote,str) and quote.strip():
                while True:
                    at=unit['text'].find(quote,cursor)
                    if at<0:break
                    offsets.append(at);cursor=at+1
            if len(offsets)==1 and occ in (None,1):at=offsets[0]
            elif type(occ) is int and 1<=occ<=len(offsets):at=offsets[occ-1]
            else:at=None
            if at is not None:
                start=unit['start']+at;end=start+len(quote)
                if text[start:end]==quote:ref.update(start=start,end=end,validation='valid')
            if ref['validation']!='valid':ref['error']='引用或出现序号无法精确匹配，需人工选择范围'
            refs.append(ref)
        result.append({k:item[k].strip() for k in ('name','definition','reason')}|{'references':refs})
    return result

def register(app,research_path,transcript_path,read_metadata,files_dir):
    root=Path(files_dir)/'_ai_coding_demo';jobs=set();job_lock=threading.Lock();organizer_busy=lambda pid,tid:False
    def location(pid,tid):
        if not research_path(pid).exists():raise HTTPException(404,'研究项目不存在')
        project=read_json(research_path(pid));allowed=set(project.get('interview_ids',[]))|{x.get('workspace_project_id') for x in project.get('uploaded_transcripts',[])}
        if tid not in allowed:raise HTTPException(404,'访谈不属于该研究项目')
        return root/digest(pid)/digest(tid)/'coding.json'
    def load(pid,tid):
        p=location(pid,tid)
        if p.exists():d=read_json(p)
        else:d={'project_id':pid,'source_id':tid,'revision':0,'codes':[],'sources':{},'runs':[]}
        d.setdefault('deleted_codes',[])
        source=transcript_path(tid)
        if not source or not source.exists():raise HTTPException(404,'访谈原文未准备，请先在访谈资料中打开该访谈')
        text=source.read_text(encoding='utf-8-sig');h=digest(text)
        d['current_hash']=h;d['sources'].setdefault(h,{'text':text,'captured_at':now()})
        for run in d['runs']:
            if run['status']=='running' and (pid,tid) not in jobs:run['status']='partial';run['error']='服务已重启，可继续未完成批次'
        return d
    def save(pid,tid,d):d['revision']+=1;d['updated_at']=now();write_json(location(pid,tid),d)
    def batch_run(pid,tid,runid):
        p=location(pid,tid)
        key=''
        try:
            from indexed_theme import MODEL,BASE_URL,read_qwen_key,get_index,validate_index,cache_path
            from openai import OpenAI
            from theme_model_io import request_json
            key=read_qwen_key();client=OpenAI(api_key=key,base_url=BASE_URL,timeout=180,max_retries=0)
            with file_lock(p):
                d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid);text=d['sources'][run['source_hash']]['text']
                preparation=run.setdefault('index_preparation',{'status':'pending','attempts':[]})
                needs_index=preparation['status']!='completed'
                if needs_index:preparation.update(status='running');preparation.pop('error',None)
                save(pid,tid,d)
            if needs_index:
                cache_dir=Path(files_dir)/'theme_topic_indexes'
                def index_call(prompt,payload,label,budget):
                    for attempt in range(3):
                        with file_lock(p):
                            d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid);prep=run['index_preparation']
                            prep['attempts'].append({'at':now(),'status':'running'});number=len(prep['attempts']);save(pid,tid,d)
                        artifact=p.parent/'calls'/runid/f'index-attempt-{number}.json'
                        try:
                            reply=request_json(client,model=MODEL,prompt=prompt,payload=payload,budget=budget,on_response=lambda response:write_json(artifact,response))
                            validate_index(reply,text.splitlines())
                            with file_lock(p):
                                d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid);run['index_preparation']['attempts'][-1].update(status='completed',ended_at=now());save(pid,tid,d)
                            return reply
                        except Exception as exc:
                            message=str(exc).replace(key,'***')[:500] if key else str(exc)[:500]
                            with file_lock(p):
                                d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid);run['index_preparation']['attempts'][-1].update(status='failed',error=message,ended_at=now());save(pid,tid,d)
                            if attempt==2:raise
                _,reused,_=get_index(text,index_call,digest(tid)[:12],cache_dir)
                with file_lock(p):
                    d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid)
                    # Resumed legacy runs retain their original batch boundaries and completed results.
                    if not run['units']:
                        units,policy=make_units(text,cache_dir,require_index=True)
                        if not units:raise ValueError('访谈没有有效原文')
                        run.update(units=units,segmentation=policy,batches=[{'status':'pending','attempts':[]} for _ in units])
                    run['index_preparation'].update(status='completed',reused=reused,source_hash=run['source_hash'],cache_file=cache_path(cache_dir,run['source_hash']).name,ended_at=now())
                    save(pid,tid,d)
            with file_lock(p):
                d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid);units=run['units']
            for index,batch in enumerate(units):
                with file_lock(p):
                    d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid)
                    if run['batches'][index]['status']=='completed':continue
                for attempt in range(3):
                    with file_lock(p):
                        d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid);b=run['batches'][index];b.update(status='running');record={'at':now(),'status':'running'};b['attempts'].append(record);save(pid,tid,d)
                        existing=[{'name':c['name'],'definition':c['definition']} for c in d['codes'] if c['source_hash']==run['source_hash']]
                    artifact=p.parent/'calls'/runid/f'batch-{index+1}-attempt-{len(b["attempts"])}.json'
                    try:
                        def capture(response):write_json(artifact,response)
                        reply=request_json(client,model=MODEL,prompt=PROMPT,payload={'units':[{'unit_id':u['unit_id'],'text':u['text']} for u in batch],'existing_codes':existing},budget=7000,on_response=capture)
                        codes=validate_codes(reply,batch,text)
                        with file_lock(p):
                            d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid);b=run['batches'][index];b['attempts'][-1]['status']='completed';b['status']='completed'
                            for c in codes:
                                # Only identical definitions within the same AI run are reused; never overwrite prior/manual codes.
                                target=next((x for x in d['codes'] if x.get('run_id')==runid and x['name']==c['name'] and x['definition']==c['definition'] and x['status']=='pending'),None)
                                if target:
                                    target['references'].extend(c['references']);target['updated_at']=now();target['revision']+=1
                                    target['ai_original']['references'].extend(json.loads(json.dumps(c['references'])))
                                else:d['codes'].append(c|{'id':uid(),'source_id':tid,'source_hash':run['source_hash'],'run_id':runid,'origin':'ai','status':'pending','revision':0,'created_at':now(),'updated_at':now(),'ai_original':json.loads(json.dumps(c))})
                            if artifact.exists():
                                a=read_json(artifact);b['attempts'][-1].update(finish_reason=a['choices'][0]['finish_reason'],usage=a.get('usage'))
                            save(pid,tid,d)
                        break
                    except Exception as exc:
                        with file_lock(p):
                            d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid);b=run['batches'][index];b['status']='failed';b['attempts'][-1].update(status='failed',error=str(exc).replace(key,'***')[:500])
                            if artifact.exists():
                                a=read_json(artifact);b['attempts'][-1].update(finish_reason=a['choices'][0]['finish_reason'],usage=a.get('usage'))
                            save(pid,tid,d)
            with file_lock(p):
                d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid);done=sum(b['status']=='completed' for b in run['batches']);run.update(status='completed' if done==len(run['batches']) else 'partial' if done else 'failed',ended_at=now());save(pid,tid,d)
        except Exception as exc:
            with file_lock(p):
                d=load(pid,tid);run=next(r for r in d['runs'] if r['id']==runid)
                if run.get('index_preparation',{}).get('status')!='completed':
                    message=str(exc).replace(key,'***')[:500] if key else str(exc)[:500]
                    run.setdefault('index_preparation',{}).update(status='failed',error=message)
                    run.update(status='failed',error='话题索引准备失败，未启动后续编码：'+message,ended_at=now())
                else:run.update(status='failed',error='运行中断：'+type(exc).__name__,ended_at=now())
                save(pid,tid,d)
        finally:
            with job_lock:jobs.discard((pid,tid))

    @app.get('/api/research-projects/{pid}/ai-coding/materials')
    def materials(pid):
        if not research_path(pid).exists():raise HTTPException(404,'研究项目不存在')
        project=read_json(research_path(pid));ids=list(dict.fromkeys(project.get('interview_ids',[])+[x['workspace_project_id'] for x in project.get('uploaded_transcripts',[]) if x.get('workspace_project_id')]))
        return [{'id':tid,'name':read_metadata(tid).get('name',tid)} for tid in ids if transcript_path(tid)]

    @app.get('/api/research-projects/{pid}/ai-coding/{tid}')
    def get(pid,tid):
        p=location(pid,tid)
        with file_lock(p):return load(pid,tid)

    @app.post('/api/research-projects/{pid}/ai-coding/{tid}/accept-all')
    def accept_all(pid,tid,body:dict):
        p=location(pid,tid)
        with job_lock,file_lock(p):
            if (pid,tid) in jobs or organizer_busy(pid,tid):raise HTTPException(409,'正在编码或整理，请完成后再批量接受')
            d=load(pid,tid)
            if body.get('confirmed') is not True:raise HTTPException(400,'请确认批量接受')
            if body.get('revision')!=d['revision']:raise HTTPException(409,'编码已变化，请刷新后重新确认数量')
            chosen=[c for c in d['codes'] if bulk_acceptable(c,d)]
            if not chosen:return {'coding':d,'accepted_count':0}
            at=now()
            for c in chosen:c.update(status='accepted',revision=c['revision']+1,updated_at=at)
            d.setdefault('bulk_review_history',[]).append({'id':uid(),'action':'accept_all','at':at,'code_ids':[c['id'] for c in chosen],'previous_status':'pending'})
            save(pid,tid,d)
            return {'coding':d,'accepted_count':len(chosen)}

    @app.post('/api/research-projects/{pid}/ai-coding/{tid}/run')
    def start(pid,tid,body:dict):
        from indexed_theme import read_qwen_key,MODEL
        if not read_qwen_key():raise HTTPException(400,'未配置QWEN_API_KEY')
        p=location(pid,tid)
        with job_lock,file_lock(p):
            if (pid,tid) in jobs or organizer_busy(pid,tid):raise HTTPException(409,'该访谈正在编码或整理')
            d=load(pid,tid);resume=body.get('resume_run_id')
            if resume:
                run=next((r for r in d['runs'] if r['id']==resume),None)
                if not run or run['status']=='completed':raise HTTPException(409,'没有可继续的批次')
            else:
                if not d['sources'][d['current_hash']]['text'].strip():raise HTTPException(400,'访谈没有有效原文')
                run={'id':uid(),'source_hash':d['current_hash'],'status':'running','created_at':now(),'model':MODEL,'thinking':False,'segmentation':'awaiting-shared-topic-index','units':[],'batches':[],'index_preparation':{'status':'pending','attempts':[]}};d['runs'].append(run)
            run['status']='running';run.pop('error',None);save(pid,tid,d);jobs.add((pid,tid));threading.Thread(target=batch_run,args=(pid,tid,run['id']),daemon=True).start()
            return {'run_id':run['id']}

    @app.post('/api/research-projects/{pid}/ai-coding/{tid}/codes/{code_id}/actions')
    def code_action(pid,tid,code_id,body:dict):
        """Recoverable local unlink/delete; never change a source or another code."""
        p=location(pid,tid)
        with file_lock(p):
            d=load(pid,tid);action=body.get('action')
            if action not in ('delete','restore','remove_reference','restore_reference','confirm_reference'):raise HTTPException(400,'操作无效')
            collection=d['deleted_codes'] if action=='restore' else d['codes']
            code=next((c for c in collection if c['id']==code_id),None)
            if not code:raise HTTPException(404,'编码不存在或已删除，请刷新')
            if body.get('revision')!=code['revision']:raise HTTPException(409,'编码已更新，请刷新后再操作')
            if action=='delete':
                collection.remove(code);code['deleted_at']=now();d['deleted_codes'].append(code)
            elif action=='restore':
                collection.remove(code);code.pop('deleted_at',None);d['codes'].append(code)
            elif action=='remove_reference':
                refs=code['references'];ref=next((r for r in refs if r.get('id')==body.get('reference_id')),None)
                if not ref:raise HTTPException(404,'引用不存在，请刷新')
                if len(refs)<=1:raise HTTPException(400,'这是最后一处引用；如不再需要，请删除整个编码')
                index=refs.index(ref);refs.pop(index)
                code.setdefault('removed_references',[]).append({'reference':ref,'index':index,'removed_at':now()})
            elif action=='confirm_reference':
                ref=next((r for r in code['references'] if r.get('id')==body.get('reference_id')),None)
                if not ref:raise HTTPException(404,'引用不存在，请刷新')
                if ref.get('validation')=='valid':raise HTTPException(409,'此引用已定位，请刷新后查看')
                if body.get('source_hash')!=code['source_hash']:raise HTTPException(409,'原文版本不一致')
                text=d['sources'][code['source_hash']]['text'];a,b,q=body.get('start'),body.get('end'),body.get('quote')
                if not (type(a) is int and type(b) is int and isinstance(q,str) and q.strip() and 0<=a<b<=len(text) and text[a:b]==q):raise HTTPException(400,'选区与原文范围不一致，请重新选择')
                stamp=now()
                code.setdefault('reference_location_history',[]).append({'reference_id':ref['id'],'previous':json.loads(json.dumps(ref)),'confirmed_at':stamp})
                ref.update(start=a,end=b,quote=q,validation='valid',confirmed_at=stamp,confirmed_by='researcher')
                ref.pop('error',None);ref.pop('unit_id',None)
                # Locating evidence is not accepting the code's interpretation; status stays unchanged.
            else:
                removed=code.get('removed_references',[])
                if not removed:raise HTTPException(409,'没有可恢复的引用')
                item=removed.pop();code['references'].insert(min(item['index'],len(code['references'])),item['reference'])
            code['updated_at']=now();code['revision']+=1
            save(pid,tid,d);return d

    from coding_organizer import register_organizer
    organizer_busy=register_organizer(app,location,load,save,lambda pid,tid:(pid,tid) in jobs,job_lock)

    @app.post('/api/research-projects/{pid}/ai-coding/{tid}/codes')
    def edit(pid,tid,body:dict):
        p=location(pid,tid)
        with file_lock(p):
            d=load(pid,tid);ident=body.get('id');code=next((c for c in d['codes'] if c['id']==ident),None)
            if ident and not code:raise HTTPException(404,'编码不存在')
            if code and body.get('revision')!=code['revision']:raise HTTPException(409,'编码已更新，请刷新后再修改')
            h=code['source_hash'] if code else body.get('source_hash',d['current_hash'])
            if h not in d['sources']:raise HTTPException(409,'原文版本不存在')
            text=d['sources'][h]['text'];refs=body.get('references',code['references'] if code else [])
            status=body.get('status','modified')
            if status not in ('pending','accepted','modified','rejected'):raise HTTPException(400,'审核状态无效')
            if not isinstance(refs,list) or any(not isinstance(r,dict) for r in refs):raise HTTPException(400,'引用格式无效')
            checked=[]
            for ref in refs:
                a,b=ref.get('start'),ref.get('end');q=ref.get('quote')
                valid=type(a) is int and type(b) is int and 0<=a<b<=len(text) and text[a:b]==q
                if not valid and not (ref.get('validation')=='needs_resolution' and status in ('pending','rejected')):raise HTTPException(400,'引用与原文范围不一致，请重新选择')
                checked.append({**ref,'id':ref.get('id') or uid(),'validation':'valid' if valid else 'needs_resolution'})
            name=body.get('name',code['name'] if code else '');definition=body.get('definition',code['definition'] if code else '')
            if not isinstance(name,str) or not isinstance(definition,str):raise HTTPException(400,'名称及说明必须为文字')
            name=name.strip();definition=definition.strip()
            if not name or not definition or not checked:raise HTTPException(400,'名称、说明和引用不能为空')
            if not code:
                code={'id':uid(),'source_id':tid,'source_hash':h,'origin':'manual','run_id':None,'reason':'研究者手动编码','revision':-1,'created_at':now()};d['codes'].append(code)
            code.update(name=name,definition=definition,references=checked,status=status,updated_at=now(),revision=code['revision']+1)
            code.setdefault('ai_original',{'name':name,'definition':definition,'references':checked} if code['origin']=='ai' else None)
            save(pid,tid,d);return d
