"""Screen original passages before coding; preserve auditable code boundaries."""
import hashlib
import json
import re
from interview_facts import ordered_parallel
from network_batches import InvalidOutput, IncompleteOutput
from node_gates import enrich_units, numeric_name

VERSION = 'source-first-codebook-v7-boundaries-20261007'
SCOPE_PROMPT = '''先筛选研究材料范围，不生成节点。只读原文和真实相邻问答，不能用常识建立研究联系。
对每段选择direct/background/drop/check。direct须有原文明示的研究制度、实践变化或应对，或回答明确承接关于该问题的问句；background须原文明示其参与这一具体过程。一般同领域话题、仅与医保有关、整篇访谈讨论过研究问题，都不足以自动纳入。明显无关drop，语境缺失check。不要求出现研究问题关键词，明确问答指代也算依据。
每段返回[unit_id,类别,关联依据原文短片段,承接逻辑]。纳入时短片段必须逐字摘自本段或context，选取足以确认联系的问句或陈述，不能只取一个领域词。check/drop可短片段为空，但解释具体缺口。同一段中仍可能有无关内容，后续编码只使用真正相关部分。不遗漏单元。
只输出JSON：{"scope":[["u0","check","","缺少研究问题与该段内容的明确联系"]]}。'''

CODE_PROMPT = '''从已筛选原文提出小型经验编码表。范围判断只说明该段有相关内容，不表示整段每句话都相关。逐个unit处理，零个或多个节点均可，不设数量目标。
节点表示一个主体明确的行动、约束、状态或判断。先在内部拆出主体和核心动作/状态，再命名。原文同时提到多个不同动作时分别编码，不用“调整行为”“符合政策”把它们包成一项；同一动作的同义复述只编码一次。定义只解释它是什么；原因、目的、后果留给后续连线，不能重复研究问题前缀或把制度名塞进每个名称。不能把同一现象按病例、金额、频率、原因拆成多个节点。不是每句换个短标题。不要生成空泛领域或具体人名、病名、数字节点。
每项有name、definition、include、exclude、mode和anchor。mode为reported（受访者报告的实践/状态，并非外部核实）、concern（担忧）、proposal（设想意愿）、claim（评价或指控）。非reported必须在名称或定义中明确担忧/设想/评价的性质。不能将提问者的假设当回答。名称尽量8字最多12字，不含数字百分比；原文数字不影响可编码性。定义<=80字，include/exclude各<=65字，明确一个纳入标准和容易混淆的排除标准，不能用“与本概念相关”等空话。条件和否定不能丢失。
最后一列subject只写该概念的一个主体或对象，不能并列两个主体。定义只陈述这一主体的一种状态或实践，不能写原因链、制度影响、笼统评价。context仅帮助解答指代和研究背景，context中的其他陈述不能成为本unit的新节点。本段original才是节点依据。名称或定义出现“导致/引发/使得/从而”通常说明还没拆成概念。不得把两个主体收入或两种动作塞入同一概念。
后端负责证据位置，不返回引文或位置。紧凑JSON：{"units":[["u0",[["名称","单一含义定义","纳入条件","排除条件","reported","一个主体或对象"]]]]}。每个unit恰好出现一次，不生成关系。'''

