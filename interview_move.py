"""Move a library membership, never delete transcript or historical evidence."""
import json
import threading
import time
from fastapi import HTTPException
from pydantic import BaseModel


class MoveRequest(BaseModel):
    source_project: str = ''
    target_project: str
    interview_id: str = ''
    uploaded_index: int | None = None


def register_interview_move(app, project_path, metadata_path, prepare):
    lock = threading.Lock()

    @app.post('/api/interviews/move')
    def move(body: MoveRequest):
        with lock:
            if body.source_project == body.target_project:
                raise HTTPException(400, '访谈稿已在该项目中')
            target_path = project_path(body.target_project)
            if not target_path.exists():
                raise HTTPException(404, '目标项目不存在')
            source_path = project_path(body.source_project) if body.source_project else None
            if source_path and not source_path.exists():
                raise HTTPException(404, '原项目不存在')
            source = json.loads(source_path.read_text(encoding='utf-8')) if source_path else None
            interview_id = body.interview_id
            if body.uploaded_index is not None:
                if not source:
                    raise HTTPException(400, '上传访谈缺少原项目')
                interview_id = prepare(body.source_project, body.uploaded_index)['project_id']
                source = json.loads(source_path.read_text(encoding='utf-8'))
            if not interview_id or not metadata_path(interview_id).exists():
                raise HTTPException(404, '访谈稿不存在')
            metadata = json.loads(metadata_path(interview_id).read_text(encoding='utf-8'))
            if metadata.get('status') in ('queued', 'running'):
                raise HTTPException(409, '请等待访谈处理完成后再移动')
            if source:
                uploads = source.get('uploaded_transcripts', [])
                if interview_id not in source.get('interview_ids', []) and not any(u.get('workspace_project_id') == interview_id for u in uploads):
                    raise HTTPException(409, '该访谈已不在原项目，请刷新列表')
                source['interview_ids'] = [i for i in source.get('interview_ids', []) if i != interview_id]
                source['uploaded_transcripts'] = [u for u in uploads if u.get('workspace_project_id') != interview_id]
                source.get('material_types', {}).pop(interview_id, None)
                source['updated_at'] = time.time()
            target = json.loads(target_path.read_text(encoding='utf-8'))
            if interview_id not in target.get('interview_ids', []) and not any(u.get('workspace_project_id') == interview_id for u in target.get('uploaded_transcripts', [])):
                target.setdefault('interview_ids', []).append(interview_id)
                target.setdefault('material_types', {})[interview_id] = 'interview'
            target['updated_at'] = time.time()
            paths = [(target_path, target)] + ([(source_path, source)] if source_path else [])
            originals = {p: p.read_bytes() for p, _ in paths}
            try:
                for path, value in paths:
                    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                for path, original in originals.items():
                    path.write_bytes(original)
                raise
            return {'moved': True, 'interview_id': interview_id}
