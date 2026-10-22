"""Adapt shared topic indexes without changing original text or cached boundaries."""
import re
import uuid
from indexed_theme import get_index


def metadata_end(text):
    offset=0
    field=re.compile(r'^(?:职业|性别|年龄|身份|地区|访谈日期|访谈时间|访谈地点|访谈形式|访问日期|访问时间|访问员|访谈员|访谈人|采访人|受访者姓名|受访人|访谈对象|录音时间|转录时间)\s*[:：]\s*[^。！？!?\n]{1,80}$')
    for line in text.splitlines(keepends=True):
        if line.strip() and not field.fullmatch(line.strip()):break
        offset+=len(line)
    return offset


def prepare(t, cache_dir, call):
    index,reused,_=get_index(t['text'],call,t['hash'][:12],cache_dir)
    lines=t['text'].splitlines(keepends=True)
    offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line))
    header=metadata_end(t['text'])
    blocks=[]
    def add(start,end,include,reason):
        if start>=end:return
        blocks.append(dict(id=uuid.uuid4().hex,start=start,end=end,include=include,
                           kind='content' if include else 'background',reason=reason))
    cursor=0
    for source in index['blocks']:
        start,end=offsets[source['start']-1],offsets[source['end']]
        add(cursor,start,False,'资料头或空白分隔；保留原文，不纳入统计')
        add(start,min(end,header),False,'开头资料信息；不纳入统计')
        add(max(start,header),end,True,'复用话题索引；正文默认纳入，可人工调整')
        cursor=end
    add(cursor,len(t['text']),False,'资料头或空白分隔；保留原文，不纳入统计')
    issues=[]
    for block in blocks:
        if block['include'] and len(re.sub(r'\s','',t['text'][block['start']:block['end']]))>500:
            issues.append(dict(start=block['start'],reason='超过500字，请确认是否需要按话题拆分；同一案例可保持完整。',
                               source='程序提醒',action='keep',resolved=False))
    return {**t,'blocks':blocks,'issues':issues,'index_reused':reused,'segmentation_policy':'shared-topic-index-v1',
            'api_calls':len(t.get('responses',[]))}
