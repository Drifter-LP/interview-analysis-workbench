"""Private SQLite accounts, opaque sessions and atomically reserved AI budgets."""
import contextlib
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path


class SiteError(Exception):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def username(value):
    value = str(value).strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,31}', value):
        raise SiteError('账号需为3—32位英文字母、数字、点、横线或下划线')
    return value


def password_hash(password, salt=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise SiteError('密码需要12—128个字符，请使用独立的长密码')
    salt = salt or secrets.token_bytes(16)
    # OWASP scrypt baseline: N=2^17, r=8, p=1; bound memory explicitly.
    try:
        raw = password.encode()
    except UnicodeEncodeError:
        raise SiteError('密码包含无效字符') from None
    result = hashlib.scrypt(raw, salt=salt, n=2**17, r=8, p=1,
                            dklen=32, maxmem=256*1024*1024)
    return salt.hex() + ':' + result.hex()


def check_password(password, encoded):
    try:
        salt, _ = encoded.split(':', 1)
        return hmac.compare_digest(password_hash(password, bytes.fromhex(salt)), encoded)
    except (ValueError, SiteError):
        return False


class Store:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        try:
            self.home.chmod(0o700)
        except OSError:
            pass
        self.path = self.home / 'accounts.sqlite3'
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users(
              id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
              role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
              daily_calls INTEGER NOT NULL DEFAULT 80, daily_tokens INTEGER NOT NULL DEFAULT 0,
              created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(
              hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, csrf TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS invitations(
              hash TEXT PRIMARY KEY, username TEXT NOT NULL, role TEXT NOT NULL,
              created_by TEXT, expires REAL NOT NULL, used REAL,
              daily_calls INTEGER NOT NULL, daily_tokens INTEGER NOT NULL, reset_id TEXT);
            CREATE TABLE IF NOT EXISTS failures(key TEXT NOT NULL, at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS failure_lookup ON failures(key,at);
            CREATE TABLE IF NOT EXISTS usage(
              day TEXT NOT NULL, user_id TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0,
              tokens INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day,user_id));
            CREATE TABLE IF NOT EXISTS calls(
              id TEXT PRIMARY KEY, day TEXT NOT NULL, user_id TEXT NOT NULL,
              model TEXT NOT NULL, reserved INTEGER NOT NULL, charged INTEGER NOT NULL,
              actual INTEGER, status TEXT NOT NULL, started REAL NOT NULL,
              heartbeat REAL NOT NULL, ended REAL);
            CREATE TABLE IF NOT EXISTS audit(
              at REAL NOT NULL, actor TEXT, action TEXT NOT NULL, target TEXT);
            CREATE TABLE IF NOT EXISTS site_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS historical_calls(
              request_key TEXT PRIMARY KEY,user_id TEXT NOT NULL,day TEXT NOT NULL,
              model TEXT NOT NULL,actual INTEGER,started REAL NOT NULL,imported_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS historical_call_evidence(
              request_key TEXT NOT NULL,source TEXT NOT NULL,sha256 TEXT NOT NULL,
              PRIMARY KEY(request_key,source));
            CREATE TABLE IF NOT EXISTS user_profiles(
              user_id TEXT PRIMARY KEY, avatar TEXT NOT NULL DEFAULT '', updated REAL NOT NULL);
            ''')
        # One-shot migration. 0 denotes no cap in the legacy NOT NULL columns.
        with self.db(True) as db:
            if db.execute("INSERT OR IGNORE INTO site_settings VALUES('calls_only_v1','1')").rowcount:
                for table in ('users','invitations'):
                    db.execute(f"UPDATE {table} SET daily_calls=CASE WHEN role='admin' THEN 0 ELSE 80 END,daily_tokens=0")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    @contextlib.contextmanager
    def db(self, write=False):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def invite(self, name, actor=None, calls=80, bootstrap=False, reset_id=None):
        name = username(name)
        if type(calls) is not int or not 1 <= calls <= 100:
            raise SiteError('每日调用上限需为1—100次')
        secret = secrets.token_urlsafe(32)
        with self.db(True) as db:
            total = db.execute("SELECT count(*) FROM users WHERE role!='guest'").fetchone()[0]
            if bootstrap:
                if total or db.execute('SELECT count(*) FROM invitations WHERE role="admin" AND used IS NULL AND expires>?', (time.time(),)).fetchone()[0]:
                    raise SiteError('已有管理员或有效初始化链接；不会重复创建')
            else:
                admin = db.execute('SELECT * FROM users WHERE id=? AND role="admin" AND active=1', (actor,)).fetchone()
                if not admin:
                    raise SiteError('需要管理员权限', 403)
                if not reset_id and total >= 8:
                    raise SiteError('试用版最多8个账号（含管理员）')
            if reset_id:
                user = db.execute('SELECT * FROM users WHERE id=?', (reset_id,)).fetchone()
                if not user or user['username'] != name or user['role'] == 'guest' or not user['active']:
                    raise SiteError('账号不存在', 404)
            elif db.execute('SELECT 1 FROM users WHERE username=?', (name,)).fetchone():
                raise SiteError('账号已存在')
            db.execute('UPDATE invitations SET used=? WHERE username=? AND used IS NULL', (time.time(), name))
            expires = time.time() + (3600 if bootstrap or reset_id else 48*3600)
            db.execute('INSERT INTO invitations VALUES(?,?,?,?,?,NULL,?,?,?)',
                       (token_hash(secret), name, 'admin' if bootstrap else 'user', actor, expires, 0 if bootstrap else calls, 0, reset_id))
            db.execute('INSERT INTO audit VALUES(?,?,?,?)', (time.time(), actor, 'bootstrap' if bootstrap else 'reset_invite' if reset_id else 'invite', name))
        return {'token': secret, 'username': name, 'expires_at': expires}

    def admin_recovery(self, name):
        """Server-operator only. Reissue access to an existing active administrator."""
        name = username(name)
        with self.db() as db:
            admin = db.execute('SELECT id FROM users WHERE username=? AND role="admin" AND active=1', (name,)).fetchone()
        if not admin:
            raise SiteError('未找到此管理员账号', 404)
        return self.invite(name, actor=admin['id'], reset_id=admin['id'])

    def attach_existing(self, name, root):
        """Explicit immutable binding; never move or copy research materials."""
        name = username(name)
        binding = json.dumps({'username': name, 'root': str(Path(root).resolve())}, sort_keys=True)
        with self.db(True) as db:
            previous = db.execute('SELECT value FROM site_settings WHERE key="legacy_owner"').fetchone()
            if previous and previous['value'] != binding:
                raise SiteError('旧资料已经绑定，禁止自动重新分配')
            user = db.execute('SELECT role FROM users WHERE username=?', (name,)).fetchone()
            if user and user['role'] != 'admin':
                raise SiteError('旧资料只能归管理员')
            db.execute('INSERT OR IGNORE INTO site_settings VALUES("legacy_owner",?)', (binding,))

    def data_root(self, user_id):
        with self.db() as db:
            user = db.execute('SELECT username,role,active FROM users WHERE id=?', (user_id,)).fetchone()
            setting = db.execute('SELECT value FROM site_settings WHERE key="legacy_owner"').fetchone()
        if not user or not user['active']:
            raise SiteError('账号不可用', 403)
        if user['role'] == 'guest':
            from site_guests import info
            info(self, user_id)
        binding = json.loads(setting['value']) if setting else None
        if binding and user['role'] == 'admin' and user['username'] == binding['username']:
            return Path(binding['root']).resolve(), True
        return self.home / 'tenants' / user_id, False

    def redeem(self, secret, password, reset_only=False):
        encoded = password_hash(password)
        with self.db(True) as db:
            invite = db.execute('SELECT * FROM invitations WHERE hash=? AND used IS NULL AND expires>?', (token_hash(str(secret)), time.time())).fetchone()
            if not invite or (reset_only and not invite['reset_id']):
                raise SiteError('链接无效、已使用或已过期', 400)
            if invite['reset_id']:
                user_id = invite['reset_id']
                if not db.execute('SELECT 1 FROM users WHERE id=? AND active=1', (user_id,)).fetchone():
                    raise SiteError('账号已停用')
                db.execute('UPDATE users SET password=? WHERE id=?', (encoded, user_id))
                db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
                db.execute('UPDATE invitations SET used=? WHERE reset_id=? AND used IS NULL', (time.time(), user_id))
                db.execute('DELETE FROM failures WHERE key IN (?,?)', ('password-change:'+token_hash(user_id), 'name:'+token_hash(invite['username'])))
            else:
                if db.execute("SELECT count(*) FROM users WHERE role!='guest'").fetchone()[0] >= 8:
                    raise SiteError('试用名额已满')
                if db.execute('SELECT 1 FROM users WHERE username=?', (invite['username'],)).fetchone():
                    raise SiteError('账号已存在')
                user_id = secrets.token_hex(16)
                db.execute('INSERT INTO users(id,username,password,role,daily_calls,daily_tokens,created) VALUES(?,?,?,?,?,?,?)',
                           (user_id, invite['username'], encoded, invite['role'], invite['daily_calls'], invite['daily_tokens'], time.time()))
            db.execute('UPDATE invitations SET used=? WHERE hash=?', (time.time(), invite['hash']))
            db.execute('INSERT INTO audit VALUES(?,?,?,?)', (time.time(), user_id, 'reset_password' if invite['reset_id'] else 'activate', user_id))
        return None if reset_only else self.new_session(user_id, expected_password=encoded)

    def change_password(self, user_id, session_secret, current, new):
        if not isinstance(new, str) or not 12 <= len(new) <= 128:
            raise SiteError('新密码需要 12–128 个字符')
        if current == new:
            raise SiteError('新密码不能与当前密码相同')
        now = time.time()
        key = 'password-change:' + token_hash(user_id)
        session_key = token_hash(session_secret)
        with self.db(True) as db:
            row = db.execute("SELECT u.password,u.username FROM users u JOIN sessions s ON s.user_id=u.id WHERE u.id=? AND u.active=1 AND u.role!='guest' AND s.hash=? AND s.expires>?", (user_id, session_key, now)).fetchone()
            if not row:
                raise SiteError('当前账号无法修改密码，请重新登录', 403)
            db.execute('DELETE FROM failures WHERE key=? AND at<?', (key, now-900))
            if db.execute('SELECT count(*) FROM failures WHERE key=?', (key,)).fetchone()[0] >= 5:
                raise SiteError('密码验证次数过多，请15分钟后再试', 429)
            db.execute('INSERT INTO failures VALUES(?,?)', (key, now))
        if not check_password(current, row['password']):
            raise SiteError('当前密码不正确')
        encoded = password_hash(new)
        with self.db(True) as db:
            result = db.execute('UPDATE users SET password=? WHERE id=? AND active=1 AND password=? AND EXISTS(SELECT 1 FROM sessions WHERE user_id=? AND hash=? AND expires>?)',
                                (encoded, user_id, row['password'], user_id, session_key, time.time()))
            if result.rowcount != 1:
                raise SiteError('账号状态已变化，请重新登录', 409)
            db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            db.execute('UPDATE invitations SET used=? WHERE reset_id=? AND used IS NULL', (time.time(), user_id))
            db.execute('DELETE FROM failures WHERE key IN (?,?)', (key, 'name:'+token_hash(row['username'])))
            db.execute('INSERT INTO audit VALUES(?,?,?,?)', (time.time(), user_id, 'change_password', user_id))

    def login(self, name, password, ip):
        name = str(name).strip().lower()[:128]
        now = time.time()
        keys = ['ip:'+token_hash(ip), 'name:'+token_hash(name)]
        with self.db(True) as db:
            db.execute('DELETE FROM failures WHERE at<?', (now-900,))
            if any(db.execute('SELECT count(*) FROM failures WHERE key=?', (key,)).fetchone()[0] >= (20 if key.startswith('ip:') else 5) for key in keys):
                raise SiteError('登录尝试过多，请15分钟后再试', 429)
            row = db.execute('SELECT * FROM users WHERE username=?', (name,)).fetchone()
            # Reserve attempts before the slow KDF to make concurrent attempts count.
            for key in keys:
                db.execute('INSERT INTO failures VALUES(?,?)', (key, now))
        fallback = '00'*16+':'+'00'*32
        valid = check_password(password, row['password'] if row else fallback)
        if not row or not row['active'] or not valid:
            raise SiteError('账号或密码不正确，或账号已停用', 401)
        with self.db(True) as db:
            db.execute('DELETE FROM failures WHERE key=?', (keys[1],))
        return self.new_session(row['id'], expected_password=row['password'])

    def new_session(self, user_id, expected_password=None):
        secret, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.db(True) as db:
            user = db.execute('SELECT password,role FROM users WHERE id=? AND active=1', (user_id,)).fetchone()
            if not user or (expected_password is not None and user['password'] != expected_password):
                raise SiteError('账号不可用', 403)
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            guest = user['role'] == 'guest'
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token_hash(secret), user_id, csrf, time.time()+(86400 if guest else 30*86400)))
        return secret

    def session(self, secret):
        if not secret:
            return None
        with self.db() as db:
            row = db.execute("SELECT users.id,users.username,users.role,users.daily_calls,users.daily_tokens,COALESCE(p.avatar,'') AS avatar,sessions.csrf FROM sessions JOIN users ON users.id=sessions.user_id LEFT JOIN user_profiles p ON p.user_id=users.id WHERE sessions.hash=? AND sessions.expires>? AND users.active=1", (token_hash(secret), time.time())).fetchone()
        if row and row['role'] == 'guest':
            from site_guests import info
            try:
                info(self, row['id'])
            except SiteError:
                return None
        return dict(row) if row else None

    def logout(self, secret):
        with self.db(True) as db:
            db.execute('DELETE FROM sessions WHERE hash=?', (token_hash(secret),))

    def usage(self, user_id):
        day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        with self.db() as db:
            row = db.execute('SELECT calls,tokens FROM usage WHERE day=? AND user_id=?', (day, user_id)).fetchone()
        return {'day_utc': day, 'calls': row['calls'] if row else 0, 'tokens': row['tokens'] if row else 0}

    def users(self):
        day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        with self.db() as db:
            return [dict(r) for r in db.execute(
                "SELECT u.id,u.username,u.role,u.active,u.daily_calls,u.daily_tokens,u.created,"
                "COALESCE(p.avatar,'') AS avatar,COALESCE(g.calls,0) AS today_calls "
                "FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id "
                "LEFT JOIN usage g ON g.user_id=u.id AND g.day=? "
                "WHERE u.role!='guest' ORDER BY u.created", (day,)
            )]

    def model_usage(self, actor, scope='self', days=7):
        if scope not in ('self', 'all') or days not in (7, 30):
            raise SiteError('统计范围无效')
        today=datetime.now(timezone.utc).date()
        dates=[(today-timedelta(days=i)).isoformat() for i in reversed(range(days))]
        with self.db() as db:
            user=db.execute('SELECT role FROM users WHERE id=? AND active=1',(actor,)).fetchone()
            if not user or (scope=='all' and user['role']!='admin'):
                raise SiteError('需要管理员权限',403)
            query='SELECT day,model,count(*) AS calls,sum(CASE WHEN actual IS NULL THEN 0 ELSE actual END) AS tokens,sum(CASE WHEN actual IS NULL THEN 1 ELSE 0 END) AS missing FROM (SELECT day,model,actual,user_id FROM calls UNION ALL SELECT day,model,actual,user_id FROM historical_calls) WHERE day>=? AND day<=?'
            args=[dates[0],dates[-1]]
            if scope=='self':
                query+=' AND user_id=?'
                args.append(actor)
            rows=db.execute(query+' GROUP BY day,model',args).fetchall()
            history_query='SELECT count(*) FROM historical_calls WHERE day>=? AND day<=?'
            history_args=[dates[0],dates[-1]]
            if scope=='self':
                history_query+=' AND user_id=?'
                history_args.append(actor)
            historical_count=db.execute(history_query,history_args).fetchone()[0]
        series={key:[{'day':day,'calls':0,'tokens':0,'missing':0} for day in dates] for key in ('deepseek','qwen')}
        other_calls=0
        for r in rows:
            name=r['model'].lower()
            key='deepseek' if name.startswith('deepseek') and 'flash' in name else 'qwen' if name.startswith('qwen') and 'flash' in name else None
            if key is None:
                other_calls+=r['calls']
                continue
            point=series[key][dates.index(r['day'])]
            for field,col in [('calls','calls'),('tokens','tokens'),('missing','missing')]:
                point[field]+=r[col] or 0
        return {'scope':scope,'days':days,'timezone':'UTC','series':series,'other_calls':other_calls,
                'historical_calls':historical_count,'coverage':'仅汇总已记录调用及去重后的历史证据，不等于供应商完整账单。'}

    def update_user(self, actor, target, active, calls):
        if type(active) is not bool or type(calls) is not int:
            raise SiteError('账号设置格式无效')
        with self.db(True) as db:
            if not db.execute('SELECT 1 FROM users WHERE id=? AND role="admin" AND active=1', (actor,)).fetchone():
                raise SiteError('需要管理员权限', 403)
            row = db.execute('SELECT * FROM users WHERE id=?', (target,)).fetchone()
            if not row:
                raise SiteError('账号不存在', 404)
            if row['role']=='admin' and not active:
                raise SiteError('试用版不允许停用管理员')
            if row['role']!='admin' and not 1 <= calls <= 100:
                raise SiteError('成员每日调用上限需为1—100次')
            db.execute('UPDATE users SET active=?,daily_calls=?,daily_tokens=0 WHERE id=?', (int(active), 0 if row['role']=='admin' else calls, target))
            if not active:
                db.execute('DELETE FROM sessions WHERE user_id=?', (target,))
            db.execute('INSERT INTO audit VALUES(?,?,?,?)', (time.time(), actor, 'update_account', target))

    def update_profile(self, user_id, new_username=None, new_avatar=None):
        with self.db(True) as db:
            row = db.execute('SELECT id,username,role,active FROM users WHERE id=?', (user_id,)).fetchone()
            if not row or not row['active']:
                raise SiteError('账号不存在或已停用', 403)
            if row['role'] == 'guest':
                raise SiteError('访客暂不支持修改资料', 403)
            changed = False
            if new_username is not None:
                clean_name = username(new_username)
                if clean_name != row['username']:
                    if db.execute('SELECT 1 FROM users WHERE username=? AND id!=?', (clean_name, user_id)).fetchone():
                        raise SiteError('该用户名已被占用', 409)
                    db.execute('UPDATE users SET username=? WHERE id=?', (clean_name, user_id))
                    if row['role'] == 'admin':
                        setting = db.execute("SELECT value FROM site_settings WHERE key='legacy_owner'").fetchone()
                        if setting:
                            binding = json.loads(setting['value'])
                            if binding.get('username') == row['username']:
                                binding['username'] = clean_name
                                db.execute("UPDATE site_settings SET value=? WHERE key='legacy_owner'", (json.dumps(binding, sort_keys=True),))
                    changed = True
            if new_avatar is not None:
                if not isinstance(new_avatar, str):
                    raise SiteError('头像格式无效')
                clean_avatar = new_avatar.strip()
                valid_presets = {'preset:teal', 'preset:ocean', 'preset:indigo', 'preset:amber', 'preset:rose', 'preset:slate'}
                if clean_avatar and clean_avatar not in valid_presets:
                    if len(clean_avatar) > 180000 or not re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+', clean_avatar):
                        raise SiteError('头像仅支持预设配色或 130KB 以内的 PNG/JPG/WebP 图片')
                db.execute('INSERT INTO user_profiles(user_id,avatar,updated) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET avatar=excluded.avatar,updated=excluded.updated', (user_id, clean_avatar, time.time()))
                changed = True
            if changed:
                db.execute('INSERT INTO audit VALUES(?,?,?,?)', (time.time(), user_id, 'update_profile', user_id))


    def reserve(self, user_id, model, tokens):
        day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        now = time.time()
        with self.db(True) as db:
            user = db.execute('SELECT * FROM users WHERE id=? AND active=1', (user_id,)).fetchone()
            if not user:
                raise SiteError('账号已停用，模型调用已阻止', 403)
            if user['role'] == 'guest':
                from site_guests import reserve_check
                reserve_check(db, user_id, day, now)
            # Abandoned calls retain conservative charges, but release concurrency after 10min.
            db.execute('UPDATE calls SET status="interrupted",ended=? WHERE status="running" AND heartbeat<?', (now, now-600))
            usage = db.execute('SELECT calls,tokens FROM usage WHERE day=? AND user_id=?', (day, user_id)).fetchone()
            if user['role'] not in ('admin','guest') and usage and usage['calls'] >= user['daily_calls']:
                raise SiteError('今日 API 调用次数已用完，额度在北京时间每天 08:00 重置；已完成结果仍保留', 429)
            busy = db.execute('SELECT user_id FROM calls WHERE status="running"').fetchall()
            if len(busy)>=4 or sum(r['user_id']==user_id for r in busy)>=(1 if user['role']=='guest' else 3):
                raise SiteError('模型并发已满，请稍后重试', 503)
            ident = secrets.token_hex(16)
            db.execute('INSERT INTO usage VALUES(?,?,1,?) ON CONFLICT(day,user_id) DO UPDATE SET calls=calls+1,tokens=usage.tokens+excluded.tokens', (day,user_id,tokens))
            db.execute('INSERT INTO calls VALUES(?,?,?,?,?,?,NULL,"running",?,?,NULL)', (ident,day,user_id,str(model)[:100],tokens,tokens,now,now))
        return ident

    def heartbeat(self, ident):
        with self.db(True) as db:
            db.execute('UPDATE calls SET heartbeat=? WHERE id=? AND status="running"', (time.time(),ident))

    def finish(self, ident, actual=None, failed=False):
        with self.db(True) as db:
            row = db.execute('SELECT * FROM calls WHERE id=? AND status="running"', (ident,)).fetchone()
            if not row:
                return
            actual = actual if type(actual) is int and actual>=0 else None
            charge = actual if actual is not None else row['reserved']
            db.execute('UPDATE usage SET tokens=tokens+? WHERE day=? AND user_id=?', (charge-row['charged'],row['day'],row['user_id']))
            db.execute('UPDATE calls SET actual=?,charged=?,status=?,ended=? WHERE id=?', (actual,charge,'failed' if failed else 'completed',time.time(),ident))

