"""Install before importing analysis modules; every SDK attempt reserves quota."""
import json
import os
import time
from site_store import Store, SiteError
from backend_observability import log_event, log_failure


def request_json(request, body):
    """Account and meter the legacy urllib model path without changing its payload."""
    import urllib.request
    store=Store(os.environ['SITE_HOME'])
    ident=store.reserve(os.environ['SITE_USER_ID'],body['model'],len(request.data or b'')+body.get('max_tokens',8192)+1024)
    actual=None
    try:
        with urllib.request.urlopen(request,timeout=240) as response:
            raw=json.load(response)
        actual=(raw.get('usage') or {}).get('total_tokens')
    except Exception as error:
        store.finish(ident,actual,failed=True)
        log_failure('model_call_failed', error, call_id=ident)
        raise
    store.finish(ident,actual)
    log_event('model_call_finished', call_id=ident, model=body['model'])
    return raw


def install():
    from openai import OpenAI
    from openai.resources.chat.completions import Completions
    store = Store(os.environ['SITE_HOME'])
    user = os.environ['SITE_USER_ID']
    original_init, original_create = OpenAI.__init__, Completions.create

    def init(self, *args, **kwargs):
        kwargs['max_retries'] = 0
        original_init(self, *args, **kwargs)

    def create(self, *args, **kwargs):
        output = kwargs.get('max_tokens') or kwargs.get('max_completion_tokens') or 8192
        if not isinstance(output, int) or not 1 <= output <= 48000:
            raise SiteError('单次模型输出上限为48000 Token')
        size = len(json.dumps(kwargs.get('messages', []), ensure_ascii=False).encode())
        if size > 250000:
            raise SiteError('本次模型输入过大，请减少材料')
        ident = store.reserve(user, kwargs.get('model', ''), size + output + 1024)
        log_event('model_call_started', call_id=ident, model=kwargs.get('model', ''))
        try:
            result = original_create(self, *args, **kwargs)
        except Exception as error:
            store.finish(ident, failed=True)
            log_failure('model_call_failed', error, call_id=ident)
            raise
        if kwargs.get('stream'):
            return GuardedStream(result, store, ident)
        usage = getattr(result, 'usage', None)
        store.finish(ident, getattr(usage, 'total_tokens', None))
        log_event('model_call_finished', call_id=ident, model=kwargs.get('model', ''),
                  finish_reason=str(getattr(result.choices[0], 'finish_reason', '')))
        return result

    OpenAI.__init__, Completions.create = init, create


class GuardedStream:
    def __init__(self, stream, store, ident):
        self.stream, self.store, self.ident = stream, store, ident
        self.actual, self.done = None, False
        self.last_heartbeat = time.monotonic()

    def __iter__(self):
        failed = True
        try:
            for chunk in self.stream:
                usage = getattr(chunk, 'usage', None)
                if usage:
                    self.actual = getattr(usage, 'total_tokens', None)
                if time.monotonic() - self.last_heartbeat > 15:
                    self.store.heartbeat(self.ident)
                    self.last_heartbeat = time.monotonic()
                yield chunk
            failed = False
        finally:
            self.close(failed)

    def close(self, failed=False):
        if not self.done:
            self.done = True
            try:
                self.stream.close()
            finally:
                self.store.finish(self.ident, self.actual, failed)
                log_event('model_stream_finished', call_id=self.ident, failed=failed)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close(bool(args[0]))

