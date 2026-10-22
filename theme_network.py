"""Evidence-bound network generation; independent of the theme-analysis pipeline."""
import hashlib
import json
import time
import threading
from functools import wraps
from fastapi import HTTPException
from pydantic import BaseModel, Field
from network_batches import BatchRun, IncompleteOutput, InvalidOutput, review_batches
from concept_first_network import build_concept_first_network, concept_first_signature

GENERATION_PROMPT = '''你是中文定性研究助手，依据原文关联标准提取给定主题之间的候选联系。
不要求证明客观因果。原文明确表达影响、限制、促使或引出时可以有方向；原文明示对比、取舍或关联但方向不清时无方向。
两个主题分别有证据、共同出现、同维度或领域相近，不足以连线。不得拼接不同材料来推断原文未表达的联系。
不新增节点，不扩大节点或原话的意思。保留可能性、否定、条件和适用范围；无法支持的节点概括标在node_warnings中。
每条线必须挑出专属证据，不要附带两个节点的所有原文。quote逐字复制某条输入sources的连续片段，保留足够上下文。
source_span和target_span分别逐字摘录该quote中对应两端主题的内容，relation_explanation说明原话表达的联系。
连续问答可作为上下文，但仅有提问而受访者未明确认可不成立。若输入片段不足，暂不连线，不补充外部知识。
有方向仅表示材料表达的方向，不表示证明因果。label不超过12字。允许孤立节点或空edges。
仅检查输入pairs列出的节点对，checked_pairs逐一列出所有已检查的节点对，即使没有找到联系也必须列出。证据通过source_id引用输入原文，不重复输出整段原文；程序将恢复该编号的完整原文。两端片段仍须逐字摘录。
只返回JSON：{"checked_pairs":[["n0","n1"]],"edges":[{"source":"n0","target":"n1","label":"关系名称","description":"关系及条件","directed":false,"direction_reason":"方向依据或为何不确定","evidence":[{"source_id":"s0","source_span":"对应起点","target_span":"对应终点","relation_explanation":"关联依据"}]}],"node_warnings":[]}'''

REVIEW_PROMPT = '''独立复核候选主题联系，不能因生成模型的概括或常识而认可。只依据附带原文及输入事实。
端点可能经粒度复核拆分。必须从source_options和target_options分别选择准确端点，以source和target返回；不能新增端点或将一种关系分配给全部组合。没有可支持的准确端点则reject。可以保留或降低输入方向，不得将原本无方向的候选提升为有方向。
逐条检查：两端是否对应原话、原文是否表达联系而非仅共同出现、否定条件是否保留、方向是否超出原文。
不要求严格因果证明。关联明确且方向明确为directed；关联明确而方向不清为undirected；联系不足或主题扩大原意为reject。
费用与医疗安全的明确取舍可无方向连线；两段分别描述亏损与中医治疗不能据此推断中医缓解亏损。
每条候选已由后端绑定一个确定的连续原文窗口，必须判断这整个窗口是否支持该联系。提问者的设问、假设不能当作受访者结论，必须有回答明确认可；角色不能仅凭说话人编号猜测。指代不明不得强行补全方向；原因和目的不能倒置为因果。不得返回证据编号、索引、引文或位置，不得新增联系或证据。每条候选必须返回一次，遗漏将视为未通过。
通过时返回label和description，忠于原文保留条件。改为无方向时也必须去掉名称及说明中不受支持的导致、促使等方向表述。
只返回JSON：{"reviews":[{"candidate_id":"c0","source":"n0","target":"n1","verdict":"directed|undirected|reject","label":"核对后的关系名称，不超过12字","description":"核对后的关系及条件","reason":"关联及方向的判断依据","node_warning":"节点概括问题，没有则空字符串"}]}'''

