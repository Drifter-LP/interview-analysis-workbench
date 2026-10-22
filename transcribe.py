import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
MODEL_CACHE = APP_DIR / "models"
OUTPUT_DIR = APP_DIR / "outputs"
HOTWORD_FILES = (
    APP_DIR / "基层医疗常用词.txt",
    APP_DIR / "基层方言常用词.txt",
)

# Keep every model and temporary model-hub file on D:.
os.environ.setdefault("MODELSCOPE_CACHE", str(MODEL_CACHE))
os.environ.setdefault("HF_HOME", str(MODEL_CACHE / "huggingface"))
os.environ.setdefault("TEMP", str(APP_DIR / "temp"))
os.environ.setdefault("TMP", str(APP_DIR / "temp"))


def choose_audio() -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    selected = filedialog.askopenfilename(
        title="选择需要转录的录音",
        filetypes=[
            ("音频文件", "*.m4a *.mp3 *.wav *.aac *.flac *.ogg *.wma"),
            ("所有文件", "*.*"),
        ],
    )
    root.destroy()
    return Path(selected) if selected else None


def read_hotwords() -> str:
    words = []
    for hotword_file in HOTWORD_FILES:
        if not hotword_file.exists():
            continue
        for line in hotword_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                words.extend(line.split())
    return " ".join(dict.fromkeys(words))


def prepare_audio(audio_path: Path, work_dir: Path) -> Path:
    if audio_path.suffix.lower() == ".wav":
        return audio_path
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("缺少音频转换组件 imageio-ffmpeg。") from exc

    wav_path = work_dir / f"{audio_path.stem}_16k.wav"
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError("音频转换失败：\n" + completed.stderr[-2000:])
    return wav_path


def clean_text(text: str) -> str:
    text = re.sub(r"<\|[^|]+\|>", "", text or "")
    text = re.sub(r"\s+", "", text)
    return text.strip()


def timecode(milliseconds) -> str:
    total_seconds = max(0, int(float(milliseconds or 0) / 1000))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def normalize_segments(result: list) -> list[dict]:
    segments = []
    for item in result or []:
        sentence_info = item.get("sentence_info") or []
        if sentence_info:
            for sentence in sentence_info:
                text = clean_text(sentence.get("text", ""))
                if not text:
                    continue
                speaker = sentence.get("spk", 0)
                try:
                    speaker = int(speaker)
                except (TypeError, ValueError):
                    speaker = 0
                segments.append(
                    {
                        "speaker": speaker + 1,
                        "start_ms": sentence.get("start", 0),
                        "end_ms": sentence.get("end", 0),
                        "text": text,
                    }
                )
        else:
            text = clean_text(item.get("text", ""))
            if text:
                segments.append(
                    {"speaker": 1, "start_ms": 0, "end_ms": 0, "text": text}
                )
    return segments


def merge_same_speaker(segments: list[dict]) -> list[dict]:
    merged = []
    for segment in segments:
        if merged and merged[-1]["speaker"] == segment["speaker"]:
            merged[-1]["text"] += segment["text"]
            merged[-1]["end_ms"] = segment["end_ms"]
        else:
            merged.append(dict(segment))
    return merged


def smooth_short_turns(segments: list[dict], max_chars: int = 6) -> list[dict]:
    """Repair tiny A-B-A diarization glitches without guessing longer turns."""
    smoothed = [dict(segment) for segment in segments]
    for index in range(1, len(smoothed) - 1):
        previous = smoothed[index - 1]
        current = smoothed[index]
        following = smoothed[index + 1]
        if (
            previous["speaker"] == following["speaker"]
            and current["speaker"] != previous["speaker"]
            and len(re.sub(r"[，。！？、；：,.!?;:\s]", "", current["text"])) <= max_chars
        ):
            current["speaker"] = previous["speaker"]
    return smoothed


