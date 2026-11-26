from __future__ import annotations

import asyncio
import html
import json
import logging
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx

from db import MEDIA_DIR, db_session, get_settings, now_iso, parse_json_safe
from lexicon_data import (
    CURATED_LEXICON,
    annotate_subtitle_html,
    build_offline_entry,
    estimate_word_timings,
    extract_offline_candidates,
    lemmatize_word,
    text_to_ipa,
    word_to_ipa,
)

logger = logging.getLogger("lingoreel.pipeline")

_FFMPEG_BIN_CACHE: str | None = None


def resolve_ffmpeg_bin() -> str:
    """Resolve system ffmpeg or bundled imageio-ffmpeg binary so macOS works without Homebrew ffmpeg."""
    global _FFMPEG_BIN_CACHE
    if _FFMPEG_BIN_CACHE and Path(_FFMPEG_BIN_CACHE).exists():
        return _FFMPEG_BIN_CACHE
    found = shutil.which("ffmpeg")
    if found:
        _FFMPEG_BIN_CACHE = found
        return found
    try:
        import imageio_ffmpeg  # type: ignore

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            _FFMPEG_BIN_CACHE = bundled
            return bundled
    except Exception:
        pass
    return "ffmpeg"


PIPELINE_TEMPLATE = [
    {"key": "media_extract", "label": "音画抽帧", "status": "pending", "detail": "等待提取音频轨与封面帧"},
    {"key": "transcribe", "label": "断句转写", "status": "pending", "detail": "等待字幕解析或语音识别"},
    {"key": "translate_ipa", "label": "译文音标", "status": "pending", "detail": "等待生成双语译文与 IPA 音标"},
    {"key": "extract_lexicon", "label": "词块抽取", "status": "pending", "detail": "等待识别短语动词、搭配与重点词"},
    {"key": "bind_index", "label": "词句绑定", "status": "pending", "detail": "等待建立篇内与跨篇复现索引"},
]

_WHISPER_CACHE: dict[str, Any] = {}


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _parse_ts_to_sec(raw: str) -> float:
    raw = raw.strip().replace(",", ".")
    parts = raw.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600.0 + float(m) * 60.0 + float(s)
    if len(parts) == 2:
        m, s = parts
        return float(m) * 60.0 + float(s)
    return float(raw)


def parse_srt_or_vtt(content: str) -> list[dict[str, Any]]:
    """Parse SRT or WebVTT text, supporting both English-only and bilingual cues."""
    cleaned = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    # Remove WEBVTT header and NOTE/STYLE blocks
    cleaned = re.sub(r"^WEBVTT[^\n]*\n+", "", cleaned, flags=re.IGNORECASE)
    blocks = re.split(r"\n{2,}", cleaned.strip())
    cues: list[dict[str, Any]] = []

    time_re = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})"
    )

    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        if lines[0].upper().startswith(("NOTE", "STYLE", "REGION")):
            continue
        ts_idx = -1
        ts_match = None
        for idx, ln in enumerate(lines[:3]):
            m = time_re.search(ln)
            if m:
                ts_idx = idx
                ts_match = m
                break
        if ts_idx < 0 or ts_match is None:
            continue
        start_sec = round(_parse_ts_to_sec(ts_match.group(1)), 3)
        end_sec = round(_parse_ts_to_sec(ts_match.group(2)), 3)
        if end_sec <= start_sec:
            end_sec = round(start_sec + 1.5, 3)

        body_lines: list[str] = []
        for ln in lines[ts_idx + 1 :]:
            stripped = re.sub(r"<[^>]+>", "", ln)
            stripped = re.sub(r"\{\\[^}]+\}", "", stripped)
            decoded = html.unescape(stripped).replace("\u00a0", " ").strip()
            if decoded:
                body_lines.append(decoded)
        if not body_lines:
            continue

        en_lines: list[str] = []
        cn_lines: list[str] = []
        for ln in body_lines:
            if _has_cjk(ln) and not re.search(r"[A-Za-z]{4,}", ln):
                cn_lines.append(ln)
            elif _has_cjk(ln) and re.search(r"[A-Za-z]{3,}", ln) and len(body_lines) == 1:
                # Single line containing both EN and CN separated by | or tab
                if "|" in ln:
                    left, right = ln.split("|", 1)
                    en_lines.append(left.strip())
                    cn_lines.append(right.strip())
                else:
                    en_lines.append(ln)
            else:
                en_lines.append(ln)

        source_text = " ".join(en_lines).strip() or " ".join(body_lines).strip()
        target_text = " ".join(cn_lines).strip()
        cues.append(
            {
                "start_sec": start_sec,
                "end_sec": end_sec,
                "source_text": source_text,
                "target_text": target_text,
                "words": estimate_word_timings(source_text, start_sec, end_sec),
            }
        )
    return cues


