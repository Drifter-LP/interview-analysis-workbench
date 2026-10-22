"""Generate resumable acoustic alignment caches; never modify source material."""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent

def save(path, data):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--project');args=parser.parse_args()
    from audio_follow import audio_file
    jobs=[]
    for project in sorted((BASE/'projects').iterdir()):
        if args.project and project.name!=args.project:continue
        if not project.is_dir() or not audio_file(project):
            continue
        link=project/'录音关联.json'
        sources=[project/json.loads(link.read_text(encoding='utf-8')).get('reference','关联录音转录.json')] if link.exists() else sorted(project.glob('*转录.json'))
        for source in sources:
            if not source.exists():continue
            data=json.loads(source.read_text(encoding='utf-8-sig'))
            if data.get('segments'):
                jobs.append((project,source,data));break
    print('PROJECTS',len(jobs),flush=True)
    import soundfile as sf
    import torch
    from qwen_asr import Qwen3ForcedAligner
    device='cuda:0' if torch.cuda.is_available() else 'cpu'
    model=Qwen3ForcedAligner.from_pretrained(str(BASE/'Qwen3-ASR/Qwen3-ForcedAligner-0.6B'),dtype=torch.float16 if device.startswith('cuda') else torch.float32,device_map=device,local_files_only=True)
    ffmpeg=BASE/'venv312/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
    failed=0
    for project,source,data in jobs:
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        path=project/'录音对齐.json'
        cache={'source_sha256':digest,'aligned_segments':[],'failed_segments':[],'status':'running'}
        if path.exists():
            existing=json.loads(path.read_text(encoding='utf-8'))
            if existing.get('source_sha256')==digest:
                cache['aligned_segments']=existing.get('aligned_segments',[existing] if 'segment_index' in existing else [])
        done={entry['segment_index'] for entry in cache['aligned_segments']}
        print('PROJECT_START',project.name,'segments',len(data['segments']),flush=True)
        for index,segment in enumerate(data['segments']):
            if index in done:
                continue
            try:
                start,end=segment['start_ms']/1000,segment['end_ms']/1000
                if not 0<=start<end or end-start>300 or not segment.get('text','').strip():
                    raise ValueError('Invalid or overlong source segment; retained coarse fallback')
                with tempfile.TemporaryDirectory(prefix='word-align-') as folder:
                    wave=Path(folder)/'clip.wav'
                    subprocess.run([str(ffmpeg),'-v','error','-ss',str(start),'-i',str(audio_file(project)),'-t',str(end-start),'-ac','1','-ar','16000',str(wave)],check=True)
                    audio,sr=sf.read(wave,dtype='float32')
                    with torch.inference_mode():
                        items=model.align(audio=(audio,sr),text=segment['text'],language='Chinese')[0].items
                    words=[{'text':it.text,'start':round(start+it.start_time,3),'end':round(start+it.end_time,3)} for it in items]
                if not words or not all(start<=w['start']<=w['end']<=end+.2 for w in words) or not all(a['start']<=b['start'] for a,b in zip(words,words[1:])):
                    raise ValueError('Timestamp bounds/order failed; retained coarse fallback')
                cache['aligned_segments'].append({'segment_index':index,'words':words})
                cache['aligned_segments'].sort(key=lambda entry:entry['segment_index'])
            except Exception as error:
                cache['failed_segments'].append({'segment_index':index,'error':str(error)})
                print('SEGMENT_FAILED',project.name,index,str(error),flush=True)
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            save(path,cache)
            print('PROGRESS',project.name,index+1,len(data['segments']),flush=True)
        cache['status']='completed_with_fallback' if cache['failed_segments'] else 'completed'
        save(path,cache)
        failed+=len(cache['failed_segments'])
        print('PROJECT_DONE',project.name,cache['status'],flush=True)
    print('ALL_DONE','fallback_segments',failed,flush=True)

if __name__=='__main__':
    main()