MERGE_PROMPT = '''对有纳入排除边界的编码目录作对照归并，不推断原文或研究联系。输入已有概念，不额外新增事实。
每个输入id恰好分配一次。只有同一主体/行动或状态、含义和适用边界兼容的同义项合并；不同来源、原因或措辞本身不是拆分理由。个案数字佐证与概括性趋势判断不必分成两项，二者若描述同一主体层次的同一现象应统一。具体机构与同类机构的不同来源不构成两个概念；不同组织层次或不同人群不能混并。上下位、相关但不同、相反状态、担忧与实际发生、设想与实际执行不能直接合并。合并定义不得叠加只有某条来源支持的条件；不能把某来源的原因变成所有来源必需的条件。保留必要适用条件；若各项条件有实质差异，分开并说明。
每组写明确decision：singleton/synonym/uncertain。synonym至少两个成员，uncertain暂不进入图谱。不能为压数量强并，也不能把同义项留成多个换名节点。相同决策原则不等于相同动作，治疗安排、诊断选择、药品选择等对象不同不能用一个共同原则把它们合成一个节点。名称和定义不保留具体人的姓名、职位更替、某年金额等个案细节，只保留有依据的概念本身；这些细节由后端原文保留。合并名称<=12字且无数字，定义<=80字，纳入排除各<=65字。
输出JSON：{"groups":[[[成员整数id],"singleton或synonym或uncertain","名称","定义","纳入条件","排除条件","reported或concern或proposal或claim","具体同异判断理由"]],"contrasts":[[第一组下标,第二组下标,"broader或related或opposite或uncertain","容易混淆但不合并的具体区别"]]}。
contrasts只列容易混淆的组，不需要遍历所有组合；组下标指输出groups顺序。来源由后端路由，不能返回引文或新增来源。'''

VERIFY_PROMPT = '''你负责挑出编码方案的错误。输入名称及定义只是待审提议，不是事实；先寻找一个否定它的理由，再决定能否保留。
对每个节点-原文绑定分别检查4项，均只取pass/fail/uncertain：
relevance：本概念（而非本段其他话题）是否明确属于研究问题。先看local_context里最近的具体提问，再核对较长context是否明确连续承接。对话已经转到另一话题时，不能借更早出现的制度名将后来的普通现象认作该制度的应对。只说医保、医院经营或普通临床决策，不能自动推出属于某一特定支付改革。必须能够指出本概念与研究对象的明确联系，不能自己补“为了规避/由于改革”。缺乏联系时uncertain；即使含义正确，也不能放行。独立判断，忽略前序是否筛选过。
判断relevance不等于检查制度名称关键词：如果最近连续问答明确讨论与研究对象一致的具体支付机制（例如按病种规定支付额度、围绕这一额度安排检查用药），即使省略制度简称，也可通过。依据必须是实际问答中的机制及承接关系，不能只是同领域联想；不能因缺少简称而否定已经明确的承接。普通药品目录、常规急诊转诊等仍需自己的研究联系。保留研究问题涵盖的制度实践，不将“直接相关”误解为必须证明改革导致变化。
meaning：本段是否支持名称、定义和必要条件的全部实质内容；context可解答明确的指代（短回答的主体），不能补本段没有的另一事实。部分支持也fail。合并后的条件也须逐个绑定核实，例如原文只说选择低价药，不能自动补成疗效相同或同一药品；不能借另一条来源的限定放行。
modality：担忧、设想、假设、指控、否定有没有被写成已发生或客观事实。
atomic：名称和definition是否只描述一个具体且可区分的含义，是否夹带了其他概念及原因结果链。仅说“有影响/受冲击/被控制/有压力”等、对象或实际变化不明确、可以套用许多行动的宽泛评价不能作为同层经验节点，标fail；不能为了保留而猜具体机制。不要用一个宽泛上位说法覆盖几个不同的具体动作。include/exclude是编码适用边界，允许说明研究背景和不纳入的现象；不能仅因为边界说明提到两个现象就判atomic失败。原因链不应塞进名称和definition，但边界说明里的背景并不自动使概念复合。
逐项判断后给一个具体的反对理由或边界风险。证据由后端以绑定id定位，不要求重新抄写原文。不能因为同批其他原文有这个现象就通过本段；不能仅写“合理”“原文明示”“无问题”。有任何实质疑点用uncertain，不默认保留。定义有任何原因结果链或两个主体的并列状态时atomic=fail，即使原文真的有此因果。提出不同于本段的话题是meaning=fail。后端仅保留四项全部pass的绑定。
只输出JSON：{"checks":[["绑定id","pass或fail或uncertain","pass或fail或uncertain","pass或fail或uncertain","pass或fail或uncertain","具体反对理由或误读风险"]]}。全部绑定恰好一次，不重写节点、不新增关系。'''

