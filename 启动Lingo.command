#!/usr/bin/env bash
set -euo pipefail

# Lingo 一键启动脚本（macOS 原生桌面控制台）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  Lingo — macOS 原生桌面控制台"
echo "=========================================="

APP_SUPPORT="$HOME/Library/Application Support/LingoReelStudio"
VENV_DIR="${LINGOREEL_VENV_DIR:-$APP_SUPPORT/.venv}"
export LINGOREEL_DATA_DIR="${LINGOREEL_DATA_DIR:-$APP_SUPPORT/data}"
export LINGOREEL_VENV_DIR="$VENV_DIR"
export LINGOREEL_FRONTEND_DIST="$SCRIPT_DIR/frontend/dist"
export LINGOREEL_DESKTOP_APP="1"
export HF_HOME="${HF_HOME:-$APP_SUPPORT/whisper-cache}"
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

auto_close_terminal_if_applicable() {
  if [ "$(uname -s)" = "Darwin" ] && [ "${TERM_PROGRAM:-}" = "Apple_Terminal" ] && [ -t 1 ] && [ "${LINGOREEL_AUTO_CLOSE_TERMINAL:-1}" = "1" ]; then
    local my_tty
    my_tty="$(tty 2>/dev/null || true)"
    if [ -n "$my_tty" ] && [ "$my_tty" != "not a tty" ]; then
      (
        sleep 0.6
        /usr/bin/osascript - "$my_tty" <<'APPLESCRIPT' >/dev/null 2>&1 || true
on run argv
  set targetTTY to item 1 of argv
  tell application "Terminal"
    repeat with w in (every window)
      try
        repeat with t in (every tab of w)
          if (tty of t) is targetTTY then
            if (count of tabs of w) is 1 then
              close w saving no
            end if
            return
          end if
        end repeat
      end try
    end repeat
  end tell
end run
APPLESCRIPT
      ) >/dev/null 2>&1 </dev/null &
    fi
  fi
}

# 1. 若已安装 Xcode Command Line Tools，可优先直接构建并启动 100% SwiftUI 原生端
if [ -f "$SCRIPT_DIR/macos/native-app/Package.swift" ] && xcode-select -p >/dev/null 2>&1 && command -v swift >/dev/null 2>&1; then
  echo "[Lingo] 检测到 Swift 编译工具链，正在构建/启动 Lingo 原生 SwiftUI 桌面端..."
  if (cd "$SCRIPT_DIR/macos/native-app" && swift build -c release); then
    BIN_DIR="$(cd "$SCRIPT_DIR/macos/native-app" && swift build -c release --show-bin-path)"
    if [ -x "$BIN_DIR/LingoReelApp" ]; then
      if [ "${TERM_PROGRAM:-}" = "Apple_Terminal" ]; then
        nohup env LINGOREEL_APP_DIR="$SCRIPT_DIR" "$BIN_DIR/LingoReelApp" >/dev/null 2>&1 </dev/null &
        sleep 0.6
        auto_close_terminal_if_applicable
        exit 0
      fi
      LINGOREEL_APP_DIR="$SCRIPT_DIR" exec "$BIN_DIR/LingoReelApp"
    fi
  else
    echo "[Lingo] SwiftUI 本机编译未成功，自动切换至同款玩味 3D 原生 PyQt6 桌面控制台..."
  fi
fi

# 2. 否则使用 .venv 启动同款玩味 3D 原生 PyQt6 桌面控制台
if [ -x "$VENV_DIR/bin/python" ] && "$VENV_DIR/bin/python" -B -c "import PyQt6.QtWidgets" >/dev/null 2>&1; then
  echo "[Lingo] 正在启动 Lingo 原生桌面控制台窗口..."
  if [ "${TERM_PROGRAM:-}" = "Apple_Terminal" ]; then
    nohup "$VENV_DIR/bin/python" -B "$SCRIPT_DIR/backend/desktop_native_gui.py" >/dev/null 2>&1 </dev/null &
    sleep 0.6
    auto_close_terminal_if_applicable
    exit 0
  fi
  exec "$VENV_DIR/bin/python" -B "$SCRIPT_DIR/backend/desktop_native_gui.py"
fi

if [ -x "$SCRIPT_DIR/macos/bootstrap.sh" ]; then
  exec "$SCRIPT_DIR/macos/bootstrap.sh" "$SCRIPT_DIR" 8000 --native-setup
fi

echo "[错误] 请先安装 Xcode 命令行工具 (xcode-select --install) 或通过 Lingo-macOS.dmg 安装。"
exit 1
