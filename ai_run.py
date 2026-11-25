"""Durable memo stages with bounded retries and immutable attempt artifacts."""
import hashlib,json,time
from pathlib import Path
from theme_file_io import file_lock,write_json,read_json
from backend_observability import log_event,log_failure

class MemoRun:
    def __init__(self,root,identity):
        self.id=hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:32]
        self.path=Path(root)/self.id
        self.path.mkdir(parents=True,exist_ok=True)
        write_json(self.path/'identity.json',identity)
        self.update(status='running')

    def update(self,**changes):
        p=self.path/'manifest.json'
        with file_lock(p):
            state=read_json(p) if p.exists() else dict(run_id=self.id,created_at=time.time())
            state.update(changes,updated_at=time.time());write_json(p,state)

    def call(self,stage,invoke,validate,request=None):
        folder=self.path/stage
        with file_lock(folder):
            checkpoint=folder/'validated.json'
            if checkpoint.exists():
                value=read_json(checkpoint);validate(value)
                log_event('memo_stage_reused',run_id=self.id,stage=stage)
                return value
            for retry in range(3):
                folder.mkdir(parents=True,exist_ok=True)
                number=len(list(folder.glob('attempt-*')))+1
                attempt=folder/f'attempt-{number:03d}'
                write_json(attempt/'started.json',dict(at=time.time(),stage=stage))
                if request is not None:write_json(attempt/'request.json',request)
                self.update(stage=stage,status='recovering' if retry else 'running',attempt=number)
                log_event('memo_stage_started',run_id=self.id,stage=stage,attempt=number)
                try:
                    response=invoke()
                    artifact=response.model_dump(mode='json')
                    write_json(attempt/'response.json',artifact)
                    choice=response.choices[0]
                    if choice.finish_reason!='stop':
                        raise ValueError('模型输出未完整结束：'+str(choice.finish_reason))
                    value=json.loads(choice.message.content or '')
                    if not isinstance(value,dict):raise ValueError('模型结果必须为JSON对象')
                    validate(value)
                    write_json(attempt/'validated.json',value)
                    write_json(checkpoint,value)
                    write_json(attempt/'finished.json',dict(status='completed',at=time.time()))
                    log_event('memo_stage_validated',run_id=self.id,stage=stage,attempt=number)
                    return value
                except Exception as error:
                    status=getattr(error,'status_code',None)
                    local_status=getattr(error,'status',None)
                    retryable=(isinstance(error,ValueError) or
                        type(error).__name__ in ('APIConnectionError','APITimeoutError','RateLimitError') or status==429 or
                        bool(status and status>=500) or local_status==503)
                    write_json(attempt/'finished.json',dict(status='failed',error_type=type(error).__name__,
                        validation_error=str(error)[:400] if isinstance(error,ValueError) else None,
                        provider_status=status,at=time.time(),retryable=retryable))
                    log_failure('memo_stage_failed',error,run_id=self.id,stage=stage,attempt=number)
                    if retry==2 or not retryable:raise
                    time.sleep(retry+1)

    def complete(self):
        self.update(status='completed')
        log_event('memo_run_saved',run_id=self.id)

    def fail(self,error):
        self.update(status='failed',error_type=type(error).__name__)
        log_failure('memo_run_failed',error,run_id=self.id)