NETWORK_MODEL = 'deepseek-v4-pro'
def network_signature():
    return hashlib.sha256((NETWORK_MODEL + REVIEW_PROMPT + concept_first_signature() + 'graph-v5-cache-v3').encode()).hexdigest()

def validate_candidate(item, facts, ids):
    if not isinstance(item, dict) or item.get('source') not in ids or item.get('target') not in ids or item['source'] == item['target']:
        return None
    if not isinstance(item.get('label'), str) or not item['label'].strip():
        return None
    evidence = item.get('evidence', [])
    if not isinstance(evidence, list):
        return None
    valid = []
    for ref in evidence:
        if not isinstance(ref, dict):
            continue
        fact = facts.get(ref.get('fact_id'))
        if not fact or fact['node_id'] not in {item['source'], item['target']}:
            continue
        quote = ref.get('quote')
        spans = [ref.get('source_span'), ref.get('target_span')]
        if not isinstance(quote, str) or not quote.strip() or any(not isinstance(s, str) or not s.strip() or s not in quote for s in spans):
            continue
        original = next((s for s in fact['sources'] if s['project_id'] == ref.get('project_id') and str(s['number']) == str(ref.get('number')) and quote in s['quote']), None)
        if original and isinstance(ref.get('relation_explanation'), str) and ref['relation_explanation'].strip():
            valid.append({**original, **ref, 'context_quote': original['quote'], 'number': original['number']})
    return {**item, 'evidence': valid} if valid else None


class NetworkRequest(BaseModel):
    research_project_id: str
    analysis: dict = Field(default_factory=dict)
    regenerate: bool = False


