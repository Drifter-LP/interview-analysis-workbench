"""Three automatic gates: relevance, concepts, then source support. No edge calls."""
import hashlib
import json
import re
from interview_facts import ordered_parallel
from network_batches import IncompleteOutput, InvalidOutput
from node_quality import quality_issue, exact_deduplicate
from raw_theme_source import original_evidence

QUALITY_VERSION = 'three-gates-v1-compact-20261006'
GATE_PROMPT = '''你是中文质性访谈概念复核助手。依据研究问题和原文，完成两个顺序关卡，不生成连线。
关卡1相关性：只保留direct（原文明确讨论研究问题涉及的制度、机制、变化或应对）和background（原文明示参与上述过程且不可缺少的既有条件）。共同出现、一般医疗现象、常识上可能相关都不够。无关进drop，上下文不足进check，不进入节点集。DIP问题不要求每段写DIP，可以依据连续问答的明确指代，但不得把一般收入低、缺药、转诊自动归因于DIP。不能把所有基层问题装进背景类。主观说法保留归属，不当作客观定论。
关卡2概念：通过关卡1后，归纳对象明确的一个行动、约束、状态或判断，不是每条事实换短标题。原因、目的、后果交给连线，案例、数字、次数、金额、百分比留在原文；名称不能含数字或百分比。事实中的复合关系可拆为原文支持的独立概念，但拆分不确认联系。不同时输出宽泛父类和重复具体子类。
同一行动或状态仅因材料、原因、频率、金额不同，不另建节点。真同义且边界一致才合并；收入下降不等于亏损，担忧不等于实际发生，外部限制不等于主动精简，医院扣款不等于医生扣薪。不得按关键词强并。名称尽量8字最多12字；definition最多100字，只写概念的对象含义、纳入/排除边界和必要条件，不复述因果，不添加原文没有的内容。保留真独特概念，不设数量目标。
依据unit.original_text核对支持，context_text只用于真实问答背景及相关性，不得用其他单元补本段缺失内容。一个候选可拆到多个节点，但必须有原文支持。每个输入候选整数id必须进入nodes成员，或drop，或check，不能多类别同时归属，不能遗漏或编造。nodes的来源unit_id必须属于成员候选已有来源，不能自动继承全部来源，只列支持最终定义且相关性明确的来源；下一关会独立复查。
输出紧凑JSON，不复述引文、不返回位置或连线：
{"nodes":[["名称","定义","direct或background",[成员候选整数id],[支持来源unit_id]]],"drop":[[候选id,"简短原因"]],"check":[[候选id,"疑点"]]}。
不能返回groups或字段对象替代上述数组。节点保留理由不要冗长输出，合并与拆分通过成员映射记录。没有合格节点可nodes为空。'''

GLOBAL_PROMPT = '''复核已经初步通过相关性关卡的概念目录，统一全局粒度。输入概括只用于提出合并方案，来源相关性和定义支持仍将逐段独立核对。本阶段没有引文，不得补充原文内容或推断关系。
不是给每条候选换短标题。找出核心行动/约束/状态/判断相同的真同义项，合为一个概念。同一行动的不同原因、目的、病例、金额或频率通常是证据细节，不形成多个节点。保留实际不同对象、不同层次、担忧与发生、限制与主动行动的区别，不为压数量强并。背景不能升为direct，不能以常识把不确定内容变成已相关。定义不得是A导致B或原因目的结果串联。疑问进check，明显无关/空泛/案例/关系句进drop。
名称尽量8字最多12字，不含数字或百分比；定义最多100字，单一含义、边界清楚，不含新增内容。目录不能有重复名称；真同义合并，异义须明确命名。输入id全部有去向，不遗漏。来源unit_id只能从成员候选来源中选择。不得生成关系或证据，不设节点数量目标。
只返回JSON：{"nodes":[["名称","定义","direct或background",[成员输入整数id],[来源unit_id]]],"drop":[[输入id,"原因"]],"check":[[输入id,"疑点"]]}。'''

