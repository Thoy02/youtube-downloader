# 方案 B：在网页粘贴 Cookies（每台电脑一次）

适合 Render 24/7，**不用开着 Mac**。每台笔记本/手机浏览器各设置一次。

## 步骤

1. 打开你的 Render 网站
2. 展开 **「设置 YouTube 登录」**
3. 在 Chrome 登录 [youtube.com](https://www.youtube.com)
4. 安装 [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
5. 在 YouTube 点扩展 → **Export** → 打开 `cookies.txt` → 全选复制
6. 贴到网站文本框 → **保存到本浏览器**
7. 再粘贴视频链接 → **解析** → 下载

## 说明

- Cookies 只存在**你的浏览器**（localStorage），不会进 GitHub
- 下载时临时发给服务器，用完从服务器删除
- 约 1～3 个月过期，失效后重新 Export 再保存
- **不要**把 Cookies 发给别人

## 更新代码

```bash
git add .
git commit -m "Plan B: paste cookies in browser"
git push
```