def format_srt_timestamp(sec: float) -> str:
    val = float(sec)
    if not math.isfinite(val):
        val = 0.0
    total_ms = max(0, int(round(val * 1000)))
    total_sec, ms = divmod(total_ms, 1000)
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt_content(subtitles: list[dict[str, Any]], bilingual: bool = True) -> str:
    blocks: list[str] = []
    for idx, sub in enumerate(subtitles, start=1):
        start_str = format_srt_timestamp(sub["start_sec"])
        end_str = format_srt_timestamp(sub["end_sec"])
        lines = [str(idx), f"{start_str} --> {end_str}", sub["source_text"]]
        if bilingual and sub.get("target_text"):
            lines.append(sub["target_text"])
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def update_episode_steps(
    episode_id: int,
    steps: list[dict[str, Any]],
    status: str | None = None,
    error_message: str | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> None:
    with db_session() as conn:
        cols = ["pipeline_steps_json = ?", "updated_at = ?"]
        vals: list[Any] = [json.dumps(steps, ensure_ascii=False), now_iso()]
        if status is not None:
            cols.append("status = ?")
            vals.append(status)
        if error_message is not None:
            cols.append("error_message = ?")
            vals.append(error_message)
        if extra_fields:
            for k, v in extra_fields.items():
                cols.append(f"{k} = ?")
                vals.append(v)
        vals.append(episode_id)
        conn.execute(f"UPDATE episodes SET {', '.join(cols)} WHERE id = ?", vals)


def _set_step(steps: list[dict[str, Any]], key: str, status: str, detail: str) -> None:
    for st in steps:
        if st["key"] == key:
            st["status"] = status
            st["detail"] = detail
            return


def probe_media_info(media_file: Path) -> tuple[float, bool]:
    """Return (duration_sec, has_video_stream), falling back to ffmpeg -i if ffprobe is absent."""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media_file),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            info = parse_json_safe(res.stdout, {})
            duration = float(info.get("format", {}).get("duration") or 0.0)
            streams = info.get("streams", [])
            has_video = any(
                s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic", 0) == 0
                for s in streams
            )
            if duration <= 0:
                for s in streams:
                    if s.get("duration"):
                        duration = max(duration, float(s["duration"]))
            return round(duration, 2), has_video
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # Fallback: parse `ffmpeg -i` output (works with bundled imageio-ffmpeg without ffprobe)
    try:
        res = subprocess.run([resolve_ffmpeg_bin(), "-i", str(media_file)], capture_output=True, text=True, timeout=20)
        err = res.stderr or ""
        duration = 0.0
        m = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)", err)
        if m:
            duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        has_video = bool(re.search(r"Stream\s+#\d+:\d+.*:\s+Video:", err)) and "attached pic" not in err.lower()
        return round(duration, 2), has_video
    except Exception:
        return 0.0, False


BROWSER_NATIVE_AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".ogg"}


