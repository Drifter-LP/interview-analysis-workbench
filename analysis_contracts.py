"""Strict, source-bound output contracts. Never silently discard evidence."""
import hashlib

def source_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def required_text(value, field):
    if not isinstance(value,str) or not value.strip():
        raise ValueError(field+'必须为非空文字')
    return value.strip()

def validate_memo(raw, text):
    if not isinstance(raw,dict):
        raise ValueError('纪要必须为对象')
    memo={k:required_text(raw.get(k),k) for k in
          ('participant_identity','interview_date','interview_topic','summary')}
    if not isinstance(raw.get('viewpoints'),list):
        raise ValueError('viewpoints必须为数组')
    evidence=[];lookup={}
    def attach(values):
        if not isinstance(values,list) or not 1<=len(values)<=3:
            raise ValueError('每个观点和要点必须有1至3条引文')
        numbers=[]
        for value in values:
            quote=required_text(value,'quote')
            start=text.find(quote)
            if start<0:raise ValueError('引文不是连续逐字原文，未接受无依据观点')
            if text.find(quote,start+1)>=0:
                raise ValueError('引文在原文重复出现，请提供足以唯一定位的连续上下文')
            if quote not in lookup:
                lookup[quote]=len(evidence)+1
                evidence.append(dict(number=lookup[quote],quote=quote,start=start,end=start+len(quote)))
            if lookup[quote] not in numbers:numbers.append(lookup[quote])
        return numbers
    views=[]
    for item in raw['viewpoints']:
        if not isinstance(item,dict):raise ValueError('观点必须为对象')
        view={k:required_text(item.get(k),k) for k in ('title','summary')}
        view['evidence']=attach(item.get('evidence'))
        if not isinstance(item.get('points'),list):raise ValueError('points必须为数组')
        points=[]
        for p in item['points']:
            if not isinstance(p,dict):raise ValueError('要点必须为对象')
            points.append(dict(text=required_text(p.get('text'),'point.text'),
                               evidence=attach(p.get('evidence'))))
        view['points']=points;views.append(view)
    return dict(**memo,viewpoints=views,evidence=evidence,source_hash=source_hash(text),
                contract_version=1,offset_encoding='unicode_codepoints')

def check_memo_source(memo,text):
    if memo.get('source_hash')!=source_hash(text):
        raise ValueError('纪要原文版本未知或已变化，请重新生成纪要，不能混用旧证据')
    for e in memo.get('evidence',[]):
        a,b=e.get('start'),e.get('end')
        if type(a) is not int or type(b) is not int or not 0<=a<b<=len(text) or text[a:b]!=e.get('quote'):
            raise ValueError('保存的纪要引文与原文不一致')

def check_analysis_sources(analysis, transcript_path):
    sources=[s for d in analysis.get('dimensions',[]) for f in d.get('findings',[])
             for fact in f.get('facts',[]) for s in fact.get('sources',[])]
    texts={}
    for s in sources:
        pid=s.get('project_id')
        if pid not in texts:
            path=transcript_path(pid)
            if not path:raise ValueError('分析引用的访谈已不存在')
            texts[pid]=path.read_text(encoding='utf-8-sig')
        text=texts[pid];a,b=s.get('start'),s.get('end')
        if (s.get('transcript_hash')!=source_hash(text) or type(a) is not int
                or type(b) is not int or not 0<=a<b<=len(text) or text[a:b]!=s.get('quote')):
            raise ValueError('主题分析的原文版本或引用已失效，请重新分析')
