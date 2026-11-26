#!/usr/bin/env bash
set -euo pipefail

# Lingo.app 内部引导脚本（支持 --swift-build 一键原生编译 SwiftUI、--native-setup 自动配置 PyQt6 桌面端）
# 用法: bootstrap.sh <RESOURCES_DIR> <PORT> [--swift-build | --native-setup | --console | --interactive | --daemon]

RESOURCES_DIR="${1:?missing resources dir}"
PORT="${2:-8000}"
RUN_MODE="${3:---native-setup}"

export PATH="/opt/homebrew/bin:/opt/homebrew/opt/python@3.12/bin:/usr/local/bin:/usr/local/opt/python@3.12/bin:/Library/Frameworks/Python.framework/Versions/3.12/bin:/Library/Frameworks/Python.framework/Versions/3.11/bin:/Library/Frameworks/Python.framework/Versions/3.10/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

APP_SUPPORT="${LINGOREEL_APP_SUPPORT:-$HOME/Library/Application Support/LingoReelStudio}"
VENV_DIR="${LINGOREEL_VENV_DIR:-$APP_SUPPORT/.venv}"
BIN_DIR="$APP_SUPPORT/bin"
MARKER="$VENV_DIR/.deps_installed_v2"
BACKEND_DIR="$RESOURCES_DIR/backend"
ACTIVE_URL_FILE="$APP_SUPPORT/active_url.txt"
PID_FILE="$APP_SUPPORT/server.pid"

mkdir -p "$APP_SUPPORT/data" "$APP_SUPPORT/whisper-cache" "$APP_SUPPORT/python" "$APP_SUPPORT/uv-cache" "$BIN_DIR" "$APP_SUPPORT/swift-apps"

export LINGOREEL_DATA_DIR="$APP_SUPPORT/data"
export LINGOREEL_FRONTEND_DIST="$RESOURCES_DIR/frontend/dist"
export LINGOREEL_VENV_DIR="$VENV_DIR"
export LINGOREEL_DESKTOP_APP="1"
export HF_HOME="$APP_SUPPORT/whisper-cache"
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export UV_PYTHON_INSTALL_DIR="$APP_SUPPORT/python"
export UV_CACHE_DIR="$APP_SUPPORT/uv-cache"
export PYTHONUNBUFFERED=1

say_step() {
  echo "[Lingo] $1"
}

is_interactive_tty() {
  [ -t 0 ] && [ "${LINGOREEL_NO_TTY:-0}" != "1" ]
}

