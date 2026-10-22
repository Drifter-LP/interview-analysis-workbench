"""Indexed, source-bound theme research for the workbench (pipeline v4)."""
import concurrent.futures
import copy
import hashlib
import itertools
import json
import os
import re
from pathlib import Path
import threading
import time
import uuid

from fastapi import HTTPException
from finding_definition import FINDING_DEFINITION
from dimension_definition import DIMENSION_DEFINITION
from finding_boundary import BOUNDARY_ADDITION, REVIEW_PROMPT, apply_review
from theme_file_io import read_json, write_json

MODEL = 'qwen3.8-flash'
BASE_URL = os.environ.get('QWEN_BASE_URL', '').strip()
VERSION = 4
DIMENSION_THRESHOLD = 8
INDEX_VERSION = 1
_index_lock = threading.RLock()
_source_locks = {}

INDEX_PROMPT = '''按连续话题对编号访谈切块，保留提问和连续回答。索引不针对某个研究问题，只忠实描述话题，不补因果。
仅允许跳过访谈正文开始之前的日期、访问员、受访者姓名等资料头及转录标题；将跳过的资料头起止行号列在header_ranges中，没有则返回空数组。资料头不能包含实质问答，不得把正文中出现的日期、人员或背景讨论当作资料头。
正文中的现场插话、寒暄、临时处理事情等也必须保留为话题块，按实际内容概括并加标签（如“现场插话”）；不要因为看起来与某个研究问题无关而省略，是否相关由后续筛选判断。
话题块按原文顺序排列，不得重叠，覆盖全部有效正文。块间可跳过空行或仅含省略号的分隔行，不能跳过其他文字。保留原行号，不修改或重新编号原文。
返回JSON {"header_ranges":[{"start":1,"end":4}],"blocks":[{"id":"B01","start":5,"end":20,"summary":"内容概括及重要区别","tags":["话题"]}]}。示例行号仅说明格式，必须按实际原文输出。'''
SELECT_PROMPT = '''根据话题索引选出有助于回答研究问题的块，关注问题涉及主体的具体行为、反应、理解、变化、不同说法、条件及反例。区分主体本人的陈述与他人转述；不确定但可能相关的块可选入，不把主题相近当成因果支持。只返回JSON {"selected_ids":["B01"],"reason":"总体筛选理由"}。'''
EXTRACT_PROMPT = '''只从输入原文提取与研究问题有明确联系的具体表述，不生成发现或编码。
summary是忠实于原文的完整概括，不是摘抄：用自己的话消除口头重复，保留实质信息。每条可独立理解，结合提问和连续回答补全原文明示的主体、对象、情境，不能只写残句。
按完整意思整理，不机械一句一条。紧密相关句子可合并，重复内容不重复输出；不同主体、条件、相反态度不得强行合并。保留实际主体，不将医院措施误写为医生个人行为，也不将医务人员转述的患者行为或判断写成患者直接陈述。区分受访者亲历、转述、推测及提问人假设，不把患者对变化的反应自动写成患者了解DIP政策。
保留否定、时间、条件、可能性、估计、不知道及观点归属，不将个人判断写成定论，不因研究问题补充关联或因果。提问可帮助理解，不能把提问人的假设改写成受访者观点。
保留与研究问题有关的不同反应、应对、例外、困难和未采取行动，不只选正向措施。仅谈背景而不能帮助回答研究问题的内容可不提取。引用所有理解概括所需的有效行号，不引用未提供编号，不强制字数或条数。
只输出JSON {"facts":[{"summary":"可独立理解的完整概括","lines":[1,2]}]}。原文由程序恢复，不输出quotes或text。'''
FINDINGS_PROMPT = FINDING_DEFINITION + '''
根据全部summary及其quotes原文形成跨访谈发现，summary只作线索，原文优先。围绕研究问题，不以问题中的对象替代原文明示的主体。发现可以表达共同点或有意义的差异。区分受访者直接陈述、他人转述、推测、提问人假设；医务人员描述患者反应时，标题和概括须体现“据受访医务人员描述”等来源范围，不伪装成患者直接访谈或患者共识。患者对诊疗变化的反应不等于患者知道DIP政策，也不证明该反应由DIP独自造成。
标题是有明确主语和判断的一句完整陈述，不是话题短语。每条一个核心主张，不强凑共性、不预设数量。不按访谈机械分组，不新增因果、目的、事实或普遍性。不强制全部表述进入发现，允许不相关背景或不明确内容不使用。同一表述可支持多个不同发现，不能只换标题重复。
只输出JSON {"findings":[{"id":"F01","title":"完整陈述","summary":"具体表现、主体与条件","differences":"差异例外，无则空","statement_ids":["S001"]}]}。只引用有效输入ID，不重复输出原话；无需输出未使用ID。'''
CANDIDATES_PROMPT = DIMENSION_DEFINITION + '''
先提出三套不同的候选划分依据，每套明确共同分类问题、分类单位、可能维度及预期难点。不改发现，暂无分类是允许的。仅返回JSON {"candidates":[{"id":"C1","basis":"划分依据","classification_question":"共同分类问题","unit":"分类单位","possible_dimensions":["名称"],"anticipated_difficulties":"难点"}]}。恰好三套不同ID。'''
TRIAL_PROMPT = DIMENSION_DEFINITION + '''
实际用这一候选依据试归全部发现，每个维度回答相同分类问题并保持同一分类单位。不要只选好归的例子，也不要改写发现或新增异质兜底维度。
每个发现给一个主要归属，跨界说明理由；无法合理归入任何维度，dimension_id=null，fit=unassigned，说明原因，结果显示为“暂无分类”，不要为了完整覆盖而强归。允许空类但不必保留无用类别。
只输出JSON {"candidate_id":"C1","dimensions":[{"id":"D01","name":"名称","definition":"纳入范围","excludes":"排除及边界","finding_ids":["F01"]}],"assignments":[{"finding_id":"F01","dimension_id":"D01或null","fit":"clear|crosscutting|forced|unassigned","reason":"具体归属或暂无分类原因"}],"boundary_conflicts":[{"dimension_ids":["D01"],"finding_ids":["F01"],"problem":"边界或角度问题"}]}。全部发现恰好一条assignment。'''
COMPARE_PROMPT = DIMENSION_DEFINITION + '''
比较三套完整试归，再选择相对合适的依据。不要替预选角度辩护。检查硬塞、跨界、角度混用、边界重叠，指出具体发现ID；试归自评不一定正确。允许“暂无分类”，有合理未分类优于伪装全覆盖，不因未分类直接淘汰方案。不得以名称整齐、维度少或全部归类作为唯一优点。
不改写发现、不在此步骤偷偷修改归属。若都不理想，允许返回null，或选相对较好方案但acceptable=false。
只输出JSON {"evaluations":[{"candidate_id":"C1","strengths":"优点","weaknesses":"问题","forced_ids":[],"crosscutting_ids":[],"unclassified_ids":[]}],"selected_candidate_id":"C1或null","acceptable":true,"selection_reason":"比较依据","remaining_issues":["具体问题"]}。每个候选恰好评价一次。'''


