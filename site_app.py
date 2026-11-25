"""Invitation-only gateway; legacy analysis state is isolated per process/user."""
import asyncio
from functools import lru_cache
import gzip
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
import secrets
import shutil
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from site_store import Store, SiteError
from site_boundary import is_audio_request
from backend_observability import request_id, setup_request_tracking, log_failure, log_event

ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get('SITE_HOME', str(ROOT / '.site-data'))).resolve()
config_file = HOME / 'settings.json'
if config_file.exists():
    config = json.loads(config_file.read_text(encoding='utf-8'))
    endpoint = str(config.get('qwen_base_url', '')).strip()
    if endpoint:
        if urlsplit(endpoint).scheme != 'https' or not urlsplit(endpoint).hostname:
            raise RuntimeError('千问接口地址必须是HTTPS地址')
        os.environ.setdefault('QWEN_BASE_URL', endpoint)
ORIGIN = os.environ.get('SITE_ORIGIN', 'http://127.0.0.1:8765').rstrip('/')
COOKIE = 'wb_session_8765'
PENDING = 'wb_guest_pending'
DEV = os.environ.get('SITE_ALLOW_HTTP') == '1'
TEXT_ONLY = os.environ.get('WORKBENCH_TEXT_ONLY') == '1'
TEXT_ONLY_STYLE = '<style>#newProjectBtn,.system-card,#systemState,#gpuState{display:none!important}</style>'
GUEST_SINGLE_UI = '''<script>window.WORKBENCH_GUEST=true;history.replaceState(null,'','/'+(location.hash||''));</script><link rel="stylesheet" href="/assets/guest-lock.css?v=2"><style>
.nav-item[data-tab="matrix"],.nav-item[data-tab="projectManage"],
#focused,#matrix,#projectManage,#projectData,#editorImportAudio,#editorMembership,
#comparisonModeBtn,#comparisonTopActions,#comparisonWorkspace,#comparisonDialog,#compareMaterialsBtn{display:none!important}
</style>'''
if urlsplit(ORIGIN).scheme != 'https' and not (DEV and urlsplit(ORIGIN).hostname in ('127.0.0.1', 'localhost')):
    raise RuntimeError('请配置HTTPS的SITE_ORIGIN；本机测试可设置SITE_ALLOW_HTTP=1')
store = Store(HOME)
import site_guests as guests
guests.initialize(store)
workers = {}
transferring = set()
active_writes = {}
ui_files = StaticFiles(directory=ROOT / 'web')
UI_REF = re.compile(rb'((?:src|href)=["\x27]/assets/)([A-Za-z0-9_.-]+\.(?:js|css))(?:\?[^"\x27]*)?(?=["\x27])')
UI_LITERAL = re.compile(rb'(["\x27]/assets/)([A-Za-z0-9_.-]+\.(?:js|css))\?v=[A-Za-z0-9_.-]+(?=["\x27])')
HEAD_STYLE = re.compile(rb'<link rel="stylesheet" href="/assets/([A-Za-z0-9_.-]+\.css)(?:\?[^"]*)?">')
HEAD_BUNDLE = 'workbench-head.css'


def ui_entry(data):
    return hashlib.sha256(data).hexdigest()[:24], data


@lru_cache(maxsize=256)
def _ui_bytes(name, modified_ns, size):
    return ui_entry((ROOT / 'web' / name).read_bytes())


def versioned_ui(name, trail=()):
    if name == HEAD_BUNDLE:
        head = (ROOT / 'web' / 'index.html').read_bytes().partition(b'</head>')[0]
        items = [versioned_ui(match.decode('ascii')) for match in HEAD_STYLE.findall(head)]
        if items and all(items):
            return _head_bundle(tuple(items))
        return None
    item = (ROOT / 'web' / name)
    if item.is_symlink() or not item.is_file():
        return None
    info = item.stat()
    versioned = _ui_bytes(name, info.st_mtime_ns, info.st_size)
    if name.endswith('.js') and b'/assets/' in versioned[1] and len(trail)<8:
        def replace(match):
            target = match[2].decode('ascii')
            if target in (*trail,name):
                return match[0]
            child = versioned_ui(target, (*trail,name))
            return match[1]+match[2]+b'?rev='+child[0].encode('ascii') if child else match[0]
        result = UI_LITERAL.sub(replace, versioned[1])
        if result != versioned[1]:
            return ui_entry(result)
    return versioned


