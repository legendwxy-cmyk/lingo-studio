#!/usr/bin/env python3
"""
Lingo Onboarding Tutorial Video — Audio & Exact Timeline Builder (v2 — crisp ~2m15s pacing)
1. Synthesizes all 26 crisp conversational Chinese voiceover chunks via edge-tts (zh-CN-XiaoxiaoNeural, +6%)
2. Trims leading/trailing silence cleanly and measures exact WAV duration
3. Builds exact timeline.json (chapters, cues, proportional subtitle splits, sfxEvents)
4. Synthesizes warm electric-piano tutorial BGM (3.6kHz low-pass) & tactile UI SFX (band-separated)
5. Mixes VO + BGM (ducked under speech) + SFX into audio_master.m4a and verifies via ffprobe
"""
import asyncio
import json
import math
import pathlib
import shutil
import subprocess
import wave
import numpy as np
import edge_tts

ROOT = pathlib.Path(__file__).resolve().parent
AUDIO_DIR = ROOT / "audio"
CHUNKS_DIR = AUDIO_DIR / "chunks"
SFX_DIR = AUDIO_DIR / "sfx"
if CHUNKS_DIR.exists():
    shutil.rmtree(CHUNKS_DIR)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
SFX_DIR.mkdir(parents=True, exist_ok=True)

SR = 44100
VOICE = "zh-CN-XiaoxiaoNeural"
RATE = "+6%"

