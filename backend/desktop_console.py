#!/usr/bin/env python3
"""
Lingo（LingoReel Studio）可视化桌面控制台 + 运行环境自检与一键安装器。

设计原则：
1. 仅依赖 Python 标准库（http.server / sqlite3 / urllib / subprocess / threading），
   即使在用户电脑尚未安装任何 pip 依赖时，桌面控制台 GUI 也能第一时间弹出，
   直观展示每一项缺失的运行环境并提供「一键安装 / 修复」按钮！
2. 支持可视化配置端口、局域网共享、访问口令、国内加速镜像，绑定各大模型与 Whisper API，
   并一键启动/停止/重启学习机网站服务、打开网页与查看实时日志。
"""
from __future__ import annotations

import argparse
import atexit
import collections
import hashlib
import json
import mimetypes
import os
import platform
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("LINGOREEL_DATA_DIR", str(BASE_DIR / "data"))).expanduser().resolve()
DB_PATH = DATA_DIR / "lexifilm.db"
CONFIG_PATH = DATA_DIR / "desktop_config.json"
FRONTEND_DIST = Path(
    os.getenv("LINGOREEL_FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist"))
).expanduser().resolve()

DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_frontend_build_id(dist_dir: Path | None = None) -> str:
    root = dist_dir or FRONTEND_DIST
    marker = root / ".lingo_build_id"
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
        fp = root / name
        if fp.is_file():
            found = True
            h.update(name.encode("utf-8"))
            h.update(b"\x00")
            h.update(fp.read_bytes())
            h.update(b"\x00")
    return h.hexdigest()[:12] if found else ""


def probe_lingoreel_health(port: int, timeout: float = 1.2) -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            obj = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if isinstance(obj, dict) and obj.get("service") == "lingoreel-studio":
                return obj
    except Exception:
        return None
    return None


