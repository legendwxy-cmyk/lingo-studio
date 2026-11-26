from __future__ import annotations

import asyncio
import difflib
import json
import logging
import math
import mimetypes
import re
import subprocess
import uuid
import wave
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from db import MEDIA_DIR, db_session, get_settings, is_masked_secret, now_iso, parse_json_safe
from lexicon_data import STOPWORDS, lemmatize_word, text_to_ipa
from pipeline import (
    _decode_audio_16k_float32,
    call_llm_json,
    resolve_ffmpeg_bin,
    transcribe_pcm_with_local_whisper,
)

logger = logging.getLogger("lingoreel.ai")


def _tokenize_en(text: str) -> list[str]:
    cleaned = (text or "").replace("’", "'").replace("‘", "'").lower()
    return re.findall(r"[a-z]+(?:'[a-z]+)?|[0-9]+", cleaned)


def _detect_linking_patterns(sentence: str) -> list[str]:
    """Detect common English consonant-vowel linking and assimilation patterns offline."""
    words = re.findall(r"[A-Za-z']+", sentence)
    tips: list[str] = []
    vowels = set("aeiouAEIOU")
    for a, b in zip(words, words[1:]):
        if not a or not b:
            continue
        last_ch = a[-1]
        first_ch = b[0]
        if last_ch.isalpha() and last_ch not in vowels and first_ch in vowels:
            tips.append(f"连读建议：「{a} + {b}」尾辅音 /{last_ch.lower()}/ 可顺滑滑入后续元音开头。")
        elif last_ch.lower() in {"t", "d", "p", "b", "k", "g"} and first_ch.lower() in {"t", "d", "p", "b", "k", "g", "m", "n"}:
            tips.append(f"失去爆破：「{a} {b}」中 {a} 尾部的爆破音只需做出舌位口型，无需重读爆出。")
        if len(tips) >= 3:
            break
    if not tips:
        tips.append("语调建议：实词（动词、名词、形容词）保持清晰重读，虚词（to/of/in/the）自然弱读加快。")
    return tips


def _detect_grammar_structure(sentence: str) -> str:
    low = sentence.lower()
    notes: list[str] = []
    if re.search(r"\b(when|while|before|after|until|once|because|although|though|if)\b", low):
        notes.append("包含状语从句，注意主从句之间的气口停顿与语调衔接。")
    if re.search(r"\b(which|that|who|where)\b", low):
        notes.append("带有修饰性从句结构，精听时先抓主干主谓宾，再回听定语补充细节。")
    if re.search(r"\b(rather than|instead of|not only|as well as)\b", low):
        notes.append("使用了对比/并列连接结构，朗读时对比项需要加重音高以突出语义重心。")
    if not notes:
        notes.append("结构清晰的主干陈述句，适合以 0.85x 至 1.0x 语速整句一口气跟读，体会意群划分。")
    return " ".join(notes)


