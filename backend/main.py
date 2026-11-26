from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import logging
import math
import os
import shutil
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from ai_service import (
    analyze_subtitle_sentence,
    evaluate_continuous_shadowing_batch,
    evaluate_retelling_attempt,
    evaluate_shadowing_recording,
    test_llm_connection,
)
from auth import (
    auth_status_payload,
    check_and_verify_login,
    clear_session_cookie,
    is_auth_enabled,
    is_request_authenticated,
    set_session_cookie,
)
from db import (
    BASE_DIR,
    MEDIA_DIR,
    db_session,
    get_public_settings,
    get_settings,
    init_db,
    now_iso,
    parse_json_safe,
    save_settings,
)
from lexicon_data import estimate_word_timings, text_to_ipa, word_to_ipa
from pipeline import (
    PIPELINE_TEMPLATE,
    _decode_audio_16k_float32,
    build_srt_content,
    rebind_episode_annotations,
    resolve_ffmpeg_bin,
    run_decomposition_pipeline,
    transcribe_pcm_with_local_whisper,
    transcribe_with_cloud_whisper,
)
from seed_demo import ensure_demo_seeded

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("lingoreel.api")

_ACTIVE_TASKS: dict[int, asyncio.Task[Any]] = {}
MAX_UPLOAD_MB = max(10, int(os.getenv("MAX_UPLOAD_MB", "500")))

PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/status",
    "/api/auth/login",
    "/api/auth/logout",
}


def _decode_subtitle_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _guess_audio_ext(filename: str | None, content_type: str | None) -> str:
    ct = (content_type or "").lower().split(";")[0].strip()
    mime_map = {
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/aac": ".m4a",
        "video/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",
        "video/webm": ".webm",
    }
    if ct in mime_map:
        return mime_map[ct]
    ext = Path(filename or "").suffix.lower()
    if ext in {".webm", ".m4a", ".mp4", ".mp3", ".ogg", ".wav", ".flac"}:
        return ext
    return ".webm"


def _cancel_episode_task(episode_id: int) -> None:
    prev = _ACTIVE_TASKS.pop(episode_id, None)
    if prev and not prev.done():
        prev.cancel()


def _schedule_pipeline(episode_id: int, media_file: Path, subtitle_content: str | None = None) -> None:
    _cancel_episode_task(episode_id)
    task = asyncio.create_task(run_decomposition_pipeline(episode_id, media_file, subtitle_content))
    _ACTIVE_TASKS[episode_id] = task

    def _cleanup(done_task: asyncio.Task[Any]) -> None:
        if _ACTIVE_TASKS.get(episode_id) is done_task:
            _ACTIVE_TASKS.pop(episode_id, None)

    task.add_done_callback(_cleanup)


_SEED_TASK: asyncio.Task[Any] | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _SEED_TASK
    init_db()
    if is_auth_enabled():
        logger.info("Access password protection is ENABLED (APP_ACCESS_PASSWORD is set).")

    async def _run_seed_bg() -> None:
        try:
            await ensure_demo_seeded()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Background demo seeding failed")

    _SEED_TASK = asyncio.create_task(_run_seed_bg())
    try:
        yield
    finally:
        if _SEED_TASK and not _SEED_TASK.done():
            _SEED_TASK.cancel()
        for t in list(_ACTIVE_TASKS.values()):
            if not t.done():
                t.cancel()


app = FastAPI(title="Lingo — Video Language Studio API", version="1.3.3", lifespan=lifespan)


def _sanitize_json_value(val: Any) -> Any:
    if isinstance(val, float):
        return str(val) if not math.isfinite(val) else val
    if isinstance(val, dict):
        return {str(k): _sanitize_json_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize_json_value(v) for v in val]
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    if isinstance(val, Exception):
        return str(val)
    return val


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": _sanitize_json_value(exc.errors())},
    )

