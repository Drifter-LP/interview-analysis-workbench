"""Recoverable library deletion; never leave analyses with missing evidence."""
import copy
import json
import shutil
import time
import uuid
from pathlib import Path


def references(value, interview_id):
    if isinstance(value, dict):
        return interview_id in value or any(references(v, interview_id) for v in value.values())
    if isinstance(value, list):
        return any(references(v, interview_id) for v in value)
    return value == interview_id


def archive_interview(app_dir, projects_dir, research_dir, files_dir, interview_id):
    projects_dir = Path(projects_dir).resolve()
    source = (projects_dir / interview_id).resolve()
    if source.parent != projects_dir or not (source / 'project.json').is_file():
        raise ValueError('访谈不存在或编号无效')
    archive = Path(app_dir) / 'deleted_interviews' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex)
    changes, moves = [], [(source, archive / 'interview')]
    for path in Path(research_dir).glob('*.json'):
        original = json.loads(path.read_text(encoding='utf-8'))
        item = copy.deepcopy(original)
        item['interview_ids'] = [i for i in item.get('interview_ids', []) if i != interview_id]
        item.get('material_types', {}).pop(interview_id, None)
        uploads = []
        for material in item.get('uploaded_transcripts', []):
            if material.get('workspace_project_id') != interview_id:
                uploads.append(material)
                continue
            root = (Path(files_dir) / path.stem).resolve()
            upload = (root / str(material.get('file', ''))).resolve()
            if upload.parent != root:
                raise ValueError('访谈文件路径无效')
            if upload.is_file():
                moves.append((upload, archive / 'uploads' / path.stem / upload.name))
        item['uploaded_transcripts'] = uploads
        for key in ('theme_analyses', 'material_comparisons'):
            if key in item:
                item[key] = [r for r in item[key] if not references(r, interview_id)]
        if item != original:
            item['updated_at'] = time.time()
            changes.append((path, original, item))
    for path in Path(files_dir).rglob('*.json'):
        if path.is_symlink():
            continue
        try:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError, OSError):
            continue
        if references(value, interview_id):
            moves.append((path, archive / 'results' / path.relative_to(files_dir)))
    archive.mkdir(parents=True)
    for path, original, item in changes:
        backup = archive / 'research_projects' / path.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding='utf-8')
    (archive / 'manifest.json').write_text(json.dumps({'interview_id': interview_id, 'moves': [[str(a), str(b)] for a,b in moves], 'research_projects': [str(p) for p,_,_ in changes]}, ensure_ascii=False, indent=2), encoding='utf-8')
    completed = []
    try:
        for src, dst in moves:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            completed.append((src, dst))
        for path, _, item in changes:
            temporary = path.with_suffix('.delete-' + uuid.uuid4().hex + '.tmp')
            temporary.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)
    except Exception:
        for path, original, _ in changes:
            path.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding='utf-8')
        for src, dst in reversed(completed):
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
        raise
    return {'deleted': True, 'recoverable': True, 'affected_projects': len(changes)}
