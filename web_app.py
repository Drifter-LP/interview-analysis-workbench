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
import winreg
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from theme_file_io import read_json as read_theme_json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from concurrent.futures import ThreadPoolExecutor
from interview_facts import limited_create


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "web"
PROJECTS_DIR = APP_DIR / "projects"
RESEARCH_PROJECTS_DIR = APP_DIR / "research_projects"
RESEARCH_FILES_DIR = APP_DIR / "research_project_files"
QWEN_DIR = APP_DIR / "Qwen3-ASR"
QWEN_MODEL = QWEN_DIR / "Qwen3-ASR-0.6B"
PYTHON = QWEN_DIR / "venv312" / "Scripts" / "python.exe"
TRANSCRIBER = QWEN_DIR / "qwen_transcribe.py"
HOTWORDS = APP_DIR / "基层医疗热词.txt"
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

os.environ.setdefault("MODELSCOPE_CACHE", str(APP_DIR / "models"))
os.environ.setdefault("HF_HOME", str(APP_DIR / "models" / "huggingface"))
os.environ.setdefault("TEMP", str(APP_DIR / "temp"))
os.environ.setdefault("TMP", str(APP_DIR / "temp"))

app = FastAPI(title="访谈分析工作台")
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
    return json.loads(path.read_text(encoding="utf-8"))