_extra_origins = [
    o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_extra_origins,
    allow_origin_regex=(
        r"^https?://(localhost|127\.0\.0\.1|\[::1\]|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_guard_middleware(request: Request, call_next: Any) -> Response:
    if request.method == "OPTIONS" or not is_auth_enabled():
        return await call_next(request)
    path = request.url.path
    if path.startswith("/api/") or path.startswith("/media/"):
        if path not in PUBLIC_API_PATHS and not is_request_authenticated(request):
            return JSONResponse(
                status_code=401,
                content={"detail": "请先输入访问口令解锁 Lingo 学习机。", "auth_required": True},
            )
    return await call_next(request)


# --- Pydantic Models ---
class LoginRequest(BaseModel):
    password: str = Field(..., min_length=1)


class EpisodePatch(BaseModel):
    title: str | None = None
    description: str | None = None
    series_name: str | None = None
    difficulty: str | None = None
    is_completed: bool | None = None
    is_favorite: bool | None = None
    last_position_sec: float | None = Field(default=None, allow_inf_nan=False, ge=0.0)


class SubtitleCreate(BaseModel):
    start_sec: float = Field(..., allow_inf_nan=False)
    end_sec: float = Field(..., allow_inf_nan=False)
    source_text: str = Field(..., min_length=1)
    target_text: str = ""
    ipa: str = ""


class SubtitlePatch(BaseModel):
    source_text: str | None = None
    target_text: str | None = None
    start_sec: float | None = Field(default=None, allow_inf_nan=False)
    end_sec: float | None = Field(default=None, allow_inf_nan=False)
    ipa: str | None = None


class EntryCreate(BaseModel):
    headword: str = Field(..., min_length=1)
    category: str = "短语"
    exam_tags: list[str] = Field(default_factory=lambda: ["自建词"])
    ipa_us: str = ""
    ipa_uk: str = ""
    pos: str = "phrase"
    definition_source: str = ""
    definition_target: str = ""
    usage_pattern: str = ""
    example_source: str = ""
    example_target: str = ""
    episode_id: int | None = None
    overwrite: bool = False


class EntryPatch(BaseModel):
    headword: str | None = None
    category: str | None = None
    exam_tags: list[str] | None = None
    pronunciations: list[dict[str, Any]] | None = None
    definitions: list[dict[str, Any]] | None = None


class RetellingEvaluateRequest(BaseModel):
    mode: str = "keywords"
    transcript_text: str = ""


class SettingsUpdate(BaseModel):
    asr_mode: str | None = None
    asr_base_url: str | None = None
    asr_api_key: str | None = None
    asr_model: str | None = None
    local_whisper_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    default_target_lang: str | None = None
    enable_online_dict_fallback: str | None = None


class TestLLMRequest(BaseModel):
    base_url: str
    api_key: str
    model: str


def _media_url(rel: str | None) -> str:
    if not rel:
        return ""
    return f"/media/{rel.lstrip('/')}"


def _serialize_episode_summary(row: Any, counts: dict[str, int] | None = None) -> dict[str, Any]:
    counts = counts or {}
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "series_name": row["series_name"],
        "episode_number": row["episode_number"],
        "source_lang": row["source_lang"],
        "target_lang": row["target_lang"],
        "difficulty": row["difficulty"],
        "duration_sec": row["duration_sec"],
        "media_kind": row["media_kind"],
        "video_url": _media_url(row["video_path"]),
        "audio_url": _media_url(row["audio_path"]),
        "cover_url": _media_url(row["cover_path"]),
        "status": row["status"],
        "pipeline_steps": parse_json_safe(row["pipeline_steps_json"], PIPELINE_TEMPLATE),
        "error_message": row["error_message"],
        "engine_used": row["engine_used"],
        "is_completed": bool(row["is_completed"]),
        "is_favorite": bool(row["is_favorite"]),
        "last_position_sec": row["last_position_sec"],
        "subtitle_count": counts.get("subtitles", 0),
        "entry_count": counts.get("entries", 0),
        "recording_count": counts.get("recordings", 0),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _is_desktop_mode() -> bool:
    return os.getenv("LINGOREEL_DESKTOP_APP", "").strip() == "1"


def _get_frontend_build_id() -> str:
    marker = FRONTEND_DIST / ".lingo_build_id"
    try:
        if marker.is_file():
            val = marker.read_text(encoding="utf-8").strip()
            if val:
                return val
    except OSError:
        pass
    h = hashlib.sha256()
    found = False
    for name in ("index.html", "lingo-logo.png", "lingo-icon.png"):
        fp = FRONTEND_DIST / name
        if fp.is_file():
            found = True
            h.update(name.encode("utf-8"))
            h.update(b"\x00")
            h.update(fp.read_bytes())
            h.update(b"\x00")
    return h.hexdigest()[:12] if found else ""


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "lingoreel-studio",
        "brand": "Lingo",
        "frontend_dist": str(FRONTEND_DIST),
        "frontend_build": _get_frontend_build_id(),
        "pid": os.getpid(),
        "auth_enabled": is_auth_enabled(),
        "desktop_mode": _is_desktop_mode(),
    }


@app.post("/api/system/shutdown")
async def api_system_shutdown(request: Request) -> dict[str, Any]:
    if not _is_desktop_mode():
        raise HTTPException(status_code=403, detail="仅本地桌面应用模式支持关闭服务。")
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="仅允许本机请求关闭服务。")
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise HTTPException(status_code=403, detail="拒绝跨站关闭服务请求。")

    async def _terminate_soon() -> None:
        await asyncio.sleep(0.35)
        os.kill(os.getpid(), 15)

    asyncio.create_task(_terminate_soon())
    return {"ok": True, "message": "学习机后台服务正在关闭。"}


@app.get("/api/auth/status")
def api_auth_status(request: Request) -> dict[str, Any]:
    payload = auth_status_payload(request)
    payload["desktop_mode"] = _is_desktop_mode()
    return payload


