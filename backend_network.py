"""Evidence ownership stays in the backend, not in model-generated indices."""
import hashlib
import json
from network_batches import compact_evidence, IncompleteOutput, InvalidOutput
from interview_facts import ordered_parallel

JOINT_PROMPT = '''逐个处理units。每个unit是一段独立原文及事实线索，不能跨unit推断联系，事实线索不能替代原文。提取原文支持的独立概念及其真实联系，节点表示单一状态、行动或约束，名称尽量8字、最多12字，定义清楚，不用关系句作为节点。保留有依据的孤立概念，不凑数量。共同出现不等于联系。原文方向明确才directed=true，否则false，不要求严格因果证明。证据由后端自动绑定，不返回证据编号、索引、引文、位置、supports或evidence。每个输入unit恰好返回一次，相同unit_id只负责路由结果。概念id仅在本unit有效，无概念时说明reason，无联系时relations为空。
只返回JSON：{"units":[{"unit_id":"u0","concepts":[{"id":"a0","label":"独立概念","definition":"概念边界"}],"relations":[{"source":"a0","target":"a1","label":"联系","description":"联系及条件","directed":false,"direction_reason":"方向依据"}],"reason":""}]}'''
NODE_REVIEW_PROMPT = '''依据候选原文复核概念粒度。真同义且边界相同才合并，保留相反状态与真实区别。案例通常为证据而非节点。可拆分复合候选、淘汰无依据候选，必须说明理由。每个候选进入一个或多个groups，或者discarded，不能同时两者。不新增研究联系。不返回证据编号、索引或引文，后端自动继承候选原文。拆分后每个概念必须被其原文支持，否则淘汰。名称最多12字，定义建议160字以内、理由建议80字以内，保留必要条件。
输入候选id为后端分配的从0开始的整数，不是证据索引。输出采用紧凑数组，groups每项固定为[名称,定义,[成员候选整数编号],理由]，discarded每项固定为[候选整数编号,理由]。不输出字段名、组id、候选原始长编号，不省略任何候选去向。定义和理由简洁但完整，不重复解释。
先核对准入和粒度再合并：每个节点必须有明确对象，能独立理解，只表达一种行动、约束、状态或判断。主体名称、地名、机构名、具体药名病名、孤立数字、年份、案例细节不单独充当概念；保留为证据。残缺短句不得保留，只有原文明示对象时才能补全。定义解释本概念边界，不写它与其他概念的因果或关联句。避免把宽泛领域词和具体案例混在同一层级。不把访谈者提问、未认可假设当成受访者结论。不合并实质不同主体、对象、条件或相反状态；真同义的不同措辞应统一，不仅按标题关键词判断。不能为减少数量而吞并不同概念，也不能为增加数量把一个概念拆成同义节点。
只返回JSON：{"groups":[["独立概念","边界",[0,17],"同义合并"]],"discarded":[[8,"具体案例"]]}'''

def joint_signature():
    return hashlib.sha256((JOINT_PROMPT+NODE_REVIEW_PROMPT+'bounded-review-v1-80-24000-2').encode()).hexdigest()

