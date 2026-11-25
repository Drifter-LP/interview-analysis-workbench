"""Small, content-free request tracing shared by gateway and private workers."""
from contextvars import ContextVar
import json
import logging
import re
import time
import uuid

request_id = ContextVar('workbench_request_id', default='')
logger = logging.getLogger('workbench.backend')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    logger.addHandler(handler)
logger.propagate = False


def valid_request_id(value):
    return value if re.fullmatch(r'[A-Za-z0-9_-]{8,64}', value or '') else uuid.uuid4().hex


def log_event(event, **fields):
    # Callers supply identifiers/counts only, never prompts, headers or model text.
    logger.info(json.dumps({'event': event, 'request_id': request_id.get(), **fields}, ensure_ascii=False))


def log_failure(event, error, **fields):
    details = {'error_type': type(error).__name__}
    if isinstance(error, json.JSONDecodeError):
        details.update(line=error.lineno, column=error.colno, position=error.pos)
    logger.error(json.dumps({'event': event, 'request_id': request_id.get(), **details, **fields}, ensure_ascii=False))


def setup_request_tracking(app, role):
    app.add_middleware(RequestTrackingMiddleware, role=role)


class RequestTrackingMiddleware:
    """Keep context alive until the final streamed body, not just its headers."""
    def __init__(self, app, role):
        self.app, self.role = app, role

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        from starlette.datastructures import Headers, MutableHeaders
        ident = valid_request_id(Headers(scope=scope).get('x-request-id'))
        scope.setdefault('state', {})['request_id'] = ident
        token = request_id.set(ident)
        started = time.monotonic()
        status, complete = None, False
        async def tracked_send(message):
            nonlocal status, complete
            if message['type'] == 'http.response.start':
                status = message['status']
                MutableHeaders(scope=message)['X-Request-ID'] = ident
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                complete = True
            await send(message)
        try:
            await self.app(scope, receive, tracked_send)
            route = scope.get('route')
            log_event('request_finished', role=self.role, method=scope['method'],
                      route=getattr(route, 'path', '[unmatched]'), status=status,
                      body_complete=complete, elapsed_ms=round((time.monotonic()-started)*1000))
        except Exception as error:
            log_failure('request_failed', error, role=self.role, method=scope['method'], status=status)
            raise
        finally:
            request_id.reset(token)