@app.post("/api/auth/login")
def api_auth_login(body: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    check_and_verify_login(request, body.password)
    set_session_cookie(request, response)
    return {"ok": True, "auth_enabled": is_auth_enabled(), "authenticated": True}


@app.post("/api/auth/logout")
def api_auth_logout(response: Response) -> dict[str, Any]:
    clear_session_cookie(response)
    return {"ok": True, "authenticated": False}


# --- Episodes ---
@app.get("/api/episodes")
def list_episodes(
    q: str = Query(default="", description="Keyword filter"),
    difficulty: str = Query(default=""),
    status: str = Query(default=""),
) -> dict[str, Any]:
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM episodes ORDER BY id DESC").fetchall()
        sub_counts = {
            r["episode_id"]: r["cnt"]
            for r in conn.execute("SELECT episode_id, COUNT(*) AS cnt FROM subtitles GROUP BY episode_id").fetchall()
        }
        ent_counts = {
            r["episode_id"]: r["cnt"]
            for r in conn.execute("SELECT episode_id, COUNT(*) AS cnt FROM episode_entries GROUP BY episode_id").fetchall()
        }
        rec_counts = {
            r["episode_id"]: r["cnt"]
            for r in conn.execute("SELECT episode_id, COUNT(*) AS cnt FROM recordings GROUP BY episode_id").fetchall()
        }

    items = []
    q_low = q.strip().lower()
    for r in rows:
        if difficulty and r["difficulty"].upper() != difficulty.upper():
            continue
        if status and r["status"] != status:
            continue
        if q_low:
            hay = f"{r['title']} {r['description']} {r['series_name']}".lower()
            if q_low not in hay:
                continue
        items.append(
            _serialize_episode_summary(
                r,
                {
                    "subtitles": sub_counts.get(r["id"], 0),
                    "entries": ent_counts.get(r["id"], 0),
                    "recordings": rec_counts.get(r["id"], 0),
                },
            )
        )
    return {"episodes": items, "total": len(items)}


@app.post("/api/episodes/upload")
async def upload_episode(
    media_file: UploadFile = File(...),
    subtitle_file: UploadFile | None = File(default=None),
    title: str = Form(default=""),
    series_name: str = Form(default="自建资料库"),
    difficulty: str = Form(default="B1"),
    description: str = Form(default=""),
    source_lang: str = Form(default="en"),
) -> dict[str, Any]:
    if not media_file.filename:
        raise HTTPException(status_code=400, detail="请上传视频或音频文件。")

    orig_name = Path(media_file.filename).name
    suffix = Path(orig_name).suffix.lower() or ".mp4"
    allowed = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".mp3", ".wav", ".m4a", ".ogg", ".flac"}
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的媒体格式：{suffix}（支持 MP4/MOV/WebM/MKV/MP3/WAV/M4A）")

    ep_title = (
        title.strip()
        or Path(orig_name).stem.replace("_", " ").replace("-", " ").strip()
        or Path(orig_name).stem.strip()
        or "未命名语料"
    )
    now = now_iso()

    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO episodes (
                title, description, series_name, episode_number, source_lang, target_lang,
                difficulty, status, pipeline_steps_json, created_at, updated_at
            ) VALUES (?, ?, ?, 1, ?, 'zh-CN', ?, 'queued', ?, ?, ?)
            """,
            (
                ep_title,
                description.strip(),
                series_name.strip() or "自建资料库",
                source_lang.strip() or "en",
                difficulty.strip() or "B1",
                json.dumps(PIPELINE_TEMPLATE, ensure_ascii=False),
                now,
                now,
            ),
        )
        ep_id = int(cur.lastrowid)

    ep_dir = MEDIA_DIR / f"ep_{ep_id}"
    ep_dir.mkdir(parents=True, exist_ok=True)
    saved_media = ep_dir / f"source{suffix}"

    # Stream uploaded media to disk in 1MB chunks to stay friendly on 1-2GB cloud VPS
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    try:
        with saved_media.open("wb") as out_f:
            while True:
                chunk = await media_file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过单次上传上限（最大 {MAX_UPLOAD_MB} MB）。",
                    )
                out_f.write(chunk)
    except Exception:
        shutil.rmtree(ep_dir, ignore_errors=True)
        with db_session() as conn:
            conn.execute("DELETE FROM episodes WHERE id = ?", (ep_id,))
        raise

    subtitle_text: str | None = None
    if subtitle_file and subtitle_file.filename:
        raw_sub = await subtitle_file.read()
        subtitle_text = _decode_subtitle_bytes(raw_sub)
        if subtitle_text:
            (ep_dir / "uploaded.srt").write_text(subtitle_text, encoding="utf-8")

    _schedule_pipeline(ep_id, saved_media, subtitle_content=subtitle_text)

    with db_session() as conn:
        row = conn.execute("SELECT * FROM episodes WHERE id = ?", (ep_id,)).fetchone()
    return {"episode": _serialize_episode_summary(row)}


@app.get("/api/episodes/{episode_id}/status")
def get_episode_status(episode_id: int) -> dict[str, Any]:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Episode not found")
        sub_cnt = conn.execute("SELECT COUNT(*) FROM subtitles WHERE episode_id = ?", (episode_id,)).fetchone()[0]
        ent_cnt = conn.execute("SELECT COUNT(*) FROM episode_entries WHERE episode_id = ?", (episode_id,)).fetchone()[0]
    return {
        "id": row["id"],
        "title": row["title"],
        "status": row["status"],
        "pipeline_steps": parse_json_safe(row["pipeline_steps_json"], PIPELINE_TEMPLATE),
        "error_message": row["error_message"],
        "engine_used": row["engine_used"],
        "duration_sec": row["duration_sec"],
        "subtitle_count": sub_cnt,
        "entry_count": ent_cnt,
    }


@app.get("/api/episodes/{episode_id}")
def get_episode_detail(episode_id: int) -> dict[str, Any]:
    with db_session() as conn:
        ep = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")

        sub_rows = conn.execute(
            "SELECT * FROM subtitles WHERE episode_id = ? ORDER BY seq_index ASC", (episode_id,)
        ).fetchall()

        rec_rows = conn.execute(
            "SELECT * FROM recordings WHERE episode_id = ? ORDER BY id DESC", (episode_id,)
        ).fetchall()
        recs_by_sub: dict[int, list[dict[str, Any]]] = {}
        for r in rec_rows:
            recs_by_sub.setdefault(r["subtitle_id"], []).append(
                {
                    "id": r["id"],
                    "subtitle_id": r["subtitle_id"],
                    "audio_url": _media_url(r["audio_path"]),
                    "duration_sec": r["duration_sec"],
                    "feedback": parse_json_safe(r["feedback_json"], {}),
                    "created_at": r["created_at"],
                }
            )

        entry_rows = conn.execute(
            """
            SELECT e.*, ee.forms_json, ee.occurrence_count
            FROM episode_entries ee
            JOIN entries e ON e.id = ee.entry_id
            WHERE ee.episode_id = ?
            ORDER BY
                CASE e.category
                    WHEN '短语动词' THEN 1
                    WHEN '惯用表达' THEN 2
                    WHEN '搭配' THEN 3
                    WHEN '短语' THEN 4
                    ELSE 5
                END,
                ee.occurrence_count DESC,
                e.headword ASC
            """,
            (episode_id,),
        ).fetchall()

        occ_rows = conn.execute(
            """
            SELECT so.entry_id, so.subtitle_id, so.matched_form, s.seq_index, s.start_sec, s.end_sec, s.source_text
            FROM subtitle_occurrences so
            JOIN subtitles s ON s.id = so.subtitle_id
            WHERE so.episode_id = ?
            ORDER BY s.seq_index ASC
            """,
            (episode_id,),
        ).fetchall()
        occ_by_entry: dict[int, list[dict[str, Any]]] = {}
        occ_by_sub: dict[int, list[int]] = {}
        for o in occ_rows:
            occ_by_entry.setdefault(o["entry_id"], []).append(
                {
                    "subtitle_id": o["subtitle_id"],
                    "seq_index": o["seq_index"],
                    "start_sec": o["start_sec"],
                    "end_sec": o["end_sec"],
                    "matched_form": o["matched_form"],
                    "source_text": o["source_text"],
                }
            )
            occ_by_sub.setdefault(o["subtitle_id"], []).append(o["entry_id"])

        # Cross-episode counts per entry
        entry_ids = [r["id"] for r in entry_rows]
        cross_counts: dict[int, int] = {}
        if entry_ids:
            placeholders = ",".join("?" for _ in entry_ids)
            c_rows = conn.execute(
                f"SELECT entry_id, COUNT(DISTINCT episode_id) AS ep_cnt FROM subtitle_occurrences WHERE entry_id IN ({placeholders}) GROUP BY entry_id",
                entry_ids,
            ).fetchall()
            cross_counts = {r["entry_id"]: r["ep_cnt"] for r in c_rows}

        retelling_rows = conn.execute(
            "SELECT * FROM retelling_sessions WHERE episode_id = ? ORDER BY id DESC LIMIT 5",
            (episode_id,),
        ).fetchall()

    subtitles = [
        {
            "id": s["id"],
            "episode_id": s["episode_id"],
            "seq_index": s["seq_index"],
            "start_sec": s["start_sec"],
            "end_sec": s["end_sec"],
            "source_text": s["source_text"],
            "source_html": s["source_html"] or s["source_text"],
            "target_text": s["target_text"],
            "ipa": s["ipa"],
            "words": parse_json_safe(s["words_json"], []),
            "is_favorite": bool(s["is_favorite"]),
            "ai_note": parse_json_safe(s["ai_note_json"], None),
            "entry_ids": list(dict.fromkeys(occ_by_sub.get(s["id"], []))),
            "recordings": recs_by_sub.get(s["id"], []),
        }
        for s in sub_rows
    ]

    entries = [
        {
            "id": e["id"],
            "headword": e["headword"],
            "lemma_key": e["lemma_key"],
            "category": e["category"],
            "exam_tags": parse_json_safe(e["exam_tags_json"], []),
            "pronunciations": parse_json_safe(e["pronunciations_json"], []),
            "definitions": parse_json_safe(e["definitions_json"], []),
            "forms": parse_json_safe(e["forms_json"], []),
            "occurrence_count": e["occurrence_count"],
            "cross_episode_count": cross_counts.get(e["id"], 1),
            "is_bookmarked": bool(e["is_bookmarked"]),
            "occurrences": occ_by_entry.get(e["id"], []),
        }
        for e in entry_rows
    ]

    summary = _serialize_episode_summary(
        ep,
        {"subtitles": len(subtitles), "entries": len(entries), "recordings": len(rec_rows)},
    )
    summary["retelling_guide"] = parse_json_safe(ep["retelling_guide_json"], {})
    summary["retelling_history"] = [
        {
            "id": r["id"],
            "mode": r["mode"],
            "transcript_text": r["transcript_text"],
            "evaluation": parse_json_safe(r["evaluation_json"], {}),
            "created_at": r["created_at"],
        }
        for r in retelling_rows
    ]

    return {"episode": summary, "subtitles": subtitles, "entries": entries}


@app.post("/api/episodes/{episode_id}/reprocess")
async def reprocess_episode(
    episode_id: int,
    subtitle_file: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    with db_session() as conn:
        ep = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")
        media_rel = ep["video_path"] or ep["audio_path"]
        if not media_rel:
            raise HTTPException(status_code=400, detail="找不到该篇目的原始媒体文件")

    media_abs = MEDIA_DIR / media_rel
    if not media_abs.exists():
        raise HTTPException(status_code=404, detail="磁盘上的媒体文件已丢失")

    ep_dir = MEDIA_DIR / f"ep_{episode_id}"
    sub_text: str | None = None
    if subtitle_file and subtitle_file.filename:
        raw = await subtitle_file.read()
        sub_text = _decode_subtitle_bytes(raw)
        if not sub_text.strip():
            raise HTTPException(status_code=400, detail="上传的字幕文件为空，请选择有效的 SRT/VTT 文件。")
        (ep_dir / "uploaded.srt").write_text(sub_text, encoding="utf-8")
    else:
        for cand in (ep_dir / "uploaded.srt", ep_dir / "source.srt"):
            if cand.exists():
                sub_text = _decode_subtitle_bytes(cand.read_bytes())
                break

    _schedule_pipeline(episode_id, media_abs, subtitle_content=sub_text)
    return {"ok": True, "episode_id": episode_id, "status": "processing"}


@app.patch("/api/episodes/{episode_id}")
def patch_episode(episode_id: int, body: EpisodePatch) -> dict[str, Any]:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    with db_session() as conn:
        ep = conn.execute("SELECT id FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")
        cols = []
        vals: list[Any] = []
        for k, v in updates.items():
            cols.append(f"{k} = ?")
            vals.append(int(v) if isinstance(v, bool) else v)
        cols.append("updated_at = ?")
        vals.append(now_iso())
        vals.append(episode_id)
        conn.execute(f"UPDATE episodes SET {', '.join(cols)} WHERE id = ?", vals)
        row = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
    return {"episode": _serialize_episode_summary(row)}


@app.delete("/api/episodes/{episode_id}")
def delete_episode(episode_id: int) -> dict[str, Any]:
    _cancel_episode_task(episode_id)
    with db_session() as conn:
        ep = conn.execute("SELECT id FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")
        conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
    ep_dir = MEDIA_DIR / f"ep_{episode_id}"
    if ep_dir.exists():
        shutil.rmtree(ep_dir, ignore_errors=True)
    return {"ok": True, "deleted_id": episode_id}


@app.get("/api/episodes/{episode_id}/export/srt")
def export_episode_srt(episode_id: int, bilingual: bool = Query(default=True)) -> Response:
    with db_session() as conn:
        ep = conn.execute("SELECT title FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")
        subs = [
            dict(r)
            for r in conn.execute(
                "SELECT start_sec, end_sec, source_text, target_text FROM subtitles WHERE episode_id = ? ORDER BY seq_index ASC",
                (episode_id,),
            ).fetchall()
        ]
    srt_text = build_srt_content(subs, bilingual=bilingual)
    filename = f"episode_{episode_id}_{'bilingual' if bilingual else 'en'}.srt"
    return PlainTextResponse(
        content=srt_text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/episodes/{episode_id}/export/json")
def export_episode_json(episode_id: int) -> Response:
    detail = get_episode_detail(episode_id)
    raw = json.dumps(detail, ensure_ascii=False, indent=2)
    return Response(
        content=raw,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="episode_{episode_id}_study_pack.json"'},
    )


# --- Subtitles ---
def _resequence_subtitles(conn: Any, episode_id: int) -> None:
    rows = conn.execute(
        "SELECT id FROM subtitles WHERE episode_id = ? ORDER BY start_sec ASC, id ASC",
        (episode_id,),
    ).fetchall()
    for idx, r in enumerate(rows, start=1):
        conn.execute("UPDATE subtitles SET seq_index = ? WHERE id = ?", (idx, r["id"]))


@app.post("/api/episodes/{episode_id}/subtitles")
def create_subtitle(episode_id: int, body: SubtitleCreate) -> dict[str, Any]:
    src = body.source_text.strip()
    if not src:
        raise HTTPException(status_code=400, detail="英文原句不能为空。")
    start_s = float(body.start_sec)
    end_s = float(body.end_sec)
    if not math.isfinite(start_s) or not math.isfinite(end_s) or start_s < 0 or end_s <= start_s:
        raise HTTPException(status_code=400, detail="字幕时间轴无效：开始时间不能小于 0，且结束时间必须大于开始时间。")

    with db_session() as conn:
        ep = conn.execute("SELECT id FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")
        ipa_str = body.ipa.strip() or text_to_ipa(src)
        words = estimate_word_timings(src, start_s, end_s)
        cur = conn.execute(
            """
            INSERT INTO subtitles (
                episode_id, seq_index, start_sec, end_sec,
                source_text, source_html, target_text, ipa, words_json, is_favorite
            ) VALUES (?, 9999, ?, ?, ?, '', ?, ?, ?, 0)
            """,
            (
                episode_id,
                start_s,
                end_s,
                src,
                body.target_text.strip(),
                ipa_str,
                json.dumps(words, ensure_ascii=False),
            ),
        )
        new_id = int(cur.lastrowid)
        _resequence_subtitles(conn, episode_id)

    rebind_episode_annotations(episode_id)
    return {"id": new_id, "episode_id": episode_id}


@app.delete("/api/subtitles/{subtitle_id}")
def delete_subtitle(subtitle_id: int) -> dict[str, Any]:
    with db_session() as conn:
        sub = conn.execute("SELECT episode_id FROM subtitles WHERE id = ?", (subtitle_id,)).fetchone()
        if not sub:
            raise HTTPException(status_code=404, detail="Subtitle not found")
        ep_id = int(sub["episode_id"])
        conn.execute("DELETE FROM subtitles WHERE id = ?", (subtitle_id,))
        _resequence_subtitles(conn, ep_id)
    rebind_episode_annotations(ep_id)
    return {"ok": True, "deleted_id": subtitle_id}


@app.patch("/api/subtitles/{subtitle_id}")
def patch_subtitle(subtitle_id: int, body: SubtitlePatch) -> dict[str, Any]:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    source_changed = False
    with db_session() as conn:
        sub = conn.execute("SELECT * FROM subtitles WHERE id = ?", (subtitle_id,)).fetchone()
        if not sub:
            raise HTTPException(status_code=404, detail="Subtitle not found")
        ep_id = int(sub["episode_id"])

        if "source_text" in updates:
            cleaned_src = str(updates["source_text"]).strip()
            if not cleaned_src:
                raise HTTPException(status_code=400, detail="英文原句不能为空。")
            updates["source_text"] = cleaned_src
            source_changed = cleaned_src != str(sub["source_text"] or "").strip()

        if "target_text" in updates:
            updates["target_text"] = str(updates["target_text"]).strip()

        new_source = updates.get("source_text", sub["source_text"])
        new_start = float(updates.get("start_sec", sub["start_sec"]))
        new_end = float(updates.get("end_sec", sub["end_sec"]))
        if not math.isfinite(new_start) or not math.isfinite(new_end) or new_start < 0 or new_end <= new_start:
            raise HTTPException(status_code=400, detail="字幕时间轴无效：开始时间不能小于 0，且结束时间必须大于开始时间。")

        if "start_sec" in updates:
            updates["start_sec"] = new_start
        if "end_sec" in updates:
            updates["end_sec"] = new_end

        if source_changed and ("ipa" not in updates or not str(updates.get("ipa", "")).strip()):
            updates["ipa"] = text_to_ipa(new_source)
        elif "ipa" in updates:
            updates["ipa"] = str(updates["ipa"]).strip()

        if source_changed or "start_sec" in updates or "end_sec" in updates:
            updates["words_json"] = json.dumps(
                estimate_word_timings(new_source, new_start, new_end), ensure_ascii=False
            )
            if source_changed:
                updates["ai_note_json"] = ""

        cols = [f"{k} = ?" for k in updates.keys()]
        vals = list(updates.values()) + [subtitle_id]
        conn.execute(f"UPDATE subtitles SET {', '.join(cols)} WHERE id = ?", vals)
        if "start_sec" in updates:
            _resequence_subtitles(conn, ep_id)

    if source_changed:
        rebind_episode_annotations(ep_id)

    with db_session() as conn:
        row = conn.execute("SELECT * FROM subtitles WHERE id = ?", (subtitle_id,)).fetchone()
    return {
        "subtitle": {
            "id": row["id"],
            "episode_id": row["episode_id"],
            "seq_index": row["seq_index"],
            "start_sec": row["start_sec"],
            "end_sec": row["end_sec"],
            "source_text": row["source_text"],
            "source_html": row["source_html"],
            "target_text": row["target_text"],
            "ipa": row["ipa"],
            "is_favorite": bool(row["is_favorite"]),
        }
    }


@app.post("/api/subtitles/{subtitle_id}/favorite")
def toggle_subtitle_favorite(subtitle_id: int) -> dict[str, Any]:
    with db_session() as conn:
        row = conn.execute("SELECT is_favorite FROM subtitles WHERE id = ?", (subtitle_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Subtitle not found")
        new_val = 0 if row["is_favorite"] else 1
        conn.execute("UPDATE subtitles SET is_favorite = ? WHERE id = ?", (new_val, subtitle_id))
    return {"id": subtitle_id, "is_favorite": bool(new_val)}


@app.post("/api/subtitles/{subtitle_id}/ai-analyze")
async def ai_analyze_subtitle(subtitle_id: int, force: bool = Query(default=False)) -> dict[str, Any]:
    try:
        note = await analyze_subtitle_sentence(subtitle_id, force_refresh=force)
        return {"subtitle_id": subtitle_id, "ai_note": note}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# --- Entries & Personal Vocabulary Deck ---
@app.post("/api/entries")
def create_entry(body: EntryCreate) -> dict[str, Any]:
    hw = body.headword.strip()
    if not hw:
        raise HTTPException(status_code=400, detail="英文词条不能为空。")
    lkey = hw.lower()
    ipa_us = body.ipa_us.strip() or word_to_ipa(hw)
    ipa_uk = body.ipa_uk.strip() or ipa_us
    pronunciations = [
        {"accent_type": "US", "ipa": ipa_us, "is_primary": True},
        {"accent_type": "UK", "ipa": ipa_uk, "is_primary": False},
    ]
    definitions = [
        {
            "pos": body.pos.strip() or "phrase",
            "definition_source": body.definition_source.strip() or hw,
            "definition_target": body.definition_target.strip() or f"用户自建释义：{hw}",
            "usage_pattern": body.usage_pattern.strip(),
            "examples": (
                [{"example_source": body.example_source.strip(), "example_target": body.example_target.strip()}]
                if body.example_source.strip()
                else []
            ),
        }
    ]
    with db_session() as conn:
        existing = conn.execute("SELECT id, headword FROM entries WHERE lemma_key = ?", (lkey,)).fetchone()
        if existing:
            if not body.overwrite:
                raise HTTPException(
                    status_code=409,
                    detail=f"词条「{existing['headword']}」已存在于词典中，无需重复新增（如需覆盖请确认覆盖选项）。",
                )
            entry_id = int(existing["id"])
            conn.execute(
                "UPDATE entries SET headword=?, category=?, exam_tags_json=?, pronunciations_json=?, definitions_json=? WHERE id=?",
                (
                    hw,
                    body.category,
                    json.dumps(body.exam_tags, ensure_ascii=False),
                    json.dumps(pronunciations, ensure_ascii=False),
                    json.dumps(definitions, ensure_ascii=False),
                    entry_id,
                ),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO entries (
                    headword, lemma_key, category, language_code, target_language_code,
                    exam_tags_json, pronunciations_json, definitions_json, is_bookmarked, created_at
                ) VALUES (?, ?, ?, 'en', 'zh-CN', ?, ?, ?, 1, ?)
                """,
                (
                    hw,
                    lkey,
                    body.category,
                    json.dumps(body.exam_tags, ensure_ascii=False),
                    json.dumps(pronunciations, ensure_ascii=False),
                    json.dumps(definitions, ensure_ascii=False),
                    now_iso(),
                ),
            )
            entry_id = int(cur.lastrowid)

    if body.episode_id:
        rebind_episode_annotations(body.episode_id)
    return {"id": entry_id, "headword": hw}


