"""Concept reconciliation is a proposal; only grounded bindings become evidence."""
import json
import re
from backend_network import expand_review
from interview_facts import ordered_parallel
from network_batches import IncompleteOutput, InvalidOutput

QUALITY_VERSION = 'grounded-concepts-v2'
GRANULARITY_PROMPT = '''任务：将访谈候选描述归纳为同一中间层级的独立经验概念目录，而不是给每条描述换短标题。输入不提供旧标题，避免照搬。你只提出目录，后续会用原文核对每一个来源。
先识别每条描述的核心行动或状态，再把真正相同的核心概念归为一组。节点是概念，不是“某次做法+原因+结果+金额”的发现句。不同材料、不同原因、目的、程度、频率、百分比、金额、具体病种、具体药名、年龄实例不是另造一个节点的理由；这些细节留在原文。保留确实不同的行动对象、不同制度层次、主动行为与外部限制、主观担忧与实际发生、相反状态，不能为压缩吞并不同概念。
原因不同但实际是同一种行动，归为同一行动节点；原因本身如有独立概念价值，可单独成节点，不能再生成“原因+行动”的复合节点。目的和后果不进入节点定义。不要同时输出一种概念的宽泛父类和多个具体子类；本目录不是编码树，不把每句原话变成节点。孤立的频率、金额或程度项并入所属概念或淘汰，不单独成节点。
名称尽量8字，最多12字，明确对象，不含因果或相关关系句。definition只用一两句定义概念本身以及必要的纳入/排除边界，最多100字；不复述来源叙述的原因、目的、结果和具体案例，不写A导致B或A与B相关。表述归属保留为受访者描述，不声称是经核实的事实。
输出前自查：是否仍有同义概念各列一项、同一行动因不同原因分列、频率或数字被单列、父类和子类重复、关系句充当节点。发现这些情况必须修正。不得为追求数量而合并真实区别；没有目标数量。不能返回原始描述清单，仅进行词语替换不算完成任务。
每个输入id恰有可追踪去向：进一个或多个groups，或discarded，不得同时两者；不遗漏、不编造id。groups为[名称,定义,[输入整数id],简短处理理由]；discarded为[id,理由]。复合描述可拆分并进入多个概念。完全同义只保留一组。不要生成连线或证据。
只返回JSON：{"groups":[],"discarded":[]}'''
CATALOG_PROMPT = '''你是质性访谈概念复核助手。本阶段统一候选节点的质量与粒度，不生成关系。输入概括仅用于提出合并方案，下一阶段会逐段核对原文；不得凭常识补充内容。
节点表达一个对象明确的行动、约束、状态或判断。事实案例、数字和具体事例作为证据，不直接充当概念；医院、医生、医疗服务、改革影响等空泛主体或领域词不能单独作为节点。节点名称不是因果句、相关句或两件事的拼接。复合候选可拆分，但不为增加数量拆分同义概念。
统一为可比较的具体经验概念，不把宽泛维度和其下具体表现并列。名称尽量8字，最多12字；不要为了短而遗漏对象。definition最多120字，只定义本概念的行动或状态、对象及必要边界，不复述事实叙述中的背景、原因、目的、结果、案例数字，不写与其他节点的联系，不把受访者观点写成客观定论。特别不要把“因为A而B”“A影响B”“A与B相关”“A但B”换一种说法塞进定义。
只有主体、对象、含义、适用条件一致的真同义项才能合并。保留相反状态、不同机制、担忧与实际行为的区别。例如检查受限与漏诊担忧不能合并。合并不可把个别来源的条件推广到所有材料。宁可保留真实区别，不为了减少数量吞并。明显空泛、残缺、无概念价值的候选应淘汰并说明原因。不设节点数量目标。
重要：不是给原有事实换短标题，而是形成一份去重的概念目录。同一行动或状态由于不同访谈、不同措辞、不同原因、具体案例或数字被多次描述，通常只保留一个共同概念；原因、目的、结果及每篇访谈的具体条件留在证据中，不将其各自组合成新的节点。只有限定条件真正改变概念含义或行动对象时才分开。宽泛概念与具体表现不要重复纳入同层节点。频率、程度、扣款金额、结算百分比不是独立新概念。节点可保留真实独特概念，但不为每句话创造节点。
每个候选整数编号必须进入至少一个groups或discarded，不能两者兼有。groups固定为[名称,定义,[成员候选编号],处理理由]，discarded固定为[候选编号,理由]。输出目录不能有重复名称；同义项合并，真实异义项须写清区别。reason最多50字。不返回关系、证据、引文。
只返回JSON：{"groups":[["费用约束","受访者描述诊疗费用受到额度限制，不包括一般收入下降。",[0,2],"同义概念"]],"discarded":[[1,"空泛主体名称"]]}'''

