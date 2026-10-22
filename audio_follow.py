"""Match exact text anchors to real ASR segments; never estimate word times."""
import json,re,hashlib
from difflib import SequenceMatcher

def precise_alignment(directory, source_path, data, text):
    """Map cached acoustic timestamps through edits, without estimating word times."""
    cache_path = directory / '录音对齐.json'
    if not cache_path.exists():
        return []
    try:
        cache = json.loads(cache_path.read_text(encoding='utf-8'))
        if cache.get('source_sha256') != hashlib.sha256(source_path.read_bytes()).hexdigest():
            return []
        source_segments = data['segments']
        original = ''.join(normalize(s.get('text',''))[0] for s in source_segments)
        current, positions = normalize(text)
        if not original or not current or current.count(original) > 1:
            return []
        matcher = SequenceMatcher(None, original, current, autojunk=False)
        if matcher.ratio() < .5:
            return []
        units = []
        for entry in cache.get('aligned_segments', [cache]):
            index = entry['segment_index']
            offset = sum(len(normalize(s.get('text',''))[0]) for s in source_segments[:index])
            segment_text = normalize(source_segments[index]['text'])[0]
            cursor = 0
            for word in entry['words']:
                value = normalize(word['text'])[0]
                if not value:
                    continue
                at = segment_text.find(value, cursor)
                if at < 0:
                    continue
                a, b = word['start'], word['end']
                if not isinstance(a,(int,float)) or not isinstance(b,(int,float)) or not 0 <= a < b:
                    continue
                units.append((offset+at, offset+at+len(value), a, b))
                cursor = at + len(value)
        result = []
        for tag, a, b, c, d in matcher.get_opcodes():
            if tag == 'equal':
                for left, right, begin, end in units:
                    lo, hi = max(a,left), min(b,right)
                    if lo < hi:
                        x, y = c+lo-a, c+hi-a
                        result.append({'start':positions[x],'end':positions[y-1]+1,'audio_start':begin,'audio_end':end,'precision':'字词对齐（模型预测）'})
            elif tag == 'replace' and 0 < b-a <= 8 and 0 < d-c <= 8:
                related = [u for u in units if u[0] < b and u[1] > a]
                if related:
                    result.append({'start':positions[c],'end':positions[d-1]+1,'audio_start':min(u[2] for u in related),'audio_end':max(u[3] for u in related),'precision':'修改处原录音范围（近似）'})
        return result
    except (ValueError,KeyError,TypeError,IndexError,OSError):
        return []

def normalize(text):
    skip=set()
    for m in re.finditer(r'(?m)^\s*[^\n：:]{1,16}[：:]',text):skip.update(range(m.start(),m.end()))
    chars=[];positions=[]
    for i,c in enumerate(text):
        if i not in skip and c.isalnum():chars.append(c.lower());positions.append(i)
    return ''.join(chars),positions

def audio_file(directory):
    link=directory/'录音关联.json'
    if link.exists():
        try:
            data=json.loads(link.read_text(encoding='utf-8'))
            if data.get('detached'):return None
            candidate=(directory/data['file']).resolve()
            if candidate.is_relative_to(directory.resolve()) and candidate.is_file():return candidate
            return None
        except (ValueError,KeyError,OSError):return None
    return next((p for p in sorted(directory.glob('原始录音.*')) if p.suffix.lower() in {'.wav','.mp3','.m4a','.aac','.flac','.ogg','.mp4'}),None)

def alignment(directory,text):
    if not audio_file(directory):return {'available':False,'message':'没有关联的原始录音','segments':[]}
    link=directory/'录音关联.json'
    if link.exists():
        state=json.loads(link.read_text(encoding='utf-8'))
        if state.get('status') not in ('completed','completed_with_fallback'):
            return {'available':True,'precision':'录音已关联，对齐尚未完成','segments':[]}
    normalized,positions=normalize(text);result=[];last=-1
    paths=[directory/state.get('reference','关联录音转录.json')] if link.exists() else sorted(directory.glob('*转录.json'))
    for path in paths:
        if not path.exists():continue
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        precise = precise_alignment(directory, path, data, text)
        for segment in data.get('segments',[]):
            value,_=normalize(segment.get('text',''))
            if len(value)<8:continue
            width=min(12,len(value));hits=[]
            for j in range(0,len(value)-width+1,max(1,width//2)):
                anchor=value[j:j+width];at=normalized.find(anchor)
                if at>last and normalized.find(anchor,at+1)<0:hits.append((at,at+width))
            if not hits:continue
            start=min(x[0] for x in hits);end=max(x[1] for x in hits)
            if end-start>len(value)*2+30:continue
            a=segment.get('start_ms');b=segment.get('end_ms')
            if not isinstance(a,(int,float)) or not isinstance(b,(int,float)) or not 0<=a<b:continue
            result.append({'start':positions[start],'end':positions[end-1]+1,'audio_start':a/1000,'audio_end':b/1000})
            last=end-1
        if precise or result:
            return {'available':True,'precision':'部分字词对齐，其余录音段定位' if precise else '录音段定位（非逐字）','segments':precise+result}
    return {'available':True,'precision':'录音段定位（非逐字）','segments':result}
