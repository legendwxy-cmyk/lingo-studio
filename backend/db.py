from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("LINGOREEL_DATA_DIR", str(BASE_DIR / "data"))).expanduser().resolve()
MEDIA_DIR = DATA_DIR / "media"
DB_PATH = DATA_DIR / "lexifilm.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=15000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


DEFAULT_SETTINGS: dict[str, str] = {
    "asr_mode": "auto",  # auto | cloud_api | local_whisper | subtitle_only
    "asr_base_url": "https://api.openai.com/v1",
    "asr_api_key": "",
    "asr_model": "whisper-1",
    "local_whisper_model": "tiny.en",
    "llm_base_url": "https://api.openai.com/v1",
    "llm_api_key": "",
    "llm_model": "gpt-4o-mini",
    "default_target_lang": "zh-CN",
    "enable_online_dict_fallback": "true",
}


def init_db() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                series_name TEXT DEFAULT '自建资料库',
                episode_number INTEGER DEFAULT 1,
                source_lang TEXT DEFAULT 'en',
                target_lang TEXT DEFAULT 'zh-CN',
                difficulty TEXT DEFAULT 'B1',
                duration_sec REAL DEFAULT 0.0,
                video_path TEXT DEFAULT '',
                audio_path TEXT DEFAULT '',
                cover_path TEXT DEFAULT '',
                media_kind TEXT DEFAULT 'video',
                status TEXT DEFAULT 'queued',
                pipeline_steps_json TEXT DEFAULT '[]',
                error_message TEXT DEFAULT '',
                engine_used TEXT DEFAULT 'offline',
                retelling_guide_json TEXT DEFAULT '{}',
                is_completed INTEGER DEFAULT 0,
                is_favorite INTEGER DEFAULT 0,
                last_position_sec REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS subtitles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                seq_index INTEGER NOT NULL,
                start_sec REAL NOT NULL,
                end_sec REAL NOT NULL,
                source_text TEXT NOT NULL,
                source_html TEXT DEFAULT '',
                target_text TEXT DEFAULT '',
                ipa TEXT DEFAULT '',
                words_json TEXT DEFAULT '[]',
                is_favorite INTEGER DEFAULT 0,
                ai_note_json TEXT DEFAULT '',
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_subtitles_episode ON subtitles(episode_id, seq_index);

            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                headword TEXT NOT NULL,
                lemma_key TEXT NOT NULL UNIQUE,
                category TEXT DEFAULT '单词',
                language_code TEXT DEFAULT 'en',
                target_language_code TEXT DEFAULT 'zh-CN',
                exam_tags_json TEXT DEFAULT '[]',
                pronunciations_json TEXT DEFAULT '[]',
                definitions_json TEXT DEFAULT '[]',
                is_bookmarked INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS episode_entries (
                episode_id INTEGER NOT NULL,
                entry_id INTEGER NOT NULL,
                forms_json TEXT DEFAULT '[]',
                occurrence_count INTEGER DEFAULT 0,
                PRIMARY KEY (episode_id, entry_id),
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
                FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS subtitle_occurrences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                subtitle_id INTEGER NOT NULL,
                entry_id INTEGER NOT NULL,
                matched_form TEXT NOT NULL,
                char_start INTEGER DEFAULT 0,
                char_end INTEGER DEFAULT 0,
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
                FOREIGN KEY (subtitle_id) REFERENCES subtitles(id) ON DELETE CASCADE,
                FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_occ_episode ON subtitle_occurrences(episode_id);
            CREATE INDEX IF NOT EXISTS idx_occ_entry ON subtitle_occurrences(entry_id);
            CREATE INDEX IF NOT EXISTS idx_occ_subtitle ON subtitle_occurrences(subtitle_id);

            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                subtitle_id INTEGER NOT NULL,
                audio_path TEXT NOT NULL,
                duration_sec REAL DEFAULT 0.0,
                feedback_json TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
                FOREIGN KEY (subtitle_id) REFERENCES subtitles(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS retelling_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                mode TEXT DEFAULT 'keywords',
                transcript_text TEXT DEFAULT '',
                audio_path TEXT DEFAULT '',
                evaluation_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )


SECRET_MASK_MARKER = "••••"
SECRET_SETTING_KEYS = ("asr_api_key", "llm_api_key")


def mask_secret(val: str) -> str:
    s = (val or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return SECRET_MASK_MARKER
    return f"{s[:3]}{SECRET_MASK_MARKER}{s[-4:]}"


def is_masked_secret(val: str | None) -> bool:
    return bool(val and SECRET_MASK_MARKER in str(val))


def get_settings() -> dict[str, str]:
    with db_session() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        merged = dict(DEFAULT_SETTINGS)
        for row in rows:
            merged[row["key"]] = row["value"]
        return merged


def get_public_settings() -> dict[str, str]:
    cfg = get_settings()
    for key in SECRET_SETTING_KEYS:
        if cfg.get(key, "").strip():
            cfg[key] = mask_secret(cfg[key])
    return cfg


def save_settings(updates: dict[str, Any]) -> dict[str, str]:
    with db_session() as conn:
        for key, value in updates.items():
            if key not in DEFAULT_SETTINGS or value is None:
                continue
            val_str = str(value)
            if key in SECRET_SETTING_KEYS and is_masked_secret(val_str):
                # Keep existing secret untouched when the masked placeholder is submitted back unchanged
                continue
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, val_str),
            )
    return get_settings()


def parse_json_safe(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback
