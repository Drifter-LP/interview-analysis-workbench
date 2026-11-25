"""Shared atomic persistence and per-document read/modify/write protection."""
from functools import wraps
from contextlib import contextmanager
import hashlib
import inspect
import json
import os
from pathlib import Path
import tempfile
from theme_file_io import file_lock, write_json
from site_store import SiteError
from backend_observability import log_failure


def atomic_write_json(path, data):
    write_json(Path(path), data)


def atomic_write_text(path, text, encoding='utf-8'):
    path = Path(path)
    with file_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding=encoding, newline='') as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)


def read_json_document(path):
    path = Path(path)
    with file_lock(path):
        raw = path.read_bytes()
        try:
            value = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(value, dict):
                raise ValueError('Expected a JSON object')
            return value
        except (ValueError, UnicodeError) as error:
            # Preserve the original and one byte-identical recovery copy per hash.
            backup = path.with_name(path.name+'.corrupt-'+hashlib.sha256(raw).hexdigest()[:16]+'.bak')
            try:
                with backup.open('xb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                pass
            except OSError as backup_error:
                log_failure('corrupt_backup_failed', backup_error, file=path.name)
            log_failure('corrupt_document_blocked', error, file=path.name)
            raise SiteError('已有研究文件损坏，已停止读取和覆盖，请联系管理员恢复备份', 409) from error


@contextmanager
def document_transaction(path):
    # Match theme_file_io's index-lock -> file-lock order to avoid inversion.
    from interview_reference_index import write_guard
    with write_guard(path), file_lock(path):
        yield


def locked_document(path_factory):
    """Lock the entire synchronous mutation, not just its final replacement."""
    def decorate(function):
        signature = inspect.signature(function)
        @wraps(function)
        def guarded(*args, **kwargs):
            values = signature.bind(*args, **kwargs).arguments
            with document_transaction(path_factory(values)):
                return function(*args, **kwargs)
        return guarded
    return decorate