def write_metadata(project_id: str, data: dict) -> None:
    metadata_path(project_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return empty_analysis()
    for key, default in (("metadata", {}), ("sources", []), ("codes", []), ("excerpts", []), ("ai_suggestions", [])):
        data.setdefault(key, default)
    return data


def read_deepseek_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as registry_key:
            value, _ = winreg.QueryValueEx(registry_key, "DEEPSEEK_API_KEY")
            return str(value).strip()
    except (FileNotFoundError, OSError):
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
        if not change.get("applied") or change.get("stage") != "word" or confidence not in {"中", "低"} or not revised:
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


def run_transcription(project_id: str, audio_path: Path) -> None:
    global active_project
    directory = project_dir(project_id)
    meta = read_metadata(project_id)
    meta.update(status="running", started_at=time.time(), message="正在加载模型并转录")
    write_metadata(project_id, meta)
    log_path = directory / "运行记录.txt"
    command = [
        str(PYTHON),
        str(TRANSCRIBER),
        str(audio_path),
        "--output-dir",
        str(directory),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        log_path.write_text(
            (completed.stdout or "") + "\n" + (completed.stderr or ""), encoding="utf-8"
        )
        meta = read_metadata(project_id)
        if completed.returncode == 0:
            meta.update(
                status="completed",
                finished_at=time.time(),
                message="转录完成，可以校订和分析",
            )
        else:
            meta.update(status="failed", message="转录失败，请查看运行记录")
        write_metadata(project_id, meta)
    except Exception as exc:
        meta = read_metadata(project_id)
        meta.update(status="failed", message=str(exc))
        write_metadata(project_id, meta)
    finally:
        with active_lock:
            active_project = None


class TranscriptUpdate(BaseModel):
    text: str
    accepted_change_ids: list[str] = []


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
    ready = PYTHON.exists() and TRANSCRIBER.exists() and (QWEN_MODEL / "config.json").exists()
    return {
        "ready": ready,
        "gpu": "NVIDIA GeForce RTX 3050",
        "model_count": 1 if ready else 0,
        "engine": "Qwen3-ASR-0.6B",
        "speaker_engine": "CAM++",
        "active_project": active_project,
    }


@app.get("/api/projects")
def list_projects():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    from interview_names import normalize_names
    normalize_names(PROJECTS_DIR, RESEARCH_PROJECTS_DIR, RESEARCH_FILES_DIR,
                    APP_DIR / "backups", refresh_material_names)
    projects = []
    for path in PROJECTS_DIR.iterdir():
        meta = path / "project.json"
        if path.is_dir() and meta.exists():
            try:
                item = json.loads(meta.read_text(encoding="utf-8"))
                item["hidden_in_library"] = bool(item.get("hidden_at") or item.get("deleted_at"))
                projects.append(item)
            except Exception:
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
        meta = read_metadata(project_id)
        meta["last_opened_at"] = time.time()
        write_metadata(project_id, meta)
    return {"last_opened_at": meta["last_opened_at"]}


class InterviewVisibilityRequest(BaseModel):
    hidden: bool


@app.post("/api/projects/{project_id}/visibility")
def set_interview_visibility(project_id: str, body: InterviewVisibilityRequest):
    """Visibility affects only the library, not material pickers or analysis."""
    with active_lock:
        meta = read_metadata(project_id)
        if body.hidden and (active_project == project_id or meta.get("status") in {"queued", "running"}):
            raise HTTPException(409, "访谈正在转录，请完成后再隐藏")
        meta.pop("deleted_at", None)
        if body.hidden:
            meta["hidden_at"] = time.time()
        else:
            meta.pop("hidden_at", None)
        target = metadata_path(project_id)
        temporary = target.with_name("project.delete-" + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return {"hidden": body.hidden, "recoverable": True}


def research_project_path(project_id: str) -> Path:
    path = (RESEARCH_PROJECTS_DIR / f"{project_id}.json").resolve()
    if path.parent != RESEARCH_PROJECTS_DIR.resolve():
        raise HTTPException(400, "研究项目编号无效")
    return path




@app.get("/api/research-projects")
def list_research_projects(summaries: bool = False):
    RESEARCH_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    interview_names = {item.get("id"): item.get("name", "") for item in list_projects()}
    items = []
    for path in RESEARCH_PROJECTS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
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
                path.write_text(json.dumps({key: value for key, value in item.items() if key != "interviews"}, ensure_ascii=False, indent=2), encoding="utf-8")
            listed=project_listing(item)
            if summaries:
                listed['theme_analyses']=[{**{k:a[k] for k in ('id','name','theme','saved_at','created_at') if k in a},'_summary':True} for a in listed.get('theme_analyses',[])]
            items.append(listed)
        except Exception:
            continue
    return sorted(items, key=lambda item: item.get("last_opened_at", item.get("created_at", 0)), reverse=True)


@app.get('/api/research-projects/{project_id}/theme-analysis-records/{record_index}')
def theme_analysis_record(project_id: str, record_index: int):
    from review_storage import project_listing
    p=research_project_path(project_id)
    if not p.exists():raise HTTPException(404,'研究项目不存在')
    records=json.loads(p.read_text(encoding='utf-8')).get('theme_analyses',[])
    if record_index<0 or record_index>=len(records):raise HTTPException(404,'分析记录不存在')
    return project_listing({'theme_analyses':[records[record_index]]})['theme_analyses'][0]

@app.post("/api/research-projects/{project_id}/opened")
def mark_research_project_opened(project_id: str):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    item = json.loads(path.read_text(encoding="utf-8"))
    item["last_opened_at"] = time.time()
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
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
    meta = read_metadata(project_id)
    meta["name"] = name
    write_metadata(project_id, meta)
    for path in RESEARCH_PROJECTS_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        before = json.dumps(data, ensure_ascii=False)
        refresh_material_names(data, project_id, name)
        if json.dumps(data, ensure_ascii=False) != before:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    list_projects()
    return {"id": project_id, "name": read_metadata(project_id)["name"]}


@app.put("/api/research-projects/{project_id}/name")
def rename_research_project(project_id: str, body: DisplayNameRequest):
    name = display_name(body.name)
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["name"] = name
    data["updated_at"] = time.time()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": project_id, "name": name}


@app.put("/api/research-projects/{project_id}/uploaded/{material_index}/name")
def rename_uploaded_interview(project_id: str, material_index: int, body: DisplayNameRequest):
    name = display_name(body.name)
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    uploads = data.get("uploaded_transcripts", [])
    if not 0 <= material_index < len(uploads):
        raise HTTPException(404, "访谈稿不存在")
    material = uploads[material_index]
    linked = material.get("workspace_project_id")
    if linked and metadata_path(linked).exists():
        return rename_interview(linked, body)
    material["name"] = name
    data["updated_at"] = time.time()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    list_projects()
    refreshed = json.loads(path.read_text(encoding="utf-8"))
    return {"name": refreshed["uploaded_transcripts"][material_index]["name"]}


@app.delete("/api/research-projects/{project_id}")
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
def remove_research_material(project_id: str, material_type: str, material_key: str):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    item = json.loads(path.read_text(encoding="utf-8"))
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
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
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
    research_project_path(project_id).write_text(
        json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
    )
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
        target.write_text(text, encoding="utf-8-sig")
        uploaded.append({"name": upload.filename, "file": target.name, "material_type": "interview"})
    return uploaded


@app.post("/api/research-projects/{project_id}/materials")
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
    available = {item.get("id") for item in list_projects()}
    selected_ids = list(dict.fromkeys(str(item) for item in selected_ids))
    if any(item not in available for item in selected_ids):
        raise HTTPException(400, "所选访谈稿不存在")
    item = json.loads(path.read_text(encoding="utf-8"))
    item["interview_ids"] = list(dict.fromkeys(item.get("interview_ids", []) + selected_ids))
    material_types = item.setdefault("material_types", {})
    for interview_id in selected_ids:
        material_types[interview_id] = "interview"
    item["uploaded_transcripts"] = item.get("uploaded_transcripts", []) + save_research_uploads(project_id, transcripts)
    item["updated_at"] = time.time()
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    return item


@app.post("/api/research-projects/{project_id}/uploaded/{material_index}/prepare")
def prepare_uploaded_research_material(project_id: str, material_index: int):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    item = json.loads(path.read_text(encoding="utf-8"))
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
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
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


@app.post("/api/transcript-projects")
def create_transcript_project(name: str = Form(""), transcript: UploadFile = File(...)):
    text = read_uploaded_transcript(transcript)
    if not text:
        raise HTTPException(400, "访谈稿内容为空")
    project_id = safe_id(name or Path(transcript.filename or "访谈稿").stem) + "-" + uuid.uuid4().hex[:6]
    directory = project_dir(project_id); directory.mkdir(parents=True)
    (directory / "导入访谈稿.txt").write_text(text, encoding="utf-8-sig")
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
    path = transcript_path(project_id)
    meta["has_transcript"] = bool(path)
    return meta


@app.get("/api/projects/{project_id}/transcript")
def get_transcript(project_id: str):
    path = transcript_path(project_id)
    if not path:
        raise HTTPException(404, "转录稿尚未生成")
    text = path.read_text(encoding="utf-8-sig")
    annotations = []
    record_path = project_dir(project_id) / "DeepSeek修改记录.json"
    if path.name in {"DeepSeek自动校订稿.txt", "校订稿.txt"} and record_path.exists():
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            annotations = record.get("annotations") or build_review_annotations(text, record.get("changes", []))
            if "annotations" not in record:
                record["annotations"] = annotations
                record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, ValueError, TypeError):
            annotations = []
    return {"text": text, "edited": path.name in {"校订稿.txt", "DeepSeek自动校订稿.txt"}, "annotations": annotations}

from audio_pairing import install as install_audio_pairing
install_audio_pairing(app, APP_DIR, project_dir)

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
def accept_transcript_change(project_id: str, body: ChangeDecision):
    record_path = project_dir(project_id) / "DeepSeek修改记录.json"
    if not record_path.exists():
        raise HTTPException(404, "修改记录不存在")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    found = False
    for item in record.get("annotations", []):
        if item.get("change_id") == body.change_id:
            item["accepted"] = True; found = True
    for item in record.get("changes", []):
        if item.get("change_id") == body.change_id:
            item["accepted"] = True
    if not found:
        raise HTTPException(404, "没有找到这条修改")
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"accepted": True}


@app.put("/api/projects/{project_id}/transcript")
def save_transcript(project_id: str, body: TranscriptUpdate):
    directory = project_dir(project_id)
    if not directory.exists():
        raise HTTPException(404, "项目不存在")
    target = directory / "校订稿.txt"
    target.write_text(body.text, encoding="utf-8-sig")
    record_path = directory / "DeepSeek修改记录.json"
    if body.accepted_change_ids and record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        accepted = set(body.accepted_change_ids)
        for item in record.get("annotations", []):
            if item.get("change_id") in accepted:
                item["accepted"] = True
        for item in record.get("changes", []):
            if item.get("change_id") in accepted:
                item["accepted"] = True
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = read_metadata(project_id)
    meta["edited_at"] = time.time()
    write_metadata(project_id, meta)
    return {"saved": True}


@app.post("/api/projects/{project_id}/optimize-transcript")
def optimize_transcript(project_id: str):
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

    def write_call_log(data: dict) -> None:
        entry = {"run_id": run_id, "logged_at": time.time(), **data}
        with log_path.open("a", encoding="utf-8") as log_file:
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
    (directory / "本地自动整理稿.txt").write_text(local_output, encoding="utf-8-sig")
    (directory / "本地自动整理修改记录.json").write_text(json.dumps({"created_at": time.time(), "counts": local_counts, "units": local_records}, ensure_ascii=False, indent=2), encoding="utf-8")

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

    content_rules = (APP_DIR / "AI文字校订规则.txt").read_text(encoding="utf-8-sig") if (APP_DIR / "AI文字校订规则.txt").exists() else ""
    punctuation_rules = (APP_DIR / "AI标点整理规则.txt").read_text(encoding="utf-8-sig") if (APP_DIR / "AI标点整理规则.txt").exists() else ""
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
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=240.0)
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
            (checkpoint_dir / f"{stage}-{safe_label}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            summary = {"stage": stage, "batch": label, "unit_count": len(source_chunk), "saved_at": payload["saved_at"]}
            target = "completed_batches" if status == "completed" else "failed_batches"
            checkpoint_manifest[target] = [item for item in checkpoint_manifest[target] if not (item["stage"] == stage and item["batch"] == label)]
            checkpoint_manifest[target].append({**summary, **({"error": error[:500]} if error else {})})
            (checkpoint_dir / "manifest.json").write_text(
                json.dumps(checkpoint_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        total_batches = len(make_chunks(units, 8500)) + len(make_chunks(units, 2500))
        write_call_log({"event": "run_started", "model": "deepseek-v4-pro", "batch_count": total_batches, "unit_count": len(units), "key_fingerprint": key_fingerprint, "local_preprocessing": local_counts, "max_suggestion_chars": MAX_AI_SUGGESTION_CHARS})

        def run_stage(source_units: list[dict], stage: str, rules: str) -> list[dict]:
            max_chars = 2500 if stage == "punctuation" else 8500
            max_split_depth = 4

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

            def process_chunk(chunk: list[dict], label: str, depth: int = 0) -> list[dict]:
                started_at = time.time()
                try:
                    response = client.chat.completions.create(
                        model="deepseek-v4-pro", temperature=0, max_tokens=12000,
                        response_format={"type": "json_object"}, extra_body={"thinking": {"type": "disabled"}},
                        messages=[{"role": "system", "content": rules}, {"role": "user", "content": json.dumps({"units": chunk}, ensure_ascii=False)}],
                    )
                    raw_content = response.choices[0].message.content or "{}"
                    raw_name = re.sub(r"[^0-9A-Za-z_-]+", "-", label)
                    (raw_dir / f"{stage}-{raw_name}.json").write_text(raw_content, encoding="utf-8")
                    parsed = json.loads(raw_content)
                    returned = parsed.get("units", [])
                    if len(returned) != len(chunk):
                        raise RuntimeError(f"{stage}阶段返回的发言单元数量不一致")
                    revised_chunk, batch_records, applied_count = [], [], 0
                    for source, result in zip(chunk, returned):
                        revised_text, records = apply_suggestions(source["text"], result.get("suggestions", []), stage)
                        enriched = [{"unit_id": source["unit_id"], "speaker": source["speaker"], **item} for item in records]
                        applied_count += sum(bool(item.get("applied")) for item in records)
                        batch_records.extend(enriched)
                        revised_chunk.append({"unit_id": source["unit_id"], "speaker": source["speaker"], "text": revised_text})
                    all_records.extend(batch_records)
                    save_checkpoint(stage, label, "completed", chunk, revised_chunk, batch_records)
                    usage = response.usage.model_dump() if getattr(response, "usage", None) else {}
                    finish_reason = getattr(response.choices[0], "finish_reason", None)
                    write_call_log({"event": "batch_completed", "stage": stage, "batch": label, "request_id": getattr(response, "id", None), "model": getattr(response, "model", None), "finish_reason": finish_reason, "response_chars": len(raw_content), "elapsed_seconds": round(time.time() - started_at, 3), "unit_count": len(chunk), "applied_change_count": applied_count, "usage": usage})
                    return revised_chunk
                except (json.JSONDecodeError, RuntimeError) as batch_exc:
                    error_text = str(batch_exc).replace(key, "***")[:1000]
                    parts = split_chunk(chunk) if depth < max_split_depth else None
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
                except Exception as batch_exc:
                    error_text = str(batch_exc).replace(key, "***")[:1000]
                    write_call_log({"event": "batch_failed", "stage": stage, "batch": label, "elapsed_seconds": round(time.time() - started_at, 3), "error": error_text})
                    save_checkpoint(stage, label, "failed", chunk, error=error_text)
                    failed_batches.append({"stage": stage, "batch": label, "unit_ids": [item["unit_id"] for item in chunk], "error": error_text})
                    return [dict(item) for item in chunk]

            revised_units = []
            for batch_index, chunk in enumerate(make_chunks(source_units, max_chars), 1):
                revised_units.extend(process_chunk(chunk, f"第{batch_index:03d}批"))
            return revised_units

        revised = run_stage(units, "word", content_rules)
        revised = run_stage(revised, "punctuation", punctuation_rules)
        output = "\n\n".join((f"{item['speaker']}：" if item["speaker"] else "") + item["text"] for item in revised)
        (project_dir(project_id) / "DeepSeek自动校订稿.txt").write_text(output, encoding="utf-8-sig")
        annotations = build_review_annotations(output, all_records)
        (directory / "DeepSeek修改记录.json").write_text(json.dumps({"run_id": run_id, "changes": all_records, "annotations": annotations, "failed_batches": failed_batches}, ensure_ascii=False, indent=2), encoding="utf-8")
        applied_total = sum(bool(item.get("applied")) for item in all_records)
        skipped_total = len(all_records) - applied_total
        write_call_log({"event": "run_completed", "applied_change_count": applied_total, "skipped_change_count": skipped_total, "failed_batch_count": len(failed_batches), "failed_batches": failed_batches, "changed_unit_count": sum(item["text"] != source["text"] for item, source in zip(revised, units))})
        checkpoint_manifest["finished_at"] = time.time()
        checkpoint_manifest["failed_batches"] = failed_batches
        (checkpoint_dir / "manifest.json").write_text(json.dumps(checkpoint_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        meta = read_metadata(project_id); meta["ai_edited_at"] = time.time(); meta["ai_run_id"] = run_id; meta["ai_key_fingerprint"] = key_fingerprint; meta["ai_partial"] = bool(failed_batches); write_metadata(project_id, meta)
        message = f"AI修订完成：应用 {applied_total} 处，跳过 {skipped_total} 处"
        if failed_batches:
            message += f"；{len(failed_batches)} 个子批次未完成，已保留其他批次结果"
        return {"text": output, "annotations": annotations, "failed_batches": failed_batches, "message": message}
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
    return read_analysis(project_id)


@app.put("/api/projects/{project_id}/analysis-workspace")
def save_analysis_workspace(project_id: str, body: AnalysisUpdate):
    read_metadata(project_id)
    data = body.data
    for key, default in (("metadata", {}), ("sources", []), ("codes", []), ("excerpts", []), ("ai_suggestions", [])):
        data.setdefault(key, default)
    data["updated_at"] = time.time()
    analysis_path(project_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": True, "updated_at": data["updated_at"]}


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
                model="deepseek-v4-pro", temperature=0, max_tokens=6000,
                response_format={"type": "json_object"}, extra_body={"thinking": {"type": "disabled"}},
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            )
            if response.choices[0].finish_reason != "stop":
                raise ValueError("编码回复未完整结束，本次未写入建议，请缩小编码范围后重试")
            return json.loads(response.choices[0].message.content or "{}")
        existing = read_analysis(project_id).get("codes", [])
        return generate_initial_codes(text, body.research_question, existing, project_id, call)
    except Exception as exc:
        raise HTTPException(500, str(exc).replace(key, "***")[:500])


@app.post("/api/projects/{project_id}/familiarity-memo")
def generate_familiarity_memo(project_id: str, body: MemoRequest):
    path = transcript_path(project_id)
    if not path:
        raise HTTPException(404, "没有找到访谈稿")
    key = read_deepseek_key()
    if not key:
        raise HTTPException(400, "未检测到 DeepSeek API Key")
    text = path.read_text(encoding="utf-8-sig")
    chunks = []
    current = []
    size = 0
    for block in [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]:
        if current and size + len(block) > 12000:
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block)
    if current:
        chunks.append("\n\n".join(current))
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=240.0)
        prompt = (
            "你是中文社会科学访谈纪要助手。根据访谈稿生成忠于原文的材料熟悉纪要。"
            "只提取受访者明确表达的信息，不推测身份和日期；无法确认时写‘未说明’。"
            "先用一段120至200字的summary概括这份访谈主要讨论了什么、受访者的核心判断及重要条件；不要逐条罗列观点，不要加入原文没有的信息。"
            "核心观点必须结构化，每个观点包含简短标题、完整概括、若干具体要点。"
            "每个观点概括和具体要点都必须附带1至3条能够直接支持它的连续原文。"
            "证据quote必须逐字复制输入文本中的连续片段，不得改写，通常20至120字。"
            "忽略访谈者自身观点，区分访谈者提问与受访者回答。"
            "只返回JSON："
            '{"participant_identity":"身份","interview_date":"日期","interview_topic":"主题","summary":"一段话摘要",'
            '"viewpoints":[{"title":"观点标题","summary":"观点概括","evidence":["连续原文"],'
            '"points":[{"text":"具体要点","evidence":["连续原文"]}]}]}。'
        )
        partials = []
        for index, chunk in enumerate(chunks, 1):
            response = limited_create(client,
                model="deepseek-v4-pro", temperature=0, max_tokens=8000,
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps({"part": index, "total_parts": len(chunks), "text": chunk}, ensure_ascii=False)},
                ],
            )
            partials.append(json.loads(response.choices[0].message.content or "{}"))
        if len(partials) == 1:
            merged = partials[0]
        else:
            response = limited_create(client,
                model="deepseek-v4-pro", temperature=0, max_tokens=8000,
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
                messages=[
                    {"role": "system", "content": prompt + "现在合并分段纪要，合并重复观点，保留全部有效证据原文。"},
                    {"role": "user", "content": json.dumps({"partial_memos": partials}, ensure_ascii=False)},
                ],
            )
            merged = json.loads(response.choices[0].message.content or "{}")
        evidence_items = []
        evidence_lookup = {}

        def attach_evidence(quotes) -> list[int]:
            numbers = []
            for value in quotes if isinstance(quotes, list) else []:
                quote = str(value).strip()
                if not quote or quote not in text:
                    continue
                if quote not in evidence_lookup:
                    start = text.find(quote)
                    evidence_lookup[quote] = len(evidence_items) + 1
                    evidence_items.append({"number": len(evidence_items) + 1, "quote": quote, "start": start, "end": start + len(quote)})
                numbers.append(evidence_lookup[quote])
            return numbers

        viewpoints = []
        for item in merged.get("viewpoints", []) if isinstance(merged.get("viewpoints"), list) else []:
            if not isinstance(item, dict):
                continue
            points = []
            for point in item.get("points", []) if isinstance(item.get("points"), list) else []:
                if isinstance(point, dict) and str(point.get("text", "")).strip():
                    points.append({"text": str(point.get("text", "")).strip(), "evidence": attach_evidence(point.get("evidence", []))})
            title = str(item.get("title", "")).strip()
            summary = str(item.get("summary", "")).strip()
            if title or summary:
                viewpoints.append({"title": title, "summary": summary, "evidence": attach_evidence(item.get("evidence", [])), "points": points})
        memo = {
            "participant_identity": str(merged.get("participant_identity", "未说明")).strip() or "未说明",
            "interview_date": str(merged.get("interview_date", "未说明")).strip() or "未说明",
            "interview_topic": str(merged.get("interview_topic", "未说明")).strip() or "未说明",
            "summary": str(merged.get("summary", "")).strip(),
            "viewpoints": viewpoints,
            "evidence": evidence_items,
            "generated_at": time.time(),
        }
        data = read_analysis(project_id)
        data["familiarity_memo"] = memo
        data["updated_at"] = time.time()
        analysis_path(project_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"memo": memo}
    except Exception as exc:
        raise HTTPException(500, str(exc).replace(key, "***")[:500])


@app.post("/api/projects/{project_id}/familiarity-summary")
def generate_familiarity_summary(project_id: str):
    data = read_analysis(project_id)
    memo = data.get("familiarity_memo")
    if not isinstance(memo, dict):
        raise HTTPException(400, "请先生成访谈纪要")
    key = read_deepseek_key()
    if not key:
        raise HTTPException(400, "未检测到 DeepSeek API Key")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com", timeout=240.0)
        response = client.chat.completions.create(
            model="deepseek-v4-pro", temperature=0, max_tokens=800,
            response_format={"type": "json_object"}, extra_body={"thinking": {"type": "disabled"}},
            messages=[
                {"role": "system", "content": "你是中文社会科学访谈摘要助手。仅根据输入的访谈纪要，用一段120至200字概括访谈主要讨论了什么、受访者的核心判断及重要条件。不要逐条罗列观点，不要加入输入中没有的信息。只返回JSON：{\"summary\":\"一段话摘要\"}。"},
                {"role": "user", "content": json.dumps({"participant_identity": memo.get("participant_identity"), "interview_topic": memo.get("interview_topic"), "viewpoints": memo.get("viewpoints", [])}, ensure_ascii=False)},
            ],
        )
        summary = str(json.loads(response.choices[0].message.content or "{}").get("summary", "")).strip()
        if not summary:
            raise HTTPException(502, "未生成有效摘要")
        memo["summary"] = summary
        data["updated_at"] = time.time()
        analysis_path(project_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"summary": summary}
    except HTTPException:
        raise
    except Exception as exc:
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
        research=json.loads(research_project_path(body.research_project_id).read_text(encoding='utf-8'))
        analysis=next((a for a in research.get('theme_analyses',[]) if a.get('id')==body.theme_analysis_id),None)
        if not analysis:raise HTTPException(404,'主题分析记录不存在')
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
        except Exception as exc:raise HTTPException(502,str(exc).replace(key,'***')[:400])
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
        research = json.loads(path.read_text(encoding="utf-8"))
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
    except HTTPException:
        raise
    except Exception as exc:
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
    source_project = json.loads(path.read_text(encoding='utf-8'))
    original_analysis = next((a for a in source_project.get('theme_analyses', []) if a.get('id') == analysis.get('id')), {})
    try:
        rehome(analysis, RESEARCH_FILES_DIR, project_id, new_analysis_id, original_analysis.get('finding_reviews', []))
    except (OSError, ValueError) as exc:
        raise HTTPException(409, '核查档案未能完整复制，分析尚未保存') from exc
    analysis["id"] = new_analysis_id
    analysis["saved_at"] = time.time()
    research = json.loads(path.read_text(encoding="utf-8"))
    records = research.setdefault("theme_analyses", [])
    records.append(analysis)
    research["updated_at"] = analysis["saved_at"]
    path.write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"analysis": analysis, "count": len(records)}


