"""Read-only resume preflight. No model loading and no checkpoint writes."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess


def load_helper(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def ensure_worker_stopped():
    """A service restart must not launch a second copy of an orphaned worker."""
    if os.name!='nt':return
    command="@(Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Where-Object { $_.CommandLine -match 'qwen_transcribe[.]py' } | Select-Object -ExpandProperty ProcessId) | ConvertTo-Json -Compress"
    try:
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],
                              capture_output=True,text=True,encoding='utf8',errors='replace',timeout=15,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:raise ValueError('无法确认后台进程状态，请稍后重试；未启动新任务')
        processes=json.loads(result.stdout.strip() or '[]')
    except (OSError,subprocess.TimeoutExpired,ValueError) as exc:
        raise ValueError('无法确认后台转录进程是否已退出，请稍后重试；未启动新任务') from exc
    if processes:raise ValueError('后台仍有转录进程运行，不能重复启动，请等待其结束')


def presentation(meta, directory, active_project):
    result=dict(meta);directory=Path(directory)
    if result.get('status') in {'running','queued'} and active_project!=result.get('id'):
        result.update(status='interrupted',message='转录已中断，已保存的结果仍保留')
    checkpoint=(directory/'转录检查点.json').is_file()
    final=any(directory.glob('*_Qwen3-ASR转录.*'))
    result['resume_available']=checkpoint and not final and result.get('status') in {'interrupted','failed'}
    return result


def preflight(app_dir, directory):
    app_dir=Path(app_dir);directory=Path(directory);qwen=app_dir/'Qwen3-ASR'
    audio=list(directory.glob('原始录音.*'))
    if len(audio)!=1 or not audio[0].is_file():raise ValueError('未找到唯一的原始录音，不能继续转录')
    source=audio[0]
    if any(directory.glob('*_Qwen3-ASR转录.*')):raise ValueError('已存在正式转录结果，已停止续转，避免覆盖')
    checkpoint_path=directory/'转录检查点.json'
    if not checkpoint_path.is_file():raise ValueError('没有可恢复的检查点，已有录音未改动')
    helper=load_helper(qwen/'transcription_checkpoint.py','resume_checkpoint_helper')
    try:saved=json.loads(checkpoint_path.read_text(encoding='utf8'))
    except (ValueError,OSError) as exc:raise ValueError('检查点无法读取，已停止续转，未覆盖已有结果') from exc
    if not isinstance(saved,dict) or not isinstance(saved.get('identity'),dict):
        raise ValueError('检查点结构不完整，不能继续转录')
    identity={'audio_sha256':helper.file_hash(source),'model':str(qwen/'Qwen3-ASR-0.6B'),
              'context':'','language':'Chinese','max_new_tokens':512,'max_chunk_ms':30000,
              'pipeline_version':3,'sample_rate':16000}
    files={'model_config_sha256':qwen/'Qwen3-ASR-0.6B/config.json',
           'speaker_script_sha256':app_dir/'speaker_timeline.py',
           'window_script_sha256':qwen/'transcription_windows.py',
           'aligner_config_sha256':qwen/'Qwen3-ForcedAligner-0.6B/config.json',
           'transcriber_sha256':qwen/'qwen_transcribe.py'}
    for key,path in files.items():
        if not path.is_file():raise ValueError('缺少恢复所需的模型配置或程序文件：'+path.name)
        identity[key]=helper.file_hash(path)
    previous=saved.get('identity',{})
    if identity.get('audio_sha256')!=previous.get('audio_sha256'):
        raise ValueError('原始录音与检查点不一致，不能续转；已有结果未覆盖')
    if identity!=previous:
        raise ValueError('模型配置或转录程序版本与检查点不一致，不能安全续转；已有结果未覆盖')
    saved=helper.Checkpoint(directory).load(identity)
    if saved.get('status')=='completed':raise ValueError('检查点已完成，无需继续转录')
    if not saved.get('plan') or not saved.get('turns'):raise ValueError('检查点缺少识别分段或说话人时间轴')
    previous_end=0
    for turn in saved['turns']:
        if (any(type(turn.get(k)) is not int for k in ['speaker','start_ms','end_ms'])
                or turn['speaker']<1 or turn['start_ms']<previous_end or turn['end_ms']<=turn['start_ms']):
            raise ValueError('检查点的说话人时间轴无效，不能继续')
        previous_end=turn['end_ms']
    windows=load_helper(qwen/'transcription_windows.py','resume_window_helper')
    if windows.build_windows(saved['turns'],16000,previous_end*16)!=saved['plan']:
        raise ValueError('检查点的识别分段与当前程序不一致，不能继续')
    return source,saved['completed_chunks'],saved['total_chunks']