def register_theme_network(app, research_project_path, files_dir, read_analysis, read_key, transcript_path=None):
    generation_locks = {}
    registry_lock = threading.Lock()
    def serialized_generation(function):
        @wraps(function)
        def guarded(body: NetworkRequest):
            identity = body.research_project_id + hashlib.sha256(json.dumps(body.analysis, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            with registry_lock:
                lock = generation_locks.setdefault(identity, threading.Lock())
            if not lock.acquire(blocking=False):
                raise HTTPException(409, '这份分析的关系图正在生成，请等待完成')
            try:
                return function(body)
            finally:
                lock.release()
        return guarded
    def prepare(body):
        path = research_project_path(body.research_project_id)
        if not path.exists():
            raise HTTPException(404, "研究项目不存在")
        research = json.loads(path.read_text(encoding="utf-8"))
        allowed = set(research.get("interview_ids", [])) | {
            str(item.get("workspace_project_id")) for item in research.get("uploaded_transcripts", [])
            if item.get("workspace_project_id")}
        analysis = body.analysis
        nodes, facts = [], {}
        for dimension in analysis.get("dimensions", []):
            for finding in dimension.get("findings", []):
                node = {"id": f"n{len(nodes)}", "label": str(finding.get("title", "")).strip(),
                        "dimension": dimension.get("name", ""), "facts": []}
                if not node["label"]:
                    continue
                for fact in finding.get("facts", []):
                    pid = fact.get("project_id")
                    if pid not in allowed:
                        raise HTTPException(400, "关系图材料必须属于当前研究项目")
                    memo = {} if analysis.get('source_mode') == 'original_transcript' else read_analysis(pid).get("familiarity_memo", {})
                    evidence_map = {str(e.get("number")): e for e in memo.get("evidence", [])}
                    evidence = fact.get("evidence", [])
                    refs = []
                    if analysis.get('source_mode') == 'original_transcript':
                        original_path = transcript_path(pid) if transcript_path else None
                        if not original_path:
                            raise HTTPException(400, '无法读取原文证据对应的访谈稿')
                        original_text = original_path.read_text(encoding='utf-8-sig')
                        original_hash = hashlib.sha256(original_text.encode()).hexdigest()
                        for entry in fact.get('sources', []):
                            if not isinstance(entry, dict) or entry.get('source_type') != 'transcript' or entry.get('project_id') != pid:
                                continue
                            start, end = entry.get('start'), entry.get('end')
                            if type(start) is not int or type(end) is not int or not (0 <= start < end <= len(original_text)) or entry.get('transcript_hash') != original_hash or original_text[start:end] != entry.get('quote'):
                                raise HTTPException(400, '访谈原文已变化或证据位置无效，请重新生成主题分析')
                            refs.append(entry)
                    for number in evidence if isinstance(evidence, list) else []:
                        if analysis.get('source_mode') == 'original_transcript':
                            continue
                        entry = evidence_map.get(str(number))
                        if entry and entry.get("quote"):
                            refs.append({"project_id": pid, "number": entry["number"],
                                         "quote": entry["quote"], "material_name": fact.get("material_name", pid)})
                    if not refs:
                        continue
                    fid = f"f{len(facts)}"
                    facts[fid] = {"id": fid, "node_id": node["id"], "text": fact.get("text", ""), "sources": refs}
                    node["facts"].append(fid)
                if node["facts"]:
                    nodes.append(node)
        payload = {"theme": analysis.get("theme", ""), "nodes": nodes, "facts": list(facts.values())}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        fingerprint = hashlib.sha256((encoded + network_signature()).encode()).hexdigest()
        dest = files_dir / body.research_project_id / "theme_networks" / f"{fingerprint}.v5.json"
        return nodes, facts, payload, fingerprint, dest

    def load_cooccurrence(body):
        if body.analysis.get('graph_type') != 'cooccurrence':
            return None
        fingerprint = str(body.analysis.get('cooccurrence_graph_id', ''))
        if len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
            raise HTTPException(400, '共现图记录编号无效')
        project = research_project_path(body.research_project_id)
        if not project.exists():
            raise HTTPException(404, '研究项目不存在')
        research = json.loads(project.read_text(encoding='utf-8'))
        allowed = set(research.get('interview_ids', [])) | {x.get('workspace_project_id') for x in research.get('uploaded_transcripts', [])}
        path = files_dir / body.research_project_id / 'cooccurrence_networks' / (fingerprint + '.json')
        if not path.exists():
            raise HTTPException(404, '共现图尚未保存')
        graph = json.loads(path.read_text(encoding='utf-8'))
        if graph.get('theme') != body.analysis.get('theme') or not set(graph.get('audit', {}).get('interviews', [])).issubset(allowed):
            raise HTTPException(400, '共现图材料或研究问题不匹配')
        checked = {}
        for node in graph.get('nodes', []):
            for source in node.get('sources', []):
                pid = source['project_id']
                if pid not in checked:
                    with transcript_path(pid).open(encoding='utf-8-sig', newline='') as f:
                        text = f.read()
                    checked[pid] = (text, hashlib.sha256(text.encode()).hexdigest())
                text, digest = checked[pid]
                if source.get('source_sha256') != digest or text[source['start']:source['end']] != source['quote']:
                    raise HTTPException(409, '访谈原文已变化，请重新生成共现图')
        return {'graph': graph, 'fingerprint': fingerprint}

    @app.post("/api/theme-networks/load")
    def load_network(body: NetworkRequest):
        cooccurrence = load_cooccurrence(body)
        if cooccurrence is not None:
            return cooccurrence
        _, _, payload, fingerprint, dest = prepare(body)
        if dest.exists():
            return {'graph': json.loads(dest.read_text(encoding='utf-8')), 'fingerprint':fingerprint}
        # Exact input equality only: never load a graph belonging to another analysis.
        for old in sorted(dest.parent.glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True):
            try:
                graph=json.loads(old.read_text(encoding='utf-8'))
                if graph.get('audit',{}).get('input')==payload and graph.get('generation_signature') == network_signature():
                    return {'graph':graph,'fingerprint':fingerprint,'legacy':True}
            except (ValueError,OSError):
                continue
        return {'graph':None,'fingerprint':fingerprint}

    @app.post("/api/theme-networks/nodes")
    @serialized_generation
    def generate_nodes_preview(body: NetworkRequest):
        """Node-only checkpoint. Never write theme_networks or invoke edge extraction."""
        findings, facts, payload, fingerprint, _ = prepare(body)
        if not facts:
            raise HTTPException(400, '没有具有原文依据的事实')
        key = read_key()
        if not key:
            raise HTTPException(400, '未检测到 DeepSeek API Key')
        dest = files_dir / body.research_project_id / 'node_previews' / f'{fingerprint}.json'
        if dest.exists() and not body.regenerate:
            return json.loads(dest.read_text(encoding='utf-8'))
        run = BatchRun(files_dir / body.research_project_id / 'node_preview_runs',
                       fingerprint, concept_first_signature(), body.regenerate)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key, base_url='https://api.deepseek.com', timeout=240)
            result = build_concept_first_network(run, client, NETWORK_MODEL, findings, facts,
                                                payload['theme'], transcript_path, nodes_only=True)
            result.update(preview_id=fingerprint, status='awaiting_node_confirmation',
                          theme=payload['theme'], edges_generated=False)
            result['audit']['input'] = payload
            dest.parent.mkdir(parents=True, exist_ok=True)
            temporary = dest.with_suffix('.tmp')
            temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(dest)
            run.finish('completed', 'nodes_only')
            return result
        except Exception as error:
            run.finish('failed', 'nodes_only')
            if isinstance(error, (InvalidOutput, IncompleteOutput)):
                raise HTTPException(502, '节点生成未通过完整性或质量核对：' + str(error)[:180] + '；未生成连线') from error
            raise HTTPException(502, '节点生成未完成，成功批次已保存；未生成连线') from error

    @app.post("/api/theme-networks")
    @serialized_generation
    def generate_network(body: NetworkRequest):
        cooccurrence = load_cooccurrence(body)
        if cooccurrence is not None:
            return cooccurrence
        nodes, facts, payload, fingerprint, dest = prepare(body)
        if dest.exists() and not body.regenerate:
            return {"graph": json.loads(dest.read_text(encoding="utf-8"))}
        if not facts:
            raise HTTPException(400, "没有具有原文依据的事实，请先生成或打开主题分析")
        key = read_key()
        if not key:
            raise HTTPException(400, "未检测到 DeepSeek API Key")
        prompt = GENERATION_PROMPT
        model = NETWORK_MODEL
        signature = network_signature()
        run = BatchRun(files_dir / body.research_project_id / 'theme_network_runs', fingerprint, signature, body.regenerate)
        stage = 'concepts'
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=240)
            concept_fingerprint = hashlib.sha256((json.dumps(payload, ensure_ascii=False, sort_keys=True) + model + concept_first_signature()).encode()).hexdigest()
            concept_path = files_dir / body.research_project_id / 'concept_nodes' / f'{concept_fingerprint}.json'
            concept_cache_hit = concept_path.exists() and not body.regenerate
            if concept_cache_hit:
                concepts = json.loads(concept_path.read_text(encoding='utf-8'))
            else:
                concepts = build_concept_first_network(run, client, model, nodes, facts, payload['theme'], transcript_path)
                concept_path.parent.mkdir(parents=True, exist_ok=True)
                concept_temp = concept_path.with_suffix('.tmp')
                concept_temp.write_text(json.dumps(concepts, ensure_ascii=False, indent=2), encoding='utf-8')
                concept_temp.replace(concept_path)
            nodes, facts = concepts['nodes'], concepts['facts']
            stage = 'generation'
            candidates, rejected = concepts['candidates'], list(concepts['rejected'])
            raw = {'edges': candidates}
            stage = 'review'
            review_raw = review_batches(run, client, model, REVIEW_PROMPT, nodes, candidates, backend_bound=True)
        except HTTPException:
            raise
        except IncompleteOutput:
            run.finish('failed', stage)
            raise HTTPException(502, f"{'概念节点' if stage == 'concepts' else '关系图'}回复仍不完整，已保留成功批次和原始回复；未保存不完整图谱")
        except InvalidOutput as error:
            run.finish('failed', stage)
            raise HTTPException(502, '回复的格式或证据引用未通过校验（不是截断）：' + str(error)[:150] + '；成功批次已保留，可重试')
        except Exception:
            run.finish('failed', stage)
            raise HTTPException(502, f"{'概念节点提取或合并' if stage == 'concepts' else '关系图生成或复核'}未完成，已保留成功批次；再次点击生成可继续")
        edges, seen = [], {}
        reviews = {}
        for r in review_raw['reviews']:
            if isinstance(r, dict) and isinstance(r.get('candidate_id'), str):
                reviews.setdefault(r['candidate_id'], []).append(r)
        for item in candidates:
            matches = reviews.get(item['candidate_id'], [])
            review = matches[0] if len(matches) == 1 else {}
            refs = item['evidence']
            if review.get('verdict') not in {'directed', 'undirected'} or not refs or not isinstance(review.get('reason'), str) or not review['reason'].strip() or not isinstance(review.get('label'), str) or not review['label'].strip() or not isinstance(review.get('description'), str) or not review['description'].strip():
                rejected.append({'candidate': item, 'review': review, 'reason': review.get('reason') or '复核未通过或没有有效专属证据'})
                continue
            source = review.get('source', item['source'] if len(item['source_options']) == 1 else None)
            target = review.get('target', item['target'] if len(item['target_options']) == 1 else None)
            if source not in item['source_options'] or target not in item['target_options'] or source == target or review['verdict'] == 'directed' and not item['directed']:
                rejected.append({'candidate':item, 'review':review, 'reason':'端点映射或方向超出候选依据'})
                continue
            directed = review['verdict'] == 'directed'
            pair = ((source, target, True) if directed else (*sorted((source, target)), False)) + (review['label'],)
            if pair in seen:
                existing = seen[pair]
                for ref in refs:
                    if ref not in existing['sources']:
                        existing['sources'].append(ref)
                existing.setdefault('additional_reviews', []).append(review)
                continue
            edges.append({"id": f"e{len(edges)}", "source": source, "target": target,
                          "label": review['label'][:12], "description": review['description'],
                          "directed": review['verdict'] == 'directed', "sources": refs, 'review': review,
                          'candidate_id': item['candidate_id'], 'verification': 'model_reviewed'})
            seen[pair] = edges[-1]
        graph = {"schema_version": 5, 'generation_signature': signature, 'node_mode': 'concept_first', 'evidence_binding':'backend_evidence_window', "fingerprint": fingerprint, "theme": payload["theme"],
                 "nodes": nodes, "edges": edges, "generated_at": time.time(),
                 'audit': {'prompts': {**concepts['audit']['prompts'], 'review': REVIEW_PROMPT},
                           'input': payload, 'generation_json': raw, 'review_json': review_raw,
                           'concept_nodes': concepts['audit'], 'relationship_input': {'nodes':nodes,'facts':list(facts.values())},
                           'concept_cache_hit': concept_cache_hit,
                           'rejected': rejected, 'node_warnings': raw.get('node_warnings', []),
                           'batch_run_id': run.path.name, 'batch_summary': json.loads(json.dumps(run.manifest)),
                           'notice': '模型辅助复核，不等于研究者确认；箭头表示材料表达的方向，不证明客观因果。'}}
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            archive = dest.with_name(f'{fingerprint}.v5.{time.time_ns()}.json')
            archive.write_text(dest.read_text(encoding='utf-8'), encoding='utf-8')
        temporary = dest.with_suffix(".tmp")
        temporary.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(dest)
        run.finish('completed', 'saved')
        return {"graph": graph}
