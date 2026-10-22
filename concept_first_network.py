"""Concepts first; evidence-window relationship extraction, never all-node pairs."""
import hashlib
import json
import re
from backend_network import plan_units
from network_batches import IncompleteOutput, InvalidOutput
from interview_facts import ordered_parallel
from raw_theme_source import original_evidence
from node_quality import preview_quality_report
import evidence_nodes

CONCEPT_PROMPT = evidence_nodes.CODE_PROMPT

RELATION_PROMPT = '''节点已完成概念提取和粒度复核，本阶段只能从输入真实原文找联系，并匹配每个window附带的已有节点。不得新增、改名或拆分节点，不遍历全部节点组合，不要求每个节点连线。
先读连续原文，再判断原文明示的联系是否能对应两个给定节点的定义。两端各有证据、同段出现、同维度或语义相近均不足以连线。找不到可靠联系则relations为空。
区分提问与回答：提问者的假设、诱导或设问不是受访者结论；需要回答明确认可。说话人编号不等于固定访谈角色，仅依原文问答内容判断。指代不明、条件缺失时不得强行确定联系和方向。不根据空间位置、分群、常识推断因果。
方向不要求严格因果证明，但必须由原文明确表达。source到target须符合原文的作用或指向；理由、目的不要倒置为因果。不明确时保留无方向联系，仅共同出现则不连线。保留否定、可能性、范围和条件。节点mode记录表述性质：reported是受访者报告，concern是担忧，proposal是设想，claim是判断或评价；不得将后几类升级成已发生事实，unspecified时从原文判断。
每个window_id返回一次，只允许该window.nodes中的节点ID，端点必须不同。label最多12字，description说明联系及条件，direction_reason简要解释方向依据。window_id仅路由；证据由后端绑定完整连续窗口，不返回证据编号、索引或引文。不同window之间不得拼接推断。
只返回JSON：{"windows":[{"window_id":"w0","relations":[{"source":"n0","target":"n1","label":"联系名称","description":"联系与条件","directed":false,"direction_reason":"方向依据或不明确原因"}],"reason":""}]}'''

def concept_first_signature():
    return hashlib.sha256((evidence_nodes.signature()+RELATION_PROMPT).encode()).hexdigest()

def valid_concept(item):
    if not isinstance(item, dict): return False
    label, definition = item.get('label'), item.get('definition')
    return (isinstance(label, str) and 0 < len(label.strip()) <= 12
            and not re.fullmatch(r'[\d\s.,，。%％年月日元万亿+-]+', label)
            and isinstance(definition, str) and bool(definition.strip()) and len(definition) <= 300)

def relation_windows(units, nodes, transcript_path=None):
    windows, seen, transcripts = [], {}, {}
    for unit in units:
        source = unit['source']; pid = source['project_id']
        if pid not in transcripts:
            path = transcript_path(pid) if transcript_path else None
            text = path.read_text(encoding='utf-8-sig') if path else None
            transcripts[pid] = (text, original_evidence(text) if text is not None else [])
        text, rows = transcripts[pid]
        refs = [source]; start, end = source.get('start'), source.get('end')
        if text is not None:
            if source.get('transcript_hash') != hashlib.sha256(text.encode()).hexdigest() or type(start) is not int or type(end) is not int or text[start:end] != source['quote']:
                raise InvalidOutput('原文已变化，无法构建连续关系窗口，请更新主题分析')
            matches = [i for i, row in enumerate(rows) if row['start'] <= start and row['end'] >= end]
            if matches:
                index = matches[0]
                first, last = index, index
                # One adjacent turn on either side; read exact intervening original text.
                for neighbour in (index-1, index+1):
                    if 0 <= neighbour < len(rows):
                        lo, hi = min(first, neighbour), max(last, neighbour)
                        if rows[hi]['end']-rows[lo]['start'] <= 3600:
                            first, last = lo, hi
                start, end = rows[first]['start'], rows[last]['end']
                refs = [{**source, 'start': start, 'end': end, 'quote': text[start:end], 'context_numbers': [r['number'] for r in rows[first:last+1]], 'binding': 'backend_continuous_window'}]
        key = json.dumps([pid, start, end, refs[0]['quote']], ensure_ascii=False)
        if key in seen: continue
        related_units = [u['unit_id'] for u in units if u['source']['project_id'] == pid and
                         (u['unit_id'] == unit['unit_id'] or type(start) is int and type(end) is int and
                          type(u['source'].get('start')) is int and type(u['source'].get('end')) is int and
                          u['source']['start'] < end and u['source']['end'] > start)]
        scoped = [n for n in nodes if set(n['evidence_unit_ids']).intersection(related_units)]
        if len(scoped) < 2: continue
        window = {'window_id': f'w{len(windows)}', 'original_text': refs[0]['quote'],
                  'nodes': [{'id': n['id'], 'label': n['label'], 'definition': n['definition'],
                             'mode':n.get('coding_rule',{}).get('mode','unspecified')} for n in scoped],
                  'sources': refs, 'unit_ids': related_units}
        seen[key] = window; windows.append(window)
    return windows