async def analyze_subtitle_sentence(subtitle_id: int, force_refresh: bool = False) -> dict[str, Any]:
    with db_session() as conn:
        sub = conn.execute("SELECT * FROM subtitles WHERE id = ?", (subtitle_id,)).fetchone()
        if not sub:
            raise ValueError("Subtitle not found")
        if sub["ai_note_json"] and not force_refresh:
            cached = parse_json_safe(sub["ai_note_json"], None)
            if cached:
                return cached
        occ_rows = conn.execute(
            """
            SELECT e.headword, e.category, e.definitions_json
            FROM subtitle_occurrences so
            JOIN entries e ON e.id = so.entry_id
            WHERE so.subtitle_id = ?
            """,
            (subtitle_id,),
        ).fetchall()

    source_text = sub["source_text"]
    target_text = sub["target_text"]
    ipa_str = sub["ipa"] or text_to_ipa(source_text)
    settings = get_settings()

    result: dict[str, Any] | None = None
    if settings.get("llm_api_key", "").strip():
        sys_prompt = (
            "You are a concise English listening & pronunciation coach for Chinese learners. "
            "Analyze the given sentence and return ONLY a JSON object:\n"
            '{"engine":"llm","grammar_summary":"...","linking_tips":["..."],"key_expressions":[{"expr":"...","note":"..."}],"practice_tip":"..."}'
        )
        user_prompt = f"Sentence: {source_text}\nChinese: {target_text}\nIPA: {ipa_str}"
        try:
            parsed = await call_llm_json(settings, sys_prompt, user_prompt)
            if isinstance(parsed, dict) and parsed.get("grammar_summary"):
                parsed["engine"] = f"LLM ({settings.get('llm_model', 'API')})"
                result = parsed
        except Exception as exc:
            logger.warning("LLM sentence analysis failed, falling back to offline analyzer: %s", exc)
            result = None

    if result is None:
        key_exprs = []
        for r in occ_rows[:5]:
            defs = parse_json_safe(r["definitions_json"], [])
            cn = defs[0].get("definition_target", "") if defs else ""
            key_exprs.append({"expr": r["headword"], "note": f"[{r['category']}] {cn}"})
        content_words = [
            w for w in re.findall(r"[A-Za-z]{4,}", source_text)
            if w.lower() not in STOPWORDS
        ][:6]
        result = {
            "engine": "离线语音语法分析引擎",
            "grammar_summary": _detect_grammar_structure(source_text),
            "linking_tips": _detect_linking_patterns(source_text),
            "stressed_words": content_words,
            "key_expressions": key_exprs,
            "practice_tip": "建议先用 0.85x 慢速跟读两遍确认连读与尾音，再切回 1.0x 原速盲听复述。",
        }

    with db_session() as conn:
        conn.execute(
            "UPDATE subtitles SET ai_note_json = ? WHERE id = ?",
            (json.dumps(result, ensure_ascii=False), subtitle_id),
        )
    return result


def _normalize_recording_to_mp3(raw_file: Path) -> Path:
    """Convert Safari MP4/M4A or Chrome WebM recording into a universal browser-playable MP3."""
    if raw_file.suffix.lower() == ".mp3":
        return raw_file
    mp3_file = raw_file.with_suffix(".mp3")
    res = subprocess.run(
        [
            resolve_ffmpeg_bin(),
            "-y",
            "-v",
            "error",
            "-i",
            str(raw_file),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-b:a",
            "96k",
            str(mp3_file),
        ],
        capture_output=True,
        timeout=30,
    )
    if res.returncode == 0 and mp3_file.exists() and mp3_file.stat().st_size > 256:
        raw_file.unlink(missing_ok=True)
        return mp3_file
    mp3_file.unlink(missing_ok=True)
    return raw_file


def _analyze_pcm_energy(pcm: np.ndarray) -> tuple[float, float, float, float]:
    """Return (duration_sec, rms, peak, active_frame_ratio) from 16kHz float32 PCM."""
    n = int(pcm.shape[0])
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0
    duration_sec = n / 16000.0
    rms = float(np.sqrt(np.mean(np.square(pcm, dtype=np.float64))))
    peak = float(np.max(np.abs(pcm)))
    frame_size = 320  # 20ms at 16kHz
    num_frames = n // frame_size
    if num_frames <= 0:
        active_ratio = 1.0 if rms > 0.008 else 0.0
    else:
        trimmed = pcm[: num_frames * frame_size].reshape(num_frames, frame_size)
        frame_rms = np.sqrt(np.mean(np.square(trimmed, dtype=np.float64), axis=1))
        active_ratio = float(np.mean(frame_rms > 0.008))
    return duration_sec, rms, peak, active_ratio


def _score_word_alignment(target_tokens: list[str], rec_tokens: list[str]) -> tuple[int, list[str]]:
    """Sequence-aware word matching returning (word_accuracy_pct, deduped_missing_words)."""
    if not target_tokens:
        return 100 if rec_tokens else 0, []
    if not rec_tokens:
        dedup = list(dict.fromkeys(w for w in target_tokens if w not in STOPWORDS))
        return 0, (dedup or list(dict.fromkeys(target_tokens)))[:6]

    matcher = difflib.SequenceMatcher(None, target_tokens, rec_tokens)
    matched_idx: set[int] = set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i in range(i1, i2):
                matched_idx.add(i)
        elif tag == "replace":
            # Allow close phonetic/inflection match for longer words (e.g. videos vs video)
            rec_slice = rec_tokens[j1:j2]
            for i in range(i1, i2):
                tw = target_tokens[i]
                if len(tw) >= 4 and any(
                    difflib.SequenceMatcher(None, tw, rw).ratio() >= 0.82
                    or lemmatize_word(tw) == lemmatize_word(rw)
                    for rw in rec_slice
                ):
                    matched_idx.add(i)

    word_acc = int(round((len(matched_idx) / len(target_tokens)) * 100))
    missing_content = list(
        dict.fromkeys(
            target_tokens[i]
            for i in range(len(target_tokens))
            if i not in matched_idx and target_tokens[i] not in STOPWORDS
        )
    )
    if not missing_content:
        missing_content = list(
            dict.fromkeys(target_tokens[i] for i in range(len(target_tokens)) if i not in matched_idx)
        )
    return word_acc, missing_content[:6]