# 26 crisp, crystal-clear spoken chunks (~2 min 15 sec total, covering all 7 chapters completely)
CHUNKS = [
    # S01: 开场亮相与 DMG 拖拽安装
    {
        "id": "c01", "scene": "S01", "cue": "intro_logo",
        "text": "你好！只需两分钟，手把手带你从零装好并用好 Lingo 英语精听学习机。",
        "subs": ["你好！只需两分钟", "带你从零装好并用好 Lingo"],
        "sfx": [(0.05, "chime", 0.36)],
    },
    {
        "id": "c02", "scene": "S01", "cue": "dmg_open",
        "text": "第一步，双击打开 Lingo 安装包，把左边图标直接拖进右边的应用程序文件夹。",
        "subs": ["第一步：双击打开 Lingo 安装包", "将图标拖进「应用程序」文件夹"],
        "sfx": [(0.12, "whoosh", 0.32), (2.4, "click", 0.44)],
    },
    {
        "id": "c03", "scene": "S01", "cue": "dmg_done",
        "text": "拷贝完成，软件就装好了。",
        "subs": ["拷贝完成，安装就搞定了"],
        "sfx": [(0.45, "chime", 0.42)],
    },

    # S02: 调整 Mac 隐私与安全性开关
    {
        "id": "c04", "scene": "S02", "cue": "mac_block",
        "text": "第二步很关键。首次打开若提示无法验证开发者，别担心，先点完成关闭弹窗。",
        "subs": ["首次打开若提示无法验证开发者", "别担心，先点「完成」关闭弹窗"],
        "sfx": [(0.0, "whoosh", 0.32), (4.2, "click", 0.45)],
    },
    {
        "id": "c05", "scene": "S02", "cue": "mac_settings",
        "text": "打开 Mac 系统设置，点进隐私与安全性，向下滑到安全性一栏。",
        "subs": ["打开系统设置 → 隐私与安全性", "向下滑到「安全性」一栏"],
        "sfx": [(1.4, "click", 0.40)],
    },
    {
        "id": "c06", "scene": "S02", "cue": "mac_open_anyway",
        "text": "找到已阻止使用 Lingo，点击右侧仍要打开并输入密码，一次永久放行。",
        "subs": ["点击右侧「仍要打开」输入密码", "一次放行，以后不再拦截"],
        "sfx": [(2.2, "click", 0.48), (3.8, "chime", 0.42)],
    },
    {
        "id": "c07", "scene": "S02", "cue": "mac_local_net",
        "text": "顺手开启下面两个开关：本地网络让平板能连上电脑，麦克风用来录音跟读对比。",
        "subs": ["顺手开启「本地网络」与「麦克风」", "方便平板连接与网页跟读录音"],
        "sfx": [(1.6, "toggle", 0.48), (3.6, "toggle", 0.48)],
    },
    {
        "id": "c08", "scene": "S02", "cue": "mac_tip",
        "text": "小技巧：也可以在应用程序里右键点击 Lingo 选择打开。",
        "subs": ["小技巧：也可右键 Lingo 选「打开」"],
        "sfx": [(0.5, "pop", 0.34)],
    },

    # S03: 免命令行初始化与环境依赖自检
    {
        "id": "c09", "scene": "S03", "cue": "hud_init",
        "text": "第三步，环境与依赖自检。首次启动会弹出原生进度浮窗自动准备，全程免开黑色命令行。",
        "subs": ["首次启动由原生进度浮窗自动准备", "全程免开黑色命令行敲指令"],
        "sfx": [(0.0, "whoosh", 0.32), (4.4, "chime", 0.38)],
    },
    {
        "id": "c10", "scene": "S03", "cue": "env_open",
        "text": "进入桌面控制台，点开顶部的环境与依赖页。",
        "subs": ["进入桌面控制台，切到「环境与依赖」"],
        "sfx": [(0.1, "whoosh", 0.30), (1.6, "click", 0.42)],
    },
    {
        "id": "c11", "scene": "S03", "cue": "env_check",
        "text": "确认独立环境、核心引擎、音视频解码与离线语音模型五项全绿已就绪。",
        "subs": ["确认右侧五项全部亮绿「已就绪」"],
        "sfx": [(1.0, "pop", 0.28), (2.4, "pop", 0.28), (3.6, "chime", 0.40)],
    },
    {
        "id": "c12", "scene": "S03", "cue": "env_repair",
        "text": "若有黄或红项，点左上修复更新依赖，内置国内加速镜像会自动一键补齐。",
        "subs": ["如有缺失点左上「修复 / 更新依赖」", "内置国内加速镜像，全自动一键补齐"],
        "sfx": [(1.8, "pop", 0.34)],
    },

    # S04: 配置端口、开启局域网共享与发布网站
    {
        "id": "c13", "scene": "S04", "cue": "pub_tab",
        "text": "第四步，一键发布学习机网站。回到服务总览页，默认端口 8000 不用改动。",
        "subs": ["第四步：回到「服务总览」发布网站", "默认端口 8000 保持默认即可"],
        "sfx": [(0.0, "whoosh", 0.30), (2.2, "click", 0.42)],
    },
    {
        "id": "c14", "scene": "S04", "cue": "pub_lan",
        "text": "重点拨开局域网共享绿色开关，允许同 Wi-Fi 的平板和手机访问；家里自用，下方口令锁可留空。",
        "subs": ["重点：拨开「局域网共享」绿色开关", "家里自用口令锁可留空免密直进"],
        "sfx": [(1.2, "toggle", 0.50), (4.2, "pop", 0.30)],
    },
    {
        "id": "c15", "scene": "S04", "cue": "pub_onair",
        "text": "启动服务，看到 8000 运行中与下方局域网地址亮起，网站就发布成功了！",
        "subs": ["看到 8000 运行中与局域网网址", "说明学习机网站已发布成功"],
        "sfx": [(0.8, "click", 0.44), (2.4, "chime", 0.45)],
    },

    # S05: 电脑浏览器上手使用
    {
        "id": "c16", "scene": "S05", "cue": "web_open",
        "text": "第五步，电脑浏览器上手使用。点在浏览器打开学习机，一键直达 Lingo 网页端。",
        "subs": ["点击「在浏览器打开学习机」", "一键直达 Lingo 网页学习机"],
        "sfx": [(0.0, "whoosh", 0.30), (2.4, "click", 0.44)],
    },
    {
        "id": "c17", "scene": "S05", "cue": "web_upload",
        "text": "进资料库直接拖入英语视频或音频，自动完成语音识别、精准分句与双语精析。",
        "subs": ["进「资料库」拖入英语视频或音频", "自动转写、分句与双语精析"],
        "sfx": [(0.4, "click", 0.40), (2.2, "pop", 0.36)],
    },
    {
        "id": "c18", "scene": "S05", "cue": "web_shadow",
        "text": "回到学习机，支持单句循环和音标精听；点跟读对比后可边听原文边连续跟读，自动逐句存到对应句子下方。",
        "subs": ["支持单句循环、音标与连续跟读对比", "边播边读，自动逐句归类存档"],
        "sfx": [(0.2, "whoosh", 0.28), (2.6, "click", 0.42), (4.8, "pop", 0.34)],
    },
    {
        "id": "c19", "scene": "S05", "cue": "web_skin",
        "text": "右上角还能一键切换三套玩味 3D 皮肤。",
        "subs": ["右上角一键切换三套 3D 主题皮肤"],
        "sfx": [(0.9, "click", 0.40)],
    },

    # S06: 同一局域网用平板电脑访问
    {
        "id": "c20", "scene": "S06", "cue": "ipad_intro",
        "text": "第六步，用平板电脑大屏访问，完全不用在平板上装任何 App。",
        "subs": ["第六步：平板大屏精听，免装任何 App"],
        "sfx": [(0.0, "whoosh", 0.34)],
    },
    {
        "id": "c21", "scene": "S06", "cue": "ipad_wifi",
        "text": "只需确认 Mac 和平板连着同一个 Wi-Fi，且电脑端服务正在运行。",
        "subs": ["确认 Mac 与平板连在同一个 Wi-Fi", "且电脑端 Lingo 服务保持运行"],
        "sfx": [(1.4, "pop", 0.32), (3.0, "pop", 0.32)],
    },
    {
        "id": "c22", "scene": "S06", "cue": "ipad_copy",
        "text": "看电脑控制台显示的局域网地址，比如 192.168.1.28 冒号 8000。",
        "subs": ["查看控制台「局域网访问地址」", "例如 http://192.168.1.28:8000"],
        "sfx": [(1.6, "click", 0.42)],
    },
    {
        "id": "c23", "scene": "S06", "cue": "ipad_type",
        "text": "打开平板浏览器，在地址栏输入这串网址并前往。",
        "subs": ["在平板浏览器输入这串网址并前往"],
        "sfx": [(1.2, "type", 0.42), (2.8, "click", 0.44)],
    },
    {
        "id": "c24", "scene": "S06", "cue": "ipad_ready",
        "text": "一秒直达完整学习机！课程、生词本与跟读记录实时同步，手机用同样方法也能随时学。",
        "subs": ["一秒同步大屏精听，记录全共享", "手机用同样方法也能随时打开"],
        "sfx": [(0.15, "chime", 0.45)],
    },

    # S07: 四步速记与收尾
    {
        "id": "c25", "scene": "S07", "cue": "recap_cards",
        "text": "最后记住四步：拖入安装、隐私点仍要打开、一键开启局域网发布、电脑与平板双端精听。",
        "subs": ["四步速记：安装 → 隐私放行", "一键发布 → 电脑与平板双端精听"],
        "sfx": [(0.0, "whoosh", 0.30), (1.3, "pop", 0.32), (2.4, "pop", 0.32), (3.6, "pop", 0.32), (4.8, "pop", 0.32)],
    },
    {
        "id": "c26", "scene": "S07", "cue": "outro_logo",
        "text": "现在就打开 Lingo，精听每一句吧。",
        "subs": ["打开 Lingo，精听每一句"],
        "sfx": [(0.4, "chime", 0.42)],
    },
]


