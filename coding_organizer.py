"""Researcher-triggered, evidence-bound coding cleanup. One atomic coding.json commit per decision."""
import copy
import hashlib
import itertools
import json
import threading
import time
import uuid
from fastapi import HTTPException
from theme_file_io import file_lock, write_json

PROMPT = '''你是质性访谈编码整理助手，不重新开放式编码，不生成理论或研究结论。
仅比较输入编码的核心含义、定义和逐字原文引用。共享关键词、话题或对象，不足以合并。
不同原因、条件、行为、结果不得仅因话题一致直接合并。包含关系不等于重复，抽象层级不同也不代表可互相替代。
检查duplicate疑似重复、boundary定义/使用边界冲突(也可单个编码内部引用异质)、granularity粒度差异。
同义不同名可以consider_merge；同名不同义应keep_independent或check_definition；包含或层级不同优先check_definition而非合并。
granularity必须明确指出一个编码更宽泛、另一个更具体。两个同级具体行为不同本身不是粒度差异，不强行提出问题。不建议建立父节点或多级理论体系，本功能只检查现有编码。
证据不足可manual_review或不提出建议，不能根据名称想象引用，不能为追求效果强行输出问题。
每个编码引用按原文位置排序后等距取最多5处，不仅取首条；超长引用可能未送入，sampling说明实际取样和遗漏。
未定位/逐字验证失败引用不作为判断证据。取样不能代表已核查所有引用。
每条建议只能使用输入中的code_ids和supporting_reference_ids，每个涉及编码至少有一条支持引文；单编码边界冲突至少两条不同ID的引文。
internal_boundary_check_allowed=false的编码严禁单独提出boundary建议，即使其一条原话提到多个方面，也不能冒充多条引用。此时可以与其他编码比较，或不提出问题。
如有validation_feedback，只修复所指出的证据/结构问题；不能虚构引用补足数量，无法提供依据的建议不应输出。
建议名称和定义仅为候选，不直接修改任何数据。审核状态只是研究者已有判断，不能自动接受、拒绝或覆盖。
reason供研究者直接阅读：写成一个连贯段落，开头用一至两句话概括主要理由（核心含义哪里重叠或不同，以及为何考虑合并、保留或检查边界），再用实际引文展开说明。使用编码名称称呼编码，不在reason中写任何编码ID、引用ID、缩写ID或数字字母标识；这些标识只放在code_ids和supporting_reference_ids字段。保留不确定性和重要差异，不为便于概括而把包含关系说成同义。
返回JSON {"suggestions":[{"id":"S1","code_ids":["已有编码ID"],"problem_type":"duplicate|boundary|granularity","action":"consider_merge|keep_independent|check_definition|manual_review","reason":"依据具体引文说明异同，保留主体和否定条件","supporting_reference_ids":["已有引用ID"],"candidate_name":"可选候选名称","candidate_definition":"可选候选定义"}]}。
无明确问题返回{"suggestions":[]}。当前输入可能是完整集合或成组配对比较；只判断本次输入，不声称已检查未提供的编码。'''


