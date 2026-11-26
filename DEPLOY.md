# Lingo 云端部署指南

支持两种上线方式：**免买服务器一键云平台托管（Zeabur / Render / Railway）**，或 **自有 Linux 云服务器（Docker Compose）**。

---

## 方式一：免买服务器，一键托管到云平台（自带免费 HTTPS 域名）

适合不想维护 Linux 服务器、希望几分钟拿到 `https://xxx` 网址直接开用的场景（自带 HTTPS 证书，手机和电脑均可直接开启麦克风跟读与口述复述）。

### 1. Render（有免费体验档）
- 网址：https://render.com
- 部署后默认地址：`https://lingoreel-studio.onrender.com`（可自定义名称或绑定自有域名）
- 步骤：
  1. 用 GitHub 登录 Render，点击 **New + → Blueprint**（或 **Web Service**），选中本仓库 `lingoreel-studio`。
  2. 系统会自动识别仓库根目录的 `render.yaml` 与 `Dockerfile`。
  3. 填入环境变量 `APP_ACCESS_PASSWORD`（你的公网访问密码），点击 **Deploy** 等待 3–5 分钟构建完成即可访问。
- 提示：Render 免费档无持久盘（休眠重启后新上传视频会重置）；如需长期保留上传视频和生词本，升级 Starter 并挂载持久盘到 `/app/backend/data`。

### 2. Zeabur（国内直连较快，支持持久存储卷）
- 网址：https://zeabur.com
- 部署后默认地址：`https://你的项目名.zeabur.app`
- 步骤：
  1. 用 GitHub 登录 Zeabur，新建项目 → **从 GitHub 仓库部署** → 选中 `lingoreel-studio`（自动识别 `Dockerfile`）。
  2. 在「环境变量」添加 `APP_ACCESS_PASSWORD=你的强密码`。
  3. 在「存储（Volumes）」添加持久化挂载目录：`/app/backend/data`（保存数据库与视频）和 `/app/whisper-cache`（缓存离线语音模型）。
  4. 在「域名」页点击 **生成免费域名** 即可通过 `https://xxx.zeabur.app` 访问。

### 3. Railway
- 网址：https://railway.app
- 部署后默认地址：`https://lingoreel-studio-production.up.railway.app`
- 步骤：GitHub 登录 → **New Project → Deploy from GitHub repo** → 选中 `lingoreel-studio`（自动读取 `railway.json` + `Dockerfile`）→ 设置环境变量 `APP_ACCESS_PASSWORD` → 添加 Volume 挂载到 `/app/backend/data` → 点击 **Generate Domain**。

---

## 方式二：自有 Linux 云服务器（阿里云 / 腾讯云 / 海外 VPS）

适合已有云服务器、想要最大硬盘空间和最低年费的场景。

### 推荐服务器规格
- **云端 API 模式**（OpenAI / DeepSeek / 通义千问 / Groq / SiliconFlow）：**1 核 2G**、30GB+ 硬盘即可。
- **纯离线本地 Whisper 模式**：**2 核 4G**、40GB+ 硬盘。

### 5 分钟一键上线
```bash
# 1. 如未安装 Docker，先执行：
curl -fsSL https://get.docker.com | sh

# 2. 拉取代码并配置公网访问口令
git clone <你的仓库地址> lingoreel
cd lingoreel
cp .env.example .env
nano .env   # 修改 APP_ACCESS_PASSWORD 为你的强密码

# 3A. 纯 IP + 端口启动（放行 8000 端口，访问 http://服务器IP:8000）
docker compose up -d --build

# 3B. 或绑定域名 + 自动免费 HTTPS（放行 80/443，完整支持麦克风跟读）
cp Caddyfile.example Caddyfile
nano Caddyfile   # 替换为你的真实域名
docker compose --profile https up -d --build
```

### 日常运维与数据备份
- 查看日志：`docker compose logs -f lingoreel`
- 更新代码：`git pull && docker compose up -d --build`
- 备份全部视频、录音与数据库：`tar -czf lingoreel_backup_$(date +%F).tar.gz data/`
