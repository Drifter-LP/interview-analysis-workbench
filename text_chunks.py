"""Exact, nonoverlapping source spans; context is separate and never evidence."""
import re
from bisect import bisect_left,bisect_right

QUESTION = re.compile(r'(?m)^[ \t]*(?:采访者|访谈者|提问者|提问人|访问员|访谈员|问)\s*[：:]')

def bounded_spans(text,limit=12000):
    if limit<16:raise ValueError('分块上限过小')
    questions=[m.start() for m in QUESTION.finditer(text)]
    paragraphs=[m.end() for m in re.finditer(r'\n\s*\n',text)]
    sentences=[m.end() for m in re.finditer(r'[。！？!?；;][”’\"]*\s*|\n',text)]
    spans=[];start=0
    while start<len(text):
        end=min(start+limit,len(text));kind='end'
        if end<len(text):
            # Keep complete Q&A groups together when they fit. For an oversized
            # group use paragraphs/sentences, finally an explicit hard split.
            kind='hard'
            for label,positions in [('question',questions),('paragraph',paragraphs),('sentence',sentences)]:
                left=bisect_left(positions,start+limit//3);right=bisect_right(positions,end)
                if left<right:end=positions[right-1];kind=label;break
        spans.append(dict(start=start,end=end,text=text[start:end],boundary=kind,
                          context_before=text[max(0,start-400):start],
                          context_after=text[end:end+400]))
        start=end
    return spans