GROUNDING_PROMPT = '''独立检查最终候选概念是否被各自的原文支持。本阶段不生成连线、不重写节点、不使用其他单元的原文或外部知识补证。
逐个unit检查它附带的每个node：名称与定义是否只表达一个清晰概念、对象和粒度是否合理、该段原文是否直接支持定义的全部实质内容及条件。不要因为概念与研究问题相关、在候选中出现、听起来合理就认可。
不认可访谈者未得到明确回答认可的假设；按原文问答判断，不凭说话人编号猜身份。受访者的判断和担忧可以作为判断概念，但不能改写成已证实事实。保留否定、时间、主体和适用条件。不把某段原文未提及的其他候选的内容拼进去。
标签含两件事的因果或相关、定义超出该段证据、具体案例被无依据推广、空泛主体、宽泛维度、残缺短语、概念不明确，均reject；原文仅支持定义一部分也reject。keep表示本段确实支持这个概念，不表示它客观正确。
每个输入unit_id返回一次，每个附带node_id返回一次。只返回keep或reject及简短理由。不返回引文、位置、证据编号；后端根据本次确切unit和判断记录原文来源，拒绝的绑定不继承。
只返回JSON：{"units":[{"unit_id":"u0","checks":[{"node_id":"q0","verdict":"keep","reason":"回答明确描述费用额度约束"}]}]}'''


def quality_issue(label, definition):
    if not isinstance(label, str) or not label.strip() or len(label.strip()) > 12:
        return '名称不完整或过长'
    if not isinstance(definition, str) or not definition.strip() or len(definition) > 300:
        return '概念边界缺失或过长'
    if re.search(r'导致|引发|促使|造成|从而|因为|所以|影响|相关|致转', label):
        return '节点名称表达关系，应拆为独立概念'
    if label.strip() in {'医生', '医院', '基层医院', '医疗服务', '医保', '影响', '相关发现', '改革影响', 'DIP改革'}:
        return '空泛主体或领域词'
    return ''


def exact_deduplicate(records):
    """Only identical label+definition; never fuzzy-merge distinct research concepts."""
    lookup = {}
    for record in records:
        key = (record['label'].strip(), record['definition'].strip())
        if key not in lookup:
            lookup[key] = {**record, 'origins': list(record['origins']), 'unit_ids': list(record['unit_ids'])}
        else:
            previous = lookup[key]
            previous['origins'] = list(dict.fromkeys(previous['origins'] + record['origins']))
            previous['unit_ids'] = list(dict.fromkeys(previous['unit_ids'] + record['unit_ids']))
    return list(lookup.values())


def preview_quality_report(nodes):
    """Safety gate, not a claim that every remaining concept is scientifically sound."""
    labels = {}
    blockers, warnings = [], []
    for node in nodes:
        labels.setdefault(node['label'].strip(), []).append(node['id'])
        issue = quality_issue(node['label'], node['definition'])
        if issue:
            blockers.append({'node_ids': [node['id']], 'label': node['label'], 'reason': issue})
        if re.search(r'\d|%|％|每月|次数|比例|数额|心梗|头晕|CT', node['label']):
            warnings.append({'node_ids': [node['id']], 'label': node['label'], 'reason': '可能是具体病例、数字或频率编码，需人工检查粒度'})
    for label, ids in labels.items():
        if len(ids) > 1:
            blockers.append({'node_ids': ids, 'label': label, 'reason': '重复名称，须确认真同义合并或明确真实区别'})
    return {'status': 'needs_revision' if blockers else 'awaiting_human_review',
            'blockers': blockers, 'warnings': warnings,
            'human_confirmed': False,
            'notice': '原文支持核对不等于研究质量保证；节点确认前不应将草稿视为正式图谱。'}