@lru_cache(maxsize=8)
def _head_bundle(items):
    return ui_entry(b'\n'.join(data for _,data in items))


def group_head_styles(html):
    head, end, rest = html.partition(b'</head>')
    if not end or not versioned_ui(HEAD_BUNDLE):
        return html
    matches = list(HEAD_STYLE.finditer(head))
    if len(matches)<2:
        return html
    # These shared links have no media attributes. Preserve their CSS order.
    first = matches[0]
    head = head[:first.start()] + b'<link rel="stylesheet" href="/assets/workbench-head.css">' + HEAD_STYLE.sub(b'', head[first.end():])
    return head + end + rest


@lru_cache(maxsize=128)
def compressed_ui(data):
    return gzip.compress(data, compresslevel=5, mtime=0)


def accepts_gzip(request):
    for part in request.headers.get('accept-encoding','').lower().split(','):
        name, *params = part.split(';')
        if name.strip() == 'gzip':
            return not params or any(re.fullmatch(r'q\s*=\s*(?:1(?:\.0*)?|0?\.\d*[1-9]\d*)', p.strip()) for p in params)
    return False


def version_ui_links(html):
    def replace(match):
        versioned = versioned_ui(match[2].decode('ascii'))
        return match[1] + match[2] + b'?rev=' + versioned[0].encode('ascii') if versioned else match[0]
    return UI_REF.sub(replace, html)
worker_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app):
    # A prior gateway crash can leave a loopback worker alive. Revoke and stop
    # verified guest processes before removing leases or accepting new requests.
    with store.db() as db:
        orphan_ids = [r[0] for r in db.execute('SELECT user_id FROM guest_workers')]
    for ident in orphan_ids:
        await stop_worker(ident)
    await recover_guest_transfers()
    with store.db(True) as db:
        db.execute('DELETE FROM guest_tasks')
    await cleanup_guests()
    task = asyncio.create_task(guest_janitor())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        for ident in list(workers):
            await stop_worker(ident)


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
auth_slots = asyncio.Semaphore(2)