@app.put("/api/research-projects/{project_id}/theme-analyses/{analysis_id}/comparison")
def save_theme_comparison(project_id: str, analysis_id: str, body: MaterialComparisonSaveRequest):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    research = json.loads(path.read_text(encoding="utf-8"))
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
    path.write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"analysis": record}


@app.post("/api/research-projects/{project_id}/material-comparisons")
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
    research = json.loads(path.read_text(encoding="utf-8"))
    records = research.setdefault("material_comparisons", [])
    records.append(comparison)
    research["updated_at"] = comparison["saved_at"]
    path.write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"comparison": comparison, "count": len(records)}


@app.put("/api/research-projects/{project_id}/material-comparisons/{record_index}")
def rename_material_comparison(project_id: str, record_index: int, body: MaterialComparisonRenameRequest):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "请填写比较结果名称")
    research = json.loads(path.read_text(encoding="utf-8"))
    records = research.get("material_comparisons", [])
    if record_index < 0 or record_index >= len(records):
        raise HTTPException(404, "比较记录不存在")
    records[record_index]["name"] = name[:80]
    research["updated_at"] = time.time()
    path.write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"comparison": records[record_index]}


@app.delete("/api/research-projects/{project_id}/material-comparisons/{record_index}")
def delete_material_comparison(project_id: str, record_index: int):
    path = research_project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "研究项目不存在")
    research = json.loads(path.read_text(encoding="utf-8"))
    records = research.get("material_comparisons", [])
    if record_index < 0 or record_index >= len(records):
        raise HTTPException(404, "比较记录不存在")
    removed = records.pop(record_index)
    archive = RESEARCH_FILES_DIR / project_id / "deleted_comparisons"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / f"{uuid.uuid4().hex}.json").write_text(json.dumps(removed, ensure_ascii=False, indent=2), encoding="utf-8")
    research["updated_at"] = time.time()
    path.write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8")
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
        meta = json.loads(meta_path.read_text(encoding="utf-8")); code_map = {item.get("id"): item.get("name", "") for item in data.get("codes", [])}; counts = {}
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
register_ai_coding_demo(app,research_project_path,transcript_path,read_metadata,RESEARCH_FILES_DIR)

from finding_review import install as install_finding_review
install_finding_review(app, research_project_path, read_deepseek_key, RESEARCH_FILES_DIR)

if __name__ == "__main__":
    import uvicorn

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex(("127.0.0.1", 8765)) == 0:
            webbrowser.open("http://127.0.0.1:8765")
            raise SystemExit(0)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