DUPLICATE_PROMPT=MERGE_PROMPT+'''\n这是最终残留重复检查。上一轮合并不是正确答案。优先比较核心主体、动作或状态：措辞、来源和事实细节不同但含义相同的，必须归并。名称不能用不同近义词维持重复。定义必须只讲本概念是什么，剥离因果、目的及其他主体状态。所有输入必须有去向，不凭空增加信息。'''

REPAIR_PROMPT='''根据独立审查发现的具体错误修订编码，不是再批准旧版本。仅修复给定概念的定义/模态/边界，不新增另一种事实，不增加来源、不转移主体。原文是唯一依据；担忧仍为担忧，评价仍为评价。把原因目的结果从定义移除，只说明本概念含义。研究联系缺失不能靠改写制造联系，应drop。
合并概念只能取所有原文共同支持的动作及必要边界，不叠加个别来源条件。没有共同的具体动作时说明错误合并并drop，不能修成宽泛上位词。意义不明确的“控制/影响/压力”等不能通过猜测补成具体行动；明确性不足则drop。原文中的疗效、病种、金额等个别说明不能成为所有来源的必需条件，除非该条件真正限定概念本身。
每个id恰好出现一次，修订名称<=12字，定义<=80字，纳入排除各<=65字，mode只能reported/concern/proposal/claim。来源仍由后端保存，不能返回证据。
JSON：{"repaired":[["id","名称","单一概念定义","纳入条件","排除条件","mode"]],"drop":[["id","无法修复原因"]]}。'''

def atomic_issue(name,definition):
    if re.search(r'影响|相关|促使|造成',name):
        return '节点名称表达影响或关联，未说明独立概念'
    if re.search(r'导致|引发|使得|从而|进而|致使',name+' '+definition):
        return '名称或定义仍包含原因结果联系，尚未拆成独立概念'
    return ''


def context_units(units,transcript_path):
    """Use a bounded continuous Q&A window, never isolated keyword retrieval."""
    units=enrich_units(units,transcript_path)
    if not transcript_path:return units
    from raw_theme_source import original_evidence
    documents={};out=[]
    for u in units:
        s=u['source'];pid=s['project_id']
        if pid not in documents:
            content=transcript_path(pid).read_text(encoding='utf-8-sig');documents[pid]=(content,original_evidence(content))
        content,turns=documents[pid]
        index=next((i for i,r in enumerate(turns) if r['start']<=s['start'] and r['end']>=s['end']),None)
        lo,hi=s['start'],s['end']
        if index is not None:
            hi=turns[min(index+1,len(turns)-1)]['end']
            for j in range(index,max(-1,index-16),-1):
                if hi-turns[j]['start']>4200:break
                lo=turns[j]['start']
        out.append({**u,'local_context':u.get('context_text',s['quote']),'context_text':content[lo:hi],'context_start':lo,'context_end':hi})
    return out


FINAL_PROMPT = '''复核已通过原文核对的编码清单，消除同义反复和案例颗粒度过细。名称及定义仍是提议，不是研究结论。
同一主体的同一具体动作，不因重复频率、金额、年度、个别病种、实施对象案例而拆成多个节点；保留真正不同的动作、制度规则、实际状态和态度。上下位概念有相同原文含义且仅案例具体程度不同可合并，否则保留区别。不同表述性质不能直接合并，担忧不能变成已发生。不要为了减少数量吞并检查、用药、治疗、转诊等不同动作。
节点只描述独立概念，不描述影响或相关关系。空泛影响、政策差异、前后变化等没有明确独立含义者进入check。不同主体或模态无法确认同义时保留。
keep中的节点不重写。merge仅列真正需要归并的2个以上节点，合并定义只保留每条原文都能支持的共同含义，不添条件。后端会重新核对全部来源。所有整数id必须恰好出现一次。
输出紧凑JSON：{"keep":[整数id],"merge":[[[成员id],"名称","定义","纳入","排除","reported或concern或proposal或claim","理由"]],"check":[[id,"理由"]]}。名称最多12字，定义80字，纳入排除各65字。不返回原文。'''