SUPPORT_PROMPT = '''独立执行关卡3：逐段核对最终节点的原文支持及研究问题相关性，不参考生成者是否认为合格，不改名、不新增节点或联系。
每个unit附带original_text（待绑定的原文）及context_text（真实相邻问答）。original_text必须直接支持节点名称、定义的全部实质内容和必要条件；context_text可确认问答指代和研究问题相关性，但不能替代original_text去支持它没讲的概念。不能拼接不同材料推断。
相关性必须是direct或background。背景必须在原文明示参与研究问题中的具体过程，一般基层问题不够。没有可靠联系或指代不明返回check；不支持、越界、仅提问者未获认可的假设、担忧写成已发生、无关则reject。受访者的判断、评价和指控不是已核实的事实。无明确DIP字样不自动reject，应检查真实连续问答。保留否定和条件。
节点含两件事的关系、宽泛父类、单个病例、数字频率细节、定义只有部分获支持，也reject。只有原文支持且相关性类别成立才keep。不自动继承候选来源。
每个输入unit_id返回一次，每个附带node_id返回一次。不返回引文、位置或证据编号，后端按输入路由绑定来源。
只返回紧凑JSON：{"units":[["unit_id",[["node_id","keep或reject或check","简短理由"]]]]}。'''


def numeric_name(label):
    # Unicode digits include full-width forms; Chinese percent and quantifiers too.
    return bool(isinstance(label, str) and re.search(
        r'\d|[%％﹪]|百分之|[零〇一二三四五六七八九十百千万亿两壹贰叁肆伍陆柒捌玖拾佰仟]+(?:岁|年|月|天|次|元|成|级|个|项|种|期)|第[零〇一二三四五六七八九十百]+', label))


def validate_gate(raw, records):
    if not isinstance(raw, dict) or any(not isinstance(raw.get(k), list) for k in ('nodes','drop','check')):
        raise ValueError('必须返回nodes/drop/check紧凑列表')
    kept, dropped, pending = set(), set(), set()
    for row in raw['nodes']:
        if not isinstance(row,list) or len(row)!=5:
            raise ValueError('nodes须为[名称,定义,相关性,候选id列表,来源id列表]')
        name, definition, relevance, members, sources = row
        if not isinstance(name,str) or not name.strip() or not isinstance(definition,str) or not definition.strip() or relevance not in ('direct','background'):
            raise ValueError('节点字段或相关性无效')
        if not isinstance(members,list) or not members or len(members)!=len(set(members)) or any(type(i) is not int or not 0<=i<len(records) for i in members):
            raise ValueError('候选路由编号无效')
        allowed={uid for i in members for uid in records[i]['unit_ids']}
        if relevance=='direct' and all(records[i].get('relevance')=='background' for i in members):
            raise ValueError('全局概念合并不能将仅背景来源升级为直接相关')
        if not isinstance(sources,list) or not sources or any(not isinstance(s,str) or s not in allowed for s in sources) or len(sources)!=len(set(sources)):
            raise ValueError('来源必须属于本节点成员候选，不允许外来或重复绑定')
        kept.update(members)
    for key, dest in (('drop',dropped),('check',pending)):
        for row in raw[key]:
            if not isinstance(row,list) or len(row)!=2 or type(row[0]) is not int or not 0<=row[0]<len(records) or row[0] in dest or not isinstance(row[1],str) or not row[1].strip():
                raise ValueError('排除或待核对项无效')
            dest.add(row[0])
    if kept & dropped or kept & pending or dropped & pending or kept|dropped|pending != set(range(len(records))):
        raise ValueError('候选去向遗漏或冲突')


def enrich_units(units, transcript_path):
    if not transcript_path:
        return units
    texts={}; enriched=[]
    for unit in units:
        source=unit['source'];pid=source['project_id']
        if pid not in texts:
            text=transcript_path(pid).read_text(encoding='utf-8-sig')
            texts[pid]=(text, original_evidence(text))
        text, rows=texts[pid];start,end=source.get('start'),source.get('end')
        if source.get('transcript_hash')!=hashlib.sha256(text.encode()).hexdigest() or type(start) is not int or type(end) is not int or text[start:end]!=source['quote']:
            raise InvalidOutput('原文已变化，不能复用节点证据')
        match=next((i for i,r in enumerate(rows) if r['start']<=start and r['end']>=end),None)
        lo,hi=start,end
        if match is not None:
            first,last=max(0,match-2),min(len(rows)-1,match+1)
            if rows[last]['end']-rows[first]['start']<=3600:
                lo,hi=rows[first]['start'],rows[last]['end']
        enriched.append({**unit,'context_text':text[lo:hi], 'context_start':lo,'context_end':hi})
    return enriched


