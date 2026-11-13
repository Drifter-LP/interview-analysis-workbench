"""Recoverable library deletion; never leave analyses with missing evidence."""
import copy
import json
import shutil
import time
import uuid
from pathlib import Path
import threading

TRASH_LOCK = threading.RLock()
RETENTION_SECONDS = 7 * 86400


def references(value, interview_id):
    if isinstance(value, dict):
        return interview_id in value or any(references(v, interview_id) for v in value.values())
    if isinstance(value, list):
        return any(references(v, interview_id) for v in value)
    return value == interview_id


def archive_interview(app_dir, projects_dir, research_dir, files_dir, interview_id):
    from interview_reference_index import INDEX_LOCK
    with TRASH_LOCK, INDEX_LOCK:
        return _archive_interview(app_dir, projects_dir, research_dir, files_dir, interview_id)


def _archive_interview(app_dir, projects_dir, research_dir, files_dir, interview_id):
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
    from interview_reference_index import get_index
    index=get_index(app_dir,files_dir)
    index_inventory=None;index_mode='indexed'
    try:
        result_paths,index_inventory=index.candidates(interview_id)
    except Exception:
        import logging
        logging.exception('关联索引校验失败，回退完整扫描')
        result_paths=list(Path(files_dir).rglob('*.json'));index_mode='full_scan_fallback'
    for path in result_paths:
        if path.is_symlink():
            continue
        try:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError, OSError):
            continue
        if references(value, interview_id):
            moves.append((path, archive / 'results' / path.relative_to(files_dir)))
    if index_inventory is not None and index.inventory()!=index_inventory:
        raise ValueError('资料正在被其他程序修改，本次删除已停止，请稍后重试')
    archive.mkdir(parents=True)
    for path, original, item in changes:
        backup = archive / 'research_projects' / path.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding='utf-8')
        after = archive / 'after_research_projects' / path.name
        after.parent.mkdir(parents=True, exist_ok=True)
        after.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
    (archive / 'manifest.json').write_text(json.dumps({'interview_id': interview_id, 'reference_lookup':index_mode, 'index_stats':index.last_stats, 'moves': [[str(a), str(b)] for a,b in moves], 'research_projects': [str(p) for p,_,_ in changes]}, ensure_ascii=False, indent=2), encoding='utf-8')
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
    from theme_file_io import write_json
    deleted_at = time.time()
    name = json.loads((archive / 'interview/project.json').read_text(encoding='utf8')).get('name', interview_id)
    write_json(archive/'trash.json', {'id':archive.name, 'name':name, 'interview_id':interview_id,
                                   'deleted_at':deleted_at, 'expires_at':deleted_at+RETENTION_SECONDS,
                                   'status':'deleted'})
    return {'deleted': True, 'recoverable': True, 'affected_projects': len(changes),
            'reference_lookup':index_mode,
            'expires_at':deleted_at+RETENTION_SECONDS}


def trash_entry(app_dir, entry_id):
    root = (Path(app_dir)/'deleted_interviews').resolve()
    candidate = root/entry_id
    entry = candidate.resolve()
    if (candidate.is_symlink() or (hasattr(candidate,'is_junction') and candidate.is_junction())
            or entry.parent != root or not entry.is_dir()):
        raise ValueError('回收站条目不存在或编号无效')
    return entry


def list_trash(app_dir):
    result=[]
    root=Path(app_dir)/'deleted_interviews'
    for entry in root.iterdir() if root.exists() else []:
        try:
            entry=trash_entry(app_dir,entry.name)
            if not (entry/'interview/project.json').is_file():
                continue
            if (entry/'trash.json').exists():
                item=json.loads((entry/'trash.json').read_text(encoding='utf8'))
                if item.get('status')!='deleted':continue
            else:
                # Never silently apply a new expiry policy to old recovery backups.
                meta=json.loads((entry/'interview/project.json').read_text(encoding='utf8'))
                item={'id':entry.name,'name':meta.get('name','未命名访谈'),
                      'deleted_at':entry.stat().st_mtime,'expires_at':None,'legacy':True}
            result.append(item)
        except (ValueError,OSError):continue
    return sorted(result,key=lambda x:x['deleted_at'],reverse=True)