def read(path):
    return read_json(path)


def save(path, value):
    write_json(path, value)


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read_qwen_key():
    if not BASE_URL:
        return ''  # Require an explicit trusted endpoint in the publication copy.
    key = os.environ.get('QWEN_API_KEY', '').strip()
    if key:
        return key
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment') as reg:
            return str(winreg.QueryValueEx(reg, 'QWEN_API_KEY')[0]).strip()
    except (OSError, ImportError):
        return ''


def line_evidence(text, project_id, name):
    """Line numbers and character offsets refer to the exact saved transcript."""
    rows, offset = [], 0
    digest = text_hash(text)
    for number, segment in enumerate(text.splitlines(keepends=True), 1):
        quote = segment.rstrip('\r\n')
        rows.append({'number': number, 'line': number, 'quote': quote, 'start': offset,
                     'end': offset + len(quote), 'source_type': 'transcript',
                     'transcript_hash': digest, 'project_id': project_id, 'material_name': name})
        offset += len(segment)
    return rows


def ignorable_index_line(line):
    value = line.strip()
    return not value or bool(re.fullmatch(r'(?:…+|\.{3,})', value))


def leading_metadata_end(lines):
    """Only recognize compact metadata at the start, never search through dialogue."""
    field = re.compile(r'^(?:访谈日期|访谈时间|访谈地点|访问日期|访问时间|访问员|访谈员|访谈人|采访人|受访者姓名|受访人|受访者|访谈对象|录音时间|转录时间)\s*[:：]\s*[^。！？!?\n]{1,80}$')
    title = re.compile(r'^\d{4}[年./-]\d{1,2}[月./-]\d{1,2}日?[^。！？!?\n]{0,60}(?:语音转文本|转录稿|转录记录)\s*$')
    end = 0
    for number, line in enumerate(lines, 1):
        value = line.strip()
        if ignorable_index_line(line) or field.fullmatch(value) or title.fullmatch(value):
            end = number
        else:
            break
    return end