@app.patch("/api/entries/{entry_id}")
def patch_entry(entry_id: int, body: EntryPatch) -> dict[str, Any]:
    affected_ep_ids: list[int] = []
    with db_session() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Entry not found")
        cols: list[str] = []
        vals: list[Any] = []
        headword_changed = False
        if body.headword is not None:
            cleaned_hw = body.headword.strip()
            if not cleaned_hw:
                raise HTTPException(status_code=400, detail="英文词条不能为空。")
            new_lkey = cleaned_hw.lower()
            conflict = conn.execute(
                "SELECT id FROM entries WHERE lemma_key = ? AND id != ?", (new_lkey, entry_id)
            ).fetchone()
            if conflict:
                raise HTTPException(status_code=409, detail=f"词条「{cleaned_hw}」已存在。")
            cols.append("headword = ?")
            vals.append(cleaned_hw)
            cols.append("lemma_key = ?")
            vals.append(new_lkey)
            headword_changed = cleaned_hw.lower() != row["lemma_key"]
        if body.category is not None:
            cols.append("category = ?")
            vals.append(body.category)
        if body.exam_tags is not None:
            cols.append("exam_tags_json = ?")
            vals.append(json.dumps(body.exam_tags, ensure_ascii=False))
        if body.pronunciations is not None:
            cols.append("pronunciations_json = ?")
            vals.append(json.dumps(body.pronunciations, ensure_ascii=False))
        if body.definitions is not None:
            cols.append("definitions_json = ?")
            vals.append(json.dumps(body.definitions, ensure_ascii=False))
        if cols:
            vals.append(entry_id)
            conn.execute(f"UPDATE entries SET {', '.join(cols)} WHERE id = ?", vals)
        if headword_changed:
            affected_ep_ids = [
                int(r["id"]) for r in conn.execute("SELECT id FROM episodes WHERE status = 'ready'").fetchall()
            ]
    for ep_id in affected_ep_ids:
        rebind_episode_annotations(ep_id)
    return {"ok": True, "id": entry_id}


