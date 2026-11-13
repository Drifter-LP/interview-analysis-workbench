"""Human decisions remain separate from AI-generated correction history."""
from copy import deepcopy
from difflib import SequenceMatcher


def save_decisions(record, old_text, text, accepted_ids, rejected_ids, now):
    result = deepcopy(record)
    accepted, rejected = set(accepted_ids), set(rejected_ids)
    known = {a['change_id'] for a in result.get('annotations', [])}
    known.update(a['change_id'] for a in result.get('changes', []) if a.get('change_id'))
    if (accepted | rejected) - known:
        raise ValueError('修改记录已变化，请重新打开访谈稿后审核')
    # Refusal wins even when an old client submits the same ID twice.
    already_rejected = {a['change_id'] for a in result.get('changes', [])
                        if a.get('rejected') and a.get('change_id')}
    rejected |= already_rejected
    accepted -= rejected
    for key in ['changes', 'annotations']:
        for item in result.get(key, []):
            cid = item.get('change_id')
            if cid in rejected:
                item.update(accepted=False, rejected=True, review_status='rejected')
            elif cid in accepted:
                item.update(accepted=True, rejected=False, review_status='accepted')
    result.setdefault('review_actions', []).extend(
        {'change_id': cid, 'decision': action, 'saved_at': now}
        for action, ids in [('rejected', set(rejected_ids)), ('accepted', accepted)]
        for cid in sorted(ids))
    blocks = SequenceMatcher(None, old_text, text, autojunk=False).get_matching_blocks()
    rebased = []
    for item in result.get('annotations', []):
        if item.get('rejected'):
            continue
        a, b = item['start'], item['end']
        if old_text[a:b] != item['revised']:
            continue
        for block in blocks:
            if block.a <= a and b <= block.a + block.size:
                start = block.b + a - block.a
                rebased.append({**item, 'start': start, 'end': start + b - a})
                break
    result['annotations'] = rebased
    return result
