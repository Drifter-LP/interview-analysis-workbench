"""Coordinate JSON reads/replacements and tolerate brief Windows file sharing."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import threading
import time
import uuid

_locks = {}
_registry_lock = threading.Lock()
RETRY_DELAYS = (0.01, 0.02, 0.04, 0.08, 0.12, 0.18, 0.25)


@contextmanager
def file_lock(path):
    key = os.path.normcase(str(Path(path).resolve()))
    with _registry_lock:
        lock = _locks.setdefault(key, threading.RLock())
    with lock:
        yield


def read_json(path):
    with file_lock(path):
        return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    with file_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                os.replace(temporary, path)
                return
            except OSError as exc:
                # Do not mask disk-full, invalid paths, or permanent denial.
                # Preserve the temporary checkpoint if bounded recovery fails.
                if getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == len(RETRY_DELAYS):
                    raise
                time.sleep(RETRY_DELAYS[attempt])
