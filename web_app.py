import json
import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from functools import lru_cache
from contextvars import copy_context
from theme_file_io import read_json as read_theme_json
from correction_speed import select_paragraphs, restore_paragraphs, RULES as PUNCTUATION_SCREEN_RULES

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from concurrent.futures import ThreadPoolExecutor
from interview_facts import limited_create
from site_store import SiteError
from backend_storage import atomic_write_json, atomic_write_text, read_json_document, locked_document, document_transaction
from theme_file_io import file_lock
from backend_observability import setup_request_tracking, request_id, log_event, log_failure
from fastapi.responses import JSONResponse


CODE_DIR = Path(__file__).resolve().parent
APP_DIR = Path(os.environ.get('WORKBENCH_DATA_DIR', str(CODE_DIR))).resolve()
STATIC_DIR = CODE_DIR / "web"
PROJECTS_DIR = APP_DIR / "projects"
RESEARCH_PROJECTS_DIR = APP_DIR / "research_projects"
RESEARCH_FILES_DIR = APP_DIR / "research_project_files"
QWEN_DIR = CODE_DIR / "Qwen3-ASR"
QWEN_MODEL = QWEN_DIR / "Qwen3-ASR-0.6B"
PYTHON = QWEN_DIR / "venv312" / "Scripts" / "python.exe"
TRANSCRIBER = QWEN_DIR / "qwen_transcribe.py"
HOTWORDS = CODE_DIR / "基层医疗热词.txt"
SUPPORTED = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma"}
MAX_AI_SUGGESTION_CHARS = 80
LOCAL_DIRECT_REPLACEMENTS = {
    "以保资金不合理使用转向政治": "医保资金不合理使用专项整治", "一物人员的工资买保障": "医务人员的工资没保障",
    "医膜管不到那么实": "医保管不了那么死", "以保转向政治": "医保专项整治", "医保转向政治": "医保专项整治",
    "处罚和移除": "处方和医嘱", "美流表中化": "没有标准化", "没流标准化": "没有标准化",
    "乙胞基因": "医保基金", "义保基金": "医保基金", "一包基金": "医保基金", "尼摩基因": "医保基金",
    "主要侦探": "主要诊断", "次要侦探": "次要诊断", "第一位侦探": "第一位诊断", "四季伯父": "实际拨付",
    "业务数字": "业务素质", "中医有服务": "中医药服务", "卡夫医疗技术": "康复医疗技术", "肺功能感染": "肺部感染",
    "再加里": "在家里", "在加里": "在家里", "大病棚头": "大病统筹", "前天一流": "千篇一律",
    "结算例": "结算率", "介绍率": "结算率", "结算力": "结算率", "洗衣室": "西医师", "裁缝线": "踩红线",
    "毁神": "亏损", "包几本": "保基本", "粉质": "分值", "粉值": "分值", "乙胞局": "医保局",
    "一国区": "医保局", "乙胞": "医保", "以保": "医保", "义保": "医保", "侦探": "诊断",
    "会复": "恢复", "体愿": "情愿", "DSP": "DIP", "DMP": "DIP", "第2P": "DIP", "第二批": "DIP",
    "DRRG": "DRG", "DR、RG": "DRG", "第二级": "DRG",
}
active_lock = threading.Lock()
active_project: str | None = None

os.environ.setdefault("MODELSCOPE_CACHE", str(CODE_DIR / "models"))
os.environ.setdefault("HF_HOME", str(CODE_DIR / "models" / "huggingface"))
os.environ.setdefault("TEMP", str(APP_DIR / "temp"))
os.environ.setdefault("TMP", str(APP_DIR / "temp"))

app = FastAPI(title="访谈分析工作台")


@app.exception_handler(SiteError)
async def site_error_response(request, error):
    log_failure('site_error', error, status=error.status)
    return JSONResponse({'detail': str(error), 'request_id': request_id.get()}, status_code=error.status)


@app.exception_handler(Exception)
async def unexpected_error_response(request, error):
    log_failure('unexpected_error', error)
    ident = getattr(request.state, 'request_id', '') or request_id.get()
    return JSONResponse({'detail': '处理失败，请联系管理员并提供请求编号',
                         'request_id': ident}, status_code=500,
                        headers={'X-Request-ID': ident})


@app.exception_handler(HTTPException)
async def http_error_response(request, error):
    if error.status_code >= 500:
        log_failure('http_operation_failed', error, status=error.status_code)
    return JSONResponse({'detail': error.detail, 'request_id': request_id.get()},
                        status_code=error.status_code, headers=error.headers)


def decode_model_json(response, stage):
    choice = response.choices[0]
    if choice.finish_reason != 'stop':
        log_event('model_output_incomplete', stage=stage, finish_reason=str(choice.finish_reason))
        raise HTTPException(502, '模型输出未完整结束，本次未保存，请缩小材料范围后重试')
    try:
        value = json.loads(choice.message.content or '{}')
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return value
    except (ValueError, TypeError) as error:
        log_failure('model_json_invalid', error, stage=stage)
        raise HTTPException(502, '模型返回的数据格式不完整，本次未保存；请提供请求编号以便排查') from error


from site_boundary import protect_worker
protect_worker(app)
setup_request_tracking(app, 'worker')
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


def safe_id(value: str) -> str:
    clean = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", value.strip()).strip("-")
    return clean[:48] or time.strftime("访谈-%Y%m%d-%H%M%S")


def project_dir(project_id: str) -> Path:
    path = (PROJECTS_DIR / project_id).resolve()
    if path.parent != PROJECTS_DIR.resolve():
        raise HTTPException(400, "项目编号无效")
    return path


def metadata_path(project_id: str) -> Path:
    return project_dir(project_id) / "project.json"


def read_metadata(project_id: str) -> dict:
    path = metadata_path(project_id)
    if not path.exists():
        raise HTTPException(404, "项目不存在")
    return read_json_document(path)


def write_metadata(project_id: str, data: dict) -> None:
    atomic_write_json(metadata_path(project_id), data)


def patch_metadata(project_id: str, **changes):
    with document_transaction(metadata_path(project_id)):
        meta = read_metadata(project_id)
        meta.update(changes)
        write_metadata(project_id, meta)
        return meta


def transcript_path(project_id: str) -> Path | None:
    directory = project_dir(project_id)
    candidates = [
        directory / "校订稿.txt", directory / "DeepSeek自动校订稿.txt",
        directory / "本地自动整理稿.txt", directory / "导入访谈稿.txt", *directory.glob("*_FunASR转录.txt"),
        *directory.glob("*_Qwen3-ASR转录.txt"),
    ]
    existing = [path for path in candidates if path.exists()]
    return max(existing, key=lambda path: path.stat().st_mtime) if existing else None


def analysis_path(project_id: str) -> Path:
    return project_dir(project_id) / "定性分析项目.json"


def empty_analysis() -> dict:
    return {"metadata": {}, "sources": [], "codes": [], "excerpts": [], "ai_suggestions": [], "updated_at": time.time()}


def read_analysis(project_id: str) -> dict:
    path = analysis_path(project_id)
    if not path.exists():
        return empty_analysis()
    data = read_json_document(path)
    for key, default in (("metadata", {}), ("sources", []), ("codes", []), ("excerpts", []), ("ai_suggestions", [])):
        data.setdefault(key, default)
    return data


def read_deepseek_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as registry_key:
            value, _ = winreg.QueryValueEx(registry_key, "DEEPSEEK_API_KEY")
            return str(value).strip()
    except (ImportError, OSError):
        return ""


