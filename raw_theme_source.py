"""Original-text evidence windows; no model and no memo dependency."""
import hashlib
import re

def original_evidence(text, limit=1400, overlap=180):
    rows = []
    # Include speaker labels and all nonblank text, retaining exact character offsets.
    for match in re.finditer(r'\S(?:[^\n]|\n(?!\s*\n))*', text):
        start, end = match.start(), match.end()
        while start < end:
            stop = min(end, start + limit)
            if stop < end:
                marks = [text.rfind(mark, start + limit // 2, stop) for mark in '。！？；\n']
                boundary = max(marks)
                if boundary >= 0:
                    stop = boundary + 1
            rows.append({'number': len(rows) + 1, 'quote': text[start:stop], 'start': start, 'end': stop, 'source_type': 'transcript', 'transcript_hash': hashlib.sha256(text.encode()).hexdigest()})
            if stop == end:
                break
            start = max(start + 1, stop - overlap)
    return rows

def material_chunks(material, limit=10000):
    chunks, rows, size = [], [], 0
    for row in material['evidence']:
        if rows and size + len(row['quote']) > limit:
            chunks.append({'project_id': material['project_id'], 'name': material['name'], 'evidence': rows})
            # Carry the last evidence window as context across chunk boundaries.
            rows = rows[-1:]
            size = sum(len(r['quote']) for r in rows)
        rows.append(row)
        size += len(row['quote'])
    if rows:
        chunks.append({'project_id': material['project_id'], 'name': material['name'], 'evidence': rows})
    for i, chunk in enumerate(chunks):
        chunk.update(part=i + 1, total_parts=len(chunks))
    return chunks
