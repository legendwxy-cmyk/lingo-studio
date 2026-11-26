from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from db import BASE_DIR, MEDIA_DIR, db_session, now_iso
from pipeline import build_srt_content, probe_media_info, resolve_ffmpeg_bin, run_decomposition_pipeline

logger = logging.getLogger("lingoreel.seed")

ASSETS_DIR = BASE_DIR / "assets"

DEMO_EPISODES: list[dict[str, Any]] = [
    {
        "title": "东京手冲咖啡的专注哲学",
        "description": "走进东京一间静谧的手冲吧台，从匠人的手部节律中精听关于专注、耐心与细节的表达。",
        "series_name": "匠人微纪录片",
        "episode_number": 1,
        "difficulty": "B1",
        "cover_asset": "tokyo_coffee.jpg",
        "voice": "en-US-AriaNeural",
        "lines": [
            (
                "Every morning before the street wakes up, the barista prepares his kettle with deliberate calm.",
                "每天清晨在街道苏醒之前，咖啡师都会怀着刻意而沉静的专注准备好手冲壶。",
            ),
            (
                "He shuts out every distraction and focuses on the steady rhythm of hot water meeting fresh grounds.",
                "他隔绝一切干扰，专注于热水落入新鲜咖啡粉时的平稳节奏。",
            ),
            (
                "Pay attention to the quiet bloom, because small details stand out when you slow down step by step.",
                "留意咖啡粉静静闷蒸的瞬间，因为当你一步步放慢脚步时，微小细节便会格外凸显。",
            ),
            (
                "An authentic cup never comes from rushing; it relies on consistent water temperature and patience.",
                "一杯地道的咖啡绝非仓促赶制，它依赖于持续稳定的水温与耐心。",
            ),
            (
                "Over years of practice, simple daily motions turn into effortless precision and graceful fluency.",
                "经年累月的练习，让简单的日常动作化作举重若轻的精准与流畅。",
            ),
            (
                "Even the tiniest habit pays off in the long run when you treat ordinary craft with genuine care.",
                "当你用真心对待平凡技艺时，哪怕最微小的习惯从长远来看也终会收获回报。",
            ),
        ],
    },
    {
        "title": "刻意精听的建筑学",
        "description": "拆解如何把 60 秒真实英语视频变成可听写、可跟读、可复述的立体语料课程。",
        "series_name": "精听方法论",
        "episode_number": 2,
        "difficulty": "B2",
        "cover_asset": "doc_speaker.jpg",
        "voice": "en-US-AndrewNeural",
        "lines": [
            (
                "When you break down a short authentic video step by step, natural fluency stops feeling mysterious.",
                "当你把一段原汁原味的短视频循序渐进地拆解开来，地道流利度就不再神秘。",
            ),
            (
                "Instead of relying on passive background audio, focus on one vivid clip and let every rhythm sink in.",
                "与其依赖被动的背景磨耳朵，不如专注在一个生动片段上，让每一处语流节奏慢慢吸收。",
            ),
            (
                "First, listen without subtitles and pay attention to stressed syllables and rising intonation.",
                "首先关闭字幕盲听一遍，密切留意重读音节以及上扬的语调起伏。",
            ),
            (
                "Next, run a quick dictation drill to figure out exactly which weak words slipped past your ear.",
                "接着做一次短句听写检验，弄明白究竟是哪些弱读词从耳边溜走了。",
            ),
            (
                "Then repeat each sentence out loud in shadowing mode so your mouth builds genuine muscle memory.",
                "然后在影子跟读模式下大声复述每一句，让口腔真正建立起肌肉记忆。",
            ),
            (
                "Always study phrasal verbs in real context rather than memorizing isolated lists without sound.",
                "务必在真实语境中学习短语动词，而不是脱离声音去死记孤立的词表。",
            ),
            (
                "Cut down on distractions and turn ten consistent minutes a day into a deliberate training ritual.",
                "减少分心干扰，把每天持续稳定的十分钟转化为一场刻意训练仪式。",
            ),
            (
                "This active approach builds lasting retention and pays off dramatically in the long run.",
                "这种主动精听法能建立持久记忆留存，并从长远来看带来惊人的回报。",
            ),
        ],
    },
]


_EDGE_TTS_OK = True


