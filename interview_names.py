"""Stable display-name disambiguation, without merging source records."""
import hashlib
import json
import threading
import time
import uuid
from functools import lru_cache
from pathlib import Path

_lock = threading.RLock()


@lru_cache(maxsize=512)
def digest(path, size, stamp):
    text = Path(path).read_text(encoding='utf-8-sig').replace('\r\n', '\n').strip()
    return hashlib.sha256(text.encode()).hexdigest() if text else None


def identity(path, fallback):
    if path and path.is_file():
        stat = path.stat()
        try:
            value = digest(str(path), stat.st_size, stat.st_mtime_ns)
            if value:
                return 'text:' + value
        except (OSError, UnicodeError):
            pass
    return fallback


def assignments(records):
    """Keep the highest-priority identity's name; suffix other identities."""
    groups = {}
    reserved = {r['name'] for r in records}
    result = {}
    for row in records:
        groups.setdefault(row['name'], {}).setdefault(row['identity'], []).append(row)
    for name, identities in sorted(groups.items()):
        ordered = sorted(identities.values(), key=lambda rows: (max(r['priority'] for r in rows), min(r['key'] for r in rows)), reverse=True)
        for rows in ordered[1:]:
            number = 1
            while name + f'（{number}）' in reserved:
                number += 1
            renamed = name + f'（{number}）'
            reserved.add(renamed)
            for row in rows:
                result[row['key']] = renamed
    return result


def normalize_names(projects_dir, research_dir, files_dir, archive_root, refresh_names):
    with _lock:
        documents, workspaces, memberships, records = {}, {}, {}, []
        for path in Path(projects_dir).glob('*/project.json'):
            if path.parent.is_symlink():
                continue
            data = json.loads(path.read_text(encoding='utf-8'))
            documents[path] = data
            workspaces[data['id']] = (path, data)
        research = {}
        for path in Path(research_dir).glob('*.json'):
            data = json.loads(path.read_text(encoding='utf-8'))
            documents[path] = data
            research[path] = data
            for key in data.get('interview_ids', []):
                memberships.setdefault(key, []).append(data)
            for material in data.get('uploaded_transcripts', []):
                if material.get('workspace_project_id'):
                    memberships.setdefault(material['workspace_project_id'], []).append(data)
        identities = {}
        def priority(owners):
            opened = max((o.get('last_opened_at', 0) or 0 for o in owners), default=0)
            return (2 if opened else 1 if owners else 0, opened)
        for key, (path, data) in workspaces.items():
            source = path.parent / '导入访谈稿.txt'
            if not source.exists():
                source = next(iter(sorted(path.parent.glob('*_Qwen3-ASR转录.txt')) + sorted(path.parent.glob('*_FunASR转录.txt'))), None)
            identities[key] = identity(source, 'workspace:' + key)
            records.append({'key': 'w:' + key, 'name': data.get('name', key), 'identity': identities[key], 'priority': priority(memberships.get(key, []))})
        for path, data in research.items():
            for index, material in enumerate(data.get('uploaded_transcripts', [])):
                key = material.get('workspace_project_id')
                root = (Path(files_dir) / path.stem).resolve()
                source = (root / str(material.get('file', ''))).resolve()
                if source.parent != root:
                    source = None
                records.append({'key': f'u:{path.stem}:{index}', 'name': material.get('name', ''), 'identity': identities.get(key) or identity(source, f'upload:{path.stem}:{index}'), 'priority': priority([data])})
        renamed = assignments(records)
        if not renamed:
            return {}
        originals = {p: p.read_text(encoding='utf-8') for p in documents}
        for key, (path, data) in workspaces.items():
            if 'w:' + key in renamed:
                data['name'] = renamed['w:' + key]
                for project in research.values():
                    refresh_names(project, key, data['name'])
        for path, data in research.items():
            for index, material in enumerate(data.get('uploaded_transcripts', [])):
                if f'u:{path.stem}:{index}' in renamed:
                    material['name'] = renamed[f'u:{path.stem}:{index}']
        changes = {p: json.dumps(d, ensure_ascii=False, indent=2) for p,d in documents.items() if json.loads(originals[p]) != d}
        backup = Path(archive_root) / ('names-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        backup.mkdir(parents=True)
        (backup / 'originals.json').write_text(json.dumps({str(p): originals[p] for p in changes}, ensure_ascii=False), encoding='utf-8')
        completed = []
        try:
            for path, text in changes.items():
                temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
                temporary.write_text(text, encoding='utf-8')
                temporary.replace(path)
                completed.append(path)
        except Exception:
            for path in completed:
                path.write_text(originals[path], encoding='utf-8')
            raise
        return renamed