def _compute_pace_score(rec_dur: float, target_dur: float) -> tuple[int, str]:
    pace_ratio = rec_dur / max(0.5, target_dur)
    if 0.85 <= pace_ratio <= 1.18:
        return 98, f"语速节奏与原声高度贴合（原句 {target_dur:.1f}s，你的跟读 {rec_dur:.1f}s）。"
    if 0.78 <= pace_ratio <= 1.28:
        return 90, f"语速节奏匹配度较好（原句 {target_dur:.1f}s，你的跟读 {rec_dur:.1f}s）。"
    if pace_ratio < 0.78:
        score = max(0, int(round(90 - (0.78 - pace_ratio) * 115)))
        return score, f"跟读快于原声（原句 {target_dur:.1f}s，你的跟读 {rec_dur:.1f}s），注意给重读词留足元音时长。"
    score = max(0, int(round(90 - (pace_ratio - 1.28) * 70)))
    return score, f"跟读慢于原声（原句 {target_dur:.1f}s，你的跟读 {rec_dur:.1f}s），可缩短词间停顿并连读弱读词。"


async def evaluate_shadowing_recording(
    episode_id: int,
    subtitle_id: int,
    audio_file: Path,
) -> dict[str, Any]:
    """Evaluate user shadowing recording with true PCM duration, silence rejection, and Whisper ASR."""
    with db_session() as conn:
        sub = conn.execute(
            "SELECT * FROM subtitles WHERE id = ? AND episode_id = ?",
            (subtitle_id, episode_id),
        ).fetchone()
        if not sub:
            audio_file.unlink(missing_ok=True)
            raise ValueError("Subtitle not found in episode")

    # 1. Normalize recording to universal browser-playable MP3 & decode exact 16kHz PCM
    final_audio = await asyncio.to_thread(_normalize_recording_to_mp3, audio_file)
    try:
        pcm = await asyncio.to_thread(_decode_audio_16k_float32, final_audio)
    except Exception as exc:
        final_audio.unlink(missing_ok=True)
        raise ValueError(f"录音文件损坏或无法解码，请检查麦克风后重试（{exc}）。")

    rec_dur, rms, peak, active_ratio = _analyze_pcm_energy(pcm)
    target_dur = max(0.5, float(sub["end_sec"]) - float(sub["start_sec"]))
    target_tokens = _tokenize_en(sub["source_text"])

    is_silent = rec_dur < 0.25 or rms < 0.0035 or peak < 0.018 or active_ratio < 0.04

    recognized_text = ""
    missing_words: list[str] = []
    word_accuracy: int | None = None
    overall_score: int | None = None
    asr_status = "ok"
    asr_warning = ""
    engine_label = ""

    if is_silent:
        pace_score = 0
        word_accuracy = 0
        overall_score = 0
        asr_status = "silent"
        engine_label = "人声能量与静音检测"
        pace_comment = (
            f"未检测到有效人声（录音 {rec_dur:.1f}s，音量过低或为纯静音），"
            "请检查浏览器麦克风输入权限与说话距离后重录。"
        )
        missing_words = list(dict.fromkeys(w for w in target_tokens if w not in STOPWORDS))[:6]
    else:
        pace_score, pace_comment = _compute_pace_score(rec_dur, target_dur)
        settings = get_settings()
        asr_succeeded = False
        asr_error = ""

        if settings.get("asr_api_key", "").strip():
            try:
                base_url = (settings.get("asr_base_url") or "https://api.openai.com/v1").strip().rstrip("/")
                asr_url = (
                    base_url
                    if base_url.endswith("/audio/transcriptions")
                    else f"{base_url}/audio/transcriptions"
                )
                headers = {"Authorization": f"Bearer {settings['asr_api_key'].strip()}"}
                mime = mimetypes.guess_type(final_audio.name)[0] or "audio/mpeg"
                async with httpx.AsyncClient(timeout=45.0) as client:
                    with final_audio.open("rb") as f:
                        resp = await client.post(
                            asr_url,
                            headers=headers,
                            data={"model": settings.get("asr_model") or "whisper-1", "language": "en"},
                            files={"file": (final_audio.name, f, mime)},
                        )
                        if resp.status_code == 200:
                            recognized_text = (resp.json().get("text") or "").strip()
                            engine_label = "Cloud Whisper 发音转写评测"
                            asr_succeeded = True
                        else:
                            asr_error = f"云端 ASR 返回 HTTP {resp.status_code}"
                            logger.warning("Cloud Whisper shadowing failed: %s", asr_error)
            except Exception as exc:
                asr_error = str(exc)
                logger.warning("Cloud Whisper shadowing exception: %s", exc)

        if not asr_succeeded:
            model_name = settings.get("local_whisper_model") or "tiny.en"
            try:
                segs = await asyncio.to_thread(transcribe_pcm_with_local_whisper, pcm, model_name)
                recognized_text = " ".join(s["source_text"] for s in segs).strip()
                engine_label = f"本地 Whisper({model_name}) 离线跟读评测"
                asr_succeeded = True
            except Exception as exc:
                asr_error = str(exc)
                logger.warning("Local Whisper shadowing failed: %s", exc)

        if asr_succeeded:
            rec_tokens = _tokenize_en(recognized_text)
            if not rec_tokens:
                asr_status = "no_speech"
                word_accuracy = 0
                overall_score = 0
                pace_comment = (
                    f"录到了环境声音但未识别出清晰英文词句（原句 {target_dur:.1f}s，你的录音 {rec_dur:.1f}s），"
                    "请贴近麦克风清晰朗读后重试。"
                )
                missing_words = list(dict.fromkeys(w for w in target_tokens if w not in STOPWORDS))[:6]
            else:
                word_accuracy, missing_words = _score_word_alignment(target_tokens, rec_tokens)
                # Gate pace_score by actual lexical accuracy so gibberish never gets inflated marks
                if word_accuracy == 0:
                    overall_score = 0
                elif word_accuracy < 20:
                    overall_score = word_accuracy
                else:
                    overall_score = min(100, max(0, int(round(word_accuracy * 0.78 + pace_score * 0.22))))
                asr_status = "ok"
        else:
            asr_status = "unavailable"
            word_accuracy = None
            overall_score = None
            engine_label = "语音引擎暂不可用（仅记录时长与音频）"
            asr_warning = (
                f"语音转写模型暂不可用（{asr_error[:100]}），当前无法给出发音准确度评分；"
                "请检查网络连接、开启桌面控制台「国内加速镜像」或配置云端 Whisper Key 后重录。"
            )

    feedback = {
        "engine": engine_label,
        "asr_status": asr_status,
        "asr_warning": asr_warning,
        "overall_score": overall_score,
        "word_accuracy": word_accuracy,
        "pace_score": pace_score,
        "is_silent": is_silent,
        "target_duration_sec": round(target_dur, 2),
        "recording_duration_sec": round(rec_dur, 2),
        "recognized_text": recognized_text,
        "missing_words": missing_words,
        "pace_comment": pace_comment,
        "tips": _detect_linking_patterns(sub["source_text"])[:2],
    }

    rel_audio = str(final_audio.relative_to(MEDIA_DIR))
    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO recordings (episode_id, subtitle_id, audio_path, duration_sec, feedback_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                episode_id,
                subtitle_id,
                rel_audio,
                round(rec_dur, 2),
                json.dumps(feedback, ensure_ascii=False),
                now_iso(),
            ),
        )
        rec_id = int(cur.lastrowid)

    return {
        "id": rec_id,
        "episode_id": episode_id,
        "subtitle_id": subtitle_id,
        "audio_url": f"/media/{rel_audio}",
        "duration_sec": round(rec_dur, 2),
        "feedback": feedback,
    }