def apply_local_preprocessing(text: str) -> tuple[str, list[dict], dict]:
    changes = []

    def record(old: str, new: str, change_type: str, reason: str, count: int = 1) -> None:
        for _ in range(count):
            changes.append({"from": old, "to": new, "type": change_type, "reason": reason, "confidence": "高"})

    for old, new in sorted(LOCAL_DIRECT_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        count = text.count(old)
        if count:
            text = text.replace(old, new)
            record(old, new, "ASR错词", "用户确认的高置信度替换。", count)

    fixed_stutters = {
        "所所以": "所以", "然然后": "然后", "但但是": "但是", "可可是": "可是", "就就是": "就是",
        "还还是": "还是", "还是是": "还是", "这这个": "这个", "那那个": "那个",
    }
    repetition_patterns = [(re.escape(old), new) for old, new in fixed_stutters.items()]
    repetition_patterns += [(r"(?:这个|这)(?:[\s，、,]*(?:这个|这)){1,}", "这个"), (r"(?:那个|那)(?:[\s，、,]*(?:那个|那)){1,}", "那个")]
    repetition_patterns += [(rf"(?:{re.escape(word)})(?:[\s，、,]*{re.escape(word)})+", word) for word in ("然后", "就是", "所以", "但是", "还是", "这个", "那个", "都", "有", "是", "你", "我", "他", "对")]
    repetition_patterns.append((r"[嗯啊呃哎哦额](?:[\s，、,]*[嗯啊呃哎哦额]){1,}", None))
    repetition_count = 0
    for pattern, replacement in repetition_patterns:
        def replace_repeat(match, replacement=replacement):
            nonlocal repetition_count
            old = match.group(0)
            if replacement is None:
                found = re.search(r"[嗯啊呃哎哦额]", old)
                new = found.group(0) if found else old
            else:
                new = replacement
            if old != new:
                repetition_count += 1
                record(old, new, "口语重复", "清理明确的口吃式机械重复。")
            return new
        text = re.sub(pattern, replace_repeat, text)

    modal_count = 0
    def add_modal_comma(match):
        nonlocal modal_count
        old = match.group(1); modal_count += 1
        record(old, old + "，", "标点", "语气词后补充逗号。")
        return old + "，"
    text = re.sub(r"([呀呃嗯呢吧])(?![，。！？；：、,.!?;:\s])(?=[\u3400-\u9fffA-Za-z0-9])", add_modal_comma, text)

    punctuation_count = 0
    translate = str.maketrans({",": "，", ".": "。", "?": "？", "!": "！", ";": "；", ":": "："})
    def clean_punctuation(match):
        nonlocal punctuation_count
        old = match.group(0); normalized = old.translate(translate)
        terminal = [char for char in normalized if char in "。！？"]
        new = terminal[-1] if terminal else ("；" if "；" in normalized else ("：" if "：" in normalized else ("，" if "，" in normalized else "、")))
        if old != new:
            punctuation_count += 1
            record(old, new, "标点", "清理连续、重复或冲突标点。")
        return new
    text = re.sub(r"[，。！？；：、,.!?;:]{2,}", clean_punctuation, text)
    counts = {
        "total": len(changes), "repetitions": repetition_count,
        "modal_commas": modal_count, "punctuation": punctuation_count,
    }
    return text, changes, counts


def split_long_paragraphs(text: str, limit: int = 300) -> str:
    output = []
    for paragraph in text.splitlines() or [text]:
        remaining = paragraph.strip()
        while len(remaining) > limit:
            window_start = max(1, limit - 80)
            cut = max((remaining.rfind(mark, window_start, limit) for mark in "。！？；"), default=-1)
            if cut < 0:
                cut = remaining.rfind("，", window_start, limit)
            if cut < 0:
                cut = limit - 1
            output.append(remaining[:cut + 1].strip()); remaining = remaining[cut + 1:].strip()
        if remaining:
            output.append(remaining)
    return "\n\n".join(output)


def build_review_annotations(text: str, changes: list[dict]) -> list[dict]:
    """Locate AI word changes in the final text for lightweight human review."""
    annotations, occupied, cursors = [], [], {}
    for change in changes:
        confidence = str(change.get("confidence", "")).strip()
        revised = str(change.get("to", ""))
        if change.get('rejected') or not change.get("applied") or change.get("stage") != "word" or not revised:
            continue
        start = text.find(revised, cursors.get(revised, 0))
        while start >= 0 and any(not (start + len(revised) <= left or start >= right) for left, right in occupied):
            start = text.find(revised, start + len(revised))
        if start < 0:
            continue
        end = start + len(revised)
        change_id = change.setdefault("change_id", uuid.uuid4().hex)
        accepted = bool(change.get("accepted", False))
        annotations.append({
            "change_id": change_id, "start": start, "end": end,
            "original": str(change.get("from", "")), "revised": revised,
            "confidence": confidence, "accepted": accepted,
        })
        occupied.append((start, end)); cursors[revised] = end
    return sorted(annotations, key=lambda item: item["start"])


def run_transcription(project_id: str, audio_path: Path, resume: bool = False) -> None:
    global active_project
    directory = project_dir(project_id)
    meta = patch_metadata(project_id, status="running",
                          message="正在从检查点继续转录" if resume else "正在加载模型并转录",
                          **{'resumed_at' if resume else 'started_at': time.time()})
    log_path = directory / "运行记录.txt"
    command = [
        str(PYTHON),
        str(TRANSCRIBER),
        str(audio_path),
        "--output-dir",
        str(directory),
    ]
    if resume:command.append('--resume')
    try:
        completed = subprocess.run(
            command,
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        with log_path.open('a' if resume else 'w',encoding='utf8') as log:
            if resume:log.write('\n【从检查点继续转录】\n')
            log.write((completed.stdout or '')+'\n'+(completed.stderr or ''))
        if completed.returncode == 0:
            patch_metadata(project_id,
                status="completed",
                finished_at=time.time(),
                message="转录完成，可以校订和分析",
            )
        else:
            patch_metadata(project_id, status="failed", message="转录失败，请查看运行记录")
    except (SiteError, HTTPException):
        raise
    except Exception as exc:
        patch_metadata(project_id, status="failed", message=str(exc))
    finally:
        with active_lock:
            if active_project==project_id:active_project = None


class TranscriptUpdate(BaseModel):
    text: str
    accepted_change_ids: list[str] = []
    rejected_change_ids: list[str] = []


class ChangeDecision(BaseModel):
    change_id: str


class AnalysisUpdate(BaseModel):
    data: dict


class CodingRequest(BaseModel):
    research_question: str = ""


class MemoRequest(BaseModel):
    refresh: bool = False


class MaterialComparisonRequest(BaseModel):
    project_ids: list[str]
    research_project_id: str = ""
    theme: str = ""
    dimensions: list[str] = []
    theme_analysis_id: str = ""


class MaterialComparisonSaveRequest(BaseModel):
    comparison: dict


class MaterialComparisonRenameRequest(BaseModel):
    name: str


class ThemeAnalysisRequest(BaseModel):
    research_project_id: str
    project_ids: list[str]
    theme: str
    resume_run_id: str = ""
    request_token: str = ""


class ThemeAnalysisSaveRequest(BaseModel):
    analysis: dict
    request_id: str = ""


def read_uploaded_transcript(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix == ".txt":
        raw = upload.file.read()
        # TXT files from Windows editors may be UTF-8, legacy Chinese encodings,
        # or UTF-16. Detect the BOM first so NUL bytes are not mistaken for text.
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            encodings = ("utf-16",)
        else:
            encodings = ("utf-8-sig", "utf-8", "gb18030")
        for encoding in encodings:
            try:
                return raw.decode(encoding).replace("\x00", "").strip()
            except UnicodeDecodeError:
                continue
        raise HTTPException(400, "无法识别TXT文件编码")
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(upload.file) as archive:
                if os.environ.get('SITE_USER_ID') and (len(archive.infolist()) > 2000 or sum(i.file_size for i in archive.infolist()) > 20*1024*1024):
                    raise HTTPException(413, 'Word解压内容超过20MB限制')
                xml_data = archive.read("word/document.xml")
        except (KeyError, zipfile.BadZipFile, OSError) as exc:
            raise HTTPException(400, "Word文件无法读取，请确认它是有效的DOCX文件") from exc
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as exc:
            raise HTTPException(400, "Word文件内容格式异常") from exc
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        body = root.find("w:body", ns)
        if body is None:
            return ""
        blocks = []
        for element in body:
            if element.tag.endswith("}p"):
                text = "".join(node.text or "" for node in element.findall(".//w:t", ns))
                if text.strip():
                    blocks.append(text.strip())
            elif element.tag.endswith("}tbl"):
                for row in element.findall(".//w:tr", ns):
                    cells = []
                    for cell in row.findall("w:tc", ns):
                        cell_text = "".join(node.text or "" for node in cell.findall(".//w:t", ns)).strip()
                        if cell_text:
                            cells.append(cell_text)
                    if cells:
                        blocks.append("\t".join(cells))
        return "\n".join(blocks).strip()
    raise HTTPException(400, "目前支持导入 TXT 或 DOCX 访谈稿")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def status():
    if os.environ.get('WORKBENCH_TEXT_ONLY') == '1':
        return {"ready": False, "gpu": None, "model_count": 0, "engine": None,
                "speaker_engine": None, "active_project": None, "text_only": True}
    ready = PYTHON.exists() and TRANSCRIBER.exists() and (QWEN_MODEL / "config.json").exists()
    return {
        "ready": ready,
        "gpu": gpu_name(),
        "model_count": 1 if ready else 0,
        "engine": "Qwen3-ASR-0.6B",
        "speaker_engine": "CAM++",
        "active_project": active_project,
    }


@lru_cache(maxsize=1)
def gpu_name():
    configured = os.environ.get('WORKBENCH_GPU_NAME', '').strip()
    if configured:
        return configured[:200]
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                                capture_output=True, text=True, timeout=1.5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        names = result.stdout.strip().splitlines() if result.returncode == 0 else []
        return names[0][:200] if names else None
    except (OSError, subprocess.SubprocessError):
        return None


@app.get("/api/projects")
def list_projects():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    from interview_names import normalize_names
    try:
        normalize_names(PROJECTS_DIR, RESEARCH_PROJECTS_DIR, RESEARCH_FILES_DIR,
                        APP_DIR / "backups", refresh_material_names)
    except (SiteError, OSError, ValueError) as error:
        log_failure('name_normalization_failed', error)
    return list_project_metadata()


def list_project_metadata():
    projects = []
    for path in PROJECTS_DIR.iterdir():
        meta = path / "project.json"
        if path.is_dir() and meta.exists():
            try:
                item = read_json_document(meta)
                from transcription_recovery import presentation
                item=presentation(item,path,active_project)
                item["hidden_in_library"] = bool(item.get("hidden_at") or item.get("deleted_at"))
                projects.append(item)
            except Exception as error:
                log_failure('interview_listing_failed', error, file=meta.name)
                continue
    return sorted(projects, key=lambda item: item.get("created_at", 0), reverse=True)


@app.delete("/api/projects/{project_id}")
def delete_interview(project_id: str):
    from interview_library import archive_interview
    with active_lock:
        meta = read_metadata(project_id)
        if active_project == project_id or meta.get("status") in {"queued", "running"}:
            raise HTTPException(409, "访谈正在转录，请完成后再删除")
        try:
            return archive_interview(APP_DIR, PROJECTS_DIR, RESEARCH_PROJECTS_DIR, RESEARCH_FILES_DIR, project_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@app.post("/api/projects/{project_id}/opened")
def mark_interview_opened(project_id: str):
    with active_lock:
        with document_transaction(metadata_path(project_id)):
            meta = read_metadata(project_id)
            meta["last_opened_at"] = time.time()
            write_metadata(project_id, meta)
    return {"last_opened_at": meta["last_opened_at"]}


class InterviewVisibilityRequest(BaseModel):
    hidden: bool


@app.post("/api/projects/{project_id}/visibility")
def set_interview_visibility(project_id: str, body: InterviewVisibilityRequest):
    """Visibility affects only the library, not material pickers or analysis."""
    with active_lock, document_transaction(metadata_path(project_id)):
        meta = read_metadata(project_id)
        if body.hidden and (active_project == project_id or meta.get("status") in {"queued", "running"}):
            raise HTTPException(409, "访谈正在转录，请完成后再隐藏")
        meta.pop("deleted_at", None)
        if body.hidden:
            meta["hidden_at"] = time.time()
        else:
            meta.pop("hidden_at", None)
        write_metadata(project_id, meta)
    return {"hidden": body.hidden, "recoverable": True}


def research_project_path(project_id: str) -> Path:
    path = (RESEARCH_PROJECTS_DIR / f"{project_id}.json").resolve()
    if path.parent != RESEARCH_PROJECTS_DIR.resolve():
        raise HTTPException(400, "研究项目编号无效")
    return path




@app.get("/api/research-projects")
def list_research_projects(summaries: bool = False):
    return research_project_list(list_projects(), summaries)


def research_project_list(projects, summaries):
    RESEARCH_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    interview_names = {item.get("id"): item.get("name", "") for item in projects}
    items = []
    for path in RESEARCH_PROJECTS_DIR.glob("*.json"):
        try:
            with document_transaction(path):
                item = read_json_document(path)
                changed = False
                from review_storage import refresh_display_names, project_listing
                refresh_display_names(item, interview_names)
                material_types = item.setdefault("material_types", {})
                for interview_id in item.get("interview_ids", []):
                    if interview_id not in material_types:
                        material_types[interview_id] = "interview"
                        changed = True
                for material in item.setdefault("uploaded_transcripts", []):
                    if "material_type" not in material:
                        material["material_type"] = "interview"
                        changed = True
                item["interviews"] = [
                    {"id": interview_id, "name": interview_names.get(interview_id, interview_id), "material_type": material_types.get(interview_id, "interview")}
                    for interview_id in item.get("interview_ids", [])
                ]
                if changed:
                    atomic_write_json(path, {key: value for key, value in item.items() if key != "interviews"})
                listed=project_listing(item)
                if summaries:
                    listed['theme_analyses']=[{**{k:a[k] for k in ('id','name','theme','saved_at','created_at') if k in a},'_summary':True} for a in listed.get('theme_analyses',[])]
                items.append(listed)
        except Exception as error:
            log_failure('research_listing_failed', error, file=path.name)
            continue
    return sorted(items, key=lambda item: item.get("last_opened_at", item.get("created_at", 0)), reverse=True)


@app.get('/api/library-bootstrap')
def library_bootstrap():
    projects = list_projects()
    return {'projects': projects, 'research': research_project_list(projects, True), 'status': status()}


@app.get('/api/library-bootstrap-guest')
def guest_library_bootstrap():
    return {'projects': list_projects(), 'research': [], 'status': status()}


@app.get('/api/research-projects/{project_id}/theme-analysis-records/{record_index}')
def theme_analysis_record(project_id: str, record_index: int):
    from review_storage import project_listing
    p=research_project_path(project_id)
    if not p.exists():raise HTTPException(404,'研究项目不存在')
    records=read_json_document(p).get('theme_analyses',[])
    if record_index<0 or record_index>=len(records):raise HTTPException(404,'分析记录不存在')
    return project_listing({'theme_analyses':[records[record_index]]})['theme_analyses'][0]

@app.post("/api/research-projects/{project_id}/opened")
@locked_document(lambda values: research_project_path(values['project_id']))
def mark_research_project_opened(project_id: str):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    item = read_json_document(path)
    item["last_opened_at"] = time.time()
    atomic_write_json(path, item)
    return {"id": project_id}


class DisplayNameRequest(BaseModel):
    name: str


def display_name(value: str) -> str:
    name = value.strip()
    if not name or len(name) > 160 or any(ord(char) < 32 for char in name):
        raise HTTPException(400, "名称不能为空，且不能超过160字或包含换行")
    return name


def refresh_material_names(value, project_id: str, name: str) -> None:
    """Update display references only; never touch prose, IDs or stored source files."""
    if isinstance(value, list):
        for item in value:
            refresh_material_names(item, project_id, name)
    elif isinstance(value, dict):
        if value.get("project_id") == project_id or value.get("workspace_project_id") == project_id:
            for field in ("name", "material_name"):
                if field in value:
                    value[field] = name
        for child in value.values():
            if isinstance(child, (list, dict)):
                refresh_material_names(child, project_id, name)


@app.put("/api/projects/{project_id}/name")
def rename_interview(project_id: str, body: DisplayNameRequest):
    name = display_name(body.name)
    with document_transaction(metadata_path(project_id)):
        meta = read_metadata(project_id)
        meta["name"] = name
        write_metadata(project_id, meta)
    for path in RESEARCH_PROJECTS_DIR.glob("*.json"):
        with document_transaction(path):
            data = read_json_document(path)
            before = json.dumps(data, ensure_ascii=False)
            refresh_material_names(data, project_id, name)
            if json.dumps(data, ensure_ascii=False) != before:
                atomic_write_json(path, data)
    list_projects()
    return {"id": project_id, "name": read_metadata(project_id)["name"]}


@app.put("/api/research-projects/{project_id}/name")
@locked_document(lambda values: research_project_path(values['project_id']))
def rename_research_project(project_id: str, body: DisplayNameRequest):
    name = display_name(body.name)
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    data = read_json_document(path)
    data["name"] = name
    data["updated_at"] = time.time()
    atomic_write_json(path, data)
    return {"id": project_id, "name": name}


@app.put("/api/research-projects/{project_id}/uploaded/{material_index}/name")
def rename_uploaded_interview(project_id: str, material_index: int, body: DisplayNameRequest):
    name = display_name(body.name)
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    with document_transaction(path):
        data = read_json_document(path)
        uploads = data.get("uploaded_transcripts", [])
        if not 0 <= material_index < len(uploads):
            raise HTTPException(404, "访谈稿不存在")
        material = uploads[material_index]
        linked = material.get("workspace_project_id")
        if not (linked and metadata_path(linked).exists()):
            material["name"] = name
            data["updated_at"] = time.time()
            atomic_write_json(path, data)
            linked = None
    if linked:
        return rename_interview(linked, body)
    list_projects()
    refreshed = read_json_document(path)
    return {"name": refreshed["uploaded_transcripts"][material_index]["name"]}


@app.delete("/api/research-projects/{project_id}")
@locked_document(lambda values: research_project_path(values['project_id']))
def delete_research_project(project_id: str):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    archive = APP_DIR / "deleted_research_projects" / f"{project_id}-{uuid.uuid4().hex[:8]}"
    archive.mkdir(parents=True)
    shutil.move(str(path), str(archive / "project.json"))
    files_dir = (RESEARCH_FILES_DIR / project_id).resolve()
    if files_dir.parent == RESEARCH_FILES_DIR.resolve() and files_dir.exists():
        shutil.move(str(files_dir), str(archive / "files"))
    return {"archived_to": str(archive)}


@app.delete("/api/research-projects/{project_id}/materials/{material_type}/{material_key}")
@locked_document(lambda values: research_project_path(values['project_id']))
def remove_research_material(project_id: str, material_type: str, material_key: str):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    item = read_json_document(path)
    if material_type == "workspace":
        ids = item.get("interview_ids", [])
        if material_key not in ids:
            raise HTTPException(404, "访谈稿不在该项目中")
        item["interview_ids"] = [value for value in ids if value != material_key]
        item.get("material_types", {}).pop(material_key, None)
    elif material_type == "uploaded":
        try:
            index = int(material_key)
        except ValueError as exc:
            raise HTTPException(400, "访谈稿编号无效") from exc
        uploaded = item.get("uploaded_transcripts", [])
        if index < 0 or index >= len(uploaded):
            raise HTTPException(404, "访谈稿不在该项目中")
        material = uploaded[index]
        source_root = (RESEARCH_FILES_DIR / project_id).resolve()
        source = (source_root / str(material.get("file", ""))).resolve()
        if source.parent != source_root:
            raise HTTPException(400, "访谈稿文件路径无效")
        if source.exists():
            archive = source_root / "deleted_materials"
            archive.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(archive / f"{uuid.uuid4().hex[:8]}-{source.name}"))
        uploaded.pop(index)
    else:
        raise HTTPException(400, "资料类型无效")
    item["updated_at"] = time.time()
    atomic_write_json(path, item)
    return {"removed": True}


@app.post("/api/research-projects")
def create_research_project(
    name: str = Form(""),
    interview_ids: str = Form("[]"),
    transcripts: list[UploadFile] = File(default=[]),
):
    name = name.strip()
    if not name:
        raise HTTPException(400, "请填写项目名称")
    try:
        selected_ids = json.loads(interview_ids)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "访谈稿选择无效") from exc
    if not isinstance(selected_ids, list):
        raise HTTPException(400, "访谈稿选择无效")
    available = {item.get("id"): item for item in list_projects()}
    selected_ids = list(dict.fromkeys(str(item) for item in selected_ids))
    invalid = [item for item in selected_ids if item not in available]
    if invalid:
        raise HTTPException(400, "所选访谈稿不存在")
    project_id = safe_id(name) + "-" + uuid.uuid4().hex[:6]
    uploaded = save_research_uploads(project_id, transcripts)
    now = time.time()
    item = {
        "id": project_id,
        "name": name,
        "interview_ids": selected_ids,
        "material_types": {interview_id: "interview" for interview_id in selected_ids},
        "uploaded_transcripts": uploaded,
        "created_at": now,
        "updated_at": now,
    }
    RESEARCH_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(research_project_path(project_id), item)
    return item


def save_research_uploads(project_id: str, transcripts: list[UploadFile]) -> list[dict]:
    uploaded = []
    files_dir = RESEARCH_FILES_DIR / project_id
    for upload in transcripts:
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in {".txt", ".docx"}:
            raise HTTPException(400, "电脑访谈稿仅支持 TXT 或 DOCX")
        text = read_uploaded_transcript(upload)
        if not text:
            raise HTTPException(400, f"{upload.filename} 没有可读取的文字")
        files_dir.mkdir(parents=True, exist_ok=True)
        base = safe_id(Path(upload.filename).stem)
        target = files_dir / f"{base}-{uuid.uuid4().hex[:6]}.txt"
        atomic_write_text(target, text, encoding="utf-8-sig")
        uploaded.append({"name": upload.filename, "file": target.name, "material_type": "interview"})
    return uploaded


@app.post("/api/research-projects/{project_id}/materials")
@locked_document(lambda values: research_project_path(values['project_id']))
def add_research_materials(
    project_id: str,
    interview_ids: str = Form("[]"),
    transcripts: list[UploadFile] = File(default=[]),
):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    try:
        selected_ids = json.loads(interview_ids)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "访谈稿选择无效") from exc
    if not isinstance(selected_ids, list):
        raise HTTPException(400, "访谈稿选择无效")
    # No display-name migration while holding a project transaction.
    available = {item.get("id") for item in list_project_metadata()}
    selected_ids = list(dict.fromkeys(str(item) for item in selected_ids))
    if any(item not in available for item in selected_ids):
        raise HTTPException(400, "所选访谈稿不存在")
    item = read_json_document(path)
    item["interview_ids"] = list(dict.fromkeys(item.get("interview_ids", []) + selected_ids))
    material_types = item.setdefault("material_types", {})
    for interview_id in selected_ids:
        material_types[interview_id] = "interview"
    item["uploaded_transcripts"] = item.get("uploaded_transcripts", []) + save_research_uploads(project_id, transcripts)
    item["updated_at"] = time.time()
    atomic_write_json(path, item)
    return item


@app.post("/api/research-projects/{project_id}/uploaded/{material_index}/prepare")
@locked_document(lambda values: research_project_path(values['project_id']))
def prepare_uploaded_research_material(project_id: str, material_index: int):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    item = read_json_document(path)
    uploaded = item.get("uploaded_transcripts", [])
    if material_index < 0 or material_index >= len(uploaded):
        raise HTTPException(404, "访谈稿不存在")
    material = uploaded[material_index]
    existing_id = material.get("workspace_project_id")
    if existing_id and metadata_path(existing_id).exists():
        return {"project_id": existing_id}
    source = (RESEARCH_FILES_DIR / project_id / str(material.get("file", ""))).resolve()
    source_root = (RESEARCH_FILES_DIR / project_id).resolve()
    if source.parent != source_root or not source.exists():
        raise HTTPException(404, "访谈稿文件不存在")
    display_name = Path(str(material.get("name", source.stem))).stem
    workspace_id = safe_id(display_name) + "-" + uuid.uuid4().hex[:6]
    directory = project_dir(workspace_id)
    directory.mkdir(parents=True)
    shutil.copyfile(source, directory / "导入访谈稿.txt")
    now = time.time()
    write_metadata(workspace_id, {
        "id": workspace_id,
        "name": display_name,
        "audio_name": material.get("name", source.name),
        "source_type": "transcript",
        "status": "completed",
        "message": "访谈稿已导入",
        "created_at": now,
        "edited_at": now,
    })
    material["workspace_project_id"] = workspace_id
    item["updated_at"] = now
    atomic_write_json(path, item)
    return {"project_id": workspace_id}


@app.post("/api/projects")
def create_project(name: str = Form(""), audio: UploadFile = File(...)):
    global active_project
    suffix = Path(audio.filename or "").suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(400, "不支持这种音频格式")
    with active_lock:
        if active_project:
            raise HTTPException(409, "已有录音正在转录，请等待完成")
        project_id = safe_id(name or Path(audio.filename).stem) + "-" + uuid.uuid4().hex[:6]
        active_project = project_id
    directory = project_dir(project_id)
    directory.mkdir(parents=True)
    audio_path = directory / ("原始录音" + suffix)
    try:
        with audio_path.open("wb") as target:
            shutil.copyfileobj(audio.file, target)
    except Exception:
        with active_lock:
            active_project = None
        raise
    meta = {
        "id": project_id,
        "name": name.strip() or Path(audio.filename).stem,
        "audio_name": audio.filename,
        "created_at": time.time(),
        "status": "queued",
        "message": "等待开始转录",
    }
    write_metadata(project_id, meta)
    threading.Thread(target=run_transcription, args=(project_id, audio_path), daemon=True).start()
    return meta




@app.post("/api/demo-samples")
@locked_document(lambda values: APP_DIR / '.demo-samples.lock')
def load_demo_samples():
    """One-click loader for built-in concert interview sample with pre-verified memo & open coding."""
    import hashlib
    existing = list_projects()
    for item in existing:
        if item.get("is_demo_sample") or "林沐" in item.get("name", ""):
            return {"loaded": False, "project": item, "message": "示例访谈已在资料库中"}

    sample_file = CODE_DIR / "examples" / "concert" / "展示材料-林沐.txt"
    if sample_file.exists():
        text = sample_file.read_text(encoding="utf-8-sig").strip()
    else:
        text = (
            "跨城看演唱会：我们到底在为什么买单？\nL01｜林沐访谈\n"
            "【虚构访谈｜仅用于产品功能演示，不是真实研究材料】\n"
            "访谈员：先从那次去南京说起吧。你记得是什么时候决定要去的吗？\n"
            "受访者：五月中旬看的，决定其实更早，大概三月底吧。沈知遥发巡演城市的时候，我第一眼先看有没有上海。没有，离我最近就是南京。我当时把截图发给室友，说“又得跨城了”。其实也没说一定去，先放那儿了。\n"
            "访谈员：下午是怎么过的？\n"
            "受访者：酒店放完东西我去了一个旧书店，原本是刷帖子看到有人推荐。里面有一只很胖的猫，店员说别摸它肚子。我买了一张明信片，也没写寄给谁。然后坐在门口喝冰咖啡。那个时候我突然觉得很安静，没有人催我去哪儿，也没有要和别人协调。可我又有点不适应，隔十分钟就拿手机看看朋友有没有回消息。"
        )

    now_ts = time.time()
    project_id = "demo-linmu-" + uuid.uuid4().hex[:6]
    directory = project_dir(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write_text(directory / "导入访谈稿.txt", text, encoding="utf-8-sig")
    meta = {
        "id": project_id,
        "name": "【示例演示】林沐 · 跨城看演唱会",
        "audio_name": "展示材料-林沐.txt",
        "source_type": "transcript",
        "is_demo_sample": True,
        "created_at": now_ts,
        "last_opened_at": now_ts,
        "status": "completed",
        "message": "示例访谈已载入，可直接体验校订、纪要与编码审核",
    }
    write_metadata(project_id, meta)

    # Pre-populate familiarity memo with accurate character offsets
    memo_quotes = [
        (1, "其实也没说一定去，先放那儿了。"),
        (2, "我本来觉得两个人去，酒店不贵，夜里走回来也有人说话，好像比较合理。"),
        (3, "那个时候我突然觉得很安静，没有人催我去哪儿，也没有要和别人协调。可我又有点不适应，隔十分钟就拿手机看看朋友有没有回消息。"),
        (4, "这首歌我听了好多年，现场那一下好像把过去和现在连上了。"),
    ]
    evidence_list = []
    for num, q in memo_quotes:
        idx = text.find(q)
        if idx >= 0:
            evidence_list.append({"number": num, "quote": q, "start": idx, "end": idx + len(q)})

    analysis_payload = {
        "metadata": {
            "participant_id": "L01（林沐）",
            "participant_role": "23岁 · 高校硕士研究生",
            "region": "上海 → 南京",
            "institution": "虚构演示样本",
            "interview_date": "2026-05",
        },
        "sources": [],
        "codes": [],
        "excerpts": [],
        "ai_suggestions": [],
        "familiarity_memo": {
            "participant_identity": "林沐（23岁，上海某高校硕士研究生）",
            "interview_date": "2026年5月（虚构演示）",
            "interview_topic": "跨城独自观看演唱会的消费决策、独处体验与情感价值重估",
            "summary": "受访者林沐最初因跨城成本与学业压力对南京演唱会犹豫搁置，在朋友邀约推动下决定购票；朋友抢票失败后转为独自出行。整个旅程呈现出“微观安全与预算弹性调整”“独处自由与社交缺失不适并存”以及“由青春私密记忆触发的体验价值重估”三重特征。",
            "evidence": evidence_list,
            "viewpoints": [
                {
                    "title": "从犹豫搁置到同伴触发的购票决策",
                    "summary": "跨城成本与学业焦虑使受访者起初将计划搁置，朋友结伴分摊住宿与夜间安全感成为促成行动的关键。",
                    "evidence": [1, 2],
                    "points": [
                        {"text": "巡演无上海站，加上研一学业与实习氛围带来的烦躁感，最初选择暂缓决定。", "evidence": [1]},
                        {"text": "朋友提议同行使住宿分摊与夜间返程陪伴具有合理性，降低了决策门槛。", "evidence": [2]},
                    ],
                },
                {
                    "title": "独自跨城出行中的自由感与连接渴望并存",
                    "summary": "被动转为独行后，受访者既享受无需迁就他人的节奏，又频繁通过查看手机寻求即时社交反馈。",
                    "evidence": [3],
                    "points": [
                        {"text": "在南京旧书店喝咖啡时体会到无人催促与无需协调的松弛感，但仍每隔十分钟查看朋友消息。", "evidence": [3]},
                    ],
                },
                {
                    "title": "跨时间私密记忆连接带来的票价价值重估",
                    "summary": "演唱会的核心价值并非短视频式的整齐狂欢，而是老歌触发高三记忆时跨越时间的自我连接。",
                    "evidence": [4],
                    "points": [
                        {"text": "听见高中常听曲目的改编前奏时唤醒高三晚自习记忆，使门票脱离单纯时长计价而获得情感溢价。", "evidence": [4]},
                    ],
                },
            ],
        },
        "updated_at": now_ts,
    }
    atomic_write_json(analysis_path(project_id), analysis_payload)

    # Pre-populate open coding suggestions for manual-coding.json and research project coding.json
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    raw_codes = [
        (
            "跨城决策的犹豫与搁置",
            "指受访者在面对异地观演的时间、金钱成本及学业压力时，虽有情感向往但暂缓作出购票决定的状态。",
            "受访者提到既要考虑开销和课程作业，又觉得周末该做“更正经的事”，因此先放着没定。",
            ["其实也没说一定去，先放那儿了。", "我那时候也有点烦躁，就会想，你是不是应该把周末用在更正经的事上。"],
        ),
        (
            "同伴邀约作为行动触发器",
            "指朋友的主动约伴通过分摊住宿成本与提供夜间同行安全感，打破原有的犹豫状态并促成购票行动。",
            "受访者明确表示朋友提议同行后，算了预算觉得两人分摊酒店和夜里结伴走回来更合理。",
            ["我本来觉得两个人去，酒店不贵，夜里走回来也有人说话，好像比较合理。"],
        ),
        (
            "抢票时的焦虑与冲动消费",
            "指在票务稀缺与网络卡顿的高压情境下，为避免错失机会而跳过协商直接完成支付的紧迫决策行为。",
            "在图书馆楼梯间刷出余票时怕犹豫就没了直接付款，事后才发现朋友没抢到。",
            ["页面转了好久，先显示没票，刷新一下又跳出一张六百八的。我怕再犹豫就没了，直接付款。"],
        ),
        (
            "独自出行的微观安全担忧",
            "指并非担忧目的地的宏观治安，而是对散场交通、手机没电、独自点餐及现场落单感等具体生活细节的不安。",
            "受访者具体列举了手机没电、一人点菜吃不完以及怕在现场看到别人结伴觉得自己傻等细节顾虑。",
            ["也不是觉得南京危险，就是怕一些小事没人商量。比如演唱会散场那么多人，手机万一没电怎么办"],
        ),
        (
            "预算弹性调整：以舒适换成本",
            "指在独自出行的情境下，主动放宽原定住宿预算上限，以换取近地铁交通便利与住宿安全感的补偿策略。",
            "酒店预算从250元以内提高到近300元，认为既已出行，安全和睡眠不能太将就。",
            ["酒店后来订到快三百了，因为我不想住得离地铁太远。那时候我又觉得，既然都去了，安全和睡觉总不能太将就。"],
        ),
        (
            "独处时的自由与不适并存",
            "指在独自活动期间，既享受无人协调的自主权，又因缺乏社交反馈而产生习惯性查看手机、寻求连接的矛盾心理。",
            "受访者在书店感到安静、没人催，但同时又不适应，频繁看手机等待回复。",
            [
                "那个时候我突然觉得很安静，没有人催我去哪儿，也没有要和别人协调。",
                "可我又有点不适应，隔十分钟就拿手机看看朋友有没有回消息。",
            ],
        ),
        (
            "拒绝陌生社交的边界维护",
            "指虽加入同场互助群获取交通信息，但抗拒为了临时结伴而向陌生人从头交代个人喜好背景的社交负担。",
            "面对同场网友约饭私信，受访者因不想从头认识陌生人、解释怎么喜欢上歌手而婉拒。",
            ["不是她有什么问题，就是我突然不想从头认识一个人，还要解释自己怎么喜欢上这个歌手。"],
        ),
        (
            "私密记忆引发的价值重估",
            "指演出中的特定曲目唤醒个人成长阶段的私密记忆，使观演体验超越即时视听娱乐并获得情感合理化。",
            "老歌编曲唤起高三晚自习回宿舍的记忆，把过去和现在连上，从而感到票价值得。",
            ["唱到第二段，我忽然想到高三晚自习回宿舍那条路。那种感觉不是“终于见到偶像”那么简单，就是你以为早忘了的东西突然都回来了。"],
        ),
    ]

    built_codes = []
    for name, definition, reason, quotes in raw_codes:
        refs = []
        for q in quotes:
            idx = text.find(q)
            if idx >= 0:
                refs.append({
                    "id": uuid.uuid4().hex,
                    "quote": q,
                    "start": idx,
                    "end": idx + len(q),
                    "validation": "valid",
                })
        if refs:
            built_codes.append({
                "id": uuid.uuid4().hex,
                "name": name,
                "definition": definition,
                "reason": reason,
                "origin": "ai",
                "status": "pending",
                "source_hash": h,
                "source_id": project_id,
                "revision": 1,
                "created_at": now_ts,
                "updated_at": now_ts,
                "references": refs,
            })

    coding_payload = {
        "project_id": None,
        "source_id": project_id,
        "revision": 1,
        "current_hash": h,
        "sources": {h: {"text": text, "captured_at": now_ts}},
        "runs": [{
            "id": uuid.uuid4().hex,
            "status": "completed",
            "source_hash": h,
            "started_at": now_ts,
            "completed_at": now_ts,
            "batches": [{"batch_index": 0, "status": "completed", "attempts": []}],
        }],
        "deleted_codes": [],
        "codes": built_codes,
        "updated_at": now_ts,
    }
    atomic_write_json(directory / "manual-coding.json", coding_payload)

    # Also create or attach to a demo research project so logged-in users see it in Research Projects & AI Coding
    try:
        with document_transaction(research_project_path('demo-concert-research')):
            demo_rp_id = "demo-concert-research"
            rp_path = research_project_path(demo_rp_id)
            if rp_path.exists():
                rp_data = read_json_document(rp_path)
                if project_id not in rp_data.get("interview_ids", []):
                    rp_data.setdefault("interview_ids", []).insert(0, project_id)
                rp_data["last_opened_at"] = now_ts
            else:
                rp_data = {
                    "id": demo_rp_id,
                    "name": "【示例项目】跨城看演唱会消费体验研究",
                    "created_at": now_ts,
                    "last_opened_at": now_ts,
                    "interview_ids": [project_id],
                    "uploaded_transcripts": [],
                    "material_comparisons": [],
                    "theme_analyses": [],
                }
            atomic_write_json(rp_path, rp_data)
            ai_coding_dir = (
                RESEARCH_FILES_DIR
                / "_ai_coding_demo"
                / hashlib.sha256(demo_rp_id.encode("utf-8")).hexdigest()
                / hashlib.sha256(project_id.encode("utf-8")).hexdigest()
            )
            ai_coding_dir.mkdir(parents=True, exist_ok=True)
            rp_coding_payload = {**coding_payload, "project_id": demo_rp_id}
            atomic_write_json(ai_coding_dir / "coding.json", rp_coding_payload)
    except (SiteError, HTTPException):
        raise
    except Exception as error:
        log_failure('demo_research_link_failed', error)

    return {"loaded": True, "project": meta, "message": "已载入示例访谈（含预置纪要与编码建议）"}


@app.post("/api/transcript-projects")
def create_transcript_project(name: str = Form(""), transcript: UploadFile = File(...)):
    text = read_uploaded_transcript(transcript)
    if not text:
        raise HTTPException(400, "访谈稿内容为空")
    project_id = safe_id(name or Path(transcript.filename or "访谈稿").stem) + "-" + uuid.uuid4().hex[:6]
    directory = project_dir(project_id); directory.mkdir(parents=True)
    atomic_write_text(directory / "导入访谈稿.txt", text, encoding="utf-8-sig")
    meta = {
        "id": project_id, "name": name.strip() or Path(transcript.filename or "访谈稿").stem,
        "audio_name": transcript.filename, "source_type": "transcript", "created_at": time.time(),
        "status": "completed", "message": "访谈稿已导入，可以AI校订或直接分析",
    }
    write_metadata(project_id, meta)
    return meta


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    meta = read_metadata(project_id)
    from transcription_recovery import presentation
    meta=presentation(meta,project_dir(project_id),active_project)
    path = transcript_path(project_id)
    meta["has_transcript"] = bool(path)
    return meta


@app.post('/api/projects/{project_id}/resume-transcription')
def resume_transcription(project_id: str):
    global active_project
    from transcription_recovery import preflight,presentation,ensure_worker_stopped
    with active_lock:
        if active_project:
            raise HTTPException(409,'已有录音正在转录，请勿重复启动')
        original=read_metadata(project_id);directory=project_dir(project_id)
        state=presentation(original,directory,active_project)
        if state.get('status') not in {'interrupted','failed'}:
            raise HTTPException(409,'该访谈不处于可继续的中断状态')
        try:
            ensure_worker_stopped()
            audio,completed,total=preflight(APP_DIR,directory)
        except (ValueError,OSError) as exc:
            raise HTTPException(409,str(exc)) from exc
        except (KeyError,TypeError,AttributeError) as exc:
            raise HTTPException(409,'检查点结构不完整或已损坏，不能继续；已有结果未覆盖') from exc
        active_project=project_id
        meta=dict(original)
        meta.update(status='queued',message=f'校验通过，准备从第{completed+1}/{total}段继续' if completed<total else '校验通过，准备保存最终结果')
        meta['resume_requests']=[*meta.get('resume_requests',[]),{'requested_at':time.time(),'completed_chunks':completed,'total_chunks':total}]
        try:
            write_metadata(project_id,meta)
            threading.Thread(target=run_transcription,args=(project_id,audio,True),daemon=True).start()
        except Exception:
            active_project=None;write_metadata(project_id,original);raise
    return {'started':True,'completed_chunks':completed,'total_chunks':total,'next_chunk':completed+1 if completed<total else None}


@app.get("/api/projects/{project_id}/transcription-progress")
def get_transcription_progress(project_id: str):
    meta = read_metadata(project_id)
    directory = project_dir(project_id)
    progress_path = directory / "转录进度.json"
    checkpoint_path = directory / "转录检查点.json"
    progress = read_json_document(progress_path) if progress_path.exists() else {}
    checkpoint = read_json_document(checkpoint_path) if checkpoint_path.exists() else {}
    from transcription_recovery import presentation
    state=presentation({**meta,'id':project_id},directory,active_project)
    return {**progress, 'status':state['status'], "task_status": state['status'], 'resume_available':state['resume_available'],
            "checkpoint_available": bool(checkpoint),
            "completed_chunks": checkpoint.get("completed_chunks", 0),
            "total_chunks": checkpoint.get("total_chunks", 0),
            "partial_available": (directory / "转录部分结果.txt").exists(),
            "partial_is_final": False}


@app.get("/api/projects/{project_id}/transcript")
@locked_document(lambda values: project_dir(values['project_id']) / 'DeepSeek修改记录.json')
def get_transcript(project_id: str):
    path = transcript_path(project_id)
    if not path:
        raise HTTPException(404, "转录稿尚未生成")
    text = path.read_text(encoding="utf-8-sig")
    annotations = []
    record_path = project_dir(project_id) / "DeepSeek修改记录.json"
    if path.name in {"DeepSeek自动校订稿.txt", "校订稿.txt"} and record_path.exists():
        try:
            record = read_json_document(record_path)
            annotations = record.get("annotations") if "annotations" in record else build_review_annotations(text, record.get("changes", []))
            if "annotations" not in record:
                record["annotations"] = annotations
                atomic_write_json(record_path, record)
        except (OSError, ValueError, TypeError):
            annotations = []
    return {"text": text, "edited": path.name in {"校订稿.txt", "DeepSeek自动校订稿.txt"}, "annotations": annotations}


@app.get("/api/projects/{project_id}/open-transcript")
def open_transcript(project_id: str):
    meta = get_project(project_id)
    return {"project": meta, "transcript": get_transcript(project_id) if meta["status"] == "completed" else None}

from audio_pairing import install as install_audio_pairing
install_audio_pairing(app, APP_DIR, project_dir)
from interview_trash_api import install as install_interview_trash
install_interview_trash(app, APP_DIR, PROJECTS_DIR, RESEARCH_PROJECTS_DIR, RESEARCH_FILES_DIR)

@app.post('/api/projects/{project_id}/audio-alignment')
def get_audio_alignment(project_id: str, body: dict):
    from audio_follow import alignment
    return alignment(project_dir(project_id),str(body.get('text','')))

@app.get('/api/projects/{project_id}/source-audio')
def get_source_audio(project_id: str):
    from audio_follow import audio_file
    audio=audio_file(project_dir(project_id))
    if not audio:raise HTTPException(404,'没有关联的原始录音')
    return FileResponse(audio)


@app.post("/api/projects/{project_id}/changes/accept")
@locked_document(lambda values: project_dir(values['project_id']) / 'DeepSeek修改记录.json')
def accept_transcript_change(project_id: str, body: ChangeDecision):
    record_path = project_dir(project_id) / "DeepSeek修改记录.json"
    if not record_path.exists():
        raise HTTPException(404, "修改记录不存在")
    record = read_json_document(record_path)
    found = False
    for item in record.get("annotations", []):
        if item.get("change_id") == body.change_id:
            if item.get('rejected'):
                raise HTTPException(409, '这条建议已拒绝，不能批量重新接受')
            item["accepted"] = True; found = True
    for item in record.get("changes", []):
        if item.get("change_id") == body.change_id:
            item["accepted"] = True
    if not found:
        raise HTTPException(404, "没有找到这条修改")
    atomic_write_json(record_path, record)
    return {"accepted": True}


@app.put("/api/projects/{project_id}/transcript")
@locked_document(lambda values: project_dir(values['project_id']) / 'DeepSeek修改记录.json')
def save_transcript(project_id: str, body: TranscriptUpdate):
    directory = project_dir(project_id)
    if not directory.exists():
        raise HTTPException(404, "项目不存在")
    target = directory / "校订稿.txt"
    record_path = directory / "DeepSeek修改记录.json"
    if record_path.exists():
        from transcript_review import save_decisions
        from theme_file_io import write_json
        record = read_json_document(record_path)
        previous = transcript_path(project_id)
        old_text = previous.read_text(encoding='utf-8-sig') if previous else ''
        try:
            record = save_decisions(record, old_text, body.text,
                                    body.accepted_change_ids, body.rejected_change_ids, time.time())
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        write_json(record_path, record)
    atomic_write_text(target, body.text, encoding="utf-8-sig")
    patch_metadata(project_id, edited_at=time.time())
    return {"saved": True}


@app.post("/api/projects/{project_id}/optimize-transcript")
def optimize_transcript(project_id: str, punctuation_mode: str = "filtered"):
    if punctuation_mode not in {"filtered", "full"}:
        raise HTTPException(400, "标点检查模式无效")
    path = transcript_path(project_id)
    if not path:
        raise HTTPException(404, "没有找到可校订的访谈稿")
    key = read_deepseek_key()
    if not key:
        raise HTTPException(400, "未检测到 DeepSeek API Key")
    directory = project_dir(project_id)
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    raw_dir = directory / "DeepSeek原始返回" / run_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_path = directory / "DeepSeek调用日志.jsonl"
    key_fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12].upper()
    result_lock = threading.RLock()
    input_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    manual_path = directory / "校订稿.txt"
    manual_hash = hashlib.sha256(manual_path.read_bytes()).hexdigest() if manual_path.exists() else None

    def write_call_log(data: dict) -> None:
        entry = {"run_id": run_id, "logged_at": time.time(), **data, "request_id": request_id.get()}
        with result_lock, log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    text = path.read_text(encoding="utf-8-sig")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    units = []
    for index, block in enumerate(blocks, 1):
        match = re.match(r"^\s*(说话人\d+|访谈者|受访者)\s*[：:]\s*(.*)$", block, re.S)
        units.append({"unit_id": index, "speaker": match.group(1) if match else "", "text": match.group(2).strip() if match else block})

    local_records, local_counts = [], {"total": 0, "repetitions": 0, "modal_commas": 0, "punctuation": 0}
    for unit in units:
        original = unit["text"]
        revised_text, changes, counts = apply_local_preprocessing(original)
        unit["text"] = split_long_paragraphs(revised_text)
        local_records.append({"unit_id": unit["unit_id"], "speaker": unit["speaker"], "original": original, "revised": unit["text"], "changes": changes})
        for key_name in local_counts:
            local_counts[key_name] += counts[key_name]
    merged_units = []
    for unit in units:
        if unit["speaker"] and merged_units and merged_units[-1]["speaker"] == unit["speaker"]:
            merged_units[-1]["text"] += "\n\n" + unit["text"]
        else:
            merged_units.append({"speaker": unit["speaker"], "text": unit["text"]})
    units = [{"unit_id": index, **unit} for index, unit in enumerate(merged_units, 1)]
    local_output = "\n\n".join((f"{item['speaker']}：" if item["speaker"] else "") + item["text"] for item in units)
    local_target = directory / '本地自动整理稿.txt'
    if path.resolve() == local_target.resolve():
        local_target = raw_dir / '本地整理输入快照.txt'
    atomic_write_text(local_target, local_output, encoding="utf-8-sig")
    atomic_write_json(directory / "本地自动整理修改记录.json", {"created_at": time.time(), "counts": local_counts, "units": local_records})

    def make_chunks(source_units: list[dict], max_chars: int = 8500) -> list[list[dict]]:
        result, current, size = [], [], 0
        for unit in source_units:
            if current and size + len(unit["text"]) > max_chars:
                result.append(current); current = []; size = 0
            current.append(unit); size += len(unit["text"])
        if current:
            result.append(current)
        return result

    def visible_characters(value: str) -> str:
        return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", value))

    def apply_suggestions(source_text: str, suggestions: list, stage: str) -> tuple[str, list[dict]]:
        replacements, records = [], []
        for suggestion in suggestions if isinstance(suggestions, list) else []:
            if not isinstance(suggestion, dict):
                continue
            old = str(suggestion.get("from", ""))
            new = str(suggestion.get("to", ""))
            if not old or old == new:
                continue
            record = {**suggestion, "stage": stage, "applied": False}
            if len(old) > MAX_AI_SUGGESTION_CHARS or len(new) > MAX_AI_SUGGESTION_CHARS:
                record['skip_reason'] = '局部建议超过80字符'; records.append(record); continue
            if stage == "punctuation" and visible_characters(old) != visible_characters(new):
                record["skip_reason"] = "标点阶段改变了文字、字母或数字"; records.append(record); continue
            try:
                occurrence = max(1, int(suggestion.get("occurrence", 1)))
            except (TypeError, ValueError):
                occurrence = 1
            positions, start = [], 0
            while True:
                found = source_text.find(old, start)
                if found < 0:
                    break
                positions.append(found); start = found + max(1, len(old))
            if occurrence > len(positions):
                record["skip_reason"] = "原文中找不到指定位置"; records.append(record); continue
            begin = positions[occurrence - 1]
            end = begin + len(old)
            if any(not (end <= item[0] or begin >= item[1]) for item in replacements):
                record["skip_reason"] = "与另一条修改位置重叠"; records.append(record); continue
            replacements.append((begin, end, new))
            record.update({"applied": True, "start": begin, "end": end}); records.append(record)
        revised_text = source_text
        for begin, end, new in sorted(replacements, reverse=True):
            revised_text = revised_text[:begin] + new + revised_text[end:]
        return revised_text, records

    content_rules = (CODE_DIR / "AI文字校订规则.txt").read_text(encoding="utf-8-sig") if (CODE_DIR / "AI文字校订规则.txt").exists() else ""
    punctuation_rules = (CODE_DIR / "AI标点整理规则.txt").read_text(encoding="utf-8-sig") if (CODE_DIR / "AI标点整理规则.txt").exists() else ""
    suggestion_limit_rule = f"\n\n强制长度限制：每条建议的from和to分别不得超过{MAX_AI_SUGGESTION_CHARS}个字符；一处建议只能包含一个局部修改；多处修改必须拆成多条建议。"
    no_op_rule = "\n仅返回会实际改变原文的建议。from与to必须不同；原文无需修改时suggestions必须为空数组；禁止解释为什么不修改。"
    content_rules += suggestion_limit_rule + no_op_rule
    punctuation_rules += suggestion_limit_rule + no_op_rule + (
        "\n标点阶段只返回最小JSON，不得返回source_excerpt、type、reason、confidence或uncertain。"
        "格式必须是："
        '{"units":[{"unit_id":1,"suggestions":[{"from":"原文片段","to":"修改后片段","occurrence":1}]}]}。'
        "每个输入发言单元都必须在units中出现一次，没有修改时suggestions返回空数组。"
    )
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=240.0, max_retries=0)
        all_records = []
        failed_batches = []
        checkpoint_dir = directory / "DeepSeek校订检查点" / run_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_manifest = {
            "run_id": run_id, "created_at": time.time(),
            "completed_batches": [], "failed_batches": [],
        }

        def save_checkpoint(stage: str, label: str, status: str, source_chunk: list[dict], revised_chunk: list[dict] | None = None, records: list[dict] | None = None, error: str = "") -> None:
            safe_label = re.sub(r"[^0-9A-Za-z_-]+", "-", label)
            payload = {
                "run_id": run_id, "stage": stage, "batch": label, "status": status,
                "saved_at": time.time(), "source_units": source_chunk,
                "revised_units": revised_chunk or [], "records": records or [],
                "error": error[:1000],
            }
            with result_lock:
                save_checkpoint_locked(stage, safe_label, label, status, source_chunk, payload, error)

        def save_checkpoint_locked(stage, safe_label, label, status, source_chunk, payload, error):
            from theme_file_io import write_json
            # Serialize manifest read/modify/write across the two workers.
            write_json(checkpoint_dir / f"{stage}-{safe_label}.json",payload)
            summary = {"stage": stage, "batch": label, "unit_count": len(source_chunk), "saved_at": payload["saved_at"]}
            target = "completed_batches" if status == "completed" else "failed_batches"
            checkpoint_manifest[target] = [item for item in checkpoint_manifest[target] if not (item["stage"] == stage and item["batch"] == label)]
            checkpoint_manifest[target].append({**summary, **({"error": error[:500]} if error else {})})
            write_json(checkpoint_dir / "manifest.json",checkpoint_manifest)

        total_batches = len(make_chunks(units, 8500)) + len(make_chunks(units, 2500))
        write_call_log({"event": "run_started", "model": "deepseek-flash", "batch_count": total_batches, "unit_count": len(units), "key_fingerprint": key_fingerprint, "local_preprocessing": local_counts, "max_suggestion_chars": MAX_AI_SUGGESTION_CHARS, "max_concurrent_batches":2, "punctuation_mode":punctuation_mode})

        def run_stage(source_units: list[dict], stage: str, rules: str) -> list[dict]:
            # DeepSeek's structured-response mode requires an explicit JSON instruction.
            rules += '\n请按以上字段和规则，仅返回一个有效的 JSON 对象。'
            max_chars = 2500 if stage == "punctuation" else 8500
            max_split_depth = 1

            def split_chunk(chunk: list[dict]) -> tuple[list[dict], list[dict]] | None:
                if len(chunk) > 1:
                    target = sum(len(item["text"]) for item in chunk) / 2
                    size, split_at = 0, 1
                    for index, item in enumerate(chunk[:-1], 1):
                        size += len(item["text"])
                        split_at = index
                        if size >= target:
                            break
                    return chunk[:split_at], chunk[split_at:]
                if not chunk or len(chunk[0]["text"]) < 400:
                    return None
                source = chunk[0]
                text_value = source["text"]
                midpoint = len(text_value) // 2
                candidates = [text_value.rfind(mark, max(0, midpoint - 250), min(len(text_value), midpoint + 250)) for mark in "。！？；，"]
                cut = max(candidates)
                if cut < 1:
                    cut = midpoint
                left = {**source, "text": text_value[:cut + 1]}
                right = {**source, "text": text_value[cut + 1:]}
                return [left], [right]

            def process_chunk(chunk: list[dict], label: str, depth: int = 0, retry: int = 0) -> list[dict]:
                started_at = time.time()
                try:
                    response = client.chat.completions.create(
                        model="deepseek-flash", temperature=0, max_tokens=12000,
                        response_format={"type": "json_object"}, extra_body={"thinking": {"type": "disabled"}},
                        messages=[{"role": "system", "content": rules}, {"role": "user", "content": json.dumps({"units": chunk}, ensure_ascii=False)}],
                    )
                    raw_content = response.choices[0].message.content or "{}"
                    raw_name = re.sub(r"[^0-9A-Za-z_-]+", "-", label)
                    atomic_write_text(raw_dir / f"{stage}-{raw_name}.json", raw_content, encoding="utf-8")
                    parsed = json.loads(raw_content)
                    if getattr(response.choices[0], 'finish_reason', None) == 'length':
                        raise RuntimeError('模型返回因长度限制截断')
                    returned = parsed.get("units", [])
                    if len(returned) != len(chunk):
                        raise RuntimeError(f"{stage}阶段返回的发言单元数量不一致")
                    if [r.get('unit_id') for r in returned] != [u['unit_id'] for u in chunk]:
                        raise RuntimeError(f'{stage}阶段发言单元编号或顺序不一致')
                    revised_chunk, batch_records, applied_count = [], [], 0
                    for source, result in zip(chunk, returned):
                        if 'speaker' in result and result['speaker'] != source['speaker']:
                            raise RuntimeError('模型改变了说话人标签')
                        allowed = {'from','to','occurrence','source_excerpt','type'} if stage=='word' else {'from','to','occurrence'}
                        suggestions=[{k:v for k,v in s.items() if k in allowed} for s in result.get('suggestions',[]) if isinstance(s,dict)]
                        revised_text, records = apply_suggestions(source["text"], suggestions, stage)
                        enriched = [{"unit_id": source["unit_id"], "speaker": source["speaker"], **item} for item in records]
                        applied_count += sum(bool(item.get("applied")) for item in records)
                        batch_records.extend(enriched)
                        revised_chunk.append({"unit_id": source["unit_id"], "speaker": source["speaker"], "text": revised_text})
                    with result_lock:
                        all_records.extend(batch_records)
                    save_checkpoint(stage, label, "completed", chunk, revised_chunk, batch_records)
                    usage = response.usage.model_dump() if getattr(response, "usage", None) else {}
                    finish_reason = getattr(response.choices[0], "finish_reason", None)
                    write_call_log({"event": "batch_completed", "stage": stage, "batch": label, "provider_request_id": getattr(response, "id", None), "model": getattr(response, "model", None), "finish_reason": finish_reason, "response_chars": len(raw_content), "elapsed_seconds": round(time.time() - started_at, 3), "unit_count": len(chunk), "applied_change_count": applied_count, "usage": usage})
                    return revised_chunk
                except (json.JSONDecodeError, RuntimeError) as batch_exc:
                    error_text = str(batch_exc).replace(key, "***")[:1000]
                    parts = split_chunk(chunk) if depth < max_split_depth and retry == 0 else None
                    write_call_log({"event": "batch_parse_failed", "stage": stage, "batch": label, "depth": depth, "elapsed_seconds": round(time.time() - started_at, 3), "error": error_text, "will_split": bool(parts)})
                    if parts:
                        left_result = process_chunk(parts[0], label + "A", depth + 1)
                        right_result = process_chunk(parts[1], label + "B", depth + 1)
                        if len(chunk) == 1 and len(left_result) == 1 and len(right_result) == 1:
                            source = chunk[0]
                            return [{"unit_id": source["unit_id"], "speaker": source["speaker"], "text": left_result[0]["text"] + right_result[0]["text"]}]
                        return left_result + right_result
                    save_checkpoint(stage, label, "failed", chunk, error=error_text)
                    failed_batches.append({"stage": stage, "batch": label, "unit_ids": [item["unit_id"] for item in chunk], "error": error_text})
                    return [dict(item) for item in chunk]
                except (SiteError, HTTPException):
                    raise
                except Exception as batch_exc:
                    error_text = str(batch_exc).replace(key, "***")[:1000]
                    write_call_log({"event": "batch_failed", "stage": stage, "batch": label, "elapsed_seconds": round(time.time() - started_at, 3), "error": error_text})
                    status = getattr(batch_exc, 'status_code', None)
                    retryable = status is None or status in {408, 409, 429} or status >= 500
                    if depth == 0 and retry < 2 and retryable:
                        time.sleep(min(2 ** retry, 4))
                        write_call_log({'event':'batch_retry','stage':stage,'batch':label,'attempt':retry+1})
                        return process_chunk(chunk,label,depth,retry+1)
                    save_checkpoint(stage, label, "failed", chunk, error=error_text)
                    failed_batches.append({"stage": stage, "batch": label, "unit_ids": [item["unit_id"] for item in chunk], "error": error_text})
                    return [dict(item) for item in chunk]

            batches = make_chunks(source_units,max_chars)
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(copy_context().run,process_chunk,chunk,f'第{i:03d}批') for i,chunk in enumerate(batches,1)]
                # Collect in original order, not completion order.
                revised_units=[unit for future in futures for unit in future.result()]
            return revised_units

        revised = run_stage(units, "word", content_rules)
        if punctuation_mode == 'filtered':
            candidates,mapping,skipped = select_paragraphs(revised)
            write_call_log({'event':'punctuation_selection','selected_paragraphs':len(candidates),
                            'skipped_paragraphs':skipped,'rules':PUNCTUATION_SCREEN_RULES})
            atomic_write_json(checkpoint_dir/'punctuation-selection.json', {'mapping':mapping,'skipped':skipped})
            checked = run_stage(candidates,'punctuation',punctuation_rules)
            revised = restore_paragraphs(revised,checked,mapping)
        else:
            revised = run_stage(revised, "punctuation", punctuation_rules)
        all_records.sort(key=lambda r:(0 if r['stage']=='word' else 1,r['unit_id'],r.get('start',0)))
        output = "\n\n".join((f"{item['speaker']}：" if item["speaker"] else "") + item["text"] for item in revised)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=input_hash or (hashlib.sha256(manual_path.read_bytes()).hexdigest() if manual_path.exists() else None)!=manual_hash:
            raise RuntimeError('运行期间原稿或人工校订稿已改变，结果仅保存在检查点，未覆盖当前稿件')
        atomic_write_text(project_dir(project_id) / "DeepSeek自动校订稿.txt", output, encoding="utf-8-sig")
        annotations = build_review_annotations(output, all_records)
        atomic_write_json(directory / "DeepSeek修改记录.json", {"run_id": run_id, "changes": all_records, "annotations": annotations, "failed_batches": failed_batches})
        applied_total = sum(bool(item.get("applied")) for item in all_records)
        skipped_total = len(all_records) - applied_total
        write_call_log({"event": "run_completed", "applied_change_count": applied_total, "skipped_change_count": skipped_total, "failed_batch_count": len(failed_batches), "failed_batches": failed_batches, "changed_unit_count": sum(item["text"] != source["text"] for item, source in zip(revised, units))})
        checkpoint_manifest["finished_at"] = time.time()
        checkpoint_manifest["failed_batches"] = failed_batches
        atomic_write_json(checkpoint_dir / "manifest.json", checkpoint_manifest)
        patch_metadata(project_id, ai_edited_at=time.time(), ai_run_id=run_id,
                       ai_key_fingerprint=key_fingerprint, ai_partial=bool(failed_batches))
        message = f"AI修订完成：应用 {applied_total} 处，跳过 {skipped_total} 处"
        if failed_batches:
            message += f"；{len(failed_batches)} 个子批次未完成，已保留其他批次结果"
        return {"text": output, "annotations": annotations, "failed_batches": failed_batches, "message": message}
    except (SiteError, HTTPException):
        raise
    except Exception as exc:
        write_call_log({"event": "run_failed", "error": str(exc).replace(key, "***")[:1000]})
        raise HTTPException(500, str(exc).replace(key, "***")[:500])