def bounded_review(run, client, model, concepts, units, theme):
    """Bound calls; retain original provenance through splits and staged merges."""
    original = list(concepts)
    unit_map = {u['unit_id']: u for u in units}
    records = [{**c, 'origins': [cid]} for cid, c in concepts.items()]
    stages, reasons, split_calls = [], {}, []
    def payload(rows):
        ids = list(dict.fromkeys(uid for row in rows for uid in row['unit_ids']))
        return {'theme': theme, 'concepts': [{'id': i, 'label': r['label'], 'definition': r['definition'], 'unit_ids': r['unit_ids']} for i, r in enumerate(rows)],
                'units': [{'unit_id': uid, 'original_text': unit_map[uid]['source']['quote']} for uid in ids]}
    def fits(rows):
        return len(rows) <= 80 and len(json.dumps(payload(rows), ensure_ascii=False)) <= 24000
    def partitions(rows):
        chunks, current = [], []
        for row in rows:
            if current and not fits(current + [row]):
                chunks.append(current); current = []
            current.append(row)
            if not fits(current):
                raise InvalidOutput('单个候选及原文超过合并输入预算，请缩小分析范围；成功批次已保留')
        if current: chunks.append(current)
        return chunks
    def process(rows, label):
        def validate(raw):
            expanded = expand_review(raw, list(range(len(rows))))
            assigned, discarded = set(), set()
            for group in expanded['groups']:
                if any(not isinstance(group[k], str) or not group[k].strip() for k in ('label', 'definition', 'reason')) or len(group['label']) > 12 or not group['members']:
                    raise ValueError('复核节点字段无效')
                members = [m['concept_id'] for m in group['members']]
                if len(members) != len(set(members)): raise ValueError('组内候选重复')
                assigned.update(members)
            for item in expanded['discarded']:
                if not isinstance(item['reason'], str) or not item['reason'].strip() or item['concept_id'] in discarded:
                    raise ValueError('淘汰字段无效或重复')
                discarded.add(item['concept_id'])
            if assigned & discarded or assigned | discarded != set(range(len(rows))):
                raise ValueError('复核遗漏或冲突')
        try:
            raw = run.call(client, model, NODE_REVIEW_PROMPT, payload(rows), label, validate, cache_incomplete=False, max_tokens=12000)
        except IncompleteOutput:
            if len(rows) < 2: raise
            split_calls.append(label)
            middle = len(rows)//2
            return process(rows[:middle], label+'a') + process(rows[middle:], label+'b')
        stages.append({'label': label, 'input_count': len(rows), 'result': raw})
        output = []
        for name, definition, members, reason in raw['groups']:
            output.append({'label': name, 'definition': definition,
                           'origins': list(dict.fromkeys(cid for i in members for cid in rows[i]['origins'])),
                           'unit_ids': list(dict.fromkeys(uid for i in members for uid in rows[i]['unit_ids'])), 'reason': reason})
        for index, reason in raw['discarded']:
            for cid in rows[index]['origins']: reasons[cid] = reason
        return output
    full_global = False
    # Local review, then bounded cross-batch reconciliation. No endless merge loop.
    for turn in range(3):
        if not records: break
        if fits(records):
            records = process(records, 'node-review' if turn == 0 else f'node-global-{turn}')
            full_global = not any(label.startswith('node-review' if turn == 0 else f'node-global-{turn}') for label in split_calls)
            break
        if turn == 1: records.sort(key=lambda r: (r['label'], r['definition']))
        if turn == 2:
            half = (len(records)+1)//2
            records = [r for pair in zip(records[:half], records[half:]) for r in pair] + (records[half-1:half] if len(records)%2 else [])
        records = [r for i, chunk in enumerate(partitions(records)) for r in process(chunk, f'node-stage-{turn}-{i}')]
    retained = {cid for r in records for cid in r['origins']}
    indices = {cid: i for i, cid in enumerate(original)}
    compact = {'groups': [[r['label'], r['definition'], [indices[cid] for cid in r['origins']], r['reason']] for r in records],
               'discarded': [[i, reasons.get(cid, '分阶段复核淘汰')] for i, cid in enumerate(original) if cid not in retained]}
    return compact, {'stages': stages, 'full_global_review': full_global,
                     'notice': '' if full_global else '采用有界分批及跨批核对；未穷尽所有跨批同义组合，可能保留重复概念。'}