def save_wav(path: pathlib.Path, stereo: np.ndarray, sr: int = SR):
    if stereo.ndim == 1:
        stereo = np.stack([stereo, stereo], axis=1)
    clipped = np.clip(stereo, -0.99, 0.99)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def read_wav_float(path: pathlib.Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        ch = wf.getnchannels()
        n = wf.getnframes()
        raw = wf.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch == 2:
        return data.reshape(-1, 2)
    return np.stack([data, data], axis=1)


async def generate_all_tts():
    sem = asyncio.Semaphore(6)

    async def gen_one(item):
        mp3_path = CHUNKS_DIR / f"{item['id']}.mp3"
        wav_path = CHUNKS_DIR / f"{item['id']}.wav"
        async with sem:
            comm = edge_tts.Communicate(item["text"], voice=VOICE, rate=RATE)
            await comm.save(str(mp3_path))
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(mp3_path),
            "-af", (
                "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-45dB,"
                "areverse,"
                "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB,"
                "areverse,"
                "highpass=f=85,aresample=44100"
            ),
            "-ac", "2", "-c:a", "pcm_s16le",
            str(wav_path),
        ]
        subprocess.run(cmd, check=True)

    await asyncio.gather(*(gen_one(item) for item in CHUNKS))


def synth_sfx():
    t = np.linspace(0, 0.045, int(SR * 0.045), endpoint=False)
    rng = np.random.default_rng(101)
    click = (
        0.55 * np.sin(2 * np.pi * 1650 * t) * np.exp(-t * 145)
        + 0.35 * np.sin(2 * np.pi * 3100 * t) * np.exp(-t * 210)
        + 0.25 * rng.standard_normal(len(t)) * np.exp(-t * 280)
    )
    save_wav(SFX_DIR / "click.wav", click * 0.72)

    t = np.linspace(0, 0.09, int(SR * 0.09), endpoint=False)
    p1 = np.sin(2 * np.pi * 880 * t) * np.exp(-t * 95)
    t2 = np.maximum(0, t - 0.024)
    p2 = (t >= 0.024) * np.sin(2 * np.pi * 1480 * t2) * np.exp(-t2 * 80)
    save_wav(SFX_DIR / "toggle.wav", (0.45 * p1 + 0.58 * p2) * 0.72)

    t = np.linspace(0, 0.075, int(SR * 0.075), endpoint=False)
    freq = 640 + 420 * np.exp(-t * 70)
    pop = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 68) * np.minimum(1.0, t / 0.004)
    save_wav(SFX_DIR / "pop.wav", pop * 0.68)

    t = np.linspace(0, 0.48, int(SR * 0.48), endpoint=False)
    env1 = np.minimum(1.0, t / 0.006) * np.exp(-t * 9.5)
    n1 = (0.75 * np.sin(2 * np.pi * 1046.5 * t) + 0.22 * np.sin(2 * np.pi * 2093.0 * t)) * env1
    t2 = np.maximum(0, t - 0.085)
    env2 = (t >= 0.085) * np.minimum(1.0, t2 / 0.006) * np.exp(-t2 * 7.8)
    n2 = (0.78 * np.sin(2 * np.pi * 1567.98 * t2) + 0.18 * np.sin(2 * np.pi * 3135.96 * t2)) * env2
    save_wav(SFX_DIR / "chime.wav", (0.55 * n1 + 0.62 * n2) * 0.65)

    t = np.linspace(0, 0.26, int(SR * 0.26), endpoint=False)
    rng = np.random.default_rng(202)
    raw = rng.standard_normal(len(t))
    bp = np.convolve(raw, np.ones(18) / 18.0, mode="same") - np.convolve(raw, np.ones(65) / 65.0, mode="same")
    whoosh = bp * (np.sin(np.pi * t / 0.26) ** 1.6) * 1.4
    save_wav(SFX_DIR / "whoosh.wav", whoosh * 0.55)

    dur = 1.40
    buf = np.zeros(int(SR * dur), dtype=np.float32)
    rng = np.random.default_rng(303)
    offsets = [0.00, 0.09, 0.17, 0.26, 0.34, 0.43, 0.51, 0.61, 0.70, 0.78, 0.87, 0.96, 1.05, 1.15, 1.24]
    kt = np.linspace(0, 0.032, int(SR * 0.032), endpoint=False)
    for i, off in enumerate(offsets):
        idx = int(off * SR)
        f = 1850 + (i % 4) * 180
        tap = (0.45 * np.sin(2 * np.pi * f * kt) + 0.35 * rng.standard_normal(len(kt))) * np.exp(-kt * 210)
        end = min(len(buf), idx + len(tap))
        buf[idx:end] += tap[:end - idx] * 0.55
    save_wav(SFX_DIR / "type.wav", buf)