def signature():
    return hashlib.sha256((VERSION+SCOPE_PROMPT+CODE_PROMPT+MERGE_PROMPT+DUPLICATE_PROMPT+VERIFY_PROMPT+REPAIR_PROMPT+FINAL_PROMPT).encode()).hexdigest()


def text(value, limit=500):
    return isinstance(value, str) and bool(value.strip()) and len(value)<=limit


def anchor(value, original):
    return isinstance(value,str) and 4<=len(value.strip())<=300 and value in original


def batches(rows, size=8, budget=22000):
    result=[]; current=[]
    for row in rows:
        if len(json.dumps(row,ensure_ascii=False))>budget:
            raise InvalidOutput('单个原文与编码超过预算，已保留完成批次')
        if current and (len(current)>=size or len(json.dumps(current+[row],ensure_ascii=False))>budget):
            result.append(current); current=[]
        current.append(row)
    if current:result.append(current)
    return result


def routed(raw, key, expected, width):
    if not isinstance(raw,dict) or not isinstance(raw.get(key),list):raise ValueError('缺少'+key)
    rows=raw[key]
    if any(not isinstance(r,list) or len(r)!=width or not isinstance(r[0],str) for r in rows):raise ValueError(key+'行格式无效')
    ids=[r[0] for r in rows]
    if len(ids)!=len(set(ids)) or set(ids)!=set(expected):raise ValueError(key+'路由遗漏、重复或越界')
    return rows


def screen(run,client,model,units,theme):
    payloads=[{'unit_id':u['unit_id'],'original':u['source']['quote'],
               'context':u.get('context_text',u['source']['quote'])} for u in units]
    def execute(task):
        index,rows=task; lookup={r['unit_id']:r for r in rows}
        def validate(raw):
            for uid,status,quote,reason in routed(raw,'scope',lookup,4):
                if status not in ('direct','background','drop','check') or not text(reason):raise ValueError('范围判断无效')
                if status in ('direct','background') and not anchor(quote,lookup[uid]['context']):
                    raise ValueError(f'单元{uid}的范围依据不匹配：请从该单元context连续复制4至80字，保留原标点，不拼接多句、不改写说话人、不加省略号；没有明确依据则check')
        try:
            raw=run.call(client,model,SCOPE_PROMPT,{'theme':theme,'units':rows},f'scope-{index}',validate,max_tokens=14000,reasoning_effort='high')
        except (IncompleteOutput,InvalidOutput):
            if len(rows)<2:raise
            mid=len(rows)//2
            return execute((str(index)+'a',rows[:mid]))+execute((str(index)+'b',rows[mid:]))
        return raw['scope']
    return [r for part in ordered_parallel(execute,list(enumerate(batches(payloads)))) for r in part]