def _decode_to_master_wav(raw_file: Path, wav_file: Path) -> float:
    """Decode any browser audio blob to 44.1kHz mono 16-bit PCM WAV and return exact duration."""
    res = subprocess.run(
        [
            resolve_ffmpeg_bin(),
            "-y",
            "-v",
            "error",
            "-i",
            str(raw_file),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(wav_file),
        ],
        capture_output=True,
        timeout=90,
    )
    if res.returncode != 0 or not wav_file.exists() or wav_file.stat().st_size <= 44:
        raise ValueError("连续跟读录音损坏或无法解码，请检查麦克风后重试。")
    with wave.open(str(wav_file), "rb") as wf:
        rate = wf.getframerate() or 44100
        frames = wf.getnframes()
        return frames / float(rate)


def _slice_wav_to_mp3(master_wav: Path, clip_start: float, clip_end: float, out_mp3: Path) -> bool:
    dur = max(0.05, clip_end - clip_start)
    res = subprocess.run(
        [
            resolve_ffmpeg_bin(),
            "-y",
            "-v",
            "error",
            "-ss",
            f"{clip_start:.3f}",
            "-t",
            f"{dur:.3f}",
            "-i",
            str(master_wav),
            "-acodec",
            "libmp3lame",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-b:a",
            "96k",
            str(out_mp3),
        ],
        capture_output=True,
        timeout=30,
    )
    return res.returncode == 0 and out_mp3.exists() and out_mp3.stat().st_size > 256