@app.get("/api/projects/{project_id}/analysis")
def analyze(project_id: str):
    path = transcript_path(project_id)
    if not path:
        raise HTTPException(404, "请先完成转录")
    text = path.read_text(encoding="utf-8-sig")
    turns = []
    speaker_chars: dict[str, int] = {}
    for block in re.split(r"\n\s*\n", text.strip()):
        match = re.match(r"(说话人\d+)：(.*)", block, re.S)
        if match:
            speaker, content = match.groups()
            speaker_chars[speaker] = speaker_chars.get(speaker, 0) + len(content)
            turns.append({"speaker": speaker, "text": content})
    words = []
    if HOTWORDS.exists():
        for line in HOTWORDS.read_text(encoding="utf-8-sig").splitlines():
            if not line.startswith("#"):
                words.extend(line.split())
    topics = []
    for word in dict.fromkeys(words):
        count = text.count(word)
        if count:
            evidence = next((t for t in turns if word in t["text"]), None)
            topics.append({"term": word, "count": count, "evidence": evidence})
    topics.sort(key=lambda item: item["count"], reverse=True)
    return {
        "turn_count": len(turns),
        "character_count": sum(speaker_chars.values()),
        "speaker_chars": speaker_chars,
        "topics": topics[:12],
        "note": "当前为本地基础分析；后续可接入结构化提取和主题编码模型。",
    }


