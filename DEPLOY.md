# 部署教程：GitHub + Render（一步一步）

## 第一步：确认本机已有 Git 提交

在项目文件夹打开终端，执行：

```bash
cd /Users/thoykarkhei/Desktop/youtube_download
git status
```

应显示 `On branch main`，且 `nothing to commit`（第一次已由助手提交好）。

---

## 第二步：在 GitHub 新建仓库

1. 浏览器打开：https://github.com/new
2. 填写：
   - **Repository name**：`youtube-downloader`（或你喜欢的名字）
   - **Description**（可选）：`YouTube MP4/MP3 downloader`
   - 选 **Public**
   - **不要**勾选 "Add a README"（本地已有文件）
3. 点 **Create repository**
4. 创建后会看到页面，记下你的 GitHub 用户名，例如 `yourname`

---

## 第三步：把代码推到 GitHub

在终端执行（把 `你的用户名` 换成真实 GitHub 用户名）：

```bash
cd /Users/thoykarkhei/Desktop/youtube_download

git remote add origin https://github.com/你的用户名/youtube-downloader.git

git push -u origin main
```

- 第一次 push 会弹出登录：用 **GitHub 账号** 或 **Personal Access Token**
- 若提示要 token：GitHub → Settings → Developer settings → Personal access tokens → 生成一个勾选 `repo` 的 token，密码处粘贴 token

成功后会看到：`Branch 'main' set up to track remote branch 'main' from 'origin'.`

---

## 第四步：注册 / 登录 Render

1. 打开：https://render.com
2. 点 **Get Started** 或 **Sign In**
3. 选 **Sign in with GitHub**（和 Vercel 一样连 GitHub 最方便）
4. 授权 Render 访问你的 GitHub

---

## 第五步：在 Render 创建网站

1. Render 控制台点 **New +** → **Blueprint**
   - 若没有 Blueprint，用：**New +** → **Web Service**
2. **Connect a repository** → 选 `youtube-downloader`
3. 若用 Blueprint：
   - Render 会自动读 `render.yaml`
   - 点 **Apply** / **Deploy Blueprint**
4. 若用手动 Web Service：
   - **Name**：`youtube-downloader`
   - **Region**：Singapore（离马来西亚较近）或 Oregon
   - **Branch**：`main`
   - **Runtime**：**Docker**
   - **Instance Type**：**Free**
   - 其余默认 → **Create Web Service**

---

## 第六步：等待部署完成

1. 点进你的 Service，看 **Logs**
2. 第一次大约 **5～15 分钟**（要下载 Docker 镜像、装 ffmpeg）
3. 状态变成 **Live** 后，顶部有链接，例如：  
   `https://youtube-downloader-xxxx.onrender.com`

复制这个链接，用手机或别的电脑打开测试。

---

## 第七步：测试网站

1. 打开 Render 给你的链接
2. 粘贴一个 YouTube 链接 → 点 **解析**
3. 选画质 → **下载 MP4** 或 **下载 MP3**

若失败，在 Render → **Logs** 里看错误；常见是免费版刚唤醒较慢，等 1 分钟再试。

---

## 以后改代码怎么更新？

改完代码后在终端：

```bash
cd /Users/thoykarkhei/Desktop/youtube_download
git add .
git commit -m "说明你改了什么"
git push
```

Render 会**自动**重新部署（和 Vercel 一样）。

---

## 常见问题

| 问题 | 处理 |
|------|------|
| `git push` 要密码 | 用 GitHub Token，不用账号密码 |
| 网站很慢 / 第一次打不开 | 免费版休眠了，等 30～60 秒 |
| MP3 失败 | Docker 里已有 ffmpeg，看 Logs 是否别的错误 |
| 想换仓库名 | GitHub 改 repo 名后，更新 `git remote set-url origin ...` |
