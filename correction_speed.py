"""Conservative punctuation triage; selection is not a correctness judgement."""
import re

RULES={'long_sentence_chars':60,'comma_count':6,'comma_sentence_chars':100,
       'sparse_paragraph_chars':80,'sparse_max_marks':1,'no_terminal_chars':150}


def punctuation_reasons(text):
    text=re.sub(r'^\s*(?:说话人\d+|访谈者|受访者)\s*[:：]','',text)
    count=lambda s:sum(ch.isalnum() for ch in s)
    size=count(text);sentences=re.split(r'[。！？!?]',text)
    reasons=[]
    if any(count(s)>60 for s in sentences):reasons.append('长句超过60字')
    if any(len(re.findall('[，,]',s))>=6 and count(s)>100 for s in sentences):reasons.append('逗号串句')
    marks=sum(not c.isalnum() and not c.isspace() for c in text)
    if size>=80 and marks<=1:reasons.append('标点稀少')
    if size>=150 and not re.search('[。！？!?]',text):reasons.append('无句末标点')
    no_ellipsis=re.sub(r'…+|\.{3,}|。{3,}','',text)
    if re.search(r'[，,]{2,}|[。！？!?]{2,}|[，,][。！？!?]',no_ellipsis):reasons.append('异常标点组合')
    return reasons


def select_paragraphs(units):
    selected=[];mapping=[];skipped=0
    for unit in units:
        for match in re.finditer(r'[^\r\n]+',unit['text']):
            if not match.group().strip():continue
            reasons=punctuation_reasons(match.group())
            if not reasons:skipped+=1;continue
            uid=len(selected)+1
            selected.append({'unit_id':uid,'speaker':unit['speaker'],'text':match.group()})
            mapping.append({'unit_id':uid,'parent_unit_id':unit['unit_id'],
                            'start':match.start(),'end':match.end(),'reasons':reasons})
    return selected,mapping,skipped


def restore_paragraphs(units,revised,mapping):
    if [x['unit_id'] for x in revised]!=[x['unit_id'] for x in mapping]:
        raise ValueError('标点片段编号不一致，拒绝合并')
    groups={}
    for target,entry in zip(revised,mapping):groups.setdefault(entry['parent_unit_id'],[]).append((entry,target))
    output=[]
    for unit in units:
        value=unit['text']
        for entry,target in sorted(groups.get(unit['unit_id'],[]),key=lambda pair:pair[0]['start'],reverse=True):
            value=value[:entry['start']]+target['text']+value[entry['end']:]
        output.append({**unit,'text':value})
    return output