def validate_index(index, lines):
    blocks = index.get('blocks')
    if not isinstance(blocks, list) or not blocks:
        raise ValueError('索引没有有效话题块')
    cursor, ids = 1, set()
    header_end = leading_metadata_end(lines)
    headers = index.get('header_ranges', [])
    if not isinstance(headers, list):
        raise ValueError('资料头范围格式无效')
    for header in headers:
        if (not isinstance(header, dict) or type(header.get('start')) is not int
                or type(header.get('end')) is not int
                or not 1 <= header['start'] <= header['end'] <= header_end):
            raise ValueError('资料头只能标记原文开头可识别的日期、人员信息或转录标题，不得排除正文')
    skipped_headers, skipped_separators = [], []
    def check_gap(start, end, leading=False):
        missing = []
        for number in range(start, end + 1):
            line = lines[number - 1]
            if ignorable_index_line(line):
                skipped_separators.append(number)
            elif leading and number <= header_end:
                skipped_headers.append(number)
            else:
                missing.append((number, line))
        if missing:
            detail = '；'.join(f'行{n}：{text[:160]}' for n, text in missing[:8])
            raise ValueError(f'索引遗漏有效正文（共{len(missing)}行）：{detail}。未自动补造话题块')
    for block in blocks:
        # Lossless normalization only; never silently repair topic boundaries.
        for key in ('start', 'end'):
            if isinstance(block.get(key), str) and block[key].isdigit():
                block[key] = int(block[key])
        start, end = block.get('start'), block.get('end')
        if (type(start) is not int or type(end) is not int or start < cursor
                or not start <= end <= len(lines) or not isinstance(block.get('id'), str)
                or not block['id'] or block['id'] in ids
                or not isinstance(block.get('summary'), str) or not block['summary'].strip()
                or not isinstance(block.get('tags'), list)):
            raise ValueError('索引边界、编号或概括无效；需检查原始输出，未自动修补')
        check_gap(cursor, start - 1, leading=not ids)
        ids.add(block['id'])
        cursor = end + 1
    check_gap(cursor, len(lines))
    if any(h['end'] >= blocks[0]['start'] for h in headers):
        raise ValueError('资料头范围与话题块重叠')
    index['coverage_validation'] = {'policy_version': 2, 'skipped_header_lines': skipped_headers,
                                    'skipped_separator_lines': skipped_separators}
    return index


def cache_path(cache_dir, digest):
    return Path(cache_dir) / f'qwen-index-v{INDEX_VERSION}-{digest}.json'


def get_index(text, call, label, cache_dir):
    lines = text.splitlines()
    digest = text_hash(text)
    path = cache_path(cache_dir, digest)
    # Lock only the same source; different interviews can build indexes in parallel.
    with _index_lock:
        source_lock = _source_locks.setdefault(digest, threading.RLock())
    with source_lock:
        if path.exists():
            cached = read(path)
            if cached.get('source_hash') != digest or cached.get('model') != MODEL or cached.get('index_version') != INDEX_VERSION:
                raise ValueError('索引缓存版本或原文校验不匹配')
            return validate_index(cached['index'], lines), True, cached.get('review_metadata')
        index = call(INDEX_PROMPT, {'lines': [{'line': n, 'text': s} for n, s in enumerate(lines, 1)]}, label + '-index', 12000)
        validate_index(index, lines)
        save(path, {'source_hash': digest, 'model': MODEL, 'index_version': INDEX_VERSION,
                    'created_at': time.time(), 'index': index, 'review_metadata': None})
        return index, False, None


