import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from raw_theme_source import original_evidence, material_chunks

MODEL = 'deepseek-v4-pro'
API_GATE = threading.BoundedSemaphore(2)
_locks = {}
_registry_lock = threading.Lock()

FACT_PROMPT = '''你是中文社会科学访谈原文事实提取助手，建立可供不同研究问题复用的基础事实库。
本次不围绕某个研究问题筛选，不依赖访谈纪要。逐段阅读输入evidence，尽可能覆盖受访者明确表达且有分析价值的经历、行动、做法、状态、判断、条件、例外、差异及明确表述的联系。不得声称已经穷尽所有事实。
每条事实表达一个可独立核对的信息单元；紧密相连且拆开会丢失条件的内容可一起保留。事实库可保留原文明确表达的关系，不在此阶段生成概念节点或推断关系。
区分说话人、提问与回答。访谈者的设问和推测不能写成受访者认可的事实；只有受访者明确认可的内容才能归入其表述。说话人不明写“未明确”，不得猜测身份。
受访者的判断、解释和评价必须保留“受访者表示/认为”等归属，不当作已经核实的客观事实。保留数字、否定、可能性、时间、适用范围和重要条件；不补充外部知识，不润色为更强的结论。
text应简短具体，但完整保留必要条件。kind只能是经历、行动、状态、判断、条件、关系。speaker沿用原文标记，没有可靠标记时写“未明确”。
每条必须引用本批真实evidence编号，并逐字复制其中能够直接支持该事实的连续quote。不能把两段不连续原文拼成一句引文。保留完整支持语义所需的上下文；关系性事实的证据必须支持联系本身，不能只分别支持两端。
每个输入evidence编号必须出现在checked_evidence中一次，即使没有可提取内容。对无信息、只有提问或含义不清的段落允许不提取；不要编造事实来填满。避免重复提取相同表述，但不能合并不同主体或相反条件。
只返回JSON：{"checked_evidence":[1,2],"facts":[{"text":"忠于原文的信息","speaker":"说话人2","kind":"判断","evidence":[{"number":1,"quote":"连续原文"}]}]}。'''

SELECT_PROMPT = '''根据研究问题，从一篇访谈的基础事实清单中选择可能相关的信息。这里只筛选，不改写事实，不推断因果，不生成新事实。
宁可保留可能相关的条件、例外、反例和背景，不因措辞不同而漏掉。事实概括只是检索线索，后续整合会核对原文；不要把“清单未找到”当作访谈未讨论。
只引用输入真实fact_id，不重复。不相关时返回空fact_ids。relevance只能是direct、contextual、unrelated、uncertain；列明范围及证据覆盖局限。
只返回JSON：{"fact_ids":["已有ID"],"relevance":"direct","reason":"相关性及覆盖局限"}。'''


def limited_create(client, **kwargs):
    with API_GATE:
        for attempt in range(3):
            try:
                return client.chat.completions.create(**kwargs)
            except Exception as error:
                if getattr(error, 'status_code', None) != 429 or attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))