def synth_warm_rhodes_bgm(total_sec: float) -> np.ndarray:
    n_samples = int(math.ceil(total_sec * SR))
    left = np.zeros(n_samples, dtype=np.float64)
    right = np.zeros(n_samples, dtype=np.float64)

    beat = 60.0 / 86.0
    bar = beat * 4.0

    def m2f(m):
        return 440.0 * (2.0 ** ((m - 69) / 12.0))

    prog = [
        ([48, 55, 59, 62, 64], [67, 71, 64, 62]),
        ([45, 52, 55, 59, 60], [64, 67, 62, 60]),
        ([53, 57, 60, 64, 67], [69, 67, 64, 60]),
        ([55, 59, 62, 64, 67], [71, 69, 67, 62]),
    ]

    def add_rhodes_note(start_s: float, dur_s: float, midi: int, amp: float, pan: float = 0.0):
        i0 = int(start_s * SR)
        if i0 >= n_samples:
            return
        n = min(int(dur_s * SR), n_samples - i0)
        if n <= 0:
            return
        t = np.arange(n, dtype=np.float64) / SR
        f = m2f(midi)
        attack = np.minimum(1.0, t / 0.016)
        decay = np.exp(-t * (1.25 if midi < 60 else 1.75))
        release = np.minimum(1.0, np.maximum(0.0, (dur_s - t) / 0.14))
        env = attack * decay * release
        trem = 1.0 + 0.045 * np.sin(2 * np.pi * 3.2 * t)
        sig = (
            0.78 * np.sin(2 * np.pi * f * t)
            + 0.17 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 3.8)
            + 0.05 * np.sin(2 * np.pi * 3 * f * t) * np.exp(-t * 7.5)
        ) * env * trem * amp
        gl = math.sqrt(0.5 * (1.0 - pan))
        gr = math.sqrt(0.5 * (1.0 + pan))
        left[i0:i0 + n] += sig * gl
        right[i0:i0 + n] += sig * gr

    t_bar = 0.0
    bar_idx = 0
    while t_bar < total_sec - 0.5:
        chord, arp = prog[bar_idx % len(prog)]
        for idx, m in enumerate(chord):
            add_rhodes_note(t_bar + idx * 0.032, bar * 0.96, m, 0.14 if idx == 0 else 0.095, pan=-0.25 + 0.125 * idx)
        add_rhodes_note(t_bar + beat * 1.5, beat * 1.6, arp[0], 0.062, pan=0.28)
        add_rhodes_note(t_bar + beat * 2.5, beat * 1.4, arp[1], 0.055, pan=-0.24)
        add_rhodes_note(t_bar + beat * 3.5, beat * 1.1, arp[2], 0.050, pan=0.22)
        t_bar += bar
        bar_idx += 1

    res_t = max(0.0, total_sec - 2.4)
    for idx, m in enumerate([48, 55, 60, 64, 67]):
        add_rhodes_note(res_t + idx * 0.04, 2.3, m, 0.11, pan=-0.2 + 0.1 * idx)

    stereo = np.stack([left, right], axis=1)
    peak = np.max(np.abs(stereo)) + 1e-9
    stereo = stereo / peak * 0.72
    fi = min(int(1.2 * SR), n_samples)
    fo = min(int(2.2 * SR), n_samples)
    stereo[:fi] *= np.linspace(0.0, 1.0, fi)[:, None]
    stereo[-fo:] *= np.linspace(1.0, 0.0, fo)[:, None]
    return stereo.astype(np.float32)