def extract(run,client,model,units,theme,scope):
    decisions={r[0]:r for r in scope}
    # Pass source text only: the previous model's interpretation is not evidence.
    payloads=[{'unit_id':u['unit_id'],'original':u['source']['quote'],'context':u.get('context_text',u['source']['quote'])}
              for u in units if decisions[u['unit_id']][1] in ('direct','background')]
    def execute(task):
        index,rows=task; lookup={r['unit_id']:r for r in rows}
        def validate(raw):
            if isinstance(raw,dict) and 'relations' in raw:raise ValueError('节点阶段不能生成关系')
            for uid,codes in routed(raw,'units',lookup,2):
                if not isinstance(codes,list):raise ValueError('编码列表无效')
                for c in codes:
                    if not isinstance(c,list) or len(c)!=6 or any(not text(x,300) for x in c[:4]) or c[4] not in ('reported','concern','proposal','claim') or not text(c[5],100):raise ValueError('编码边界、模态或主体无效')
        try:
            raw=run.call(client,model,CODE_PROMPT,{'theme':theme,'units':rows},f'codebook-{index}',validate,max_tokens=18000,reasoning_effort='high')
        except (IncompleteOutput,InvalidOutput):
            if len(rows)<2:raise
            mid=len(rows)//2
            return execute((str(index)+'a',rows[:mid]))+execute((str(index)+'b',rows[mid:]))
        return raw['units']
    raw=[r for part in ordered_parallel(execute,list(enumerate(batches(payloads,6)))) for r in part]
    records=[];excluded=[]
    for uid,codes in raw:
        for name,definition,include,exclude,mode,subject in codes:
            r={'label':name,'definition':definition,'include':include,'exclude':exclude,'mode':mode,
               'unit_ids':[uid],'origins':[f'code{len(records)+len(excluded)}'],'subject':subject,'relevance':decisions[uid][1]}
            if numeric_name(name):excluded.append({**r,'reason':'名称含数字或百分比'})
            else:records.append(r)
    return records,excluded,raw


def merge(run,client,model,records,theme,prompt=MERGE_PROMPT,label='codebook-contrast'):
    catalog=[{'id':i,**{k:r[k] for k in ('label','definition','include','exclude','mode')},'subject':r.get('subject','')} for i,r in enumerate(records)]
    if len(json.dumps(catalog,ensure_ascii=False))>48000:
        raise InvalidOutput('编码目录超过一次完整对照预算；保留编码草稿，未跳过全局对照')
    def validate(raw):
        if not isinstance(raw,dict) or not isinstance(raw.get('groups'),list) or not isinstance(raw.get('contrasts'),list):raise ValueError('缺少对照归并结果')
        fields=('members','decision','name','definition','include','exclude','mode','reason')
        normalized=[]
        for g in raw['groups']:
            if isinstance(g,dict):
                if any(k not in g for k in fields):raise ValueError('归并对象缺少必要字段')
                g=[g[k] for k in fields]
            normalized.append(g)
        raw['groups']=normalized
        ids=[]
        for g in raw['groups']:
            if not isinstance(g,list) or len(g)!=8:raise ValueError('归并行格式无效')
            members,decision,name,definition,inc,exc,mode,reason=g
            if not isinstance(members,list) or not members or any(type(i) is not int or not 0<=i<len(records) for i in members):raise ValueError('归并成员越界')
            ids.extend(members)
            if decision not in ('singleton','synonym','uncertain') or decision=='singleton' and len(members)!=1 or decision=='synonym' and len(members)<2:raise ValueError('同异判定与成员数冲突')
            if any(not text(s,300) for s in (name,definition,inc,exc,reason)) or len(name)>12 or mode not in ('reported','concern','proposal','claim'):raise ValueError('归并边界缺失')
            if decision!='uncertain' and any(records[i]['mode']!=mode for i in members):raise ValueError('不同表述模态不能直接合并或升级为已发生')
        if len(ids)!=len(set(ids)) or set(ids)!=set(range(len(records))):raise ValueError('编码归并遗漏或重复')
    try:
        raw=run.call(client,model,prompt,{'theme':theme,'codes':catalog},label,validate,max_tokens=24000,reasoning_effort='high')
    except IncompleteOutput:
        # One bounded expansion retains a truly global comparison. Never present
        # separately reviewed chunks as if cross-chunk synonyms were reviewed.
        raw=run.call(client,model,prompt,{'theme':theme,'codes':catalog},label+'-extended',validate,max_tokens=48000,reasoning_effort='high')
    # Optional contrast notes never determine membership. Preserve malformed notes
    # for audit rather than failing an otherwise complete, valid partition.
    valid_notes=[]; invalid_notes=[]
    for r in raw['contrasts']:
        valid=(isinstance(r,list) and len(r)==4 and all(type(i) is int and 0<=i<len(raw['groups']) for i in r[:2])
               and r[0]!=r[1] and r[2] in ('broader','related','opposite','uncertain') and text(r[3]))
        (valid_notes if valid else invalid_notes).append(r)
    raw={**raw,'contrasts':valid_notes,'invalid_contrasts':invalid_notes}
    groups=[];pending=[]
    for index,(members,decision,name,definition,inc,exc,mode,reason) in enumerate(raw['groups']):
        r={'label':name,'definition':definition,'include':inc,'exclude':exc,'mode':mode,'reason':reason,'decision':decision,
           'origins':[o for i in members for o in records[i]['origins']],
           'unit_ids':list(dict.fromkeys(u for i in members for u in records[i]['unit_ids'])),
           'relevance':'direct' if any(records[i]['relevance']=='direct' for i in members) else 'background'}
        if decision=='uncertain' or numeric_name(name):pending.append(r)
        else:groups.append(r)
    return groups,pending,raw


