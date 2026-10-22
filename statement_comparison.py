"""Compare source-bound statements, never renumber model-generated citations."""
import time

PLAN = '''根据研究主题、已有维度及具体表述，提出值得跨访谈比较的具体问题。不能只是将维度改成问句，不预设因果或负面结论。相近问题合并，不强制每个维度都有问题。只返回JSON {"questions":[{"id":"Q01","dimension":"已有维度原名","question":"具体可比问题"}]}。'''
COMPARE = '''围绕给定问题，依据具体表述及附带原文逐篇对齐回答，再归纳共性与差异。summary仅为线索，以原文为准；保留时间、条件、说话人和不确定性，不将提问当成受访者观点。
每个问题必须包含全部材料的回答。answered需原文支持；当前输入未找到回答用not_found（不等于全文未讨论）；含义不清用uncertain。不得补充事实、因果或猜测。
每条回答仅返回本材料有效statement_ids，不生成原文编号。共性至少两份有证据回答表达同一含义。差异只能是对同一具体问题的实质不同回答，不同侧面、例子、未找到均不算差异。无明确差异则返回空数组。
输出JSON {"aspects":[{"question_id":"Q01","name":"具体比较发现","answers":[{"project_id":"材料ID","status":"answered|not_found|uncertain","text":"回答概括","statement_ids":["S001"]}],"common":[{"text":"共性","project_ids":["材料ID1","材料ID2"]}],"differences":[{"question":"同一具体问题","variants":[{"project_id":"材料ID1","text":"不同回答","statement_ids":["S001"]},{"project_id":"材料ID2","text":"不同回答","statement_ids":["S002"]}]}]}]}。'''

def prepare(analysis):
    rows=[];seen=set()
    materials={m['project_id']:m['name'] for m in analysis.get('materials',[])}
    for d in analysis.get('dimensions',[]):
        for finding in d.get('findings',[]):
            for fact in finding.get('facts',[]):
                sources=[s for s in fact.get('sources',[]) if s.get('source_type')=='transcript' and s.get('quote') and s.get('project_id')==fact.get('project_id')]
                identity=(fact.get('project_id'),fact.get('text'),tuple((s.get('start'),s.get('end'),s['quote']) for s in sources))
                if not sources or identity in seen:continue
                seen.add(identity)
                rows.append({'id':f'S{len(rows)+1:03d}','project_id':fact['project_id'],'summary':fact['text'],'sources':sources})
    if not rows:raise ValueError('当前主题结果没有可追溯原文的具体表述，请先生成主题研究')
    return materials,rows

def generate(analysis,call):
    materials,rows=prepare(analysis);lookup={r['id']:r for r in rows}
    dims=[d['name'] for d in analysis.get('dimensions',[])]
    plan=call(PLAN,{'theme':analysis['theme'],'dimensions':dims,'statements':[{k:v for k,v in r.items() if k!='sources'} for r in rows]})
    questions=plan.get('questions',[])
    if not questions or any(q.get('dimension') not in dims or not q.get('question') for q in questions) or len({q['id'] for q in questions})!=len(questions):raise ValueError('比较问题格式无效')
    aspects=[]
    def answer(raw):
        pid=raw['project_id'];ids=raw.get('statement_ids',[]);status=raw.get('status')
        if pid not in materials or status not in ('answered','not_found','uncertain') or not isinstance(ids,list):raise ValueError('回答格式无效')
        if any(i not in lookup or lookup[i]['project_id']!=pid for i in ids):raise ValueError('回答引用了不属于本材料的表述')
        if status=='answered' and (not ids or not raw.get('text')):raise ValueError('回答缺少依据')
        sources={ (s['number'],s.get('start'),s['quote']):s for i in ids for s in lookup[i]['sources']}
        return {**raw,'material_name':materials[pid],'evidence':list(dict.fromkeys(s['number'] for s in sources.values())),'sources':list(sources.values())}
    # Small question batches avoid lengthy, truncated comparison matrices.
    for offset in range(0,len(questions),4):
        batch=questions[offset:offset+4];qmap={q['id']:q for q in batch}
        raw=call(COMPARE,{'theme':analysis['theme'],'questions':batch,'materials':[{'project_id':p,'name':n} for p,n in materials.items()],'statements':rows})
        items=raw.get('aspects',[])
        if len(items)!=len(batch) or {a.get('question_id') for a in items}!=set(qmap):raise ValueError('比较问题遗漏或重复')
        for item in items:
            answers=[answer(a) for a in item['answers']]
            if len(answers)!=len(materials) or {a['project_id'] for a in answers}!=set(materials):raise ValueError('材料回答遗漏或重复')
            supported={a['project_id'] for a in answers if a['status']=='answered'}
            common=item.get('common',[])
            if any(len(set(c.get('project_ids',[])))<2 or not set(c['project_ids'])<=supported for c in common):raise ValueError('共性引用无效')
            differences=[]
            for diff in item.get('differences',[]):
                variants=[answer({**v,'status':'answered'}) for v in diff.get('variants',[])]
                if len({v['project_id'] for v in variants})<2 or not {v['project_id'] for v in variants}<=supported:raise ValueError('差异引用无效')
                differences.append({**diff,'variants':variants})
            q=qmap[item['question_id']]
            aspects.append({**item,'question':q['question'],'dimension':q['dimension'],'answers':answers,'common':common,'differences':differences})
    return {'schema_version':3,'theme':analysis['theme'],'aspects':aspects,'materials':[{'project_id':p,'name':n} for p,n in materials.items()],
        'generated_at':time.time(),'model':'deepseek-flash','thinking':'disabled','source_mode':'theme_statements','questions':questions,
        'notice':'未找到相关表述不代表整篇访谈未讨论；本次复用当前主题结果，未重新检索全文。'}
