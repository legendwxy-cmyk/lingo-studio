<p align="center">
  <img src="frontend/public/lingo-logo.png" alt="Lingo" height="92" />
</p>

<h1 align="center">Lingo — AI 双语精听与连续跟读学习机</h1>

<p align="center">
  <strong>当前版本：v1.3.3（Build 8）</strong> · macOS 原生桌面程序 + 本地 / 局域网 / 云端自托管 Web 学习机<br />
  玩味 3D 实体机壳设计 · 全程免命令行启动 · 零密钥离线可用 · 同 Wi-Fi 平板 / 手机免装 App 直连
</p>

<p align="center">
  <a href="https://github.com/legendwxy-cmyk/lingo-studio/raw/main/releases/Lingo-macOS.dmg"><strong>⬇ 下载 macOS 安装包（Lingo-macOS.dmg）</strong></a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="https://github.com/legendwxy-cmyk/lingo-studio/raw/main/releases/Lingo-User-Guide-1080p.mp4"><strong>🎬 观看 1080p 零基础使用介绍视频（2分48秒）</strong></a>
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <a href="DEPLOY.md"><strong>☁️ 云端与 Docker 部署指南</strong></a>
</p>

---

## 界面一览

### 1. Web 精听学习机（玩味 3D 实体旋钮与拨动开关）
<p align="center">
  <img src="docs/screenshots/web_learning_machine.png" alt="Lingo Web 学习机（柑橘旋钮机皮肤）" width="100%" />
</p>

### 2. macOS 原生桌面控制台（拨开「局域网共享」即刻显示完整局域网网址）
<p align="center">
  <img src="docs/screenshots/desktop_console_lan.png" alt="Lingo macOS 桌面控制台与局域网共享" width="100%" />
</p>

### 3. 同 Wi-Fi 平板电脑大屏直连（免装任何 App，进度与跟读记录实时同步）
<p align="center">
  <img src="docs/screenshots/ipad_lan_view.png" alt="iPad 浏览器局域网访问 Lingo 学习机" width="88%" />
</p>

---

## 下载与快速获取（v1.3.3）

