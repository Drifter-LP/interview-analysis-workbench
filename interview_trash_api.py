"""Recycle-bin routes and service-owned periodic expiry, with no model calls."""
import logging
import threading
from fastapi import HTTPException
from interview_library import list_trash, restore_interview, purge_expired, TRASH_LOCK


def install(app, app_dir, projects_dir, research_dir, files_dir):
    stop=threading.Event()
    from interview_reference_index import get_index, INDEX_LOCK
    index=get_index(app_dir,files_dir)

    @app.get('/api/trash/interviews')
    def get_interview_trash():
        with TRASH_LOCK:
            purge_expired(app_dir)
            return {'items':list_trash(app_dir),'retention_days':7}

    @app.post('/api/trash/interviews/{entry_id}/restore')
    def restore(entry_id: str):
        try:
            return restore_interview(app_dir,projects_dir,research_dir,files_dir,entry_id)
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from exc

    def sweep():
        try:
            with INDEX_LOCK:index.refresh()
            logging.getLogger('uvicorn.error').info('访谈关联索引已就绪：%s',index.last_stats)
        except Exception:logging.exception('关联索引预建失败，删除时仍保留完整扫描回退')
        while not stop.is_set():
            try:purge_expired(app_dir)
            except Exception:logging.exception('回收站到期清理失败，保留文件等待下次重试')
            stop.wait(3600)

    @app.on_event('startup')
    def start_cleanup():
        stop.clear()
        threading.Thread(target=sweep,name='interview-trash-expiry',daemon=True).start()

    @app.on_event('shutdown')
    def stop_cleanup():
        stop.set()
