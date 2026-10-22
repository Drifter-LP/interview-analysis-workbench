"""Finding boundary review from the isolated 66-statement experiment."""
import copy

BOUNDARY_ADDITION = '''
合并前检查：这些表述是在共同支持同一个具体判断，还是只是原因相同、话题相关？若一条发现中的几个判断各有独立证据，且删除其中一个后，其他判断仍可独立成立，应考虑拆分。背景、条件、例子和反例用于说明核心判断，不因此单独拆分。不以发现数量多少作为质量目标。'''

REVIEW_PROMPT = '''你是中文定性研究的发现边界复核者。本次只检查发现是否过度合并，不重新进行一轮自由归纳，也不要求一定拆分。
每条发现应表达一个具体核心判断。若数种表现共同支持这一判断，或其他内容是背景、条件、例子、反例，应保留；不要因包含多个行为或多篇访谈就自动拆分。只有多个判断可各自独立成立、各有直接原文证据，且合并遮蔽重要区别时，才建议拆分。不得用更大的话题替代判断，也不能逐条改写summary造成过度拆分。
输入仅包含研究问题、一条待复核发现，以及该发现实际引用的具体表述summary和quotes，保持这些表述在原材料清单中的顺序。本次看不到其他发现或其他表述，也不要猜测、补写或讨论它们。summary只作线索，原文优先。不得新增材料未支持的因果、动机、普遍性、诊断或评价；受访者观点须保留来源范围。
逐条作keep或split判断，理由不超过两句话。keep必须原样保留，由程序恢复原发现，不输出新标题或改写内容。split至少提出两条各自完整的陈述式发现，并解释核心判断区别；只使用该原发现实际引用过的表述编号，每个子发现至少一条引用，同一表述可以支持多个子发现。不得新增或删除整条发现，不跨父发现合并，不归纳维度，不预设条数。
拆分时保留原发现中有原文支持的重要内容和条件。若某个原引用确实不支持任何子发现，可列入unused_statement_ids并给简短原因，不能为凑覆盖率硬挂引用。children的引用与unused_statement_ids合计必须覆盖父发现全部引用，未使用和已引用不得重叠。无法在不丢失重要内容的前提下合理拆分时，选择keep并解释疑虑。
只输出JSON {"reviews":[{"finding_id":"F01","decision":"keep|split","reason":"不超过两句话","children":[{"title":"完整陈述","summary":"具体表现、条件和来源范围","differences":"差异和例外，无则空","statement_ids":["S001"]}],"unused_statement_ids":[],"unused_reason":"无则空"}]}。keep的children及unused_statement_ids为空数组。本次只有一个输入发现，恰好返回一条review。
'''


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_findings(raw, statements):
    findings = raw.get('findings')
    allowed = {s['id'] for s in statements}
    if not isinstance(findings, list) or not findings:
        raise ValueError('No findings')
    ids = [f.get('id') for f in findings]
    if any(not isinstance(fid, str) or not fid for fid in ids) or len(ids) != len(set(ids)):
        raise ValueError('Invalid finding IDs')
    for f in findings:
        if any(not isinstance(f.get(k), str) or not f[k].strip() for k in ('title', 'summary')) or not isinstance(f.get('differences'), str):
            raise ValueError('Invalid finding fields')
        refs = f.get('statement_ids')
        if not isinstance(refs, list) or not refs or any(not isinstance(s, str) for s in refs) or len(refs) != len(set(refs)) or not set(refs) <= allowed:
            raise ValueError('Invalid statement references')
    return findings


def apply_review(findings, raw):
    originals = {f['id']: f for f in findings}
    reviews = raw.get('reviews')
    if not isinstance(reviews, list) or len(reviews) != len(findings) or {r.get('finding_id') for r in reviews} != set(originals):
        raise ValueError('Review omitted, duplicated or added a finding')
    lookup = {r['finding_id']: r for r in reviews}
    results = []
    for f in findings:
        r = lookup[f['id']]
        if not isinstance(r.get('reason'), str) or not r['reason'].strip():
            raise ValueError('Missing review reason')
        if r.get('decision') == 'keep':
            if r.get('children') != [] or r.get('unused_statement_ids') != []:
                raise ValueError('Keep must not rewrite findings or remove references')
            results.append(copy.deepcopy(f))
            continue
        if r.get('decision') != 'split' or not isinstance(r.get('children'), list) or len(r['children']) < 2:
            raise ValueError('Invalid split decision')
        allowed = set(f['statement_ids'])
        children = [dict(c, id=f['id'] + '.' + str(i)) for i, c in enumerate(r['children'], 1)]
        validate_findings({'findings': children}, [{'id': sid} for sid in allowed])
        used = {sid for c in children for sid in c['statement_ids']}
        unused = r.get('unused_statement_ids')
        if not isinstance(unused, list) or any(not isinstance(s, str) for s in unused) or len(unused) != len(set(unused)) or not set(unused) <= allowed:
            raise ValueError('Invalid unused references')
        if set(unused) & used or used | set(unused) != allowed or (unused and not r.get('unused_reason', '').strip()):
            raise ValueError('Split silently dropped or duplicated unused references')
        for child in children:
            child['parent_finding_id'] = f['id']
        results.extend(children)
    return results