def verify(run,client,model,groups,units,theme,scope):
    lookup={u['unit_id']:u for u in units}; decisions={r[0]:r for r in scope}; bindings=[]
    for i,g in enumerate(groups):
        for uid in g['unit_ids']:
            u=lookup[uid]
            bindings.append({'id':f'{i}:{uid}','unit_id':uid,'node_index':i,
                'code':{k:g[k] for k in ('label','definition','include','exclude','mode')},
                'original':u['source']['quote'],'local_context':u.get('local_context',u.get('context_text',u['source']['quote'])),
                'context':u.get('context_text',u['source']['quote'])})
    def execute(task):
        index,rows=task; expected={r['id']:r for r in rows}
        def validate(raw):
            for r in routed(raw,'checks',expected,6):
                bid,*_=r
                if any(v not in ('pass','fail','uncertain') for v in r[1:5]) or not text(r[5]):raise ValueError('缺少分项核对或反对理由')
        try:
            raw=run.call(client,model,VERIFY_PROMPT,{'theme':theme,'bindings':rows},f'challenge-{index}',validate,max_tokens=16000,reasoning_effort='high')
        except (IncompleteOutput,InvalidOutput):
            if len(rows)<2:raise
            mid=len(rows)//2
            return execute((str(index)+'a',rows[:mid]))+execute((str(index)+'b',rows[mid:]))
        checked=[]
        for original in raw['checks']:
            r=list(original); b=expected[r[0]]
            issue=atomic_issue(b['code']['label'],b['code']['definition'])
            if issue:r[4]='fail';r[5]+='；程序核对：'+issue
            checked.append(r)
        return checked
    checks=[r for part in ordered_parallel(execute,list(enumerate(batches(bindings,6)))) for r in part]
    approved={i:[] for i in range(len(groups))}
    for r in checks:
        i,uid=r[0].split(':',1)
        if all(v=='pass' for v in r[1:5]):approved[int(i)].append(uid)
    accepted=[];pending=[]
    for i,g in enumerate(groups):
        if approved[i]:
            relevance='direct' if any(decisions[uid][1]=='direct' for uid in approved[i]) else 'background'
            accepted.append({**g,'unit_ids':approved[i],'relevance':relevance,'gates_passed':[1,2,3]})
        else:
            failed=[r for r in checks if r[0].split(':',1)[0]==str(i)]
            pending.append({**g,'reason':'；'.join(dict.fromkeys(r[5] for r in failed)), 'binding_checks':failed})
    return accepted,pending,checks


