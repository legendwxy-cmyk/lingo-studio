#!/usr/bin/env python3
"""
Lingo 100% 原生桌面控制台（PyQt6 / macOS Cocoa 原生窗口与菜单栏）。

特性：
1. 纯桌面原生应用界面（非网页、非浏览器标签页、非 WebView），采用与 Lingo Web 学习机一致的
   玩味 3D 材质设计语言（支持柑橘旋钮机 / 薰衣草工坊 / 奶油陶瓷台三套 3D 机壳皮肤）。
2. 复用 desktop_console.py 经过全量质检验收的核心逻辑：共享 SQLite (lexifilm.db) AI 模型配置、
   desktop_config.json 发布配置、实时运行环境自检与一键依赖安装、uvicorn 网站生命周期管理。
3. 支持单实例唤醒（通过本机 UNIX Socket）、关闭窗口最小化到托盘、退出时优雅停止后台服务。
"""
from __future__ import annotations

import json
import os
import platform
import signal
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

# Ensure sibling backend modules resolve regardless of CWD
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

import desktop_console as dc

# Vendor presets matching SettingsModal.jsx & native SwiftUI (LLM-only presets preserve ASR URL/model)
PROVIDER_PRESETS: list[dict[str, Any]] = [
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "llm_base_url": "https://api.deepseek.com/v1",
        "llm_model": "deepseek-chat",
        "asr_base_url": None,
        "asr_model": None,
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-4o-mini",
        "asr_base_url": "https://api.openai.com/v1",
        "asr_model": "whisper-1",
    },
    {
        "id": "qwen",
        "label": "通义千问",
        "llm_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "llm_model": "qwen-plus",
        "asr_base_url": None,
        "asr_model": None,
    },
    {
        "id": "groq",
        "label": "Groq Whisper",
        "llm_base_url": "https://api.groq.com/openai/v1",
        "llm_model": "llama-3.3-70b-versatile",
        "asr_base_url": "https://api.groq.com/openai/v1",
        "asr_model": "whisper-large-v3-turbo",
    },
    {
        "id": "siliconflow",
        "label": "硅基流动",
        "llm_base_url": "https://api.siliconflow.cn/v1",
        "llm_model": "Qwen/Qwen2.5-7B-Instruct",
        "asr_base_url": "https://api.siliconflow.cn/v1",
        "asr_model": "FunAudioLLM/SenseVoiceSmall",
    },
    {
        "id": "gemini",
        "label": "Gemini 兼容",
        "llm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "llm_model": "gemini-2.5-flash",
        "asr_base_url": None,
        "asr_model": None,
    },
]

ASR_MODE_OPTIONS: list[tuple[str, str]] = [
    ("auto", "智能自动（优先云端，失败自动回退本地 Whisper）"),
    ("local_whisper", "纯本地离线 Whisper（完全免费、零网络依赖）"),
    ("cloud_api", "强制使用云端 Whisper API"),
    ("subtitle_only", "仅解析上传字幕（不做语音识别）"),
]

WHISPER_MODELS: list[str] = ["tiny.en", "base.en", "small.en", "tiny", "base", "small"]

# Exact Web App Playful 3D Tactile Skins (tokens.css parity)
SKINS: dict[str, dict[str, str]] = {
    "citrus": {
        "label": "柑橘旋钮机",
        "dot": "#FF7A2D",
        "shell_top": "#FF8E47",
        "shell_bg": "#FF7A2D",
        "shell_bottom": "#FF7224",
        "shell_deep": "#C44908",
        "shell_well": "rgba(255, 245, 228, 0.28)",
        "shell_pill_bg": "#FFF8EB",
        "shell_pill_deep": "#C45312",
        "panel_bg": "#FFF6E8",
        "panel_deep": "#C45312",
        "card_bg": "#FFFFFF",
        "card_deep": "#DECBB0",
        "ink": "#1B1330",
        "ink_deep": "#090512",
        "ink_sub": "#473C5C",
        "ink_muted": "#6A5C7F",
        "accent": "#FFE24C",
        "accent_deep": "#C49B00",
        "accent_soft": "#FFF9CE",
        "mint": "#53D89A",
        "mint_soft": "#D7F8E8",
        "mint_ink": "#0B3320",
        "mint_deep": "#1E8A58",
        "coral": "#E02850",
        "coral_soft": "#FFE4E9",
        "coral_deep": "#8F102D",
        "keycap_bg": "#FFF0D4",
        "keycap_ink": "#542204",
        "keycap_deep": "#D48A3B",
        "dial_outer_0": "#FFF7E8",
        "dial_outer_1": "#FFD699",
        "dial_outer_2": "#DF7E22",
        "dial_inner_0": "#FFFFFF",
        "dial_inner_1": "#FFE9C4",
        "dial_inner_2": "#F3B773",
        "dial_edge": "#A4400A",
    },
    "lavender": {
        "label": "薰衣草工坊",
        "dot": "#B5A1FF",
        "shell_top": "#C4B3FF",
        "shell_bg": "#B5A1FF",
        "shell_bottom": "#A68EFF",
        "shell_deep": "#6E52D4",
        "shell_well": "rgba(255, 255, 255, 0.28)",
        "shell_pill_bg": "#FFFFFF",
        "shell_pill_deep": "#7B62D8",
        "panel_bg": "#F9F7FF",
        "panel_deep": "#7B62D8",
        "card_bg": "#FFFFFF",
        "card_deep": "#CFC3F2",
        "ink": "#1A1230",
        "ink_deep": "#090512",
        "ink_sub": "#3A2E59",
        "ink_muted": "#5B4C80",
        "accent": "#D4FF3F",
        "accent_deep": "#85AD00",
        "accent_soft": "#F4FFBE",
        "mint": "#53D89A",
        "mint_soft": "#D7F8E8",
        "mint_ink": "#0B3320",
        "mint_deep": "#1E8A58",
        "coral": "#E02850",
        "coral_soft": "#FFE4E9",
        "coral_deep": "#8F102D",
        "keycap_bg": "#EDE7FF",
        "keycap_ink": "#2A1666",
        "keycap_deep": "#967EEB",
        "dial_outer_0": "#FFFFFF",
        "dial_outer_1": "#E7DEFF",
        "dial_outer_2": "#8E74EB",
        "dial_inner_0": "#FFFFFF",
        "dial_inner_1": "#F3EEFF",
        "dial_inner_2": "#C4B3FF",
        "dial_edge": "#5C3FC0",
    },
    "ceramic": {
        "label": "奶油陶瓷台",
        "dot": "#EAE7DF",
        "shell_top": "#F7F5F0",
        "shell_bg": "#E7E3DA",
        "shell_bottom": "#E8E4DC",
        "shell_deep": "#BDB7AA",
        "shell_well": "rgba(23, 26, 33, 0.06)",
        "shell_pill_bg": "#FFFFFF",
        "shell_pill_deep": "#C4BFB3",
        "panel_bg": "#F7F5F0",
        "panel_deep": "#BDB7AA",
        "card_bg": "#FFFFFF",
        "card_deep": "#CDC8BC",
        "ink": "#171A21",
        "ink_deep": "#07080B",
        "ink_sub": "#434957",
        "ink_muted": "#5C6374",
        "accent": "#FFE14A",
        "accent_deep": "#BD9900",
        "accent_soft": "#FFF7BD",
        "mint": "#53D89A",
        "mint_soft": "#D7F8E8",
        "mint_ink": "#0B3320",
        "mint_deep": "#1E8A58",
        "coral": "#E02850",
        "coral_soft": "#FFE4E9",
        "coral_deep": "#8F102D",
        "keycap_bg": "#EEF2FF",
        "keycap_ink": "#162B85",
        "keycap_deep": "#8AA0E6",
        "dial_outer_0": "#FFFFFF",
        "dial_outer_1": "#EFECE5",
        "dial_outer_2": "#BDB7AA",
        "dial_inner_0": "#FFFFFF",
        "dial_inner_1": "#F7F5F0",
        "dial_inner_2": "#DCD7CB",
        "dial_edge": "#9A9386",
    },
}


def _resolve_wordmark_path() -> Path | None:
    candidates = [
        dc.FRONTEND_DIST / "lingo-logo.png",
        _BACKEND_DIR.parent / "lingo-logo.png",
        _BACKEND_DIR.parent / "frontend" / "public" / "lingo-logo.png",
        _BACKEND_DIR.parent / "macos" / "native-app" / "Sources" / "LingoReelApp" / "Resources" / "lingo-logo.png",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _resolve_logo_path() -> Path | None:
    candidates = [
        dc.FRONTEND_DIST / "lingo-icon.png",
        _BACKEND_DIR.parent / "macos" / "LingoAppIcon.png",
        _BACKEND_DIR.parent / "frontend" / "public" / "lingo-icon.png",
        dc.FRONTEND_DIST / "lingo-logo.png",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _build_app_icon() -> QIcon:
    logo = _resolve_logo_path()
    if logo is not None:
        return QIcon(str(logo))
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#FF7A2D"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
    painter.setPen(QColor("#FFFDF8"))
    f = QFont()
    f.setPointSize(24)
    f.setBold(True)
    painter.setFont(f)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "L")
    painter.end()
    return QIcon(pix)


def _format_uptime(sec: int) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def _ipc_socket_path() -> Path:
    return dc.DATA_DIR / "native_gui.sock"


def _send_ipc_cmd(sock_path: Path, cmd: str, timeout: float = 1.2) -> str | None:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(sock_path))
            s.sendall((cmd + "\n").encode("utf-8"))
            return s.recv(512).decode("utf-8", errors="ignore").strip()
    except Exception:
        return None


def try_wake_existing_instance() -> bool:
    """If an identical-version native console GUI is already running for this DATA_DIR, raise its window.
    If an older/stale version is running, politely send QUIT so the new version takes over cleanly."""
    sock_path = _ipc_socket_path()
    if not sock_path.exists():
        return False

    status_raw = _send_ipc_cmd(sock_path, "STATUS", timeout=1.2)
    if status_raw is None:
        try:
            sock_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False

    expected_dist = str(dc.FRONTEND_DIST)
    expected_build = dc.get_frontend_build_id()
    version_matches = False
    try:
        obj = json.loads(status_raw)
        if isinstance(obj, dict):
            running_dist = str(obj.get("frontend_dist") or "")
            running_build = str(obj.get("build") or "")
            dist_ok = bool(running_dist) and Path(running_dist).resolve() == Path(expected_dist).resolve()
            build_ok = (not expected_build) or (running_build == expected_build)
            version_matches = dist_ok and build_ok
    except Exception:
        version_matches = False

    if not version_matches:
        _send_ipc_cmd(sock_path, "QUIT", timeout=1.2)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if not sock_path.exists():
                break
            if _send_ipc_cmd(sock_path, "STATUS", timeout=0.2) is None:
                try:
                    sock_path.unlink(missing_ok=True)
                except Exception:
                    pass
                break
            time.sleep(0.12)
        return False

    reply = _send_ipc_cmd(sock_path, "RAISE", timeout=1.2)
    return bool(reply and "OK" in reply)


class WorkerBridge(QObject):
    """Cross-thread Qt signal bridge so background tasks safely update UI on the main thread."""

    envChecked = pyqtSignal(dict)
    serviceActionDone = pyqtSignal(str, bool, str, dict)  # action, ok, message, status
    llmTestDone = pyqtSignal(dict)
    raiseRequested = pyqtSignal()
    quitRequested = pyqtSignal()
    statusPolled = pyqtSignal(dict)