def _find_uvicorn_listener_pids(port: int) -> list[int]:
    lsof_bin = shutil.which("lsof") or ("/usr/sbin/lsof" if Path("/usr/sbin/lsof").is_file() else None)
    if not lsof_bin:
        return []
    try:
        res = subprocess.run(
            [lsof_bin, "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        pids: list[int] = []
        for tok in (res.stdout or "").split():
            if not tok.isdigit():
                continue
            pid = int(tok)
            if pid <= 1 or pid == os.getpid():
                continue
            ps = subprocess.run(["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True, timeout=2)
            cmdline = (ps.stdout or "").lower()
            if "uvicorn" in cmdline and "main:app" in cmdline:
                pids.append(pid)
        return pids
    except Exception:
        return []


def retire_stale_lingo_backend(port: int, log_fn: Any = None) -> bool:
    health = probe_lingoreel_health(port)
    if health is None:
        return False
    if log_fn:
        log_fn(f"检测到端口 {port} 运行着旧版后台服务，正在自动平滑切换至当前最新 Lingo 版本...")
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/system/shutdown",
            data=b"",
            method="POST",
            headers={"Origin": f"http://127.0.0.1:{port}"},
        )
        with urllib.request.urlopen(req, timeout=2.0):
            pass
    except Exception:
        pass

    for _ in range(25):
        if not is_port_in_use(port):
            return True
        time.sleep(0.1)

    candidate_pids: list[int] = []
    hp = health.get("pid")
    if isinstance(hp, int) and hp > 1 and hp != os.getpid():
        candidate_pids.append(hp)
    for pid in _find_uvicorn_listener_pids(port):
        if pid not in candidate_pids:
            candidate_pids.append(pid)

    for pid in candidate_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    for _ in range(25):
        if not is_port_in_use(port):
            return True
        time.sleep(0.1)
    return not is_port_in_use(port)

SECRET_MASK_MARKER = "••••"
SECRET_KEYS = ("asr_api_key", "llm_api_key")

DEFAULT_DESKTOP_CONFIG: dict[str, Any] = {
    "port": 8000,
    "lan_access": False,
    "access_password": "",
    "hf_mirror": True,
    "auto_start_service": False,
}

DEFAULT_ENGINE_SETTINGS: dict[str, str] = {
    "asr_mode": "auto",
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

REQUIRED_PACKAGES: list[tuple[str, str]] = [
    ("fastapi", "FastAPI 接口框架"),
    ("uvicorn", "Uvicorn 网站服务"),
    ("multipart", "文件上传解析"),
    ("httpx", "异步网络客户端"),
    ("eng_to_ipa", "CMUdict 音标引擎"),
    ("faster_whisper", "本地离线 Whisper"),
    ("numpy", "音频 PCM 信号分析"),
]


def _default_venv_dir() -> Path:
    env_v = os.getenv("LINGOREEL_VENV_DIR", "").strip()
    if env_v:
        return Path(env_v).expanduser().resolve()
    local_v = BASE_DIR / ".venv"
    if local_v.exists():
        return local_v
    if platform.system() == "Darwin":
        app_sup = Path.home() / "Library" / "Application Support" / "LingoReelStudio" / ".venv"
        if app_sup.exists() or os.getenv("LINGOREEL_DESKTOP_APP") == "1":
            return app_sup
    return local_v


def get_venv_dir() -> Path:
    return _default_venv_dir()


def get_venv_python() -> Path | None:
    venv = get_venv_dir()
    for cand in (venv / "bin" / "python", venv / "bin" / "python3", venv / "Scripts" / "python.exe"):
        if cand.is_file():
            return cand
    return None


def mask_secret(val: str) -> str:
    s = (val or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return SECRET_MASK_MARKER
    return f"{s[:3]}{SECRET_MASK_MARKER}{s[-4:]}"


def is_masked_secret(val: str | None) -> bool:
    return bool(val and SECRET_MASK_MARKER in str(val))


def _ensure_settings_table() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        for k, v in DEFAULT_ENGINE_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        conn.commit()
    finally:
        conn.close()


def read_raw_engine_settings() -> dict[str, str]:
    _ensure_settings_table()
    merged = dict(DEFAULT_ENGINE_SETTINGS)
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
    try:
        for k, v in conn.execute("SELECT key, value FROM settings").fetchall():
            merged[str(k)] = str(v)
    finally:
        conn.close()
    return merged


def read_public_engine_settings() -> dict[str, str]:
    cfg = read_raw_engine_settings()
    for k in SECRET_KEYS:
        if cfg.get(k, "").strip():
            cfg[k] = mask_secret(cfg[k])
    return cfg


def write_engine_settings(updates: dict[str, Any]) -> dict[str, str]:
    _ensure_settings_table()
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
    try:
        conn.execute("PRAGMA busy_timeout=15000;")
        for k, v in updates.items():
            if k not in DEFAULT_ENGINE_SETTINGS or v is None:
                continue
            v_str = str(v)
            if k in SECRET_KEYS and is_masked_secret(v_str):
                continue
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, v_str),
            )
        conn.commit()
    finally:
        conn.close()
    return read_raw_engine_settings()


def read_db_counts() -> tuple[int, int]:
    if not DB_PATH.is_file():
        return 0, 0
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            ep_cnt = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] if "episodes" in tables else 0
            voc_cnt = (
                conn.execute("SELECT COUNT(*) FROM entries WHERE is_bookmarked = 1").fetchone()[0]
                if "entries" in tables
                else 0
            )
            return int(ep_cnt), int(voc_cnt)
        finally:
            conn.close()
    except Exception:
        return 0, 0


def load_desktop_config() -> dict[str, Any]:
    cfg = dict(DEFAULT_DESKTOP_CONFIG)
    if CONFIG_PATH.is_file():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update({k: raw[k] for k in DEFAULT_DESKTOP_CONFIG if k in raw})
        except Exception:
            pass
    return cfg


def save_desktop_config(updates: dict[str, Any]) -> dict[str, Any]:
    cfg = load_desktop_config()
    for k in DEFAULT_DESKTOP_CONFIG:
        if k in updates and updates[k] is not None:
            cfg[k] = updates[k]
    try:
        port_val = int(cfg["port"])
    except (TypeError, ValueError):
        port_val = 8000
    cfg["port"] = max(1024, min(65535, port_val))
    cfg["lan_access"] = bool(cfg["lan_access"])
    cfg["hf_mirror"] = bool(cfg["hf_mirror"])
    cfg["auto_start_service"] = bool(cfg["auto_start_service"])
    cfg["access_password"] = str(cfg["access_password"] or "").strip()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def _is_private_lan_ipv4(ip: str) -> bool:
    parts = ip.strip().split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False
    if any(n < 0 or n > 255 for n in nums):
        return False
    if nums[0] == 10:
        return True
    if nums[0] == 192 and nums[1] == 168:
        return True
    if nums[0] == 172 and 16 <= nums[1] <= 31:
        return True
    return False


def _select_best_lan_ip(candidates: list[tuple[str, str]]) -> str:
    virtual_prefixes = ("lo", "utun", "awdl", "llw", "bridge", "ap", "anpi", "gif", "stf", "ipsec", "ppp", "docker", "br-", "veth")
    best_ip = ""
    best_score = -10_000
    for iface, raw_ip in candidates:
        ip = (raw_ip or "").strip()
        name = (iface or "").strip().lower()
        if not ip or ip.startswith(("127.", "169.254.", "198.18.", "198.19.")):
            continue
        is_virtual = any(name.startswith(p) for p in virtual_prefixes)
        score = 0
        if name == "en0":
            score += 100
        elif name == "en1":
            score += 90
        elif name.startswith(("en", "eth", "wlan", "wlp", "enp")):
            score += 70
        elif is_virtual:
            score -= 100
        else:
            score += 20
        if _is_private_lan_ipv4(ip):
            score += 50
        if score > best_score:
            best_score = score
            best_ip = ip
    return best_ip


def detect_lan_ip() -> str:
    candidates: list[tuple[str, str]] = []
    sys_name = platform.system()
    if sys_name == "Darwin":
        for iface in ("en0", "en1"):
            try:
                res = subprocess.run(
                    ["/usr/sbin/ipconfig", "getifaddr", iface],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                ip = (res.stdout or "").strip()
                if res.returncode == 0 and ip:
                    candidates.append((iface, ip))
            except Exception:
                pass
        try:
            res = subprocess.run(["/sbin/ifconfig"], capture_output=True, text=True, timeout=1.5)
            cur_iface = ""
            for line in (res.stdout or "").splitlines():
                if line and not line[0].isspace() and ":" in line:
                    cur_iface = line.split(":", 1)[0].strip()
                elif cur_iface and "\tinet " in line:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        candidates.append((cur_iface, parts[1]))
        except Exception:
            pass
    else:
        try:
            res = subprocess.run(
                ["ip", "-4", "-o", "addr", "show", "up", "scope", "global"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            for line in (res.stdout or "").splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[2] == "inet":
                    candidates.append((parts[1], parts[3].split("/", 1)[0]))
        except Exception:
            pass

    picked = _select_best_lan_ip(candidates)
    if picked:
        return picked

    for target in ("192.168.1.1", "10.255.255.255", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect((target, 80))
            ip = s.getsockname()[0]
            s.close()
            picked = _select_best_lan_ip([("udp", ip)])
            if picked:
                return picked
        except Exception:
            pass
    return ""



def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def http_get_ok(url: str, timeout: float = 1.0) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def test_llm_stdlib(base_url: str, api_key: str, model: str) -> dict[str, Any]:
    resolved_key = (api_key or "").strip()
    if is_masked_secret(resolved_key):
        resolved_key = read_raw_engine_settings().get("llm_api_key", "").strip()
    if not resolved_key:
        return {"ok": False, "message": "请先填写 API Key 再测试连接。"}
    base = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
    url = base if base.endswith("/chat/completions") else base + "/chat/completions"
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return {
            "ok": False,
            "message": "API Base URL 格式无效，必须以 http:// 或 https:// 开头（例如 https://api.deepseek.com/v1）。",
        }
    body = json.dumps(
        {
            "model": (model or "gpt-4o-mini").strip(),
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Reply with OK"}],
        }
    ).encode("utf-8")
    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {resolved_key}",
                "Content-Type": "application/json",
                "User-Agent": "LingoReel-Desktop-Console/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            reply = (data["choices"][0]["message"].get("content") or "").strip()
            return {"ok": True, "message": f"连接成功！模型返回：{reply or 'OK'}"}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")[:160]
        return {"ok": False, "message": f"接口返回 HTTP {exc.code}：{err_body}"}
    except Exception as exc:
        return {"ok": False, "message": f"请求失败：{exc}"}


def _hf_cache_roots() -> list[Path]:
    roots: list[Path] = []
    hf_home = os.getenv("HF_HOME", "").strip()
    if hf_home:
        p = Path(hf_home).expanduser()
        roots.extend([p / "hub", p])
    if platform.system() == "Darwin":
        app_cache = Path.home() / "Library" / "Application Support" / "LingoReelStudio" / "whisper-cache"
        roots.extend([app_cache / "hub", app_cache])
    roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    return roots


def is_whisper_model_cached(model_name: str) -> bool:
    slug = f"models--Systran--faster-whisper-{model_name}".lower()
    for root in _hf_cache_roots():
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.name.lower() == slug and (child / "snapshots").is_dir():
                for snap in (child / "snapshots").iterdir():
                    if (snap / "model.bin").exists():
                        return True
    return False


def _find_compatible_system_python() -> str | None:
    extra_bins = [
        "/opt/homebrew/opt/python@3.12/bin/python3.12",
        "/opt/homebrew/bin/python3.12",
        "/usr/local/opt/python@3.12/bin/python3.12",
        "/usr/local/bin/python3.12",
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
    ]
    candidates = [*extra_bins]
    for name in ("python3.12", "python3.11", "python3.10", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    if (3, 10) <= sys.version_info[:2] <= (3, 12):
        candidates.insert(0, sys.executable)

    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen or not os.path.isfile(cand):
            continue
        seen.add(cand)
        try:
            r = subprocess.run(
                [cand, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}'); raise SystemExit(0 if (3,10)<=sys.version_info[:2]<=(3,12) else 1)"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                return cand
        except Exception:
            continue
    return None


def inspect_environment() -> dict[str, Any]:
    """Check Python 3.12/.venv, required pip packages, FFmpeg, Whisper model cache, and frontend dist."""
    venv_dir = get_venv_dir()
    venv_py = get_venv_python()
    sys_py = _find_compatible_system_python()
    target_py = str(venv_py) if venv_py else (sys_py or "")

    python_ok = False
    python_ver = ""
    if venv_py:
        try:
            r = subprocess.run(
                [str(venv_py), "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}'); raise SystemExit(0 if (3,10)<=sys.version_info[:2]<=(3,12) else 1)"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            python_ver = (r.stdout or "").strip()
            python_ok = r.returncode == 0
        except Exception:
            python_ok = False

    missing_pkgs: list[str] = []
    installed_pkgs: list[str] = []
    bundled_ffmpeg = ""
    pywebview_ok = platform.system() != "Darwin"

    if target_py and venv_py:
        probe_code = (
            "import importlib.util, json, sys\n"
            f"mods = {[m for m, _ in REQUIRED_PACKAGES]!r}\n"
            "res = {m: bool(importlib.util.find_spec(m)) for m in mods}\n"
            "res['webview'] = bool(importlib.util.find_spec('webview'))\n"
            "ff = ''\n"
            "if importlib.util.find_spec('imageio_ffmpeg'):\n"
            "    try:\n"
            "        import imageio_ffmpeg; ff = imageio_ffmpeg.get_ffmpeg_exe() or ''\n"
            "    except Exception:\n"
            "        ff = ''\n"
            "print(json.dumps({'mods': res, 'bundled_ffmpeg': ff}))\n"
        )
        try:
            r = subprocess.run([str(venv_py), "-c", probe_code], capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and r.stdout.strip():
                info = json.loads(r.stdout.strip().splitlines()[-1])
                mods_map = info.get("mods") or {}
                for mod, _label in REQUIRED_PACKAGES:
                    if mods_map.get(mod):
                        installed_pkgs.append(mod)
                    else:
                        missing_pkgs.append(mod)
                bundled_ffmpeg = info.get("bundled_ffmpeg") or ""
                if platform.system() == "Darwin":
                    pywebview_ok = bool(mods_map.get("webview"))
            else:
                missing_pkgs = [m for m, _ in REQUIRED_PACKAGES]
        except Exception:
            missing_pkgs = [m for m, _ in REQUIRED_PACKAGES]
    else:
        missing_pkgs = [m for m, _ in REQUIRED_PACKAGES]

    venv_ffmpeg = venv_dir / "bin" / "ffmpeg"
    sys_ffmpeg = shutil.which("ffmpeg") or ""
    ffmpeg_path = ""
    if sys_ffmpeg:
        ffmpeg_path = sys_ffmpeg
    elif venv_ffmpeg.exists():
        ffmpeg_path = str(venv_ffmpeg)
    elif bundled_ffmpeg and Path(bundled_ffmpeg).exists():
        ffmpeg_path = bundled_ffmpeg
    ffmpeg_ok = bool(ffmpeg_path)

    es = read_raw_engine_settings()
    whisper_model = es.get("local_whisper_model") or "tiny.en"
    whisper_cached = is_whisper_model_cached(whisper_model)
    frontend_ok = (FRONTEND_DIST / "index.html").is_file()

    packages_ok = len(missing_pkgs) == 0 and bool(venv_py)
    core_ready = python_ok and packages_ok and ffmpeg_ok and frontend_ok

    items = [
        {
            "key": "python",
            "label": "Python 3.10–3.12 独立运行环境",
            "ok": python_ok,
            "required": True,
            "detail": (
                f"已就绪：Python {python_ver}（{venv_dir.name}）"
                if python_ok
                else ("尚未创建独立运行环境（点击右侧按钮自动安装 Python 3.12 与依赖）" if not venv_py else f"虚拟环境 Python 版本异常：{python_ver}")
            ),
        },
        {
            "key": "packages",
            "label": "核心学习机后端引擎包",
            "ok": packages_ok,
            "required": True,
            "detail": (
                f"全部 {len(REQUIRED_PACKAGES)} 项核心引擎包已安装就绪"
                if packages_ok
                else f"缺失 {len(missing_pkgs)} 项：{', '.join(missing_pkgs[:6])}"
            ),
            "missing": missing_pkgs,
        },
        {
            "key": "ffmpeg",
            "label": "FFmpeg 音画解码与录音转码器",
            "ok": ffmpeg_ok,
            "required": True,
            "detail": (
                f"已就绪：{Path(ffmpeg_path).name}"
                if ffmpeg_ok
                else "未检测到 FFmpeg（点击「一键安装缺失环境」将自动启用内置组件）"
            ),
        },
        {
            "key": "whisper_model",
            "label": f"本地离线语音模型（{whisper_model}）",
            "ok": whisper_cached,
            "required": False,
            "detail": (
                f"已缓存至本机，跟读打分与无字幕拆解可秒级离线运行"
                if whisper_cached
                else f"尚未预下载（建议点击「一键预热语音模型」，避免首次跟读等待下载）"
            ),
        },
        {
            "key": "frontend",
            "label": "学习机前端界面资源",
            "ok": frontend_ok,
            "required": True,
            "detail": "前端界面包完整就绪" if frontend_ok else f"未找到 {FRONTEND_DIST / 'index.html'}",
        },
    ]

    return {
        "core_ready": core_ready,
        "all_ready": core_ready and whisper_cached,
        "python_version": python_ver or platform.python_version(),
        "venv_dir": str(venv_dir),
        "ffmpeg_path": ffmpeg_path,
        "whisper_model": whisper_model,
        "whisper_cached": whisper_cached,
        "missing_packages": missing_pkgs,
        "items": items,
    }


class DesktopManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self._started_at: float | None = None
        self._active_port: int = 8000
        self._active_host: str = "127.0.0.1"
        self._active_auth: bool = False
        self._logs: collections.deque[str] = collections.deque(maxlen=260)
        self._log_seq: int = 0

        self._install_lock = threading.Lock()
        self._installing_kind: str = ""  # "" | "deps" | "whisper"
        self._last_install_result: dict[str, Any] = {"ok": True, "message": ""}

    def append_log(self, line: str) -> None:
        text = line.rstrip()
        if not text:
            return
        stamp = time.strftime("%H:%M:%S")
        self._logs.append(f"[{stamp}] {text}")
        self._log_seq += 1

    def _stream_proc_output(self, proc: subprocess.Popen[str], prefix: str = "") -> None:
        if not proc.stdout:
            return
        try:
            for line in proc.stdout:
                self.append_log(f"{prefix}{line}" if prefix else line)
        except Exception:
            pass

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def status(self) -> dict[str, Any]:
        cfg = load_desktop_config()
        running = self.is_running()
        port = self._active_port if running else int(cfg["port"])
        local_url = f"http://127.0.0.1:{port}"
        lan_ip = detect_lan_ip()
        lan_active = running and (self._active_host == "0.0.0.0")
        lan_enabled = lan_active or bool(cfg["lan_access"])
        lan_url = f"http://{lan_ip}:{port}" if (lan_ip and lan_enabled) else ""

        health_ok = http_get_ok(f"{local_url}/api/health", timeout=0.9) if running else False
        ep_count, vocab_count = read_db_counts()

        return {
            "running": running,
            "healthy": health_ok,
            "pid": self._proc.pid if running and self._proc else None,
            "port": port,
            "host": self._active_host if running else ("0.0.0.0" if cfg["lan_access"] else "127.0.0.1"),
            "auth_enabled": self._active_auth if running else bool(cfg["access_password"]),
            "local_url": local_url,
            "lan_ip": lan_ip,
            "lan_active": lan_active,
            "lan_url": lan_url,
            "uptime_sec": int(time.time() - self._started_at) if (running and self._started_at) else 0,
            "installing": bool(self._installing_kind),
            "installing_kind": self._installing_kind,
            "last_install_result": self._last_install_result,
            "env_summary": {
                "data_dir": str(DATA_DIR),
                "episode_count": ep_count,
                "vocab_count": vocab_count,
            },
            "log_seq": self._log_seq,
            "logs": list(self._logs),
        }

    def start(self) -> tuple[int, dict[str, Any]]:
        with self._lock:
            if self.is_running():
                return 200, {"service": self.status()}

            env_info = inspect_environment()
            if not env_info["core_ready"]:
                missing_labels = [it["label"] for it in env_info["items"] if it["required"] and not it["ok"]]
                return 400, {
                    "detail": f"运行环境尚未就绪（缺少：{'、'.join(missing_labels)}），请先点击「一键安装缺失环境」后再启动服务。"
                }

            cfg = load_desktop_config()
            port = int(cfg["port"])
            if is_port_in_use(port):
                health = probe_lingoreel_health(port)
                if health is not None:
                    expected_build = get_frontend_build_id()
                    is_current_lingo = (
                        health.get("brand") == "Lingo"
                        and health.get("frontend_dist") == str(FRONTEND_DIST)
                        and (not expected_build or health.get("frontend_build") == expected_build)
                    )
                    if not is_current_lingo:
                        retire_stale_lingo_backend(port, self.append_log)
            if is_port_in_use(port):
                return 409, {
                    "detail": f"端口 {port} 已被其他程序占用，请更换一个端口（如 {port + 1}）后再启动。"
                }

            venv_py = get_venv_python()
            if not venv_py:
                return 400, {"detail": "未找到独立 Python 运行环境，请先点击「一键安装缺失环境」。"}

            host = "0.0.0.0" if cfg["lan_access"] else "127.0.0.1"
            env = os.environ.copy()
            env["LINGOREEL_DATA_DIR"] = str(DATA_DIR)
            env["LINGOREEL_FRONTEND_DIST"] = str(FRONTEND_DIST)
            env["LINGOREEL_DESKTOP_APP"] = "1"
            env["APP_ACCESS_PASSWORD"] = cfg["access_password"]
            env["PYTHONUNBUFFERED"] = "1"
            env["PATH"] = f"{get_venv_dir() / 'bin'}:{env.get('PATH', '')}"
            if cfg["hf_mirror"]:
                env["HF_ENDPOINT"] = "https://hf-mirror.com"
            else:
                env.pop("HF_ENDPOINT", None)

            proxy_flag = (
                "--proxy-headers"
                if os.getenv("TRUST_PROXY", "").strip().lower() in {"1", "true", "yes"}
                else "--no-proxy-headers"
            )
            cmd = [
                str(venv_py),
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                host,
                "--port",
                str(port),
                proxy_flag,
            ]
            self.append_log(f"正在启动网站服务：{host}:{port}（口令锁={'开启' if cfg['access_password'] else '关闭'}）")
            proc = subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._proc = proc
            self._started_at = time.time()
            self._active_port = port
            self._active_host = host
            self._active_auth = bool(cfg["access_password"])

            threading.Thread(target=self._stream_proc_output, args=(proc,), daemon=True).start()

        local_url = f"http://127.0.0.1:{port}"
        for _ in range(50):
            if not self.is_running():
                return 500, {"detail": "网站服务启动失败，请查看下方运行日志排查。"}
            if http_get_ok(f"{local_url}/api/health", timeout=0.8):
                self.append_log(f"网站服务已就绪：{local_url}")
                break
            time.sleep(0.35)
        return 200, {"service": self.status()}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                self.append_log("正在停止网站服务...")
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                self.append_log("网站服务已安全停止。")
            self._proc = None
            self._started_at = None
        return self.status()

    def _run_logged(self, cmd: list[str], env: dict[str, str] | None = None, cwd: Path | None = None) -> int:
        self.append_log(f"$ {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd or BASE_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if proc.stdout:
            for line in proc.stdout:
                self.append_log(line)
        return proc.wait()

    def _ensure_uv_bin(self) -> str | None:
        existing = shutil.which("uv")
        if existing:
            return existing
        bin_dir = DATA_DIR.parent / "bin" if platform.system() == "Darwin" else DATA_DIR / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        local_uv = bin_dir / "uv"
        if local_uv.is_file() and os.access(local_uv, os.X_OK):
            return str(local_uv)
        if platform.system() != "Darwin":
            return None
        arch = platform.machine().lower()
        url = (
            "https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz"
            if arch in ("arm64", "aarch64")
            else "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-apple-darwin.tar.gz"
        )
        self.append_log("正在自动下载轻量安装工具 uv（免管理员密码安装 Python 3.12）...")
        try:
            with tempfile.TemporaryDirectory() as td:
                tgz = Path(td) / "uv.tar.gz"
                urllib.request.urlretrieve(url, str(tgz))
                rc = self._run_logged(["tar", "-xzf", str(tgz), "-C", td])
                if rc == 0:
                    for found in Path(td).rglob("uv"):
                        if found.is_file():
                            shutil.copy2(found, local_uv)
                            os.chmod(local_uv, 0o755)
                            return str(local_uv)
        except Exception as exc:
            self.append_log(f"下载 uv 失败，将回退到系统工具：{exc}")
        return None

    def trigger_install_deps(self) -> tuple[int, dict[str, Any]]:
        with self._install_lock:
            if self._installing_kind:
                return 409, {"detail": "已有安装任务正在运行，请查看下方实时日志等待完成。"}
            self._installing_kind = "deps"
            self._last_install_result = {"ok": True, "message": "正在自动安装与修复运行环境..."}

        def _worker() -> None:
            try:
                venv_dir = get_venv_dir()
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                env["UV_PYTHON_INSTALL_DIR"] = str(DATA_DIR.parent / "python")
                env["UV_CACHE_DIR"] = str(DATA_DIR.parent / "uv-cache")
                self.append_log("=== 开始检测并安装Lingo运行依赖 ===")

                uv_bin = self._ensure_uv_bin()
                venv_py = get_venv_python()

                if not venv_py:
                    sys_py = _find_compatible_system_python()
                    if not sys_py and uv_bin:
                        self.append_log("未检测到 Python 3.10–3.12，正在通过 uv 自动安装独立版 Python 3.12...")
                        if self._run_logged([uv_bin, "python", "install", "3.12"], env=env) == 0:
                            r = subprocess.run([uv_bin, "python", "find", "3.12"], capture_output=True, text=True, env=env)
                            if r.returncode == 0:
                                sys_py = r.stdout.strip()
                    if not sys_py and shutil.which("brew"):
                        self.append_log("正在通过 Homebrew 安装 python@3.12...")
                        self._run_logged(["brew", "install", "python@3.12"], env=env)
                        sys_py = _find_compatible_system_python()
                    if not sys_py:
                        raise RuntimeError("未检测到兼容的 Python 3.10–3.12，且自动安装失败，请检查网络或手动安装 Python 3.12。")

                    self.append_log(f"正在创建独立虚拟环境：{venv_dir}")
                    if uv_bin:
                        rc = self._run_logged([uv_bin, "venv", "--seed", "--python", sys_py, str(venv_dir)], env=env)
                    else:
                        rc = self._run_logged([sys_py, "-m", "venv", str(venv_dir)], env=env)
                    if rc != 0:
                        raise RuntimeError("创建独立 Python 虚拟环境失败。")
                    venv_py = get_venv_python()

                if not venv_py:
                    raise RuntimeError("虚拟环境 Python 可执行文件未生成。")

                req_file = BASE_DIR / "requirements.txt"
                self.append_log("正在安装/补全核心 Python 引擎依赖（优先清华大学 PyPI 国内镜像）...")
                if uv_bin:
                    rc = self._run_logged(
                        [uv_bin, "pip", "install", "--python", str(venv_py), "-r", str(req_file),
                         "--default-index", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                        env=env,
                    )
                    if rc != 0:
                        self.append_log("清华镜像安装未完全成功，正在切换官方 PyPI 重试...")
                        rc = self._run_logged([uv_bin, "pip", "install", "--python", str(venv_py), "-r", str(req_file)], env=env)
                else:
                    rc = self._run_logged(
                        [str(venv_py), "-m", "pip", "install", "-r", str(req_file),
                         "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
                         "--trusted-host", "pypi.tuna.tsinghua.edu.cn"],
                        env=env,
                    )
                    if rc != 0:
                        self.append_log("清华镜像安装未完全成功，正在切换官方 PyPI 重试...")
                        rc = self._run_logged([str(venv_py), "-m", "pip", "install", "-r", str(req_file)], env=env)

                if rc != 0:
                    raise RuntimeError("安装核心 Python 依赖失败，请查看上方日志。")

                # Ensure FFmpeg symlink via imageio-ffmpeg when system ffmpeg is absent
                if not shutil.which("ffmpeg"):
                    r = subprocess.run(
                        [str(venv_py), "-c", "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"],
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    ff_exe = (r.stdout or "").strip()
                    if ff_exe and os.path.isfile(ff_exe):
                        target_link = venv_dir / "bin" / "ffmpeg"
                        target_link.parent.mkdir(parents=True, exist_ok=True)
                        if target_link.is_symlink() or target_link.exists():
                            target_link.unlink()
                        target_link.symlink_to(ff_exe)
                        self.append_log(f"已自动配置内置 FFmpeg 组件：{ff_exe}")

                marker = venv_dir / ".deps_installed_v2"
                marker.write_text("ok\n", encoding="utf-8")
                self._last_install_result = {"ok": True, "message": "全部核心运行环境安装与修复完成！"}
                self.append_log("=== [✓] 核心运行环境已全部就绪！===")
            except Exception as exc:
                self._last_install_result = {"ok": False, "message": str(exc)}
                self.append_log(f"[错误] 环境安装失败：{exc}")
            finally:
                with self._install_lock:
                    self._installing_kind = ""

        threading.Thread(target=_worker, daemon=True).start()
        return 202, {"ok": True, "message": "已开始安装缺失依赖，请查看实时日志。"}

    def trigger_install_whisper(self) -> tuple[int, dict[str, Any]]:
        with self._install_lock:
            if self._installing_kind:
                return 409, {"detail": "已有安装任务正在运行，请等待当前任务完成。"}
            venv_py = get_venv_python()
            if not venv_py:
                return 400, {"detail": "请先点击「一键安装缺失环境」安装 Python 与 faster-whisper。"}
            self._installing_kind = "whisper"
            self._last_install_result = {"ok": True, "message": "正在下载并预热离线 Whisper 语音模型..."}

        def _worker() -> None:
            try:
                cfg = load_desktop_config()
                es = read_raw_engine_settings()
                model_name = es.get("local_whisper_model") or "tiny.en"
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                if cfg.get("hf_mirror", True):
                    env["HF_ENDPOINT"] = "https://hf-mirror.com"
                self.append_log(f"=== 开始预热离线 Whisper 模型：{model_name}（镜像={env.get('HF_ENDPOINT', '官方 HuggingFace')}）===")
                code = (
                    "from faster_whisper import WhisperModel; "
                    f"WhisperModel({model_name!r}, device='cpu', compute_type='int8'); "
                    "print('WHISPER_MODEL_WARM_OK')"
                )
                rc = self._run_logged([str(venv_py), "-c", code], env=env)
                if rc != 0:
                    raise RuntimeError(f"下载 Whisper({model_name}) 模型失败，请确认网络连接或开启国内镜像。")
                self._last_install_result = {"ok": True, "message": f"离线语音模型 {model_name} 已下载缓存完成！"}
                self.append_log(f"=== [✓] 离线语音模型 {model_name} 已就绪！===")
            except Exception as exc:
                self._last_install_result = {"ok": False, "message": str(exc)}
                self.append_log(f"[错误] 模型预热失败：{exc}")
            finally:
                with self._install_lock:
                    self._installing_kind = ""

        threading.Thread(target=_worker, daemon=True).start()
        return 202, {"ok": True, "message": "已开始预热本地 Whisper 模型，请查看实时日志。"}


manager = DesktopManager()
atexit.register(manager.stop)


CONSOLE_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Lingo — 桌面控制台</title>
<style>
  :root {
    --shell: #FF7A2D;
    --shell-deep: #C44908;
    --panel: #FFF6E8;
    --card: #FFFFFF;
    --card-deep: #DECBB0;
    --ink: #1B1330;
    --ink-sub: #4A3F61;
    --yellow: #FFE24C;
    --yellow-deep: #C49B00;
    --mint: #53D89A;
    --mint-soft: #D7F8E8;
    --mint-ink: #0B3320;
    --mint-deep: #1E8A58;
    --coral: #C91D42;
    --coral-soft: #FFE4E9;
    --coral-deep: #850E29;
    font-synthesis: none;
    line-break: strict;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--shell);
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Noto Sans SC", sans-serif;
    font-size: 14.5px;
    line-height: 1.5;
    padding: 16px 20px 24px;
  }
  .wrap { max-width: 1060px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
  .header { display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
  .brand { display: flex; align-items: center; gap: 12px; }
  .mascot {
    width: 52px; height: 52px; border-radius: 16px; background: #FFF8EB; padding: 3px;
    box-shadow: 0 5px 0 var(--shell-deep), inset 0 2px 0 #FFF; overflow: hidden;
  }
  .mascot img { width: 100%; height: 100%; object-fit: cover; border-radius: 13px; display: block; }
  .brand h1 { font-size: 22px; font-weight: 900; letter-spacing: -0.02em; }
  .brand p { font-size: 13px; font-weight: 700; color: #3D1A06; }

  .status-pill {
    display: inline-flex; align-items: center; gap: 8px; padding: 8px 16px; border-radius: 999px;
    background: #FFF8EB; font-weight: 900; font-size: 14px;
    box-shadow: 0 4px 0 var(--shell-deep), inset 0 2px 0 #FFF;
  }
  .dot { width: 11px; height: 11px; border-radius: 50%; background: #8E84A3; }
  .dot.on { background: var(--mint-deep); box-shadow: 0 0 0 4px rgba(83,216,154,0.35); }
  .dot.warn { background: var(--coral); box-shadow: 0 0 0 4px rgba(201,29,66,0.22); }

  .panel {
    background: var(--panel); border-radius: 26px; padding: 18px 20px;
    box-shadow: 0 10px 0 var(--shell-deep), inset 0 4px 0 #FFF;
    display: flex; flex-direction: column; gap: 16px;
  }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 840px) { .grid-2 { grid-template-columns: 1fr; } }

  .card {
    background: var(--card); border-radius: 20px; padding: 16px 18px;
    box-shadow: 0 6px 0 var(--card-deep), inset 0 3px 0 #FFF;
    display: flex; flex-direction: column; gap: 12px;
  }
  .card h2 {
    font-size: 16.5px; font-weight: 900;
    display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;
  }
  .tag {
    display: inline-flex; align-items: center; padding: 3px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 800; background: #FFF2D8; color: var(--ink);
    white-space: nowrap; flex-shrink: 0;
  }
  .tag.dark { background: var(--ink); color: var(--yellow); }
  .tag.mint { background: var(--mint-soft); color: var(--mint-ink); }
  .tag.coral { background: var(--coral-soft); color: var(--coral-deep); }

  .env-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
  @media (max-width: 980px) { .env-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  @media (max-width: 600px) { .env-grid { grid-template-columns: 1fr; } }
  .env-item {
    background: var(--panel); border-radius: 14px; padding: 10px 12px;
    border: 2px solid var(--card-deep); display: flex; flex-direction: column; gap: 5px;
  }
  .env-item.ok { border-color: #7AD9AC; background: #F2FDF7; }
  .env-item.missing { border-color: #F08DA1; background: #FFF5F7; }
  .env-item-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 6px; }
  .env-item strong { font-size: 13px; line-height: 1.35; }
  .env-item small { font-size: 12px; color: var(--ink-sub); font-weight: 600; line-height: 1.4; }

  .row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  label { display: block; font-size: 12.5px; font-weight: 800; color: var(--ink-sub); margin-bottom: 4px; }
  input[type="text"], input[type="password"], input[type="number"], select {
    width: 100%; padding: 9px 12px; border-radius: 13px; border: 2px solid var(--card-deep);
    background: #FFFDF9; font: inherit; font-size: 14px; font-weight: 600; color: var(--ink);
  }
  input:focus, select:focus { outline: none; border-color: var(--ink); }

  .switch-row {
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    padding: 9px 12px; background: var(--panel); border-radius: 14px;
  }
  .switch-row strong { font-size: 13.5px; }
  .switch-row small { display: block; font-size: 12px; color: var(--ink-sub); }
  input[type="checkbox"] { width: 20px; height: 20px; accent-color: var(--ink); cursor: pointer; }

  .btn-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .chunk {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    border: none; cursor: pointer; font: inherit; font-weight: 800; font-size: 14px;
    padding: 9px 16px; border-radius: 14px; white-space: nowrap;
    box-shadow: 0 5px 0 var(--d, #090512), inset 0 3px 0 rgba(255,255,255,0.42);
    transition: transform 0.08s ease;
  }
  .chunk:active:not(:disabled) { transform: translateY(3px); box-shadow: 0 2px 0 var(--d, #090512); }
  .chunk:disabled { opacity: 0.55; cursor: not-allowed; }
  .c-dark { background: var(--ink); color: #FFF8EB; --d: #090512; }
  .c-yellow { background: var(--yellow); color: var(--ink); --d: var(--yellow-deep); }
  .c-mint { background: var(--mint); color: var(--mint-ink); --d: var(--mint-deep); }
  .c-coral { background: var(--coral); color: #FFF; --d: var(--coral-deep); }
  .c-white { background: #FFF; color: var(--ink); --d: var(--card-deep); }
  .c-sm { padding: 6px 12px; font-size: 12.5px; border-radius: 11px; box-shadow: 0 3px 0 var(--d, var(--card-deep)); }

  .url-box {
    background: var(--ink); color: #FFF8EB; border-radius: 16px; padding: 12px 16px;
    display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  }
  .url-box code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 14px; color: var(--yellow); font-weight: 700;
  }

  .env-strip { display: flex; flex-wrap: wrap; gap: 8px; }
  .log-box {
    background: #140E24; color: #E2DAF7; border-radius: 14px; padding: 12px 14px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px;
    height: 150px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;
  }
  .toast {
    position: fixed; top: 18px; left: 50%; transform: translateX(-50%);
    background: var(--ink); color: var(--yellow); padding: 9px 18px; border-radius: 14px;
    font-weight: 800; font-size: 14px; box-shadow: 0 5px 0 #090512; display: none; z-index: 99;
  }
</style>
</head>
<body>
<div class="toast" id="toast"></div>
<div class="wrap">
  <header class="header">
    <div class="brand">
      <img src="/console/lingo-logo.png" alt="Lingo" style="height:44px;width:auto;display:block;filter:drop-shadow(0 3px 5px rgba(27,19,48,0.18));" />
      <div>
        <h1>Lingo 桌面控制台</h1>
        <p>一键体检并安装运行依赖、绑定 AI 接口、配置端口与口令，启动并访问精听学习机网站</p>
      </div>
    </div>
    <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
      <div class="status-pill">
        <span class="dot" id="status-dot"></span>
        <span id="status-text">正在检测环境与服务状态...</span>
      </div>
      <button class="chunk c-white c-sm" id="btn-quit-console" onclick="shutdownConsole()" title="停止本地服务并关闭桌面控制台进程">退出控制台</button>
    </div>
  </header>

  <main class="panel">
    <!-- Top Launch Banner -->
    <section class="url-box">
      <div>
        <div style="font-size:12.5px; color:#D7CFF0; margin-bottom:2px;">网站发布地址（确认环境就绪后点击「启动网站服务」即可打开访问）</div>
        <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
          <code id="local-url">http://127.0.0.1:8000</code>
          <span id="lan-url-wrap" style="display:none; font-size:13px; color:#9FF0C8;">
            局域网：<code id="lan-url" style="color:#9FF0C8;"></code>
          </span>
        </div>
      </div>
      <div class="btn-row">
        <button class="chunk c-mint" id="btn-start" onclick="startService()">启动网站服务</button>
        <button class="chunk c-coral" id="btn-stop" onclick="stopService()" style="display:none;">停止服务</button>
        <button class="chunk c-yellow" id="btn-open" onclick="openBrowser()">打开学习机页面</button>
      </div>
    </section>

    <!-- 0. Live Runtime Dependency Check & One-Click Installer -->
    <section class="card" id="env-check-card">
      <h2>
        <span style="display:inline-flex; align-items:center; gap:8px;">
          <span>0. 运行环境自检与一键安装</span>
          <span class="tag mint" id="env-overall-badge">检测中...</span>
        </span>
        <div class="btn-row">
          <button class="chunk c-coral c-sm" id="btn-install-deps" onclick="installDeps()">一键安装 / 修复缺失环境</button>
          <button class="chunk c-yellow c-sm" id="btn-install-whisper" onclick="installWhisper()">一键预热离线语音模型</button>
          <button class="chunk c-white c-sm" onclick="refreshEnvCheck(true)">重新检测环境</button>
        </div>
      </h2>
      <div class="env-grid" id="env-grid"></div>
      <div id="install-banner" style="display:none; font-size:13px; font-weight:800; padding:8px 12px; border-radius:12px; background:#FFF2D8;"></div>
    </section>

    <div class="grid-2">
      <!-- 1. Server & Publishing Settings -->
      <section class="card">
        <h2>
          <span>1. 网站发布与安全配置</span>
          <span class="tag dark">本地 / 局域网</span>
        </h2>

        <div class="row-2">
          <div>
            <label for="cfg-port">监听端口</label>
            <input id="cfg-port" type="number" min="1024" max="65535" value="8000" oninput="updateLanPreview()" />
          </div>
          <div>
            <label for="cfg-pwd">访问口令（可选）</label>
            <input id="cfg-pwd" type="password" placeholder="留空表示免密直接进入" />
          </div>
        </div>

        <div class="switch-row">
          <div>
            <strong>开放局域网访问（手机 / iPad 同 Wi-Fi 使用）</strong>
            <small>默认仅本机 127.0.0.1 更安全；开启后可在平板或手机上刷精听</small>
          </div>
          <input id="cfg-lan" type="checkbox" onchange="updateLanPreview()" />
        </div>
        <div id="cfg-lan-preview" style="display:none; margin-top:-4px; padding:10px 12px; border-radius:12px; background:#EEF6FF; border:1.5px solid #BFDBFE; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap;">
          <div>
            <div style="font-size:12px; font-weight:800; color:#1E3A8A;">局域网同 Wi-Fi 访问地址</div>
            <div id="cfg-lan-preview-url" style="font-size:14px; font-weight:900; font-family:monospace; color:#1D4ED8; user-select:all;"></div>
            <div id="cfg-lan-preview-hint" style="font-size:11.5px; color:#475569; margin-top:2px;"></div>
          </div>
          <button class="chunk c-white c-sm" type="button" onclick="copyLanPreviewUrl()">复制局域网地址</button>
        </div>

        <div class="switch-row">
          <div>
            <strong>国内加速镜像（hf-mirror）</strong>
            <small>离线语音模型 faster-whisper 下载自动走国内镜像</small>
          </div>
          <input id="cfg-hf" type="checkbox" checked />
        </div>

        <div class="switch-row">
          <div>
            <strong>打开桌面控制台时自动启动网站服务</strong>
            <small>下次打开「Lingo」自动拉起学习机服务</small>
          </div>
          <input id="cfg-autostart" type="checkbox" />
        </div>

        <div class="btn-row" style="justify-content:flex-end;">
          <button class="chunk c-dark c-sm" onclick="saveDesktopConfig()">保存发布配置</button>
          <button class="chunk c-white c-sm" onclick="restartService()">保存并重启服务</button>
        </div>
      </section>

      <!-- 2. AI API & ASR Engine Binding -->
      <section class="card">
        <h2>
          <span>2. AI 大模型与语音引擎绑定</span>
          <span class="tag mint" id="ai-mode-badge">离线模式可用</span>
        </h2>

        <div class="btn-row">
          <span style="font-size:12.5px; font-weight:800; color:var(--ink-sub);">一键预设：</span>
          <button class="chunk c-white c-sm" type="button" onclick="applyPreset('OpenAI')">OpenAI</button>
          <button class="chunk c-white c-sm" type="button" onclick="applyPreset('DeepSeek')">DeepSeek</button>
          <button class="chunk c-white c-sm" type="button" onclick="applyPreset('Qwen')">通义千问</button>
          <button class="chunk c-white c-sm" type="button" onclick="applyPreset('Groq')">Groq</button>
          <button class="chunk c-white c-sm" type="button" onclick="applyPreset('SiliconFlow')">SiliconFlow</button>
        </div>

        <div class="row-2">
          <div>
            <label for="llm-url">LLM 接口地址（OpenAI 兼容）</label>
            <input id="llm-url" type="text" placeholder="https://api.deepseek.com/v1" />
          </div>
          <div>
            <label for="llm-model">LLM 模型名</label>
            <input id="llm-model" type="text" placeholder="deepseek-chat" />
          </div>
        </div>

        <div>
          <label for="llm-key">LLM API Key（留空则使用本地离线词库与语法分析）</label>
          <input id="llm-key" type="password" placeholder="sk-..." />
        </div>

        <div class="row-2">
          <div>
            <label for="asr-mode">语音识别模式</label>
            <select id="asr-mode">
              <option value="auto">自动（优先云端，否则本地）</option>
              <option value="local_whisper">仅本地离线 Whisper</option>
              <option value="cloud_api">强制云端 Whisper API</option>
              <option value="subtitle_only">仅使用 SRT/VTT 字幕</option>
            </select>
          </div>
          <div>
            <label for="whisper-model">本地 Whisper 模型</label>
            <select id="whisper-model">
              <option value="tiny.en">tiny.en（极速，约 75MB）</option>
              <option value="base.en">base.en（均衡推荐，约 145MB）</option>
              <option value="small.en">small.en（高精度，约 480MB）</option>
            </select>
          </div>
        </div>

        <div class="row-2">
          <div>
            <label for="asr-url">云端 Whisper URL（选填）</label>
            <input id="asr-url" type="text" />
          </div>
          <div>
            <label for="asr-key">云端 Whisper Key（选填）</label>
            <input id="asr-key" type="password" placeholder="留空走本地离线识别" />
          </div>
        </div>

        <div class="btn-row" style="justify-content:space-between;">
          <button class="chunk c-white c-sm" id="btn-test-llm" onclick="testLLM()">测试 AI 连通性</button>
          <button class="chunk c-yellow c-sm" onclick="saveEngineSettings()">保存 AI 与引擎绑定</button>
        </div>
        <div id="test-result" style="font-size:13px; font-weight:800; display:none;"></div>
      </section>
    </div>

    <!-- 3. Data Summary & Live Logs -->
    <section class="card">
      <h2>
        <span>3. 数据目录与实时运行日志</span>
        <div class="btn-row">
          <button class="chunk c-white c-sm" onclick="openDataDir()">打开视频与数据目录</button>
          <button class="chunk c-white c-sm" onclick="refreshState()">刷新状态</button>
        </div>
      </h2>
      <div class="env-strip" id="env-strip"></div>
      <div class="log-box" id="log-box">等待环境检查或服务启动...</div>
    </section>
  </main>
</div>

<script>
const PRESETS = {
  OpenAI:      { base: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  DeepSeek:    { base: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  Qwen:        { base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  Groq:        { base: 'https://api.groq.com/openai/v1', model: 'llama-3.3-70b-versatile' },
  SiliconFlow: { base: 'https://api.siliconflow.cn/v1', model: 'Qwen/Qwen2.5-72B-Instruct' },
};

let initializedForm = false;
let wasInstalling = false;

function showToast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.display = 'block';
  clearTimeout(window._t);
  window._t = setTimeout(() => { el.style.display = 'none'; }, 3400);
}

function escapeHtml(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function applyPreset(name) {
  const p = PRESETS[name];
  if (!p) return;
  document.getElementById('llm-url').value = p.base;
  document.getElementById('llm-model').value = p.model;
  showToast('已填入 ' + name + ' 接口地址，填写 API Key 后点击保存即可');
}

function renderEnvCheck(env) {
  if (!env) return;
  const badge = document.getElementById('env-overall-badge');
  const btnDeps = document.getElementById('btn-install-deps');
  const btnWhisper = document.getElementById('btn-install-whisper');

  if (env.all_ready) {
    badge.textContent = '全部依赖与离线模型已就绪';
    badge.className = 'tag mint';
    btnDeps.textContent = '校验 / 修复依赖';
    btnDeps.className = 'chunk c-white c-sm';
    btnWhisper.textContent = '已预热（重新校验）';
    btnWhisper.className = 'chunk c-white c-sm';
  } else if (env.core_ready) {
    badge.textContent = '核心环境就绪（建议预热语音模型）';
    badge.className = 'tag dark';
    btnDeps.textContent = '校验 / 修复依赖';
    btnDeps.className = 'chunk c-white c-sm';
    btnWhisper.textContent = '一键预热离线语音模型';
    btnWhisper.className = 'chunk c-yellow c-sm';
  } else {
    badge.textContent = '检测到缺失运行环境，请一键安装';
    badge.className = 'tag coral';
    btnDeps.textContent = '一键安装缺失环境';
    btnDeps.className = 'chunk c-coral c-sm';
    btnWhisper.textContent = '一键预热离线语音模型';
    btnWhisper.className = 'chunk c-yellow c-sm';
  }

  const grid = document.getElementById('env-grid');
  grid.innerHTML = (env.items || []).map((it) => {
    const cls = it.ok ? 'ok' : (it.required ? 'missing' : '');
    const statusTag = it.ok
      ? '<span class="tag mint">已就绪</span>'
      : (it.required ? '<span class="tag coral">未安装</span>' : '<span class="tag">待下载</span>');
    return `
      <div class="env-item ${cls}">
        <div class="env-item-head">
          <strong>${escapeHtml(it.label)}</strong>
          ${statusTag}
        </div>
        <small>${escapeHtml(it.detail)}</small>
      </div>
    `;
  }).join('');
}

function renderService(svc) {
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  const btnStart = document.getElementById('btn-start');
  const btnStop = document.getElementById('btn-stop');
  const btnDeps = document.getElementById('btn-install-deps');
  const btnWhisper = document.getElementById('btn-install-whisper');
  const banner = document.getElementById('install-banner');

  if (svc.installing) {
    dot.className = 'dot warn';
    txt.textContent = svc.installing_kind === 'whisper' ? '正在下载预热离线语音模型...' : '正在安装运行环境依赖...';
    btnDeps.disabled = true;
    btnWhisper.disabled = true;
    banner.style.display = 'block';
    banner.style.background = '#FFF2D8';
    banner.style.color = '#1B1330';
    banner.textContent = (svc.last_install_result && svc.last_install_result.message) || '安装任务运行中，请查看下方实时日志...';
    wasInstalling = true;
  } else {
    btnDeps.disabled = false;
    btnWhisper.disabled = false;
    if (wasInstalling) {
      wasInstalling = false;
      refreshEnvCheck(false);
    }
    if (svc.last_install_result && svc.last_install_result.message) {
      banner.style.display = 'block';
      banner.style.background = svc.last_install_result.ok ? '#D7F8E8' : '#FFE4E9';
      banner.style.color = svc.last_install_result.ok ? '#0B3320' : '#850E29';
      banner.textContent = svc.last_install_result.message;
    } else {
      banner.style.display = 'none';
    }

    if (svc.running) {
      dot.className = 'dot on';
      txt.textContent = (svc.healthy ? '网站服务运行中' : '正在初始化') + '（端口 ' + svc.port + '）';
      btnStart.style.display = 'none';
      btnStop.style.display = 'inline-flex';
    } else {
      dot.className = 'dot';
      txt.textContent = '网站服务未启动（确认环境就绪后点启动）';
      btnStart.style.display = 'inline-flex';
      btnStop.style.display = 'none';
    }
  }

  window.__lastSvc = svc;
  document.getElementById('local-url').textContent = svc.local_url;
  updateLanPreview();

  const esum = svc.env_summary || {};
  document.getElementById('env-strip').innerHTML =
    `<span class="tag">已拆解课程 ${esum.episode_count ?? 0} 篇</span>` +
    `<span class="tag">生词本 ${esum.vocab_count ?? 0} 词</span>` +
    `<span class="tag">数据目录：${escapeHtml(esum.data_dir || '-')}</span>`;

  const logBox = document.getElementById('log-box');
  if (svc.logs && svc.logs.length) {
    logBox.textContent = svc.logs.join('\n');
    logBox.scrollTop = logBox.scrollHeight;
  }
}

function updateLanPreview() {
  const svc = window.__lastSvc || {};
  const lanChecked = Boolean(document.getElementById('cfg-lan')?.checked);
  const portVal = Math.max(1024, Math.min(65535, Number(document.getElementById('cfg-port')?.value) || svc.port || 8000));
  const lanIp = svc.lan_ip || '';
  const liveUrl = (lanChecked || svc.lan_active) && lanIp ? `http://${lanIp}:${lanChecked ? portVal : (svc.port || portVal)}` : '';

  const lanWrap = document.getElementById('lan-url-wrap');
  if (lanWrap) {
    if (liveUrl) {
      lanWrap.style.display = 'inline';
      document.getElementById('lan-url').textContent = liveUrl;
    } else {
      lanWrap.style.display = 'none';
    }
  }

  const box = document.getElementById('cfg-lan-preview');
  if (!box) return;
  if (!lanChecked) {
    box.style.display = 'none';
    return;
  }
  box.style.display = 'flex';
  const urlEl = document.getElementById('cfg-lan-preview-url');
  const hintEl = document.getElementById('cfg-lan-preview-hint');
  if (lanIp) {
    const previewUrl = `http://${lanIp}:${portVal}`;
    urlEl.textContent = previewUrl;
    if (svc.running && svc.lan_active && Number(svc.port) === portVal) {
      hintEl.textContent = '已生效：同 Wi-Fi 平板 / 手机浏览器直接输入此地址即可访问';
    } else if (svc.running) {
      hintEl.textContent = '请点击下方「保存并重启服务」后，同 Wi-Fi 设备即可通过此地址访问';
    } else {
      hintEl.textContent = '保存配置并启动服务后，同 Wi-Fi 平板 / 手机输入此地址访问';
    }
  } else {
    urlEl.textContent = '暂未检测到本机局域网 IP';
    hintEl.textContent = '请确认电脑已连接 Wi-Fi 或网线后再试';
  }
}

function copyLanPreviewUrl() {
  const txt = (document.getElementById('cfg-lan-preview-url')?.textContent || '').trim();
  if (!txt.startsWith('http://')) {
    showToast('暂未检测到可用局域网地址');
    return;
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(txt).then(() => showToast('已复制局域网地址：' + txt));
  } else {
    showToast('请手动复制：' + txt);
  }
}

async function refreshEnvCheck(withToast) {
  try {
    const r = await fetch('/console/api/env-check');
    const env = await r.json();
    renderEnvCheck(env);
    if (withToast) {
      showToast(env.all_ready ? '全部运行环境与离线语音模型已就绪' : (env.core_ready ? '核心环境就绪，可选预热离线语音模型' : '检测到缺失依赖，请点击「一键安装缺失环境」'));
    }
  } catch (e) {}
}

async function refreshState() {
  try {
    const r = await fetch('/console/api/state');
    const data = await r.json();
    renderService(data.service);

    if (!initializedForm) {
      initializedForm = true;
      const dc = data.desktop_config || {};
      document.getElementById('cfg-port').value = dc.port || 8000;
      document.getElementById('cfg-pwd').value = dc.access_password || '';
      document.getElementById('cfg-lan').checked = Boolean(dc.lan_access);
      document.getElementById('cfg-hf').checked = dc.hf_mirror !== false;
      document.getElementById('cfg-autostart').checked = Boolean(dc.auto_start_service);
      updateLanPreview();

      const es = data.engine_settings || {};
      document.getElementById('llm-url').value = es.llm_base_url || 'https://api.openai.com/v1';
      document.getElementById('llm-model').value = es.llm_model || 'gpt-4o-mini';
      document.getElementById('llm-key').value = es.llm_api_key || '';
      document.getElementById('asr-mode').value = es.asr_mode || 'auto';
      document.getElementById('whisper-model').value = es.local_whisper_model || 'tiny.en';
      document.getElementById('asr-url').value = es.asr_base_url || 'https://api.openai.com/v1';
      document.getElementById('asr-key').value = es.asr_api_key || '';

      const badge = document.getElementById('ai-mode-badge');
      if (data.has_llm_key || data.has_asr_key) {
        badge.textContent = '已绑定云端 API';
        badge.className = 'tag dark';
      } else {
        badge.textContent = '离线模式可用';
        badge.className = 'tag mint';
      }
    }
  } catch (e) {}
}

async function installDeps() {
  const r = await fetch('/console/api/env/install-deps', { method: 'POST' });
  const data = await r.json();
  if (!r.ok) { showToast(data.detail || '启动安装失败'); return; }
  showToast(data.message || '已开始安装缺失环境');
  refreshState();
}

async function installWhisper() {
  await saveDesktopConfig(true);
  await saveEngineSettings(true);
  const r = await fetch('/console/api/env/install-whisper', { method: 'POST' });
  const data = await r.json();
  if (!r.ok) { showToast(data.detail || '启动模型预热失败'); return; }
  showToast(data.message || '已开始预热离线语音模型');
  refreshState();
}

async function saveDesktopConfig(silent) {
  const payload = {
    port: Number(document.getElementById('cfg-port').value) || 8000,
    access_password: document.getElementById('cfg-pwd').value,
    lan_access: document.getElementById('cfg-lan').checked,
    hf_mirror: document.getElementById('cfg-hf').checked,
    auto_start_service: document.getElementById('cfg-autostart').checked,
  };
  const r = await fetch('/console/api/desktop-config', {
    method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await r.json();
  if (data.desktop_config) {
    document.getElementById('cfg-port').value = data.desktop_config.port;
    document.getElementById('cfg-lan').checked = Boolean(data.desktop_config.lan_access);
    document.getElementById('cfg-hf').checked = data.desktop_config.hf_mirror !== false;
    document.getElementById('cfg-autostart').checked = Boolean(data.desktop_config.auto_start_service);
  }
  renderService(data.service);
  if (!silent) showToast('发布配置已保存（如服务正在运行，点「保存并重启服务」立即生效）');
}

async function saveEngineSettings(silent) {
  const payload = {
    llm_base_url: document.getElementById('llm-url').value.trim(),
    llm_model: document.getElementById('llm-model').value.trim(),
    llm_api_key: document.getElementById('llm-key').value.trim(),
    asr_mode: document.getElementById('asr-mode').value,
    local_whisper_model: document.getElementById('whisper-model').value,
    asr_base_url: document.getElementById('asr-url').value.trim(),
    asr_api_key: document.getElementById('asr-key').value.trim(),
  };
  const r = await fetch('/console/api/engine-settings', {
    method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  });
  const data = await r.json();
  if (data.engine_settings) {
    document.getElementById('llm-key').value = data.engine_settings.llm_api_key || '';
    document.getElementById('asr-key').value = data.engine_settings.asr_api_key || '';
  }
  const badge = document.getElementById('ai-mode-badge');
  if (data.has_llm_key || data.has_asr_key) {
    badge.textContent = '已绑定云端 API'; badge.className = 'tag dark';
  } else {
    badge.textContent = '离线模式可用'; badge.className = 'tag mint';
  }
  refreshEnvCheck(false);
  if (!silent) showToast('AI 与语音引擎配置已同步保存至学习机');
}

async function testLLM() {
  const btn = document.getElementById('btn-test-llm');
  const box = document.getElementById('test-result');
  btn.disabled = true; btn.textContent = '测试中...';
  try {
    const r = await fetch('/console/api/test-llm', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        base_url: document.getElementById('llm-url').value.trim(),
        api_key: document.getElementById('llm-key').value.trim(),
        model: document.getElementById('llm-model').value.trim(),
      })
    });
    const res = await r.json();
    box.style.display = 'block';
    box.style.color = res.ok ? '#1E8A58' : '#C91D42';
    box.textContent = res.message;
  } finally {
    btn.disabled = false; btn.textContent = '测试 AI 连通性';
  }
}

async function startService() {
  await saveDesktopConfig(true);
  const btn = document.getElementById('btn-start');
  btn.disabled = true; btn.textContent = '启动中...';
  try {
    const r = await fetch('/console/api/service/start', { method: 'POST' });
    const data = await r.json();
    if (!r.ok) { showToast(data.detail || '启动失败'); return; }
    renderService(data.service);
    if (data.service && data.service.healthy) {
      showToast('学习机网站已就绪，点击「打开学习机页面」即可使用！');
    } else {
      showToast('服务正在初始化中，请稍候状态灯变绿后打开页面');
    }
  } finally {
    btn.disabled = false; btn.textContent = '启动网站服务';
  }
}

async function stopService() {
  const r = await fetch('/console/api/service/stop', { method: 'POST' });
  const data = await r.json();
  renderService(data.service);
  showToast('学习机网站服务已停止');
}

async function restartService() {
  await saveDesktopConfig(true);
  const r = await fetch('/console/api/service/restart', { method: 'POST' });
  const data = await r.json();
  if (!r.ok) { showToast(data.detail || '重启失败'); return; }
  renderService(data.service);
  showToast(
    data.service && data.service.healthy
      ? '已按最新配置重启网站服务'
      : '服务正在按最新配置重新初始化...'
  );
}

async function openBrowser() {
  await saveDesktopConfig(true);
  const r = await fetch('/console/api/open-browser', { method: 'POST' });
  const data = await r.json();
  if (!r.ok) { showToast(data.detail || '打开失败，请检查环境与端口设置'); return; }
  if (data.url) {
    showToast('已为你打开学习机页面：' + data.url);
    refreshState();
  }
}

async function openDataDir() {
  await fetch('/console/api/open-data-dir', { method: 'POST' });
  showToast('已打开数据文件夹');
}

let pollTimer = null;
async function shutdownConsole() {
  const btn = document.getElementById('btn-quit-console');
  if (btn) { btn.disabled = true; btn.textContent = '正在退出...'; }
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  try {
    await fetch('/console/api/console/shutdown', { method: 'POST' });
  } catch (e) {}
  document.getElementById('status-dot').className = 'dot';
  document.getElementById('status-text').textContent = '控制台与本地服务已关闭';
  showToast('Lingo控制台与服务已安全退出，可关闭本页面；下次点击应用图标即可重新打开。');
}

refreshEnvCheck(false);
refreshState();
pollTimer = setInterval(refreshState, 2200);
</script>
</body>
</html>
"""


class ConsoleHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send_json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _is_origin_allowed(self) -> bool:
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return True
        parsed = urlparse(origin)
        return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 1024 * 1024))
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = CONSOLE_HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path in ("/console/lingo-logo.png", "/console/mascot.png"):
            for cand in (
                FRONTEND_DIST / "lingo-logo.png",
                BASE_DIR.parent / "frontend" / "public" / "lingo-logo.png",
                BASE_DIR.parent / "macos" / "native-app" / "Sources" / "LingoReelApp" / "Resources" / "lingo-logo.png",
            ):
                if cand.is_file():
                    raw = cand.read_bytes()
                    ctype = mimetypes.guess_type(str(cand))[0] or "image/png"
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
            self._send_json({"detail": "Logo not found"}, 404)
            return

        if path == "/console/api/state":
            raw_es = read_raw_engine_settings()
            self._send_json(
                {
                    "service": manager.status(),
                    "desktop_config": load_desktop_config(),
                    "engine_settings": read_public_engine_settings(),
                    "has_llm_key": bool(raw_es.get("llm_api_key", "").strip()),
                    "has_asr_key": bool(raw_es.get("asr_api_key", "").strip()),
                }
            )
            return

        if path == "/console/api/env-check":
            self._send_json(inspect_environment())
            return

        self._send_json({"detail": "Not found"}, 404)

    def do_PUT(self) -> None:  # noqa: N802
        if not self._is_origin_allowed():
            self._send_json({"detail": "拒绝跨站修改本地控制台配置。"}, 403)
            return
        path = urlparse(self.path).path
        body = self._read_json()

        if path == "/console/api/desktop-config":
            cfg = save_desktop_config(body)
            self._send_json({"desktop_config": cfg, "service": manager.status()})
            return

        if path == "/console/api/engine-settings":
            raw = write_engine_settings(body)
            self._send_json(
                {
                    "engine_settings": read_public_engine_settings(),
                    "has_llm_key": bool(raw.get("llm_api_key", "").strip()),
                    "has_asr_key": bool(raw.get("asr_api_key", "").strip()),
                }
            )
            return

        self._send_json({"detail": "Not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if not self._is_origin_allowed():
            self._send_json({"detail": "拒绝跨站操作本地桌面控制台。"}, 403)
            return
        path = urlparse(self.path).path
        body = self._read_json()

        if path == "/console/api/test-llm":
            res = test_llm_stdlib(
                str(body.get("base_url") or ""),
                str(body.get("api_key") or ""),
                str(body.get("model") or ""),
            )
            self._send_json(res)
            return

        if path == "/console/api/env/install-deps":
            code, payload = manager.trigger_install_deps()
            self._send_json(payload, code)
            return

        if path == "/console/api/env/install-whisper":
            code, payload = manager.trigger_install_whisper()
            self._send_json(payload, code)
            return

        if path == "/console/api/service/start":
            code, payload = manager.start()
            self._send_json(payload, code)
            return

        if path == "/console/api/service/stop":
            self._send_json({"service": manager.stop()})
            return

        if path == "/console/api/service/restart":
            manager.stop()
            code, payload = manager.start()
            self._send_json(payload, code)
            return

        if path == "/console/api/open-browser":
            st = manager.status()
            if not st["running"]:
                code, payload = manager.start()
                if code != 200:
                    self._send_json(payload, code)
                    return
                st = payload["service"]
            if not st.get("healthy"):
                self._send_json({"detail": "网站服务仍在初始化中，请稍候几秒待状态灯变绿后再打开。"}, 503)
                return
            url = st["local_url"]
            build_id = get_frontend_build_id() or "1.3.3"
            open_url = f"{url.rstrip('/')}/?v={build_id}"
            _open_url_in_browser(open_url)
            self._send_json({"ok": True, "url": url})
            return

        if path == "/console/api/open-data-dir":
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            opener = "/usr/bin/open" if platform.system() == "Darwin" else (shutil.which("xdg-open") or "")
            if opener and Path(opener).exists():
                subprocess.Popen([opener, str(DATA_DIR)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._send_json({"ok": True, "path": str(DATA_DIR)})
            return

        if path == "/console/api/console/shutdown":
            self._send_json({"ok": True})
            srv = getattr(self, "server", None)

            def _do_quit() -> None:
                time.sleep(0.15)
                try:
                    manager.stop()
                except Exception:
                    pass
                try:
                    (DATA_DIR / "console_url.txt").unlink(missing_ok=True)
                except Exception:
                    pass
                if srv is not None:
                    try:
                        srv.shutdown()
                    except Exception:
                        pass
                os._exit(0)

            threading.Thread(target=_do_quit, daemon=True).start()
            return

        self._send_json({"detail": "Not found"}, 404)


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def pick_console_port() -> int:
    for p in range(17890, 17910):
        if not is_port_in_use(p):
            return p
    return 17890


def _open_url_in_browser(url: str) -> None:
    if platform.system() == "Darwin":
        if Path("/usr/bin/open").is_file():
            subprocess.Popen(["/usr/bin/open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    opener = shutil.which("open") if platform.system() == "Darwin" else shutil.which("xdg-open")
    if opener:
        subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lingo桌面控制台")
    parser.add_argument("--port", type=int, default=0, help="Control panel port")
    parser.add_argument("--window", action="store_true", help="Open desktop control panel automatically in browser")
    parser.add_argument("--native-window", action="store_true", help="Prefer pywebview native window when installed")
    args = parser.parse_args()

    _ensure_settings_table()
    cfg = load_desktop_config()

    port = args.port or pick_console_port()
    url = f"http://127.0.0.1:{port}"
    server = ReusableThreadingHTTPServer(("127.0.0.1", port), ConsoleHTTPHandler)

    url_file = DATA_DIR / "console_url.txt"
    tmp_url = DATA_DIR / "console_url.txt.tmp"
    tmp_url.write_text(url, encoding="utf-8")
    tmp_url.replace(url_file)

    stop_event = threading.Event()

    def _cleanup_on_exit() -> None:
        try:
            manager.stop()
        except Exception:
            pass
        try:
            if url_file.is_file() and url_file.read_text(encoding="utf-8").strip() == url:
                url_file.unlink(missing_ok=True)
        except Exception:
            pass

    atexit.register(_cleanup_on_exit)

    def _handle_sig(_signum: int, _frame: Any) -> None:
        stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_sig)
        except Exception:
            pass

    # Launch auto-start service asynchronously so the control panel responds in < 0.2s
    if cfg.get("auto_start_service"):
        def _auto_start_worker() -> None:
            try:
                if inspect_environment()["core_ready"]:
                    manager.start()
            except Exception as exc:
                manager.append_log(f"自动启动服务失败：{exc}")

        threading.Thread(target=_auto_start_worker, daemon=True).start()

    if not args.window:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            _cleanup_on_exit()
        return

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    for _ in range(30):
        if http_get_ok(f"{url}/console/api/state", timeout=0.5):
            break
        time.sleep(0.1)

    if args.native_window:
        try:
            import webview  # type: ignore

            webview.create_window(
                "Lingo — 桌面控制台",
                url,
                width=1080,
                height=800,
                min_size=(860, 640),
                background_color="#FF7A2D",
            )
            webview.start()
            _cleanup_on_exit()
            return
        except Exception:
            pass

    _open_url_in_browser(url)

    try:
        while not stop_event.is_set() and server_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.shutdown()
        except Exception:
            pass
        _cleanup_on_exit()


if __name__ == "__main__":
    main()