@app.post("/api/entries/{entry_id}/bookmark")
def toggle_entry_bookmark(entry_id: int) -> dict[str, Any]:
    with db_session() as conn:
        row = conn.execute("SELECT is_bookmarked FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Entry not found")
        new_val = 0 if row["is_bookmarked"] else 1
        conn.execute("UPDATE entries SET is_bookmarked = ? WHERE id = ?", (new_val, entry_id))
    return {"id": entry_id, "is_bookmarked": bool(new_val)}


@app.get("/api/entries/{entry_id}/occurrences")
def get_entry_occurrences(entry_id: int) -> dict[str, Any]:
    with db_session() as conn:
        entry = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        rows = conn.execute(
            """
            SELECT so.episode_id, e.title AS episode_title, e.difficulty,
                   so.subtitle_id, s.seq_index, s.start_sec, s.end_sec,
                   s.source_text, s.target_text, so.matched_form
            FROM subtitle_occurrences so
            JOIN episodes e ON e.id = so.episode_id
            JOIN subtitles s ON s.id = so.subtitle_id
            WHERE so.entry_id = ?
            ORDER BY so.episode_id ASC, s.seq_index ASC
            """,
            (entry_id,),
        ).fetchall()
    return {
        "entry_id": entry_id,
        "headword": entry["headword"],
        "occurrences": [dict(r) for r in rows],
    }