def merge_restoration(before, after, current):
    """Undo only deletion's delta, not subsequent research edits."""
    if before==after:return copy.deepcopy(current)
    if current==after or current==before:return copy.deepcopy(before)
    if isinstance(before,list) and isinstance(after,list) and isinstance(current,list):
        restored=copy.deepcopy(current)
        for item in before:
            if item not in after and item not in restored:
                if isinstance(item,dict):
                    for old in restored:
                        if isinstance(old,dict) and any(item.get(k) and item.get(k)==old.get(k) for k in ['id','run_id','file','workspace_project_id']):
                            raise ValueError('原项目存在同名或已修改的研究记录，已停止恢复，未覆盖数据')
                restored.append(copy.deepcopy(item))
        return restored
    if all(isinstance(x,dict) for x in [before,after,current]):
        restored=copy.deepcopy(current)
        for key,value in before.items():
            if key=='updated_at':continue
            if key not in after:
                if key not in current:restored[key]=copy.deepcopy(value)
                elif current[key]!=value:raise ValueError('原项目字段存在冲突，已停止恢复')
            elif value!=after[key]:
                if key not in current:raise ValueError('原项目结构已改变，已停止恢复')
                restored[key]=merge_restoration(value,after[key],current[key])
        return restored
    raise ValueError('原项目数据已更新且存在恢复冲突，已停止恢复')


def restore_interview(app_dir, projects_dir, research_dir, files_dir, entry_id):
    from theme_file_io import write_json
    with TRASH_LOCK:
        entry=trash_entry(app_dir,entry_id)
        info_path=entry/'trash.json'
        if not info_path.exists():
            # Old archives have no reliable post-delete baseline. Restore the
            # interview itself, retaining all project snapshots in the archive.
            source=entry/'interview'
            meta=json.loads((source/'project.json').read_text(encoding='utf8'))
            root=Path(projects_dir).resolve();target=(root/str(meta['id'])).resolve()
            if target.parent!=root or target.exists():raise ValueError('恢复位置无效或已有同名访谈，未覆盖')
            shutil.move(str(source),str(target))
            try:write_json(info_path,{'status':'restored','restored_at':time.time(),'legacy':True})
            except Exception:
                shutil.move(str(target),str(source));raise
            return {'restored':True,'interview_id':meta['id'],
                    'message':'旧访谈已恢复；原项目关联未自动恢复，历史分析备份仍保留'}
        info=json.loads(info_path.read_text(encoding='utf8')) if info_path.exists() else {'status':'deleted'}
        if info.get('status')!='deleted':raise ValueError('该访谈已经恢复')
        if info.get('expires_at') and info['expires_at']<=time.time():raise ValueError('该访谈已超过七天保留期')
        manifest=json.loads((entry/'manifest.json').read_text(encoding='utf8'))
        moves=[]; updates=[]
        project_root=Path(projects_dir).resolve(); files_root=Path(files_dir).resolve()
        for original,archived in manifest['moves']:
            src=Path(archived).resolve(); dst=Path(original).resolve()
            if not src.is_relative_to(entry) or not (dst.is_relative_to(files_root) or dst.parent==project_root):
                raise ValueError('恢复路径无效')
            if not src.exists():raise ValueError('归档文件缺失，已停止恢复')
            if dst.exists():raise ValueError('恢复位置已有同名文件，未覆盖，请先核查')
            moves.append((src,dst))
        for snapshot in (entry/'research_projects').glob('*.json'):
            path=Path(research_dir)/snapshot.name
            if not path.exists():raise ValueError('原研究项目已删除，请先核查项目后恢复')
            before=json.loads(snapshot.read_text(encoding='utf8'))
            after_path=entry/'after_research_projects'/snapshot.name
            if not after_path.exists():raise ValueError('旧归档缺少安全恢复信息，需要人工恢复项目关联')
            current=json.loads(path.read_text(encoding='utf8'))
            after=json.loads(after_path.read_text(encoding='utf8'))
            restored=merge_restoration(before,after,current);restored['updated_at']=time.time()
            updates.append((path,current,restored))
        completed=[]
        try:
            for src,dst in moves:
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.move(str(src),str(dst));completed.append((src,dst))
            for path,_,restored in updates:write_json(path,restored)
            write_json(info_path,{**info,'status':'restored','restored_at':time.time()})
        except Exception:
            for path,old,_ in updates:write_json(path,old)
            for src,dst in reversed(completed):
                src.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(dst),str(src))
            raise
        return {'restored':True,'interview_id':manifest['interview_id']}


def purge_expired(app_dir, now=None):
    now=time.time() if now is None else now
    removed=[]
    with TRASH_LOCK:
        for item in list_trash(app_dir):
            expiry=item.get('expires_at')
            if not isinstance(expiry,(float,int)) or expiry>now:continue
            entry=trash_entry(app_dir,item['id'])
            # Validate every resolved target before recursive removal on Windows.
            if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction())
                   or not p.resolve().is_relative_to(entry) for p in entry.rglob('*')):
                continue
            shutil.rmtree(entry)
            removed.append(item['id'])
    return removed