def extract_relations(run, client, model, windows, theme):
    def payload(items):
        return {'theme': theme, 'windows': [{k: w[k] for k in ('window_id', 'original_text', 'nodes')} for w in items]}
    batches, current = [], []
    for window in windows:
        if len(json.dumps(payload([window]), ensure_ascii=False)) > 24000:
            raise InvalidOutput('单个关系原文窗口及相关节点过大，成功批次已保留，请缩小分析范围')
        if current and (len(current) >= 4 or len(json.dumps(payload(current+[window]), ensure_ascii=False)) > 24000):
            batches.append(current); current = []
        current.append(window)
    if current: batches.append(current)
    def execute(task):
        i, items = task
        def process(rows, label):
            expected = {w['window_id']: {n['id'] for n in w['nodes']} for w in rows}
            def validate(raw):
                if not isinstance(raw, dict) or not isinstance(raw.get('windows'), list): raise ValueError('缺少关系窗口结果')
                identifiers = [w.get('window_id') for w in raw['windows'] if isinstance(w, dict)]
                if len(identifiers) != len(expected) or set(identifiers) != set(expected): raise ValueError('关系窗口遗漏或重复')
                for w in raw['windows']:
                    if not isinstance(w.get('relations'), list): raise ValueError('缺少关系列表')
                    for edge in w['relations']:
                        if not isinstance(edge, dict) or edge.get('source') not in expected[w['window_id']] or edge.get('target') not in expected[w['window_id']] or edge['source'] == edge['target'] or type(edge.get('directed')) is not bool:
                            raise ValueError('关系端点超出本原文窗口或方向字段无效')
                        if any(not isinstance(edge.get(k), str) or not edge[k].strip() for k in ('label', 'description', 'direction_reason')) or len(edge['label']) > 12:
                            raise ValueError('关系说明或方向依据缺失')
            try: raw = run.call(client, model, RELATION_PROMPT, payload(rows), label, validate)
            except IncompleteOutput:
                if len(rows) < 2: raise
                mid = len(rows)//2
                return process(rows[:mid], label+'a') + process(rows[mid:], label+'b')
            return [(label, raw)]
        return process(items, f'relation-window-{i}')
    results = ordered_parallel(execute, list(enumerate(batches)))
    lookup = {w['window_id']: w for w in windows}; candidates = []
    for pieces in results:
        for _, raw in pieces:
            for window in raw['windows']:
                for edge in window['relations']:
                    candidates.append({**{k: edge[k] for k in ('source','target','label','description','directed','direction_reason')},
                                       'candidate_id': f'c{len(candidates)}', 'source_options': [edge['source']], 'target_options': [edge['target']],
                                       'window_id': window['window_id'], 'evidence': lookup[window['window_id']]['sources']})
    return candidates, results

def build_concept_first_network(run, client, model, findings, facts, theme, transcript_path=None, nodes_only=False):
    units, _ = plan_units(facts); lookup = {u['unit_id']: u for u in units}
    context = {n['id']: n for n in findings}
    groups, plan, concepts, extractions, units = evidence_nodes.generate(run,client,model,units,theme,transcript_path)
    nodes, mapped_facts, mapping = [], {}, {}
    for group in groups:
        if not valid_concept(group): raise InvalidOutput('合并后的概念名称或定义未通过准入校验')
        nid = f'n{len(nodes)}'; members = group['origins']
        # Only semantically accepted source bindings survive reconciliation.
        uids = group['unit_ids']
        fids = list(dict.fromkeys(fid for uid in uids for fid in lookup[uid]['fact_ids']))
        dimensions = list(dict.fromkeys(context[facts[fid]['node_id']].get('dimension', '') for fid in fids))
        for cid in members: mapping.setdefault(cid, []).append(nid)
        node_facts = []
        for fid in fids:
            mapped_id = nid+':'+fid; node_facts.append(mapped_id)
            mapped_facts[mapped_id] = {**facts[fid], 'id': mapped_id, 'node_id': nid,
                                      'sources': [lookup[uid]['source'] for uid in uids if fid in lookup[uid]['fact_ids']]}
        nodes.append({'id': nid, 'label': group['label'], 'definition': group['definition'], 'dimension': dimensions[0] if len(dimensions)==1 else '',
                      'dimensions': dimensions, 'facts': node_facts, 'source_fact_ids': fids, 'sources': [lookup[uid]['source'] for uid in uids], 'evidence_unit_ids': uids,
                      'quality_status': 'automatic_gates_passed', 'relevance': group['relevance'],
                      'coding_rule': {k:group[k] for k in ('include','exclude','mode')},
                      'gates_passed': group['gates_passed'], 'review_reason': group['reason']})
    if not nodes: raise InvalidOutput('粒度复核未保留可靠概念，不保存空图谱')
    quality_report = preview_quality_report(nodes)
    if quality_report['blockers'] and not nodes_only:
        raise InvalidOutput('节点仍有重复名称或关系式标题，请先生成节点预览并修订；未启动连线提取')
    windows = [] if nodes_only else relation_windows(units, nodes, transcript_path)
    candidates, relations = ([], []) if nodes_only else extract_relations(run, client, model, windows, theme)
    return {'nodes': nodes, 'facts': mapped_facts, 'candidates': candidates, 'rejected': [], 'quality_report': quality_report,
            'audit': {'pipeline': evidence_nodes.VERSION, 'nodes_only': nodes_only,
                      'prompts': {'scope':evidence_nodes.SCOPE_PROMPT,'concept': evidence_nodes.CODE_PROMPT, 'granularity': evidence_nodes.MERGE_PROMPT, 'residual_synonyms':evidence_nodes.DUPLICATE_PROMPT, 'grounding': evidence_nodes.VERIFY_PROMPT, 'boundary_repair':evidence_nodes.REPAIR_PROMPT, 'relation': RELATION_PROMPT},
                      'units': units, 'extractions': extractions, 'candidate_count': len(concepts), 'candidate_index_map': list(concepts),
                      'node_review': groups, 'review_plan': plan, 'mapping': mapping,
                      'relation_windows': windows, 'relation_extractions': relations, 'all_pairs_enumerated': False}}