@app.get("/api/vocab-deck")
def get_vocab_deck() -> dict[str, Any]:
    with db_session() as conn:
        entries_rows = conn.execute(
            "SELECT * FROM entries WHERE is_bookmarked = 1 ORDER BY id DESC"
        ).fetchall()
        fav_subs_rows = conn.execute(
            """
            SELECT s.*, e.title AS episode_title
            FROM subtitles s
            JOIN episodes e ON e.id = s.episode_id
            WHERE s.is_favorite = 1
            ORDER BY s.id DESC
            """
        ).fetchall()

        entry_items = []
        for e in entries_rows:
            occ = conn.execute(
                """
                SELECT so.episode_id, ep.title AS episode_title, so.subtitle_id, s.seq_index, s.start_sec, s.source_text
                FROM subtitle_occurrences so
                JOIN episodes ep ON ep.id = so.episode_id
                JOIN subtitles s ON s.id = so.subtitle_id
                WHERE so.entry_id = ?
                ORDER BY so.episode_id ASC, s.seq_index ASC
                LIMIT 5
                """,
                (e["id"],),
            ).fetchall()
            entry_items.append(
                {
                    "id": e["id"],
                    "headword": e["headword"],
                    "category": e["category"],
                    "exam_tags": parse_json_safe(e["exam_tags_json"], []),
                    "pronunciations": parse_json_safe(e["pronunciations_json"], []),
                    "definitions": parse_json_safe(e["definitions_json"], []),
                    "is_bookmarked": True,
                    "occurrences": [dict(o) for o in occ],
                }
            )

        fav_subs = [
            {
                "id": s["id"],
                "episode_id": s["episode_id"],
                "episode_title": s["episode_title"],
                "seq_index": s["seq_index"],
                "start_sec": s["start_sec"],
                "end_sec": s["end_sec"],
                "source_text": s["source_text"],
                "target_text": s["target_text"],
                "ipa": s["ipa"],
            }
            for s in fav_subs_rows
        ]
    return {"entries": entry_items, "favorite_subtitles": fav_subs}


def _tsv_cell(val: Any) -> str:
    return " ".join(str(val or "").replace("\t", " ").splitlines()).strip()


def _csv_cell(val: Any) -> str:
    s = str(val or "")
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