async def evaluate_continuous_shadowing_batch(
    episode_id: int,
    segments: list[dict[str, Any]],
    raw_audio_file: Path,
) -> dict[str, Any]:
    """Split a continuous shadowing recording by tracked sentence boundaries and score each cue."""
    if not segments:
        raw_audio_file.unlink(missing_ok=True)
        raise ValueError("未记录到有效的跟读句子区间，请重新录制。")

    # Validate episode & subtitle ownership upfront
    sub_ids = [int(s["subtitle_id"]) for s in segments]
    with db_session() as conn:
        ep = conn.execute("SELECT id FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not ep:
            raw_audio_file.unlink(missing_ok=True)
            raise ValueError("Episode not found")
        placeholders = ",".join("?" for _ in set(sub_ids))
        rows = conn.execute(
            f"SELECT id, seq_index FROM subtitles WHERE episode_id = ? AND id IN ({placeholders})",
            (episode_id, *set(sub_ids)),
        ).fetchall()
    seq_by_id = {int(r["id"]): int(r["seq_index"]) for r in rows}
    missing = [sid for sid in set(sub_ids) if sid not in seq_by_id]
    if missing:
        raw_audio_file.unlink(missing_ok=True)
        raise ValueError(f"目标篇目中不存在字幕句：{missing[0]}")

    rec_dir = MEDIA_DIR / f"ep_{episode_id}" / "recordings"
    rec_dir.mkdir(parents=True, exist_ok=True)
    master_wav = rec_dir / f"tmp_master_{uuid.uuid4().hex[:10]}.wav"

    try:
        total_dur = await asyncio.to_thread(_decode_to_master_wav, raw_audio_file, master_wav)
        if total_dur < 0.2:
            raise ValueError("连续跟读录音时长过短，请重新录制。")

        # 1. Merge consecutive duplicate subtitle_ids
        merged: list[dict[str, float | int]] = []
        for seg in segments:
            sid = int(seg["subtitle_id"])
            st = max(0.0, float(seg["start_sec"]))
            ed = max(st, float(seg["end_sec"]))
            if merged and merged[-1]["subtitle_id"] == sid:
                merged[-1]["end_sec"] = max(float(merged[-1]["end_sec"]), ed)
            else:
                merged.append({"subtitle_id": sid, "start_sec": st, "end_sec": ed})

        # 2. Drop tiny accidental transition stubs (<0.30s) when valid segments exist
        if len(merged) > 1:
            substantial = [m for m in merged if (float(m["end_sec"]) - float(m["start_sec"])) >= 0.30]
            if substantial:
                merged = substantial
            else:
                merged = [max(merged, key=lambda m: float(m["end_sec"]) - float(m["start_sec"]))]

        # 3. Proportionally reconcile clock skew if frontend offsets exceed decoded audio duration
        max_seg_end = max(float(m["end_sec"]) for m in merged)
        if max_seg_end > total_dur + 0.05 and max_seg_end > 0:
            scale = total_dur / max_seg_end
            for m in merged:
                m["start_sec"] = float(m["start_sec"]) * scale
                m["end_sec"] = float(m["end_sec"]) * scale

        # 4. Slice each sentence clip with subtle shadowing trail padding & evaluate independently
        results: list[dict[str, Any]] = []
        multi = len(merged) > 1
        for idx, m in enumerate(merged):
            sid = int(m["subtitle_id"])
            raw_st = float(m["start_sec"])
            raw_ed = float(m["end_sec"])
            if not multi:
                clip_start = 0.0
                clip_end = total_dur
            else:
                clip_start = max(0.0, raw_st - 0.05)
                if idx == len(merged) - 1:
                    clip_end = total_dur
                else:
                    clip_end = min(total_dur, raw_ed + 0.25)
                if clip_end <= clip_start + 0.15:
                    clip_end = min(total_dur, clip_start + 0.25)
                if clip_end <= clip_start + 0.08:
                    continue

            stamp = now_iso().replace(":", "").replace("-", "").replace(".", "") + "_" + uuid.uuid4().hex[:6]
            clip_mp3 = rec_dir / f"sub_{sid}_{stamp}.mp3"
            ok = await asyncio.to_thread(_slice_wav_to_mp3, master_wav, clip_start, clip_end, clip_mp3)
            if not ok:
                clip_mp3.unlink(missing_ok=True)
                continue

            rec_payload = await evaluate_shadowing_recording(episode_id, sid, clip_mp3)
            results.append(
                {
                    "subtitle_id": sid,
                    "seq_index": seq_by_id[sid],
                    "clip_start_sec": round(clip_start, 2),
                    "clip_end_sec": round(clip_end, 2),
                    "recording": rec_payload,
                }
            )

        if not results:
            raise ValueError("未能从连续录音中切分出有效句段，请确认录音时长后重试。")

        return {
            "episode_id": episode_id,
            "total_duration_sec": round(total_dur, 2),
            "saved_count": len(results),
            "results": results,
        }
    finally:
        raw_audio_file.unlink(missing_ok=True)
        master_wav.unlink(missing_ok=True)


async def evaluate_retelling_attempt(
    episode_id: int,
    mode: str,
    transcript_text: str,
) -> dict[str, Any]:
    with db_session() as conn:
        ep = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        if not ep:
            raise ValueError("Episode not found")
        guide = parse_json_safe(ep["retelling_guide_json"], {})

    core_points = guide.get("core_points") or []
    keywords = guide.get("keywords") or []
    user_clean = transcript_text.strip()
    user_tokens = _tokenize_en(user_clean)
    user_words = set(user_tokens)
    user_lemmas = {lemmatize_word(w) for w in user_words}

    settings = get_settings()
    evaluation: dict[str, Any] | None = None

    if settings.get("llm_api_key", "").strip() and user_clean:
        sys_prompt = (
            "You are an English speaking tutor for Chinese learners evaluating a learner's retelling of a short video. "
            "Write fluency_comment, point_zh, note, and upgrade_tips in Simplified Chinese; write polished_version in idiomatic English. "
            "Return ONLY a JSON object:\n"
            '{"engine":"llm","coverage_score":85,"fluency_comment":"...",'
            '"point_checks":[{"id":1,"status":"covered|partial|missing","point_zh":"...","note":"..."}],'
            '"polished_version":"...","upgrade_tips":["..."]}'
        )
        user_prompt = json.dumps(
            {
                "episode_title": ep["title"],
                "core_points": core_points,
                "target_keywords": keywords,
                "learner_retelling": user_clean,
            },
            ensure_ascii=False,
        )
        try:
            parsed = await call_llm_json(settings, sys_prompt, user_prompt)
            if isinstance(parsed, dict) and "coverage_score" in parsed:
                try:
                    raw_score = float(parsed["coverage_score"])
                    if not math.isfinite(raw_score):
                        raise ValueError("non-finite coverage_score")
                    parsed["coverage_score"] = max(0, min(100, int(round(raw_score))))
                except (TypeError, ValueError, OverflowError):
                    parsed["coverage_score"] = 0
                parsed["engine"] = f"LLM ({settings.get('llm_model', 'API')})"
                evaluation = parsed
        except Exception as exc:
            logger.warning("LLM retelling evaluation failed, falling back to offline evaluator: %s", exc)
            evaluation = None

    if evaluation is None:
        point_checks = []
        covered_weight = 0.0
        for pt in core_points:
            kws = [k.lower() for k in (pt.get("keywords") or [])]
            hits = [
                k
                for k in kws
                if k in user_words or (len(k) >= 3 and lemmatize_word(k) in user_lemmas)
            ]
            ratio = len(hits) / max(1, len(kws))
            if ratio >= 0.45:
                st = "covered"
                covered_weight += 1.0
                note = f"已准确提及核心词：{', '.join(hits[:3])}"
            elif ratio > 0:
                st = "partial"
                covered_weight += 0.5
                note = f"覆盖了部分线索（{', '.join(hits)}），可补充完整因果关系。"
            else:
                st = "missing"
                note = f"尚未展开此要点，建议串联表达：{pt.get('point_en', '')[:64]}..."
            point_checks.append(
                {
                    "id": pt.get("id"),
                    "status": st,
                    "point_zh": pt.get("point_zh", ""),
                    "point_en": pt.get("point_en", ""),
                    "note": note,
                }
            )
        user_lower = user_clean.lower()
        used_target_kws = [
            kw for kw in keywords
            if re.search(rf"\b{re.escape(kw.lower())}\b", user_lower)
        ]
        word_count = len(user_tokens)
        if not core_points or word_count == 0:
            score = 0
        else:
            score = int(round((covered_weight / len(core_points)) * 100))
        evaluation = {
            "engine": "离线语义要点覆写评测",
            "coverage_score": score,
            "word_count": word_count,
            "used_keywords": used_target_kws,
            "fluency_comment": (
                f"本次复述共输出 {word_count} 个英文词，命中 {len(used_target_kws)}/{len(keywords)} 个推荐表达。"
                + (" 要点覆盖较完整，可尝试无提示脱稿再说一遍！" if score >= 70 else " 建议对照下方未覆盖要点，先用关键词串联出 3-4 句主干再流畅复述。")
            ),
            "point_checks": point_checks,
            "polished_version": " ".join(pt.get("point_en", "") for pt in core_points[:3]),
            "upgrade_tips": [
                "尽量用原片中的短语动词（如 break down / sink in / pay off）替换泛用动词。",
                "复述时先总起主题，再按步骤顺序用 First / Next / In the long run 衔接。",
            ],
        }

    with db_session() as conn:
        cur = conn.execute(
            """
            INSERT INTO retelling_sessions (episode_id, mode, transcript_text, evaluation_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (episode_id, mode, user_clean, json.dumps(evaluation, ensure_ascii=False), now_iso()),
        )
        session_id = int(cur.lastrowid)

    return {"id": session_id, "episode_id": episode_id, "mode": mode, "evaluation": evaluation}


async def test_llm_connection(base_url: str, api_key: str, model: str) -> dict[str, Any]:
    resolved_key = (api_key or "").strip()
    if is_masked_secret(resolved_key):
        resolved_key = get_settings().get("llm_api_key", "").strip()
    if not resolved_key:
        return {"ok": False, "message": "请先填写 API Key 再测试连接。"}
    base = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
    url = base if base.endswith("/chat/completions") else base + "/chat/completions"
    headers = {"Authorization": f"Bearer {resolved_key}", "Content-Type": "application/json"}
    payload = {
        "model": (model or "gpt-4o-mini").strip(),
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "Reply with OK"}],
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code == 200:
                reply = r.json()["choices"][0]["message"]["content"].strip()
                return {"ok": True, "message": f"连接成功！模型返回：{reply}"}
            return {"ok": False, "message": f"接口返回 HTTP {r.status_code}：{r.text[:160]}"}
    except Exception as exc:
        return {"ok": False, "message": f"请求失败：{exc}"}