@app.get("/api/projects/{project_id}/analysis-workspace")
def get_analysis_workspace(project_id: str):
    read_metadata(project_id)
    from analysis_contracts import source_hash
    source = transcript_path(project_id)
    return {**read_analysis(project_id), "_version": analysis_version(project_id),
            "_source_hash": source_hash(source.read_text(encoding='utf-8-sig')) if source else None}


def analysis_version(project_id):
    path = analysis_path(project_id)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "new"


@app.put("/api/projects/{project_id}/analysis-workspace")
@locked_document(lambda values: analysis_path(values['project_id']))
def save_analysis_workspace(project_id: str, body: AnalysisUpdate):
    read_metadata(project_id)
    # A valid client payload must not silently overwrite damaged stored results.
    read_analysis(project_id)
    expected = body.data.get("_version")
    actual = analysis_version(project_id)
    if expected != actual and not (actual == "new" and expected is None):
        raise HTTPException(409, "分析记录已被其他页面或任务更新，请重新打开访谈后再保存；当前内容未覆盖")
    from analysis_contracts import source_hash
    source = transcript_path(project_id)
    if body.data.get("_source_hash") and (not source or body.data["_source_hash"] != source_hash(source.read_text(encoding='utf-8-sig'))):
        raise HTTPException(409, "原文已变化，旧页面的分析不能覆盖，请重新打开访谈")
    data = {k: v for k, v in body.data.items() if k not in ("_version", "_source_hash")}
    for key, default in (("metadata", {}), ("sources", []), ("codes", []), ("excerpts", []), ("ai_suggestions", [])):
        data.setdefault(key, default)
    data["updated_at"] = time.time()
    atomic_write_json(analysis_path(project_id), data)
    return {"saved": True, "updated_at": data["updated_at"], "_version": analysis_version(project_id)}


