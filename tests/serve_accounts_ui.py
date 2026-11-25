"""Ephemeral UI QA server with synthetic existing/friend data, no real account DB."""
import json
import os
from pathlib import Path
import sys
import tempfile
import uvicorn

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

if __name__=='__main__':
    port=int(os.getenv('WB_QA_PORT','9877'))
    with tempfile.TemporaryDirectory(prefix='workbench-account-ui-') as temporary:
        home=Path(temporary)
        legacy=home/'synthetic-existing'
        p=legacy/'projects'/'qa-existing'
        p.mkdir(parents=True)
        (p/'project.json').write_text(json.dumps({'id':'qa-existing','name':'[测试资料] 管理员原有访谈','status':'completed','created_at':1}),encoding='utf8')
        (p/'导入访谈稿.txt').write_text('访谈者：喜欢什么活动？\n受访者：我喜欢散步。这是构造的测试资料。',encoding='utf8')
        os.environ.update(SITE_HOME=str(home/'accounts'),SITE_ALLOW_HTTP='1',SITE_ORIGIN=f'http://127.0.0.1:{port}')
        from site_store import Store
        store=Store(home/'accounts')
        store.attach_existing('qa_owner',legacy)
        secret=store.redeem(store.invite('qa_owner',bootstrap=True)['token'],'temporary-qa-login-123')
        admin=store.session(secret)
        store.redeem(store.invite('qa_friend',actor=admin['id'])['token'],'temporary-qa-friend-123')
        # Synthetic history to visually verify the charts; no provider requests.
        from datetime import datetime, timezone, timedelta
        import time
        with store.db(True) as db:
            history_day=(datetime.now(timezone.utc).date()-timedelta(days=12)).isoformat()
            db.execute('INSERT INTO historical_calls VALUES(?,?,?,?,?,?,?)',
                       ('synthetic-history',admin['id'],history_day,'qwen3.8-flash',700,time.time()-12*86400,time.time()))
            for offset,count in enumerate([6,5,8,5,7,9,4]):
                day=(datetime.now(timezone.utc).date()-timedelta(days=offset)).isoformat()
                for model,n in [('deepseek-flash',count),('qwen3.8-flash',3)]:
                    for j in range(n):
                        actual=None if offset==2 and j==0 else 18000+j*1000
                        db.execute('INSERT INTO calls VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                                   (f'{day}-{model}-{j}',day,admin['id'],model,22000,actual or 22000,actual,'completed',time.time(),time.time(),time.time()))
                db.execute('INSERT INTO usage VALUES(?,?,?,?)',(day,admin['id'],count+3,(count+3)*22000))
        uvicorn.run('site_app:app',host='127.0.0.1',port=port,access_log=False)