async def _synthesize_sentence_mp3(text: str, voice: str, out_mp3: Path) -> bool:
    """Synthesize clear natural English narration via edge-tts, then offline espeak-ng."""
    global _EDGE_TTS_OK
    if _EDGE_TTS_OK:
        try:
            import asyncio
            import edge_tts

            comm = edge_tts.Communicate(text, voice=voice, rate="-4%")
            await asyncio.wait_for(comm.save(str(out_mp3)), timeout=5.0)
            if out_mp3.exists() and out_mp3.stat().st_size > 1024:
                return True
        except Exception as exc:
            _EDGE_TTS_OK = False
            logger.warning("edge-tts unreachable or timed out (%s), switching demo synth to offline TTS", exc)

    # Offline spoken English TTS on macOS via built-in `say` -> aiff -> mp3
    try:
        import shutil as _shutil

        if _shutil.which("say"):
            aiff_tmp = out_mp3.with_suffix(".aiff")
            mac_voice = "Samantha" if "Aria" in voice else "Daniel"
            r = subprocess.run(
                ["say", "-v", mac_voice, "-r", "165", "-o", str(aiff_tmp), text],
                capture_output=True,
                timeout=20,
            )
            if r.returncode != 0:
                r = subprocess.run(
                    ["say", "-r", "165", "-o", str(aiff_tmp), text],
                    capture_output=True,
                    timeout=20,
                )
            if r.returncode == 0 and aiff_tmp.exists() and aiff_tmp.stat().st_size > 1024:
                subprocess.run(
                    [
                        resolve_ffmpeg_bin(),
                        "-y",
                        "-i",
                        str(aiff_tmp),
                        "-acodec",
                        "libmp3lame",
                        "-ar",
                        "24000",
                        "-ac",
                        "1",
                        "-b:a",
                        "128k",
                        str(out_mp3),
                    ],
                    capture_output=True,
                    timeout=20,
                )
                aiff_tmp.unlink(missing_ok=True)
                if out_mp3.exists() and out_mp3.stat().st_size > 1024:
                    return True
    except Exception as exc:
        logger.warning("macOS say fallback unavailable (%s)", exc)

    # Offline spoken English TTS on Linux via espeak-ng -> wav -> mp3
    try:
        wav_tmp = out_mp3.with_suffix(".wav")
        espeak_voice = "en-us+f3" if "Aria" in voice else "en-us+m3"
        r = subprocess.run(
            ["espeak-ng", "-v", espeak_voice, "-s", "145", "-w", str(wav_tmp), text],
            capture_output=True,
            timeout=20,
        )
        if r.returncode == 0 and wav_tmp.exists() and wav_tmp.stat().st_size > 1024:
            subprocess.run(
                [
                    resolve_ffmpeg_bin(),
                    "-y",
                    "-i",
                    str(wav_tmp),
                    "-acodec",
                    "libmp3lame",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-b:a",
                    "128k",
                    str(out_mp3),
                ],
                capture_output=True,
                timeout=20,
            )
            wav_tmp.unlink(missing_ok=True)
            if out_mp3.exists() and out_mp3.stat().st_size > 1024:
                return True
    except Exception as exc:
        logger.warning("espeak-ng fallback unavailable (%s)", exc)
    return False


def _generate_fallback_tone_mp3(duration_sec: float, out_mp3: Path) -> None:
    """Clean gentle ambient chime fallback if edge-tts is unreachable."""
    subprocess.run(
        [
            resolve_ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration_sec:.2f}",
            "-af",
            "volume=0.05",
            "-acodec",
            "libmp3lame",
            "-ar",
            "24000",
            "-ac",
            "1",
            str(out_mp3),
        ],
        capture_output=True,
        timeout=20,
    )


