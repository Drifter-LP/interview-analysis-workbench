"""Publish only the three guide assets; preserve the active backend and data."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

FILES = ('web/empty-guide.css', 'web/empty-guide.js', 'web/index.html')

def digest(raw):
    return hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()

if sys.argv[1] == 'pack':
    root = Path(__file__).resolve().parents[1]
    baseline = subprocess.check_output(['git', 'show', 'origin/main:web/index.html'], cwd=root)
    with zipfile.ZipFile(sys.argv[2], 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            z.write(root/name, name)
        z.writestr('manifest.json', json.dumps(dict(baseline_index=digest(baseline),
            revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip())))
else:
    active = Path(subprocess.check_output(['systemctl','show','workbench.service','-p','WorkingDirectory','--value'],text=True).strip())
    assert active.parent == Path('/home/ubuntu') and active.is_dir()
    with zipfile.ZipFile(sys.argv[2]) as z:
        assert set(z.namelist()) == {*FILES, 'manifest.json'}
        info = json.loads(z.read('manifest.json'))
        assert digest((active/'web/index.html').read_bytes()) == info['baseline_index'], 'Active homepage differs; refusing overwrite'
        before = {name: (active/name).read_bytes() if (active/name).exists() else None for name in FILES}
        backup = Path(tempfile.mkdtemp(prefix='workbench-guide-backup-', dir='/home/ubuntu'))
        for name, raw in before.items():
            if raw is not None:
                p=backup/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        def replace(name, raw):
            fd,tmp=tempfile.mkstemp(dir=(active/name).parent)
            with os.fdopen(fd,'wb') as stream: stream.write(raw)
            os.chmod(tmp,0o644);os.replace(tmp,active/name)
        try:
            for name in FILES: replace(name, z.read(name))
            for name in FILES: assert (active/name).read_bytes() == z.read(name)
        except BaseException:
            for name,raw in before.items():
                if raw is not None: replace(name,raw)
            raise
    print(json.dumps(dict(published=info['revision'],active=str(active),backup=str(backup),
                          backend_restarted=False,data_modified=False)),flush=True)
