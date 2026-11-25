"""Stage isolated tests, then activate only against the verified cloud baseline."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile


def current():
    return Path(subprocess.check_output(['systemctl', 'show', 'workbench.service',
                                        '-p', 'WorkingDirectory', '--value'], text=True).strip())


def stage(archive):
    target = Path(tempfile.mkdtemp(prefix='workbench-memo-index.', dir='/home/ubuntu'))
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise RuntimeError('Unsafe archive member')
        bundle.extractall(target)
    old = current()
    changes = []
    for path in target.rglob('*'):
        if not path.is_file() or path.parts[-2] == 'tests' or path.name == 'release.json':
            continue
        peer = old/path.relative_to(target)
        if not peer.exists() or peer.read_bytes().replace(b'\r\n', b'\n') != path.read_bytes().replace(b'\r\n', b'\n'):
            changes.append(path.relative_to(target).as_posix())
    assert set(changes) == {'web_app.py', 'indexed_memo.py'}, changes
    python = '/home/ubuntu/workbench-text.f8dSdA/.venv/bin/python'
    env = {k: v for k, v in os.environ.items() if k not in ('DEEPSEEK_API_KEY', 'QWEN_API_KEY')}
    checks = [
        ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_indexed_memo.py', '-q'],
        ['tests/test_ai_reliability.py', '-q'],
        ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*audit.py', '-q'],
    ]
    for args in checks:
        result = subprocess.run([python, *args], cwd=target, env=env, capture_output=True,
                                text=True, timeout=180)
        lines = (result.stdout + result.stderr).splitlines()
        print('CHECK', args, 'exit', result.returncode, flush=True)
        print('\n'.join(lines[-6:]), flush=True)
        assert result.returncode == 0, 'Isolated Linux tests failed'
    baseline = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in old.iterdir() if p.is_file() and p.suffix == '.py'}
    (target/'deployment-check.json').write_text(json.dumps(dict(previous=str(old), baseline=baseline)))
    print('VERIFIED_RELEASE=' + str(target), flush=True)


def idle():
    data = Path('/home/ubuntu/workbench-cloud-data')
    with sqlite3.connect(f'file:{data}/accounts.sqlite3?mode=ro', uri=True) as db:
        running = db.execute("SELECT count(*) FROM calls WHERE status='running'").fetchone()[0]
        guests = db.execute('SELECT count(*) FROM guest_tasks').fetchone()[0]
    queued = 0
    for path in data.rglob('project.json'):
        queued += json.loads(path.read_text(encoding='utf-8')).get('status') in ('running', 'queued')
    assert not (running or guests or queued), f'Active tasks: {running}, {guests}, {queued}; refusing restart'


def activate(target):
    target = Path(target).resolve(strict=True)
    assert target.parent == Path('/home/ubuntu') and target.name.startswith('workbench-memo-index.')
    checked = json.loads((target/'deployment-check.json').read_text())
    old = current()
    assert str(old) == checked['previous'], 'Deployment changed after staging; recheck first'
    for name, digest in checked['baseline'].items():
        assert hashlib.sha256((old/name).read_bytes()).hexdigest() == digest, 'Backend changed after staging'
    idle()
    service = Path('/etc/systemd/system/workbench.service')
    original = service.read_bytes()
    needle = ('WorkingDirectory='+str(old)).encode()
    assert original.count(needle) == 1
    backup = Path(tempfile.mkdtemp(prefix='workbench-memo-service-backup-', dir='/home/ubuntu'))
    (backup/'workbench.service').write_bytes(original)
    def write(raw):
        fd, name = tempfile.mkstemp(dir=service.parent)
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
        os.chmod(name, 0o644)
        os.replace(name, service)
    def restart():
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'restart', 'workbench.service'], check=True)
    try:
        subprocess.run(['systemctl', 'stop', 'workbench.service'], check=True)
        idle()  # Catch requests that started between the first check and stop.
        write(original.replace(needle, ('WorkingDirectory='+str(target)).encode()))
        restart()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(60):
            try:
                request = urllib.request.Request('http://127.0.0.1:8765/health', headers={'Host': 'sociolab.cn'})
                with opener.open(request, timeout=2) as reply:
                    if json.load(reply).get('ok'):
                        break
            except Exception:
                pass
            time.sleep(.5)
        else:
            raise RuntimeError('Production health timeout')
        assert current() == target
        print('ACTIVATED=' + str(target), 'ROLLBACK=' + str(backup), flush=True)
    except BaseException:
        write(original)
        restart()
        print('ROLLED_BACK=' + str(old), flush=True)
        raise


if __name__ == '__main__':
    if sys.argv[1] == 'stage':
        stage(sys.argv[2])
    elif sys.argv[1] == 'activate':
        activate(sys.argv[2])
    elif sys.argv[1] == 'pack-tests':
        root = Path(__file__).resolve().parents[1]
        with zipfile.ZipFile(sys.argv[2], 'a', compression=zipfile.ZIP_DEFLATED) as bundle:
            for name in ('test_indexed_memo.py', 'test_ai_reliability.py', 'test_backend_audit.py',
                         'test_gateway_audit.py', 'test_account_storage_audit.py', 'test_observability_audit.py',
                         'probe_indexed_memo.py'):
                bundle.write(root/'tests'/name, 'tests/'+name)
            revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
            bundle.writestr('release.json', json.dumps(dict(commit=revision, kind='source-indexed-memo')))