def review_quality(run, client, model, concepts, units, theme, transcript_path=None):
    units=enrich_units(units,transcript_path);unit_map={u['unit_id']:u for u in units}
    records=[{**c,'origins':[cid]} for cid,c in concepts.items()]
    stages=[]; dropped={}; pending={}; filtered=[]
    def drop_numeric(rows):
        out=[]
        for r in rows:
            if numeric_name(r['label']):
                reason='名称含数字或百分比，程序自动排除'
                for cid in r['origins']:dropped[cid]=reason
                filtered.append({'label':r['label'],'origins':r['origins'],'reason':reason})
            else:out.append(r)
        return out
    records=drop_numeric(records)
    def payload(rows, originals):
        data={'theme':theme,'concepts':[{'id':i,'label':r['label'],'definition':r['definition'],'unit_ids':r['unit_ids'],
                                      'relevance':r.get('relevance','unreviewed')} for i,r in enumerate(rows)]}
        if originals:
            uids=list(dict.fromkeys(uid for r in rows for uid in r['unit_ids']))
            data['units']=[{'unit_id':uid,'original_text':unit_map[uid]['source']['quote'],
                            'context_text':unit_map[uid].get('context_text',unit_map[uid]['source']['quote'])} for uid in uids]
        return data
    def process(rows,label,originals):
        prompt=GATE_PROMPT if originals else GLOBAL_PROMPT
        try:
            raw=run.call(client,model,prompt,payload(rows,originals),label,lambda raw:validate_gate(raw,rows),max_tokens=9000,cache_incomplete=False)
        except IncompleteOutput:
            if len(rows)<2:raise
            mid=len(rows)//2
            return process(rows[:mid],label+'a',originals)+process(rows[mid:],label+'b',originals)
        stages.append({'label':label,'input_count':len(rows),'result':raw})
        out=[]
        for name,definition,relevance,members,sources in raw['nodes']:
            origins=list(dict.fromkeys(cid for i in members for cid in rows[i]['origins']))
            issue=quality_issue(name,definition)
            if issue:
                for cid in origins:pending[cid]=issue
                continue
            out.append({'label':name.strip(),'definition':definition.strip(),'relevance':relevance,'origins':origins,
                        'unit_ids':sources,'reason':'通过相关性与概念关卡'})
        for key, dest in (('drop',dropped),('check',pending)):
            for index,reason in raw[key]:
                for cid in rows[index]['origins']:dest[cid]=reason
        return drop_numeric(out)
    batches,current=[],[]
    for r in records:
        if current and (len(current)>=40 or len(json.dumps(payload(current+[r],True),ensure_ascii=False))>24000):
            batches.append(current);current=[]
        current.append(r)
        if len(json.dumps(payload(current,True),ensure_ascii=False))>28000:
            raise InvalidOutput('单个候选及原文上下文超过预算')
    if current:batches.append(current)
    records=[r for result in ordered_parallel(lambda task:process(task[1],f'gate12-{task[0]}',True),list(enumerate(batches))) for r in result]
    if records:
        if len(json.dumps(payload(records,False),ensure_ascii=False))>48000:
            raise InvalidOutput('全局概念目录过大，未跳过全局粒度关卡')
        records=process(records,'gate12-global',False)
        if any(s['label'].startswith('gate12-global') and s['label']!='gate12-global' for s in stages):
            raise InvalidOutput('全局概念复核被拆批，未将局部结果冒充完整全局关卡')
    # Identity-only dedup; no fuzzy semantic merging by code.
    unique={}
    for r in records:
        key=(r['label'],r['definition'],r['relevance'])
        if key in unique:
            previous=unique[key]; previous['origins']=list(dict.fromkeys(previous['origins']+r['origins']))
            previous['unit_ids']=list(dict.fromkeys(previous['unit_ids']+r['unit_ids']))
        else:unique[key]=r
    records=list(unique.values());names={}
    for r in records:names[r['label']]=names.get(r['label'],0)+1
    accepted_records=[]
    for r in records:
        if names[r['label']]>1:
            for cid in r['origins']:pending[cid]='重复名称且定义不同，需明确含义，暂不进入主图'
        else:accepted_records.append(r)
    records=accepted_records
    for i,r in enumerate(records):
        # Stable routing means unchanged nodes keep reusable grounding checkpoints.
        r['id']='q'+hashlib.sha256(json.dumps([r['label'],r['definition'],r['relevance']],ensure_ascii=False).encode()).hexdigest()[:16]
        if not r['definition'].startswith(('受访者','原文')):r['definition']='受访者表述的'+r['definition']
    tasks=[];current=[]
    for unit in units:
        scoped=[{'node_id':r['id'],'label':r['label'],'definition':r['definition'],'relevance':r['relevance']} for r in records if unit['unit_id'] in r['unit_ids']]
        if not scoped:continue
        row={'unit_id':unit['unit_id'],'original_text':unit['source']['quote'],
             'context_text':unit.get('context_text',unit['source']['quote']),'nodes':scoped}
        if current and (len(current)>=8 or len(json.dumps(current+[row],ensure_ascii=False))>24000):tasks.append(current);current=[]
        current.append(row)
        if len(json.dumps(current,ensure_ascii=False))>28000:raise InvalidOutput('原文支持核对单元超过预算')
    if current:tasks.append(current)
    def ground(task):
        index,rows=task
        def call(part,label):
            expected={r['unit_id']:{n['node_id'] for n in r['nodes']} for r in part}
            def validate(raw):
                if not isinstance(raw,dict) or not isinstance(raw.get('units'),list):raise ValueError('缺少units核对结果')
                seen=set()
                for row in raw['units']:
                    if not isinstance(row,list) or len(row)!=2 or row[0] not in expected or row[0] in seen or not isinstance(row[1],list):raise ValueError('核对unit路由无效')
                    seen.add(row[0]);nids=[]
                    for check in row[1]:
                        if not isinstance(check,list) or len(check)!=3 or check[0] not in expected[row[0]] or check[1] not in ('keep','reject','check') or not isinstance(check[2],str) or not check[2].strip():raise ValueError('节点核对格式无效')
                        nids.append(check[0])
                    if len(nids)!=len(set(nids)) or set(nids)!=expected[row[0]]:raise ValueError('节点核对遗漏或重复')
                if seen!=set(expected):raise ValueError('原文核对遗漏')
            try:raw=run.call(client,model,SUPPORT_PROMPT,{'theme':theme,'units':part},label,validate,max_tokens=6000)
            except IncompleteOutput:
                if len(part)<2:raise
                mid=len(part)//2;return call(part[:mid],label+'a')+call(part[mid:],label+'b')
            return raw['units']
        return call(rows,f'gate3-{index}')
    checks=[r for result in ordered_parallel(ground,list(enumerate(tasks))) for r in result]
    approved={r['id']:[] for r in records};questionable=set()
    for uid,decisions in checks:
        for nid,decision,reason in decisions:
            if decision=='keep':approved[nid].append(uid)
            elif decision=='check':questionable.add(nid)
    accepted=[]
    for r in records:
        if approved[r['id']]:accepted.append({**r,'unit_ids':list(dict.fromkeys(approved[r['id']])),'gates_passed':[1,2,3]})
        else:
            dest=pending if r['id'] in questionable else dropped
            for cid in r['origins']:dest[cid]='原文支持或研究问题相关性未通过第三关'
    retained={cid for r in accepted for cid in r['origins']}
    # A split candidate may have an accepted child and an excluded child; preserve events separately.
    audit={'version':QUALITY_VERSION,'catalog_stages':stages,'grounding_checks':checks,'full_global_review':True,
           'candidate_count':len(concepts),'proposal_count':len(records),'accepted_count':len(accepted),
           'numeric_filtered':filtered,'discarded':[{'concept_id':cid,'reason':dropped.get(cid,'候选未保留')} for cid in concepts if cid not in retained and cid not in pending],
           'pending':[{'concept_id':cid,'reason':reason} for cid,reason in pending.items() if cid not in retained],
           'source_contexts':[{k:u[k] for k in ('unit_id','context_start','context_end','context_text') if k in u} for u in units]}
    if not accepted:raise InvalidOutput('没有通过三个关卡的节点，未生成连线；复核批次及排除理由已保留')
    return accepted,audit
