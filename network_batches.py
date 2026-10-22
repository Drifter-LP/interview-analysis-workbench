import hashlib
import itertools
import json
import re
import time
import uuid
import threading
from interview_facts import limited_create


class IncompleteOutput(ValueError):
    pass

class InvalidOutput(ValueError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class BatchRun:
    def __init__(self, directory, fingerprint, signature, regenerate=False):
        self.lock = threading.RLock()
        self.reuse_checkpoints = not regenerate
        directory.mkdir(parents=True, exist_ok=True)
        self.path = None
        if not regenerate:
            for previous in sorted(directory.glob('*/manifest.json'), reverse=True):
                try:
                    manifest = json.loads(previous.read_text(encoding='utf-8'))
                    if manifest.get('fingerprint') == fingerprint and manifest.get('signature') == signature and manifest.get('status') in {'failed', 'running'}:
                        self.path, self.manifest = previous.parent, manifest
                        break
                except (ValueError, OSError):
                    continue
        if self.path is None:
            self.path = directory / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
            self.path.mkdir()
            self.manifest = {'run_id': self.path.name, 'fingerprint': fingerprint, 'signature': signature, 'calls': [], 'started_at': time.time()}
        self.manifest['status'] = 'running'
        self.save()

    def save(self):
        with self.lock:
            temporary = self.path / 'manifest.tmp'
            temporary.write_text(encoded(self.manifest), encoding='utf-8')
            temporary.replace(self.path / 'manifest.json')

    def call(self, client, model, prompt, payload, label, validate, cache_incomplete=True, max_tokens=7000, reasoning_effort=None):
        identity=[model,prompt,payload]
        if reasoning_effort:identity.append({'thinking':'enabled','effort':reasoning_effort})
        digest = hashlib.sha256(encoded(identity).encode()).hexdigest()
        checkpoint = self.path / (digest + '-checkpoint.json')
        incomplete = self.path / (digest + '-incomplete.json')
        if checkpoint.exists():
            result = json.loads(checkpoint.read_text(encoding='utf-8'))
            try:
                validate(result)
                return result
            except (ValueError, TypeError, KeyError):
                checkpoint.replace(checkpoint.with_name(digest + '-invalid-checkpoint-' + str(time.time_ns()) + '.json'))
        # Prompt+payload+model digest identifies reusable results across run versions.
        # Changing only integration format must not repeat original extraction.
        for previous in sorted(self.path.parent.glob('*/' + digest + '-checkpoint.json')) if self.reuse_checkpoints else []:
            if previous.parent == self.path:
                continue
            try:
                result=json.loads(previous.read_text(encoding='utf-8'))
                validate(result)
                checkpoint.write_text(encoded(result),encoding='utf-8')
                with self.lock:
                    self.manifest.setdefault('reused_checkpoints',[]).append({'label':label,'digest':digest,'run_id':previous.parent.name})
                    self.save()
                return result
            except (ValueError,TypeError,KeyError,OSError):
                continue
        # A complete response rejected solely by an older format validator may
        # become valid after a compatible parser repair. Revalidate it against
        # this exact prompt/payload identity before spending another request.
        previous_paths=[self.path]
        if self.reuse_checkpoints:
            previous_paths += [p.parent for p in self.path.parent.glob('*/manifest.json') if p.parent!=self.path]
        for prior in previous_paths:
            try:
                saved=json.loads((prior/'manifest.json').read_text(encoding='utf-8'))
                for index,entry in enumerate(saved.get('calls',[]),1):
                    if entry.get('digest')!=digest or entry.get('finish_reason')!='stop' or entry.get('status')!='invalid_output':continue
                    stem=f'{index:03d}-{re.sub(r"[^a-zA-Z0-9_-]", "_", entry["label"])}'
                    result=json.loads((prior/(stem+'-raw.txt')).read_text(encoding='utf-8'))
                    try:validate(result)
                    except (ValueError,TypeError,KeyError):continue
                    checkpoint.write_text(encoded(result),encoding='utf-8')
                    with self.lock:
                        self.manifest.setdefault('recovered_responses',[]).append({'label':label,'digest':digest,'run_id':prior.name,'raw_file':stem+'-raw.txt'})
                        self.save()
                    return result
            except (ValueError,TypeError,KeyError,OSError):continue
        if cache_incomplete and self.reuse_checkpoints and not incomplete.exists():
            for previous in self.path.parent.glob('*/' + digest + '-incomplete.json'):
                try:
                    marker = json.loads(previous.read_text(encoding='utf-8'))
                    if marker.get('max_tokens', 7000) != max_tokens:
                        continue
                    incomplete.write_text(encoded(marker),encoding='utf-8')
                    break
                except (OSError, ValueError):
                    continue
        if cache_incomplete and incomplete.exists():
            marker = json.loads(incomplete.read_text(encoding='utf-8'))
            if marker.get('max_tokens', 7000) == max_tokens:
                raise IncompleteOutput('复用上次拆批决定')
        feedback = []
        for attempt in range(2):
            entry = {'label': label, 'digest': digest, 'attempt': attempt + 1, 'status': 'running'}
            with self.lock:
                self.manifest['calls'].append(entry)
                self.save()
                stem = f'{len(self.manifest["calls"]):03d}-{re.sub(r"[^a-zA-Z0-9_-]", "_", label)}'
            (self.path / (stem + '-input.json')).write_text(encoded({'prompt': prompt, 'payload': payload}), encoding='utf-8')
            try:
                options={'reasoning_effort':reasoning_effort} if reasoning_effort else {'temperature':0}
                response = limited_create(client, model=model, max_tokens=max_tokens, **options,
                    response_format={'type': 'json_object'}, extra_body={'thinking': {'type': 'enabled' if reasoning_effort else 'disabled'}},
                    messages=[{'role': 'system', 'content': prompt}, {'role': 'user', 'content': encoded(payload)}] + feedback)
                choice = response.choices[0]
                content = choice.message.content or '{}'
                (self.path / (stem + '-raw.txt')).write_text(content, encoding='utf-8')
                entry['finish_reason'] = choice.finish_reason
                entry['reasoning_effort']=reasoning_effort
                usage=getattr(response,'usage',None)
                if usage:
                    entry['usage']={k:getattr(usage,k,0) or 0 for k in ('prompt_tokens','completion_tokens')}
                if choice.finish_reason == 'length':
                    raise IncompleteOutput('输出被截断')
                result = json.loads(content)
                validate(result)
                checkpoint.write_text(encoded(result), encoding='utf-8')
                entry['status'] = 'completed'
                self.save()
                return result
            except (ValueError, TypeError, KeyError) as error:
                entry.update(status='invalid_output', error=str(error)[:250])
                self.save()
                if isinstance(error, IncompleteOutput):
                    if cache_incomplete:
                        incomplete.write_text(encoded({'reason': str(error), 'max_tokens': max_tokens}), encoding='utf-8')
                    raise IncompleteOutput(str(error)) from error
                if attempt == 1:
                    raise InvalidOutput(str(error)) from error
                feedback = [{'role': 'user', 'content': '上次输出未通过格式或引用校验：' + str(error)[:500] + '。请根据原始输入修正并返回完整JSON，不新增证据。'}]
            except Exception as error:
                entry.update(status='request_failed', error=type(error).__name__, status_code=getattr(error, 'status_code', None))
                self.save()
                if attempt==0 and type(error).__name__ in {'APIConnectionError','APITimeoutError'}:
                    time.sleep(0.5)
                    continue
                raise

    def finish(self, status, stage=None):
        self.manifest.update(status=status, stage=stage, updated_at=time.time())
        self.save()


def compact_evidence(facts):
    catalog, lookup, references = {}, {}, {}
    for fact in facts.values():
        references[fact['id']] = []
        for source in fact['sources']:
            key = encoded([source['project_id'], source['number'], source.get('start'), source.get('end'), source['quote']])
            if key not in lookup:
                identifier = f's{len(catalog)}'
                lookup[key] = identifier
                catalog[identifier] = {'source': source, 'fact_ids': []}
            identifier = lookup[key]
            if fact['id'] not in catalog[identifier]['fact_ids']:
                catalog[identifier]['fact_ids'].append(fact['id'])
            if identifier not in references[fact['id']]:
                references[fact['id']].append(identifier)
    return catalog, references


def plan_tasks(nodes, facts, catalog, references):
    tasks, skipped = [], []
    for left, right in itertools.combinations(nodes, 2):
        identifiers = list(dict.fromkeys(identifier for node in (left, right) for fact_id in node['facts'] for identifier in references[fact_id]))
        material_sets = [{facts[fact_id]['sources'][index]['project_id'] for fact_id in node['facts'] for index in range(len(facts[fact_id]['sources']))} for node in (left, right)]
        shared = material_sets[0] & material_sets[1]
        if not shared:
            skipped.append([left['id'], right['id']])
            continue
        identifiers = [identifier for identifier in identifiers if catalog[identifier]['source']['project_id'] in shared]
        chunks, chunk, size = [], [], 0
        for identifier in identifiers:
            length = len(catalog[identifier]['source']['quote']) + 150
            if chunk and size + length > 14000:
                chunks.append(chunk)
                chunk, size = [], 0
            chunk.append(identifier)
            size += length
        if chunk:
            chunks.append(chunk)
        for chunk in chunks:
            tasks.append({'pair': [left['id'], right['id']], 'source_ids': chunk})
    return tasks, skipped


def generation_payload(tasks, nodes, facts, catalog, references, theme):
    node_ids = set(itertools.chain.from_iterable(task['pair'] for task in tasks))
    source_ids = list(dict.fromkeys(identifier for task in tasks for identifier in task['source_ids']))
    selected_sources = set(source_ids)
    selected_facts = [fact for fact in facts.values() if fact['node_id'] in node_ids and selected_sources.intersection(references[fact['id']])]
    return {'theme': theme, 'pairs': list(dict.fromkeys(tuple(task['pair']) for task in tasks)),
        'nodes': [{'id': node['id'], 'label': node['label'], 'definition': node.get('definition', ''), 'dimension': node['dimension']} for node in nodes if node['id'] in node_ids],
        'facts': [{'id': fact['id'], 'node_id': fact['node_id'], 'text': fact['text'], 'source_ids': [identifier for identifier in references[fact['id']] if identifier in selected_sources]} for fact in selected_facts],
        'sources': [{'source_id': identifier, 'project_id': catalog[identifier]['source']['project_id'], 'number': catalog[identifier]['source']['number'], 'quote': catalog[identifier]['source']['quote']} for identifier in source_ids]}


def normalize_edges(result, catalog, facts, payload):
    allowed_sources = {source['source_id'] for source in payload['sources']}
    allowed_facts = {fact['id'] for fact in payload['facts']}
    edges = []
    for item in result['edges']:
        if not isinstance(item, dict):
            continue
        normalized = []
        for reference in item.get('evidence', []) if isinstance(item.get('evidence'), list) else []:
            if not isinstance(reference, dict):
                continue
            identifier = reference.get('source_id')
            if identifier not in allowed_sources:
                continue
            source = catalog[identifier]['source']
            start, end = reference.get('quote_start', 0), reference.get('quote_end', len(source['quote']))
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source['quote']):
                continue
            quote = source['quote'][start:end]
            for fact_id in catalog[identifier]['fact_ids']:
                if fact_id in allowed_facts and facts[fact_id]['node_id'] in {item.get('source'), item.get('target')}:
                    normalized.append({**reference, 'fact_id': fact_id, 'project_id': source['project_id'], 'number': source['number'], 'quote': quote})
                    break
        edges.append({**item, 'evidence': normalized})
    return edges