def load_model(device: str):
    from funasr import AutoModel

    return AutoModel(
        model="paraformer-zh",
        vad_model="fsmn-vad",
        punc_model="ct-punc",
        spk_model="cam++",
        device=device,
        disable_update=True,
    )


def transcribe(audio_path: Path, prefer_cpu: bool = False) -> tuple[list, str]:
    APP_DIR.joinpath("temp").mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    hotwords = read_hotwords()
    device = "cpu" if prefer_cpu else "cuda:0"

    with tempfile.TemporaryDirectory(dir=APP_DIR / "temp") as temporary:
        print("@@PROGRESS|10|正在检查并转换音频格式", flush=True)
        prepared = prepare_audio(audio_path, Path(temporary))
        print("@@PROGRESS|22|音频准备完成，正在加载本地模型", flush=True)
        try:
            model = load_model(device)
            print("@@PROGRESS|-1|正在识别语音、恢复标点并区分说话人", flush=True)
            result = model.generate(
                input=str(prepared),
                hotword=hotwords,
                preset_spk_num=2,
                batch_size_s=60,
                merge_vad=True,
                merge_length_s=15,
            )
            print("@@PROGRESS|88|语音识别完成，正在整理发言单元", flush=True)
        except RuntimeError as exc:
            if prefer_cpu or "memory" not in str(exc).lower():
                raise
            print("显存不足，正在自动改用CPU继续……", flush=True)
            try:
                import torch

                torch.cuda.empty_cache()
            except Exception:
                pass
            model = load_model("cpu")
            device = "cpu"
            print("@@PROGRESS|-1|正在使用CPU识别语音、恢复标点并区分说话人", flush=True)
            result = model.generate(
                input=str(prepared),
                hotword=hotwords,
                preset_spk_num=2,
                batch_size_s=30,
                merge_vad=True,
                merge_length_s=15,
            )
            print("@@PROGRESS|88|语音识别完成，正在整理发言单元", flush=True)
    return result, device


def save_outputs(audio_path: Path, result: list, device: str, elapsed: float, output_dir: Path = OUTPUT_DIR) -> tuple[Path, Path]:
    segments = smooth_short_turns(normalize_segments(result))
    merged = merge_same_speaker(segments)
    stem = audio_path.stem + "_FunASR转录"
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / f"{stem}.txt"
    json_path = output_dir / f"{stem}.json"

    txt_lines = [f"说话人{x['speaker']}：{x['text']}" for x in merged]
    txt_path.write_text("\n\n".join(txt_lines) + "\n", encoding="utf-8-sig")

    payload = {
        "source_audio": str(audio_path),
        "engine": "FunASR paraformer-zh",
        "device": device,
        "elapsed_seconds": round(elapsed, 2),
        "segments": segments,
        "merged_turns": merged,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return txt_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="基层医疗访谈录音转录")
    parser.add_argument("audio", nargs="?", help="音频文件路径；不填写则弹出选择窗口")
    parser.add_argument("--cpu", action="store_true", help="强制使用CPU")
    parser.add_argument("--output-dir", help="指定输出目录")
    args = parser.parse_args()

    audio_path = Path(args.audio.strip('"')) if args.audio else choose_audio()
    if not audio_path:
        print("没有选择音频。")
        return 1
    if not audio_path.is_file():
        print(f"找不到音频：{audio_path}")
        return 1

    print(f"开始转录：{audio_path}", flush=True)
    started = time.time()
    try:
        result, device = transcribe(audio_path, args.cpu)
        print("@@PROGRESS|94|正在合并连续发言并保存原始转录稿", flush=True)
        destination = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
        txt_path, json_path = save_outputs(audio_path, result, device, time.time() - started, destination)
    except Exception as exc:
        print(f"转录失败：{exc}", file=sys.stderr)
        return 2

    print(f"转录完成，使用设备：{device}")
    print(f"TXT：{txt_path}")
    print(f"JSON：{json_path}")
    print("@@PROGRESS|100|转录完成", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