class LingoStatusDial(QWidget):
    """Playful 3D tactile circular hardware dial matching the Web Learning Machine speed dial."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(94, 94)
        self._skin = SKINS["citrus"]
        self._port = 8000
        self._running = False
        self._healthy = False

    def set_skin(self, skin_id: str) -> None:
        self._skin = SKINS.get(skin_id, SKINS["citrus"])
        self.update()

    def set_state(self, port: int, running: bool, healthy: bool) -> None:
        self._port = port
        self._running = running
        self._healthy = healthy
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        s = self._skin
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Bottom 3D lip shadow
        p.setPen(Qt.PenStyle.NoPen)
        edge = QColor(s["dial_edge"])
        edge.setAlpha(95)
        p.setBrush(edge)
        p.drawEllipse(QRectF(5, 8, 84, 84))

        # Outer radial tactile ring
        g_outer = QRadialGradient(QPointF(30, 26), 56)
        g_outer.setColorAt(0.0, QColor(s["dial_outer_0"]))
        g_outer.setColorAt(0.45, QColor(s["dial_outer_1"]))
        g_outer.setColorAt(1.0, QColor(s["dial_outer_2"]))
        p.setBrush(QBrush(g_outer))
        p.setPen(QPen(QColor(s["dial_edge"]), 1.4))
        p.drawEllipse(QRectF(5, 3, 84, 84))

        # Inner glossy cap
        g_inner = QRadialGradient(QPointF(36, 30), 42)
        g_inner.setColorAt(0.0, QColor(s["dial_inner_0"]))
        g_inner.setColorAt(0.58, QColor(s["dial_inner_1"]))
        g_inner.setColorAt(1.0, QColor(s["dial_inner_2"]))
        p.setBrush(QBrush(g_inner))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(15, 13, 64, 64))

        # Indicator LED dot
        dot_color = QColor("#1CC978") if (self._running and self._healthy) else (
            QColor("#F59E0B") if self._running else QColor(s["ink"])
        )
        p.setBrush(dot_color)
        p.drawEllipse(QRectF(43.5, 19, 7, 7))

        # Port text
        p.setPen(QColor(s["ink"]))
        f_port = QFont("Menlo", 12)
        f_port.setBold(True)
        p.setFont(f_port)
        p.drawText(QRectF(12, 31, 70, 22), Qt.AlignmentFlag.AlignCenter, f":{self._port}")

        # Status micro-caption
        p.setPen(QColor(s["ink_sub"]))
        f_sub = QFont()
        f_sub.setPointSize(8)
        f_sub.setBold(True)
        p.setFont(f_sub)
        label = "ON AIR" if (self._running and self._healthy) else ("BOOT" if self._running else "READY")
        p.drawText(QRectF(12, 51, 70, 16), Qt.AlignmentFlag.AlignCenter, label)
        p.end()


def build_skin_stylesheet(skin_id: str = "citrus") -> str:
    s = SKINS.get(skin_id, SKINS["citrus"])
    return f"""
QMainWindow, QWidget#ChassisRoot {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {s["shell_top"]}, stop:0.5 {s["shell_bg"]}, stop:1 {s["shell_bottom"]});
}}
QWidget {{
    color: {s["ink"]};
    font-size: 13px;
}}
QFrame#ChassisHeader {{
    background: transparent;
    border: none;
}}
QFrame#StudioPanel {{
    background-color: {s["panel_bg"]};
    border: 2px solid #FFFFFF;
    border-bottom: 6px solid {s["panel_deep"]};
    border-radius: 22px;
}}
QWidget#PageBody {{
    background-color: transparent;
}}
QFrame#NavWell {{
    background-color: {s["shell_well"]};
    border: 1px solid rgba(27, 19, 48, 0.10);
    border-radius: 17px;
}}
QFrame#StatusPill {{
    background-color: {s["shell_pill_bg"]};
    border: 1px solid #FFFFFF;
    border-bottom: 3px solid {s["shell_pill_deep"]};
    border-radius: 14px;
}}
QFrame#SkinDock {{
    background-color: {s["shell_pill_bg"]};
    border: 1px solid #FFFFFF;
    border-bottom: 3px solid {s["shell_pill_deep"]};
    border-radius: 14px;
}}
QPushButton#NavBtn {{
    padding: 7px 14px;
    border: 1px solid #FFFFFF;
    border-bottom: 3px solid {s["shell_pill_deep"]};
    border-radius: 12px;
    background-color: {s["shell_pill_bg"]};
    color: {s["ink"]};
    font-size: 13px;
    font-weight: 800;
}}
QPushButton#NavBtn:hover {{
    background-color: #FFFFFF;
}}
QPushButton#NavBtn[active="true"] {{
    background-color: {s["ink"]};
    color: {s["accent"]};
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-bottom: 3px solid {s["ink_deep"]};
    font-weight: 900;
}}
QFrame#Card {{
    background-color: {s["card_bg"]};
    border: 1.5px solid {s["card_deep"]};
    border-bottom: 4px solid {s["card_deep"]};
    border-radius: 18px;
}}
QFrame#HeroCardActive {{
    background-color: {s["accent"]};
    border: 1.5px solid #FFFFFF;
    border-bottom: 5px solid {s["accent_deep"]};
    border-radius: 20px;
}}
QFrame#WarnBanner {{
    background-color: {s["accent"]};
    border: 1.5px solid #FFFFFF;
    border-bottom: 4px solid {s["accent_deep"]};
    border-radius: 18px;
}}
QFrame#StatCard {{
    background-color: {s["card_bg"]};
    border: 1.5px solid {s["card_deep"]};
    border-bottom: 4px solid {s["card_deep"]};
    border-radius: 16px;
}}
QPushButton#PrimaryBtn {{
    background-color: {s["ink"]};
    color: {s["accent"]};
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-bottom: 4px solid {s["ink_deep"]};
    border-radius: 13px;
    padding: 8px 16px;
    font-weight: 800;
}}
QPushButton#PrimaryBtn:hover {{
    background-color: #2A1F47;
}}
QPushButton#PrimaryBtn:pressed {{
    border-bottom: 1px solid {s["ink_deep"]};
    padding-top: 10px;
}}
QPushButton#PrimaryBtn:disabled {{
    background-color: #9A92AA;
    color: #EDEBF2;
    border-bottom: 3px solid #7A7388;
}}
QPushButton#MintBtn {{
    background-color: {s["mint"]};
    color: {s["mint_ink"]};
    border: 1px solid rgba(255, 255, 255, 0.48);
    border-bottom: 4px solid {s["mint_deep"]};
    border-radius: 13px;
    padding: 8px 15px;
    font-weight: 800;
}}
QPushButton#MintBtn:hover {{
    background-color: #62E1A5;
}}
QPushButton#MintBtn:disabled {{
    background-color: #A7DFC5;
    color: #466958;
    border-bottom: 3px solid #7EB89E;
}}
QPushButton#SecondaryBtn {{
    background-color: #FFFFFF;
    color: {s["ink"]};
    border: 1.5px solid {s["card_deep"]};
    border-bottom: 4px solid {s["card_deep"]};
    border-radius: 13px;
    padding: 7px 14px;
    font-weight: 700;
}}
QPushButton#SecondaryBtn:hover {{
    background-color: {s["panel_bg"]};
}}
QPushButton#SecondaryBtn:disabled {{
    color: #9CA3AF;
    background-color: #F9FAFB;
}}
QPushButton#DangerBtn {{
    background-color: {s["coral"]};
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.28);
    border-bottom: 4px solid {s["coral_deep"]};
    border-radius: 13px;
    padding: 7px 14px;
    font-weight: 800;
}}
QPushButton#DangerBtn:hover {{
    background-color: #EE3A61;
}}
QPushButton#PresetBtn {{
    background-color: {s["keycap_bg"]};
    color: {s["keycap_ink"]};
    border: 1px solid rgba(255, 255, 255, 0.72);
    border-bottom: 3px solid {s["keycap_deep"]};
    border-radius: 12px;
    padding: 7px 12px;
    font-weight: 800;
}}
QPushButton#PresetBtn:hover {{
    background-color: {s["accent"]};
    color: {s["ink"]};
    border-bottom: 3px solid {s["accent_deep"]};
}}
QLineEdit, QSpinBox, QComboBox {{
    background-color: {s["panel_bg"]};
    color: {s["ink"]};
    border: 1.5px solid {s["card_deep"]};
    border-radius: 11px;
    padding: 6px 10px;
    min-height: 22px;
    font-weight: 600;
}}
QSpinBox {{
    padding-right: 22px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 2px solid {s["ink"]};
    background-color: #FFFFFF;
}}
QCheckBox {{
    spacing: 9px;
    font-weight: 700;
    color: {s["ink"]};
}}
QCheckBox::indicator {{
    width: 38px;
    height: 20px;
    border-radius: 10px;
    border: 2px solid {s["ink"]};
    background-color: {s["ink"]};
}}
QCheckBox::indicator:checked {{
    background-color: #1FB671;
    border: 2px solid #147E4D;
}}
QPlainTextEdit#LogConsole {{
    background-color: {s["ink"]};
    color: #F3EEFF;
    border: 1.5px solid rgba(255, 255, 255, 0.12);
    border-bottom: 4px solid {s["ink_deep"]};
    border-radius: 18px;
    padding: 12px;
    font-family: "Menlo", "SF Mono", "JetBrains Mono", "DejaVu Sans Mono", monospace;
    font-size: 12px;
}}
QLabel#PageTitle {{
    font-size: 21px;
    font-weight: 900;
    color: {s["ink"]};
}}
QLabel#PageSub {{
    font-size: 12.5px;
    color: {s["ink_muted"]};
    font-weight: 600;
}}
QLabel#CardTitle {{
    font-size: 15px;
    font-weight: 800;
    color: {s["ink"]};
}}
QLabel#HintLabel {{
    font-size: 11.5px;
    color: {s["ink_muted"]};
}}
QLabel#ToastOk {{
    background-color: {s["ink"]};
    color: {s["accent"]};
    border-bottom: 3px solid {s["ink_deep"]};
    border-radius: 14px;
    padding: 9px 18px;
    font-weight: 800;
}}
QLabel#ToastErr {{
    background-color: {s["coral"]};
    color: #FFFFFF;
    border-bottom: 3px solid {s["coral_deep"]};
    border-radius: 14px;
    padding: 9px 18px;
    font-weight: 800;
}}
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 6px 2px 6px 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(27, 19, 48, 0.22);
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(27, 19, 48, 0.38);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0px;
}}
"""


APP_STYLESHEET = build_skin_stylesheet("citrus")


class TactileToggle(QCheckBox):
    """Playful 3D pill toggle switch with white marble knob matching Web Learning Machine switches."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(28)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text()) + 12 if self.text() else 0
        return QSize(50 + text_w, max(28, fm.height() + 8))

    def hitButton(self, pos) -> bool:  # type: ignore[override]
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        track_w, track_h = 44.0, 24.0
        ty = (h - track_h) / 2.0
        checked = self.isChecked()

        track_rect = QRectF(1.0, ty, track_w, track_h)
        track_bg = QColor("#1FB671") if checked else QColor("#1B1330")
        track_border = QColor("#147E4D") if checked else QColor("#090512")
        p.setBrush(track_bg)
        p.setPen(QPen(track_border, 1.5))
        p.drawRoundedRect(track_rect, track_h / 2.0, track_h / 2.0)

        knob_d = 18.0
        kx = (1.0 + track_w - knob_d - 3.0) if checked else (1.0 + 3.0)
        ky = ty + (track_h - knob_d) / 2.0
        knob_grad = QRadialGradient(QPointF(kx + 6.0, ky + 5.0), 14.0)
        knob_grad.setColorAt(0.0, QColor("#FFFFFF"))
        knob_grad.setColorAt(0.75, QColor("#F5F1EA"))
        knob_grad.setColorAt(1.0, QColor("#DDD5C8"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 55))
        p.drawEllipse(QRectF(kx, ky + 1.2, knob_d, knob_d))
        p.setBrush(QBrush(knob_grad))
        p.drawEllipse(QRectF(kx, ky, knob_d, knob_d))

        if self.text():
            p.setPen(QColor("#1B1330") if self.isEnabled() else QColor("#9CA3AF"))
            text_rect = QRectF(track_w + 11.0, 0.0, max(10.0, self.width() - track_w - 12.0), float(h))
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        p.end()


