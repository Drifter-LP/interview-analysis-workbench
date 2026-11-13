"""Fail closed for enabled installations and authenticate private worker requests."""
import hmac
import os
from pathlib import Path
from fastapi.responses import JSONResponse


def is_audio_request(path, method):
    path = path.strip('/').lower()
    return (path == 'api/projects' and method == 'POST') or any(
        term in path for term in ('audio', 'transcrib', 'transcription', 'align', 'recording'))


def protect_worker(app):
    token = os.environ.get('SITE_WORKER_SECRET', '')
    text_only = os.environ.get('WORKBENCH_TEXT_ONLY') == '1'
    if text_only and not token:
        raise RuntimeError('文本部署只能通过账号网关启动，禁止直接公开分析服务')
    enabled = (Path(__file__).resolve().parent / '.site-data' / 'enabled.json').exists()
    # The supported public entrypoint is run_accounts.py, never web_app:app.
    if enabled and not token and Path(getattr(__import__('__main__'),'__file__','')).resolve() != Path(__file__).with_name('web_app.py').resolve():
        raise RuntimeError('账号模式已启用，请通过run_accounts.py启动，不能直接公开web_app:app')
    if token:
        @app.middleware('http')
        async def private_worker(request, call_next):
            if not hmac.compare_digest(request.headers.get('x-workbench-worker', ''), token):
                return JSONResponse({'detail': '请通过登录入口访问'}, status_code=401)
            if text_only and is_audio_request(request.url.path, request.method):
                return JSONResponse({'detail': '线上工作台仅支持文本访谈分析'}, status_code=403)
            return await call_next(request)