async def _build_demo_media_and_srt(spec: dict[str, Any], ep_dir: Path) -> tuple[Path, str]:
    ep_dir.mkdir(parents=True, exist_ok=True)
    video_out = ep_dir / "source.mp4"
    cover_img = ASSETS_DIR / spec["cover_asset"]
    lines: list[tuple[str, str]] = spec["lines"]

    with tempfile.TemporaryDirectory(prefix="lingo_seed_") as tmp:
        tmp_dir = Path(tmp)
        silence_mp3 = tmp_dir / "gap.mp3"
        subprocess.run(
            [
                resolve_ffmpeg_bin(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono",
                "-t",
                "0.45",
                "-acodec",
                "libmp3lame",
                "-b:a",
                "96k",
                str(silence_mp3),
            ],
            capture_output=True,
            timeout=20,
        )

        concat_entries: list[str] = []
        subtitles: list[dict[str, Any]] = []
        cursor = 0.25

        # Leading 0.25s breath pad
        lead_mp3 = tmp_dir / "lead.mp3"
        subprocess.run(
            [
                resolve_ffmpeg_bin(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono",
                "-t",
                "0.25",
                "-acodec",
                "libmp3lame",
                "-b:a",
                "96k",
                str(lead_mp3),
            ],
            capture_output=True,
            timeout=20,
        )
        concat_entries.append(f"file '{lead_mp3}'")

        for idx, (en, zh) in enumerate(lines, start=1):
            raw_mp3 = tmp_dir / f"raw_{idx}.mp3"
            norm_mp3 = tmp_dir / f"norm_{idx}.mp3"
            ok = await _synthesize_sentence_mp3(en, spec["voice"], raw_mp3)
            if not ok:
                est_dur = max(3.2, len(en.split()) * 0.42)
                _generate_fallback_tone_mp3(est_dur, raw_mp3)

            # Normalize sample rate & channels so concat is seamless
            subprocess.run(
                [
                    resolve_ffmpeg_bin(),
                    "-y",
                    "-i",
                    str(raw_mp3),
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-acodec",
                    "libmp3lame",
                    "-b:a",
                    "128k",
                    str(norm_mp3),
                ],
                capture_output=True,
                timeout=30,
            )
            dur, _ = probe_media_info(norm_mp3)
            if dur <= 0.4:
                dur = 3.5

            start_s = round(cursor, 3)
            end_s = round(cursor + dur, 3)
            subtitles.append(
                {
                    "start_sec": start_s,
                    "end_sec": end_s,
                    "source_text": en,
                    "target_text": zh,
                }
            )
            concat_entries.append(f"file '{norm_mp3}'")
            concat_entries.append(f"file '{silence_mp3}'")
            cursor = end_s + 0.45

        concat_txt = tmp_dir / "concat.txt"
        concat_txt.write_text("\n".join(concat_entries) + "\n", encoding="utf-8")
        full_audio = tmp_dir / "full_narration.mp3"
        subprocess.run(
            [
                resolve_ffmpeg_bin(),
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_txt),
                "-c",
                "copy",
                str(full_audio),
            ],
            capture_output=True,
            timeout=60,
        )

        # Render crisp 1280x720 MP4 video with subtle cinematic breathing zoom from cover image
        total_dur, _ = probe_media_info(full_audio)
        if total_dur <= 1:
            total_dur = cursor + 0.5

        if cover_img.exists():
            vf = (
                "scale=1280:720:force_original_aspect_ratio=increase,"
                "crop=1280:720,"
                "fps=24"
            )
            cmd = [
                resolve_ffmpeg_bin(),
                "-y",
                "-loop",
                "1",
                "-framerate",
                "24",
                "-i",
                str(cover_img),
                "-i",
                str(full_audio),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-tune",
                "stillimage",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                "-shortest",
                str(video_out),
            ]
        else:
            cmd = [
                resolve_ffmpeg_bin(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=#1B1330:s=1280x720:d={total_dur:.2f}",
                "-i",
                str(full_audio),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                "-shortest",
                str(video_out),
            ]
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)

    srt_content = build_srt_content(subtitles, bilingual=True)
    (ep_dir / "source.srt").write_text(srt_content, encoding="utf-8")
    return video_out, srt_content


async def ensure_demo_seeded() -> None:
    """Seed two real playable English demo episodes on first boot if database is empty."""
    with db_session() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        if cnt > 0:
            return

    logger.info("Database is empty; seeding 2 real demo episodes...")
    for spec in DEMO_EPISODES:
        now = now_iso()
        with db_session() as conn:
            cur = conn.execute(
                """
                INSERT INTO episodes (
                    title, description, series_name, episode_number, source_lang, target_lang,
                    difficulty, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'en', 'zh-CN', ?, 'queued', ?, ?)
                """,
                (
                    spec["title"],
                    spec["description"],
                    spec["series_name"],
                    spec["episode_number"],
                    spec["difficulty"],
                    now,
                    now,
                ),
            )
            ep_id = int(cur.lastrowid)

        ep_dir = MEDIA_DIR / f"ep_{ep_id}"
        video_file, srt_text = await _build_demo_media_and_srt(spec, ep_dir)
        await run_decomposition_pipeline(ep_id, video_file, subtitle_content=srt_text)

    # Bookmark 3 useful phrases on Episode 1 so Personal Vocab Deck isn't empty on first view
    with db_session() as conn:
        conn.execute(
            "UPDATE entries SET is_bookmarked = 1 WHERE lemma_key IN ('break down', 'sink in', 'in the long run')"
        )
    logger.info("Demo episodes seeded and decomposed successfully.")