def expand_review(result, candidate_ids):
    if not isinstance(result,dict) or any(not isinstance(result.get(k),list) for k in ('groups','discarded')):
        raise ValueError('复核列表缺失')
    def candidate(index):
        if type(index) is not int or not 0 <= index < len(candidate_ids):
            raise ValueError('候选编号必须为有效整数，不是证据索引')
        return candidate_ids[index]
    expanded={'groups':[],'discarded':[]}
    for i,row in enumerate(result['groups']):
        if not isinstance(row,list) or len(row)!=4 or not isinstance(row[2],list):
            raise ValueError('groups每项必须为[名称,定义,[候选编号],理由]')
        expanded['groups'].append({'id':f'g{i}','label':row[0],'definition':row[1],'members':[{'concept_id':candidate(index)} for index in row[2]],'reason':row[3]})
    for row in result['discarded']:
        if not isinstance(row,list) or len(row)!=2:
            raise ValueError('discarded每项必须为[候选编号,理由]')
        expanded['discarded'].append({'concept_id':candidate(row[0]),'reason':row[1]})
    return expanded

def plan_units(facts):
    catalog, _ = compact_evidence(facts)
    units=[{'unit_id':'u'+str(i),'source':entry['source'],'fact_ids':entry['fact_ids']} for i,entry in enumerate(catalog.values())]
    units.sort(key=lambda u:(u['source']['project_id'],u['source'].get('start',0),str(u['source']['number'])))
    batches,current,fids,size=[],[],set(),0
    for u in units:
        cost=len(u['source']['quote'])+sum(len(facts[fid]['text']) for fid in u['fact_ids'])+200
        if current and (current[0]['source']['project_id']!=u['source']['project_id'] or size+cost>22000 or len(fids)>=8 and not fids.intersection(u['fact_ids'])):
            batches.append(current);current,fids,size=[],set(),0
        current.append(u);fids.update(u['fact_ids']);size+=cost
    if current:batches.append(current)
    return units,batches