auto_close_terminal_if_applicable() {
  if [ "$(uname -s)" = "Darwin" ] && [ "${TERM_PROGRAM:-}" = "Apple_Terminal" ] && [ -t 1 ] && [ "${LINGOREEL_AUTO_CLOSE_TERMINAL:-1}" = "1" ] && [ "${LINGOREEL_NO_TTY:-0}" != "1" ]; then
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

# ==============================================================================
# 模式 0: --swift-build — 本机一键编译 100% 原生 SwiftUI Lingo.app（仅首次约 15 秒）
# ==============================================================================
if [ "$RUN_MODE" = "--swift-build" ]; then
  if is_interactive_tty; then
    clear || true
  fi
  echo "============================================================"
  echo "  Lingo — 首次启动原生 SwiftUI 桌面程序构建（仅需一次）"
  echo "============================================================"
  echo "  正在为您本机编译 100% 原生 macOS SwiftUI + AppKit 桌面控制台"
  echo "  预计耗时 15–30 秒，编译完成后将自动缓存并直接打开 Lingo 原生窗口！"
  echo "============================================================"
  echo ""

  SRC_SWIFT="$RESOURCES_DIR/native-app"
  HASH_FILE="$RESOURCES_DIR/swift_source.sha256"
  if [ ! -f "$SRC_SWIFT/Package.swift" ] || [ ! -f "$HASH_FILE" ]; then
    say_step "未找到 SwiftUI 源码目录，自动切换至原生 PyQt6 桌面控制台..."
    exec "$0" "$RESOURCES_DIR" "$PORT" "--native-setup"
  fi

  SHORT_HASH="$(head -c 8 "$HASH_FILE" | tr -d '[:space:]')"
  SWIFT_VER="$(/usr/bin/swift --version 2>/dev/null | awk 'NF { $1=$1; print; exit }' || true)"
  FAIL_MARKER="$APP_SUPPORT/swift-apps/failed_build.marker"
  BUILD_WORK="$APP_SUPPORT/swift-build-$SHORT_HASH"
  TARGET_APP="$APP_SUPPORT/swift-apps/Lingo-${SHORT_HASH}.app"
  TMP_APP="$APP_SUPPORT/swift-apps/.Lingo-${SHORT_HASH}.app.tmp"

  rm -rf "$BUILD_WORK" "$TMP_APP"
  cp -R "$SRC_SWIFT" "$BUILD_WORK"

  say_step "[1/3] 正在编译 Lingo 原生 SwiftUI 桌面程序..."
  if (cd "$BUILD_WORK" && /usr/bin/swift build -c release); then
    BIN_DIR_SWIFT="$(cd "$BUILD_WORK" && /usr/bin/swift build -c release --show-bin-path)"
    SWIFT_BIN="$BIN_DIR_SWIFT/LingoReelApp"

    say_step "[2/3] 正在组装并签名 Lingo 原生 App（含无白边 3D 图标与透明 Logo）..."
    mkdir -p "$TMP_APP/Contents/MacOS" "$TMP_APP/Contents/Resources/app/backend" "$TMP_APP/Contents/Resources/app/frontend/dist"
    cp "$RESOURCES_DIR/../Info.plist" "$TMP_APP/Contents/Info.plist"
    plutil -replace CFBundleIdentifier -string com.lingoreel.studio.native "$TMP_APP/Contents/Info.plist" >/dev/null 2>&1 || true
    plutil -replace LSUIElement -bool false "$TMP_APP/Contents/Info.plist" >/dev/null 2>&1 || true
    printf 'APPL????' > "$TMP_APP/Contents/PkgInfo"
    cp "$SWIFT_BIN" "$TMP_APP/Contents/MacOS/LingoReelApp"
    chmod +x "$TMP_APP/Contents/MacOS/LingoReelApp"
    cp "$RESOURCES_DIR/AppIcon.icns" "$TMP_APP/Contents/Resources/AppIcon.icns"
    if [ -f "$RESOURCES_DIR/lingo-logo.png" ]; then
      cp "$RESOURCES_DIR/lingo-logo.png" "$TMP_APP/Contents/Resources/lingo-logo.png"
    fi
    for b in "$BIN_DIR_SWIFT"/*.bundle; do
      if [ -d "$b" ]; then
        cp -R "$b" "$TMP_APP/Contents/Resources/"
      fi
    done
    cp -R "$RESOURCES_DIR/backend/." "$TMP_APP/Contents/Resources/app/backend/"
    cp -R "$RESOURCES_DIR/frontend/dist/." "$TMP_APP/Contents/Resources/app/frontend/dist/"
    codesign --force --deep --sign - "$TMP_APP" >/dev/null 2>&1 || true

    say_step "[3/3] 正在自检并启动 Lingo 原生 SwiftUI 桌面端..."
    if "$TMP_APP/Contents/MacOS/LingoReelApp" --self-test --verify-bundle; then
      rm -rf "$TARGET_APP"
      mv "$TMP_APP" "$TARGET_APP"
      rm -rf "$BUILD_WORK"
      rm -f "$FAIL_MARKER"
      # 清理旧版本缓存的 SwiftUI App
      for old_app in "$APP_SUPPORT/swift-apps"/Lingo-*.app; do
        if [ -d "$old_app" ] && [ "$old_app" != "$TARGET_APP" ]; then
          rm -rf "$old_app"
        fi
      done
      if [ "${LINGOREEL_SKIP_RELAUNCH:-0}" = "1" ]; then
        say_step "Lingo 原生 SwiftUI 桌面端已编译就绪，正在打开窗口..."
        exit 0
      fi
      /usr/bin/open -a "$TARGET_APP"
      echo ""
      echo "============================================================"
      echo "  [✓] Lingo 原生 SwiftUI 桌面控制台已编译就绪并打开！"
      echo "  以后直接点击「Lingo」应用图标即可 0.2 秒秒开原生 SwiftUI 窗口。"
      echo "  此终端窗口即将自动关闭..."
      echo "============================================================"
      auto_close_terminal_if_applicable
      exit 0
    fi
  fi

  rm -rf "$BUILD_WORK" "$TMP_APP"
  printf '%s|%s\n' "$SHORT_HASH" "$SWIFT_VER" > "$FAIL_MARKER"
  say_step "SwiftUI 本机编译未成功，将自动为您准备同款玩味 3D 原生 PyQt6 桌面控制台..."
  RUN_MODE="--native-setup"
fi

ensure_uv() {
  local arch tmp_dir url
  arch="$(uname -m)"
  if [ -x "$RESOURCES_DIR/bin/uv-$arch" ]; then
    echo "$RESOURCES_DIR/bin/uv-$arch"
    return 0
  fi
  if [ -x "$BIN_DIR/uv" ]; then
    echo "$BIN_DIR/uv"
    return 0
  fi
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return 0
  fi

  say_step "正在自动下载轻量安装工具 uv（用于免配置安装 Python 3.12）..." >&2
  tmp_dir="$(mktemp -d)"
  if [ "$arch" = "arm64" ]; then
    url="https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz"
  else
    url="https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-apple-darwin.tar.gz"
  fi
  if curl -fsSL --connect-timeout 15 --max-time 90 "$url" -o "$tmp_dir/uv.tar.gz" 2>/dev/null; then
    tar -xzf "$tmp_dir/uv.tar.gz" -C "$tmp_dir"
    find "$tmp_dir" -maxdepth 2 -name uv -type f -exec cp {} "$BIN_DIR/uv" \;
    chmod +x "$BIN_DIR/uv"
    rm -rf "$tmp_dir"
    if [ -x "$BIN_DIR/uv" ]; then
      echo "$BIN_DIR/uv"
      return 0
    fi
  fi
  rm -rf "$tmp_dir"

  if UV_INSTALL_DIR="$BIN_DIR" curl -LsSf --connect-timeout 15 --max-time 90 https://astral.sh/uv/install.sh | sh >/dev/null 2>&1; then
    if [ -x "$BIN_DIR/uv" ]; then
      echo "$BIN_DIR/uv"
      return 0
    fi
  fi
  return 1
}

find_system_python312() {
  for bin in python3.12 python3.11 python3.10; do
    if command -v "$bin" >/dev/null 2>&1; then
      command -v "$bin"
      return 0
    fi
  done
  if command -v python3 >/dev/null 2>&1; then
    local py3_path
    py3_path="$(command -v python3)"
    if [ "$py3_path" != "/usr/bin/python3" ] || /usr/bin/xcode-select -p >/dev/null 2>&1; then
      if "$py3_path" -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)" 2>/dev/null; then
        echo "$py3_path"
        return 0
      fi
    fi
  fi
  return 1
}

# 1. 首次启动：自动准备 Python 3.12 与独立虚拟环境
if [ ! -f "$MARKER" ]; then
  if [ "$RUN_MODE" != "--daemon" ]; then
    if is_interactive_tty; then
      clear || true
    fi
    echo "============================================================"
    echo "  Lingo — 首次启动原生桌面环境自动安装向导"
    echo "============================================================"
    echo "  全程全自动安装 Python 3.12 与核心引擎（约 1–2 分钟）"
    echo "  安装完成后将自动打开「Lingo 玩味 3D 原生桌面控制台」！"
    echo "============================================================"
    echo ""
  fi

  PYTHON_BIN="$(find_system_python312 || true)"
  UV_BIN=""

  if [ -n "$PYTHON_BIN" ]; then
    say_step "已检测到兼容 Python：$("$PYTHON_BIN" --version) ($PYTHON_BIN)"
  else
    say_step "未检测到 Python 3.10–3.12，正在为您自动安装 Python 3.12..."
    UV_BIN="$(ensure_uv || true)"
    if [ -n "$UV_BIN" ]; then
      say_step "正在通过 uv 下载独立版 Python 3.12..."
      if "$UV_BIN" python install 3.12; then
        PYTHON_BIN="$("$UV_BIN" python find 3.12 2>/dev/null || true)"
      fi
    fi

    if [ -z "$PYTHON_BIN" ] && command -v brew >/dev/null 2>&1; then
      say_step "正在通过 Homebrew 安装 python@3.12（请稍候）..."
      brew install python@3.12
      export PATH="/opt/homebrew/opt/python@3.12/bin:/usr/local/opt/python@3.12/bin:$PATH"
      PYTHON_BIN="$(find_system_python312 || true)"
    fi

    if [ -z "$PYTHON_BIN" ]; then
      echo ""
      echo "[错误] 自动安装 Python 3.12 失败（请检查网络连接）。"
      echo "       您也可以手动访问 https://www.python.org/downloads/macos/ 安装 Python 3.12 后重新打开「Lingo」。"
      if is_interactive_tty && [ "$RUN_MODE" != "--daemon" ]; then
        read -r -p "按回车键关闭窗口..."
      fi
      exit 1
    fi
    say_step "Python 3.12 安装成功：$("$PYTHON_BIN" --version)"
  fi

  if [ -z "$UV_BIN" ]; then
    UV_BIN="$(ensure_uv || true)"
  fi
  say_step "正在创建独立运行环境 ($VENV_DIR)..."
  if [ ! -d "$VENV_DIR" ]; then
    if [ -n "$UV_BIN" ]; then
      "$UV_BIN" venv --seed --python "$PYTHON_BIN" "$VENV_DIR"
    else
      "$PYTHON_BIN" -m venv "$VENV_DIR"
    fi
  fi

  say_step "正在安装 Lingo 核心引擎（FastAPI / Whisper / 音标 / FFmpeg / 原生桌面组件）..."
  if [ -n "$UV_BIN" ]; then
    if ! "$UV_BIN" pip install --python "$VENV_DIR/bin/python" -r "$BACKEND_DIR/requirements.txt" --default-index https://pypi.tuna.tsinghua.edu.cn/simple; then
      say_step "正在切换官方 PyPI 源完成安装..."
      "$UV_BIN" pip install --python "$VENV_DIR/bin/python" -r "$BACKEND_DIR/requirements.txt"
    fi
  else
    "$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null 2>&1 || true
    if ! "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn; then
      "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
    fi
  fi

  touch "$MARKER"
  say_step "全部核心依赖安装完成！"
fi

# 1b. 若是从旧版升级（已有 .venv 但尚未安装 PyQt6 原生桌面组件），自动补装 PyQt6 预编译包
if [ "$(uname -s)" = "Darwin" ] && [ -x "$VENV_DIR/bin/python" ]; then
  if ! "$VENV_DIR/bin/python" -B -c "import PyQt6.QtWidgets" >/dev/null 2>&1; then
    say_step "正在为当前环境补装 macOS 原生桌面界面组件（PyQt6 预编译包，仅首次约 15 秒）..."
    UV_BIN="$(ensure_uv || true)"
    if [ -n "$UV_BIN" ]; then
      if ! "$UV_BIN" pip install --python "$VENV_DIR/bin/python" --only-binary :all: "PyQt6>=6.6.0" --default-index https://pypi.tuna.tsinghua.edu.cn/simple; then
        "$UV_BIN" pip install --python "$VENV_DIR/bin/python" --only-binary :all: "PyQt6>=6.6.0" || true
      fi
    fi
    if ! "$VENV_DIR/bin/python" -B -c "import PyQt6.QtWidgets" >/dev/null 2>&1; then
      if ! "$VENV_DIR/bin/python" -m pip install --only-binary :all: "PyQt6>=6.6.0" -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn; then
        "$VENV_DIR/bin/python" -m pip install --only-binary :all: "PyQt6>=6.6.0" || true
      fi
    fi
  fi
fi

# 2. 自动确保 FFmpeg 可用
export PATH="$VENV_DIR/bin:$PATH"
if ! command -v ffmpeg >/dev/null 2>&1; then
  FF_PATH="$("$VENV_DIR/bin/python" -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null || true)"
  if [ -n "$FF_PATH" ] && [ -x "$FF_PATH" ]; then
    ln -sf "$FF_PATH" "$VENV_DIR/bin/ffmpeg"
    say_step "已启用内置 FFmpeg 音画解码组件"
  elif [ "$RUN_MODE" != "--daemon" ] && command -v brew >/dev/null 2>&1; then
    say_step "正在通过 Homebrew 安装 FFmpeg..."
    brew install ffmpeg || true
  fi
fi

cd "$BACKEND_DIR"

# 3. 原生桌面控制台模式（默认绝不静默打开浏览器控制台）
if [ "$RUN_MODE" = "--console" ] || [ "$RUN_MODE" = "--native-setup" ]; then
  HAS_PYQT=0
  if [ -x "$VENV_DIR/bin/python" ] && "$VENV_DIR/bin/python" -B -c "import PyQt6.QtWidgets" >/dev/null 2>&1; then
    HAS_PYQT=1
  fi
  LAUNCHER_BIN="$RESOURCES_DIR/../MacOS/LingoReelApp"
  if [ "$HAS_PYQT" = "1" ]; then
    if [ "${LINGOREEL_SKIP_RELAUNCH:-0}" = "1" ]; then
      say_step "原生桌面组件已就绪，正在打开 Lingo 原生窗口..."
      exit 0
    fi
    say_step "正在启动「Lingo — macOS 原生桌面控制台」..."
    if [ -x "$LAUNCHER_BIN" ]; then
      nohup env LINGOREEL_SKIP_SWIFT_BUILD=1 LINGOREEL_SKIP_NATIVE_SETUP=1 "$LAUNCHER_BIN" >/dev/null 2>&1 </dev/null &
      sleep 0.6
      echo ""
      echo "============================================================"
      echo "  [✓] Lingo 原生桌面控制台已启动！此终端窗口即将自动关闭..."
      echo "  以后直接双击「Lingo」应用图标即可秒开原生桌面窗口。"
      echo "============================================================"
      auto_close_terminal_if_applicable
      exit 0
    fi
    if [ "${TERM_PROGRAM:-}" = "Apple_Terminal" ]; then
      nohup "$VENV_DIR/bin/python" -B "$BACKEND_DIR/desktop_native_gui.py" >/dev/null 2>&1 </dev/null &
      sleep 0.6
      auto_close_terminal_if_applicable
      exit 0
    fi
    exec "$VENV_DIR/bin/python" -B "$BACKEND_DIR/desktop_native_gui.py"
  else
    echo ""
    echo "============================================================"
    echo "  [!] 未能安装原生桌面组件 PyQt6（请检查网络或确认 Python 版本为 3.10–3.12）。"
    echo "      您也可以运行 xcode-select --install 后重新打开 Lingo 以启用 100% SwiftUI 原生端。"
    echo "============================================================"
    if is_interactive_tty; then
      read -r -p "按回车键关闭窗口..."
    fi
    exit 1
  fi
fi

# 4. 兼容直接后台启动模式
BIND_HOST="127.0.0.1"
if [ "${LINGOREEL_LAN:-0}" = "1" ]; then
  BIND_HOST="0.0.0.0"
fi
URL="http://127.0.0.1:${PORT}"
echo "$URL" > "$ACTIVE_URL_FILE"

PROXY_FLAG="--no-proxy-headers"
if [ "${TRUST_PROXY:-0}" = "1" ]; then
  PROXY_FLAG="--proxy-headers"
fi

if [ "$RUN_MODE" = "--daemon" ]; then
  echo $$ > "$PID_FILE"
  exec "$VENV_DIR/bin/uvicorn" main:app --host "$BIND_HOST" --port "$PORT" "$PROXY_FLAG"
else
  say_step "正在启动 Lingo 学习机（${BIND_HOST}:${PORT}）..."
  nohup "$VENV_DIR/bin/uvicorn" main:app --host "$BIND_HOST" --port "$PORT" "$PROXY_FLAG" > "$APP_SUPPORT/server.log" 2>&1 < /dev/null &
  SERVER_PID=$!
  echo "$SERVER_PID" > "$PID_FILE"

  for _ in $(seq 1 90); do
    if curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  open "$URL" 2>/dev/null || true
fi
