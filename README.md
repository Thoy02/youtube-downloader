# YouTube 下载器

粘贴 YouTube 链接，下载 **MP4 视频** 或 **MP3 音频**。  
**不需要 npm**，用 Python 即可运行；部署到云端后，任何电脑用手机/浏览器都能用。

## 功能

- 粘贴 YouTube 链接自动解析标题、封面、时长
- 多种 MP4 画质（720p、1080p 等）
- 一键下载 MP3（192kbps）
- 下载进度显示
- 深色现代界面

## 方式一：本机一键启动（给局域网其他设备用）

```bash
chmod +x start.sh
./start.sh
```

浏览器打开终端里显示的地址。同一 WiFi 下的手机、别的电脑访问 **局域网地址** 即可。

**需要 ffmpeg（MP3 必装）：**

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg
```

## 方式二：Docker 部署（推荐，任何电脑都能用公网链接）

```bash
docker build -t youtube-downloader .
docker run -d -p 8080:8080 --name yt-dl youtube-downloader
```

访问：`http://你的服务器IP:8080`

## 能放 Vercel 吗？（`xxx.vercel.app` 那种链接）

**不太适合。** Vercel 主要给静态网页和「几秒就结束」的 Serverless 函数用，而这个项目需要：

| 需求 | Vercel | Render / Railway（推荐） |
|------|--------|--------------------------|
| 下载可能要 1～5 分钟 | 函数最长约 10～60 秒就超时 | 可以长时间跑 |
| 需要 yt-dlp + ffmpeg | 很难装、容量不够 | Docker 里自带 |
| 后台任务 + 进度条 | 无状态，不好做 | 正常 Web 服务 |

所以：**想要「一个链接、任何电脑都能打开」**，请用下面 **Render**（体验和 Vercel 很像：连 GitHub → 自动部署 → 得到一个 `https://xxx.onrender.com`）。

若你坚持要 `vercel.app` 域名，只能把**纯前端**放 Vercel，下载 API 还要放在 Render 上，维护两套，不推荐。

---

## 方式三：Render 部署（最接近 Vercel，免费公网链接）

和 Vercel 一样：**不用开自己电脑**，部署后永久有一个 HTTPS 链接。

### 步骤

1. 把本项目推到 **GitHub**（新建 repo → upload 或 `git push`）
2. 打开 [render.com](https://render.com) 注册（可用 GitHub 登录）
3. 点击 **New +** → **Blueprint**（或 Web Service）
4. 连接你的 GitHub repo；若用 Blueprint，会自动读项目里的 `render.yaml`
5. 选 **Free** 套餐 → **Deploy**
6. 等 5～10 分钟，会得到地址，例如：  
   `https://youtube-downloader-xxxx.onrender.com`

把这个链接发给任何人，手机/别的电脑打开就能用。

**注意（免费版）：** 15 分钟没人访问会「休眠」，第一次打开可能要等 30～60 秒唤醒。

### 其他平台

[Railway](https://railway.app)、[Fly.io](https://fly.io) 也可以，同样用项目里的 `Dockerfile` 部署。

## 手动启动（不用 start.sh）

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

默认端口 `8080`（macOS 上 5000 常被 AirPlay 占用），可改：`PORT=3000 python app.py`

## 项目结构

```
youtube_download/
├── app.py              # Flask 后端 + yt-dlp
├── static/index.html   # 前端页面（无需构建）
├── requirements.txt
├── Dockerfile
├── start.sh
└── README.md
```

## 说明

- 仅供个人学习使用，请遵守 YouTube 服务条款及当地法律
- 下载文件保存在服务器 `downloads/` 目录，约 2 小时后自动清理
- 若解析失败，请更新 yt-dlp：`pip install -U yt-dlp`