def build_joint_network(run,client,model,context_nodes,facts,theme):
    units,batches=plan_units(facts);lookup={u['unit_id']:u for u in units};context={n['id']:n for n in context_nodes}
    def extract(task):
        index,batch=task
        def execute(items,label):
            payload={'theme':theme,'units':[{'unit_id':u['unit_id'],'original_text':u['source']['quote'],'facts':[{'text':facts[fid]['text'],'finding':context[facts[fid]['node_id']]['label']} for fid in u['fact_ids']]} for u in items]}
            expected={u['unit_id'] for u in items}
            def validate(result):
                if not isinstance(result,dict) or not isinstance(result.get('units'),list):raise ValueError('缺少单元结果')
                output=[u.get('unit_id') for u in result['units']]
                if len(output)!=len(expected) or set(output)!=expected:raise ValueError('单元遗漏或重复')
                for u in result['units']:
                    if not isinstance(u.get('concepts'),list) or not isinstance(u.get('relations'),list):raise ValueError('概念或关系列表缺失')
                    ids=[c.get('id') for c in u['concepts']]
                    if any(not isinstance(i,str) or not i for i in ids) or len(ids)!=len(set(ids)):raise ValueError('概念编号无效')
                    for c in u['concepts']:
                        if not isinstance(c.get('label'),str) or not c['label'].strip() or len(c['label'])>12 or not c.get('definition'):raise ValueError('概念字段无效')
                    for e in u['relations']:
                        if e.get('source') not in ids or e.get('target') not in ids or e['source']==e['target'] or type(e.get('directed')) is not bool or not e.get('label') or not e.get('description'):raise ValueError('关系端点或字段无效')
                    if not ids and not u.get('reason'):raise ValueError('空单元缺少理由')
            try:result=run.call(client,model,JOINT_PROMPT,payload,label,validate)
            except IncompleteOutput:
                if len(items)<2:raise
                middle=len(items)//2
                return execute(items[:middle],label+'a')+execute(items[middle:],label+'b')
            return [(label,result)]
        return execute(batch,f'b{index}')
    extracted=ordered_parallel(extract,list(enumerate(batches)))
    concepts,relations={},[]
    for pieces in extracted:
        for label,result in pieces:
            for output in result['units']:
                uid=output['unit_id'];prefix=label+':'+uid+':'
                for c in output['concepts']:
                    cid=prefix+c['id'];concepts[cid]={'id':cid,'label':c['label'],'definition':c['definition'],'unit_ids':[uid]}
                for e in output['relations']:
                    relations.append({k:e.get(k,'') for k in ('label','description','directed','direction_reason')}|{'source':prefix+e['source'],'target':prefix+e['target'],'unit_id':uid})
    candidate_ids=list(concepts)
    def validate_review(result):
        result=expand_review(result,candidate_ids)
        if not isinstance(result,dict) or any(not isinstance(result.get(k),list) for k in ('groups','discarded')):raise ValueError('复核列表缺失')
        assigned,discarded,gids=set(),set(),set()
        for g in result['groups']:
            if not isinstance(g.get('id'),str) or g['id'] in gids or not isinstance(g.get('label'),str) or not g['label'].strip() or len(g['label'])>12 or not isinstance(g.get('definition'),str) or not g['definition'].strip() or not g.get('members') or not isinstance(g.get('reason'),str) or not g['reason'].strip():raise ValueError('复核节点无效')
            gids.add(g['id']);members=set()
            for m in g['members']:
                cid=m.get('concept_id')
                if cid not in concepts or cid in members:raise ValueError('复核成员无效')
                members.add(cid);assigned.add(cid)
        for c in result['discarded']:
            cid=c.get('concept_id')
            if cid not in concepts or cid in discarded or not c.get('reason'):raise ValueError('淘汰成员无效')
            discarded.add(cid)
        if assigned&discarded or assigned|discarded!=set(concepts):raise ValueError('复核遗漏或冲突')
    review_raw, review_plan = bounded_review(run,client,model,concepts,units,theme)
    validate_review(review_raw)
    reviewed=expand_review(review_raw,candidate_ids)
    nodes,mapping,mapped_facts=[],{},{}
    for g in reviewed['groups']:
        nid=f'n{len(nodes)}';uids=list(dict.fromkeys(uid for m in g['members'] for uid in concepts[m['concept_id']]['unit_ids']))
        for m in g['members']:mapping.setdefault(m['concept_id'],[]).append(nid)
        fids=list(dict.fromkeys(fid for uid in uids for fid in lookup[uid]['fact_ids']))
        dimensions=list(dict.fromkeys(context[facts[fid]['node_id']].get('dimension','') for fid in fids));node_facts=[]
        for fid in fids:
            newfid=nid+':'+fid;node_facts.append(newfid)
            mapped_facts[newfid]={**facts[fid],'id':newfid,'node_id':nid,'sources':[lookup[uid]['source'] for uid in uids if fid in lookup[uid]['fact_ids']]}
        nodes.append({'id':nid,'label':g['label'],'definition':g['definition'],'dimension':dimensions[0] if dimensions else '', 'dimensions':dimensions,'facts':node_facts,'source_fact_ids':fids,'sources':[lookup[uid]['source'] for uid in uids],'evidence_unit_ids':uids})
    candidates,rejected=[],[]
    for e in relations:
        left,right=mapping.get(e['source'],[]),mapping.get(e['target'],[])
        if not left or not right or len(left)==len(right)==1 and left==right:
            rejected.append({'candidate':e,'reason':'端点淘汰或合并为同一节点'});continue
        candidates.append({**e,'candidate_id':f'c{len(candidates)}','source':left[0],'target':right[0],'source_options':left,'target_options':right,'evidence':[{**lookup[e['unit_id']]['source'],'evidence_unit_id':e['unit_id'],'binding':'backend_original_unit'}]})
    return {'nodes':nodes,'facts':mapped_facts,'candidates':candidates,'rejected':rejected,'audit':{'prompts':{'joint':JOINT_PROMPT,'node_review':NODE_REVIEW_PROMPT},'evidence_binding':'backend_original_unit','units':units,'batches':[{'project_id':b[0]['source']['project_id'],'unit_ids':[u['unit_id'] for u in b]} for b in batches],'extractions':extracted,'node_review':reviewed,'node_review_compact':review_raw,'review_plan':review_plan,'candidate_index_map':candidate_ids,'mapping':mapping,'candidate_count':len(concepts)}}