@app.post("/api/projects/{project_id}/coding-suggestions")
def coding_suggestions(project_id: str, body: CodingRequest):
    path = transcript_path(project_id)
    if not path:
        raise HTTPException(404, "请先完成转录")
    key = read_deepseek_key()
    if not key:
        raise HTTPException(400, "未检测到 DeepSeek API Key")
    text = path.read_text(encoding="utf-8-sig")
    try:
        from openai import OpenAI
        from interview_coding import generate_initial_codes
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=180.0)
        def call(prompt, payload):
            response = limited_create(client,
                model="deepseek-flash", temperature=0, max_tokens=6000,
                response_format={"type": "json_object"}, extra_body={"thinking": {"type": "disabled"}},
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            )
            if response.choices[0].finish_reason != "stop":
                raise ValueError("编码回复未完整结束，本次未写入建议，请缩小编码范围后重试")
            return json.loads(response.choices[0].message.content or "{}")
        existing = read_analysis(project_id).get("codes", [])
        return generate_initial_codes(text, body.research_question, existing, project_id, call)
    except (SiteError, HTTPException):
        raise
    except Exception as exc:
        log_failure('backend_operation_failed', exc)
        raise HTTPException(500, str(exc).replace(key, "***")[:500])


@app.post("/api/projects/{project_id}/familiarity-memo")
def generate_familiarity_memo(project_id: str, body: MemoRequest):
    starting_memo = read_analysis(project_id).get('familiarity_memo')
    path = transcript_path(project_id)
    if not path:
        raise HTTPException(404, "没有找到访谈稿")
    key = read_deepseek_key()
    if not key:
        raise HTTPException(400, "未检测到 DeepSeek API Key")
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():raise HTTPException(400,'访谈稿没有可分析内容')
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=240.0, max_retries=0)
        from indexed_memo import IndexedMemoPipeline
        pipeline = IndexedMemoPipeline(text, project_dir(project_id)/'memo_runs', starting_memo,
                                       lambda request: limited_create(client, _attempts=1, **request))
        run = pipeline.run
        validated_memo = pipeline.generate()
        memo = {**validated_memo, "generated_at": time.time()}
        with document_transaction(analysis_path(project_id)):
            data = read_analysis(project_id)
            if data.get('familiarity_memo') != starting_memo:
                raise HTTPException(409, '生成期间纪要已被修改，本次结果未覆盖，请刷新后确认')
            current_source = transcript_path(project_id)
            if not current_source or current_source.read_text(encoding='utf-8-sig') != text:
                raise HTTPException(409, '生成期间访谈稿已修改，本次结果未覆盖，请刷新后确认')
            data["familiarity_memo"] = memo
            data["updated_at"] = time.time()
            atomic_write_json(analysis_path(project_id), data)
        run.complete()
        return {"run_id": run.id, "memo": memo, "_version": analysis_version(project_id)}
    except (SiteError, HTTPException):
        if 'run' in locals():run.fail(__import__('sys').exc_info()[1])
        raise
    except ValueError as exc:
        if 'run' in locals():run.fail(exc)
        raise HTTPException(502,'模型结果未通过校验，成功阶段已保留；'+str(exc).replace(key,'***')[:300]) from exc
    except Exception as exc:
        if 'run' in locals():run.fail(exc)
        log_failure('backend_operation_failed', exc)
        raise HTTPException(500, ("纪要未完成，已保留成功阶段。运行编号："+run.id+"。"+str(exc).replace(key, "***")[:300]) if "run" in locals() else str(exc).replace(key, "***")[:500])