def review_quality(run, client, model, concepts, units, theme):
    """Global compact reconciliation, then per-source semantic acceptance.

    Routing IDs identify items supplied by the backend; models never invent evidence.
    No accepted source is inherited merely because it belonged to a merged candidate.
    """
    records = [{**c, 'origins': [cid]} for cid, c in concepts.items()]
    stages = []
    discarded = {}

    def payload(rows, blind=False):
        return {'theme': theme, 'concepts': [
            {'id': i, **({} if blind else {'label': r['label']}), 'definition': r['definition'],
             'kind': r.get('kind', ''), 'subject': r.get('subject', '')}
            for i, r in enumerate(rows)]}

    def fits(rows):
        return len(rows) <= 240 and len(json.dumps(payload(rows), ensure_ascii=False)) <= 48000

    def process(rows, label, prompt=CATALOG_PROMPT):
        def validate(raw):
            expanded = expand_review(raw, list(range(len(rows))))
            kept, dropped = set(), set()
            for g in expanded['groups']:
                if not g['members'] or not isinstance(g['reason'], str) or not g['reason'].strip():
                    raise ValueError('缺少概念成员或复核理由')
                if not isinstance(g['label'], str) or not isinstance(g['definition'], str):
                    raise ValueError('复核概念字段格式无效')
                members = [m['concept_id'] for m in g['members']]
                if len(members) != len(set(members)):
                    raise ValueError('同组候选重复')
                kept.update(members)
            for d in expanded['discarded']:
                if d['concept_id'] in dropped or not isinstance(d['reason'], str) or not d['reason'].strip():
                    raise ValueError('淘汰项重复或无理由')
                dropped.add(d['concept_id'])
            if kept & dropped or kept | dropped != set(range(len(rows))):
                raise ValueError('概念去向遗漏或冲突')
        try:
            raw = run.call(client, model, prompt, payload(rows, prompt == GRANULARITY_PROMPT), label,
                           validate, cache_incomplete=False, max_tokens=12000)
        except IncompleteOutput:
            if len(rows) < 2:
                raise
            mid = len(rows)//2
            return process(rows[:mid], label+'a', prompt) + process(rows[mid:], label+'b', prompt)
        stages.append({'label': label, 'input_count': len(rows), 'result': raw})
        out = []
        for name, definition, members, reason in raw['groups']:
            origins = list(dict.fromkeys(cid for i in members for cid in rows[i]['origins']))
            issue = quality_issue(name, definition)
            if issue:
                for cid in origins:
                    discarded[cid] = issue
                continue
            out.append({'label': name.strip(), 'definition': definition.strip(), 'reason': reason,
                        'origins': origins,
                        'unit_ids': list(dict.fromkeys(uid for i in members for uid in rows[i]['unit_ids']))})
        for i, reason in raw['discarded']:
            for cid in rows[i]['origins']:
                discarded[cid] = reason
        return exact_deduplicate(out)

    # First reconcile small batches; then explicitly compare the compact whole catalog.
    chunks, current = [], []
    for record in records:
        if current and (len(current) >= 60 or not fits(current+[record])):
            chunks.append(current); current = []
        current.append(record)
        if not fits(current):
            raise InvalidOutput('单个概念超过复核预算')
    if current:
        chunks.append(current)
    records = [r for i, chunk in enumerate(chunks) for r in process(chunk, f'quality-local-{i}')]
    if records and (len(chunks) > 1 or len(stages) > len(chunks)):
        if not fits(records):
            raise InvalidOutput('全局概念目录仍过大，已保留候选，请先缩小范围；未跳过全局复核')
        split_before = len(stages)
        records = process(records, 'quality-global')
        if any(s['label'] != 'quality-global' for s in stages[split_before:]):
            # A split review is not a global review. Try the reduced catalog once.
            records = process(records, 'quality-global-final')
            if any(s['label'].startswith('quality-global-final') and s['label'] != 'quality-global-final' for s in stages):
                raise InvalidOutput('全局复核回复仍过大，未将分批结果冒充全局复核')
    if records:
        if not fits(records):
            raise InvalidOutput('最终粒度目录过大，未跳过全局概念归纳')
        records = process(records, 'quality-granularity', GRANULARITY_PROMPT)
        if any(s['label'].startswith('quality-granularity') and s['label'] != 'quality-granularity' for s in stages):
            raise InvalidOutput('最终粒度复核输出被拆批，未将不完整全局归纳作为通过结果')
    for i, r in enumerate(records):
        if not r['definition'].startswith(('受访者', '原文')):
            r['definition'] = '受访者表述的' + r['definition']
        r['id'] = f'q{i}'
    rows = [{'unit_id': u['unit_id'], 'original_text': u['source']['quote'],
             'nodes': [{'node_id': r['id'], 'label': r['label'], 'definition': r['definition']}
                       for r in records if u['unit_id'] in r['unit_ids']]} for u in units]
    rows = [r for r in rows if r['nodes']]
    batches, current = [], []
    for row in rows:
        if current and (len(current) >= 8 or len(json.dumps(current+[row], ensure_ascii=False)) > 22000):
            batches.append(current); current = []
        current.append(row)
        if len(json.dumps(current, ensure_ascii=False)) > 24000:
            raise InvalidOutput('单段原文及待验节点过大，未跳过证据核对')
    if current:
        batches.append(current)

    def ground(task):
        i, items = task
        def call(part, label):
            expected = {r['unit_id']: {n['node_id'] for n in r['nodes']} for r in part}
            def validate(raw):
                if not isinstance(raw, dict) or not isinstance(raw.get('units'), list):
                    raise ValueError('缺少逐段节点核对结果')
                ids = [r.get('unit_id') for r in raw['units'] if isinstance(r, dict)]
                if len(ids) != len(expected) or set(ids) != set(expected):
                    raise ValueError('核对单元遗漏或重复')
                for row in raw['units']:
                    checks = row.get('checks')
                    if not isinstance(checks, list):
                        raise ValueError('缺少核对列表')
                    nids = [c.get('node_id') for c in checks if isinstance(c, dict)]
                    if len(nids) != len(expected[row['unit_id']]) or set(nids) != expected[row['unit_id']]:
                        raise ValueError('节点核对遗漏、重复或超出单元')
                    if any(c.get('verdict') not in ('keep', 'reject') or not isinstance(c.get('reason'), str) or not c['reason'].strip() for c in checks):
                        raise ValueError('核对判断或理由无效')
            try:
                raw = run.call(client, model, GROUNDING_PROMPT, {'theme': theme, 'units': part},
                               label, validate, max_tokens=7000)
            except IncompleteOutput:
                if len(part) < 2:
                    raise
                mid = len(part)//2
                return call(part[:mid], label+'a') + call(part[mid:], label+'b')
            return raw['units']
        return call(items, f'quality-evidence-{i}')
    checks = [r for result in ordered_parallel(ground, list(enumerate(batches))) for r in result]
    approved = {r['id']: [] for r in records}
    for row in checks:
        for check in row['checks']:
            if check['verdict'] == 'keep':
                approved[check['node_id']].append(row['unit_id'])
    accepted = []
    for r in records:
        if not approved[r['id']]:
            for cid in r['origins']:
                discarded[cid] = '最终定义未获任何逐段原文支持'
            continue
        accepted.append({**r, 'unit_ids': list(dict.fromkeys(approved[r['id']]))})
    if not accepted:
        raise InvalidOutput('没有通过原文支持及粒度核对的概念；未生成连线')
    retained = {cid for r in accepted for cid in r['origins']}
    return accepted, {'version': QUALITY_VERSION, 'catalog_stages': stages,
                      'grounding_checks': checks, 'full_global_review': True,
                      'candidate_count': len(concepts), 'proposal_count': len(records),
                      'accepted_count': len(accepted), 'discarded': [
                          {'concept_id': cid, 'reason': discarded.get(cid, '候选未保留')}
                          for cid in concepts if cid not in retained]}
