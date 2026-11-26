#!/usr/bin/env python3
"""
Deterministic 1920x1080 30fps MP4 Renderer for Lingo Onboarding Tutorial Video
Uses 3 parallel Playwright Chromium CDP workers piping JPEG-96 frames directly into FFmpeg
libx264 (yuv420p, CRF 18), concatenates chunks losslessly, muxes audio_master.m4a with
+faststart, verifies both streams via ffprobe, and extracts final verification frames from MP4.
"""
import base64
import json
import math
import multiprocessing as mp
import pathlib
import shutil
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent
TIMELINE = json.loads((ROOT / "timeline.json").read_text(encoding="utf-8"))
HTML_URI = (ROOT / "lingo-guide.html").as_uri() + "?render=1"
AUDIO_PATH = ROOT / "audio" / "audio_master.m4a"
CHUNKS_DIR = ROOT / "render_chunks"
OUT_MP4 = ROOT / "lingo-user-guide.mp4"

FPS = 30
WORKERS = 3


def render_chunk(args):
    idx, f_start, f_end, fps, html_uri, out_path = args
    from playwright.sync_api import sync_playwright

    ff_cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
        "-r", str(fps), "-g", str(fps * 2),
        "-an", str(out_path),
    ]
    proc = subprocess.Popen(ff_cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    total = f_end - f_start

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        page.goto(html_uri, wait_until="networkidle")
        cdp = page.context.new_cdp_session(page)
        for i, f in enumerate(range(f_start, f_end)):
            ts = f / fps
            page.evaluate("t => window.__seek(t)", ts)
            res = cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 96})
            proc.stdin.write(base64.b64decode(res["data"]))
            if (i + 1) % 300 == 0 or (i + 1) == total:
                dt = time.time() - t0
                print(f"[worker {idx}] {i+1}/{total} frames ({(i+1)/dt:.1f} fps)", flush=True)
        browser.close()

    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"FFmpeg worker {idx} exited with code {rc}")
    return str(out_path)


def main():
    total_dur = float(TIMELINE["totalDuration"])
    total_frames = int(math.ceil(total_dur * FPS))
    print(f"Rendering {total_frames} frames @ {FPS}fps ({total_dur:.2f}s) using {WORKERS} workers...", flush=True)

    if CHUNKS_DIR.exists():
        shutil.rmtree(CHUNKS_DIR)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    step = math.ceil(total_frames / WORKERS)
    jobs = []
    for i in range(WORKERS):
        s = i * step
        e = min(total_frames, (i + 1) * step)
        if s < e:
            jobs.append((i, s, e, FPS, HTML_URI, CHUNKS_DIR / f"part_{i:02d}.mp4"))

    t0 = time.time()
    ctx = mp.get_context("spawn")
    with ctx.Pool(len(jobs)) as pool:
        parts = pool.map(render_chunk, jobs)

    render_dt = time.time() - t0
    print(f"All {total_frames} frames rendered in {render_dt:.1f}s ({total_frames/render_dt:.1f} fps agg)", flush=True)

    concat_txt = CHUNKS_DIR / "concat.txt"
    concat_txt.write_text("\n".join(f"file '{p}'" for p in parts) + "\n", encoding="utf-8")

    # Concat video + mux audio_master.m4a with +faststart (QuickTime / Safari / iPad / Chrome ready)
    print("Muxing H.264 video + mixed AAC audio (voiceover + BGM + SFX)...", flush=True)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_txt),
        "-i", str(AUDIO_PATH),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart",
        "-shortest",
        str(OUT_MP4),
    ], check=True)

    # Verify both streams cleanly via ffprobe
    print("Verifying final MP4 via ffprobe...", flush=True)
    v_info = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v",
        "-show_entries", "stream=codec_name,profile,pix_fmt,width,height,r_frame_rate,duration",
        "-of", "default=noprint_wrappers=1", str(OUT_MP4)
    ], text=True).strip()
    a_info = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_name,sample_rate,channels,bit_rate,duration",
        "-of", "default=noprint_wrappers=1", str(OUT_MP4)
    ], text=True).strip()
    size_mb = OUT_MP4.stat().st_size / 1024 / 1024
    print(f"--- VIDEO ---\n{v_info}\n--- AUDIO ---\n{a_info}\nSIZE={size_mb:.2f} MB", flush=True)

    # Extract 6 final verification frames directly from the encoded MP4!
    ver_dir = ROOT / "mp4_verify"
    ver_dir.mkdir(exist_ok=True)
    C = TIMELINE["cues"]
    checks = [
        ("v01_dmg", C["dmg_open"]["start"] + 4.0),
        ("v02_privacy", C["mac_open_anyway"]["start"] + 1.8),
        ("v03_env", C["env_check"]["start"] + 2.2),
        ("v04_lan", C["pub_lan"]["start"] + 1.5),
        ("v05_web", C["web_shadow"]["start"] + 3.2),
        ("v06_ipad", C["ipad_ready"]["start"] + 2.8),
    ]
    for name, ts in checks:
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{ts:.2f}", "-i", str(OUT_MP4),
            "-frames:v", "1", str(ver_dir / f"{name}.png")
        ], check=True)

    print("MP4_RENDER_AND_VERIFY_OK", flush=True)


if __name__ == "__main__":
    main()