def repair(run,client,model,groups,checks,units,theme):
    byunit={u['unit_id']:u for u in units};rows=[]
    for i,g in enumerate(groups):
        failures=[r for r in checks if r[0].split(':',1)[0]==str(i)]
        if not failures or any(all(v=='pass' for v in r[1:5]) for r in failures):continue
        # Missing relevance is not repaired by renaming. Keep it pending.
        if not any(r[1]=='pass' for r in failures):continue
        rows.append({'id':str(i),'code':{k:g[k] for k in ('label','definition','include','exclude','mode')},
                     'issues':[r[1:] for r in failures],
                     'originals':[{'original':byunit[uid]['source']['quote'],
                                  'local_context':byunit[uid].get('local_context','')} for uid in g['unit_ids']]})
    def execute(task):
        index,part=task;expected={r['id'] for r in part}
        def validate(raw):
            if not isinstance(raw,dict) or any(not isinstance(raw.get(k),list) for k in ('repaired','drop')):raise ValueError('缺少修订去向')
            ids=[]
            for r in raw['repaired']:
                if not isinstance(r,list) or len(r)!=6 or r[0] not in expected or any(not text(x,300) for x in r[1:5]) or len(r[1])>12 or r[5] not in ('reported','concern','proposal','claim'):raise ValueError('修订格式或路由无效')
                ids.append(r[0])
            for r in raw['drop']:
                if not isinstance(r,list) or len(r)!=2 or r[0] not in expected or not text(r[1]):raise ValueError('修订排除无效')
                ids.append(r[0])
            if len(ids)!=len(set(ids)) or set(ids)!=expected:raise ValueError('修订去向遗漏或冲突')
        return run.call(client,model,REPAIR_PROMPT,{'theme':theme,'items':part},f'boundary-repair-{index}',validate,max_tokens=16000,reasoning_effort='high')
    results=ordered_parallel(execute,list(enumerate(batches(rows,6))))
    revised=[]
    for raw in results:
        for identifier,name,definition,inc,exc,mode in raw['repaired']:
            if numeric_name(name) or atomic_issue(name,definition):continue
            revised.append({**groups[int(identifier)],'label':name,'definition':definition,'include':inc,'exclude':exc,'mode':mode})
    return revised,results


def consolidate(run,client,model,nodes,units,theme,scope):
    if len(nodes)<2:return nodes,[],{}
    catalog=[{'id':i,**{k:n[k] for k in ('label','definition','include','exclude','mode')}} for i,n in enumerate(nodes)]
    def validate(raw):
        if not isinstance(raw,dict) or any(not isinstance(raw.get(k),list) for k in ('keep','merge','check')):raise ValueError('缺少最终去向')
        ids=list(raw['keep'])
        for row in raw['merge']:
            if not isinstance(row,list) or len(row)!=7 or not isinstance(row[0],list) or len(row[0])<2:raise ValueError('最终合并格式无效')
            members,name,definition,inc,exc,mode,reason=row
            if any(type(i) is not int or not 0<=i<len(nodes) for i in members):raise ValueError('最终合并越界')
            if any(not text(s,300) for s in (name,definition,inc,exc,reason)) or len(name)>12 or numeric_name(name) or atomic_issue(name,definition):raise ValueError('最终合并概念无效')
            if any(nodes[i]['mode']!=mode for i in members):raise ValueError('最终合并改变表述性质')
            ids+=members
        for row in raw['check']:
            if not isinstance(row,list) or len(row)!=2 or not text(row[1]):raise ValueError('缺少暂缓理由')
            ids.append(row[0])
        if any(type(i) is not int or not 0<=i<len(nodes) for i in ids) or len(ids)!=len(set(ids)) or set(ids)!=set(range(len(nodes))):raise ValueError('最终去向遗漏或重复')
    raw=run.call(client,model,FINAL_PROMPT,{'theme':theme,'codes':catalog},'final-compact-review',validate,max_tokens=20000,reasoning_effort='high')
    kept=[nodes[i] for i in raw['keep']]
    pending=[{**nodes[i],'reason':reason} for i,reason in raw['check']]
    merged=[]
    for members,name,definition,inc,exc,mode,reason in raw['merge']:
        merged.append({**nodes[members[0]],'label':name,'definition':definition,'include':inc,'exclude':exc,'mode':mode,'reason':reason,
                       'origins':list(dict.fromkeys(o for i in members for o in nodes[i]['origins'])),
                       'unit_ids':list(dict.fromkeys(u for i in members for u in nodes[i]['unit_ids']))})
    if merged:
        approved,rejected,checks=verify(run,client,model,merged,units,theme,scope)
        proposed_by_origin={tuple(n['origins']):n for n in merged}
        # Consolidation must not discard a previously accepted source simply
        # because the new common definition only fits part of the members.
        approved=[n for n in approved if set(n['unit_ids'])==set(proposed_by_origin[tuple(n['origins'])]['unit_ids'])]
        approved_origins={tuple(n['origins']) for n in approved}
        kept+=approved
        for proposal,row in zip(merged,raw['merge']):
            if tuple(proposal['origins']) not in approved_origins:
                kept.extend(nodes[i] for i in row[0])
        raw['binding_checks']=checks;raw['rejected_merges']=rejected
    safe=[]
    for node in kept:
        issue=atomic_issue(node['label'],node['definition'])
        if issue:pending.append({**node,'reason':'最终程序核对：'+issue})
        else:safe.append(node)
    return safe,pending,raw