@app.post("/api/projects/{project_id}/familiarity-summary")
def generate_familiarity_summary(project_id: str):
    data = read_analysis(project_id)
    memo = data.get("familiarity_memo")
    if not isinstance(memo, dict):
        raise HTTPException(400, "请先生成访谈纪要")
    from analysis_contracts import check_memo_source
    source = transcript_path(project_id)
    try:
        check_memo_source(memo, source.read_text(encoding='utf-8-sig') if source else '')
    except ValueError as error:
        raise HTTPException(409,str(error)) from error
    key = read_deepseek_key()
    if not key:
        raise HTTPException(400, "未检测到 DeepSeek API Key")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=240.0)
        response = client.chat.completions.create(
            model="deepseek-flash", temperature=0, max_tokens=800,
            response_format={"type": "json_object"}, extra_body={"thinking": {"type": "disabled"}},
            messages=[
                {"role": "system", "content": "你是中文社会科学访谈摘要助手。仅根据输入的访谈纪要，用一段120至200字概括访谈主要讨论了什么、受访者的核心判断及重要条件。不要逐条罗列观点，不要加入输入中没有的信息。只返回JSON：{\"summary\":\"一段话摘要\"}。"},
                {"role": "user", "content": json.dumps({"participant_identity": memo.get("participant_identity"), "interview_topic": memo.get("interview_topic"), "viewpoints": memo.get("viewpoints", [])}, ensure_ascii=False)},
            ],
        )
        from analysis_contracts import required_text
        summary = required_text(decode_model_json(response, "memo_summary").get("summary"), "summary")
        if not summary:
            raise HTTPException(502, "未生成有效摘要")
        with document_transaction(analysis_path(project_id)):
            latest = read_analysis(project_id)
            if latest.get('familiarity_memo') != memo:
                raise HTTPException(409, '生成期间纪要已被修改，本次摘要未覆盖，请刷新后确认')
            latest['familiarity_memo']['summary'] = summary
            latest['updated_at'] = time.time()
            atomic_write_json(analysis_path(project_id), latest)
        return {"summary": summary, "_version": analysis_version(project_id)}
    except (SiteError, HTTPException):
        raise
    except Exception as exc:
        log_failure('backend_operation_failed', exc)
        raise HTTPException(500, str(exc).replace(key, "***")[:500])