@app.get("/api/vocab-deck/export")
def export_vocab_deck(fmt: str = Query(default="csv", alias="format")) -> Response:
    deck = get_vocab_deck()
    entries = deck["entries"]
    if fmt.lower() == "anki":
        lines = []
        for e in entries:
            ipa = (e["pronunciations"][0]["ipa"] if e["pronunciations"] else "")
            d0 = e["definitions"][0] if e["definitions"] else {}
            front = _tsv_cell(f"{e['headword']} {ipa}")
            ex = d0.get("examples", [{}])[0].get("example_source", "") if d0.get("examples") else ""
            back_raw = f"[{e['category']}] {d0.get('definition_target', '')} — {d0.get('definition_source', '')}"
            if ex:
                back_raw += f" | 例句: {ex}"
            back = _tsv_cell(back_raw)
            lines.append(f"{front}\t{back}")
        return PlainTextResponse(
            content="\n".join(lines) + ("\n" if lines else ""),
            media_type="text/tab-separated-values; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="lingoreel_anki_deck.tsv"'},
        )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["词条", "类别", "美式音标", "标签", "中文释义", "英文释义", "用法搭配", "示例原句"])
    for e in entries:
        ipa = e["pronunciations"][0]["ipa"] if e["pronunciations"] else ""
        d0 = e["definitions"][0] if e["definitions"] else {}
        ex = d0.get("examples", [{}])[0].get("example_source", "") if d0.get("examples") else ""
        writer.writerow(
            [
                _csv_cell(e["headword"]),
                _csv_cell(e["category"]),
                _csv_cell(ipa),
                _csv_cell(" / ".join(e["exam_tags"])),
                _csv_cell(d0.get("definition_target", "")),
                _csv_cell(d0.get("definition_source", "")),
                _csv_cell(d0.get("usage_pattern", "")),
                _csv_cell(ex),
            ]
        )
    # Prepend UTF-8 BOM for Excel friendliness
    return Response(
        content=("\ufeff" + buf.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="lingoreel_vocab_deck.csv"'},
    )


# --- Shadowing Recordings & Retelling ---
@app.post("/api/episodes/{episode_id}/recordings")
async def upload_recording(
    episode_id: int,
    subtitle_id: int = Form(...),
    audio_file: UploadFile = File(...),
) -> dict[str, Any]:
    with db_session() as conn:
        sub = conn.execute(
            "SELECT id FROM subtitles WHERE id = ? AND episode_id = ?",
            (subtitle_id, episode_id),
        ).fetchone()
        if not sub:
            raise HTTPException(status_code=404, detail="目标篇目中不存在该字幕句。")

    raw_bytes = await audio_file.read()
    if len(raw_bytes) < 64:
        raise HTTPException(status_code=400, detail="录音文件为空或过短，请重新录制。")

    rec_dir = MEDIA_DIR / f"ep_{episode_id}" / "recordings"
    rec_dir.mkdir(parents=True, exist_ok=True)
    ext = _guess_audio_ext(audio_file.filename, audio_file.content_type)
    stamp = now_iso().replace(":", "").replace("-", "").replace(".", "") + "_" + uuid.uuid4().hex[:6]
    out_file = rec_dir / f"sub_{subtitle_id}_{stamp}{ext}"
    out_file.write_bytes(raw_bytes)
    try:
        result = await evaluate_shadowing_recording(episode_id, subtitle_id, out_file)
        return {"recording": result}
    except ValueError as exc:
        out_file.unlink(missing_ok=True)
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=status, detail=msg)


@app.post("/api/episodes/{episode_id}/recordings/batch")
async def upload_continuous_recordings_batch(
    episode_id: int,
    segments_json: str = Form(...),
    audio_file: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        raw_segments = json.loads(segments_json)
    except Exception:
        raise HTTPException(status_code=400, detail="segments_json 格式无效，必须是 JSON 数组。")
    if not isinstance(raw_segments, list) or not raw_segments or len(raw_segments) > 200:
        raise HTTPException(status_code=400, detail="跟读分段列表不能为空且不得超过 200 句。")

    cleaned_segments: list[dict[str, Any]] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="分段项格式无效。")
        if "subtitle_id" not in item or "start_sec" not in item or "end_sec" not in item:
            raise HTTPException(status_code=400, detail="分段缺少合法的 subtitle_id / start_sec / end_sec。")
        raw_sid = item["subtitle_id"]
        if isinstance(raw_sid, bool):
            raise HTTPException(status_code=400, detail="subtitle_id 必须为正整数。")
        if isinstance(raw_sid, int):
            sid = raw_sid
        elif isinstance(raw_sid, str) and raw_sid.strip().isdigit():
            sid = int(raw_sid.strip())
        else:
            raise HTTPException(status_code=400, detail="subtitle_id 必须为正整数。")
        if sid <= 0:
            raise HTTPException(status_code=400, detail="subtitle_id 必须为正整数。")
        try:
            st = float(item["start_sec"])
            ed = float(item["end_sec"])
        except (TypeError, ValueError, OverflowError):
            raise HTTPException(status_code=400, detail="分段缺少合法的 start_sec / end_sec。")
        if isinstance(item["start_sec"], bool) or isinstance(item["end_sec"], bool):
            raise HTTPException(status_code=400, detail="分段起止时间不能为布尔值。")
        if not (math.isfinite(st) and math.isfinite(ed)) or st < 0 or ed <= st:
            raise HTTPException(status_code=400, detail="分段起止时间无效（需为有限数值且结束时间大于开始时间）。")
        cleaned_segments.append({"subtitle_id": sid, "start_sec": st, "end_sec": ed})

    # Verify episode and all subtitle_ids exist BEFORE touching the filesystem
    unique_sids = list({s["subtitle_id"] for s in cleaned_segments})
    with db_session() as conn:
        ep = conn.execute("SELECT id FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")
        placeholders = ",".join("?" for _ in unique_sids)
        rows = conn.execute(
            f"SELECT id FROM subtitles WHERE episode_id = ? AND id IN ({placeholders})",
            (episode_id, *unique_sids),
        ).fetchall()
        found_ids = {int(r["id"]) for r in rows}
        missing = [sid for sid in unique_sids if sid not in found_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"目标篇目中不存在字幕句：{missing[0]}")

    raw_bytes = await audio_file.read()
    if len(raw_bytes) < 64:
        raise HTTPException(status_code=400, detail="连续录音文件为空或过短，请重新录制。")

    rec_dir = MEDIA_DIR / f"ep_{episode_id}" / "recordings"
    rec_dir.mkdir(parents=True, exist_ok=True)
    ext = _guess_audio_ext(audio_file.filename, audio_file.content_type)
    raw_file = rec_dir / f"tmp_batch_{uuid.uuid4().hex[:10]}{ext}"
    raw_file.write_bytes(raw_bytes)
    try:
        return await evaluate_continuous_shadowing_batch(episode_id, cleaned_segments, raw_file)
    except ValueError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() or "不存在" in msg else 400
        raise HTTPException(status_code=status, detail=msg)
    finally:
        raw_file.unlink(missing_ok=True)


