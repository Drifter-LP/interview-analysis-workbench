"""Structural validation and bounded recovery, never semantic rewriting."""
import copy


def array_key(label):
    if label.endswith('-index'): return 'blocks'
    if label.endswith('-select'): return 'selected_ids'
    if '-extract-' in label: return 'facts'
    if label == '04-findings': return 'findings'
    if label.startswith('04b-boundary-review-'): return 'reviews'
    if label == '05-dimension-candidates': return 'candidates'
    return None  # Multi-field objects cannot be reconstructed from an array.


def validate_stage(label, raw, payload):
    import indexed_theme as t
    from finding_boundary import validate_findings, apply_review
    if not isinstance(raw, dict): raise ValueError('模型结果必须为JSON对象')
    try:
        if label.endswith('-index'):
            t.validate_index(copy.deepcopy(raw), [r['text'] for r in payload['lines']])
        elif label.endswith('-select'):
            ids = raw.get('selected_ids')
            allowed = {b['id'] for b in payload['index']['blocks']}
            if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)) or not set(ids) <= allowed:
                raise ValueError('话题筛选编号遗漏格式、重复或无效')
        elif '-extract-' in label:
            facts = raw.get('facts'); allowed = {r['line'] for r in payload['original_lines']}
            if not isinstance(facts, list): raise ValueError('表述提取缺少facts数组')
            for n, f in enumerate(facts, 1):
                if not isinstance(f, dict) or not isinstance(f.get('summary'), str) or not f['summary'].strip(): raise ValueError(f'第{n}条表述概括无效')
                refs = f.get('lines')
                if not isinstance(refs, list) or not refs or any(type(i) is not int or i not in allowed for i in refs) or len(refs) != len(set(refs)):
                    raise ValueError(f'第{n}条表述原文行号重复或无效')
        elif label == '04-findings':
            validate_findings(raw, payload['statements'])
        elif label.startswith('04b-boundary-review-'):
            apply_review(payload['findings'], raw)
        elif label == '05-dimension-candidates':
            candidates = raw.get('candidates')
            if not isinstance(candidates, list) or len(candidates) != 3 or any(not isinstance(c, dict) or not isinstance(c.get('id'), str) or not c['id'] for c in candidates) or len({c['id'] for c in candidates}) != 3:
                raise ValueError('维度候选方案缺失或编号重复')
        elif label.startswith('06-trial-'):
            if raw.get('candidate_id') != payload['candidate']['id']: raise ValueError('维度试归候选编号不匹配')
            t.validate_trial(raw, {f['id'] for f in payload['findings']})
        elif label == '07-dimension-comparison':
            allowed = {c['id'] for c in payload['candidates']};evaluations = raw.get('evaluations')
            if not isinstance(evaluations, list) or len(evaluations) != len(allowed) or any(not isinstance(e, dict) for e in evaluations) or {e.get('candidate_id') for e in evaluations} != allowed or type(raw.get('acceptable')) is not bool:
                raise ValueError('维度比较评价遗漏、重复或格式无效')
            if raw.get('selected_candidate_id') is not None and raw['selected_candidate_id'] not in allowed: raise ValueError('选定维度方案编号无效')
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError('模型结果字段缺失或结构无效：' + str(exc)) from exc
    return raw


def stage_name(label):
    if label.endswith('-index'): return '建立索引'
    if label.endswith('-select'): return '筛选话题'
    if '-extract-' in label: return '提取表述'
    if label == '04-findings': return '归纳发现'
    if label.startswith('04b-boundary-review-'): return '复核发现边界'
    if label.startswith('05-'): return '提出维度方案'
    if label.startswith('06-'): return '维度试归'
    return '比较维度方案'