| 交付文件 | 适用场景 | 体积 | 获取方式 |
|---|---|---|---|
| **macOS 通用安装包**（Apple Silicon & Intel） | 双击挂载并将 `Lingo.app` 拖入「应用程序」即用 | `16.06 MB` | [下载 Lingo-macOS.dmg](https://github.com/legendwxy-cmyk/lingo-studio/raw/main/releases/Lingo-macOS.dmg) |
| **macOS 便携压缩包** | 解压后直接运行或供开发者查阅脚本 | `2.38 MB` | [下载 lingo-macos.zip](https://github.com/legendwxy-cmyk/lingo-studio/raw/main/releases/lingo-macos.zip) |
| **零基础全流程使用介绍视频**（1080p 30fps） | 带中文自然配音、字幕与实机操作演示，2 分 48 秒走完安装到平板联机 | `36.42 MB` | [下载 Lingo-User-Guide-1080p.mp4](https://github.com/legendwxy-cmyk/lingo-studio/raw/main/releases/Lingo-User-Guide-1080p.mp4) |

---

## 核心特性

### 1. macOS 原生桌面控制台（全程免命令行）
- **通用二进制启动器 + 原生桌面窗口**：内嵌 SwiftUI 原生桌面控制中心（Playful 3D 视觉与 Web 端完全统一，无 Xcode 环境下自动平滑回退同视觉 PyQt6 原生窗口），顶部支持一键切换 **柑橘旋钮机 / 薰衣草工坊 / 奶油陶瓷台** 三套 3D 皮肤，并常驻系统菜单栏快捷图标。
- **免命令行自动初始化**：首次启动由原生 Cocoa 进度浮窗在后台自动完成环境准备与校验，**不弹出黑色终端窗口**，准备完成后自动关闭浮窗并打开桌面控制台。
- **4 大核心控制面板**：
  - **服务总览**：3D 实体状态表盘（`:8000 ON AIR`）、一键启停/重启、监听端口、局域网共享、访问口令锁与自动启动。
  - **环境与依赖**：自动检测 Python 3.10–3.12 独立虚拟环境、核心引擎、FFmpeg、本地离线 Whisper 语音模型（`tiny.en`）与前端资源，内置清华 PyPI / `hf-mirror` 国内加速镜像，缺失一键补齐。
  - **AI 模型配置**：内置 DeepSeek / OpenAI / 通义千问 / Groq / 硅基流动 / Gemini 一键预设，支持密钥脱敏保存与一键测速连通。
  - **运行日志**：实时查看服务与安装日志、关键词过滤与一键复制。
- **无缝覆盖升级**：覆盖安装新版本 `Lingo.app` 后，启动器会自动识别构建版本号并优雅替换旧版后台进程与常驻窗口，同时通过缓存控制确保浏览器立即加载最新界面；用户全部历史数据自动保留。

### 2. 局域网一键共享与多端大屏访问（v1.3.3 增强）
- **开启即见地址**：在控制台拨开 **「局域网共享」** 开关的瞬间，开关正下方与顶部状态卡均立即显示可选中、可一键复制的完整局域网网址（如 `http://192.168.1.28:8000`），修改端口实时联动。
- **一键应用生效**：若服务此前仅在 `127.0.0.1` 运行，地址旁会直接出现 **「立即应用并重启」** 按钮，点一下即可切换为 `0.0.0.0` 对局域网生效。
- **防代理 / VPN 假 IP 干扰**：内置物理网卡（`en0` / `en1` / `en*`）RFC1918 私网 IP 优先探测算法，自动过滤回环、链路本地 `169.254.*` 以及 Clash / Surge / VPN 的 `utun` 与 `198.18.*` 虚拟假 IP。
- **可选访问口令锁**：家庭自用可留空免密直进；在公共 Wi-Fi 或云端部署时可设置口令保护学习记录。

### 3. 资料库与 5 步全自动拆解流水线
- 支持拖入任意 **MP4 / MOV / WebM / MP3 / WAV / M4A**（可选附带 SRT / VTT 字幕）。
- 实时可视化展示 5 步处理进度：**音画抽帧 → 断句转写 → 译文音标 → 词块抽取 → 词句绑定**。
- **双引擎无缝切换**：
  - **零密钥纯离线引擎**：FFmpeg 抽帧/音轨 + SRT/VTT 双语解析或本地 `faster-whisper` 离线转写 + CMUdict `eng_to_ipa` 音标 + 内置精选词块库 + 离线复述覆盖率批改。
  - **云端增强引擎**：绑定 DeepSeek / OpenAI / 通义千问 / Groq / SiliconFlow / Gemini 兼容 API Key 后，自动启用高质量 LLM 逐句精译、词典精讲与 AI 口语复述教练。

### 4. 学习机精听与同步连续跟读
- **实体操作台体验**：球面 3D 倍速旋钮（`0.5x – 2.0x`）、逐句快切键、精确 AB 区间复读、断点续播与字幕自动跟随，配备 6 枚 3D 实体拨动开关（单句循环 / 逐句暂停 / 盲听模式 / 音标 IPA / AB 复读 / 画面字幕）。
- **播放原文同步连续跟读**：开启「跟读对比」并开始录音后，随着原文视频/音频连续向前播放，系统会按句子时间轴自动将连续跟读录音拆分、转写打分并**分别归档保存到对应的每一句下方**，随时逐句回放原声与跟读对比。
- **全套精学工具箱**：双语精听、连续跟读对比、挖空回忆、关键词与全句听写、重点词典与跨篇词块复现跳转、AI 精讲与语音口述复述、字幕增删校对与替换 SRT、3D 闪卡生词本（支持 CSV / Anki TSV 导出）以及可打印 PDF 精听讲义。

---

## macOS 零基础 5 步上手指南

1. **拖拽安装**：下载并双击打开 [Lingo-macOS.dmg](https://github.com/legendwxy-cmyk/lingo-studio/raw/main/releases/Lingo-macOS.dmg)，将 `Lingo.app` 拖入右侧 `Applications（应用程序）` 文件夹。
2. **放行 Mac 隐私与安全性**：
   - 首次打开若提示「无法验证开发者」，先点 **「完成」** 关闭弹窗；
   - 前往 **「系统设置 → 隐私与安全性 → 安全性」**，点击 `Lingo` 右侧的 **「仍要打开」** 并输入开机密码即可永久放行（也可在「应用程序」里右键点击 `Lingo` 选择「打开」）；
   - 顺手确认开启 **「本地网络」**（供平板连接）与 **「麦克风」**（供网页跟读录音）权限。
3. **环境自检（全程免命令行）**：首次启动由原生浮窗自动准备环境并进入桌面控制台；切到 **「环境与依赖」** 确认 5 项全部亮绿「已就绪」（如有黄/红项，点左上 **「修复 / 更新依赖」** 自动走国内镜像补齐）。
4. **一键发布与开启局域网共享**：回到 **「服务总览」**，保持默认端口 `8000`，拨开 **「局域网共享」** 开关，此时下方会立刻显示本机局域网地址（例如 `http://192.168.1.28:8000`）；点 **「启动学习机服务」**（或 **「立即应用并重启」**）看到 `:8000 ON AIR` 亮起即发布完成。
5. **电脑与平板双端精听**：
   - **电脑使用**：点击控制台 **「在浏览器打开学习机」** 即可开始上传视频与精听跟读；
   - **平板 / 手机访问**：确保平板与 Mac 连在**同一个 Wi-Fi** 下且 Mac 端服务保持运行，在平板浏览器（Safari / Chrome）地址栏直接输入控制台显示的局域网网址（如 `http://192.168.1.28:8000`）回车即用，无需安装 App。

> **数据存储位置**：macOS 桌面版的全部语料库、跟读录音、生词本、配置与 Whisper 缓存均独立保存在 `~/Library/Application Support/LingoReelStudio/`，覆盖更新或重装程序不会丢失任何学习记录。

---

## 本地开发与自托管启动

### 方式一：单端口生产模式（构建前端并由 FastAPI 统一托管，端口 `8000`）
```bash
./start.sh
```

### 方式二：前后端分离开发模式
```bash
# 终端 1：后端 API（端口 8000）
cd backend
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000

# 终端 2：前端热更新（端口 5173）
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

### 方式三：Docker / 云端部署
支持 Docker Compose（含自动 HTTPS 的 Caddy 配置）以及 Render / Zeabur / Railway 一键托管，详见 [DEPLOY.md](DEPLOY.md)：
```bash
cp .env.example .env      # 设置公网访问密码 APP_ACCESS_PASSWORD
docker compose up -d --build
```

---

## 仓库目录结构

```text
lingoreel/
├── frontend/               # React 19 + Vite + Playful 3D Vanilla CSS 学习机前端
├── backend/                # FastAPI + SQLite(WAL) + FFmpeg + Whisper 拆解与桌面控制后端
│   ├── main.py             # 学习机核心 API、流式媒体、认证与缓存控制
│   ├── pipeline.py         # 5 步音视频自动拆解与连续跟读逐句切分引擎
│   ├── desktop_console.py  # 桌面服务管理、环境检测、防 VPN 局域网 IP 探测与备用 Web 控制台
│   └── desktop_native_gui.py # Playful 3D PyQt6 原生桌面控制台
├── macos/                  # macOS 通用打包与原生桌面工程
│   ├── launcher/           # Go 通用二进制启动器（arm64 + x86_64，免终端编排与单实例升级替换）
│   ├── native-app/         # SwiftUI 原生桌面应用源码（LingoReelCore + LingoReelApp + Tests）
│   ├── setup_progress.jxa  # macOS 原生 Cocoa 无命令行安装进度浮窗
│   └── package_macos_artifacts.py # 一键构建前端、透明 3D AppIcon、通用 DMG 与 ZIP 脚本
├── releases/               # 已构建发布的 Lingo-macOS.dmg、lingo-macos.zip 与 1080p 使用介绍视频
├── video-guide/            # 1080p 零基础使用介绍视频的分镜导演稿、Edge-TTS 音频与确定性渲染工程
├── docs/screenshots/       # README 展示用实机截图
├── DEPLOY.md               # 云端与 Docker Compose 部署文档
├── LICENSE                 # MIT 开源协议
└── macOS安装说明.txt        # 随包附带的 macOS 快速安装指引
```

---

## 构建、打包与测试

```bash
# 1. 运行 Go 通用启动器单元测试
cd macos/launcher && go test -v ./...

# 2. 在 macOS 上运行 Swift Core 单元测试
cd macos/native-app && swift test

# 3. 重新构建前端并一键生成 macOS DMG 与 ZIP 安装包
python3 macos/package_macos_artifacts.py
```

---

## 最近版本更新

- **v1.3.3（Build 8）**
  - 在 SwiftUI / PyQt6 / Web 三端控制台拨开 **「局域网共享」** 开关时，立即在开关下方与顶部状态卡显示可复制的完整局域网网址，实时联动监听端口，并提供 **「立即应用并重启」** 一键按钮；
  - 升级物理网卡 RFC1918 私网 IPv4 优先检测，自动避开 Clash / Surge / VPN 虚拟网卡与 `198.18.*` 假 IP；
  - 新增 **1080p 零基础全流程使用介绍视频**（`releases/Lingo-User-Guide-1080p.mp4`，2 分 48 秒，带自然中文配音、字幕与实机演示）。
- **v1.3.2（Build 7）**
  - 彻底修复覆盖升级时旧版后台进程残留与浏览器缓存问题（`Cache-Control: no-store` + 构建版本查询参数 + 版本感知单实例替换），确保左上角立即展示全新无底衬 3D「Lingo」标志。
- **v1.3.1 / v1.3.0**
  - 全面焕新为 **Lingo** 玩味 3D 品牌视觉、无白边透明 AppIcon 与三套 3D 桌面端皮肤；
  - 实现首次启动免命令行原生 Cocoa 进度浮窗；
  - 新增播放原文同步连续跟读录音与自动按句归档对比功能。

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。