def extract_batches(run, client, model, prompt, nodes, facts, theme):
    catalog, references = compact_evidence(facts)
    tasks, skipped = plan_tasks(nodes, facts, catalog, references)
    run.manifest.update(total_pairs=len(nodes) * (len(nodes) - 1) // 2, skipped_pairs_without_shared_material=skipped, evidence_tasks=len(tasks))
    run.save()
    edges, warnings, batch = [], [], []

    def execute(items, label):
        payload = generation_payload(items, nodes, facts, catalog, references, theme)
        expected = {tuple(pair) for pair in payload['pairs']}
        def validate(result):
            if not isinstance(result, dict) or not isinstance(result.get('edges'), list) or not isinstance(result.get('checked_pairs'), list):
                raise ValueError('候选关系格式不完整')
            checked = {tuple(pair) for pair in result['checked_pairs'] if isinstance(pair, list) and len(pair) == 2}
            if checked != expected or len(result['checked_pairs']) != len(expected):
                raise ValueError('节点对检查未覆盖当前批次')
            for edge in result['edges']:
                if not isinstance(edge, dict) or (edge.get('source'), edge.get('target')) not in expected and (edge.get('target'), edge.get('source')) not in expected:
                    raise ValueError('候选关系超出当前批次范围')
        try:
            result = run.call(client, model, prompt, payload, label, validate)
        except IncompleteOutput:
            if len(items) > 1:
                middle = len(items) // 2
                execute(items[:middle], label + '-a')
                execute(items[middle:], label + '-b')
                return
            sources = items[0]['source_ids']
            if len(sources) > 1:
                middle = len(sources) // 2
                execute([{**items[0], 'source_ids': sources[:middle]}], label + '-a')
                execute([{**items[0], 'source_ids': sources[middle:]}], label + '-b')
                return
            raise
        edges.extend(normalize_edges(result, catalog, facts, payload))
        warnings.extend(result.get('node_warnings', []) if isinstance(result.get('node_warnings', []), list) else [])

    for task in tasks:
        if batch and (len(batch) >= 6 or len(encoded(generation_payload(batch + [task], nodes, facts, catalog, references, theme))) > 26000):
            execute(batch, f'generate-{len(edges)}-{tasks.index(batch[0])}')
            batch = []
        batch.append(task)
    if batch:
        execute(batch, f'generate-last-{len(tasks)}')
    return {'edges': edges, 'node_warnings': warnings}


def review_batches(run, client, model, prompt, nodes, candidates, backend_bound=False):
    reviews, batch = [], []
    def payload(items):
        identifiers = {item[key] for item in items for key in ('source', 'target')}
        identifiers.update(identifier for item in items for key in ('source_options', 'target_options') for identifier in item.get(key, []))
        return {'nodes': [{'id': node['id'], 'label': node['label'], 'definition': node.get('definition', '')} for node in nodes if node['id'] in identifiers],
            'candidates': [{key: value for key, value in item.items() if key != 'evidence'} | {'evidence': [{key: source.get(key) for key in ('quote', 'source_span', 'target_span', 'relation_explanation', 'project_id', 'number')} for source in item['evidence']]} for item in items]}
    def execute(items, label):
        expected = {item['candidate_id'] for item in items}
        def validate(result):
            if not isinstance(result, dict) or not isinstance(result.get('reviews'), list):
                raise ValueError('关系复核格式不完整')
            identifiers = [entry.get('candidate_id') for entry in result['reviews'] if isinstance(entry, dict)]
            if len(identifiers) != len(expected) or set(identifiers) != expected:
                raise ValueError('关系复核遗漏或重复候选')
            lookup = {item['candidate_id']: item for item in items}
            for entry in result['reviews']:
                if backend_bound:
                    if entry.get('verdict') not in ('directed','undirected','reject') or not isinstance(entry.get('reason'),str) or not entry['reason'].strip():
                        raise ValueError('关系复核判定或理由缺失')
                    candidate = lookup[entry['candidate_id']]
                    if entry.get('verdict') != 'reject':
                        if entry.get('source') not in candidate['source_options'] or entry.get('target') not in candidate['target_options'] or entry['source']==entry['target'] or not entry.get('label') or not entry.get('description'):
                            raise ValueError('复核端点、名称或说明无效')
                    continue
                if entry.get('verdict') in ('directed', 'undirected'):
                    indices = entry.get('evidence_indices', [])
                    count = len(lookup[entry['candidate_id']]['evidence'])
                    if not isinstance(indices, list) or not indices or any(type(i) is not int or not 0 <= i < count for i in indices):
                        raise ValueError('evidence_indices从0开始，必须属于候选证据范围；仅一条证据时只能返回[0]')
        try:
            result = run.call(client, model, prompt, payload(items), label, validate)
        except IncompleteOutput:
            if len(items) < 2:
                raise
            middle = len(items) // 2
            execute(items[:middle], label + '-a')
            execute(items[middle:], label + '-b')
            return
        reviews.extend(result['reviews'])
    for item in candidates:
        if batch and (len(batch) >= 6 or len(encoded(payload(batch + [item]))) > 26000):
            execute(batch, 'review-' + batch[0]['candidate_id'])
            batch = []
        batch.append(item)
    if batch:
        execute(batch, 'review-' + batch[0]['candidate_id'])
    return {'reviews': reviews}