def ordered_parallel(function, values):
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(function, values))


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def ensure_library(project_id, text, directory, client):
    source_hash = hashlib.sha256(text.encode()).hexdigest()
    version = hashlib.sha256((FACT_PROMPT + MODEL + 'windows-v1').encode()).hexdigest()
    fingerprint = hashlib.sha256((source_hash + version).encode()).hexdigest()
    directory = Path(directory) / project_id / 'fact_libraries'
    directory.mkdir(parents=True, exist_ok=True)
    with _registry_lock:
        lock = _locks.setdefault(str(directory), threading.Lock())
    with lock:
        destination = directory / (fingerprint + '.json')
        if destination.exists():
            try:
                cached = json.loads(destination.read_text(encoding='utf-8'))
                facts = cached.get('facts')
                valid = isinstance(facts, list) and all(isinstance(fact, dict) and isinstance(fact.get('text'), str) and fact.get('sources') and all(source.get('project_id') == project_id and source.get('transcript_hash') == source_hash and type(source.get('start')) is int and type(source.get('end')) is int and 0 <= source['start'] < source['end'] <= len(text) and text[source['start']:source['end']] == source.get('quote') for source in fact['sources']) for fact in facts)
                if valid and cached.get('status') == 'complete' and cached.get('source_hash') == source_hash and cached.get('version') == version:
                    return {**cached, 'cache_hit': True}
            except (ValueError, TypeError, KeyError):
                pass
        run = directory / fingerprint
        run.mkdir(exist_ok=True)
        material = {'project_id': project_id, 'name': project_id, 'evidence': original_evidence(text)}
        if not material['evidence']:
            raise ValueError('访谈原文为空')
        def extract(rows):
            digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            checkpoint = run / (digest + '.json')
            if checkpoint.exists():
                return json.loads(checkpoint.read_text(encoding='utf-8'))
            row_map = {row['number']: row for row in rows}
            last_error = None
            for attempt in range(2):
                started = time.time()
                response = limited_create(client, model=MODEL, temperature=0, max_tokens=6000,
                    response_format={'type': 'json_object'}, extra_body={'thinking': {'type': 'disabled'}},
                    messages=[{'role': 'system', 'content': FACT_PROMPT}, {'role': 'user', 'content': json.dumps({'project_id': project_id, 'evidence': [{'number': row['number'], 'quote': row['quote']} for row in rows]}, ensure_ascii=False)}])
                choice = response.choices[0]
                atomic_json(run / f'{digest}-{attempt}-call.json', {'started_at': started, 'elapsed_seconds': round(time.time()-started,3), 'finish_reason': choice.finish_reason, 'evidence_numbers': list(row_map), 'model': MODEL})
                (run / f'{digest}-{attempt}-raw.txt').write_text(choice.message.content or '', encoding='utf-8')
                try:
                    if choice.finish_reason == 'length':
                        raise ValueError('基础事实回复被截断')
                    raw = json.loads(choice.message.content or '{}')
                    checked = raw.get('checked_evidence')
                    if not isinstance(checked, list) or any(type(number) is not int for number in checked) or len(checked) != len(row_map) or set(checked) != set(row_map) or not isinstance(raw.get('facts'), list):
                        raise ValueError('原文分段覆盖不完整')
                    result = []
                    for item in raw['facts']:
                        if not isinstance(item, dict) or not isinstance(item.get('text'), str) or not item['text'].strip() or item.get('kind') not in {'经历','行动','状态','判断','条件','关系'} or not isinstance(item.get('speaker'), str) or not isinstance(item.get('evidence'), list) or not item['evidence']:
                            raise ValueError('基础事实格式无效')
                        sources = []
                        for ref in item['evidence']:
                            if not isinstance(ref, dict) or type(ref.get('number')) is not int:
                                raise ValueError('原文证据编号无效')
                            row = row_map.get(ref['number'])
                            quote = ref.get('quote')
                            if not row or not isinstance(quote, str) or not quote.strip() or quote not in row['quote']:
                                raise ValueError('事实引文不是本批连续原文')
                            start = row['start'] + row['quote'].index(quote)
                            sources.append({**row, 'project_id': project_id, 'start': start, 'end': start+len(quote), 'quote': quote, 'context_quote': row['quote']})
                        identity = json.dumps([project_id, item['text'], [(s['start'], s['end']) for s in sources]], ensure_ascii=False)
                        result.append({'id': 'F'+hashlib.sha256(identity.encode()).hexdigest()[:24], 'text': item['text'].strip(), 'speaker': item['speaker'], 'kind': item['kind'], 'project_id': project_id, 'sources': sources, 'evidence': list(dict.fromkeys(s['number'] for s in sources))})
                    atomic_json(checkpoint, result)
                    return result
                except (ValueError, TypeError, KeyError) as error:
                    last_error = error
                    if len(rows) > 1:
                        middle = len(rows)//2
                        result = extract(rows[:middle]) + extract(rows[middle:])
                        atomic_json(checkpoint, result)
                        return result
            raise ValueError(str(last_error))
        parts = ordered_parallel(lambda chunk: extract(chunk['evidence']), material_chunks(material, limit=6500))
        facts, seen = [], set()
        for part in parts:
            for fact in part:
                if fact['id'] not in seen:
                    seen.add(fact['id'])
                    facts.append(fact)
        library = {'status': 'complete', 'schema_version': 1, 'project_id': project_id, 'source_hash': source_hash, 'version': version, 'fingerprint': fingerprint, 'prompt': FACT_PROMPT, 'facts': facts, 'generated_at': time.time(), 'calls': [json.loads(path.read_text(encoding='utf-8')) for path in sorted(run.glob('*-call.json'))], 'coverage_notice': '覆盖所有输入原文段落，不保证穷尽所有可分析信息；新问题必要时回查原文。'}
        atomic_json(destination, library)
        return {**library, 'cache_hit': False}


def select_facts(library, theme, call, label):
    facts = library['facts']
    batches, batch, size = [], [], 0
    for fact in facts:
        row = {key: fact[key] for key in ('id','text','speaker','kind')}
        length = len(json.dumps(row, ensure_ascii=False))
        if batch and size + length > 14000:
            batches.append(batch)
            batch, size = [], 0
        batch.append(row)
        size += length
    if batch:
        batches.append(batch)
    def select(task):
        index, rows = task
        allowed = {row['id'] for row in rows}
        for attempt in range(2):
            result = call(SELECT_PROMPT, {'theme': theme, 'project_id': library['project_id'], 'facts': [{'fact_id': row['id'], **{key: row[key] for key in ('text','speaker','kind')}} for row in rows]}, f'{label}-{index}' + ('-retry' if attempt else ''), 3000)
            identifiers = result.get('fact_ids')
            if isinstance(identifiers, list) and all(isinstance(value, str) and value in allowed for value in identifiers) and len(set(identifiers)) == len(identifiers) and result.get('relevance') in {'direct','contextual','unrelated','uncertain'}:
                return result
        raise ValueError('事实筛选引用无效')
    selected = ordered_parallel(select, list(enumerate(batches, 1)))
    identifiers = {value for part in selected for value in part['fact_ids']}
    rank = {'unrelated': 0, 'uncertain': 1, 'contextual': 2, 'direct': 3}
    relevance = max((part['relevance'] for part in selected), key=lambda value: rank[value], default='uncertain')
    if identifiers and relevance in {'unrelated','uncertain'}:
        relevance = 'contextual'
    return {'facts': [fact for fact in facts if fact['id'] in identifiers], 'relevance': relevance, 'reason': '；'.join(str(part.get('reason','')) for part in selected), 'library_fingerprint': library['fingerprint'], 'cache_hit': library['cache_hit']}