def generate(run,client,model,units,theme,transcript_path=None):
    units=context_units(units,transcript_path)
    scope=screen(run,client,model,units,theme)
    records,excluded,extractions=extract(run,client,model,units,theme,scope)
    if records:
        groups,pending,contrast=merge(run,client,model,records,theme)
        if len(groups)>1:
            groups,extra_pending,dedup=merge(run,client,model,groups,theme,DUPLICATE_PROMPT,'remaining-synonyms')
            pending+=extra_pending;contrast['residual_review']=dedup
        accepted,rejected,checks=verify(run,client,model,groups,units,theme,scope)
        revised,repairs=repair(run,client,model,groups,checks,units,theme)
        if revised:
            repaired,still_pending,rechecks=verify(run,client,model,revised,units,theme,scope)
            existing={g['label'] for g in accepted}
            for g in repaired:
                if g['label'] in existing:
                    still_pending.append({**g,'reason':'修订后与保留节点重名，暂不重复进入图谱'})
                else:accepted.append(g);existing.add(g['label'])
            passed_origins={tuple(g['origins']) for g in accepted}
            rejected=[g for g in rejected if tuple(g['origins']) not in passed_origins]
            # Keep the latest failed repair and its concrete source checks in the
            # review queue, rather than only the superseded pre-repair wording.
            latest_pending={tuple(g['origins']):g for g in still_pending}
            rejected=[latest_pending.pop(tuple(g['origins']),g) for g in rejected]
            rejected.extend(latest_pending.values())
            contrast['repair_checks']=rechecks
        contrast['repairs']=repairs
        accepted,final_pending,final_review=consolidate(run,client,model,accepted,units,theme,scope)
        pending+=final_pending;contrast['final_review']=final_review
    else:groups=[];pending=[];contrast={};accepted=[];rejected=[];checks=[]
    plan={'version':VERSION,'scope':scope,'coding_draft':records,'contrast':contrast,'grounding_checks':checks,
          'pending':pending+rejected,'numeric_filtered':excluded,'candidate_count':len(records)+len(excluded),
          'accepted_count':len(accepted),'full_global_review':bool(records),
          'notice':'自动审查草稿；原文定位正确不等于研究者认可。范围仅覆盖传入的原文单元。'}
    return accepted,plan,{r['origins'][0]:r for r in records},extractions,units
