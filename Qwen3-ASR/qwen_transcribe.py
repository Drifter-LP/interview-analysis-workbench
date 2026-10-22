import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

import soundfile as sf
import torch
from qwen_asr import Qwen3ASRModel


APP_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = APP_DIR / "Qwen3-ASR" / "Qwen3-ASR-0.6B"
FUNASR_PYTHON = APP_DIR / "venv312" / "Scripts" / "python.exe"
FUNASR_TRANSCRIBER = APP_DIR / "transcribe.py"
FFMPEG = APP_DIR / "venv312" / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries" / "ffmpeg-win-x86_64-v7.1.exe"
HOTWORD_FILES = (
    APP_DIR / "基层医疗常用词.txt",
    APP_DIR / "基层方言常用词.txt",
)


def emit(percent: int, message: str) -> None:
    print(f"@@PROGRESS|{percent}|{message}", flush=True)


def read_context() -> str:
    words = []
    for path in HOTWORD_FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            word = line.strip().split()[0] if line.strip() else ""
            if word and word not in words:
                words.append(word)
    return "基层医疗访谈。重点词汇：" + "、".join(words[:500])


def convert_audio(source: Path, target: Path) -> None:
    command = [
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "音频转换失败")


def diarize(wav_path: Path, diarization_dir: Path) -> list[dict]:
    """Use the existing FunASR VAD + CAM++ pipeline only as the speaker timeline."""
    command = [
        str(FUNASR_PYTHON), str(FUNASR_TRANSCRIBER), str(wav_path),
        "--output-dir", str(diarization_dir),
    ]
    process = subprocess.Popen(
        command,
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    log = []
    for line in process.stdout or []:
        log.append(line)
        if line.startswith("@@PROGRESS|"):
            try:
                raw = int(line.split("|", 2)[1])
                emit(5 + round(max(0, min(100, raw)) * 0.30), "CAM++正在区分说话人")
            except (ValueError, IndexError):
                pass
    if process.wait() != 0:
        raise RuntimeError("CAM++说话人区分失败：" + "".join(log)[-1000:])
    results = list(diarization_dir.glob("*_FunASR转录.json"))
    if not results:
        raise RuntimeError("CAM++没有生成说话人时间轴")
    data = json.loads(results[0].read_text(encoding="utf-8"))
    turns = data.get("merged_turns") or []
    if not turns:
        raise RuntimeError("没有检测到可用的说话人发言段")
    return turns


def build_speaker_chunks(turns: list[dict], sample_rate: int, total_samples: int) -> list[dict]:
    """Split long speaker turns into GPU-safe pieces while preserving speaker labels."""
    chunks = []
    max_ms = 30_000
    for turn in turns:
        speaker = int(turn.get("speaker", 0))
        start_ms = max(0, int(turn.get("start_ms", 0)))
        end_ms = min(round(total_samples / sample_rate * 1000), int(turn.get("end_ms", 0)))
        while start_ms < end_ms:
            piece_end = min(end_ms, start_ms + max_ms)
            chunks.append({"speaker": speaker, "start_ms": start_ms, "end_ms": piece_end})
            start_ms = piece_end
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen3-ASR 0.6B transcription for the desktop interview app")
    parser.add_argument("audio")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    source = Path(args.audio)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_txt = output_dir / f"{source.stem}_Qwen3-ASR转录.txt"
    output_json = output_dir / f"{source.stem}_Qwen3-ASR转录.json"
    started = time.time()

    emit(3, "正在准备千问ASR和音频")
    (APP_DIR / "temp").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qwen_asr_", dir=str(APP_DIR / "temp")) as temp_dir:
        temp_path = Path(temp_dir)
        wav_path = temp_path / "audio.wav"
        convert_audio(source, wav_path)
        wav, sample_rate = sf.read(str(wav_path), dtype="float32")
        emit(5, "正在使用CAM++区分说话人")
        turns = diarize(wav_path, temp_path / "diarization")

    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    speaker_chunks = build_speaker_chunks(turns, sample_rate, len(wav))
    emit(36, "说话人时间轴完成，正在加载Qwen3-ASR 0.6B")
    model = Qwen3ASRModel.from_pretrained(
        str(MODEL_DIR),
        device_map="cuda:0",
        dtype=torch.float16,
        attn_implementation="sdpa",
        max_inference_batch_size=1,
        max_new_tokens=512,
    )

    total_chunks = len(speaker_chunks)
    context = read_context()
    transcribed_segments = []
    detected_language = "Chinese"
    for index, chunk in enumerate(speaker_chunks, 1):
        start = round(chunk["start_ms"] / 1000 * sample_rate)
        end = round(chunk["end_ms"] / 1000 * sample_rate)
        result = model.transcribe(
            (wav[start:end], sample_rate),
            context=context,
            language="Chinese",
            return_time_stamps=False,
        )[0]
        detected_language = result.language
        if result.text.strip():
            transcribed_segments.append({**chunk, "text": result.text.strip()})
        progress = 38 + round(index / total_chunks * 56)
        emit(progress, f"千问ASR正在转录：第{index}/{total_chunks}段")

    merged = []
    for segment in transcribed_segments:
        if merged and merged[-1]["speaker"] == segment["speaker"]:
            merged[-1]["end_ms"] = segment["end_ms"]
            merged[-1]["text"] += segment["text"]
        else:
            merged.append(dict(segment))
    full_text = "\n\n".join(f"说话人{item['speaker']}：{item['text']}" for item in merged)
    output_txt.write_text(full_text + "\n", encoding="utf-8-sig")
    output_json.write_text(
        json.dumps(
            {
                "engine": "Qwen3-ASR-0.6B",
                "audio": str(source),
                "language": detected_language,
                "speaker_engine": "FunASR CAM++",
                "chunk_seconds_max": 30,
                "elapsed_seconds": round(time.time() - started, 2),
                "segments": transcribed_segments,
                "merged_turns": merged,
                "text": full_text,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    emit(100, "千问ASR转录完成")


if __name__ == "__main__":
    main()
