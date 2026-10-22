"""Build an audio reference only; never replace the user's transcript."""
import json,subprocess,tempfile,gc,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent
def main():
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_asr import Qwen3ASRModel
    from audio_follow import audio_file
    project=(BASE/'projects'/sys.argv[1]).resolve()
    if project.parent!=(BASE/'projects').resolve():raise ValueError('Invalid project')
    device='cuda:0' if torch.cuda.is_available() else 'cpu'
    model=Qwen3ASRModel.from_pretrained(str(BASE/'Qwen3-ASR/Qwen3-ASR-0.6B'),dtype=torch.float16 if device.startswith('cuda') else torch.float32,device_map=device,local_files_only=True)
    ffmpeg=BASE/'venv312/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
    segments=[]
    with tempfile.TemporaryDirectory(prefix='paired-audio-') as folder:
        wave=Path(folder)/'audio.wav'
        subprocess.run([str(ffmpeg),'-v','error','-i',str(audio_file(project)),'-ac','1','-ar','16000',str(wave)],check=True)
        with sf.SoundFile(wave) as audio:
            sr=audio.samplerate;offset=0
            while True:
                clip=audio.read(sr*30,dtype='float32')
                if not len(clip):break
                with torch.inference_mode():
                    text=model.transcribe(audio=(clip,sr),language='Chinese')[0].text
                segments.append({'text':text,'start_ms':round(offset*1000),'end_ms':round((offset+len(clip)/sr)*1000)})
                offset+=len(clip)/sr
                print('REFERENCE_SEGMENT',len(segments),flush=True)
    del model;gc.collect()
    if torch.cuda.is_available():torch.cuda.empty_cache()
    reference=project/'关联录音转录.json'
    reference.write_text(json.dumps({'segments':segments,'purpose':'Timing reference only; user transcript unchanged'},ensure_ascii=False),encoding='utf-8')
    subprocess.run([sys.executable,str(BASE/'align_recordings.py'),'--project',project.name],check=True)
if __name__=='__main__':main()