def extract_material(material, question, call, cache_dir):
    pid, text = material['project_id'], material['text']
    rows = line_evidence(text, pid, material['name'])
    lines = [r['quote'] for r in rows]
    label = hashlib.sha256(pid.encode()).hexdigest()[:12]
    index, reused, review = get_index(text, call, label, cache_dir)
    selected = call(SELECT_PROMPT, {'question': question, 'index': index}, label + '-select', 12000)
    chosen = selected.get('selected_ids')
    if not isinstance(chosen, list) or len(chosen) != len(set(chosen)) or not set(chosen) <= {b['id'] for b in index['blocks']}:
        raise ValueError('话题筛选编号无效')
    numbers = set()
    for block in index['blocks']:
        if block['id'] in chosen:
            numbers.update(range(max(1, block['start'] - 2), min(len(lines), block['end'] + 2) + 1))
    chunks, current, size = [], [], 0
    for n in sorted(numbers):
        if current and size + len(lines[n - 1]) > 10000:
            chunks.append(current)
            current, size = [], 0
        current.append(n)
        size += len(lines[n - 1])
    if current:
        chunks.append(current)
    facts, seen = [], set()
    recovery_splits = []
    def extract_chunk(chunk, stage, depth=0):
        context = set(chunk)
        for n in (chunk[0], chunk[-1]):
            context.update(range(max(1, n - 2), min(len(lines), n + 2) + 1))
        try:
            result = call(EXTRACT_PROMPT, {'question': question, 'original_lines': [{'line': n, 'text': lines[n - 1]} for n in sorted(context)]}, stage, 12000 if depth == 0 else 6000)
            if not isinstance(result.get('facts'), list):
                raise ValueError('表述提取格式无效')
            batch = []
            for f in result['facts']:
                if not isinstance(f, dict):
                    raise ValueError('表述格式无效')
                summary, refs = f.get('summary'), f.get('lines')
                if not isinstance(summary, str) or not summary.strip() or not isinstance(refs, list) or not refs or any(type(n) is not int or n not in context for n in refs):
                    raise ValueError('表述概括或原文行号无效')
                refs = sorted(set(refs))
                batch.append({'interview_id': pid, 'project_id': pid, 'material_name': material['name'],
                              'summary': summary.strip(), 'text': summary.strip(), 'lines': refs,
                              'quotes': [{'line': n, 'text': lines[n - 1]} for n in refs],
                              'evidence': refs, 'sources': [rows[n - 1] for n in refs]})
            return batch
        except ValueError:
            if getattr(call, 'no_split_recovery', False):
                raise  # Web calls already exhausted their bounded retries.
            if depth >= 1 or len(chunk) < 2:
                raise
            # Only the failed batch is divided; no content is dropped or invented.
            total = sum(len(lines[n - 1]) for n in chunk)
            used, middle = 0, max(1, len(chunk) // 2)
            if total:
                for index, n in enumerate(chunk[:-1], 1):
                    used += len(lines[n - 1])
                    if used >= total / 2:
                        middle = index
                        break
            recovery_splits.append({'stage': stage, 'first_line': chunk[0], 'last_line': chunk[-1],
                                    'boundary_line': chunk[middle]})
            return (extract_chunk(chunk[:middle], stage + '-part-a', depth + 1)
                    + extract_chunk(chunk[middle:], stage + '-part-b', depth + 1))
    for i, chunk in enumerate(chunks, 1):
        for fact in extract_chunk(chunk, label + f'-extract-{i:02d}'):
            identity = (fact['summary'], tuple(fact['lines']))
            if identity not in seen:
                seen.add(identity)
                facts.append(fact)
    return facts, {'project_id': pid, 'index_reused': reused, 'index_review': review,
                   'blocks': len(index['blocks']), 'selected_blocks': len(chosen),
                   'extraction_batches': len(chunks), 'recovery_splits': recovery_splits, 'statements': len(facts)}


def validate_trial(raw, finding_ids):
    raw = copy.deepcopy(raw)  # Keep the provider response untouched for auditing.
    dimensions, assignments = raw.get('dimensions'), raw.get('assignments')
    if not isinstance(dimensions, list) or not isinstance(assignments, list):
        raise ValueError('维度试归格式无效')
    dims = {d['id']: d for d in dimensions}
    if len(dims) != len(dimensions) or any(not d.get('name') or not d.get('definition') or d['name'] in ('其他', '其它', '其他发现', '其它发现', '相关发现') for d in dimensions):
        raise ValueError('维度名称、定义或编号无效')
    ids = [a['finding_id'] for a in assignments]
    if len(ids) != len(set(ids)) or set(ids) != finding_ids:
        raise ValueError('维度归属遗漏或重复发现')
    normalizations = list(raw.get('unassigned_normalizations', []))
    for a in assignments:
        if a.get('fit') == 'unassigned' and a.get('dimension_id') is not None:
            reason = a.get('reason', '')
            explicit = isinstance(reason, str) and re.search(
                r'无法(?:直接|合理)?归|无合适归类|无处归类|列为[“\"\s]*暂无分类|无合适.*维度', reason)
            contradictory = isinstance(reason, str) and re.search(
                r'(?:并非|不是|并不)无法归|(?:应该|应当|适合|可以|能够|明确|应|可)归入\s*(?:D\d|该维度|此维度|本维度)', reason)
            if not explicit or contradictory or a['dimension_id'] not in dims:
                raise ValueError(f"{a['finding_id']}暂无分类状态与编号或理由不一致，未自动转换")
            normalizations.append({'finding_id': a['finding_id'], 'original_dimension_id': a['dimension_id'],
                                   'normalized_dimension_id': None, 'fit': 'unassigned',
                                   'reason': reason, 'operation': 'explicit_unassigned_to_null'})
            a['dimension_id'] = None
        if a.get('fit') not in ('clear', 'crosscutting', 'forced', 'unassigned') or (a.get('dimension_id') is None) != (a['fit'] == 'unassigned') or (a['dimension_id'] is not None and a['dimension_id'] not in dims):
            raise ValueError('维度归属状态无效')
        if a['dimension_id'] is not None and dims[a['dimension_id']]['name'].startswith('暂无分类'):
            raise ValueError('暂无分类不能同时作为已分类维度，未猜测实际归属')
    repairs = []
    for did, d in dims.items():
        expected = [a['finding_id'] for a in assignments if a['dimension_id'] == did]
        if d.get('finding_ids') != expected:
            repairs.append({'dimension_id': did, 'original': d.get('finding_ids'), 'from_assignments': expected})
        d['finding_ids'] = expected
    raw['membership_repairs'] = repairs
    removed = [d for d in dimensions if d['name'].startswith('暂无分类') and not d['finding_ids']]
    raw['dimensions'] = [d for d in dimensions if d not in removed]
    raw['removed_unclassified_dimensions'] = list(raw.get('removed_unclassified_dimensions', [])) + removed
    raw['unassigned_normalizations'] = normalizations
    raw['unclassified'] = [{'finding_id': a['finding_id'], 'reason': a.get('reason', '')} for a in assignments if a['dimension_id'] is None]
    return raw


def synthesize(statements, question, call, checkpoint=None):
    allowed = {s['id'] for s in statements}
    payload = [{k: s[k] for k in ('id', 'interview_id', 'summary', 'quotes')} for s in statements]
    raw = call(FINDINGS_PROMPT + BOUNDARY_ADDITION, {'question': question, 'statements': payload}, '04-findings', 16000)
    findings = raw.get('findings')
    if not isinstance(findings, list) or not findings:
        raise ValueError('没有有效发现')
    ids = [f.get('id') for f in findings]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('发现编号重复或无效')
    for f in findings:
        refs = f.get('statement_ids')
        if any(not isinstance(f.get(k), str) or not f[k].strip() for k in ('title', 'summary')) or not isinstance(f.get('differences'), str) or not isinstance(refs, list) or not refs or any(not isinstance(i, str) for i in refs) or len(refs) != len(set(refs)) or not set(refs) <= allowed:
            raise ValueError('发现内容或引用编号无效')
    generated = copy.deepcopy(findings)
    if checkpoint:
        checkpoint('generated-findings.json', {'findings': generated})
    def review_one(finding):
        cited = set(finding['statement_ids'])
        subset = [s for s in payload if s['id'] in cited]
        if {s['id'] for s in subset} != cited:
            raise ValueError('单条复核缺少原始引用')
        suffix = hashlib.sha256(finding['id'].encode()).hexdigest()[:12]
        part = call(REVIEW_PROMPT, {'question': question, 'statements': subset, 'findings': [finding]},
                    '04b-boundary-review-' + suffix, 6000)
        validated_findings = apply_review([finding], part)
        if checkpoint:
            checkpoint('boundary-review-' + suffix + '.json', {
                'finding_id': finding['id'], 'provided_statement_ids': [s['id'] for s in subset],
                'review': part, 'findings': validated_findings})
        return part['reviews'][0]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        review = {'reviews': list(pool.map(review_one, generated))}
    findings = apply_review(generated, review)
    ids = [f['id'] for f in findings]
    if len(ids) != len(set(ids)):
        raise ValueError('边界复核后的发现编号重复')
    review_audit = {'generated_findings': generated, 'boundary_review': review,
                    'boundary_review_model': MODEL, 'boundary_review_applied': True,
                    'boundary_review_scope': 'single_finding_cited_statements'}
    if checkpoint:
        checkpoint('reviewed-findings.json', {'findings': findings, **review_audit})
    relations = []
    for a, b in itertools.combinations(findings, 2):
        x, y = set(a['statement_ids']), set(b['statement_ids'])
        if x == y:
            relations.append({'type': 'identical', 'a': a['id'], 'b': b['id']})
        elif x < y:
            relations.append({'type': 'contained', 'contained': a['id'], 'container': b['id']})
        elif y < x:
            relations.append({'type': 'contained', 'contained': b['id'], 'container': a['id']})
    if len(findings) <= DIMENSION_THRESHOLD:
        return {'findings': findings, 'reference_relations': relations, **review_audit,
                'dimension_stage_skipped': True, 'dimension_skip_threshold': DIMENSION_THRESHOLD,
                'dimension_candidates': [], 'dimension_trials': [], 'selected_dimensions': None,
                'dimension_selection': {'skipped': True, 'selected_candidate_id': None,
                    'selection_reason': f'发现不超过{DIMENSION_THRESHOLD}条，直接展示发现，不归纳维度。',
                    'remaining_issues': []}}
    compact = [{k: f[k] for k in ('id', 'title', 'summary', 'differences')} for f in findings]
    candidates = call(CANDIDATES_PROMPT, {'question': question, 'findings': compact}, '05-dimension-candidates', 12000)['candidates']
    if len(candidates) != 3 or len({c['id'] for c in candidates}) != 3:
        raise ValueError('必须有三套不同的候选划分依据')
    def trial(c):
        t = call(TRIAL_PROMPT, {'question': question, 'candidate': c, 'findings': compact}, '06-trial-' + c['id'], 12000)
        if t.get('candidate_id') != c['id']:
            raise ValueError('候选依据编号不匹配')
        validated = validate_trial(t, set(ids))
        if checkpoint:
            checkpoint('validated-trial-' + hashlib.sha256(c['id'].encode()).hexdigest()[:12] + '.json', validated)
        return validated
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        trials = list(pool.map(trial, candidates))
    selection = call(COMPARE_PROMPT, {'question': question, 'candidates': candidates, 'trials': trials, 'findings': compact}, '07-dimension-comparison', 12000)
    evaluations = selection.get('evaluations', [])
    if len(evaluations) != 3 or {e['candidate_id'] for e in evaluations} != {c['id'] for c in candidates} or type(selection.get('acceptable')) is not bool:
        raise ValueError('维度比较输出不完整')
    selected_id = selection.get('selected_candidate_id')
    if selected_id is not None and selected_id not in {c['id'] for c in candidates}:
        raise ValueError('最终维度方案编号无效')
    return {'findings': findings, 'reference_relations': relations, **review_audit, 'dimension_candidates': candidates,
            'dimension_trials': trials, 'dimension_selection': selection,
            'selected_dimensions': next((t for t in trials if t['candidate_id'] == selected_id), None)}


def assemble_result(statements, raw):
    lookup = {s['id']: s for s in statements}
    notes = {f['id']: [] for f in raw['findings']}
    for r in raw['reference_relations']:
        if r['type'] == 'identical':
            notes[r['a']].append('与' + r['b'] + '引用完全一致')
            notes[r['b']].append('与' + r['a'] + '引用完全一致')
        else:
            notes[r['contained']].append('引用被' + r['container'] + '完全包含')
            notes[r['container']].append('引用完全包含' + r['contained'])
    findings = {}
    review_lookup = {r['finding_id']: r for r in raw.get('boundary_review', {}).get('reviews', [])}
    generated_lookup = {f['id']: f for f in raw.get('generated_findings', [])}
    for f in raw['findings']:
        facts = []
        for sid in f['statement_ids']:
            s = lookup[sid]
            facts.append({k: s[k] for k in ('project_id', 'material_name', 'text', 'summary', 'lines', 'evidence', 'sources')} | {'source_fact_ids': [sid], 'library_fact_ids': []})
        findings[f['id']] = {**f, 'source_ids': f['statement_ids'], 'facts': facts,
                             'material_count': len({s['project_id'] for s in facts}),
                             'reference_notes': notes[f['id']]}
        parent_id = f.get('parent_finding_id', f['id'])
        if parent_id in review_lookup:
            findings[f['id']]['boundary_review_info'] = {
                'decision': review_lookup[parent_id]['decision'],
                'reason': review_lookup[parent_id]['reason'],
                'original_finding': generated_lookup[parent_id],
                'unused_statement_ids': review_lookup[parent_id].get('unused_statement_ids', []),
                'unused_reason': review_lookup[parent_id].get('unused_reason', '')}
    if raw.get('dimension_stage_skipped'):
        # Compatibility container for saved records/review; not a model-generated dimension.
        return [{'name': '研究发现', 'is_flat_findings': True, 'findings': list(findings.values())}]
    selected = raw['selected_dimensions']
    dimensions = []
    if selected:
        for d in selected['dimensions']:
            if d['finding_ids']:
                dimensions.append({**d, 'findings': [findings[i] for i in d['finding_ids']]})
        pending = selected['unclassified']
    else:
        pending = [{'finding_id': i, 'reason': '三套维度方案均未选定，保留发现供研究者判断。'} for i in findings]
    if pending:
        dimensions.append({'name': '暂无分类', 'definition': '以下发现未强行归入分析维度。', 'is_unclassified': True,
                           'findings': [{**findings[r['finding_id']], 'unclassified_reason': r['reason']} for r in pending]})
    return dimensions


def run_theme(body, research_project_path, transcript_path, files_dir, list_projects):
    if not re.fullmatch(r'[0-9A-Za-z\u4e00-\u9fff_-]+', body.research_project_id):
        raise HTTPException(400, '无效研究项目编号')
    path = research_project_path(body.research_project_id)
    if not path.exists():
        raise HTTPException(404, '研究项目不存在')
    research = read(path)
    request_token = getattr(body, 'request_token', '')
    if request_token and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request_token):
        raise HTTPException(400, '请求标识格式无效')
    theme = body.theme.strip()[:300]
    allowed = set(research.get('interview_ids', [])) | {str(r['workspace_project_id']) for r in research.get('uploaded_transcripts', []) if r.get('workspace_project_id')}
    ids = list(dict.fromkeys(str(i).strip() for i in body.project_ids if str(i).strip()))
    if not theme or not ids or not set(ids) <= allowed:
        raise HTTPException(400, '请填写研究问题，并从本项目选择访谈稿')
    key = read_qwen_key()
    if not key:
        raise HTTPException(400, '未检测到 QWEN_API_KEY，请设置千问密钥后重试')
    names = {p['id']: p.get('name', p['id']) for p in list_projects()}
    materials = []
    for pid in ids:
        source = transcript_path(pid)
        if not source:
            raise HTTPException(400, '所选访谈没有可用原文')
        text = source.read_text(encoding='utf-8-sig')
        if not text.strip():
            raise HTTPException(400, '所选访谈原文为空')
        materials.append({'project_id': pid, 'name': names.get(pid, pid), 'text': text})
    hashes = {m['project_id']: text_hash(m['text']) for m in materials}
    resume = getattr(body, 'resume_run_id', '')
    old = None
    if resume:
        if not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[0-9a-f]{6}', resume):
            raise HTTPException(400, '无效运行编号')
        old_dir = Path(files_dir) / body.research_project_id / 'theme_analysis_runs' / resume
        if not (old_dir / 'manifest.json').exists():
            raise HTTPException(404, '运行记录不存在')
        old = read(old_dir / 'manifest.json')
        if old.get('theme_pipeline_version') != VERSION:
            raise HTTPException(409, '旧任务使用不同流程，请新建主题研究；旧结果保留')
        if old.get('theme') != theme or old.get('source_hashes') != hashes or old.get('model') != MODEL:
            raise HTTPException(409, '研究问题、材料或模型已变化，不能复用旧任务')
    run_id = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    run_dir = Path(files_dir) / body.research_project_id / 'theme_analysis_runs' / run_id
    manifest = {'run_id': run_id, 'theme': theme, 'material_ids': ids, 'source_hashes': hashes,
                'theme_pipeline_version': VERSION, 'analysis_pipeline': 'indexed_direct_synthesis',
                'provider': 'qwen', 'model': MODEL, 'thinking': 'disabled', 'fact_library_mode': False,
                'boundary_review_enabled': True, 'boundary_review_version': 2,
                'boundary_review_scope': 'single_finding_cited_statements',
                'status': 'running', 'started_at': time.time(), 'batches': [], 'resumed_from': resume or None,
                'request_token': request_token, 'recovery_policy_version': 1, 'active_calls': {}}
    lock = threading.RLock()
    def manifest_save():
        save(run_dir / 'manifest.json', manifest)
    from theme_recovery import validate_stage, array_key, stage_name
    call_counter = itertools.count(1)
    def update_progress(label, number, recovering=False, retry=0, done=False):
        with lock:
            active = manifest['active_calls']
            if done:
                active.pop(label, None)
            else:
                active[label] = {'number': number, 'stage': stage_name(label), 'recovering': recovering,
                                 'retry': retry}
            waiting = list(active.values())
            focus = next((v for v in waiting if v['recovering']), waiting[-1] if waiting else None)
            message = ('正在恢复第%d批（%s，第%d/2次）' % (focus['number'], focus['stage'], focus['retry'])
                       if focus and focus['recovering'] else
                       '正在处理第%d批（%s）' % (focus['number'], focus['stage']) if focus else '正在整理已完成结果')
            manifest['progress'] = {'message': message, 'recovering': bool(focus and focus['recovering']),
                                    'completed_batches': sum(b.get('status') in ('completed', 'reused') for b in manifest['batches']),
                                    'active_batches': len(waiting)}
            manifest_save()
    manifest_save()
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=BASE_URL, timeout=240, max_retries=0)
    def signature(prompt, payload, budget):
        return text_hash(json.dumps({'model': MODEL, 'temperature': 0, 'thinking': 'disabled',
                                    'prompt': prompt, 'payload': payload, 'budget': budget}, ensure_ascii=False, sort_keys=True))
    reusable, failed_outputs = {}, {}
    if old:
        for folder in (old_dir / 'calls').glob('*'):
            if not (folder / 'input.json').exists() or not (folder / 'diagnostic.json').exists():
                continue
            previous, diagnostic = read(folder / 'input.json'), read(folder / 'diagnostic.json')
            digest = signature(previous['system'], previous['payload'], diagnostic.get('max_tokens', 12000))
            if (folder / 'parsed.json').exists() and diagnostic.get('status') in ('completed', 'reused') and diagnostic.get('finish_reason') == 'stop':
                reusable[digest] = folder
            elif (diagnostic.get('status') == 'failed' and
                  ((diagnostic.get('finish_reason') in ('stop', 'length') and (folder / 'response.json').exists())
                   or diagnostic.get('recovery_action') == 'split_failed_batch')):
                failed_outputs[digest] = folder
    def call(prompt, payload, label, budget):
        # Stage labels are cache identities, not filenames supplied by the model.
        folder = run_dir / 'calls' / hashlib.sha256(label.encode()).hexdigest()[:20]
        if (folder / 'parsed.json').exists():
            return validate_stage(label, read(folder / 'parsed.json'), payload)
        save(folder / 'input.json', {'system': prompt, 'payload': payload})
        diagnostic = {'label': label, 'status': 'running', 'started_at': time.time(), 'model': MODEL, 'max_tokens': budget,
                      'finish_reason': None, 'usage': None}
        request_id = signature(prompt, payload, budget)
        save(folder / 'diagnostic.json', diagnostic)
        number = next(call_counter)
        update_progress(label, number)
        try:
            if request_id in reusable:
                previous = reusable[request_id]
                parsed = read(previous / 'parsed.json')
                try:
                    validate_stage(label, parsed, payload)
                except ValueError as exc:
                    diagnostic['rejected_checkpoint'] = {'path': str(previous), 'reason': str(exc)}
                else:
                    save(folder / 'parsed.json', parsed)
                    diagnostic.update(status='reused', finish_reason='stop', usage=None,
                                      reused_from=str(previous), request_signature=request_id)
                    return parsed
            if old and not old.get('recovery_policy_version') and request_id in failed_outputs and '-extract-' in label:
                diagnostic.update(previous_failed_output=str(failed_outputs[request_id]), recovery_action='split_failed_batch')
                raise ValueError('该批次已有异常输出，保留原响应并直接缩小分批')
            from theme_model_io import request_json
            from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
            attempts = []
            diagnostic['attempts'] = attempts
            for attempt in range(1, 4):
                attempt_dir = folder / f'attempt-{attempt:02d}'
                record = {'attempt': attempt, 'status': 'running', 'started_at': time.time(),
                          'finish_reason': None, 'usage': None}
                save(attempt_dir / 'input.json', {'system': prompt, 'payload': payload, 'model': MODEL,
                                                 'temperature': 0, 'thinking': 'disabled', 'max_tokens': budget})
                def record_response(response):
                    save(attempt_dir / 'response.json', response)
                    save(folder / 'response.json', response)
                    record.update(finish_reason=response['choices'][0]['finish_reason'], usage=response.get('usage'),
                                  locally_aborted=response.get('locally_aborted', False))
                def record_normalization(operation):
                    record['normalization'] = operation
                    save(attempt_dir / 'normalization.json', operation)
                try:
                    parsed = request_json(client, model=MODEL, prompt=prompt, payload=payload, budget=budget,
                                          guarded='-extract-' in label, on_response=record_response,
                                          array_key=array_key(label), on_normalization=record_normalization)
                    save(attempt_dir / 'parsed.json', parsed)
                    validate_stage(label, parsed, payload)
                    save(folder / 'parsed.json', parsed)
                    record['status'] = 'completed'
                    diagnostic.update(status='completed', accepted_attempt=attempt)
                    return parsed
                except Exception as exc:
                    retryable = isinstance(exc, (ValueError, APIConnectionError, APITimeoutError, InternalServerError, RateLimitError))
                    record.update(status='failed', error_type=type(exc).__name__,
                                  error=str(exc).replace(key, '***')[:1000], retryable=retryable)
                    if attempt == 3 or not retryable:
                        raise
                    update_progress(label, number, recovering=True, retry=attempt)
                    if isinstance(exc, (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)):
                        time.sleep(attempt * 2)
                finally:
                    record['elapsed_seconds'] = round(time.time() - record['started_at'], 3)
                    attempts.append(record)
                    diagnostic.update(finish_reason=record['finish_reason'], usage=record['usage'],
                                      locally_aborted=record.get('locally_aborted', False))
                    save(attempt_dir / 'diagnostic.json', record)
                    save(folder / 'diagnostic.json', diagnostic)
        except Exception as exc:
            diagnostic.update(status='failed', error=str(exc).replace(key, '***')[:500])
            raise
        finally:
            diagnostic['elapsed_seconds'] = round(time.time() - diagnostic['started_at'], 3)
            save(folder / 'diagnostic.json', diagnostic)
            with lock:
                manifest['batches'].append(diagnostic)
                update_progress(label, number, done=True)
    call.no_split_recovery = not (old and not old.get('recovery_policy_version'))
    try:
        if old and (old_dir / 'statements.json').exists():
            statements = read(old_dir / 'statements.json')['statements']
            metrics = old.get('extraction_metrics', [])
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(lambda m: extract_material(m, theme, call, Path(files_dir) / 'theme_topic_indexes'), materials))
            statements = [dict(f, id=f'S{i:03d}') for i, f in enumerate((f for rows, _ in results for f in rows), 1)]
            metrics = [m for _, m in results]
        save(run_dir / 'statements.json', {'statements': statements})
        manifest.update(status='integrating', statement_count=len(statements), extraction_metrics=metrics)
        manifest_save()
        raw = synthesize(statements, theme, call, lambda name, value: save(run_dir / name, value)) if statements else None
        if raw:
            save(run_dir / 'synthesis.json', raw)
        for m in materials:
            current = transcript_path(m['project_id'])
            if not current or text_hash(current.read_text(encoding='utf-8-sig')) != hashes[m['project_id']]:
                raise ValueError('分析期间原文已变化，请重新分析；本次原文快照保留于运行记录')
        result = {'theme': theme, 'dimensions': assemble_result(statements, raw) if raw else [],
                  'materials': [{'project_id': m['project_id'], 'name': m['name']} for m in materials],
                  'run_id': run_id, 'generated_at': time.time(), 'source_mode': 'original_transcript',
                  'source_schema_version': 1, 'theme_pipeline_version': VERSION,
                  'analysis_pipeline': 'indexed_direct_synthesis', 'extraction_mode': 'indexed_theme_statements',
                  'model': MODEL, 'provider': 'qwen', 'thinking': 'disabled', 'relevance': [], 'failed_batches': [],
                  'fact_libraries': [], 'statements': statements, 'extraction_metrics': metrics,
                  **({k: v for k, v in raw.items() if k != 'findings'} if raw else {})}
        if not statements:
            result['notice'] = '本次未提取到与研究问题相关的具体表述。'
        save(run_dir / 'result.json', result)
        manifest.update(status='completed', completed_at=time.time(), finding_count=len(raw['findings']) if raw else 0)
        manifest_save()
        return {'analysis': result}
    except Exception as exc:
        resumable = (run_dir / 'statements.json').exists()
        manifest.update(status='integration_failed' if resumable else 'failed', completed_at=time.time(), error=str(exc).replace(key, '***')[:1000])
        manifest_save()
        message = '主题研究整合未完成，提取结果已保留，可仅重试整合。' if resumable else '索引或表述提取未完成，检查点已保留，可继续未完成分析。'
        raise HTTPException(502, message + '运行编号：' + run_id + '。' + str(exc).replace(key, '***')[:250]) from exc