@app.delete("/api/recordings/{recording_id}")
def delete_recording(recording_id: int) -> dict[str, Any]:
    with db_session() as conn:
        row = conn.execute("SELECT audio_path FROM recordings WHERE id = ?", (recording_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recording not found")
        conn.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
    abs_f = MEDIA_DIR / row["audio_path"]
    if abs_f.exists():
        abs_f.unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/episodes/{episode_id}/retelling/evaluate")
async def retelling_evaluate(episode_id: int, body: RetellingEvaluateRequest) -> dict[str, Any]:
    if not body.transcript_text.strip():
        raise HTTPException(status_code=400, detail="请先输入或口述转写你的复述内容。")
    try:
        res = await evaluate_retelling_attempt(episode_id, body.mode, body.transcript_text)
        return res
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/episodes/{episode_id}/retelling/audio")
async def retelling_evaluate_audio(
    episode_id: int,
    mode: str = Form(default="keywords"),
    audio_file: UploadFile = File(...),
) -> dict[str, Any]:
    with db_session() as conn:
        ep = conn.execute("SELECT id FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")

    raw_bytes = await audio_file.read()
    if len(raw_bytes) < 64:
        raise HTTPException(status_code=400, detail="口述录音为空或过短，请重新录制。")

    ret_dir = MEDIA_DIR / f"ep_{episode_id}" / "retelling"
    ret_dir.mkdir(parents=True, exist_ok=True)
    ext = _guess_audio_ext(audio_file.filename, audio_file.content_type)
    stamp = now_iso().replace(":", "").replace("-", "").replace(".", "") + "_" + uuid.uuid4().hex[:6]
    raw_file = ret_dir / f"retell_{stamp}{ext}"
    mp3_file = ret_dir / f"retell_{stamp}.mp3"

    try:
        raw_file.write_bytes(raw_bytes)
        try:
            pcm = await asyncio.to_thread(_decode_audio_16k_float32, raw_file)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"口述录音文件无法解码，请检查麦克风后重录（{str(exc)[:100]}）。",
            )

        settings = get_settings()
        transcript = ""
        if settings.get("asr_api_key", "").strip():
            await asyncio.to_thread(
                subprocess.run,
                [
                    resolve_ffmpeg_bin(), "-y", "-v", "error", "-i", str(raw_file),
                    "-vn", "-ar", "16000", "-ac", "1", "-acodec", "libmp3lame", "-b:a", "96k",
                    str(mp3_file),
                ],
                capture_output=True,
                timeout=30,
            )
            target_audio = mp3_file if mp3_file.exists() else raw_file
            try:
                segs = await transcribe_with_cloud_whisper(target_audio, settings, "en")
                transcript = " ".join(s["source_text"] for s in segs).strip()
            except Exception as exc:
                logger.warning("Cloud Whisper retelling failed, falling back to local Whisper: %s", exc)
                transcript = ""

        if not transcript:
            model_name = settings.get("local_whisper_model") or "tiny.en"
            try:
                segs = await asyncio.to_thread(transcribe_pcm_with_local_whisper, pcm, model_name)
                transcript = " ".join(s["source_text"] for s in segs).strip()
            except Exception as exc:
                logger.warning("Local Whisper retelling failed: %s", exc)
                raise HTTPException(
                    status_code=503,
                    detail=f"本地语音识别模型暂不可用（{str(exc)[:100]}），请检查网络或切换文字复述。",
                )

        if not transcript:
            raise HTTPException(status_code=400, detail="未能从口述录音中识别出英文语音，请靠近麦克风清晰复述后重试。")

        res = await evaluate_retelling_attempt(episode_id, mode, transcript)
        res["transcript_text"] = transcript
        return res
    finally:
        raw_file.unlink(missing_ok=True)
        mp3_file.unlink(missing_ok=True)


# --- Engine Settings ---
@app.get("/api/settings")
def api_get_settings() -> dict[str, Any]:
    raw_cfg = get_settings()
    return {
        "settings": get_public_settings(),
        "has_asr_key": bool(raw_cfg.get("asr_api_key", "").strip()),
        "has_llm_key": bool(raw_cfg.get("llm_api_key", "").strip()),
    }


@app.put("/api/settings")
def api_put_settings(body: SettingsUpdate) -> dict[str, Any]:
    raw_cfg = save_settings(body.model_dump(exclude_none=True))
    return {
        "settings": get_public_settings(),
        "has_asr_key": bool(raw_cfg.get("asr_api_key", "").strip()),
        "has_llm_key": bool(raw_cfg.get("llm_api_key", "").strip()),
    }


@app.post("/api/settings/test-llm")
async def api_test_llm(body: TestLLMRequest) -> dict[str, Any]:
    return await test_llm_connection(body.base_url, body.api_key, body.model)


# --- Safe Media File Serving (with HTTP Range support via Starlette FileResponse) ---
@app.get("/media/{file_path:path}")
def serve_media(file_path: str) -> FileResponse:
    resolved = (MEDIA_DIR / file_path).resolve()
    media_root = MEDIA_DIR.resolve()
    if not resolved.is_relative_to(media_root) or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(resolved)


# --- Production Frontend SPA Static Serving (when frontend/dist is built) ---
FRONTEND_DIST = Path(
    os.getenv("LINGOREEL_FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist"))
).expanduser().resolve()


@app.get("/{full_path:path}")
def serve_frontend_spa(full_path: str) -> FileResponse:
    if full_path.startswith(("api/", "media/")):
        raise HTTPException(status_code=404, detail="Not found")
    if not FRONTEND_DIST.exists():
        raise HTTPException(status_code=404, detail="Frontend bundle not built yet")
    # Never expose internal hidden metadata files such as .lingo_build_id
    path_parts = [part for part in full_path.split("/") if part]
    if any(part.startswith(".") for part in path_parts):
        raise HTTPException(status_code=404, detail="Not found")
    candidate = (FRONTEND_DIST / full_path).resolve()
    if full_path and candidate.is_relative_to(FRONTEND_DIST) and candidate.is_file():
        if candidate.name == "index.html":
            headers = {
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        elif full_path.startswith("assets/"):
            headers = {"Cache-Control": "public, max-age=31536000, immutable"}
        else:
            headers = {"Cache-Control": "no-cache, must-revalidate"}
        return FileResponse(candidate, headers=headers)
    index_html = FRONTEND_DIST / "index.html"
    if index_html.is_file():
        return FileResponse(
            index_html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    raise HTTPException(status_code=404, detail="Frontend index.html missing")

