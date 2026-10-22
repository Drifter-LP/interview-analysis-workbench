"""Source-bound initial coding, compatible with the existing suggestion review UI."""
import hashlib
import json
import re
import uuid

PROMPT_VERSION = "initial-coding-20261010-1"
CODING_PROMPT = r'''你是中文社会科学质性访谈的初始编码助手。请围绕给定研究问题，对访谈原文进行编码，为后续跨访谈比较和概念共现分析提供可追溯的基础。

【输入】
你将收到：
- research_question：研究问题；为空时进行探索性编码。
- units：按原文顺序排列的原文单元，每个单元包含unit_id和text。
- context：必要的相邻原文，仅用于理解，不对context单独输出绑定。
- existing_codes：已有编码表，包含编码名称和定义。
原文有明确问答角色时按问答组织；角色不明确时保留原文段落，不猜测采访者身份。unit_id仅用于定位，不代表主题分类。

【一、编码对象】
编码受访者实际表达的行动、做法、条件、约束、体验、判断、顾虑、意愿或状态。
围绕研究问题识别有分析价值的内容。保留直接相关的内容，以及理解这些内容所必需的背景。不因材料中出现某个关键词就认定其相关。
研究问题为空时，从材料自身识别有意义的概念，不预设结论。
提问用于理解语境。不得把采访者提出的假设或观点，当作受访者已经表达的内容。受访者只有简短肯定回答时，必须结合被确认的具体问题判断；含义不明确时不编码。

【二、编码名称与粒度】
1. 一个编码表达一个可以单独理解的概念，范围保持具体、适中。
2. 名称尽量简短，通常为4～12个汉字；准确性优先，不为缩短名称而改变意思。
3. 名称应体现材料中的具体内容，避免“政策影响”“存在问题”“医疗服务”等过于宽泛的标签。
4. 不把完整的因果或关联句直接用作编码名称。原文同时表达多个独立概念时，可以分别编码。
5. 不把同一个意思拆成多个近义编码，也不为追求细致，把一个不可分割的意思拆成碎片。
6. 同一概念在不同原文中重复出现，应复用同一编码。
7. 不同主体、情境或程度不一定需要建立新编码；只有差异改变了概念含义时才分开。
8. 保留表达性质。例如“担心漏诊”不能编码为“发生漏诊”，“计划转诊”不能编码为“已经转诊”。
9. 数字、比例、时间、个别人名一般作为证据细节保留，不单独作为编码。若具体阈值本身具有分析意义，应在定义中保留其条件，不机械删除。

【三、证据要求】
1. 每次编码必须绑定原文中连续、逐字一致的引文，并提供正确的unit_id。
2. 引文应足以支持该编码，同时保留理解原意所必需的否定、条件、主体和语气。
3. 不改写、拼接、补全引文，不用省略号替代原文。
4. 一段原文可以支持多个不同编码，但每个编码必须分别得到该段文字支持。
5. 不得仅因两个概念出现在同一问答中，就推断它们之间存在因果、促进、抑制或其他关系。
6. 受访者的说法是访谈材料中的陈述，不代表已经核实的客观事实。
7. 表述过于含糊、语音识别错误导致含义不清，或证据不足以支持明确编码时，暂不编码，不猜测。

【四、复用与新增】
如果提供已有编码表：含义和适用范围一致时，优先复用已有编码的名称与定义。仅名称相似、实际含义不同，不得强行合并。已有编码不能准确表达原文时，可以新增编码。
不要为了减少编码数量而合并有实质差异的概念，也不要为了增加覆盖率而制造编码。

【五、输出前复核】
逐项检查：编码是否与研究问题相关，或属于必要背景？名称是否具体，是否只表达一个概念？是否与其他编码同义重复？每条引文是否在指定单元中连续出现？引文是否真正支持编码，而不只是包含相同词语？是否错误地把顾虑、建议、假设或否定表达写成已经发生的事实？
发现问题时，修改或删除相应编码及其绑定。不要求每个单元都有编码，不设固定编码数量。没有可靠结果时返回空数组。

【六、输出格式】
只返回JSON，不输出前言、分析过程或总结：
{"codes":[{"id":"c1","name":"编码名称","definition":"一句话说明该编码表示什么，以及必要的适用边界"}],"bindings":[{"code_id":"c1","unit_id":"u12","quote":"来自该单元的连续原文"}]}
id仅在本次输出内用于关联。相同编码只在codes中定义一次，可以对应多条bindings。同一单元内完全相同的编码与引文绑定不要重复输出。'''