def main():
    print("1/5 Generating 26 crisp Neural Chinese voiceover chunks (+6% rate)...")
    asyncio.run(generate_all_tts())

    print("2/5 Measuring exact durations & assembling timeline.json...")
    LEAD_IN = 0.50
    INTRA_PAUSE = 0.24
    CHAPTER_PAUSE = 0.62
    OUTRO_HOLD = 1.85

    cursor = LEAD_IN
    prev_scene = None
    cues_out = {}
    chunks_timeline = []
    chapters = {}
    sfx_events = []
    vo_segments = []

    for item in CHUNKS:
        if prev_scene is not None:
            cursor += CHAPTER_PAUSE if item["scene"] != prev_scene else INTRA_PAUSE
        wav_path = CHUNKS_DIR / f"{item['id']}.wav"
        data = read_wav_float(wav_path)
        dur = len(data) / SR
        start = round(cursor, 3)
        end = round(cursor + dur, 3)

        subs_list = item["subs"]
        lengths = [max(1, len(s)) for s in subs_list]
        tot_chars = sum(lengths)
        sub_cursor = start
        subs_timed = []
        for idx, s_txt in enumerate(subs_list):
            s_end = end if idx == len(subs_list) - 1 else round(sub_cursor + dur * (lengths[idx] / tot_chars), 3)
            subs_timed.append({"start": round(sub_cursor, 3), "end": s_end, "text": s_txt})
            sub_cursor = s_end

        for rel_t, sfx_name, gain in item.get("sfx", []):
            ev_t = round(start + min(rel_t, max(0.0, dur - 0.05)), 3)
            sfx_events.append({"time": ev_t, "type": sfx_name, "gain": gain, "cue": item["cue"]})

        entry = {
            "id": item["id"], "scene": item["scene"], "cue": item["cue"],
            "start": start, "end": end, "duration": round(dur, 3),
            "text": item["text"], "subs": subs_timed,
        }
        chunks_timeline.append(entry)
        cues_out[item["cue"]] = entry

        sc = item["scene"]
        if sc not in chapters:
            chapters[sc] = {"scene": sc, "start": start, "end": end}
        else:
            chapters[sc]["end"] = end

        vo_segments.append((start, data))
        cursor = end
        prev_scene = sc

    total_duration = round(cursor + OUTRO_HOLD, 3)
    scene_order = ["S01", "S02", "S03", "S04", "S05", "S06", "S07"]
    for i, sc in enumerate(scene_order):
        if i == 0:
            chapters[sc]["start"] = 0.0
        if i < len(scene_order) - 1:
            nxt = scene_order[i + 1]
            next_first = next(c["start"] for c in chunks_timeline if c["scene"] == nxt)
            split_t = round(next_first - 0.34, 3)
            chapters[sc]["end"] = split_t
            chapters[nxt]["start"] = split_t
        else:
            chapters[sc]["end"] = total_duration

    timeline = {
        "fps": 30, "width": 1920, "height": 1080,
        "totalDuration": total_duration, "voice": VOICE, "rate": RATE,
        "chapters": [chapters[s] for s in scene_order],
        "cues": cues_out, "chunks": chunks_timeline, "sfxEvents": sfx_events,
    }
    (ROOT / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   Measured totalDuration = {total_duration:.2f}s across {len(chunks_timeline)} chunks")
    for ch in timeline["chapters"]:
        print(f"   {ch['scene']}: {ch['start']:.2f}s -> {ch['end']:.2f}s ({ch['end']-ch['start']:.2f}s)")

    print("3/5 Synthesizing tactile UI SFX & warm Rhodes BGM...")
    synth_sfx()
    bgm_raw = synth_warm_rhodes_bgm(total_duration)
    bgm_raw_path = AUDIO_DIR / "bgm_raw.wav"
    bgm_lp_path = AUDIO_DIR / "bgm_lp.wav"
    save_wav(bgm_raw_path, bgm_raw)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(bgm_raw_path),
        "-af", "lowpass=f=3600,highpass=f=55",
        "-ac", "2", "-ar", str(SR), "-c:a", "pcm_s16le", str(bgm_lp_path)
    ], check=True)

    print("4/5 Mixing VO + Speech-Ducked BGM + Band-Separated SFX...")
    n_tot = int(math.ceil(total_duration * SR))
    vo_bus = np.zeros((n_tot, 2), dtype=np.float32)
    speech_mask = np.zeros(n_tot, dtype=np.float32)
    for start_s, seg in vo_segments:
        i0 = int(start_s * SR)
        end = min(n_tot, i0 + len(seg))
        vo_bus[i0:end] += seg[:end - i0]
        speech_mask[max(0, i0 - int(0.14 * SR)):min(n_tot, end + int(0.22 * SR))] = 1.0

    win = int(0.22 * SR)
    smooth_speech = np.convolve(speech_mask, np.ones(win, dtype=np.float32) / win, mode="same")
    bgm_gain = 0.23 - 0.088 * smooth_speech

    bgm_lp = read_wav_float(bgm_lp_path)
    bgm_bus = np.zeros((n_tot, 2), dtype=np.float32)
    m = min(n_tot, len(bgm_lp))
    bgm_bus[:m] = bgm_lp[:m] * bgm_gain[:m, None]

    sfx_cache = {p.stem: read_wav_float(p) for p in SFX_DIR.glob("*.wav")}
    sfx_bus = np.zeros((n_tot, 2), dtype=np.float32)
    for ev in sfx_events:
        clip = sfx_cache.get(ev["type"])
        if clip is None:
            continue
        i0 = int(ev["time"] * SR)
        end = min(n_tot, i0 + len(clip))
        if end > i0:
            sfx_bus[i0:end] += clip[:end - i0] * float(ev["gain"])

    vo_active = vo_bus[speech_mask > 0.5]
    vo_rms = float(np.sqrt(np.mean(vo_active ** 2)) + 1e-9)
    vo_bus = vo_bus * (0.195 / vo_rms)

    save_wav(AUDIO_DIR / "voiceover.wav", vo_bus)
    master = vo_bus + bgm_bus + sfx_bus
    peak = float(np.max(np.abs(master)))
    if peak > 0.94:
        master = np.tanh(master / 0.94) * 0.94
    master_wav = AUDIO_DIR / "audio_master.wav"
    master_m4a = AUDIO_DIR / "audio_master.m4a"
    save_wav(master_wav, master)

    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(master_wav),
        "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-ac", "2", str(master_m4a)
    ], check=True)

    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_name,sample_rate,channels,duration",
        "-of", "default=noprint_wrappers=1", str(master_m4a)
    ], text=True)
    print(out.strip())
    print("AUDIO_V2_OK")


if __name__ == "__main__":
    main()