def normalize_comparison_differences(items, answers):
    supported = {answer["project_id"]: answer for answer in answers if answer["status"] == "answered"}
    differences = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("variants"), list):
            continue
        variants = []
        for variant in item["variants"]:
            if not isinstance(variant, dict):
                continue
            project_id = str(variant.get("project_id", ""))
            answer = supported.get(project_id)
            text = str(variant.get("text", "")).strip()
            if answer and text and project_id not in {v["project_id"] for v in variants}:
                variants.append({"project_id": project_id, "material_name": answer["material_name"],
                                 "text": text, "evidence": answer["evidence"]})
        if len(variants) >= 2 and len({v["text"] for v in variants}) >= 2:
            differences.append({"question": str(item.get("question", "")).strip(), "variants": variants})
    return differences


def normalize_question_comparison(raw, materials, theme, dimensions=None):
    aspects = []
    seen = set()
    for aspect in raw.get("aspects", []) if isinstance(raw, dict) and isinstance(raw.get("aspects"), list) else []:
        if not isinstance(aspect, dict):
            continue
        name = str(aspect.get("name", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        supplied = {str(a.get("project_id")): a for a in aspect.get("answers", []) if isinstance(a, dict)} if isinstance(aspect.get("answers"), list) else {}
        answers = []
        for material in materials:
            answer = supplied.get(material["project_id"], {})
            valid = {int(e["number"]) for e in material["evidence"] if str(e.get("number", "")).isdigit()}
            evidence = []
            for n in answer.get("evidence", []) if isinstance(answer.get("evidence"), list) else []:
                if str(n).isdigit() and int(n) in valid and int(n) not in evidence:
                    evidence.append(int(n))
            status = answer.get("status", "not_discussed")
            text = str(answer.get("text", "")).strip()
            if status not in ("answered", "not_discussed", "uncertain"):
                status = "uncertain"
            if status == "answered" and (not evidence or not text):
                status = "uncertain"
            answers.append({"project_id": material["project_id"], "material_name": material["name"], "status": status,
                            "text": text if status != "not_discussed" else "", "evidence": evidence if status != "not_discussed" else []})
        supported = {a["project_id"] for a in answers if a["status"] == "answered"}
        summaries = {}
        for category in ("common",):
            summaries[category] = []
            for item in aspect.get(category, []) if isinstance(aspect.get(category), list) else []:
                if not isinstance(item, dict):
                    continue
                ids = list(dict.fromkeys(str(i) for i in item.get("project_ids", []) if str(i) in supported)) if isinstance(item.get("project_ids"), list) else []
                text = str(item.get("text", "")).strip()
                if len(ids) >= 2 and text:
                    summaries[category].append({"text": text, "project_ids": ids})
        if supported:
            dimension = str(aspect.get("dimension", "")).strip()
            if dimensions and dimension not in dimensions:
                dimension = "其他发现"
            aspects.append({"dimension": dimension, "name": name, "question": str(aspect.get("question", "")).strip(),
                            "answers": answers, **summaries,
                            "differences": normalize_comparison_differences(aspect.get("differences"), answers)})
    return {"schema_version": 2, "theme": theme, "aspects": aspects, "materials": [{"project_id": m["project_id"], "name": m["name"]} for m in materials], "generated_at": time.time()}


def merge_question_comparison_batches(raw, batch_results, materials, theme, dimensions=None):
    source = {}
    for batch_index, batch in enumerate(batch_results):
        for aspect_index, aspect in enumerate(batch.get("aspects", [])):
            source[f"B{batch_index + 1}A{aspect_index + 1}"] = aspect
    merged = []
    used = set()
    for group in raw.get("aspects", []) if isinstance(raw, dict) and isinstance(raw.get("aspects"), list) else []:
        if not isinstance(group, dict):
            continue
        ids = [str(value) for value in group.get("member_ids", []) if str(value) in source and str(value) not in used] if isinstance(group.get("member_ids"), list) else []
        if not ids:
            continue
        used.update(ids)
        answers_by_material = {}
        for source_id in ids:
            for answer in source[source_id].get("answers", []):
                project_id = answer.get("project_id")
                previous = answers_by_material.get(project_id)
                if previous and previous.get("status") == "answered" and answer.get("status") == "answered":
                    texts = list(dict.fromkeys(text for text in (previous.get("text", ""), answer.get("text", "")) if text))
                    answers_by_material[project_id] = {**previous, "text": "；".join(texts),
                                                       "evidence": list(dict.fromkeys((previous.get("evidence") or []) + (answer.get("evidence") or [])))}
                elif not previous or (previous.get("status") != "answered" and answer.get("status") == "answered"):
                    answers_by_material[project_id] = answer
        accepted = {project_id for project_id, answer in answers_by_material.items() if answer.get("status") == "answered"}
        summaries = {}
        for category in ("common",):
            summaries[category] = []
            for item in group.get(category, []) if isinstance(group.get(category), list) else []:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text", "")).strip()
                ids_in_item = list(dict.fromkeys(str(value) for value in item.get("project_ids", []) if str(value) in accepted)) if isinstance(item.get("project_ids"), list) else []
                if text and len(ids_in_item) >= 2:
                    summaries[category].append({"text": text, "project_ids": ids_in_item})
        answers = [answers_by_material.get(material["project_id"], {"project_id": material["project_id"], "material_name": material["name"], "status": "not_discussed", "text": "", "evidence": []}) for material in materials]
        dimension = str(group.get("dimension", "")).strip() or source[ids[0]].get("dimension", "")
        if dimensions and dimension not in dimensions:
            dimension = "其他发现"
        merged.append({"dimension": dimension, "name": str(group.get("name", "")).strip() or source[ids[0]]["name"],
                       "question": str(group.get("question", "")).strip() or source[ids[0]].get("question", ""),
                       "answers": answers, **summaries,
                       "differences": normalize_comparison_differences(group.get("differences"), answers)})
    for source_id, aspect in source.items():
        if source_id not in used:
            answers = {answer["project_id"]: answer for answer in aspect.get("answers", [])}
            merged.append({**aspect, "answers": [answers.get(material["project_id"], {"project_id": material["project_id"], "material_name": material["name"], "status": "not_discussed", "text": "", "evidence": []}) for material in materials]})
    return {"schema_version": 2, "theme": theme, "aspects": merged, "materials": [{"project_id": m["project_id"], "name": m["name"]} for m in materials], "generated_at": time.time()}


@app.post("/api/material-comparisons")
def generate_material_comparison(body: MaterialComparisonRequest):
    if body.theme_analysis_id:
        research=read_json_document(research_project_path(body.research_project_id))
        analysis=next((a for a in research.get('theme_analyses',[]) if a.get('id')==body.theme_analysis_id),None)
        if not analysis:raise HTTPException(404,'主题分析记录不存在')
        from analysis_contracts import check_analysis_sources
        try:check_analysis_sources(analysis,transcript_path)
        except ValueError as error:raise HTTPException(409,str(error)) from error
        if analysis.get('theme')!=body.theme or set(body.project_ids)!={m['project_id'] for m in analysis.get('materials',[])}:raise HTTPException(400,'比较主题与材料不匹配')
        from openai import OpenAI
        from statement_comparison import generate
        key=read_deepseek_key()
        if not key:raise HTTPException(400,'未检测到 DeepSeek API Key')
        client=OpenAI(api_key=key,base_url='https://api.deepseek.com',timeout=120,max_retries=0)
        def statement_call(prompt,payload):
            response=client.chat.completions.create(model='deepseek-flash',temperature=0,max_tokens=9000,response_format={'type':'json_object'},extra_body={'thinking':{'type':'disabled'}},messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}])
            if response.choices[0].finish_reason!='stop':raise ValueError('比较输出不完整')
            return json.loads(response.choices[0].message.content)
        try:return {'comparison':generate(analysis,statement_call)}
        except (SiteError, HTTPException):
            raise
        except Exception as exc:
            log_failure('material_comparison_failed', exc)
            raise HTTPException(502,str(exc).replace(key,'***')[:400])
    theme = body.theme.strip()
    dimensions = list(dict.fromkeys(str(name).strip()[:80] for name in body.dimensions if str(name).strip()))[:20]
    if not theme or len(theme) > 300:
        raise HTTPException(400, "请填写不超过300字的比较主题")
    project_ids = list(dict.fromkeys(str(value).strip() for value in body.project_ids if str(value).strip()))
    if len(project_ids) < 2:
        raise HTTPException(400, "请至少选择两份访谈稿")
    if body.research_project_id:
        path = research_project_path(body.research_project_id)
        if not path.exists():
            raise HTTPException(404, "研究项目不存在")
        research = read_json_document(path)
        allowed = set(research.get("interview_ids", [])) | {
            str(item.get("workspace_project_id")) for item in research.get("uploaded_transcripts", []) if item.get("workspace_project_id")
        }
        if any(project_id not in allowed for project_id in project_ids):
            raise HTTPException(400, "请从本项目选择比较材料")
    key = read_deepseek_key()
    if not key:
        raise HTTPException(400, "未检测到 DeepSeek API Key")
    project_names = {item.get("id"): item.get("name", "") for item in list_projects()}
    materials = []
    missing = []
    for project_id in project_ids:
        if not metadata_path(project_id).exists():
            raise HTTPException(404, "所选访谈稿不存在")
        memo = read_analysis(project_id).get("familiarity_memo")
        if not memo:
            missing.append(project_names.get(project_id, project_id))
            continue
        from analysis_contracts import check_memo_source
        source=transcript_path(project_id)
        try:check_memo_source(memo,source.read_text(encoding='utf-8-sig') if source else '')
        except ValueError as error:raise HTTPException(409,str(error)) from error
        materials.append({
            "project_id": project_id,
            "name": project_names.get(project_id, project_id),
            "participant_identity": memo.get("participant_identity", "未说明"),
            "interview_topic": memo.get("interview_topic", "未说明"),
            "viewpoints": memo.get("viewpoints", []),
            "evidence": [{"number": item.get("number"), "quote": item.get("quote", "")} for item in memo.get("evidence", [])],
        })
    if missing:
        raise HTTPException(400, "请先为这些材料生成纪要：" + "、".join(missing))
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=240.0)
        prompt = (
            "你是一名严谨的中文定性研究材料比较助手。围绕用户的比较主题，对所选访谈纪要及附带原文证据进行比较。"
            "只使用输入材料，不补充外部知识，不将领域相近的内容自行归因于主题。每项回答都必须有明确或连续上下文的主题依据。"
            "先理解主题，再从材料实际讨论的内容归纳若干含义不同、粒度相近的比较方面。方面应是可以向每份材料提出的同一具体问题。"
            "不要机械套用满意度、质量、数量等预设分类；未被材料讨论的方面不建立。相近方面合并，不重复发现，不设置数量上限。"
            "逐方面对齐所有材料的回答。answered表示材料明确回答且有原文证据；not_discussed表示未讨论；uncertain表示无法确认。"
            "未讨论不等于否定、不认同或不存在，不能作为差异。保留受访者身份、条件和重要例外，不将受访者判断当成核实事实。"
            "如用户提供已有维度，只能从已有维度中选择dimension；不得另建相近维度。没有合适维度则填其他发现。"
            "每个方面的name写成相对具体的共同发现，而非空泛的分类标签。"
            "共性必须至少两份有证据的回答表达相近内容。单人回答仍可保留在answers，但不能制造共性。"
            "差异只比较同一具体事实问题的不同答案：先在question写明可比问题，再逐一列出真正不同的材料回答。"
            "仅仅谈到不同侧面、原因或例子，不是差异；未讨论也不是差异。若没有明确差异，differences必须为空数组。"
            "每条差异的variants至少两份，分别写明材料ID及其不同答案；不得只写一个笼统差异概括。"
            "共性用project_ids标明支持材料；差异中的project_id必须是该方面有证据的材料。"
            "回答概括相互关联的事实，细节为观点提供展开，不逐句罗列。证据编号只能使用该材料已有编号。"
            "只返回完整JSON，不使用Markdown："
            '{"aspects":[{"dimension":"已有维度名称或其他发现","name":"共同发现","question":"本方面比较的具体问题",'
            '"answers":[{"project_id":"材料ID","status":"answered|not_discussed|uncertain","text":"材料的回答","evidence":[1]}],'
            '"common":[{"text":"共性概括","project_ids":["材料ID1","材料ID2"]}],'
            '"differences":[{"question":"同一具体事实问题","variants":[{"project_id":"材料ID1","text":"该材料的答案"},{"project_id":"材料ID2","text":"不同答案"}]}]}]}'
        )
        def call_model(system_prompt, payload):
            response = client.chat.completions.create(
                model="deepseek-flash", temperature=0, max_tokens=8000,
                response_format={"type": "json_object"}, extra_body={"thinking": {"type": "disabled"}},
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            )
            if response.choices[0].finish_reason == "length":
                raise HTTPException(502, "比较结果超出单次输出长度")
            try:
                parsed = json.loads(response.choices[0].message.content or "{}")
            except json.JSONDecodeError:
                raise HTTPException(502, "模型返回的比较结果不完整，请重试")
            if not isinstance(parsed, dict) or not isinstance(parsed.get("aspects"), list):
                raise HTTPException(502, "模型未返回完整的比较结果，请重试")
            return parsed

        def compare_batch(batch):
            try:
                return normalize_question_comparison(call_model(prompt, {"theme": theme, "dimensions": dimensions, "materials": batch}), batch, theme, dimensions)
            except HTTPException as exc:
                if exc.status_code != 502 or len(batch) < 2:
                    raise
                middle = len(batch) // 2
                left = compare_batch(batch[:middle])
                right = compare_batch(batch[middle:])
                return merge_batches([left, right], batch)

        synthesis_prompt = (
            "你是中文定性研究材料比较助手。输入是同一主题的分批比较结果。先把含义相同或紧密相关的比较方面归为一组，"
            "每个输入方面ID必须恰好出现一次；不能遗漏或把无关方面合并。基于各访谈回答归纳共性和差异。"
            "保留输入的已有维度归属，相同问题才可合并。共性至少两份有证据的材料表达相近内容。"
            "差异必须是对同一具体事实问题的实质不同回答；不同侧面、原因、例子和未讨论均不构成差异。没有差异返回空数组。"
            "仅使用输入中的回答，不添加事实、证据、因果。各条共性/差异标明真正支持的project_ids。"
            "只返回完整JSON："
            '{"aspects":[{"dimension":"已有维度名称或其他发现","name":"共同发现","question":"共同问题","member_ids":["B1A1","B2A1"],'
            '"common":[{"text":"共性","project_ids":["材料ID1","材料ID2"]}],'
            '"differences":[{"question":"同一具体事实问题","variants":[{"project_id":"材料ID1","text":"答案一"},{"project_id":"材料ID2","text":"不同答案"}]}]}]}'
        )

        def merge_batches(batches, scope):
            if not any(batch.get("aspects") for batch in batches):
                return merge_question_comparison_batches({"aspects": []}, batches, scope, theme, dimensions)
            summary = []
            for batch_index, batch in enumerate(batches):
                for aspect_index, aspect in enumerate(batch.get("aspects", [])):
                    summary.append({"id": f"B{batch_index + 1}A{aspect_index + 1}", "dimension": aspect.get("dimension", ""), "name": aspect["name"], "question": aspect.get("question", ""),
                                    "answers": [{"project_id": answer["project_id"], "status": answer["status"], "text": answer["text"]} for answer in aspect.get("answers", []) if answer.get("status") == "answered"]})
            raw = call_model(synthesis_prompt, {"theme": theme, "dimensions": dimensions, "aspects": summary})
            return merge_question_comparison_batches(raw, batches, scope, theme, dimensions)

        if len(materials) <= 2:
            comparison = compare_batch(materials)
        else:
            batches = [compare_batch(materials[index:index + 2]) for index in range(0, len(materials), 2)]
            comparison = merge_batches(batches, materials)
        return {"comparison": comparison}
    except (SiteError, HTTPException):
        raise
    except Exception as exc:
        log_failure('backend_operation_failed', exc)
        raise HTTPException(500, str(exc).replace(key, "***")[:500])


