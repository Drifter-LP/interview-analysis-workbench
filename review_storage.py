"""Content-addressed review records; project JSON keeps only lightweight indexes."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

PROJECT_LOCK = threading.RLock()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def digest(record):
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def record_path(files_dir, project_id, analysis_id, storage_key):
    if not re.fullmatch(r'[A-Za-z0-9_\-\u4e00-\u9fff]+', project_id) or not re.fullmatch(r'[0-9a-f]{64}', storage_key):
        raise ValueError('无效核查档案编号')
    analysis_key = hashlib.sha256(analysis_id.encode('utf-8')).hexdigest()
    return Path(files_dir) / project_id / 'finding_reviews' / analysis_key / (storage_key + '.json')


def index_record(record, storage_key=None):
    keys = ('id', 'dimension_index', 'finding_index', 'saved_at', 'generated_at', 'model',
            'experiment_id', 'experimental', 'provider', 'input_mode', 'repeat')
    entry = {k: record[k] for k in keys if k in record}
    entry['item_count'] = len(record.get('items', []))
    entry['storage_key'] = storage_key
    if storage_key is None:
        entry['legacy_key'] = digest(record)
    return entry


def store(files_dir, pid, aid, record):
    key = digest(record)
    path = record_path(files_dir, pid, aid, key)
    if path.exists():
        if read_record(files_dir, pid, aid, key) != record:
            raise ValueError('已有核查档案内容不一致')
    else:
        atomic_json(path, record)
    return index_record(record, key)


def read_record(files_dir, pid, aid, key):
    path = record_path(files_dir, pid, aid, key)
    record = json.loads(path.read_text(encoding='utf-8'))
    if digest(record) != key:
        raise ValueError('核查档案完整性校验失败')
    return record


def indexes(analysis):
    rows = list(analysis.get('finding_review_index', [])) + [index_record(r) for r in analysis.get('finding_reviews', [])]
    return sorted(rows, key=lambda r: float(r.get('saved_at') or r.get('generated_at') or 0))


def project_listing(project):
    """Never send embedded review evidence as part of the project-list response."""
    result = dict(project)
    result['theme_analyses'] = []
    for analysis in project.get('theme_analyses', []):
        entry = {k: v for k, v in analysis.items() if k not in ('finding_reviews', 'finding_review_index')}
        entry['finding_review_index'] = indexes(analysis)
        result['theme_analyses'].append(entry)
    return result


def refresh_display_names(value, names):
    """One pass instead of one complete traversal per interview; skip immutable reviews."""
    if isinstance(value, list):
        for child in value:
            refresh_display_names(child, names)
    elif isinstance(value, dict):
        pid = value.get('project_id') or value.get('workspace_project_id')
        if isinstance(pid, str) and pid in names:
            for field in ('name', 'material_name'):
                if field in value:
                    value[field] = names[pid]
        for key, child in value.items():
            if key not in ('finding_reviews', 'finding_review_index') and isinstance(child, (dict, list)):
                refresh_display_names(child, names)


def rehome(analysis, files_dir, pid, new_id, legacy_records=()):
    """Saving an edited analysis creates a new ID; keep its archived reviews usable."""
    old_id = analysis.get('id')
    result = []
    for entry in analysis.get('finding_review_index', []):
        if entry.get('storage_key'):
            if not isinstance(old_id, str):
                raise ValueError('核查索引缺少原分析编号')
            record = read_record(files_dir, pid, old_id, entry['storage_key'])
            result.append(store(files_dir, pid, new_id, record))
        else:
            record = next((r for r in legacy_records if digest(r) == entry.get('legacy_key')), None)
            if record is None:
                raise ValueError('未找到旧版核查索引对应的完整记录')
            result.append(store(files_dir, pid, new_id, record))
    for record in analysis.get('finding_reviews', []):
        result.append(store(files_dir, pid, new_id, record))
    analysis.pop('finding_reviews', None)
    if result:
        analysis['finding_review_index'] = result
    return analysis


def migrate(project_path, files_dir, backup_path):
    """Copy, verify every record, then atomically replace main JSON. Preserve full backup."""
    path = Path(project_path)
    with PROJECT_LOCK:
        before = path.read_bytes()
        project = json.loads(before.decode('utf-8'))
        work = copy.deepcopy(project)
        count = 0
        for analysis in work.get('theme_analyses', []):
            records = analysis.get('finding_reviews', [])
            for record in records:
                entry = store(files_dir, path.stem, analysis['id'], record)
                if read_record(files_dir, path.stem, analysis['id'], entry['storage_key']) != record:
                    raise ValueError('转存内容核对失败，项目未替换')
                analysis.setdefault('finding_review_index', []).append(entry)
                count += 1
            analysis.pop('finding_reviews', None)
        if not count:
            return {'records': 0, 'before_bytes': len(before), 'after_bytes': len(before)}
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        with backup.open('xb') as handle:
            handle.write(before)
        if path.read_bytes() != before:
            raise RuntimeError('项目在转存期间发生变化，未替换主文件')
        atomic_json(path, work)
        return {'records': count, 'before_bytes': len(before), 'after_bytes': path.stat().st_size,
                'backup': str(backup)}