async def stop_worker(ident):
    current = workers.pop(ident, None)
    if not current:
        with store.db() as db:
            old = db.execute('SELECT * FROM guest_workers WHERE user_id=?', (ident,)).fetchone()
        if old and guests.process_identity(old['pid']) == old['identity']:
            if os.name == 'nt':
                await asyncio.to_thread(subprocess.run,['taskkill','/PID',str(old['pid']),'/T','/F'],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            else:
                os.kill(old['pid'],9)
            for _ in range(100):
                if guests.process_identity(old['pid']) != old['identity']:break
                await asyncio.sleep(.05)
            else:raise RuntimeError('Could not stop orphan guest worker; cleanup deferred')
        with store.db(True) as db:
            db.execute('DELETE FROM guest_workers WHERE user_id=?',(ident,))
        return
    process, _, log, _ = current
    if process.poll() is None:
        if os.name == 'nt':
            await asyncio.to_thread(subprocess.run, ['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                    capture_output=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        else:
            process.kill()
        await asyncio.to_thread(process.wait, 15)
    log.close()
    with store.db(True) as db:
        db.execute('DELETE FROM guest_workers WHERE user_id=?',(ident,))


async def recover_guest_transfers():
    with store.db() as db:
        records = db.execute('SELECT t.*,g.state FROM guest_transfers t JOIN guests g ON g.user_id=t.user_id').fetchall()
    for row in records:
        await stop_worker(row['target_id'])
        if row['state'] == 'transferring':
            root,_ = store.data_root(row['target_id'])
            for relative in json.loads(row['paths']):
                path = (root / relative).resolve()
                if root.resolve() not in path.parents or len(Path(relative).parts)!=2:
                    raise RuntimeError('Unsafe transfer recovery path')
                if path.is_dir():shutil.rmtree(path)
                elif path.exists():path.unlink()
        with store.db(True) as db:
            db.execute("UPDATE guests SET state=CASE WHEN state='transferring' THEN 'active' ELSE 'expired' END,expires=CASE WHEN state='transferred' THEN ? ELSE expires END WHERE user_id=?",(time.time(),row['user_id']))
            db.execute('DELETE FROM guest_transfers WHERE user_id=?',(row['user_id'],))


async def cleanup_guests():
    async with worker_lock:
        with store.db(True) as db:
            rows = db.execute("SELECT user_id FROM guests WHERE state IN ('active','expired') AND expires<=?", (time.time(),)).fetchall()
            for row in rows:
                db.execute("UPDATE guests SET state='expired' WHERE user_id=?", (row['user_id'],))
                db.execute('DELETE FROM sessions WHERE user_id=?', (row['user_id'],))
        for row in rows:
            ident = row['user_id']
            await stop_worker(ident)
            target = (HOME / 'tenants' / ident).resolve()
            if target.parent != (HOME / 'tenants').resolve() or not ident.startswith('guest_'):
                raise RuntimeError('Refusing unsafe guest cleanup')
            if target.exists():
                await asyncio.to_thread(shutil.rmtree, target)
            log_path = HOME / 'logs' / (ident+'.log')
            if log_path.exists():
                log_path.unlink()
            with store.db(True) as db:
                db.execute('DELETE FROM guest_tasks WHERE user_id=?', (ident,))
                db.execute('UPDATE users SET active=0 WHERE id=? AND role=\'guest\'', (ident,))
                db.execute("UPDATE guests SET state='cleaned' WHERE user_id=?", (ident,))


async def guest_janitor():
    while True:
        await asyncio.sleep(30)
        try:
            await cleanup_guests()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Guest cleanup failed; will retry')


async def worker(user_id):
    async with worker_lock:
        current = workers.get(user_id)
        if current and current[0].poll() is None:
            return current[1]
        if current:
            current[2].close()
        tenant, owner = store.data_root(user_id)
        tenant.mkdir(parents=True, exist_ok=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        secret = secrets.token_urlsafe(32)
        env = {**os.environ, 'SITE_HOME': str(HOME), 'SITE_USER_ID': user_id,
               'WORKBENCH_DATA_DIR': str(tenant), 'SITE_WORKER_PORT': str(port),
               'SITE_WORKER_SECRET': secret, 'SITE_IS_OWNER': '1' if owner else '0'}
        logs = HOME / 'logs'
        logs.mkdir(exist_ok=True)
        log = (logs / (user_id+'.log')).open('ab')
        process = subprocess.Popen([sys.executable, str(ROOT / 'site_worker.py')], cwd=str(tenant), env=env,
                                   stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        workers[user_id] = process, port, log, secret
        with store.db(True) as db:
            role = db.execute('SELECT role FROM users WHERE id=?',(user_id,)).fetchone()
            if role:
                identity=guests.process_identity(process.pid)
                if not identity:
                    process.kill()
                    raise SiteError('无法核实临时服务身份，请稍后重试',503)
                db.execute('INSERT OR REPLACE INTO guest_workers VALUES(?,?,?)',(user_id,process.pid,identity))
        for _ in range(150):
            if process.poll() is not None:
                raise SiteError('分析服务启动失败，请联系管理员', 503)
            try:
                reader, writer = await asyncio.open_connection('127.0.0.1', port)
                writer.close()
                await writer.wait_closed()
                return port
            except OSError:
                await asyncio.sleep(.1)
        process.terminate()
        raise SiteError('分析服务启动超时，请重试', 503)


@app.middleware('http')
async def security(request, call_next):
    try:
        if request.headers.get('host') != urlsplit(ORIGIN).netloc:
            raise SiteError('访问地址不正确', 400)
        user = None if request.url.path == '/health' else store.session(request.cookies.get(COOKIE, ''))
        request.state.user = user
        if user and user['id'] in transferring:
            raise SiteError('资料正在保留到账号，请稍后刷新', 409)
        public = request.url.path in ('/account', '/auth/login', '/auth/redeem', '/auth/reset-password', '/auth/guest', '/auth/logout', '/health')
        if not public and not user:
            response = HTMLResponse('<script>location.replace("/account")</script>', status_code=401) if request.url.path == '/' else JSONResponse({'detail': '请先登录'}, status_code=401)
            response.headers['Cache-Control'] = 'no-store'
            return response
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if request.headers.get('origin') != ORIGIN:
                raise SiteError('请求来源无效', 403)
            if (not public or (request.url.path == '/auth/logout' and user)) and (not user or request.headers.get('x-csrf-token') != user['csrf']):
                raise SiteError('登录校验已失效，请刷新页面', 403)
        response = await call_next(request)
    except SiteError as exc:
        if exc.status >= 500:
            log_failure('gateway_error', exc, status=exc.status)
        response = JSONResponse({'detail': str(exc)}, status_code=exc.status)
    cache_control = 'no-store'
    if getattr(request.state, 'static_ui', False) and response.status_code in (200,304):
        cache_control = ('private, max-age=31536000, immutable' if getattr(request.state, 'versioned_ui', False)
                         else 'private, no-cache')
    response.headers.update({'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
                             'Referrer-Policy': 'same-origin', 'Cache-Control': cache_control})
    return response


setup_request_tracking(app, 'gateway')


@app.get('/health')
def health():
    checks = {}
    try:
        # mode=ro must not create a missing database or run Store initialization.
        with contextlib.closing(sqlite3.connect(store.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=.25)) as db:
            db.execute('SELECT 1 FROM users LIMIT 1').fetchall()
        checks['accounts'] = True
    except Exception as exc:
        checks['accounts'] = False
        log_failure('health_accounts_failed', exc)
    try:
        checks['disk'] = shutil.disk_usage(HOME).free >= 100 * 1024 * 1024
    except OSError as exc:
        checks['disk'] = False
        log_failure('health_disk_failed', exc)
    # Observe only already-known processes; never start or contact a worker.
    try:
        checks['workers'] = all(item[0].poll() is None for item in list(workers.values()))
    except Exception as exc:
        checks['workers'] = False
        log_failure('health_workers_failed', exc)
    ok = all(checks.values())
    return JSONResponse({'ok': ok, 'checks': checks}, status_code=200 if ok else 503)


@app.get('/account', response_class=HTMLResponse)
def account(request: Request):
    user = request.state.user
    state = json.dumps({'role': user['role']} if user else None)
    html = (ROOT / 'web' / 'account-center.html').read_text(encoding='utf-8')
    return html.replace('<head>', '<head><script>window.workbenchLoginSession=' + state + ';</script>', 1)


async def small_json(request):
    raw = await bounded_body(request, 8192)
    import json
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (ValueError, UnicodeError):
        raise SiteError('请求格式无效')


async def bounded_body(request, limit):
    parts, size = [], 0
    async for part in request.stream():
        size += len(part)
        if size > limit:
            raise SiteError('请求内容超过大小限制', 413)
        parts.append(part)
    return b''.join(parts)


async def warm_login_worker(secret):
    user = store.session(secret)
    if user:
        with contextlib.suppress(SiteError, OSError):
            await worker(user['id'])


@app.post('/auth/{action}')
async def auth(action: str, request: Request):
    if action == 'logout':
        store.logout(request.cookies.get(COOKIE, ''))
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE)
        response.delete_cookie(PENDING)
        return response
    data = await small_json(request)
    if action == 'guest':
        if request.state.user:
            return JSONResponse({'ok': True})
        secret = guests.create(store, request.client.host)
    elif action == 'guest-transfer':
        return await guest_transfer(request)
    elif action == 'login':
        async with auth_slots:
            secret = await asyncio.to_thread(store.login, data.get('username', ''), data.get('password', ''), request.client.host)
    elif action in ('redeem', 'reset-password'):
        # Validate token before performing an expensive password derivation.
        from site_store import token_hash
        with store.db() as db:
            valid = db.execute('SELECT reset_id FROM invitations WHERE hash=? AND used IS NULL AND expires>?', (token_hash(str(data.get('token', ''))), time.time())).fetchone()
        reset_only = action == 'reset-password'
        if not valid or (reset_only and not valid['reset_id']):
            raise SiteError('链接无效、已使用或已过期')
        async with auth_slots:
            secret = await asyncio.to_thread(store.redeem, data.get('token', ''), data.get('password', ''), reset_only)
        if reset_only:
            return JSONResponse({'ok': True})
    elif action == 'change-password':
        user = request.state.user
        if user['role'] == 'guest':
            raise SiteError('访客空间没有账号密码', 403)
        async with auth_slots:
            await asyncio.to_thread(store.change_password, user['id'], request.cookies.get(COOKIE, ''), data.get('current_password'), data.get('new_password'))
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE)
        return response
    else:
        raise SiteError('未知操作', 404)
    old_guest = request.state.user and request.state.user['role'] == 'guest' and action in ('login','redeem')
    pending_guest = store.session(request.cookies.get(PENDING, ''))
    has_guest = bool(old_guest or (pending_guest and pending_guest['role']=='guest'))
    response = JSONResponse({'ok': True, 'has_guest': has_guest},
                            background=None if has_guest else BackgroundTask(warm_login_worker, secret))
    if old_guest:
        response.set_cookie(PENDING, request.cookies.get(COOKIE), max_age=86400, httponly=True, secure=not DEV, samesite='strict')
    response.set_cookie(COOKIE, secret, max_age=86400 if action=='guest' else 30*86400, httponly=True, secure=not DEV, samesite='strict')
    return response


def account_profile(request: Request):
    _, owner = store.data_root(request.state.user['id'])
    result = {**request.state.user, 'owns_existing_data': owner, 'usage': store.usage(request.state.user['id'])}
    if request.state.user['role'] == 'guest':
        result['guest'] = guests.info(store, request.state.user['id'])
        result['usage']['calls'] = result['guest']['calls']
    return result


@app.get('/auth/me')
def me(request: Request):
    return account_profile(request)


@app.get('/auth/users')
def users(request: Request):
    if request.state.user['role'] != 'admin':
        raise SiteError('需要管理员权限', 403)
    return store.users()


@app.get('/auth/usage')
def model_usage(request: Request, scope: str = 'self', days: int = 7):
    return store.model_usage(request.state.user['id'],scope,days)


@app.get('/auth/account-panel')
def account_panel(request: Request, scope: str = 'self', days: int = 7):
    usage = store.model_usage(request.state.user['id'], scope, days)
    return {'profile': account_profile(request), 'model_usage': usage}


@app.post('/auth/admin/{action}')
async def admin(action: str, request: Request):
    user = request.state.user
    if user['role'] != 'admin':
        raise SiteError('需要管理员权限', 403)
    data = await small_json(request)
    if action in ('invite', 'reset'):
        if action == 'reset' and (not isinstance(data.get('id'), str) or not data['id']):
            raise SiteError('请选择需要重设密码的账号')
        result = store.invite(data.get('username', ''), actor=user['id'],
                              calls=data.get('daily_calls', 80),
                              reset_id=data.get('id') if action == 'reset' else None)
        return {'url': ORIGIN + ('/account#reset=' if action == 'reset' else '/account#invite=') + result['token'], 'expires_at': result['expires_at']}
    if action == 'update':
        store.update_user(user['id'], data.get('id'), data.get('active'), data.get('daily_calls'))
        if not data.get('active') and data.get('id') in workers:
            # Do not kill active work on disable. Sessions and subsequent model
            # calls are revoked immediately; already-running writes may finish.
            pass
        return {'ok': True}
    raise SiteError('未知操作', 404)


async def guest_transfer(request: Request):
    target = request.state.user
    source = store.session(request.cookies.get(PENDING, ''))
    if target['role'] == 'guest' or not source or source['role'] != 'guest':
        raise SiteError('没有可保留的访客空间', 400)
    sid, tid = source['id'], target['id']
    async with worker_lock:
        if active_writes.get(tid, 0):
            raise SiteError('账号中有任务正在运行，请完成后再保留访客资料', 409)
        target_root,_ = store.data_root(tid)
        for metadata in (target_root/'projects').glob('*/project.json'):
            try:
                if json.loads(metadata.read_text(encoding='utf-8')).get('status') in ('running','queued'):
                    raise SiteError('账号中有转写任务，请完成后再保留访客资料',409)
            except (OSError,ValueError):
                raise SiteError('暂无法确认账号任务状态，请稍后重试',409)
        with store.db(True) as db:
            if db.execute('SELECT 1 FROM guest_tasks WHERE user_id=?', (sid,)).fetchone():
                raise SiteError('请等待访客任务完成，再保留资料', 409)
            if db.execute("SELECT 1 FROM calls WHERE user_id=? AND status='running'",(tid,)).fetchone():
                raise SiteError('账号中有模型调用尚未结束，请稍后再保留资料',409)
            guests.info(store, sid)
            db.execute("UPDATE guests SET state='transferring' WHERE user_id=?", (sid,))
        transferring.update((sid, tid))
        copied = []
        try:
            await stop_worker(sid)
            await stop_worker(tid)
            source_root = (HOME / 'tenants' / sid).resolve()
            target_root, _ = store.data_root(tid)
            plans = []
            for name in ('projects','research_projects','research_project_files'):
                folder = source_root / name
                for item in folder.iterdir() if folder.exists() else []:
                    dest = target_root / name / item.name
                    if dest.exists():
                        # Some tools create empty shared containers at import.
                        # No guest content lives in these; never replace a
                        # populated destination or merge ambiguous records.
                        if item.is_dir() and not any(item.iterdir()):
                            continue
                        raise SiteError('项目编号冲突（'+item.name+'），尚未合并；请先导出访客资料', 409)
                    plans.append((item,dest))
            with store.db(True) as db:
                db.execute('INSERT INTO guest_transfers VALUES(?,?,?)',(sid,tid,json.dumps([str(dest.relative_to(target_root)) for _,dest in plans])))
            for item,dest in plans:
                dest.parent.mkdir(parents=True,exist_ok=True)
                copied.append(dest)
                if item.is_dir():
                    shutil.copytree(item,dest)
                else:
                    shutil.copy2(item,dest)
            with store.db(True) as db:
                db.execute("UPDATE guests SET state='transferred' WHERE user_id=?", (sid,))
                db.execute('UPDATE users SET active=0 WHERE id=?', (sid,))
                db.execute('DELETE FROM sessions WHERE user_id=?', (sid,))
                db.execute('INSERT INTO audit VALUES(?,?,?,?)', (time.time(),tid,'retain_guest',sid))
        except BaseException:
            for dest in reversed(copied):
                if dest.is_dir(): shutil.rmtree(dest)
                elif dest.exists(): dest.unlink()
            with store.db(True) as db:
                db.execute("UPDATE guests SET state='active' WHERE user_id=? AND state='transferring'", (sid,))
                db.execute('DELETE FROM guest_transfers WHERE user_id=?',(sid,))
            raise
        finally:
            transferring.difference_update((sid,tid))
    # Source is now revoked. Janitor deletes the redundant temporary copy.
    with store.db(True) as db:
        db.execute("UPDATE guests SET state='expired',expires=? WHERE user_id=?", (time.time(),sid))
        db.execute('DELETE FROM guest_transfers WHERE user_id=?',(sid,))
    response = JSONResponse({'ok':True})
    response.delete_cookie(PENDING)
    return response


SESSION_SCRIPT = '''<script data-workbench-accounts>(()=>{
const f=window.fetch.bind(window),session=window.workbenchSession;
window.fetch=async(input,opts={})=>{
 const u=new URL(typeof input==='string'?input:input.url,location.href);
 if(u.origin===location.origin&&!['GET','HEAD','OPTIONS'].includes((opts.method||(input instanceof Request?input.method:'GET')).toUpperCase())){
  opts.headers=new Headers(opts.headers||(input instanceof Request?input.headers:undefined));opts.headers.set('X-CSRF-Token',session.csrf);
 }
 const result=await f(input,opts);if(result.status===401&&u.origin===location.origin)location.replace('/account');return result;
};
// One fresh, authenticated library read while the shared UI assets are loading.
window.workbenchInitialLibrary=window.fetch(session.role==='guest'?'/api/library-bootstrap-guest':'/api/library-bootstrap').then(r=>r.ok?r.json():null).catch(()=>null);
addEventListener('pageshow',e=>{if(e.persisted)location.reload()});
let lastFocusCheck=Date.now(),checking=false;
addEventListener('focus',async()=>{if(checking||Date.now()-lastFocusCheck<20000)return;checking=true;lastFocusCheck=Date.now();try{const r=await f('/auth/me');if(r.status===401||(r.ok&&(await r.json()).id!==session.id))location.replace('/account')}catch{}finally{checking=false}});
})();</script><script defer src="/assets/guest-mode.js?v=20261109-expiry-1"></script>'''


def workspace_html(content, request, text_only, guest_style):
    session = request.state.user
    boot = {key: session[key] for key in ('id', 'username', 'role', 'csrf')}
    if session['role'] == 'guest':
        boot['guest'] = {'expires': guests.info(store, session['id'])['expires']}
    script = '<script>window.workbenchSession=' + json.dumps(boot, ensure_ascii=True).replace('<', r'\u003c') + ';</script>'
    prefix = '<head>' + script + SESSION_SCRIPT + (TEXT_ONLY_STYLE if text_only else '') + guest_style
    return version_ui_links(group_head_styles(content).replace(b'<head>', prefix.encode(), 1))


@app.api_route('/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'])
async def proxy(path: str, request: Request):
    user = request.state.user
    if user['role'] != 'guest':
        if request.method in ('GET','HEAD'):
            return await proxy_upstream(path,request)
        ident=user['id']
        active_writes[ident]=active_writes.get(ident,0)+1
        pending=False
        try:
            response=await proxy_upstream(path,request)
            if isinstance(response,StreamingResponse):
                original=response.body_iterator
                background=response.background
                async def tracked():
                    try:
                        async for chunk in original:yield chunk
                    finally:
                        try:
                            if background:await background()
                        finally:active_writes[ident]-=1
                response.body_iterator=tracked()
                response.background=None
                pending=True
            return response
        finally:
            if not pending:active_writes[ident]-=1
    if request.method in ('GET', 'HEAD') and path == 'api/research-projects':
        # Shared workspace compatibility; old guest projects remain on disk for transfer.
        return JSONResponse([])
    if request.method == 'POST' and path.startswith('api/projects/') and path.endswith('/coding-suggestions'):
        raise SiteError('访客可手动编码；登录后可使用 AI 编码', 403)
    if not guests.allowed(path, request.method):
        raise SiteError('访客仅开放文本导入、AI 文字校订和单篇访谈分析；其他功能请登录后使用', 403)
    if request.method in ('GET', 'HEAD'):
        return await proxy_upstream(path, request)
    lease = guests.acquire(store, user['id'])
    streaming = False
    try:
        raw = await bounded_body(request, 10*1024*1024+256*1024)
        request._body = raw
        if 'multipart/form-data' in request.headers.get('content-type', ''):
            form = await request.form(max_files=5, max_fields=20)
            count, size = 0, 0
            try:
                import io, zipfile
                for _, item in form.multi_items():
                    if not hasattr(item, 'filename') or not item.filename:
                        continue
                    suffix = Path(item.filename).suffix.lower()
                    if suffix not in ('.txt', '.docx'):
                        raise SiteError('访客仅支持TXT和DOCX文本', 400)
                    content = await item.read()
                    count += 1
                    size += len(content)
                    if suffix == '.docx':
                        try:
                            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                                if sum(i.file_size for i in archive.infolist()) > 20*1024*1024:
                                    raise SiteError('DOCX解压内容过大', 413)
                        except zipfile.BadZipFile:
                            raise SiteError('DOCX文件格式无效', 400)
                guests.uploads(store, user['id'], count, size)
            finally:
                await form.close()
        response = await proxy_upstream(path, request)
        if isinstance(response, StreamingResponse):
            streaming = True
            original = response.body_iterator
            background = response.background
            async def guarded():
                completed = False
                try:
                    async for chunk in original:
                        yield chunk
                    completed = True
                finally:
                    if not completed:
                        async with worker_lock:
                            await stop_worker(user['id'])
                    if background:
                        await background()
                    guests.release(store, user['id'], lease)
            response.body_iterator = guarded()
            response.background = None
        return response
    except BaseException:
        async with worker_lock:
            await stop_worker(user['id'])
        raise
    finally:
        if not streaming:
            guests.release(store, user['id'], lease)


async def proxy_upstream(path: str, request: Request):
    if path and not path.startswith(('api/', 'assets/')):
        raise SiteError('页面不存在', 404)
    # Hosted trial deliberately excludes local GPU/audio processing and large uploads.
    _, owner = store.data_root(request.state.user['id'])
    guest_style = GUEST_SINGLE_UI if request.state.user['role'] == 'guest' else ''
    text_only = TEXT_ONLY or not owner
    if text_only and is_audio_request(path, request.method):
        raise SiteError('账号试用版暂仅支持文本访谈分析', 403)
    # Only ship the shared UI here; account/session checks above still apply
    # even to a conditional request. Never cache HTML or a research response.
    if request.method in ('GET','HEAD'):
        if not path:
            if request.state.user['role'] == 'guest' and request.query_params.get('guest') != '1':
                return HTMLResponse(account(request))
            content = (ROOT / 'web' / 'index.html').read_bytes()
            return HTMLResponse(workspace_html(content, request, text_only, guest_style))
        name = path.removeprefix('assets/')
        if path.startswith('assets/') and name==Path(name).name and Path(name).suffix in ('.js','.css'):
            request.state.static_ui=True
            rev = request.query_params.get('rev')
            if rev and re.fullmatch(r'[0-9a-f]{24}', rev):
                versioned = versioned_ui(name)
                if versioned and versioned[0] == rev:
                    request.state.versioned_ui = True
                    data = versioned[1]
                    zipped = len(data)>1024 and accepts_gzip(request)
                    tag = '"' + rev + ('-gzip' if zipped else '') + '"'
                    headers = {'ETag': tag, 'Vary':'Accept-Encoding'}
                    if tag in [part.strip() for part in request.headers.get('if-none-match', '').split(',')]:
                        return Response(status_code=304, headers=headers)
                    if zipped:
                        data = compressed_ui(data)
                        headers['Content-Encoding'] = 'gzip'
                    headers['Content-Length'] = str(len(data))
                    return Response(data if request.method == 'GET' else b'', headers=headers,
                                    media_type='text/css' if name.endswith('.css') else 'text/javascript')
            if name == HEAD_BUNDLE:
                raise SiteError('界面资源已更新，请刷新页面',404)
            return await ui_files.get_response(name,request.scope)
    if request.method in ('GET','HEAD'):
        body = None
    elif not text_only:
        limit=2*1024**3
        try:
            declared_size=int(request.headers.get('content-length','0'))
        except ValueError:
            raise SiteError('上传长度格式无效',400)
        if declared_size < 0:
            raise SiteError('上传长度格式无效',400)
        if declared_size > limit:
            raise SiteError('上传文件超过2GB限制',413)
        async def upload_stream():
            size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>limit:raise SiteError('上传文件超过2GB限制',413)
                yield chunk
        body=upload_stream()
    else:
        body = await bounded_body(request, 10 * 1024 * 1024 + (256*1024 if request.state.user['role']=='guest' else 0))
    port = await worker(request.state.user['id'])
    headers = {k: v for k, v in request.headers.items() if k.lower() in ('content-type', 'accept', 'range')}
    headers['X-Workbench-Worker'] = workers[request.state.user['id']][3]
    headers['X-Request-ID'] = request_id.get()
    client=httpx.AsyncClient(trust_env=False, timeout=1800)
    try:
        req=client.build_request(request.method,f'http://127.0.0.1:{port}/{path}',params=request.query_params,content=body,headers=headers)
        result=await client.send(req,stream=True)
    except Exception as exc:
        log_failure('gateway_proxy_failed', exc)
        await client.aclose()
        raise
    async def close_upstream():
        await result.aclose()
        await client.aclose()
    async def upstream_body():
        try:
            async for chunk in result.aiter_bytes():
                yield chunk
            log_event('gateway_body_completed', status=result.status_code)
        except Exception as error:
            log_failure('gateway_stream_failed', error, status=result.status_code)
            raise
        finally:
            await close_upstream()
    output_headers = {k: v for k, v in result.headers.items() if k.lower() in ('content-type', 'content-disposition', 'content-range', 'accept-ranges')}
    if result.status_code >= 500:
        log_event('gateway_upstream_error', status=result.status_code)
    if not path and 'text/html' in result.headers.get('content-type', ''):
        content=await result.aread()
        await close_upstream()
        return Response(workspace_html(content, request, text_only, guest_style),status_code=result.status_code,headers=output_headers)
    return StreamingResponse(upstream_body(),status_code=result.status_code,headers=output_headers)