@app.post("/api/theme-analyses")
def generate_theme_analysis(body: ThemeAnalysisRequest):
    from indexed_theme import run_theme
    return run_theme(body, research_project_path, transcript_path, RESEARCH_FILES_DIR, list_projects)


@app.get("/api/research-projects/{project_id}/theme-run-status")
def latest_theme_run_status(project_id: str, request_token: str = ""):
    project = research_project_path(project_id)
    if not project.exists():
        raise HTTPException(404, '研究项目不存在')
    root = RESEARCH_FILES_DIR / project.stem / 'theme_analysis_runs'
    manifests = sorted(root.glob('*/manifest.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    if request_token:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request_token):
            raise HTTPException(400, '请求标识格式无效')
        manifests = [p for p in manifests if read_theme_json(p).get('request_token') == request_token]
    if not manifests:
        return {'retry': None}
    manifest = read_theme_json(manifests[0])
    if manifest.get('status') not in ('failed', 'integration_failed') or manifest.get('theme_pipeline_version') != 4:
        return {'retry': None, 'status': manifest.get('status'), 'runId': manifest.get('run_id'),
                'progress': manifest.get('progress') if manifest.get('status') in ('running', 'integrating') else None}
    for pid, digest in manifest.get('source_hashes', {}).items():
        source = transcript_path(pid)
        if not source or hashlib.sha256(source.read_text(encoding='utf-8-sig').encode()).hexdigest() != digest:
            return {'retry': None, 'notice': '失败任务的原文已变化，请新建分析。'}
    return {'retry': {'runId': manifest['run_id'], 'theme': manifest['theme'],
                     'projectId': project.stem, 'ids': manifest['material_ids'],
                     'recovery': not (manifests[0].parent / 'statements.json').exists()}}


@app.post("/api/research-projects/{project_id}/theme-analyses")
@locked_document(lambda values: research_project_path(values['project_id']))
def save_theme_analysis(project_id: str, body: ThemeAnalysisSaveRequest):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    analysis = dict(body.analysis or {})
    name = str(analysis.get("name", "")).strip()[:80]
    if not name or not str(analysis.get("theme", "")).strip():
        raise HTTPException(400, "请填写分析名称和主题")
    if not isinstance(analysis.get("dimensions"), list) and not any(isinstance(analysis.get(key), list) for key in ("findings", "exceptions")):
        raise HTTPException(400, "没有可保存的分析结果")
    analysis["name"] = name
    from review_storage import rehome
    new_analysis_id = uuid.uuid4().hex
    source_project = read_json_document(path)
    if body.request_id:
        if not re.fullmatch(r'[a-zA-Z0-9-]{8,80}',body.request_id):
            raise HTTPException(400,'保存请求标识格式无效')
        digest=hashlib.sha256(json.dumps(body.analysis,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        previous=next((a for a in source_project.get('theme_analyses',[]) if a.get('_save_request_id')==body.request_id),None)
        if previous:
            if previous.get('_save_digest')!=digest:raise HTTPException(409,'该保存标识已用于不同内容，请刷新后重试')
            return {'analysis':previous,'count':len(source_project['theme_analyses']),'reused':True}
        analysis['_save_request_id']=body.request_id
        analysis['_save_digest']=digest
    original_analysis = next((a for a in source_project.get('theme_analyses', []) if a.get('id') == analysis.get('id')), {})
    try:
        rehome(analysis, RESEARCH_FILES_DIR, project_id, new_analysis_id, original_analysis.get('finding_reviews', []))
    except (OSError, ValueError) as exc:
        raise HTTPException(409, '核查档案未能完整复制，分析尚未保存') from exc
    analysis["id"] = new_analysis_id
    analysis["saved_at"] = time.time()
    research = read_json_document(path)
    records = research.setdefault("theme_analyses", [])
    records.append(analysis)
    research["updated_at"] = analysis["saved_at"]
    atomic_write_json(path, research)
    return {"analysis": analysis, "count": len(records)}


@app.put("/api/research-projects/{project_id}/theme-analyses/{analysis_id}/comparison")
@locked_document(lambda values: research_project_path(values['project_id']))
def save_theme_comparison(project_id: str, analysis_id: str, body: MaterialComparisonSaveRequest):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    research = read_json_document(path)
    record = next((item for item in research.get("theme_analyses", []) if item.get("id") == analysis_id), None)
    if record is None:
        raise HTTPException(404, "主题分析记录不存在")
    comparison = dict(body.comparison or {})
    expected = {str(item.get("project_id")) for item in record.get("materials", [])}
    actual = {str(item.get("project_id")) for item in comparison.get("materials", []) if isinstance(item, dict)}
    if not isinstance(comparison.get("aspects"), list) or comparison.get("theme") != record.get("theme") or actual != expected:
        raise HTTPException(400, "比较结果与主题分析记录不匹配")
    if isinstance(record.get("comparison"), dict):
        record.setdefault("previous_comparisons", []).append(record["comparison"])
    record["comparison"] = comparison
    record["updated_at"] = time.time()
    research["updated_at"] = record["updated_at"]
    atomic_write_json(path, research)
    return {"analysis": record}


@app.post("/api/research-projects/{project_id}/material-comparisons")
@locked_document(lambda values: research_project_path(values['project_id']))
def save_material_comparison(project_id: str, body: MaterialComparisonSaveRequest):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    comparison = dict(body.comparison or {})
    name = str(comparison.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "请填写比较结果名称")
    comparison["name"] = name[:80]
    if not any(isinstance(comparison.get(key), list) for key in ("aspects", "common", "differences", "unique")):
        raise HTTPException(400, "没有可保存的比较结果")
    comparison["id"] = comparison.get("id") or uuid.uuid4().hex
    comparison["saved_at"] = time.time()
    research = read_json_document(path)
    records = research.setdefault("material_comparisons", [])
    records.append(comparison)
    research["updated_at"] = comparison["saved_at"]
    atomic_write_json(path, research)
    return {"comparison": comparison, "count": len(records)}


@app.put("/api/research-projects/{project_id}/material-comparisons/{record_index}")
@locked_document(lambda values: research_project_path(values['project_id']))
def rename_material_comparison(project_id: str, record_index: int, body: MaterialComparisonRenameRequest):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "请填写比较结果名称")
    research = read_json_document(path)
    records = research.get("material_comparisons", [])
    if record_index < 0 or record_index >= len(records):
        raise HTTPException(404, "比较记录不存在")
    records[record_index]["name"] = name[:80]
    research["updated_at"] = time.time()
    atomic_write_json(path, research)
    return {"comparison": records[record_index]}


@app.delete("/api/research-projects/{project_id}/material-comparisons/{record_index}")
@locked_document(lambda values: research_project_path(values['project_id']))
def delete_material_comparison(project_id: str, record_index: int):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    research = read_json_document(path)
    records = research.get("material_comparisons", [])
    if record_index < 0 or record_index >= len(records):
        raise HTTPException(404, "比较记录不存在")
    removed = records.pop(record_index)
    archive = RESEARCH_FILES_DIR / project_id / "deleted_comparisons"
    archive.mkdir(parents=True, exist_ok=True)
    atomic_write_json(archive / f"{uuid.uuid4().hex}.json", removed)
    research["updated_at"] = time.time()
    atomic_write_json(path, research)
    return {"deleted": True, "count": len(records)}


@app.get("/api/comparison")
def comparison():
    rows, code_names = [], set()
    for directory in PROJECTS_DIR.iterdir() if PROJECTS_DIR.exists() else []:
        meta_path = directory / "project.json"
        if not directory.is_dir() or not meta_path.exists():
            continue
        data = read_analysis(directory.name)
        if not data.get("excerpts"):
            continue
        meta = read_json_document(meta_path); code_map = {item.get("id"): item.get("name", "") for item in data.get("codes", [])}; counts = {}
        for excerpt in data.get("excerpts", []):
            name = code_map.get(excerpt.get("code_id"), "")
            if name:
                counts[name] = counts.get(name, 0) + 1; code_names.add(name)
        rows.append({"project": meta.get("name", directory.name), "metadata": data.get("metadata", {}), "counts": counts})
    return {"codes": sorted(code_names), "rows": rows}


from theme_network import register_theme_network
from interview_move import register_interview_move
register_interview_move(app, research_project_path, metadata_path, prepare_uploaded_research_material)
from source_search import register_source_search
register_source_search(app, transcript_path, read_deepseek_key)
register_theme_network(app, research_project_path, RESEARCH_FILES_DIR, read_analysis, read_deepseek_key, transcript_path)
from word_cooccurrence import register_word_cooccurrence
register_word_cooccurrence(app, research_project_path, transcript_path, read_deepseek_key, prepare_uploaded_research_material, read_metadata)
from ai_coding_demo import register as register_ai_coding_demo
register_ai_coding_demo(app,research_project_path,transcript_path,read_metadata,RESEARCH_FILES_DIR,project_dir)

from finding_review import install as install_finding_review
install_finding_review(app, research_project_path, read_deepseek_key, RESEARCH_FILES_DIR)

if __name__ == "__main__":
    if (CODE_DIR / '.site-data' / 'enabled.json').exists():
        from run_accounts import main
        main()
        raise SystemExit(0)
    import uvicorn

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex(("127.0.0.1", 8765)) == 0:
            webbrowser.open("http://127.0.0.1:8765")
            raise SystemExit(0)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
