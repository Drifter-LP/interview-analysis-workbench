"""Guest lifetime, upload accounting and task leases; no research text in SQLite."""
import secrets
import time
from pathlib import Path

from site_store import SiteError


def initialize(store):
    with store.db(True) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS guests(
          user_id TEXT PRIMARY KEY, expires REAL NOT NULL, state TEXT NOT NULL DEFAULT 'active',
          files INTEGER NOT NULL DEFAULT 0, bytes INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS guest_tasks(
          user_id TEXT PRIMARY KEY, token TEXT NOT NULL, heartbeat REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS guest_workers(
          user_id TEXT PRIMARY KEY, pid INTEGER NOT NULL, identity TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS guest_transfers(
          user_id TEXT PRIMARY KEY, target_id TEXT NOT NULL, paths TEXT NOT NULL);
        ''')


def create(store, peer):
    from site_store import token_hash
    now = time.time()
    ident = 'guest_' + secrets.token_hex(16)
    key = 'guest-start:' + token_hash(peer)
    with store.db(True) as db:
        # Abuse backstop only; a campus IP is not treated as an identity.
        db.execute('DELETE FROM failures WHERE at<?', (now-3600,))
        if db.execute('SELECT count(*) FROM failures WHERE key=? AND at>?', (key, now-3600)).fetchone()[0] >= 20:
            raise SiteError('临时空间创建过于频繁，请稍后再试或登录', 429)
        if db.execute("SELECT count(*) FROM guests WHERE state='active' AND expires>?", (now,)).fetchone()[0] >= 30:
            raise SiteError('访客空间暂满，请稍后再试或登录', 503)
        db.execute('INSERT INTO failures VALUES(?,?)', (key, now))
        db.execute('INSERT INTO users VALUES(?,?,?,\'guest\',1,20,0,?)', (ident, ident, '!no-password', now))
        db.execute('INSERT INTO guests(user_id,expires) VALUES(?,?)', (ident, now+86400))
    return store.new_session(ident)


def info(store, ident):
    with store.db() as db:
        row = db.execute('SELECT * FROM guests WHERE user_id=?', (ident,)).fetchone()
        calls = db.execute('SELECT coalesce(sum(calls),0) FROM usage WHERE user_id=?', (ident,)).fetchone()[0]
    if not row or row['state'] != 'active' or row['expires'] <= time.time():
        raise SiteError('访客空间已过期，请登录或重新创建临时空间', 401)
    return {**dict(row), 'calls': calls, 'limit': 20}


def acquire(store, ident):
    """A write request is the task boundary, including the entire upstream stream."""
    token = secrets.token_hex(16)
    with store.db(True) as db:
        row = db.execute('SELECT * FROM guests WHERE user_id=?', (ident,)).fetchone()
        if not row or row['state'] != 'active' or row['expires'] <= time.time():
            raise SiteError('访客空间已过期', 401)
        # Do not steal stale leases: cleanup must kill the old worker first.
        if db.execute('SELECT 1 FROM guest_tasks WHERE user_id=?', (ident,)).fetchone():
            raise SiteError('当前空间有任务正在运行，请完成后再操作', 409)
        db.execute('INSERT INTO guest_tasks VALUES(?,?,?)', (ident, token, time.time()))
    return token


def release(store, ident, token):
    with store.db(True) as db:
        db.execute('DELETE FROM guest_tasks WHERE user_id=? AND token=?', (ident, token))


def uploads(store, ident, count, size):
    with store.db(True) as db:
        row = db.execute('SELECT * FROM guests WHERE user_id=?', (ident,)).fetchone()
        if not row or row['state'] != 'active' or row['expires'] <= time.time():
            raise SiteError('访客空间已过期', 401)
        # Lifetime admissions, not a delete-and-reupload loophole. Failed requests
        # retain reservations because legacy endpoints can partially save files.
        if row['files']+count > 5 or row['bytes']+size > 10*1024*1024:
            raise SiteError('每个临时空间累计最多上传5个文件、合计10MB（删除不返还）', 413)
        db.execute('UPDATE guests SET files=files+?,bytes=bytes+? WHERE user_id=?', (count, size, ident))


def reserve_check(db, ident, day, now):
    row = db.execute('SELECT * FROM guests WHERE user_id=?', (ident,)).fetchone()
    if not row or row['state'] != 'active' or row['expires'] <= now:
        raise SiteError('访客空间已过期，停止模型调用', 403)
    total = db.execute('SELECT coalesce(sum(calls),0) FROM usage WHERE user_id=?', (ident,)).fetchone()[0]
    if total >= 20:
        raise SiteError('临时空间累计20次 API 调用已用完，请导出结果或登录', 429)
    # Includes migrated spaces; guest provenance is retained after login.
    global_total = db.execute('SELECT coalesce(sum(u.calls),0) FROM usage u JOIN guests g ON g.user_id=u.user_id WHERE u.day=?', (day,)).fetchone()[0]
    if global_total >= 100:
        raise SiteError('今日全站访客100次调用额度已用完，请稍后或登录', 429)


def allowed(path, method):
    import re
    project = r'api/projects/[a-zA-Z0-9_\-\u4e00-\u9fff]+'
    # Enumerate reads and writes: new cross-interview routes are denied by default.
    if method in ('GET', 'HEAD'):
        return path in ('', 'api/status', 'api/projects', 'api/library-bootstrap-guest', 'api/trash/interviews') or bool(
            re.fullmatch(project + r'(?:/(?:transcript|open-transcript|analysis|analysis-workspace|manual-coding))?', path)
            or re.fullmatch(r'assets/[a-zA-Z0-9_.-]+\.(?:js|css)', path)
        )
    if method == 'POST':
        return path == 'api/transcript-projects' or bool(re.fullmatch(
            project + r'/(?:opened|visibility|optimize-transcript|changes/accept|familiarity-memo|familiarity-summary|source-search|manual-coding/codes(?:/[a-f0-9]{32}/actions)?)', path
        ))
    if method == 'PUT':
        return bool(re.fullmatch(project + r'/(?:name|transcript|analysis-workspace)', path))
    if method == 'DELETE':
        return bool(re.fullmatch(project, path))
    return False


def process_identity(pid):
    """PID alone is unsafe after a restart because it can be reused."""
    if __import__('os').name != 'nt':
        try:
            return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        except (OSError,IndexError):
            return None
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000,False,pid)
    if not handle:return None
    try:
        # Windows may retain a queryable handle after the process has exited.
        exit_code = wintypes.DWORD()
        if kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) and exit_code.value != 259:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,*[ctypes.byref(t) for t in times]):return None
        return str((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)
    finally:
        kernel.CloseHandle(handle)
