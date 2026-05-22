# 让 Render 24/7 能下载（不用开着 Mac）— 必做

> **你没开 Mac 也要能下载 → 必须完成下面步骤。**  
> 本机可以、Render 不行，几乎都是因为 **还没设置 Cookies**。

YouTube 会挡 Render 的机房 IP。**解决办法：把你浏览器登录 YouTube 的 Cookies 交给 Render**（设一次，每 1～3 个月更新一次）。

---

## 第一步：导出 Cookies（在你 Mac 上，只需几分钟）

1. 用 **Chrome** 打开并**登录** [youtube.com](https://www.youtube.com)
2. 安装扩展（任选一个）：
   - [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
3. 在 YouTube 页面点扩展 → **Export** → 得到 `cookies.txt`
4. 用文本编辑器打开 `cookies.txt`，**全选复制**（第一行应是 `# Netscape HTTP Cookie File`）

> 不要用别人的 Cookies，不要上传到 GitHub（已在 .gitignore）。

---

## 第二步：放进 Render 环境变量

1. 打开 [dashboard.render.com](https://dashboard.render.com)
2. 点你的服务 **youtube-downloader**
3. 左侧 **Environment** → **Add Environment Variable**
4. 添加：

| Key | Value |
|-----|--------|
| `YOUTUBE_COOKIES` | 粘贴整个 `cookies.txt` 内容 |

5. 点 **Save Changes**
6. 服务会**自动重新部署**，等状态变成 **Live**（约 5 分钟）

---

## 第三步：确认是否生效

浏览器打开：

```
https://你的-render地址.onrender.com/api/health
```

应看到：

```json
{"cookies": true, "ffmpeg": true, "status": "ok"}
```

若 `"cookies": false`，说明环境变量没贴对（要包含 `# Netscape HTTP Cookie File` 那行）。

---

## 第四步：再试下载

打开 Render 网站链接，粘贴 YouTube 链接 → **解析** → 下载。

---

## 常见问题

| 问题 | 处理 |
|------|------|
| 以前可以，现在又不行 | Cookies 过期，重新导出再更新 `YOUTUBE_COOKIES` |
| 变量太长贴不进去 | 改用 `YOUTUBE_COOKIES_B64`：终端执行 `base64 -i cookies.txt`（Mac），把输出贴进 Render |
| 仍有个别视频失败 | 会员专享 / 私密 / 极强地区限制，任何云端都难下 |
| 不想暴露账号 | 可用小号登录 YouTube 再导出 Cookies |

---

## 更新代码后

```bash
git add .
git commit -m "Cloud cookies support for Render"
git push
```

Render 会自动部署；**环境变量不用重设**，会保留。