def uid(): return uuid.uuid4().hex
def stamp(): return time.time()
def fingerprint(code):
    return hashlib.sha256(json.dumps(code,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def eligible(d): return [c for c in d['codes'] if c['status']!='rejected' and not c.get('deleted_at')]


def evidence_input(code, sources):
    text=sources.get(code['source_hash'],{}).get('text','')
    valid=[]
    for r in code['references']:
        a,b=r.get('start'),r.get('end')
        if r.get('id') and r.get('validation')=='valid' and type(a) is int and type(b) is int and 0<=a<b<=len(text) and text[a:b]==r.get('quote'):valid.append(r)
    ordered=sorted(valid,key=lambda r:(r['start'],r['end'],r['id']))
    indexes=sorted({round(i*(len(ordered)-1)/4) for i in range(5)}) if len(ordered)>5 else list(range(len(ordered)))
    sampled=[ordered[i] for i in indexes]
    sent=[{'id':r['id'],'quote':r['quote']} for r in sampled if len(r['quote'])<=4000]
    return {'id':code['id'],'name':code['name'],'definition':code['definition'],'status':code['status'],
            'reference_count':len(code['references']),'references':sent,'source_hash':code['source_hash'],'internal_boundary_check_allowed':len(sent)>=2,
            'sampling':{'rule':'原文位置排序，等距取最多5处；单处超过4000字不截断，未送入AI',
                        'valid_count':len(valid),'sent_count':len(sent),'unresolved_count':len(code['references'])-len(valid),
                        'omitted_long_count':len(sampled)-len(sent)}}


def plan(d):
    codes=eligible(d);inputs=[evidence_input(c,d['sources']) for c in codes]
    groups=[];group=[];size=0
    for item in inputs:
        n=len(json.dumps(item,ensure_ascii=False))
        if group and size+n>14000:groups.append(group);group=[];size=0
        group.append(item);size+=n
    if group:groups.append(group)
    # Every group pair is compared: no lexical filter can discard synonym pairs.
    tasks=[groups[0]] if len(groups)==1 else [a+b for a,b in itertools.combinations(groups,2)]
    return codes,inputs,tasks


def validate_reply(reply, inputs):
    if not isinstance(reply,dict) or not isinstance(reply.get('suggestions'),list):raise ValueError('缺少suggestions数组')
    byid={c['id']:c for c in inputs};refs={r['id'] for c in inputs for r in c['references']};out=[]
    for raw in reply['suggestions']:
        if not isinstance(raw,dict):raise ValueError('整理建议格式错误')
        ids=raw.get('code_ids');support=raw.get('supporting_reference_ids')
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids) or not set(ids)<=set(byid):raise ValueError('建议引用了未知编码ID')
        if raw.get('problem_type') not in ('duplicate','boundary','granularity') or raw.get('action') not in ('consider_merge','keep_independent','check_definition','manual_review'):raise ValueError('建议类型或处理方式无效')
        if len(ids)<2 and raw['problem_type']!='boundary':raise ValueError('重复或粒度建议至少涉及两个编码')
        if not isinstance(support,list) or any(not isinstance(i,str) for i in support) or not support or not set(support)<=refs:raise ValueError('建议引用了未知原文ID')
        allowed={r['id'] for i in ids for r in byid[i]['references']}
        if not set(support)<=allowed or any(not set(support)&{r['id'] for r in byid[i]['references']} for i in ids):raise ValueError('每个涉及编码必须有对应原文依据')
        if len(ids)==1 and len(set(support))<2:raise ValueError('内部边界问题需要至少两处引用')
        if not isinstance(raw.get('reason'),str) or not raw['reason'].strip():raise ValueError('缺少判断理由')
        if any(not isinstance(raw.get(k,''),str) for k in ('candidate_name','candidate_definition')):raise ValueError('候选名称定义必须为文本')
        out.append({k:copy.deepcopy(raw.get(k,'')) for k in ('code_ids','problem_type','action','reason','supporting_reference_ids','candidate_name','candidate_definition')})
    return out


def stale(suggestion,run,d):
    current={c['id']:c for c in d['codes']};saved={c['id']:c for c in run['snapshot']}
    return any(i not in current or fingerprint(current[i])!=fingerprint(saved[i]) for i in suggestion['code_ids'])


def merge_codes(d,run,suggestion,body):
    if stale(suggestion,run,d):raise HTTPException(409,'涉及编码已变化，旧建议失效，请重新整理')
    ids=suggestion['code_ids']
    if len(ids)<2:raise HTTPException(400,'至少需要两个编码才能合并')
    keep=body.get('keep_id');name=body.get('name');definition=body.get('definition')
    if keep not in ids or not isinstance(name,str) or not name.strip() or not isinstance(definition,str) or not definition.strip():raise HTTPException(400,'请选择保留ID并填写名称和定义')
    codes=[next(c for c in d['codes'] if c['id']==i) for i in ids]
    if len({c['source_hash'] for c in codes})!=1:raise HTTPException(409,'不同原文版本的编码不能直接合并')
    before=copy.deepcopy(codes);target=copy.deepcopy(next(c for c in codes if c['id']==keep));text=d['sources'][target['source_hash']]['text']
    refs=[];dedup={}
    for c in sorted(codes,key=lambda c:c['id']!=keep):
        for r in c['references']:
            a,b=r.get('start'),r.get('end');valid=type(a) is int and type(b) is int and 0<=a<b<=len(text) and text[a:b]==r.get('quote')
            if r.get('validation')=='valid' and not valid:raise HTTPException(409,'引用位置校验失败，未执行合并')
            item=copy.deepcopy(r);origin={'code_id':c['id'],'reference_id':r['id'],'status':c['status']}
            item.setdefault('merge_origins',[]).append(origin)
            key=(a,b,r.get('quote')) if valid else None
            if key is not None and key in dedup:dedup[key]['merge_origins'].extend(item['merge_origins'])
            else:
                if any(x['id']==item['id'] for x in refs):item['id']=uid()
                refs.append(item)
                if key is not None:dedup[key]=item
    status='pending' if any(c['status']=='pending' for c in codes) or any(r.get('validation')!='valid' for r in refs) else 'modified'
    operation={'id':uid(),'type':'merge','before_codes':before,'survivor_id':keep,'status':'applied','at':stamp()}
    target.update(name=name.strip(),definition=definition.strip(),references=refs,status=status,revision=target['revision']+1,updated_at=stamp(),
                  merge_operation_id=operation['id'],merge_review_required=status=='pending')
    operation['after_fingerprint']=fingerprint(target)
    d['codes']=[target if c['id']==keep else c for c in d['codes'] if c['id']==keep or c['id'] not in ids]
    d.setdefault('merged_codes',[]).extend(copy.deepcopy([c for c in codes if c['id']!=keep]))
    run.setdefault('operations',[]).append(operation)
    return operation


def undo_merge(d,run,operation):
    if operation['status']!='applied':raise HTTPException(409,'此合并已撤销')
    target=next((c for c in d['codes'] if c['id']==operation['survivor_id']),None)
    if not target or fingerprint(target)!=operation['after_fingerprint']:raise HTTPException(409,'合并后编码已编辑或删除，不能覆盖后续修改；请先人工核对')
    ids={c['id'] for c in operation['before_codes']};occupied={c['id'] for c in d['codes']+d.get('deleted_codes',[])}-{target['id']}
    if ids&occupied:raise HTTPException(409,'原编码ID已被使用，无法安全恢复')
    restored=copy.deepcopy(operation['before_codes'])
    for c in restored:c.update(revision=max(c['revision'],target['revision'])+1,updated_at=stamp())
    d['codes']=[c for c in d['codes'] if c['id']!=target['id']]+restored
    d['merged_codes']=[c for c in d.get('merged_codes',[]) if c['id'] not in ids]
    operation.update(status='undone',undone_at=stamp())


def register_organizer(app,location,load,save,is_coding_running,coordination_lock):
    jobs=set();mutex=threading.RLock()
    def runs(d):return d.setdefault('organization_runs',[])
    def find(d,rid):
        run=next((r for r in runs(d) if r['id']==rid),None)
        if not run:raise HTTPException(404,'整理记录不存在')
        return run
    def presentation(d):
        result=copy.deepcopy(runs(d))
        for run in result:
            if run['status']=='running' and (d['project_id'],d['source_id']) not in jobs:run.update(status='partial',error='服务已重启，可继续未完成检查')
            run['collection_changed']={c['id']:fingerprint(c) for c in eligible(d)}!={c['id']:fingerprint(c) for c in run['snapshot']}
            for suggestion in run['suggestions']:suggestion['stale']=suggestion['status'] in ('pending','skipped') and stale(suggestion,run,d)
        return {'runs':result}
    def worker(pid,tid,rid):
        p=location(pid,tid);key=''
        try:
            from indexed_theme import MODEL,BASE_URL,read_qwen_key
            from openai import OpenAI
            from theme_model_io import request_json
            key=read_qwen_key();client=OpenAI(api_key=key,base_url=BASE_URL,timeout=180,max_retries=0)
            with file_lock(p):total=len(find(load(pid,tid),rid)['tasks'])
            for i in range(total):
                with file_lock(p):
                    d=load(pid,tid);run=find(d,rid)
                    if run['tasks'][i]['status']=='completed':continue
                feedback=None
                for attempt in range(3):
                    with file_lock(p):
                        d=load(pid,tid);run=find(d,rid);task=run['tasks'][i];task['status']='running';task['attempts'].append({'at':stamp(),'status':'running'});inputs=task['inputs'];number=len(task['attempts']);save(pid,tid,d)
                    artifact=p.parent/'organization_calls'/rid/f'task-{i+1}-attempt-{number}.json'
                    try:
                        raw=request_json(client,model=MODEL,prompt=PROMPT,payload={'codes':inputs,**({'validation_feedback':feedback} if feedback else {})},budget=7000,on_response=lambda response:write_json(artifact,response))
                        with file_lock(p):
                            d=load(pid,tid);find(d,rid)['tasks'][i]['attempts'][-1]['raw_output']=raw;save(pid,tid,d)
                        suggestions=validate_reply(raw,inputs)
                        with file_lock(p):
                            d=load(pid,tid);run=find(d,rid);task=run['tasks'][i];task.update(status='completed');task['attempts'][-1].update(status='completed',ended_at=stamp());task['raw_output']=raw
                            keys={(tuple(sorted(s['code_ids'])),s['problem_type']) for s in run['suggestions']}
                            for s in suggestions:
                                k=(tuple(sorted(s['code_ids'])),s['problem_type'])
                                if k not in keys:run['suggestions'].append(s|{'id':uid(),'status':'pending','task_index':i,'decisions':[]});keys.add(k)
                            save(pid,tid,d)
                        break
                    except Exception as exc:
                        feedback=str(exc)[:500] if isinstance(exc,ValueError) else None
                        message=str(exc).replace(key,'***')[:500] if key else str(exc)[:500]
                        with file_lock(p):
                            d=load(pid,tid);task=find(d,rid)['tasks'][i];task['status']='failed';task['attempts'][-1].update(status='failed',error=message);save(pid,tid,d)
            with file_lock(p):
                d=load(pid,tid);run=find(d,rid);done=sum(t['status']=='completed' for t in run['tasks']);run.update(status='completed' if done==len(run['tasks']) else 'partial' if done else 'failed',ended_at=stamp());save(pid,tid,d)
        except Exception as exc:
            with file_lock(p):
                d=load(pid,tid);run=find(d,rid);run.update(status='failed',error=(str(exc).replace(key,'***') if key else str(exc))[:500],ended_at=stamp());save(pid,tid,d)
        finally:
            with mutex:jobs.discard((pid,tid))

    base='/api/research-projects/{pid}/ai-coding/{tid}/organize'
    @app.get(base)
    def get(pid,tid):
        with file_lock(location(pid,tid)):return presentation(load(pid,tid))
    @app.get(base+'/plan')
    def preview(pid,tid):
        with file_lock(location(pid,tid)):
            codes,inputs,tasks=plan(load(pid,tid))
            return {'code_count':len(codes),'task_count':len(tasks),'sampling':[{'id':c['id'],**c['sampling']} for c in inputs]}
    @app.post(base+'/run')
    def start(pid,tid,body:dict):
        from indexed_theme import read_qwen_key,MODEL
        if not read_qwen_key():raise HTTPException(400,'未配置QWEN_API_KEY')
        p=location(pid,tid)
        with coordination_lock,mutex,file_lock(p):
            if (pid,tid) in jobs or is_coding_running(pid,tid):raise HTTPException(409,'当前访谈正在编码或整理，请稍后')
            d=load(pid,tid);rid=body.get('resume_run_id')
            if rid:
                run=find(d,rid)
                if run['status']=='completed':raise HTTPException(409,'整理已完成')
                if {c['id']:fingerprint(c) for c in eligible(d)}!={c['id']:fingerprint(c) for c in run['snapshot']}:raise HTTPException(409,'编码集合已变化，请重新整理')
            else:
                codes,inputs,tasks=plan(d)
                if not codes:raise HTTPException(400,'暂无可整理编码')
                if len(tasks)>1 and body.get('confirm_task_count')!=len(tasks):raise HTTPException(409,f'需要{len(tasks)}批全组配对检查，请确认调用数量后开始')
                run={'id':uid(),'status':'running','created_at':stamp(),'model':MODEL,'snapshot':copy.deepcopy(codes),'snapshot_fingerprints':{c['id']:fingerprint(c) for c in codes},'sampling':[{'id':c['id'],**c['sampling']} for c in inputs],'coverage_policy':'全部编码输入；过大时全组两两配对，覆盖跨组编码对','tasks':[{'inputs':t,'status':'pending','attempts':[]} for t in tasks],'suggestions':[],'operations':[]};runs(d).append(run)
            run.update(status='running');run.pop('error',None);save(pid,tid,d);jobs.add((pid,tid));threading.Thread(target=worker,args=(pid,tid,run['id']),daemon=True).start()
            return {'run_id':run['id']}
    @app.post(base+'/{rid}/suggestions/{sid}')
    def decide(pid,tid,rid,sid,body:dict):
        with file_lock(location(pid,tid)):
            d=load(pid,tid);run=find(d,rid);s=next((s for s in run['suggestions'] if s['id']==sid),None)
            if not s:raise HTTPException(404,'建议不存在')
            if s['status'] in ('merged','kept'):raise HTTPException(409,'建议已处理，请刷新')
            if stale(s,run,d):raise HTTPException(409,'涉及编码已变化，建议失效，请重新整理')
            action=body.get('action')
            if action not in ('merge','keep','skip'):raise HTTPException(400,'处理方式无效')
            if action=='merge':
                if body.get('confirmed') is not True:raise HTTPException(400,'合并需要研究者明确确认')
                operation=merge_codes(d,run,s,body);s.update(status='merged',operation_id=operation['id'])
            else:s['status']='kept' if action=='keep' else 'skipped'
            s['decisions'].append({'action':action,'at':stamp(),'keep_id':body.get('keep_id'),'name':body.get('name'),'definition':body.get('definition')});save(pid,tid,d);return {'coding':d,'organization':presentation(d)}
    @app.post(base+'/{rid}/operations/{oid}/undo')
    def undo(pid,tid,rid,oid):
        with file_lock(location(pid,tid)):
            d=load(pid,tid);run=find(d,rid);op=next((o for o in run.get('operations',[]) if o['id']==oid),None)
            if not op:raise HTTPException(404,'合并记录不存在')
            undo_merge(d,run,op)
            for s in run['suggestions']:
                if s.get('operation_id')==oid:s['status']='undone';s['decisions'].append({'action':'undo','at':stamp()})
            save(pid,tid,d);return {'coding':d,'organization':presentation(d)}
    return lambda pid,tid:(pid,tid) in jobs