def extract_media_assets(episode_id: int, source_file: Path) -> dict[str, Any]:
    """Extract normalized 16kHz ASR MP3, preserve high-quality playback audio, and capture cover thumbnail."""
    ep_dir = MEDIA_DIR / f"ep_{episode_id}"
    ep_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = resolve_ffmpeg_bin()

    duration_sec, has_video = probe_media_info(source_file)
    asr_audio_out = ep_dir / "asr_16k.mp3"
    cover_out = ep_dir / "cover.jpg"

    # Extract 16kHz mono MP3 strictly for Whisper ASR
    audio_cmd = [
        ffmpeg_bin,
        "-y",
        "-v",
        "error",
        "-i",
        str(source_file),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-b:a",
        "96k",
        str(asr_audio_out),
    ]
    audio_res = subprocess.run(audio_cmd, capture_output=True, text=True, timeout=180)
    if audio_res.returncode != 0 or not asr_audio_out.exists() or asr_audio_out.stat().st_size < 256:
        asr_audio_out.unlink(missing_ok=True)
        err_snip = (audio_res.stderr or "").strip().splitlines()
        detail = err_snip[-1][:140] if err_snip else "文件格式损坏或不包含有效音频轨"
        raise RuntimeError(f"无法解析该媒体文件，请确认文件未损坏且包含有效音轨（{detail}）。")

    if duration_sec <= 0:
        probed_asr_dur, _ = probe_media_info(asr_audio_out)
        duration_sec = probed_asr_dur
    if duration_sec <= 0.05:
        asr_audio_out.unlink(missing_ok=True)
        raise RuntimeError("该媒体文件的有效音频时长为 0 秒，请检查文件是否损坏。")

    rel_source = str(source_file.relative_to(MEDIA_DIR))
    if has_video:
        playback_audio_rel = f"ep_{episode_id}/asr_16k.mp3"
    elif source_file.suffix.lower() in BROWSER_NATIVE_AUDIO_EXTS:
        # Preserve original 44.1kHz stereo audio quality for browser playback!
        playback_audio_rel = rel_source
    else:
        # Transcode non-web audio (e.g. FLAC) to high-quality 44.1kHz stereo MP3 for playback
        hq_out = ep_dir / "audio_hq.mp3"
        hq_res = subprocess.run(
            [
                ffmpeg_bin, "-y", "-v", "error", "-i", str(source_file),
                "-vn", "-acodec", "libmp3lame", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                str(hq_out),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        playback_audio_rel = f"ep_{episode_id}/audio_hq.mp3" if (hq_res.returncode == 0 and hq_out.exists()) else f"ep_{episode_id}/asr_16k.mp3"

    cover_rel = ""
    if has_video:
        seek_t = min(max(0.5, duration_sec * 0.18), max(0.5, duration_sec - 0.5)) if duration_sec > 1 else 0.2
        cover_cmd = [
            ffmpeg_bin,
            "-y",
            "-ss",
            f"{seek_t:.2f}",
            "-i",
            str(source_file),
            "-vframes",
            "1",
            "-vf",
            "scale=960:-2",
            "-q:v",
            "3",
            str(cover_out),
        ]
        r = subprocess.run(cover_cmd, capture_output=True, text=True, timeout=45)
        if r.returncode == 0 and cover_out.exists():
            cover_rel = f"ep_{episode_id}/cover.jpg"

    # Fallback cover for audio-only uploads: render a subtle warm tactile card via ffmpeg lavfi
    if not cover_rel:
        fallback_cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=#1B1330:s=960x540:d=1",
            "-vframes",
            "1",
            str(cover_out),
        ]
        r = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and cover_out.exists():
            cover_rel = f"ep_{episode_id}/cover.jpg"

    return {
        "duration_sec": round(duration_sec, 2),
        "media_kind": "video" if has_video else "audio",
        "video_path": rel_source if has_video else "",
        "audio_path": playback_audio_rel,
        "cover_path": cover_rel,
        "_asr_audio_path": f"ep_{episode_id}/asr_16k.mp3",
    }


async def transcribe_with_cloud_whisper(audio_path: Path, settings: dict[str, str], source_lang: str) -> list[dict[str, Any]]:
    base_url = (settings.get("asr_base_url") or "https://api.openai.com/v1").strip().rstrip("/")
    api_key = settings["asr_api_key"].strip()
    model = settings.get("asr_model") or "whisper-1"
    url = (
        base_url
        if base_url.endswith("/audio/transcriptions")
        else f"{base_url}/audio/transcriptions"
    )

    async with httpx.AsyncClient(timeout=180.0) as client:
        with audio_path.open("rb") as f:
            files = {"file": (audio_path.name, f, "audio/mpeg")}
            data = {
                "model": model,
                "response_format": "verbose_json",
                "language": source_lang[:2] if source_lang else "en",
            }
            headers = {"Authorization": f"Bearer {api_key}"}
            resp = await client.post(url, headers=headers, data=data, files=files)
            resp.raise_for_status()
            payload = resp.json()

    cues: list[dict[str, Any]] = []
    segments = payload.get("segments") or []
    for seg in segments:
        txt = (seg.get("text") or "").strip()
        if not txt:
            continue
        start_s = round(float(seg.get("start", 0.0)), 3)
        end_s = round(float(seg.get("end", start_s + 2.0)), 3)
        raw_words = seg.get("words") or []
        if raw_words:
            words = [
                {
                    "index": i,
                    "word": (w.get("word") or "").strip(),
                    "start": round(float(w.get("start", start_s)), 3),
                    "end": round(float(w.get("end", end_s)), 3),
                    "has_timing": True,
                }
                for i, w in enumerate(raw_words)
                if (w.get("word") or "").strip()
            ]
        else:
            words = estimate_word_timings(txt, start_s, end_s)
        cues.append(
            {
                "start_sec": start_s,
                "end_sec": end_s,
                "source_text": txt,
                "target_text": "",
                "words": words,
            }
        )
    if not cues and payload.get("text"):
        full_txt = payload["text"].strip()
        cues.append(
            {
                "start_sec": 0.0,
                "end_sec": float(payload.get("duration") or 10.0),
                "source_text": full_txt,
                "target_text": "",
                "words": estimate_word_timings(full_txt, 0.0, float(payload.get("duration") or 10.0)),
            }
        )
    return cues


def _decode_audio_16k_float32(audio_path: Path):
    import numpy as np

    cmd = [
        resolve_ffmpeg_bin(),
        "-v",
        "error",
        "-i",
        str(audio_path),
        "-vn",
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ar",
        "16000",
        "-ac",
        "1",
        "pipe:1",
    ]
    res = subprocess.run(cmd, capture_output=True, timeout=90)
    if res.returncode != 0 or not res.stdout:
        raise RuntimeError(f"FFmpeg 音频解码失败：{res.stderr.decode('utf-8', errors='ignore')[:160]}")
    return np.frombuffer(res.stdout, dtype=np.float32).copy()


def _load_whisper_model(model_name: str = "tiny.en") -> Any:
    from faster_whisper import WhisperModel

    model = _WHISPER_CACHE.get(model_name)
    if model is not None:
        return model

    try:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception as first_exc:
        # Automatic fallback to hf-mirror for users in mainland China when huggingface.co is unreachable
        if os.getenv("HF_ENDPOINT", "").rstrip("/") != "https://hf-mirror.com":
            logger.warning("Whisper model load failed (%s); retrying via https://hf-mirror.com", first_exc)
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
        else:
            raise
    _WHISPER_CACHE[model_name] = model
    return model


def transcribe_pcm_with_local_whisper(audio_pcm: Any, model_name: str = "tiny.en") -> list[dict[str, Any]]:
    model = _load_whisper_model(model_name)
    segments, _info = model.transcribe(audio_pcm, word_timestamps=True, vad_filter=True)
    cues: list[dict[str, Any]] = []
    for seg in segments:
        txt = (seg.text or "").strip()
        if not txt:
            continue
        start_s = round(float(seg.start), 3)
        end_s = round(float(seg.end), 3)
        words: list[dict[str, Any]] = []
        if seg.words:
            for idx, w in enumerate(seg.words):
                wtxt = (w.word or "").strip()
                if wtxt:
                    words.append(
                        {
                            "index": idx,
                            "word": wtxt,
                            "start": round(float(w.start), 3),
                            "end": round(float(w.end), 3),
                            "has_timing": True,
                        }
                    )
        if not words:
            words = estimate_word_timings(txt, start_s, end_s)
        cues.append(
            {
                "start_sec": start_s,
                "end_sec": end_s,
                "source_text": txt,
                "target_text": "",
                "words": words,
            }
        )
    return cues


def transcribe_with_local_whisper(audio_path: Path, model_name: str = "tiny.en") -> list[dict[str, Any]]:
    audio_pcm = _decode_audio_16k_float32(audio_path)
    return transcribe_pcm_with_local_whisper(audio_pcm, model_name=model_name)


def _extract_json_block(text: str) -> Any:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


async def call_llm_json(
    settings: dict[str, str],
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> Any | None:
    api_key = settings.get("llm_api_key", "").strip()
    if not api_key:
        return None
    base_url = (settings.get("llm_base_url") or "https://api.openai.com/v1").strip().rstrip("/")
    url = (
        base_url
        if base_url.endswith("/chat/completions")
        else f"{base_url}/chat/completions"
    )
    model = settings.get("llm_model") or "gpt-4o-mini"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    content = data["choices"][0]["message"]["content"]
    return _extract_json_block(content)


async def translate_cues_with_llm(cues: list[dict[str, Any]], settings: dict[str, str]) -> bool:
    missing_indices = [i for i, c in enumerate(cues) if not c.get("target_text")]
    if not missing_indices:
        return False
    if not settings.get("llm_api_key", "").strip():
        return False

    # Process in chunks of 25 sentences
    batch_size = 25
    used_llm = False
    for offset in range(0, len(missing_indices), batch_size):
        chunk_ids = missing_indices[offset : offset + batch_size]
        payload = [{"idx": i, "text": cues[i]["source_text"]} for i in chunk_ids]
        sys_prompt = (
            "You are an expert English-to-Simplified-Chinese subtitle translator for language learners. "
            "Translate naturally, faithfully, and concisely. Return ONLY a JSON array of objects "
            '[{"idx": number, "zh": string}].'
        )
        try:
            result = await call_llm_json(settings, sys_prompt, json.dumps(payload, ensure_ascii=False))
            if isinstance(result, list):
                for item in result:
                    idx = item.get("idx")
                    zh = (item.get("zh") or "").strip()
                    if isinstance(idx, int) and 0 <= idx < len(cues) and zh:
                        cues[idx]["target_text"] = zh
                        used_llm = True
        except Exception as exc:
            logger.warning("LLM translation batch failed, falling back: %s", exc)
    return used_llm


def build_offline_translation_gloss(source_text: str) -> str:
    """Fallback concise gloss when no bilingual SRT and no LLM key are provided."""
    hits: list[str] = []
    lower = source_text.lower()
    for key, item in CURATED_LEXICON.items():
        if key in lower:
            cn = item["definitions"][0]["definition_target"].split("；")[0]
            hits.append(f"{item['headword']}({cn})")
            if len(hits) >= 3:
                break
    if hits:
        return "词义提示：" + "，".join(hits) + "（配置 LLM API 可自动生成完整逐句中文翻译）"
    return "（离线模式：导入双语字幕或配置 LLM API 后可自动生成完整中文译文）"


async def enrich_unknown_entries_online(entries: list[dict[str, Any]], enabled: bool) -> None:
    """Optionally enrich non-curated single words from free dictionaryapi.dev with a short timeout."""
    if not enabled:
        return
    unknown = [
        e for e in entries
        if e["lemma_key"] not in CURATED_LEXICON and " " not in e["lemma_key"]
    ][:8]
    if not unknown:
        return

    async def _fetch_one(client: httpx.AsyncClient, entry: dict[str, Any]) -> None:
        try:
            r = await client.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{entry['lemma_key']}")
            if r.status_code != 200:
                return
            arr = r.json()
            if not isinstance(arr, list) or not arr:
                return
            first = arr[0]
            phonetics = first.get("phonetics") or []
            ipa_found = next((p.get("text") for p in phonetics if p.get("text")), None)
            if ipa_found:
                entry["pronunciations"] = [
                    {"accent_type": "US", "ipa": ipa_found, "is_primary": True},
                    {"accent_type": "UK", "ipa": ipa_found, "is_primary": False},
                ]
            meanings = first.get("meanings") or []
            defs: list[dict[str, Any]] = []
            for m in meanings[:2]:
                pos = m.get("partOfSpeech") or "word"
                for d in (m.get("definitions") or [])[:1]:
                    ex_src = d.get("example") or ""
                    defs.append(
                        {
                            "pos": pos,
                            "definition_source": d.get("definition") or "",
                            "definition_target": entry["definitions"][0]["definition_target"],
                            "usage_pattern": "",
                            "examples": (
                                [{"example_source": ex_src, "example_target": ""}] if ex_src else []
                            ),
                        }
                    )
            if defs:
                entry["definitions"] = defs
        except Exception:
            return

    try:
        async with httpx.AsyncClient(timeout=3.5) as client:
            await asyncio.gather(*[_fetch_one(client, e) for e in unknown])
    except Exception:
        pass


async def extract_lexicon_with_llm(cues: list[dict[str, Any]], settings: dict[str, str]) -> list[dict[str, Any]] | None:
    if not settings.get("llm_api_key", "").strip():
        return None
    transcript = "\n".join(f"[{i+1}] {c['source_text']}" for i, c in enumerate(cues[:60]))
    sys_prompt = (
        "You are an English lexicographer building a structured study glossary for Chinese learners. "
        "Extract 10 to 22 high-value vocabulary items (phrasal verbs, idioms, collocations, and key words) "
        "from the transcript. Return ONLY a JSON array of objects with schema:\n"
        '[{"headword":"break down","category":"短语动词|惯用表达|搭配|短语|单词","form":"breaking down",'
        '"exam_tags":["雅思","口语"],"ipa_us":"/breɪk daʊn/","ipa_uk":"/breɪk daʊn/",'
        '"definitions":[{"pos":"verb phrase","definition_source":"...","definition_target":"...",'
        '"usage_pattern":"...","examples":[{"example_source":"...","example_target":"..."}]}]}]'
    )
    try:
        res = await call_llm_json(settings, sys_prompt, transcript)
        if not isinstance(res, list) or not res:
            return None
        cleaned: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in res:
            hw = (item.get("headword") or "").strip()
            if not hw:
                continue
            lkey = hw.lower()
            if lkey in seen:
                continue
            seen.add(lkey)
            ipa_us = item.get("ipa_us") or word_to_ipa(hw)
            ipa_uk = item.get("ipa_uk") or ipa_us
            cleaned.append(
                {
                    "headword": hw,
                    "lemma_key": lkey,
                    "category": item.get("category") or ("短语" if " " in hw else "单词"),
                    "form": item.get("form") or hw,
                    "exam_tags": item.get("exam_tags") or ["核心词"],
                    "pronunciations": [
                        {"accent_type": "US", "ipa": ipa_us, "is_primary": True},
                        {"accent_type": "UK", "ipa": ipa_uk, "is_primary": False},
                    ],
                    "definitions": item.get("definitions") or build_offline_entry(lkey, hw)["definitions"],
                }
            )
        return cleaned
    except Exception as exc:
        logger.warning("LLM lexicon extraction failed, falling back offline: %s", exc)
        return None


def build_offline_retelling_guide(title: str, cues: list[dict[str, Any]], entries: list[dict[str, Any]]) -> dict[str, Any]:
    keywords = [e["headword"] for e in entries[:8]]
    core_points = []
    # Pick up to 4 representative sentences evenly spaced through the clip
    if cues:
        step = max(1, len(cues) // 4)
        picked = cues[::step][:4]
        for idx, sub in enumerate(picked, start=1):
            core_points.append(
                {
                    "id": idx,
                    "point_en": sub["source_text"],
                    "point_zh": sub.get("target_text") or f"核心论点 {idx}",
                    "keywords": [
                        w.lower()
                        for w in re.findall(r"[A-Za-z]{4,}", sub["source_text"])
                        if w.lower() not in {"that", "this", "with", "from", "have", "your", "into", "when", "what"}
                    ][:5],
                }
            )
    questions = [
        {
            "en": f"What is the main method or insight presented in '{title}'?",
            "zh": f"《{title}》中提出的核心方法或核心观点是什么？",
        },
        {
            "en": "Which concrete habits or steps does the speaker recommend practicing?",
            "zh": "讲述者建议通过哪些具体步骤或习惯来落实？",
        },
        {
            "en": "Why does this deliberate approach work better in the long run?",
            "zh": "为什么这种刻意练习的方法从长远来看更有效？",
        },
    ]
    return {
        "keywords": keywords,
        "questions": questions,
        "core_points": core_points,
    }


def _episode_exists(episode_id: int) -> bool:
    with db_session() as conn:
        return conn.execute("SELECT 1 FROM episodes WHERE id = ?", (episode_id,)).fetchone() is not None


def upsert_and_bind_episode(
    episode_id: int,
    cues: list[dict[str, Any]],
    candidate_entries: list[dict[str, Any]],
    retelling_guide: dict[str, Any],
) -> tuple[int, int]:
    """Persist subtitles, upsert entries, annotate HTML, and populate occurrence indexes."""
    with db_session() as conn:
        if not conn.execute("SELECT 1 FROM episodes WHERE id = ?", (episode_id,)).fetchone():
            return 0, 0
        # Clear previous episode subtitles & occurrence mappings (for re-decomposition)
        conn.execute("DELETE FROM subtitle_occurrences WHERE episode_id = ?", (episode_id,))
        conn.execute("DELETE FROM episode_entries WHERE episode_id = ?", (episode_id,))
        conn.execute("DELETE FROM subtitles WHERE episode_id = ?", (episode_id,))

        # 1. Upsert vocabulary entries globally so cross-episode jumps share the same entry_id!
        db_entries: list[dict[str, Any]] = []
        now = now_iso()
        for item in candidate_entries:
            lkey = (item.get("lemma_key") or item.get("headword") or "").lower().strip()
            if not lkey:
                continue
            existing = conn.execute(
                "SELECT * FROM entries WHERE lemma_key = ?", (lkey,)
            ).fetchone()
            if existing:
                entry_id = existing["id"]
                # Keep bookmarked status; upgrade definitions if existing was generic fallback
                existing_defs = parse_json_safe(existing["definitions_json"], [])
                new_defs = item.get("definitions") or []
                if new_defs and existing_defs and "语境重点词「" in str(existing_defs[0].get("definition_target", "")):
                    conn.execute(
                        "UPDATE entries SET category=?, exam_tags_json=?, pronunciations_json=?, definitions_json=? WHERE id=?",
                        (
                            item.get("category", existing["category"]),
                            json.dumps(item.get("exam_tags", []), ensure_ascii=False),
                            json.dumps(item.get("pronunciations", []), ensure_ascii=False),
                            json.dumps(new_defs, ensure_ascii=False),
                            entry_id,
                        ),
                    )
                entry_rec = {
                    "id": entry_id,
                    "headword": existing["headword"],
                    "lemma_key": lkey,
                    "category": existing["category"],
                    "form": item.get("form") or existing["headword"],
                }
            else:
                cur = conn.execute(
                    """
                    INSERT INTO entries (
                        headword, lemma_key, category, language_code, target_language_code,
                        exam_tags_json, pronunciations_json, definitions_json, is_bookmarked, created_at
                    ) VALUES (?, ?, ?, 'en', 'zh-CN', ?, ?, ?, 0, ?)
                    """,
                    (
                        item["headword"],
                        lkey,
                        item.get("category", "单词"),
                        json.dumps(item.get("exam_tags", []), ensure_ascii=False),
                        json.dumps(item.get("pronunciations", []), ensure_ascii=False),
                        json.dumps(item.get("definitions", []), ensure_ascii=False),
                        now,
                    ),
                )
                entry_id = int(cur.lastrowid)
                entry_rec = {
                    "id": entry_id,
                    "headword": item["headword"],
                    "lemma_key": lkey,
                    "category": item.get("category", "单词"),
                    "form": item.get("form") or item["headword"],
                }
            db_entries.append(entry_rec)

        # 2. Insert subtitles & annotate occurrences
        entry_forms: dict[int, set[str]] = {}
        entry_counts: dict[int, int] = {}

        for seq_idx, cue in enumerate(cues, start=1):
            src = cue["source_text"].strip()
            annotated_html, occs = annotate_subtitle_html(src, db_entries)
            ipa_str = cue.get("ipa") or text_to_ipa(src)
            words = cue.get("words") or estimate_word_timings(src, cue["start_sec"], cue["end_sec"])
            cur = conn.execute(
                """
                INSERT INTO subtitles (
                    episode_id, seq_index, start_sec, end_sec,
                    source_text, source_html, target_text, ipa, words_json, is_favorite
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    episode_id,
                    seq_idx,
                    float(cue["start_sec"]),
                    float(cue["end_sec"]),
                    src,
                    annotated_html,
                    cue.get("target_text", ""),
                    ipa_str,
                    json.dumps(words, ensure_ascii=False),
                ),
            )
            sub_id = int(cur.lastrowid)
            for occ in occs:
                eid = int(occ["entry_id"])
                conn.execute(
                    """
                    INSERT INTO subtitle_occurrences (
                        episode_id, subtitle_id, entry_id, matched_form, char_start, char_end
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode_id,
                        sub_id,
                        eid,
                        occ["matched_form"],
                        occ["char_start"],
                        occ["char_end"],
                    ),
                )
                entry_forms.setdefault(eid, set()).add(occ["matched_form"])
                entry_counts[eid] = entry_counts.get(eid, 0) + 1

        # 3. Populate episode_entries for matched entries
        for eid, cnt in entry_counts.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO episode_entries (episode_id, entry_id, forms_json, occurrence_count)
                VALUES (?, ?, ?, ?)
                """,
                (episode_id, eid, json.dumps(sorted(entry_forms.get(eid, set())), ensure_ascii=False), cnt),
            )

        conn.execute(
            "UPDATE episodes SET retelling_guide_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(retelling_guide, ensure_ascii=False), now_iso(), episode_id),
        )
        return len(cues), len(entry_counts)


def rebind_episode_annotations(episode_id: int) -> int:
    """Re-annotate all subtitles of an episode using current global + episode entries."""
    with db_session() as conn:
        sub_rows = conn.execute(
            "SELECT id, source_text FROM subtitles WHERE episode_id = ? ORDER BY seq_index ASC",
            (episode_id,),
        ).fetchall()
        entry_rows = conn.execute("SELECT id, headword, lemma_key, category FROM entries").fetchall()
        entry_list = [dict(r) for r in entry_rows]

        conn.execute("DELETE FROM subtitle_occurrences WHERE episode_id = ?", (episode_id,))
        conn.execute("DELETE FROM episode_entries WHERE episode_id = ?", (episode_id,))

        entry_forms: dict[int, set[str]] = {}
        entry_counts: dict[int, int] = {}

        for sub in sub_rows:
            annotated_html, occs = annotate_subtitle_html(sub["source_text"], entry_list)
            conn.execute(
                "UPDATE subtitles SET source_html = ? WHERE id = ?",
                (annotated_html, sub["id"]),
            )
            for occ in occs:
                eid = int(occ["entry_id"])
                conn.execute(
                    """
                    INSERT INTO subtitle_occurrences (
                        episode_id, subtitle_id, entry_id, matched_form, char_start, char_end
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode_id,
                        sub["id"],
                        eid,
                        occ["matched_form"],
                        occ["char_start"],
                        occ["char_end"],
                    ),
                )
                entry_forms.setdefault(eid, set()).add(occ["matched_form"])
                entry_counts[eid] = entry_counts.get(eid, 0) + 1

        for eid, cnt in entry_counts.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO episode_entries (episode_id, entry_id, forms_json, occurrence_count)
                VALUES (?, ?, ?, ?)
                """,
                (episode_id, eid, json.dumps(sorted(entry_forms.get(eid, set())), ensure_ascii=False), cnt),
            )
        return len(entry_counts)


async def run_decomposition_pipeline(
    episode_id: int,
    media_file: Path,
    subtitle_content: str | None = None,
) -> None:
    """Execute the full 5-stage automatic video decomposition pipeline."""
    steps = [dict(s) for s in PIPELINE_TEMPLATE]
    settings = get_settings()
    engine_tags: list[str] = []

    try:
        with db_session() as conn:
            ep_row = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
            if not ep_row:
                return
            ep_title = ep_row["title"]
            source_lang = ep_row["source_lang"] or "en"

        # --- Stage 1: Media Extract ---
        _set_step(steps, "media_extract", "running", "正在用 FFmpeg 抽取音轨与首帧封面...")
        update_episode_steps(episode_id, steps, status="processing", error_message="")
        media_meta = await asyncio.to_thread(extract_media_assets, episode_id, media_file)
        if not _episode_exists(episode_id):
            return
        asr_audio_rel = media_meta.pop("_asr_audio_path", media_meta["audio_path"])
        dur_str = f"{int(media_meta['duration_sec'] // 60):02d}:{int(media_meta['duration_sec'] % 60):02d}"
        _set_step(
            steps,
            "media_extract",
            "done",
            f"已提取音画资源（时长 {dur_str}，{'视频' if media_meta['media_kind'] == 'video' else '纯音频'}）",
        )
        update_episode_steps(episode_id, steps, extra_fields=media_meta)

        # --- Stage 2: Transcribe / Subtitle Parse ---
        _set_step(steps, "transcribe", "running", "正在解析字幕或执行语音断句识别...")
        update_episode_steps(episode_id, steps)
        audio_abs = MEDIA_DIR / asr_audio_rel

        cues: list[dict[str, Any]] = []
        if subtitle_content and subtitle_content.strip():
            cues = parse_srt_or_vtt(subtitle_content)
            engine_tags.append("SRT/VTT字幕")
            _set_step(steps, "transcribe", "done", f"已解析上传字幕，共 {len(cues)} 句精确时间轴")
        else:
            asr_mode = settings.get("asr_mode", "auto")
            has_cloud_asr = bool(settings.get("asr_api_key", "").strip())
            if asr_mode == "subtitle_only":
                raise RuntimeError("当前语音识别策略为「仅使用已有字幕」，请附带上传 SRT/VTT 字幕或在「引擎」中切换为自动/本地识别。")
            if asr_mode == "cloud_api" and not has_cloud_asr:
                raise RuntimeError("当前语音识别策略为「强制云端 Whisper API」，但尚未配置云端 ASR API Key，请在「引擎」中填写或切回自动/本地模式。")
            if asr_mode == "cloud_api" or (asr_mode == "auto" and has_cloud_asr):
                _set_step(steps, "transcribe", "running", "正在调用云端 Whisper API 识别字幕与词级时间戳...")
                update_episode_steps(episode_id, steps)
                try:
                    cues = await transcribe_with_cloud_whisper(audio_abs, settings, source_lang)
                    engine_tags.append("Cloud Whisper")
                    _set_step(steps, "transcribe", "done", f"云端语音识别完成，生成 {len(cues)} 句")
                except Exception as exc:
                    if asr_mode == "cloud_api":
                        raise
                    logger.warning("Cloud Whisper failed in auto mode, falling back to local faster-whisper: %s", exc)
                    cues = []

            if not cues:
                local_model = settings.get("local_whisper_model") or "tiny.en"
                _set_step(steps, "transcribe", "running", f"正在用本地 faster-whisper ({local_model}) 离线转写...")
                update_episode_steps(episode_id, steps)
                cues = await asyncio.to_thread(transcribe_with_local_whisper, audio_abs, local_model)
                engine_tags.append(f"本地 Whisper({local_model})")
                _set_step(steps, "transcribe", "done", f"离线语音转写完成，共断句 {len(cues)} 条")

        if not _episode_exists(episode_id):
            return
        if not cues:
            raise RuntimeError("未能解析出有效字幕句子，请检查视频是否包含清晰语音或补充上传 SRT/VTT 字幕。")

        # Clamp duration if ffprobe reported 0
        if media_meta["duration_sec"] <= 0 and cues:
            inferred_dur = max(c["end_sec"] for c in cues)
            update_episode_steps(episode_id, steps, extra_fields={"duration_sec": inferred_dur})

        # --- Stage 3: Translate & IPA ---
        _set_step(steps, "translate_ipa", "running", "正在生成中文译文与 CMUdict 国际音标...")
        update_episode_steps(episode_id, steps)
        used_llm_trans = await translate_cues_with_llm(cues, settings)
        if not _episode_exists(episode_id):
            return
        if used_llm_trans:
            engine_tags.append("LLM译文")
        for cue in cues:
            cue["ipa"] = text_to_ipa(cue["source_text"])
            if not cue.get("target_text"):
                cue["target_text"] = build_offline_translation_gloss(cue["source_text"])
        _set_step(
            steps,
            "translate_ipa",
            "done",
            f"已完成 {len(cues)} 句 IPA 音标" + ("与 LLM 中文精译" if used_llm_trans else "与双语对齐"),
        )
        update_episode_steps(episode_id, steps)

        # --- Stage 4: Extract Lexicon & Retelling Guide ---
        _set_step(steps, "extract_lexicon", "running", "正在抽取短语动词、惯用表达、核心词汇与复述大纲...")
        update_episode_steps(episode_id, steps)
        entries = await extract_lexicon_with_llm(cues, settings)
        if not _episode_exists(episode_id):
            return
        if entries:
            engine_tags.append("LLM词典")
        else:
            entries = await asyncio.to_thread(extract_offline_candidates, cues)
            online_dict = settings.get("enable_online_dict_fallback", "true").lower() == "true"
            await enrich_unknown_entries_online(entries, enabled=online_dict)
            engine_tags.append("离线词库引擎")

        retelling_guide = build_offline_retelling_guide(ep_title, cues, entries)
        _set_step(steps, "extract_lexicon", "done", f"已提炼 {len(entries)} 个重点词块与 3 级复述提示")
        update_episode_steps(episode_id, steps)

        # --- Stage 5: Bind & Index ---
        _set_step(steps, "bind_index", "running", "正在向字幕嵌入词块键帽并构建跨篇复现索引...")
        update_episode_steps(episode_id, steps)
        if not _episode_exists(episode_id):
            return
        sub_count, bound_count = await asyncio.to_thread(
            upsert_and_bind_episode, episode_id, cues, entries, retelling_guide
        )
        if not _episode_exists(episode_id):
            return
        _set_step(steps, "bind_index", "done", f"已绑定 {bound_count} 组词块至 {sub_count} 句字幕")
        update_episode_steps(
            episode_id,
            steps,
            status="ready",
            error_message="",
            extra_fields={"engine_used": " + ".join(engine_tags) or "离线引擎"},
        )
        logger.info("Episode %s decomposed successfully: %d cues, %d entries", episode_id, sub_count, bound_count)

    except asyncio.CancelledError:
        logger.info("Pipeline cancelled for deleted/restarted episode %s", episode_id)
        raise
    except Exception as exc:
        logger.exception("Pipeline failed for episode %s", episode_id)
        if not _episode_exists(episode_id):
            return
        for st in steps:
            if st["status"] == "running":
                st["status"] = "error"
                st["detail"] = f"处理中断：{exc}"
        update_episode_steps(
            episode_id,
            steps,
            status="error",
            error_message=str(exc),
        )
