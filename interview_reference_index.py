"""Derived exact-value reference index; changed files are discovered by stat inventory."""
from contextlib import nullcontext, contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
import time

INDEX_LOCK=threading.RLock()
_indexes={}


def tokens(value):
    stack=[value];found=set()
    while stack:
        item=stack.pop()
        if isinstance(item,str):found.add(hashlib.sha256(item.encode('utf8')).digest())
        elif isinstance(item,dict):stack.extend(item.keys());stack.extend(item.values())
        elif isinstance(item,list):stack.extend(item)
    return found


def fingerprint(path):
    return stat_fingerprint(path.stat())


def stat_fingerprint(s):
    # Windows DirEntry.stat does not expose a stable inode; use the same
    # size/mtime/creation-time fingerprint for directory and direct checks.
    return json.dumps([s.st_size,s.st_mtime_ns,s.st_ctime_ns])


class ReferenceIndex:
    def __init__(self,app_dir,root):
        self.root=Path(root).resolve()
        self.path=Path(app_dir)/'.cache'/'interview-references.sqlite3'
        self.last_stats={}

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=30)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.executescript('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);'
                             'CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,stamp TEXT,valid INTEGER);'
                             'CREATE TABLE IF NOT EXISTS refs(path TEXT,token BLOB,PRIMARY KEY(path,token),'
                             'FOREIGN KEY(path) REFERENCES files(path) ON DELETE CASCADE);'
                             'CREATE INDEX IF NOT EXISTS refs_token ON refs(token);')
            root=db.execute("SELECT value FROM meta WHERE key='root'").fetchone()
            if root and root[0]!=str(self.root):raise ValueError('关联索引的资料目录不一致')
            db.execute("INSERT OR IGNORE INTO meta VALUES('root',?)",(str(self.root),))
            with db:yield db
        finally:db.close()

    def inventory(self):
        result={}
        pending=[str(self.root)]
        while pending:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    if entry.is_symlink():continue
                    if entry.is_dir(follow_symlinks=False):
                        if hasattr(os.path,'isjunction') and os.path.isjunction(entry.path):
                            raise ValueError('资料目录包含外部连接，需完整检查')
                        pending.append(entry.path)
                    elif entry.name.lower().endswith('.json') and entry.is_file(follow_symlinks=False):
                        rel=os.path.relpath(entry.path,self.root).replace('\\','/')
                        result[rel]=stat_fingerprint(entry.stat(follow_symlinks=False))
        return result

    def put(self,db,rel,stamp,value,valid=True):
        db.execute('DELETE FROM files WHERE path=?',(rel,))
        db.execute('INSERT INTO files VALUES(?,?,?)',(rel,stamp,int(valid)))
        if valid:db.executemany('INSERT INTO refs VALUES(?,?)',((rel,t) for t in tokens(value)))

    def refresh(self):
        started=time.perf_counter();parsed=0
        inventory=self.inventory()
        with self.connect() as db:
            complete=db.execute("SELECT value FROM meta WHERE key='complete'").fetchone()
            if not complete:db.execute('DELETE FROM files')
            cached=dict(db.execute('SELECT path,stamp FROM files'))
            for rel,stamp in list(cached.items()):
                old=json.loads(stamp)
                if len(old)==4:
                    cached[rel]=json.dumps(old[:3])
                    db.execute('UPDATE files SET stamp=? WHERE path=?',(cached[rel],rel))
            for rel in cached.keys()-inventory.keys():db.execute('DELETE FROM files WHERE path=?',(rel,))
            for rel,stamp in inventory.items():
                if cached.get(rel)==stamp:continue
                path=self.root/rel
                try:value=json.loads(path.read_text(encoding='utf-8-sig'));valid=True
                except (ValueError,UnicodeError):value=None;valid=False
                if fingerprint(path)!=stamp:raise ValueError('索引建立期间资料发生变化，请稍后重试')
                self.put(db,rel,stamp,value,valid);parsed+=1
            # Changed files need a stable second snapshot during rebuilding.
            # Warm deletion lookups receive another inventory check immediately
            # before moving files in archive_interview, avoiding a third walk.
            if parsed and self.inventory()!=inventory:raise ValueError('资料目录正在变化，索引校验未通过')
            db.execute("INSERT OR REPLACE INTO meta VALUES('complete','1')")
            invalid=db.execute('SELECT COUNT(*) FROM files WHERE valid=0').fetchone()[0]
        self.last_stats={'files':len(inventory),'parsed':parsed,'invalid':invalid,
                         'seconds':round(time.perf_counter()-started,3)}
        return inventory,invalid

    def candidates(self,interview_id):
        with INDEX_LOCK:
            inventory,invalid=self.refresh()
            if invalid:raise ValueError('存在无法解析的资料，回退完整检查')
            token=hashlib.sha256(interview_id.encode('utf8')).digest()
            with self.connect() as db:
                rows=db.execute('SELECT path FROM refs WHERE token=? ORDER BY path',(token,)).fetchall()
            return [self.root/r[0] for r in rows],inventory

    def saved(self,path,value):
        if not self.path.exists():return
        rel=path.relative_to(self.root).as_posix()
        stamp=fingerprint(path)
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        if fingerprint(path)!=stamp:raise ValueError('文件正在被修改，延后更新关联索引')
        with self.connect() as db:self.put(db,rel,stamp,value)


def get_index(app_dir,root):
    key=(str(Path(app_dir).resolve()),str(Path(root).resolve()))
    with INDEX_LOCK:
        if key not in _indexes:_indexes[key]=ReferenceIndex(app_dir,root)
        return _indexes[key]


def write_guard(path):
    path=Path(path).resolve()
    return INDEX_LOCK if any(path.is_relative_to(i.root) for i in list(_indexes.values())) else nullcontext()


def notify_saved(path,value):
    path=Path(path).resolve()
    for index in list(_indexes.values()):
        if path.is_relative_to(index.root):
            try:index.saved(path,value)
            except Exception:logging.exception('关联索引更新失败；下次删除将重新校验文件')