class LingoReelNativeWindow(QMainWindow):
    def __init__(self, manager: dc.DesktopManager | None = None, enable_ipc: bool = True, enable_tray: bool = True) -> None:
        super().__init__()
        self.manager = manager or dc.DesktopManager()
        self.bridge = WorkerBridge()
        self._quitting = False
        self._busy_service = False
        self._busy_env = False
        self._busy_llm = False
        self._clear_llm_key = False
        self._clear_asr_key = False
        self._last_env_info: dict[str, Any] = {}
        self._last_status: dict[str, Any] = {}
        self._last_log_sig: tuple[Any, ...] | None = None
        self._last_log_filter = ""
        self._polling = False
        self._skin_id = "citrus"
        self._detected_lan_ip = dc.detect_lan_ip()
        self._auto_start_pending = bool(dc.load_desktop_config().get("auto_start_service"))
        self._ipc_stop = threading.Event()
        self._ipc_sock: socket.socket | None = None

        self.setWindowTitle("Lingo — 桌面控制台")
        self.setWindowIcon(_build_app_icon())
        self.resize(1040, 710)
        self.setMinimumSize(860, 580)

        self._setup_menus()
        self._build_ui()
        self._connect_signals()
        self.apply_skin("citrus")

        self.tray: QSystemTrayIcon | None = None
        if enable_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self._setup_tray()

        if enable_ipc:
            self._start_ipc_server()

        # Load initial values from disk (fast, no blocking network calls)
        self.manager.append_log(f"Lingo 原生桌面控制台已就绪（数据目录：{dc.DATA_DIR}）")
        self.load_desktop_config_into_form()
        self.load_ai_settings_into_form()
        self._apply_status_snapshot(self.manager.status())

        # Start async env check (auto_start_service triggers deterministically once env check finishes)
        self.refresh_environment_async()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1500)
        self._poll_timer.timeout.connect(self._poll_status_async)
        self._poll_timer.start()

        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._hide_toast)

    # ------------------------------------------------------------------ Skin Switcher
    def apply_skin(self, skin_id: str) -> None:
        if skin_id not in SKINS:
            skin_id = "citrus"
        self._skin_id = skin_id
        qss = build_skin_stylesheet(skin_id)
        self.setStyleSheet(qss)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss)
        if hasattr(self, "dial_widget"):
            self.dial_widget.set_skin(skin_id)
        if hasattr(self, "skin_buttons"):
            s_cur = SKINS[skin_id]
            for sid, btn in self.skin_buttons.items():
                dot_hex = SKINS[sid]["dot"]
                border = f"2.5px solid {s_cur['ink']}" if sid == skin_id else "1.5px solid rgba(27,19,48,0.22)"
                btn.setStyleSheet(
                    f"background-color: {dot_hex}; border: {border}; border-radius: 10px;"
                )

    # ------------------------------------------------------------------ Menus & Tray
    def _setup_menus(self) -> None:
        mb = self.menuBar()
        assert mb is not None

        app_menu = mb.addMenu("控制")
        assert app_menu is not None
        act_show = QAction("显示 Lingo 控制台", self)
        act_show.triggered.connect(self.bring_to_front)
        app_menu.addAction(act_show)

        act_open_web = QAction("在浏览器打开 Lingo 学习机", self)
        act_open_web.triggered.connect(self.open_web_app)
        app_menu.addAction(act_open_web)

        act_open_dir = QAction("打开数据目录", self)
        act_open_dir.triggered.connect(self.open_data_dir)
        app_menu.addAction(act_open_dir)

        app_menu.addSeparator()
        act_quit = QAction("退出 Lingo", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.quit_application)
        app_menu.addAction(act_quit)

        edit_menu = mb.addMenu("编辑")
        assert edit_menu is not None
        for label, std_key, method in [
            ("撤销", QKeySequence.StandardKey.Undo, "undo"),
            ("剪切", QKeySequence.StandardKey.Cut, "cut"),
            ("拷贝", QKeySequence.StandardKey.Copy, "copy"),
            ("粘贴", QKeySequence.StandardKey.Paste, "paste"),
            ("全选", QKeySequence.StandardKey.SelectAll, "selectAll"),
        ]:
            act = QAction(label, self)
            act.setShortcut(std_key)
            act.triggered.connect(lambda _=False, m=method: self._dispatch_edit_action(m))
            edit_menu.addAction(act)

    def _dispatch_edit_action(self, method_name: str) -> None:
        w = QApplication.focusWidget()
        if w is not None and hasattr(w, method_name):
            try:
                getattr(w, method_name)()
            except Exception:
                pass

    def _setup_tray(self) -> None:
        tray = QSystemTrayIcon(_build_app_icon(), self)
        tray.setToolTip("Lingo 桌面控制台")
        menu = QMenu()
        self.tray_act_status = QAction("状态：已停止", self)
        self.tray_act_status.setEnabled(False)
        menu.addAction(self.tray_act_status)
        menu.addSeparator()

        act_show = QAction("打开 Lingo 控制台", self)
        act_show.triggered.connect(self.bring_to_front)
        menu.addAction(act_show)

        act_web = QAction("在浏览器打开 Lingo 学习机", self)
        act_web.triggered.connect(self.open_web_app)
        menu.addAction(act_web)

        menu.addSeparator()
        self.tray_act_toggle = QAction("启动学习机服务", self)
        self.tray_act_toggle.triggered.connect(self._toggle_service_from_tray)
        menu.addAction(self.tray_act_toggle)

        menu.addSeparator()
        act_quit = QAction("退出 Lingo", self)
        act_quit.triggered.connect(self.quit_application)
        menu.addAction(act_quit)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self.tray = tray

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.bring_to_front()

    def _toggle_service_from_tray(self) -> None:
        if self.manager.is_running():
            self.stop_service_async()
        else:
            self.start_service_async()

    # ------------------------------------------------------------------ Single-Instance IPC
    def _start_ipc_server(self) -> None:
        sock_path = _ipc_socket_path()
        try:
            sock_path.parent.mkdir(parents=True, exist_ok=True)
            sock_path.unlink(missing_ok=True)
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(sock_path))
            srv.listen(4)
            srv.settimeout(0.5)
            self._ipc_sock = srv
        except Exception as exc:
            self.manager.append_log(f"单实例监听跳过：{exc}")
            return

        def _loop() -> None:
            while not self._ipc_stop.is_set():
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    data = conn.recv(128).decode("utf-8", errors="ignore").strip()
                    if data == "RAISE":
                        self._safe_emit("raiseRequested")
                        conn.sendall(b"OK\n")
                    elif data == "QUIT":
                        conn.sendall(b"OK\n")
                        self._safe_emit("quitRequested")
                    elif data == "STATUS":
                        payload = json.dumps(
                            {
                                "running": self.manager.is_running(),
                                "frontend_dist": str(dc.FRONTEND_DIST),
                                "build": dc.get_frontend_build_id(),
                            }
                        ).encode("utf-8")
                        conn.sendall(payload + b"\n")
                    else:
                        conn.sendall(b"OK\n")
                except Exception:
                    pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

        threading.Thread(target=_loop, daemon=True).start()

    def _stop_ipc_server(self) -> None:
        self._ipc_stop.set()
        if self._ipc_sock is not None:
            try:
                self._ipc_sock.close()
            except Exception:
                pass
            self._ipc_sock = None
            try:
                _ipc_socket_path().unlink(missing_ok=True)
            except Exception:
                pass

    # ------------------------------------------------------------------ UI Construction (Playful 3D Chassis)
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("ChassisRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 10, 14, 14)
        outer.setSpacing(10)

        outer.addWidget(self._build_top_chassis_bar())

        studio_panel = QFrame()
        studio_panel.setObjectName("StudioPanel")
        panel_layout = QVBoxLayout(studio_panel)
        panel_layout.setContentsMargins(4, 4, 4, 8)
        panel_layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setObjectName("MainStack")
        self.stack.addWidget(self._wrap_scroll(self._build_overview_page()))
        self.stack.addWidget(self._wrap_scroll(self._build_environment_page()))
        self.stack.addWidget(self._wrap_scroll(self._build_ai_page()))
        self.stack.addWidget(self._build_logs_page())
        panel_layout.addWidget(self.stack, 1)

        # Toast bar pinned cleanly at bottom of inner studio stage
        toast_bar = QHBoxLayout()
        toast_bar.setContentsMargins(20, 4, 20, 6)
        self.lbl_toast = QLabel("")
        self.lbl_toast.setObjectName("ToastOk")
        self.lbl_toast.setVisible(False)
        self.lbl_toast.setWordWrap(True)
        toast_bar.addStretch(1)
        toast_bar.addWidget(self.lbl_toast)
        toast_bar.addStretch(1)
        panel_layout.addLayout(toast_bar)

        outer.addWidget(studio_panel, 1)
        self.switch_tab(0)

    def _wrap_scroll(self, widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(widget)
        return area

    def _build_top_chassis_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("ChassisHeader")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(10)

        # Left: Frameless transparent 3D Lingo Wordmark (ZERO box/backing!) + Status Pill
        logo_lbl = QLabel()
        logo_lbl.setStyleSheet("background: transparent; border: none;")
        wm = _resolve_wordmark_path()
        if wm is not None:
            pix = QPixmap(str(wm))
            scaled = pix.scaledToHeight(38, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(scaled)
        else:
            logo_lbl.setText("Lingo")
            logo_lbl.setStyleSheet("font-size: 24px; font-weight: 900; color: #1B1330; background: transparent;")
        lay.addWidget(logo_lbl)

        pill = QFrame()
        pill.setObjectName("StatusPill")
        pill_lay = QHBoxLayout(pill)
        pill_lay.setContentsMargins(10, 5, 10, 5)
        pill_lay.setSpacing(6)
        self.lbl_sidebar_dot = QLabel("●")
        self.lbl_sidebar_dot.setStyleSheet("color: #9CA3AF; font-size: 11px; background: transparent;")
        self.lbl_sidebar_status = QLabel("服务已停止")
        self.lbl_sidebar_status.setStyleSheet("font-size: 12px; font-weight: 800; background: transparent;")
        self.lbl_sidebar_port = QLabel(":8000")
        self.lbl_sidebar_port.setStyleSheet("font-size: 11px; color: #5A4E70; font-family: monospace; font-weight: 700; background: transparent;")
        pill_lay.addWidget(self.lbl_sidebar_dot)
        pill_lay.addWidget(self.lbl_sidebar_status)
        pill_lay.addWidget(self.lbl_sidebar_port)
        lay.addWidget(pill)

        lay.addStretch(1)

        # Center: Recessed 3D Pill Navigation Well (exact Web TopBar signature)
        nav_well = QFrame()
        nav_well.setObjectName("NavWell")
        nav_lay = QHBoxLayout(nav_well)
        nav_lay.setContentsMargins(6, 5, 6, 5)
        nav_lay.setSpacing(6)
        self.nav_buttons: list[QPushButton] = []
        nav_specs = [
            ("nav_overview", "服务总览"),
            ("nav_env", "环境与依赖"),
            ("nav_ai", "AI 模型配置"),
            ("nav_logs", "运行日志"),
        ]
        for idx, (obj_name, title) in enumerate(nav_specs):
            btn = QPushButton(title)
            btn.setObjectName("NavBtn")
            btn.setProperty("navKey", obj_name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=idx: self.switch_tab(i))
            self.nav_buttons.append(btn)
            nav_lay.addWidget(btn)
        lay.addWidget(nav_well)

        lay.addStretch(1)

        # Right: 3-Dot Skin Switcher + Mint Open Web + Quit
        skin_dock = QFrame()
        skin_dock.setObjectName("SkinDock")
        sd_lay = QHBoxLayout(skin_dock)
        sd_lay.setContentsMargins(8, 5, 8, 5)
        sd_lay.setSpacing(6)
        self.skin_buttons: dict[str, QPushButton] = {}
        for sid, sdata in SKINS.items():
            sb_btn = QPushButton("")
            sb_btn.setFixedSize(20, 20)
            sb_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            sb_btn.setToolTip(f"切换外壳皮肤：{sdata['label']}")
            sb_btn.clicked.connect(lambda _=False, target=sid: self.apply_skin(target))
            self.skin_buttons[sid] = sb_btn
            sd_lay.addWidget(sb_btn)
        lay.addWidget(skin_dock)

        self.btn_sidebar_open_web = QPushButton("打开学习机")
        self.btn_sidebar_open_web.setObjectName("MintBtn")
        self.btn_sidebar_open_web.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sidebar_open_web.clicked.connect(self.open_web_app)
        lay.addWidget(self.btn_sidebar_open_web)

        self.btn_sidebar_quit = QPushButton("退出")
        self.btn_sidebar_quit.setObjectName("SecondaryBtn")
        self.btn_sidebar_quit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sidebar_quit.clicked.connect(self.quit_application)
        lay.addWidget(self.btn_sidebar_quit)

        return bar

    # ---- TAB 0: OVERVIEW ----
    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PageBody")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(15)

        title = QLabel("服务总览与主机发布")
        title.setObjectName("PageTitle")
        sub = QLabel("一键启停 Lingo 本机学习机服务、配置监听端口与局域网共享，随后直接在浏览器中打开使用。")
        sub.setObjectName("PageSub")
        sub.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(sub)

        # Missing dependencies warning banner (Sunny 3D highlight card)
        self.banner_missing_deps = QFrame()
        self.banner_missing_deps.setObjectName("WarnBanner")
        b_lay = QHBoxLayout(self.banner_missing_deps)
        b_lay.setContentsMargins(16, 12, 16, 12)
        b_text = QVBoxLayout()
        bt1 = QLabel("检测到缺失核心运行依赖")
        bt1.setStyleSheet("font-weight: 900; font-size: 14px; color: #1B1330; background: transparent;")
        bt2 = QLabel("首次使用请点击右侧前往「环境与依赖」一键补装 Python 虚拟环境、FFmpeg 与本地 Whisper。")
        bt2.setStyleSheet("font-size: 12px; font-weight: 600; color: #473C5C; background: transparent;")
        bt2.setWordWrap(True)
        b_text.addWidget(bt1)
        b_text.addWidget(bt2)
        b_lay.addLayout(b_text, 1)
        self.btn_goto_env = QPushButton("前往一键安装")
        self.btn_goto_env.setObjectName("PrimaryBtn")
        self.btn_goto_env.clicked.connect(lambda: self.switch_tab(1))
        b_lay.addWidget(self.btn_goto_env)
        self.banner_missing_deps.setVisible(False)
        lay.addWidget(self.banner_missing_deps)

        # Hero Service Card (with Playful 3D Hardware Status Dial!)
        self.hero_card = QFrame()
        self.hero_card.setObjectName("Card")
        hero = self.hero_card
        h_lay = QVBoxLayout(hero)
        h_lay.setContentsMargins(20, 18, 20, 18)
        h_lay.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(18)
        self.dial_widget = LingoStatusDial()
        top_row.addWidget(self.dial_widget)

        hero_right = QVBoxLayout()
        hero_right.setSpacing(10)

        title_line = QHBoxLayout()
        self.lbl_hero_dot = QLabel("●")
        self.lbl_hero_dot.setStyleSheet("font-size: 16px; color: #9CA3AF; background: transparent;")
        self.lbl_status_title = QLabel("学习机服务已停止")
        self.lbl_status_title.setStyleSheet("font-size: 18px; font-weight: 900; background: transparent;")
        self.lbl_pid = QLabel("")
        self.lbl_pid.setStyleSheet(
            "font-size: 11px; color: #FFFFFF; background: #1B1330; border-radius: 8px; padding: 3px 9px; font-family: monospace; font-weight: 700;"
        )
        self.lbl_pid.setVisible(False)
        title_line.addWidget(self.lbl_hero_dot)
        title_line.addWidget(self.lbl_status_title)
        title_line.addWidget(self.lbl_pid)
        title_line.addStretch(1)
        hero_right.addLayout(title_line)

        meta_line = QHBoxLayout()
        self.lbl_local_url = QLabel("本机地址：http://127.0.0.1:8000")
        self.lbl_local_url.setStyleSheet("font-size: 12.5px; color: #473C5C; font-family: monospace; font-weight: 700; background: transparent;")
        self.lbl_uptime = QLabel("")
        self.lbl_uptime.setStyleSheet("font-size: 12px; color: #5A4E70; font-family: monospace; font-weight: 700; background: transparent;")
        meta_line.addWidget(self.lbl_local_url)
        meta_line.addSpacing(12)
        meta_line.addWidget(self.lbl_uptime)
        meta_line.addStretch(1)
        hero_right.addLayout(meta_line)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_start_service = QPushButton("启动学习机服务")
        self.btn_start_service.setObjectName("PrimaryBtn")
        self.btn_start_service.clicked.connect(self.start_service_async)

        self.btn_open_web = QPushButton("在浏览器打开学习机")
        self.btn_open_web.setObjectName("MintBtn")
        self.btn_open_web.clicked.connect(self.open_web_app)
        self.btn_open_web.setVisible(False)

        self.btn_restart_service = QPushButton("重启服务")
        self.btn_restart_service.setObjectName("SecondaryBtn")
        self.btn_restart_service.clicked.connect(self.restart_service_async)
        self.btn_restart_service.setVisible(False)

        self.btn_stop_service = QPushButton("停止服务")
        self.btn_stop_service.setObjectName("DangerBtn")
        self.btn_stop_service.clicked.connect(self.stop_service_async)
        self.btn_stop_service.setVisible(False)

        self.btn_copy_url = QPushButton("复制网址")
        self.btn_copy_url.setObjectName("SecondaryBtn")
        self.btn_copy_url.clicked.connect(self._copy_local_url)

        btn_row.addWidget(self.btn_start_service)
        btn_row.addWidget(self.btn_open_web)
        btn_row.addWidget(self.btn_restart_service)
        btn_row.addWidget(self.btn_stop_service)
        btn_row.addWidget(self.btn_copy_url)
        btn_row.addStretch(1)
        hero_right.addLayout(btn_row)

        top_row.addLayout(hero_right, 1)
        h_lay.addLayout(top_row)

        # LAN Share Row (Hero Banner)
        self.lan_row_widget = QWidget()
        lan_lay = QHBoxLayout(self.lan_row_widget)
        lan_lay.setContentsMargins(0, 6, 0, 0)
        lan_lay.setSpacing(8)
        self.lbl_lan_prefix = QLabel("局域网同 Wi-Fi 访问：")
        self.lbl_lan_url = QLabel("")
        self.lbl_lan_url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_lan_url.setStyleSheet("font-size: 13px; font-weight: 800; color: #1D4ED8; font-family: monospace;")
        self.lbl_lan_hero_badge = QLabel("")
        self.lbl_lan_hero_badge.setStyleSheet(
            "font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; "
            "background: #DCFCE7; color: #166534;"
        )
        self.btn_hero_apply_lan = QPushButton("立即应用并重启")
        self.btn_hero_apply_lan.setObjectName("PrimaryBtn")
        self.btn_hero_apply_lan.clicked.connect(self._apply_lan_and_restart)
        self.btn_hero_apply_lan.setVisible(False)
        self.btn_copy_lan = QPushButton("复制局域网地址")
        self.btn_copy_lan.setObjectName("SecondaryBtn")
        self.btn_copy_lan.clicked.connect(self._copy_lan_url)
        lan_lay.addWidget(self.lbl_lan_prefix)
        lan_lay.addWidget(self.lbl_lan_url)
        lan_lay.addWidget(self.lbl_lan_hero_badge)
        lan_lay.addStretch(1)
        lan_lay.addWidget(self.btn_hero_apply_lan)
        lan_lay.addWidget(self.btn_copy_lan)
        self.lan_row_widget.setVisible(False)
        h_lay.addWidget(self.lan_row_widget)

        lay.addWidget(hero)

        # 4 Stat Cards
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self.stat_episodes = self._make_stat_card("已拆解语料", "0 篇")
        self.stat_vocab = self._make_stat_card("生词本收藏", "0 词")
        self.stat_env = self._make_stat_card("运行环境", "检测中...")
        self.stat_llm = self._make_stat_card("AI 大模型", "离线模式")
        for card_w, _ in (self.stat_episodes, self.stat_vocab, self.stat_env, self.stat_llm):
            stats_row.addWidget(card_w, 1)
        lay.addLayout(stats_row)

        # Publish & Security Config Card
        cfg_card = QFrame()
        cfg_card.setObjectName("Card")
        c_lay = QVBoxLayout(cfg_card)
        c_lay.setContentsMargins(18, 16, 18, 16)
        c_lay.setSpacing(12)

        ct = QLabel("基础发布与安全设置")
        ct.setObjectName("CardTitle")
        c_lay.addWidget(ct)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)

        self.spin_port = QSpinBox()
        self.spin_port.setObjectName("spin_port")
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(8000)
        self.spin_port.setFixedWidth(130)
        self.spin_port.valueChanged.connect(lambda _: self._update_lan_address_ui())
        self._add_form_row(grid, 0, "监听端口", "范围 1024 - 65535，默认 8000", self.spin_port)

        lan_ctrl_wrap = QWidget()
        lan_ctrl_lay = QVBoxLayout(lan_ctrl_wrap)
        lan_ctrl_lay.setContentsMargins(0, 0, 0, 0)
        lan_ctrl_lay.setSpacing(8)

        self.chk_lan = TactileToggle("允许局域网同 Wi-Fi 设备访问 (0.0.0.0)")
        self.chk_lan.setObjectName("chk_lan")
        self.chk_lan.toggled.connect(self._on_lan_toggle_changed)
        lan_ctrl_lay.addWidget(self.chk_lan)

        # Immediate Inline LAN Address Card shown right beneath the toggle when ON
        self.lan_inline_box = QFrame()
        self.lan_inline_box.setObjectName("lan_inline_box")
        self.lan_inline_box.setStyleSheet(
            "QFrame#lan_inline_box { background: #EEF6FF; border: 1.5px solid #93C5FD; border-radius: 12px; }"
        )
        inline_lay = QHBoxLayout(self.lan_inline_box)
        inline_lay.setContentsMargins(12, 10, 12, 10)
        inline_lay.setSpacing(10)

        inline_txt = QVBoxLayout()
        inline_txt.setSpacing(2)
        self.lbl_lan_inline_url = QLabel("")
        self.lbl_lan_inline_url.setObjectName("lbl_lan_inline_url")
        self.lbl_lan_inline_url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_lan_inline_url.setStyleSheet(
            "font-size: 13.5px; font-weight: 800; color: #1D4ED8; font-family: monospace; background: transparent;"
        )
        self.lbl_lan_inline_hint = QLabel("")
        self.lbl_lan_inline_hint.setStyleSheet(
            "font-size: 11.5px; font-weight: 600; color: #334155; background: transparent;"
        )
        self.lbl_lan_inline_hint.setWordWrap(True)
        inline_txt.addWidget(self.lbl_lan_inline_url)
        inline_txt.addWidget(self.lbl_lan_inline_hint)
        inline_lay.addLayout(inline_txt, 1)

        self.btn_lan_apply_restart = QPushButton("立即应用并重启")
        self.btn_lan_apply_restart.setObjectName("PrimaryBtn")
        self.btn_lan_apply_restart.clicked.connect(self._apply_lan_and_restart)
        self.btn_lan_apply_restart.setVisible(False)
        inline_lay.addWidget(self.btn_lan_apply_restart)

        self.btn_lan_inline_copy = QPushButton("复制地址")
        self.btn_lan_inline_copy.setObjectName("SecondaryBtn")
        self.btn_lan_inline_copy.clicked.connect(self._copy_lan_url)
        inline_lay.addWidget(self.btn_lan_inline_copy)

        self.btn_lan_inline_refresh = QPushButton("刷新检测")
        self.btn_lan_inline_refresh.setObjectName("SecondaryBtn")
        self.btn_lan_inline_refresh.clicked.connect(self._refresh_lan_ip)
        self.btn_lan_inline_refresh.setVisible(False)
        inline_lay.addWidget(self.btn_lan_inline_refresh)

        self.lan_inline_box.setVisible(False)
        lan_ctrl_lay.addWidget(self.lan_inline_box)

        self._add_form_row(grid, 1, "局域网共享", "开启后 iPad / 手机可访问本机学习机", lan_ctrl_wrap)

        pw_wrap = QWidget()
        pw_lay = QHBoxLayout(pw_wrap)
        pw_lay.setContentsMargins(0, 0, 0, 0)
        pw_lay.setSpacing(8)
        self.edit_password = QLineEdit()
        self.edit_password.setObjectName("edit_password")
        self.edit_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_password.setPlaceholderText("留空表示免密直接进入学习机")
        self.btn_toggle_pw = QPushButton("显示")
        self.btn_toggle_pw.setObjectName("SecondaryBtn")
        self.btn_toggle_pw.setCheckable(True)
        self.btn_toggle_pw.toggled.connect(
            lambda checked: (
                self.edit_password.setEchoMode(
                    QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
                ),
                self.btn_toggle_pw.setText("隐藏" if checked else "显示"),
            )
        )
        pw_lay.addWidget(self.edit_password, 1)
        pw_lay.addWidget(self.btn_toggle_pw)
        self._add_form_row(grid, 2, "访问口令锁", "可选；设置后访问学习机需先输口令解锁", pw_wrap)

        self.chk_hf_mirror = TactileToggle("启用国内下载加速镜像（hf-mirror / 清华 PyPI）")
        self.chk_hf_mirror.setObjectName("chk_hf_mirror")
        self._add_form_row(grid, 3, "国内加速镜像", "加速下载离线 Whisper 语音模型与依赖", self.chk_hf_mirror)

        self.chk_auto_start = TactileToggle("打开桌面控制台时自动启动学习机服务")
        self.chk_auto_start.setObjectName("chk_auto_start")
        self._add_form_row(grid, 4, "自动启动服务", "下次打开本程序即自动就绪", self.chk_auto_start)

        c_lay.addLayout(grid)

        cfg_actions = QHBoxLayout()
        cfg_actions.addStretch(1)
        self.btn_reset_config = QPushButton("还原")
        self.btn_reset_config.setObjectName("SecondaryBtn")
        self.btn_reset_config.clicked.connect(self.load_desktop_config_into_form)
        self.btn_save_config = QPushButton("保存发布配置")
        self.btn_save_config.setObjectName("PrimaryBtn")
        self.btn_save_config.clicked.connect(self.save_desktop_config_from_form)
        cfg_actions.addWidget(self.btn_reset_config)
        cfg_actions.addWidget(self.btn_save_config)
        c_lay.addLayout(cfg_actions)

        lay.addWidget(cfg_card)
        lay.addStretch(1)
        return page

    def _make_stat_card(self, title: str, initial_val: str) -> tuple[QFrame, QLabel]:
        f = QFrame()
        f.setObjectName("StatCard")
        fl = QVBoxLayout(f)
        fl.setContentsMargins(14, 12, 14, 12)
        fl.setSpacing(4)
        lt = QLabel(title)
        lt.setStyleSheet("font-size: 12px; color: #64607A;")
        lv = QLabel(initial_val)
        lv.setStyleSheet("font-size: 17px; font-weight: 800; color: #1B1330;")
        fl.addWidget(lt)
        fl.addWidget(lv)
        return f, lv

    def _add_form_row(self, grid: QGridLayout, row: int, label: str, hint: str, widget: QWidget) -> None:
        left = QWidget()
        left.setFixedWidth(220)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(1)
        l1 = QLabel(label)
        l1.setStyleSheet("font-weight: 700; font-size: 13px;")
        l2 = QLabel(hint)
        l2.setObjectName("HintLabel")
        l2.setWordWrap(True)
        ll.addWidget(l1)
        ll.addWidget(l2)
        grid.addWidget(left, row, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(widget, row, 1, Qt.AlignmentFlag.AlignVCenter)

    # ---- TAB 1: ENVIRONMENT ----
    def _build_environment_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PageBody")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(16)

        hdr = QHBoxLayout()
        h_text = QVBoxLayout()
        t = QLabel("运行环境与依赖管理")
        t.setObjectName("PageTitle")
        s = QLabel("自动检测 Python、独立虚拟环境、FFmpeg 与离线语音模型；缺失项可一键自动补齐。")
        s.setObjectName("PageSub")
        s.setWordWrap(True)
        h_text.addWidget(t)
        h_text.addWidget(s)
        hdr.addLayout(h_text, 1)

        self.btn_env_refresh = QPushButton("重新检测")
        self.btn_env_refresh.setObjectName("SecondaryBtn")
        self.btn_env_refresh.clicked.connect(self.refresh_environment_async)
        hdr.addWidget(self.btn_env_refresh)
        lay.addLayout(hdr)

        # Action Card
        act_card = QFrame()
        act_card.setObjectName("Card")
        al = QVBoxLayout(act_card)
        al.setContentsMargins(18, 16, 18, 16)
        al.setSpacing(10)

        self.lbl_env_banner_title = QLabel("正在扫描本机运行环境...")
        self.lbl_env_banner_title.setStyleSheet("font-size: 15px; font-weight: 800;")
        self.lbl_env_banner_sub = QLabel("请稍候，正在检查独立虚拟环境与模型依赖。")
        self.lbl_env_banner_sub.setObjectName("HintLabel")
        self.lbl_env_banner_sub.setWordWrap(True)
        al.addWidget(self.lbl_env_banner_title)
        al.addWidget(self.lbl_env_banner_sub)

        self.progress_install = QProgressBar()
        self.progress_install.setRange(0, 0)
        self.progress_install.setFixedHeight(8)
        self.progress_install.setVisible(False)
        al.addWidget(self.progress_install)

        act_btns = QHBoxLayout()
        act_btns.setSpacing(10)
        self.btn_install_deps = QPushButton("一键安装 / 修复全部依赖")
        self.btn_install_deps.setObjectName("PrimaryBtn")
        self.btn_install_deps.clicked.connect(self.trigger_install_deps)

        self.btn_install_whisper = QPushButton("一键预热离线语音模型")
        self.btn_install_whisper.setObjectName("SecondaryBtn")
        self.btn_install_whisper.clicked.connect(self.trigger_install_whisper)

        self.btn_env_logs = QPushButton("查看实时日志")
        self.btn_env_logs.setObjectName("SecondaryBtn")
        self.btn_env_logs.clicked.connect(lambda: self.switch_tab(3))

        act_btns.addWidget(self.btn_install_deps)
        act_btns.addWidget(self.btn_install_whisper)
        act_btns.addStretch(1)
        act_btns.addWidget(self.btn_env_logs)
        al.addLayout(act_btns)
        lay.addWidget(act_card)

        # Checklist Card
        list_card = QFrame()
        list_card.setObjectName("Card")
        lc_lay = QVBoxLayout(list_card)
        lc_lay.setContentsMargins(18, 16, 18, 16)
        lc_lay.setSpacing(10)
        lt = QLabel("依赖检测清单")
        lt.setObjectName("CardTitle")
        lc_lay.addWidget(lt)

        self.env_list_layout = QVBoxLayout()
        self.env_list_layout.setSpacing(10)
        lc_lay.addLayout(self.env_list_layout)
        lay.addWidget(list_card)

        # Paths Card
        path_card = QFrame()
        path_card.setObjectName("Card")
        pl = QVBoxLayout(path_card)
        pl.setContentsMargins(18, 14, 18, 14)
        pl.setSpacing(8)
        pt = QLabel("本机数据与虚拟环境路径")
        pt.setObjectName("CardTitle")
        pl.addWidget(pt)
        self.lbl_data_dir = QLabel(f"用户数据目录：{dc.DATA_DIR}")
        self.lbl_data_dir.setStyleSheet("font-family: monospace; font-size: 12px; color: #4B5563;")
        self.lbl_data_dir.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_venv_dir = QLabel(f"独立虚拟环境：{dc.get_venv_dir()}")
        self.lbl_venv_dir.setStyleSheet("font-family: monospace; font-size: 12px; color: #4B5563;")
        self.lbl_venv_dir.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pl.addWidget(self.lbl_data_dir)
        pl.addWidget(self.lbl_venv_dir)

        p_row = QHBoxLayout()
        p_row.addStretch(1)
        self.btn_open_data_dir = QPushButton("打开数据目录")
        self.btn_open_data_dir.setObjectName("SecondaryBtn")
        self.btn_open_data_dir.clicked.connect(self.open_data_dir)
        p_row.addWidget(self.btn_open_data_dir)
        pl.addLayout(p_row)
        lay.addWidget(path_card)

        lay.addStretch(1)
        return page

    # ---- TAB 2: AI SETTINGS ----
    def _build_ai_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PageBody")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(16)

        t = QLabel("AI 模型与语音转写配置")
        t.setObjectName("PageTitle")
        s = QLabel("与学习机网页共享同一份本机 SQLite 数据库；服务未启动前即可完成绑定与连通性测试。")
        s.setObjectName("PageSub")
        s.setWordWrap(True)
        lay.addWidget(t)
        lay.addWidget(s)

        # Vendor Presets Card
        preset_card = QFrame()
        preset_card.setObjectName("Card")
        pr_lay = QVBoxLayout(preset_card)
        pr_lay.setContentsMargins(18, 14, 18, 14)
        pr_lay.setSpacing(8)
        pt = QLabel("快捷厂商预设（一键填入接口地址与推荐模型）")
        pt.setObjectName("CardTitle")
        ps = QLabel("DeepSeek、通义千问、Gemini 兼容等纯对话模型预设仅更新 LLM 接口，不会覆盖您自定义的云端 ASR 地址。")
        ps.setObjectName("HintLabel")
        ps.setWordWrap(True)
        pr_lay.addWidget(pt)
        pr_lay.addWidget(ps)

        pgrid = QGridLayout()
        pgrid.setSpacing(8)
        self.preset_buttons: dict[str, QPushButton] = {}
        for idx, preset in enumerate(PROVIDER_PRESETS):
            btn = QPushButton(preset["label"])
            btn.setObjectName("PresetBtn")
            btn.setProperty("presetId", preset["id"])
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, p=preset: self.apply_vendor_preset(p))
            self.preset_buttons[preset["id"]] = btn
            pgrid.addWidget(btn, idx // 3, idx % 3)
        pr_lay.addLayout(pgrid)
        lay.addWidget(preset_card)

        # LLM Card
        llm_card = QFrame()
        llm_card.setObjectName("Card")
        ll_lay = QVBoxLayout(llm_card)
        ll_lay.setContentsMargins(18, 16, 18, 16)
        ll_lay.setSpacing(12)

        l_hdr = QHBoxLayout()
        lt = QLabel("大语言模型（LLM：字幕翻译 / 词条提取 / AI 精讲 / 复述评分）")
        lt.setObjectName("CardTitle")
        self.lbl_llm_key_badge = QLabel("未绑定密钥")
        self.lbl_llm_key_badge.setStyleSheet(
            "font-size: 11.5px; color: #6B7280; background: #F3F4F6; border-radius: 6px; padding: 3px 8px; font-family: monospace;"
        )
        l_hdr.addWidget(lt)
        l_hdr.addStretch(1)
        l_hdr.addWidget(self.lbl_llm_key_badge)
        ll_lay.addLayout(l_hdr)

        lgrid = QGridLayout()
        lgrid.setHorizontalSpacing(18)
        lgrid.setVerticalSpacing(10)
        lgrid.setColumnStretch(1, 1)

        self.edit_llm_base = QLineEdit()
        self.edit_llm_base.setObjectName("edit_llm_base")
        self.edit_llm_base.setPlaceholderText("https://api.openai.com/v1")
        self._add_form_row(lgrid, 0, "API Base URL", "兼容 OpenAI 格式，例如 https://api.deepseek.com/v1", self.edit_llm_base)

        self.edit_llm_model = QLineEdit()
        self.edit_llm_model.setObjectName("edit_llm_model")
        self.edit_llm_model.setPlaceholderText("gpt-4o-mini / deepseek-chat")
        self._add_form_row(lgrid, 1, "模型名称", "例如 deepseek-chat / gpt-4o-mini / qwen-plus", self.edit_llm_model)

        llm_key_wrap = QWidget()
        lk_lay = QHBoxLayout(llm_key_wrap)
        lk_lay.setContentsMargins(0, 0, 0, 0)
        lk_lay.setSpacing(8)
        self.edit_llm_key = QLineEdit()
        self.edit_llm_key.setObjectName("edit_llm_key")
        self.edit_llm_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_llm_key.setPlaceholderText("sk-...")
        self.edit_llm_key.textChanged.connect(self._on_llm_key_edited)
        self.btn_clear_llm_key = QPushButton("清除密钥")
        self.btn_clear_llm_key.setObjectName("SecondaryBtn")
        self.btn_clear_llm_key.clicked.connect(self._mark_clear_llm_key)
        lk_lay.addWidget(self.edit_llm_key, 1)
        lk_lay.addWidget(self.btn_clear_llm_key)
        self._add_form_row(lgrid, 2, "API Key", "仅保存在本机数据库；已绑定时留空即保持原密钥不变", llm_key_wrap)

        ll_lay.addLayout(lgrid)

        test_row = QHBoxLayout()
        self.btn_test_llm = QPushButton("测试大模型连通性")
        self.btn_test_llm.setObjectName("SecondaryBtn")
        self.btn_test_llm.clicked.connect(self.test_llm_async)
        self.lbl_llm_test_result = QLabel("")
        self.lbl_llm_test_result.setWordWrap(True)
        test_row.addWidget(self.btn_test_llm)
        test_row.addWidget(self.lbl_llm_test_result, 1)
        ll_lay.addLayout(test_row)
        lay.addWidget(llm_card)

        # ASR Card
        asr_card = QFrame()
        asr_card.setObjectName("Card")
        ar_lay = QVBoxLayout(asr_card)
        ar_lay.setContentsMargins(18, 16, 18, 16)
        ar_lay.setSpacing(12)

        a_hdr = QHBoxLayout()
        at = QLabel("语音转写与跟读评测引擎（ASR）")
        at.setObjectName("CardTitle")
        self.lbl_asr_key_badge = QLabel("离线模式")
        self.lbl_asr_key_badge.setStyleSheet(
            "font-size: 11.5px; color: #6B7280; background: #F3F4F6; border-radius: 6px; padding: 3px 8px; font-family: monospace;"
        )
        a_hdr.addWidget(at)
        a_hdr.addStretch(1)
        a_hdr.addWidget(self.lbl_asr_key_badge)
        ar_lay.addLayout(a_hdr)

        agrid = QGridLayout()
        agrid.setHorizontalSpacing(18)
        agrid.setVerticalSpacing(10)
        agrid.setColumnStretch(1, 1)

        self.combo_asr_mode = QComboBox()
        self.combo_asr_mode.setObjectName("combo_asr_mode")
        for code, label in ASR_MODE_OPTIONS:
            self.combo_asr_mode.addItem(label, code)
        self._add_form_row(agrid, 0, "转写策略", "推荐「智能自动」，云端异常自动回退本地离线 Whisper", self.combo_asr_mode)

        self.combo_whisper_model = QComboBox()
        self.combo_whisper_model.setObjectName("combo_whisper_model")
        for m in WHISPER_MODELS:
            self.combo_whisper_model.addItem(m, m)
        self.combo_whisper_model.setFixedWidth(180)
        self._add_form_row(agrid, 1, "本地 Whisper 模型", "tiny.en 速度最快，base.en / small.en 更精准", self.combo_whisper_model)

        self.edit_asr_base = QLineEdit()
        self.edit_asr_base.setObjectName("edit_asr_base")
        self.edit_asr_base.setPlaceholderText("https://api.openai.com/v1")
        self._add_form_row(agrid, 2, "云端 ASR Base URL", "可选；支持 OpenAI Whisper / Groq / 硅基流动", self.edit_asr_base)

        self.edit_asr_model = QLineEdit()
        self.edit_asr_model.setObjectName("edit_asr_model")
        self.edit_asr_model.setPlaceholderText("whisper-1")
        self._add_form_row(agrid, 3, "云端 ASR 模型", "例如 whisper-1 / whisper-large-v3-turbo", self.edit_asr_model)

        asr_key_wrap = QWidget()
        ak_lay = QHBoxLayout(asr_key_wrap)
        ak_lay.setContentsMargins(0, 0, 0, 0)
        ak_lay.setSpacing(8)
        self.edit_asr_key = QLineEdit()
        self.edit_asr_key.setObjectName("edit_asr_key")
        self.edit_asr_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_asr_key.setPlaceholderText("可选（留空默认离线识别）")
        self.edit_asr_key.textChanged.connect(self._on_asr_key_edited)
        self.btn_clear_asr_key = QPushButton("清除密钥")
        self.btn_clear_asr_key.setObjectName("SecondaryBtn")
        self.btn_clear_asr_key.clicked.connect(self._mark_clear_asr_key)
        ak_lay.addWidget(self.edit_asr_key, 1)
        ak_lay.addWidget(self.btn_clear_asr_key)
        self._add_form_row(agrid, 4, "云端 ASR API Key", "可选；不填也可使用内置本地离线 Whisper", asr_key_wrap)

        self.chk_online_dict = TactileToggle("离线词库未收录时自动联网补全音标与释义")
        self.chk_online_dict.setObjectName("chk_online_dict")
        self._add_form_row(agrid, 5, "在线词典补全", "推荐开启，扩充长尾生词词典覆盖率", self.chk_online_dict)

        ar_lay.addLayout(agrid)
        lay.addWidget(asr_card)

        # Save Footer
        foot = QHBoxLayout()
        note = QLabel("所有密钥仅保存在本机用户目录下，不会上传至第三方服务器。")
        note.setObjectName("HintLabel")
        foot.addWidget(note)
        foot.addStretch(1)
        self.btn_reset_ai = QPushButton("重置修改")
        self.btn_reset_ai.setObjectName("SecondaryBtn")
        self.btn_reset_ai.clicked.connect(self.load_ai_settings_into_form)
        self.btn_save_ai = QPushButton("保存 AI 与语音配置")
        self.btn_save_ai.setObjectName("PrimaryBtn")
        self.btn_save_ai.clicked.connect(self.save_ai_settings_from_form)
        foot.addWidget(self.btn_reset_ai)
        foot.addWidget(self.btn_save_ai)
        lay.addLayout(foot)

        lay.addStretch(1)
        return page

    # ---- TAB 3: LOGS ----
    def _build_logs_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PageBody")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 22, 24, 16)
        lay.setSpacing(12)

        t = QLabel("实时运行日志")
        t.setObjectName("PageTitle")
        s = QLabel("实时展示学习机网站服务与依赖安装器的完整输出。")
        s.setObjectName("PageSub")
        lay.addWidget(t)
        lay.addWidget(s)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.edit_log_filter = QLineEdit()
        self.edit_log_filter.setObjectName("edit_log_filter")
        self.edit_log_filter.setPlaceholderText("过滤日志关键词...")
        self.edit_log_filter.setFixedWidth(240)
        self.edit_log_filter.textChanged.connect(lambda _: self._render_logs(force=True))

        self.chk_log_autoscroll = TactileToggle("自动滚底")
        self.chk_log_autoscroll.setChecked(True)

        self.btn_log_copy = QPushButton("复制全部日志")
        self.btn_log_copy.setObjectName("SecondaryBtn")
        self.btn_log_copy.clicked.connect(self._copy_logs)

        self.btn_log_clear = QPushButton("清空视图")
        self.btn_log_clear.setObjectName("SecondaryBtn")
        self.btn_log_clear.clicked.connect(self._clear_logs)

        bar.addWidget(self.edit_log_filter)
        bar.addWidget(self.chk_log_autoscroll)
        bar.addStretch(1)
        bar.addWidget(self.btn_log_copy)
        bar.addWidget(self.btn_log_clear)
        lay.addLayout(bar)

        self.txt_logs = QPlainTextEdit()
        self.txt_logs.setObjectName("LogConsole")
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        lay.addWidget(self.txt_logs, 1)
        return page

    # ------------------------------------------------------------------ Signals & Actions
    def _connect_signals(self) -> None:
        self.bridge.envChecked.connect(self._apply_env_report)
        self.bridge.serviceActionDone.connect(self._on_service_action_done)
        self.bridge.llmTestDone.connect(self._on_llm_test_done)
        self.bridge.raiseRequested.connect(self.bring_to_front)
        self.bridge.quitRequested.connect(self.quit_application)
        self.bridge.statusPolled.connect(self._apply_status_snapshot)

    def switch_tab(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        for i, btn in enumerate(self.nav_buttons):
            btn.setProperty("active", i == idx)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if idx == 1:
            self.refresh_environment_async()
        elif idx == 2:
            self.load_ai_settings_into_form()
        elif idx == 3:
            self._render_logs(force=True)

    def show_toast(self, message: str, is_error: bool = False) -> None:
        self.lbl_toast.setObjectName("ToastErr" if is_error else "ToastOk")
        self.lbl_toast.style().unpolish(self.lbl_toast)
        self.lbl_toast.style().polish(self.lbl_toast)
        self.lbl_toast.setText(message)
        self.lbl_toast.setVisible(True)
        self._toast_timer.start(3600)

    def _hide_toast(self) -> None:
        self.lbl_toast.setVisible(False)

    def bring_to_front(self) -> None:
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def open_data_dir(self) -> None:
        dc.DATA_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(dc.DATA_DIR)))

    def open_web_app(self) -> None:
        st = self._last_status or self.manager.status()
        url = st.get("local_url", f"http://127.0.0.1:{dc.load_desktop_config()['port']}")
        if not self.manager.is_running():
            self.show_toast("请先点击「启动学习机服务」，启动完成后再打开网页。", is_error=True)
            return
        build_id = dc.get_frontend_build_id() or "1.3.3"
        open_url = f"{url.rstrip('/')}/?v={build_id}"
        webbrowser.open(open_url)
        self.show_toast(f"已在默认浏览器打开：{url}")

    def _copy_local_url(self) -> None:
        url = (self._last_status or self.manager.status()).get("local_url", "http://127.0.0.1:8000")
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(url)
        self.show_toast(f"已复制网址：{url}")

    def _current_lan_preview_url(self) -> str:
        st = self._last_status or {}
        ip = str(st.get("lan_ip") or self._detected_lan_ip or "").strip()
        if not ip:
            return ""
        lan_checked = hasattr(self, "chk_lan") and self.chk_lan.isChecked()
        lan_active = bool(st.get("lan_active"))
        if not (lan_checked or lan_active):
            return ""
        port = self.spin_port.value() if (lan_checked and hasattr(self, "spin_port")) else int(st.get("port", 8000))
        return f"http://{ip}:{port}"

    def _copy_lan_url(self) -> None:
        url = self._current_lan_preview_url() or (self._last_status or self.manager.status()).get("lan_url", "")
        if url:
            cb = QApplication.clipboard()
            if cb is not None:
                cb.setText(url)
            self.show_toast(f"已复制局域网地址：{url}")
        else:
            self.show_toast("暂未检测到本机局域网 IP，请先连接 Wi-Fi 或网线。", is_error=True)

    def _on_lan_toggle_changed(self, checked: bool) -> None:
        if checked:
            detected = dc.detect_lan_ip()
            if detected:
                self._detected_lan_ip = detected
        self._update_lan_address_ui()

    def _refresh_lan_ip(self) -> None:
        detected = dc.detect_lan_ip()
        self._detected_lan_ip = detected
        self._update_lan_address_ui()
        if detected:
            self.show_toast(f"已检测到本机局域网 IP：{detected}")
        else:
            self.show_toast("暂未检测到本机局域网 IP，请确认电脑已连接 Wi-Fi 或有线网络。", is_error=True)

    def _apply_lan_and_restart(self) -> None:
        if self._busy_service:
            return
        dc.save_desktop_config(
            {
                "port": self.spin_port.value(),
                "lan_access": self.chk_lan.isChecked(),
                "access_password": self.edit_password.text().strip(),
                "hf_mirror": self.chk_hf_mirror.isChecked(),
                "auto_start_service": self.chk_auto_start.isChecked(),
            }
        )
        self.manager.append_log(
            f"保存并应用局域网配置：port={self.spin_port.value()}, lan={self.chk_lan.isChecked()}"
        )
        if self.manager.is_running():
            self.restart_service_async()
        else:
            self.start_service_async()

    def _update_lan_address_ui(self) -> None:
        if not hasattr(self, "chk_lan") or not hasattr(self, "lan_inline_box"):
            return
        st = self._last_status or {}
        running = bool(st.get("running"))
        lan_active = bool(st.get("lan_active"))
        active_port = int(st.get("port", 8000))
        lan_checked = self.chk_lan.isChecked()
        draft_port = self.spin_port.value()
        ip = str(st.get("lan_ip") or self._detected_lan_ip or "").strip()
        live_active = running and lan_active and active_port == draft_port
        needs_restart = running and lan_checked and not live_active

        # 1. Inline LAN Address Card directly beneath the toggle
        if lan_checked:
            self.lan_inline_box.setVisible(True)
            if ip:
                url = f"http://{ip}:{draft_port}"
                self.lbl_lan_inline_url.setText(url)
                if live_active:
                    self.lbl_lan_inline_hint.setText("已生效：同 Wi-Fi 下的平板 / 手机浏览器直接输入此地址即可访问")
                elif running:
                    self.lbl_lan_inline_hint.setText("请点右侧「立即应用并重启」后，同 Wi-Fi 设备即可通过此地址访问")
                else:
                    self.lbl_lan_inline_hint.setText("保存或启动服务后，同 Wi-Fi 平板 / 手机输入此地址访问")
                self.btn_lan_apply_restart.setVisible(needs_restart)
                self.btn_lan_apply_restart.setEnabled(not self._busy_service and not bool(st.get("installing")))
                self.btn_lan_inline_copy.setVisible(True)
                self.btn_lan_inline_refresh.setVisible(False)
            else:
                self.lbl_lan_inline_url.setText("暂未检测到本机局域网 IP")
                self.lbl_lan_inline_hint.setText("请先将电脑连接至 Wi-Fi 或路由器网线，再点击右侧刷新检测")
                self.btn_lan_apply_restart.setVisible(False)
                self.btn_lan_inline_copy.setVisible(False)
                self.btn_lan_inline_refresh.setVisible(True)
        else:
            self.lan_inline_box.setVisible(False)

        # 2. Top Hero Card LAN Banner
        if lan_checked or lan_active:
            self.lan_row_widget.setVisible(True)
            if ip:
                hero_port = draft_port if lan_checked else active_port
                hero_url = f"http://{ip}:{hero_port}"
                self.lbl_lan_url.setText(hero_url)
                self.btn_copy_lan.setVisible(True)
                if running and lan_active and active_port == hero_port:
                    self.lbl_lan_hero_badge.setText("已生效")
                    self.lbl_lan_hero_badge.setStyleSheet(
                        "font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; "
                        "background: #DCFCE7; color: #166534;"
                    )
                elif running:
                    self.lbl_lan_hero_badge.setText("待重启生效")
                    self.lbl_lan_hero_badge.setStyleSheet(
                        "font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; "
                        "background: #FEF3C7; color: #92400E;"
                    )
                else:
                    self.lbl_lan_hero_badge.setText("启动后生效")
                    self.lbl_lan_hero_badge.setStyleSheet(
                        "font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; "
                        "background: #E0F2FE; color: #075985;"
                    )
                self.lbl_lan_hero_badge.setVisible(True)
                self.btn_hero_apply_lan.setVisible(needs_restart)
                self.btn_hero_apply_lan.setEnabled(not self._busy_service and not bool(st.get("installing")))
            else:
                self.lbl_lan_url.setText("暂未检测到本机 Wi-Fi / 局域网 IP")
                self.lbl_lan_hero_badge.setVisible(False)
                self.btn_hero_apply_lan.setVisible(False)
                self.btn_copy_lan.setVisible(False)
        else:
            self.lan_row_widget.setVisible(False)

    # ---- Desktop Config ----
    def load_desktop_config_into_form(self) -> None:
        cfg = dc.load_desktop_config()
        self.spin_port.setValue(int(cfg["port"]))
        self.chk_lan.setChecked(bool(cfg["lan_access"]))
        self.edit_password.setText(str(cfg["access_password"] or ""))
        self.chk_hf_mirror.setChecked(bool(cfg["hf_mirror"]))
        self.chk_auto_start.setChecked(bool(cfg["auto_start_service"]))
        self._update_lan_address_ui()

    def save_desktop_config_from_form(self) -> None:
        old_cfg = dc.load_desktop_config()
        saved = dc.save_desktop_config(
            {
                "port": self.spin_port.value(),
                "lan_access": self.chk_lan.isChecked(),
                "access_password": self.edit_password.text().strip(),
                "hf_mirror": self.chk_hf_mirror.isChecked(),
                "auto_start_service": self.chk_auto_start.isChecked(),
            }
        )
        self.spin_port.setValue(int(saved["port"]))
        self.manager.append_log(
            f"保存桌面配置：port={saved['port']}, lan={saved['lan_access']}, "
            f"hf_mirror={saved['hf_mirror']}, auto_start={saved['auto_start_service']}"
        )
        needs_restart = self.manager.is_running() and (
            saved["port"] != old_cfg["port"]
            or saved["lan_access"] != old_cfg["lan_access"]
            or saved["access_password"] != old_cfg["access_password"]
            or saved["hf_mirror"] != old_cfg["hf_mirror"]
        )
        self._apply_status_snapshot(self.manager.status())
        if needs_restart:
            self.show_toast("发布配置已保存；请点击「重启服务」以应用新的端口或访问设置。")
        else:
            self.show_toast("发布配置已保存。")

    # ---- AI & ASR Settings ----
    def load_ai_settings_into_form(self) -> None:
        pub = dc.read_public_engine_settings()
        raw = dc.read_raw_engine_settings()
        has_llm = bool(raw.get("llm_api_key", "").strip())
        has_asr = bool(raw.get("asr_api_key", "").strip())

        self._clear_llm_key = False
        self._clear_asr_key = False

        self.edit_llm_base.setText(pub.get("llm_base_url", "https://api.openai.com/v1"))
        self.edit_llm_model.setText(pub.get("llm_model", "gpt-4o-mini"))
        self.edit_llm_key.blockSignals(True)
        self.edit_llm_key.setText("")
        self.edit_llm_key.blockSignals(False)
        self.edit_llm_key.setPlaceholderText(
            f"已保存（{pub['llm_api_key']}），留空保持不变" if has_llm else "sk-..."
        )
        self.btn_clear_llm_key.setVisible(has_llm)
        self._update_key_badge(self.lbl_llm_key_badge, has_llm, pub.get("llm_api_key", ""), "未绑定密钥")

        idx_mode = self.combo_asr_mode.findData(pub.get("asr_mode", "auto"))
        if idx_mode >= 0:
            self.combo_asr_mode.setCurrentIndex(idx_mode)

        idx_w = self.combo_whisper_model.findData(pub.get("local_whisper_model", "tiny.en"))
        if idx_w >= 0:
            self.combo_whisper_model.setCurrentIndex(idx_w)

        self.edit_asr_base.setText(pub.get("asr_base_url", "https://api.openai.com/v1"))
        self.edit_asr_model.setText(pub.get("asr_model", "whisper-1"))
        self.edit_asr_key.blockSignals(True)
        self.edit_asr_key.setText("")
        self.edit_asr_key.blockSignals(False)
        self.edit_asr_key.setPlaceholderText(
            f"已保存（{pub['asr_api_key']}），留空保持不变" if has_asr else "可选（留空默认离线识别）"
        )
        self.btn_clear_asr_key.setVisible(has_asr)
        self._update_key_badge(self.lbl_asr_key_badge, has_asr, pub.get("asr_api_key", ""), "离线模式")

        self.chk_online_dict.setChecked(
            str(pub.get("enable_online_dict_fallback", "true")).lower() != "false"
        )
        self.stat_llm[1].setText("已绑定" if has_llm else "离线模式")

    def _update_key_badge(self, lbl: QLabel, bound: bool, masked: str, empty_text: str) -> None:
        if bound:
            lbl.setText(f"已绑定 {masked}")
            lbl.setStyleSheet(
                "font-size: 11.5px; color: #047857; background: #D1FAE5; border-radius: 6px; padding: 3px 8px; font-family: monospace;"
            )
        else:
            lbl.setText(empty_text)
            lbl.setStyleSheet(
                "font-size: 11.5px; color: #6B7280; background: #F3F4F6; border-radius: 6px; padding: 3px 8px; font-family: monospace;"
            )

    def _on_llm_key_edited(self, text: str) -> None:
        if text.strip():
            self._clear_llm_key = False

    def _on_asr_key_edited(self, text: str) -> None:
        if text.strip():
            self._clear_asr_key = False

    def _mark_clear_llm_key(self) -> None:
        self._clear_llm_key = True
        self.edit_llm_key.clear()
        self.edit_llm_key.setPlaceholderText("将在点击「保存」后清除已保存密钥")
        self._update_key_badge(self.lbl_llm_key_badge, False, "", "待清除（点击保存生效）")

    def _mark_clear_asr_key(self) -> None:
        self._clear_asr_key = True
        self.edit_asr_key.clear()
        self.edit_asr_key.setPlaceholderText("将在点击「保存」后清除已保存密钥")
        self._update_key_badge(self.lbl_asr_key_badge, False, "", "待清除（点击保存生效）")

    def apply_vendor_preset(self, preset: dict[str, Any]) -> None:
        self.edit_llm_base.setText(preset["llm_base_url"])
        self.edit_llm_model.setText(preset["llm_model"])
        if preset.get("asr_base_url"):
            self.edit_asr_base.setText(preset["asr_base_url"])
        if preset.get("asr_model"):
            self.edit_asr_model.setText(preset["asr_model"])
        self.show_toast(f"已填入「{preset['label']}」预设接口与模型，填写密钥后点击保存即可。")

    def save_ai_settings_from_form(self) -> None:
        updates: dict[str, Any] = {
            "llm_base_url": self.edit_llm_base.text().strip() or "https://api.openai.com/v1",
            "llm_model": self.edit_llm_model.text().strip() or "gpt-4o-mini",
            "asr_mode": self.combo_asr_mode.currentData() or "auto",
            "local_whisper_model": self.combo_whisper_model.currentData() or "tiny.en",
            "asr_base_url": self.edit_asr_base.text().strip() or "https://api.openai.com/v1",
            "asr_model": self.edit_asr_model.text().strip() or "whisper-1",
            "enable_online_dict_fallback": "true" if self.chk_online_dict.isChecked() else "false",
        }
        llm_in = self.edit_llm_key.text().strip()
        if llm_in:
            updates["llm_api_key"] = llm_in
        elif self._clear_llm_key:
            updates["llm_api_key"] = ""

        asr_in = self.edit_asr_key.text().strip()
        if asr_in:
            updates["asr_api_key"] = asr_in
        elif self._clear_asr_key:
            updates["asr_api_key"] = ""

        dc.write_engine_settings(updates)
        self.load_ai_settings_into_form()
        self.manager.append_log(
            f"已保存共享 AI 模型配置：llm_model={updates['llm_model']}, asr_mode={updates['asr_mode']}"
        )
        self.show_toast("AI 与语音转写配置已保存（与学习机网页实时共享）。")

    def test_llm_async(self) -> None:
        if self._busy_llm:
            return
        self._busy_llm = True
        self.btn_test_llm.setEnabled(False)
        self.btn_test_llm.setText("正在测试连接...")
        self.lbl_llm_test_result.setText("")

        base = self.edit_llm_base.text().strip()
        model = self.edit_llm_model.text().strip()
        key_input = self.edit_llm_key.text().strip()
        if not key_input:
            if self._clear_llm_key:
                key_input = ""
            else:
                # Reuse stored secret via masked sentinel
                raw_saved = dc.read_raw_engine_settings().get("llm_api_key", "").strip()
                key_input = dc.mask_secret(raw_saved) if raw_saved else ""

        def _work() -> None:
            try:
                res = dc.test_llm_stdlib(base, key_input, model)
            except Exception as exc:
                res = {"ok": False, "message": f"测试连接异常：{exc}"}
            self._safe_emit("llmTestDone", res)

        threading.Thread(target=_work, daemon=True).start()

    def _safe_emit(self, signal_name: str, *args: Any) -> None:
        try:
            sig = getattr(self.bridge, signal_name, None)
            if sig is not None:
                sig.emit(*args)
        except RuntimeError:
            pass

    def _on_llm_test_done(self, res: dict[str, Any]) -> None:
        self._busy_llm = False
        self.btn_test_llm.setEnabled(True)
        self.btn_test_llm.setText("测试大模型连通性")
        ok = bool(res.get("ok"))
        msg = str(res.get("message") or "")
        self.lbl_llm_test_result.setText(msg)
        self.lbl_llm_test_result.setStyleSheet(
            f"font-size: 12.5px; font-weight: 600; color: {'#047857' if ok else '#B91C1C'};"
        )
        self.manager.append_log(f"大模型连通测试：{'成功' if ok else '失败'} — {msg}")
        self.show_toast(msg, is_error=not ok)

    # ---- Environment Check & Install ----
    def refresh_environment_async(self) -> None:
        if self._busy_env:
            return
        self._busy_env = True
        self.btn_env_refresh.setEnabled(False)
        self.btn_env_refresh.setText("检测中...")

        def _work() -> None:
            try:
                info = dc.inspect_environment()
            except Exception as exc:
                info = {
                    "core_ready": False,
                    "all_ready": False,
                    "items": [
                        {
                            "key": "error",
                            "label": "环境扫描异常",
                            "ok": False,
                            "required": True,
                            "detail": str(exc),
                        }
                    ],
                }
            self._safe_emit("envChecked", info)

        threading.Thread(target=_work, daemon=True).start()

    def _apply_env_report(self, info: dict[str, Any]) -> None:
        self._busy_env = False
        self._last_env_info = info
        self.btn_env_refresh.setEnabled(True)
        self.btn_env_refresh.setText("重新检测")

        core_ready = bool(info.get("core_ready"))
        all_ready = bool(info.get("all_ready"))
        whisper_cached = bool(info.get("whisper_cached"))

        self.banner_missing_deps.setVisible(not core_ready)
        self.stat_env[1].setText("全部就绪" if all_ready else ("核心就绪" if core_ready else "缺少依赖"))
        self.nav_buttons[1].setText("环境与依赖" if core_ready else "环境与依赖（缺）")

        self.lbl_data_dir.setText(f"用户数据目录：{dc.DATA_DIR}")
        self.lbl_venv_dir.setText(f"独立虚拟环境：{info.get('venv_dir', dc.get_venv_dir())}")

        if all_ready:
            self.lbl_env_banner_title.setText("所有运行环境与离线语音模型均已就绪")
            self.lbl_env_banner_sub.setText("您可以随时前往「服务总览」一键启动本地Lingo学习机。")
            self.btn_install_deps.setText("修复 / 更新依赖")
        elif core_ready:
            self.lbl_env_banner_title.setText("核心运行环境已就绪，离线语音模型待预热")
            self.lbl_env_banner_sub.setText("可立即启动学习机；也建议点击「一键预热离线语音模型」让首次跟读打分秒开。")
            self.btn_install_deps.setText("修复 / 更新依赖")
        else:
            self.lbl_env_banner_title.setText("检测到缺失核心运行依赖")
            self.lbl_env_banner_sub.setText("点击「一键安装 / 修复全部依赖」将自动准备隔离虚拟环境、FFmpeg 与本地 Whisper。")
            self.btn_install_deps.setText("一键安装 / 修复全部依赖")

        self.btn_install_whisper.setText(
            f"重新校验语音模型 ({info.get('whisper_model', 'tiny.en')})"
            if whisper_cached
            else f"一键预热离线语音模型 ({info.get('whisper_model', 'tiny.en')})"
        )

        # Rebuild checklist rows cleanly
        while self.env_list_layout.count():
            child = self.env_list_layout.takeAt(0)
            if child and child.widget():
                child.widget().deleteLater()

        items = info.get("items") or []
        for idx, it in enumerate(items):
            row = QFrame()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(2, 6, 2, 6)
            rl.setSpacing(10)

            ok = bool(it.get("ok"))
            req = bool(it.get("required"))
            dot = QLabel("●")
            dot.setStyleSheet(
                f"font-size: 14px; color: {'#10B981' if ok else ('#EF4444' if req else '#F59E0B')};"
            )
            rl.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)

            info_col = QVBoxLayout()
            info_col.setSpacing(2)
            head = QHBoxLayout()
            lbl_name = QLabel(str(it.get("label", "")))
            lbl_name.setStyleSheet("font-weight: 700; font-size: 13px;")
            tag = QLabel("必需" if req else "推荐")
            tag.setStyleSheet(
                "font-size: 10.5px; font-weight: 700; padding: 1px 6px; border-radius: 4px; "
                + ("background: #DBEAFE; color: #1D4ED8;" if req else "background: #F3F4F6; color: #4B5563;")
            )
            head.addWidget(lbl_name)
            head.addWidget(tag)
            head.addStretch(1)
            info_col.addLayout(head)

            lbl_det = QLabel(str(it.get("detail", "")))
            lbl_det.setObjectName("HintLabel")
            lbl_det.setWordWrap(True)
            info_col.addWidget(lbl_det)
            rl.addLayout(info_col, 1)

            badge = QLabel("已就绪" if ok else ("缺失" if req else "未预热"))
            badge.setStyleSheet(
                "font-size: 11.5px; font-weight: 700; padding: 3px 9px; border-radius: 6px; "
                + (
                    "background: #D1FAE5; color: #047857;"
                    if ok
                    else ("background: #FEE2E2; color: #B91C1C;" if req else "background: #FEF3C7; color: #B45309;")
                )
            )
            rl.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
            self.env_list_layout.addWidget(row)

            if idx < len(items) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet("color: #ECEDF2;")
                self.env_list_layout.addWidget(sep)

        # Deterministic auto-start once initial environment check finishes
        if self._auto_start_pending:
            self._auto_start_pending = False
            self._maybe_auto_start()

    def trigger_install_deps(self) -> None:
        code, payload = self.manager.trigger_install_deps()
        if code >= 400:
            self.show_toast(str(payload.get("detail") or "无法启动安装任务"), is_error=True)
            return
        self.show_toast("已开始安装核心运行依赖，可在「运行日志」查看实时进度。")
        self._apply_status_snapshot(self.manager.status())

    def trigger_install_whisper(self) -> None:
        code, payload = self.manager.trigger_install_whisper()
        if code >= 400:
            self.show_toast(str(payload.get("detail") or "无法预热语音模型"), is_error=True)
            return
        self.show_toast("已开始预热本地离线语音模型，可在「运行日志」查看实时进度。")
        self._apply_status_snapshot(self.manager.status())

    # ---- Service Lifecycle ----
    def _maybe_auto_start(self) -> None:
        if self._last_env_info.get("core_ready") and not self.manager.is_running() and not self._busy_service:
            self.manager.append_log("已开启「自动启动服务」，正在拉起学习机...")
            self.start_service_async()

    def start_service_async(self) -> None:
        if self._busy_service:
            return
        # Ensure any unsaved LAN sharing / port changes in the form apply cleanly when clicking Start
        if hasattr(self, "chk_lan") and hasattr(self, "spin_port"):
            saved_cfg = dc.load_desktop_config()
            form_cfg = {
                "port": self.spin_port.value(),
                "lan_access": self.chk_lan.isChecked(),
                "access_password": self.edit_password.text().strip(),
                "hf_mirror": self.chk_hf_mirror.isChecked(),
                "auto_start_service": self.chk_auto_start.isChecked(),
            }
            if any(saved_cfg.get(k) != v for k, v in form_cfg.items()):
                dc.save_desktop_config(form_cfg)
        self._busy_service = True
        self._set_service_buttons_busy(True, action="start")

        def _work() -> None:
            try:
                code, payload = self.manager.start()
                ok = 200 <= code < 300
                msg = "Lingo学习机服务已就绪，点击「在浏览器打开学习机」即可使用。" if ok else str(
                    payload.get("detail") or "启动学习机服务失败"
                )
                st = payload.get("service") if ok else self.manager.status()
            except Exception as exc:
                ok = False
                msg = f"启动服务异常：{exc}"
                st = self.manager.status()
            self._safe_emit("serviceActionDone", "start", ok, msg, st)

        threading.Thread(target=_work, daemon=True).start()

    def stop_service_async(self) -> None:
        if self._busy_service:
            return
        self._busy_service = True
        self._set_service_buttons_busy(True, action="stop")

        def _work() -> None:
            try:
                st = self.manager.stop()
                ok, msg = True, "学习机服务已安全停止。"
            except Exception as exc:
                st = self.manager.status()
                ok, msg = False, f"停止服务异常：{exc}"
            self._safe_emit("serviceActionDone", "stop", ok, msg, st)

        threading.Thread(target=_work, daemon=True).start()

    def restart_service_async(self) -> None:
        if self._busy_service:
            return
        self._busy_service = True
        self._set_service_buttons_busy(True, action="restart")

        def _work() -> None:
            try:
                self.manager.stop()
                code, payload = self.manager.start()
                ok = 200 <= code < 300
                msg = "学习机服务已重启就绪。" if ok else str(payload.get("detail") or "重启学习机服务失败")
                st = payload.get("service") if ok else self.manager.status()
            except Exception as exc:
                ok = False
                msg = f"重启服务异常：{exc}"
                st = self.manager.status()
            self._safe_emit("serviceActionDone", "restart", ok, msg, st)

        threading.Thread(target=_work, daemon=True).start()

    def _set_service_buttons_busy(self, busy: bool, action: str = "") -> None:
        self.btn_start_service.setEnabled(not busy)
        self.btn_restart_service.setEnabled(not busy)
        self.btn_stop_service.setEnabled(not busy)
        if busy:
            if action == "start":
                self.btn_start_service.setText("正在启动...")
            elif action == "restart":
                self.btn_restart_service.setText("正在重启...")
            elif action == "stop":
                self.btn_stop_service.setText("正在停止...")

    def _on_service_action_done(self, _action: str, ok: bool, msg: str, status: dict[str, Any]) -> None:
        self._busy_service = False
        self.btn_start_service.setText("启动学习机服务")
        self.btn_restart_service.setText("重启服务")
        self.btn_stop_service.setText("停止服务")
        self._apply_status_snapshot(status)
        self.show_toast(msg, is_error=not ok)

    # ---- Periodic Status Polling & Log Streaming ----
    def _poll_status_async(self) -> None:
        if self._polling:
            return
        self._polling = True

        def _work() -> None:
            try:
                st = self.manager.status()
                self.bridge.statusPolled.emit(st)
            except Exception:
                pass
            finally:
                self._polling = False

        threading.Thread(target=_work, daemon=True).start()

    def _apply_status_snapshot(self, st: dict[str, Any]) -> None:
        was_installing = bool(self._last_status.get("installing"))
        self._last_status = st

        running = bool(st.get("running"))
        healthy = bool(st.get("healthy"))
        installing = bool(st.get("installing"))
        port = st.get("port", 8000)
        local_url = st.get("local_url", f"http://127.0.0.1:{port}")
        lan_url = st.get("lan_url", "")
        pid = st.get("pid")
        uptime_sec = int(st.get("uptime_sec") or 0)
        env_summary = st.get("env_summary") or {}

        # Trigger automatic env re-check right when an install finishes
        if was_installing and not installing:
            last_res = st.get("last_install_result") or {}
            if last_res.get("message"):
                self.show_toast(str(last_res["message"]), is_error=not bool(last_res.get("ok")))
            self.refresh_environment_async()

        # Header status pill + 3D status dial + hero highlight card
        if installing:
            dot_c, short_s, hero_s = "#F59E0B", "安装依赖中", "正在安装运行依赖..."
        elif running and healthy:
            dot_c, short_s, hero_s = "#10B981", "运行中", "Lingo 学习机运行中"
        elif running:
            dot_c, short_s, hero_s = "#F59E0B", "启动中", "Lingo 学习机启动中..."
        else:
            dot_c, short_s, hero_s = "#9CA3AF", "已停止", "学习机服务已停止"

        if hasattr(self, "dial_widget"):
            self.dial_widget.set_state(int(port), running, healthy)
        if hasattr(self, "hero_card"):
            desired_name = "HeroCardActive" if (running and healthy) else "Card"
            if self.hero_card.objectName() != desired_name:
                self.hero_card.setObjectName(desired_name)
                st_style = self.hero_card.style()
                if st_style is not None:
                    st_style.unpolish(self.hero_card)
                    st_style.polish(self.hero_card)

        self.lbl_sidebar_dot.setStyleSheet(f"color: {dot_c}; font-size: 11px; background: transparent;")
        self.lbl_sidebar_status.setText(short_s)
        self.lbl_sidebar_port.setText(f":{port}")

        self.lbl_hero_dot.setStyleSheet(f"font-size: 16px; color: {dot_c}; background: transparent;")
        self.lbl_status_title.setText(hero_s)
        if running and pid:
            self.lbl_pid.setText(f"PID {pid}")
            self.lbl_pid.setVisible(True)
        else:
            self.lbl_pid.setVisible(False)

        self.lbl_local_url.setText(f"本机地址：{local_url}")
        self.lbl_uptime.setText(f"运行时长：{_format_uptime(uptime_sec)}" if running else "")

        self.btn_start_service.setVisible(not running)
        self.btn_open_web.setVisible(running)
        self.btn_restart_service.setVisible(running)
        self.btn_stop_service.setVisible(running)

        if not self._busy_service:
            self.btn_start_service.setEnabled(not installing)
            self.btn_restart_service.setEnabled(not installing)
            self.btn_stop_service.setEnabled(not installing)
        self.btn_sidebar_open_web.setEnabled(running and not installing)

        if st.get("lan_ip"):
            self._detected_lan_ip = str(st["lan_ip"])
        self._update_lan_address_ui()

        # Stats
        self.stat_episodes[1].setText(f"{env_summary.get('episode_count', 0)} 篇")
        self.stat_vocab[1].setText(f"{env_summary.get('vocab_count', 0)} 词")

        # Installer progress controls
        self.progress_install.setVisible(installing)
        self.btn_install_deps.setEnabled(not installing)
        self.btn_install_whisper.setEnabled(not installing)

        # Tray menu sync
        if self.tray is not None:
            self.tray_act_status.setText(f"状态：{short_s} (:{port})")
            self.tray_act_toggle.setText("停止学习机服务" if running else "启动学习机服务")
            self.tray_act_toggle.setEnabled(not installing and not self._busy_service)

        # Logs counter & live render
        logs = st.get("logs") or []
        self.nav_buttons[3].setText(f"运行日志 ({len(logs)})" if logs else "运行日志")
        self._render_logs(force=False)

    def _render_logs(self, force: bool = False) -> None:
        st = self._last_status or {}
        logs = st.get("logs") or []
        log_seq = st.get("log_seq")
        sig = (log_seq, len(logs), logs[0] if logs else "", logs[-1] if logs else "")
        flt = self.edit_log_filter.text().strip().lower()
        if not force and sig == self._last_log_sig and flt == self._last_log_filter:
            return
        self._last_log_sig = sig
        self._last_log_filter = flt
        shown = [l for l in logs if flt in l.lower()] if flt else logs
        self.txt_logs.setPlainText("\n".join(shown))
        if self.chk_log_autoscroll.isChecked():
            sb = self.txt_logs.verticalScrollBar()
            if sb is not None:
                sb.setValue(sb.maximum())

    def _copy_logs(self) -> None:
        text = self.txt_logs.toPlainText()
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(text)
        self.show_toast("已复制当前日志内容到剪贴板。")

    def _clear_logs(self) -> None:
        self.manager._logs.clear()
        self.manager.append_log("已清空日志视图。")
        self._last_status = self.manager.status()
        self._render_logs(force=True)

    # ------------------------------------------------------------------ Window & App Lifecycle
    def closeEvent(self, event) -> None:  # type: ignore[override]
        if not self._quitting and self.tray is not None and self.tray.isVisible():
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Lingo仍在后台运行",
                "控制台窗口已最小化至顶部菜单栏图标，学习机服务保持运行；点击菜单栏图标可随时恢复或退出。",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            return
        self._quitting = True
        self._cleanup_before_exit()
        event.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def quit_application(self) -> None:
        self._quitting = True
        self._cleanup_before_exit()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _cleanup_before_exit(self) -> None:
        if self._poll_timer.isActive():
            self._poll_timer.stop()
        self._stop_ipc_server()
        if self.tray is not None:
            self.tray.hide()
        try:
            self.manager.stop()
        except Exception:
            pass


class MacDockReopenFilter(QObject):
    """Restores hidden main window when user clicks the Dock icon on macOS."""

    def __init__(self, window: LingoReelNativeWindow) -> None:
        super().__init__()
        self._window = window

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() == QEvent.Type.ApplicationActivate:
            if not self._window.isVisible():
                self._window.bring_to_front()
        return False


def main() -> int:
    # Single-instance check: wake running native console instead of opening duplicate window
    if try_wake_existing_instance():
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("Lingo")
    app.setApplicationDisplayName("Lingo — 桌面控制台")
    app.setOrganizationName("LingoReelStudio")
    app.setWindowIcon(_build_app_icon())
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(APP_STYLESHEET)

    window = LingoReelNativeWindow()
    reopen_filter = MacDockReopenFilter(window)
    app.installEventFilter(reopen_filter)

    # Ensure SIGTERM / SIGINT cleanly stops uvicorn & exits
    def _handle_sig(_signum: int, _frame: Any) -> None:
        QTimer.singleShot(0, window.quit_application)

    signal.signal(signal.SIGTERM, _handle_sig)
    signal.signal(signal.SIGINT, _handle_sig)
    # Periodic no-op timer allows Python signal handlers to fire promptly under Qt event loop
    sig_pump = QTimer()
    sig_pump.setInterval(250)
    sig_pump.timeout.connect(lambda: None)
    sig_pump.start()

    window.show()
    window.bring_to_front()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