def source_units(text):
    paragraphs = [{"start": m.start(), "end": m.end(), "text": m.group()} for m in re.finditer(r"\S(?:[^\n]|\n(?!\s*\n))*", text)]
    # Only explicit role labels establish Q&A boundaries; numbered speakers are not inferred.
    explicit_question = re.compile(r"^(?:采访者|访谈者|提问者|问)\s*[：:]")
    has_roles = any(explicit_question.match(p["text"]) for p in paragraphs)
    grouped = []
    for p in paragraphs:
        if has_roles and grouped and not explicit_question.match(p["text"]):
            grouped[-1]["end"] = p["end"]
            grouped[-1]["text"] = text[grouped[-1]["start"]:p["end"]]
        else:
            grouped.append(dict(p))
    for i, unit in enumerate(grouped, 1):
        unit.update(unit_id=f"u{i}", unit_kind="question_answer" if has_roles else "source_paragraph")
    return grouped

def batches(units, limit=9000):
    result, current, size = [], [], 0
    for unit in units:
        if current and size + len(unit["text"]) > limit:
            result.append(current)
            current, size = [], 0
        current.append(unit)
        size += len(unit["text"])
    if current:
        result.append(current)
    return result

def validate_reply(reply, units, text, project_id):
    if not isinstance(reply, dict) or not isinstance(reply.get("codes"), list) or not isinstance(reply.get("bindings"), list):
        raise ValueError("编码回复格式不完整，未写入建议")
    by_id = {}
    for code in reply["codes"]:
        if not isinstance(code, dict) or not all(isinstance(code.get(k), str) and code[k].strip() for k in ("id", "name", "definition")):
            raise ValueError("编码缺少名称或定义，未写入建议")
        if code["id"] in by_id:
            raise ValueError("编码编号重复，未写入建议")
        by_id[code["id"]] = code
    unit_map = {u["unit_id"]: u for u in units}
    suggestions, seen, rejected = [], set(), 0
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    for binding in reply["bindings"]:
        if not isinstance(binding, dict):
            rejected += 1
            continue
        code, unit = by_id.get(binding.get("code_id")), unit_map.get(binding.get("unit_id"))
        quote = binding.get("quote")
        if not code or not unit or not isinstance(quote, str) or not quote.strip() or quote not in unit["text"]:
            rejected += 1
            continue
        cursor = 0
        # Repeated exact quotes within one unit retain every verifiable occurrence.
        while (offset := unit["text"].find(quote, cursor)) >= 0:
            start = unit["start"] + offset
            identity = (code["name"].strip(), unit["unit_id"], start, quote)
            cursor = offset + len(quote)
            if identity in seen:
                continue
            seen.add(identity)
            end = start + len(quote)
            suggestions.append({"id": uuid.uuid4().hex, "code": code["name"].strip(), "definition": code["definition"].strip(), "reason": code["definition"].strip(), "quote": quote, "unit_id": unit["unit_id"], "unit_kind": unit["unit_kind"], "project_id": project_id, "source_start": start, "source_end": end, "start": len(text[:start].encode("utf-16-le")) // 2, "end": len(text[:end].encode("utf-16-le")) // 2, "transcript_hash": digest, "prompt_version": PROMPT_VERSION, "speaker": "", "status": "待确认"})
    return suggestions, rejected

def generate_initial_codes(text, question, existing, project_id, call):
    units = source_units(text)
    chunks = batches(units)
    known = [{"name": c["name"], "definition": c.get("definition") or "未提供定义"} for c in existing if isinstance(c, dict) and isinstance(c.get("name"), str)]
    suggestions, seen, rejected = [], set(), 0
    for chunk in chunks:
        index = units.index(chunk[0])
        last = index + len(chunk)
        context = units[max(0, index-1):index] + units[last:last+1]
        payload = {"research_question": question or "", "units": [{k: u[k] for k in ("unit_id", "text")} for u in chunk], "context": [{k: u[k] for k in ("unit_id", "text")} for u in context], "existing_codes": known}
        reply = call(CODING_PROMPT, payload)
        rows, dropped = validate_reply(reply, chunk, text, project_id)
        rejected += dropped
        for row in rows:
            identity = (row["code"], row["start"], row["quote"])
            if identity not in seen:
                suggestions.append(row)
                seen.add(identity)
        names = {c["name"] for c in known}
        for row in rows:
            if row["code"] not in names:
                known.append({"name": row["code"], "definition": row["definition"]})
                names.add(row["code"])
    return {"suggestions": suggestions, "prompt_version": PROMPT_VERSION, "unit_count": len(units), "batch_count": len(chunks), "rejected_bindings": rejected}
