from __future__ import annotations

import base64
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

import yt_dlp

from piped_fallback import (
    download_file as piped_download_file,
    fetch_piped,
    merge_av,
    piped_info_dict,
    pick_stream_url,
    to_mp3,
    video_id_from_url,
)

app = Flask(__name__, static_folder="static", static_url_path="")
piped_cache: dict[str, dict] = {}
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Clean up old files every hour (older than 2 hours)
CLEANUP_MAX_AGE = 2 * 60 * 60


def cleanup_old_files():
    now = time.time()
    for path in DOWNLOAD_DIR.iterdir():
        if path.is_file() and now - path.stat().st_mtime > CLEANUP_MAX_AGE:
            try:
                path.unlink()
            except OSError:
                pass


def is_valid_youtube_url(url: str) -> bool:
    patterns = [
        r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/",
        r"(https?://)?(www\.)?youtube\.com/shorts/",
    ]
    return any(re.search(p, url, re.I) for p in patterns)


CACHE_DIR = BASE_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
COOKIES_PATH = BASE_DIR / "cookies.txt"
USER_COOKIES_DIR = BASE_DIR / "user_cookies"
USER_COOKIES_DIR.mkdir(exist_ok=True)
MAX_COOKIE_BYTES = 512 * 1024

# Try multiple clients; cloud (Render) often needs cookies + android/ios clients
YOUTUBE_CLIENT_SETS = [
    ["android_vr", "android", "web"],
    ["ios", "mweb"],
    ["tv_embedded", "web_safari"],
    ["android", "web"],
]


def setup_cookies() -> str | None:
    """Load cookies from env (Render) or cookies.txt — greatly improves cloud success."""
    if COOKIES_PATH.exists() and COOKIES_PATH.stat().st_size > 0:
        return str(COOKIES_PATH)

    raw = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if not raw:
        b64 = os.environ.get("YOUTUBE_COOKIES_B64", "").strip()
        if b64:
            try:
                raw = base64.b64decode(b64).decode("utf-8")
            except Exception:
                return None

    if raw and "# Netscape HTTP Cookie File" in raw:
        COOKIES_PATH.write_text(raw, encoding="utf-8")
        return str(COOKIES_PATH)
    return None


COOKIES_FILE = setup_cookies()


def cookies_configured() -> bool:
    return bool(COOKIES_FILE and Path(COOKIES_FILE).exists())


def normalize_cookie_text(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw or len(raw.encode("utf-8")) > MAX_COOKIE_BYTES:
        return None
    if "# Netscape HTTP Cookie File" not in raw and ".youtube.com" not in raw:
        return None
    return raw


def cookies_from_body(data: dict | None) -> str | None:
    if not data:
        return None
    return normalize_cookie_text(data.get("cookies", ""))


def write_user_cookie_file(raw: str, suffix: str) -> str:
    path = USER_COOKIES_DIR / f"{suffix}.txt"
    path.write_text(raw, encoding="utf-8")
    return str(path)


def cleanup_cookie_file(path: str | None) -> None:
    if not path:
        return
    try:
        p = Path(path).resolve()
        if p.parent == USER_COOKIES_DIR.resolve() and p.exists():
            p.unlink()
    except OSError:
        pass


def resolve_cookiefile(user_cookies: str | None, temp_id: str | None = None) -> str | None:
    if user_cookies:
        return write_user_cookie_file(user_cookies, temp_id or uuid.uuid4().hex[:12])
    if COOKIES_FILE:
        return COOKIES_FILE
    return None


def common_ydl_opts(
    player_clients: list[str] | None = None,
    cookiefile: str | None = None,
    **extra,
) -> dict:
    clients = player_clients or YOUTUBE_CLIENT_SETS[0]
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 60,
        "retries": 5,
        "fragment_retries": 5,
        "cachedir": str(CACHE_DIR),
        "extractor_args": {
            "youtube": {
                "player_client": clients,
                "player_skip": ["webpage"],
            }
        },
    }
    node = shutil.which("node")
    if node:
        opts["js_runtimes"] = {"node": {"path": node}}
    cf = cookiefile or COOKIES_FILE
    if cf:
        opts["cookiefile"] = cf
    opts.update(extra)
    return opts


def extract_youtube(
    url: str,
    download: bool = False,
    cookiefile: str | None = None,
    **extra,
):
    """Try several YouTube clients; optional per-user cookiefile."""
    last_err = None
    for clients in YOUTUBE_CLIENT_SETS:
        opts = common_ydl_opts(player_clients=clients, cookiefile=cookiefile, **extra)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download)
        except Exception as e:
            last_err = e
    raise last_err


def extract_video_info(url: str, cookiefile: str | None = None) -> dict:
    """yt-dlp first; Piped fallback only when no user/server cookies."""
    try:
        info = extract_youtube(
            url, download=False, skip_download=True, cookiefile=cookiefile
        )
        info["source"] = "ytdlp"
        return info
    except Exception as ytdlp_err:
        if cookiefile:
            raise ytdlp_err
        vid = video_id_from_url(url)
        if not vid:
            raise ytdlp_err
        try:
            piped = fetch_piped(vid)
            piped_cache[vid] = piped
            return piped_info_dict(piped, vid)
        except Exception:
            raise ytdlp_err


def friendly_youtube_error(err: str, user_cookies: bool = False) -> str:
    lower = err.lower()
    if user_cookies:
        cookie_hint = "\n\n请重新导出 Cookies（可能已过期），或换一支公开视频试。"
    else:
        cookie_hint = (
            "\n\n请点击页面上方「设置 YouTube 登录」，粘贴 cookies.txt（每台电脑设一次）。"
        )
    if "not available" in lower or "video unavailable" in lower:
        return (
            "YouTube 拒绝了此视频（云端 IP 限制或视频不可用）。"
            "请先在本页设置 YouTube Cookies。"
            + cookie_hint
        )
    if "sign in" in lower or "confirm your age" in lower or "not a bot" in lower:
        return "YouTube 要求登录/验证。请先在本页「设置 YouTube 登录」粘贴 Cookies。" + cookie_hint
    if "private" in lower:
        return "这是私密视频，无法下载。"
    return f"无法获取视频信息: {err}" + cookie_hint


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/health")
def health():
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    return jsonify(
        {
            "status": "ok",
            "ffmpeg": ffmpeg_ok,
            "cookies": cookies_configured(),
            "user_cookies_supported": True,
            "hint": None
            if cookies_configured()
            else "Paste cookies in the website (Plan B) or set YOUTUBE_COOKIES on Render",
        }
    )


@app.route("/api/info", methods=["POST"])
def video_info():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "请粘贴 YouTube 链接"}), 400
    if not is_valid_youtube_url(url):
        return jsonify({"error": "无效的 YouTube 链接"}), 400

    user_cookies = cookies_from_body(data)
    temp_cookie = resolve_cookiefile(user_cookies, uuid.uuid4().hex[:10])
    try:
        info = extract_video_info(url, cookiefile=temp_cookie)
    except Exception as e:
        return jsonify(
            {"error": friendly_youtube_error(str(e), user_cookies=bool(user_cookies))}
        ), 400
    finally:
        if user_cookies:
            cleanup_cookie_file(temp_cookie)

    formats = []
    seen = set()

    for f in info.get("formats") or []:
        ext = f.get("ext")
        if ext not in ("mp4", "webm", "m4a"):
            continue
        height = f.get("height")
        acodec = f.get("acodec")
        vcodec = f.get("vcodec")
        note = f.get("format_note") or ""

        if vcodec != "none" and height:
            label = f"{height}p"
            if f.get("fps") and f["fps"] > 30:
                label += f" {int(f['fps'])}fps"
            key = f"video_{height}"
            if key not in seen:
                seen.add(key)
                formats.append(
                    {
                        "id": key,
                        "type": "video",
                        "label": label,
                        "quality": height,
                        "ext": "mp4",
                    }
                )
        elif acodec != "none" and "audio" not in seen:
            seen.add("audio")
            formats.append(
                {
                    "id": "audio_best",
                    "type": "audio",
                    "label": "最佳音质",
                    "quality": 0,
                    "ext": "m4a",
                }
            )

    formats.sort(key=lambda x: (x["type"] != "video", -x.get("quality", 0)))

    return jsonify(
        {
            "id": info.get("id"),
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "formats": formats,
            "url": url,
            "source": info.get("source", "ytdlp"),
        }
    )


@app.route("/api/download", methods=["POST"])
def start_download():
    cleanup_old_files()
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    format_id = data.get("format_id") or "video_best"
    download_type = data.get("type") or "video"  # video | audio (mp3)

    if not url or not is_valid_youtube_url(url):
        return jsonify({"error": "无效的链接"}), 400

    user_cookies = cookies_from_body(data)
    if data.get("cookies") and not user_cookies:
        return jsonify({"error": "Cookies 格式无效，请粘贴完整 cookies.txt 内容"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "pending",
        "progress": 0,
        "error": None,
        "file": None,
        "user_cookies": bool(user_cookies),
        "cookies_raw": user_cookies,
    }

    thread = threading.Thread(
        target=run_download,
        args=(job_id, url, format_id, download_type),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


jobs: dict = {}


def progress_hook(job_id: str):
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            if total > 0:
                pct = min(99, int(downloaded * 100 / total))
                jobs[job_id]["progress"] = pct
                jobs[job_id]["status"] = "downloading"
        elif d["status"] == "finished":
            jobs[job_id]["progress"] = 95
            jobs[job_id]["status"] = "processing"

    return hook


def run_piped_download(
    job_id: str,
    url: str,
    format_id: str,
    download_type: str,
    title: str,
):
    vid = video_id_from_url(url)
    if not vid:
        raise RuntimeError("无效视频 ID")
    data = piped_cache.get(vid) or fetch_piped(vid)
    piped_cache[vid] = data

    audio_only = download_type == "audio" or format_id == "mp3"
    v_url, a_url = pick_stream_url(data, format_id, audio_only)

    def prog(pct):
        jobs[job_id]["progress"] = pct
        jobs[job_id]["status"] = "downloading"

    tmp_v = DOWNLOAD_DIR / f"{job_id}_v.tmp"
    tmp_a = DOWNLOAD_DIR / f"{job_id}_a.tmp"

    if audio_only:
        piped_download_file(v_url, tmp_a, on_progress=prog)
        out = DOWNLOAD_DIR / f"{job_id}.mp3"
        if shutil.which("ffmpeg"):
            to_mp3(tmp_a, out)
            tmp_a.unlink(missing_ok=True)
        else:
            tmp_a.rename(out)
    elif a_url and shutil.which("ffmpeg"):
        piped_download_file(v_url, tmp_v, on_progress=lambda p: prog(min(70, p)))
        jobs[job_id]["status"] = "processing"
        piped_download_file(a_url, tmp_a, on_progress=lambda p: prog(70 + min(25, p // 4)))
        out = DOWNLOAD_DIR / f"{job_id}.mp4"
        merge_av(tmp_v, tmp_a, out)
        tmp_v.unlink(missing_ok=True)
        tmp_a.unlink(missing_ok=True)
    else:
        out = DOWNLOAD_DIR / f"{job_id}.mp4"
        piped_download_file(v_url, out, on_progress=prog)

    safe = re.sub(r'[<>:"/\\|?*]', "", title)[:80]
    ext = out.suffix.lstrip(".")
    jobs[job_id]["file"] = str(out)
    jobs[job_id]["filename"] = f"{safe}.{ext}"
    jobs[job_id]["status"] = "done"
    jobs[job_id]["progress"] = 100


def run_download(job_id: str, url: str, format_id: str, download_type: str):
    jobs[job_id]["status"] = "downloading"
    out_base = str(DOWNLOAD_DIR / f"{job_id}")
    title = "download"
    user_cookies = jobs[job_id].get("cookies_raw")
    temp_cookie = resolve_cookiefile(user_cookies, job_id) if user_cookies else None

    try:
        extra: dict = {"outtmpl": out_base + ".%(ext)s", "progress_hooks": [progress_hook(job_id)]}
        if download_type == "audio" or format_id == "mp3":
            extra.update(
                format="bestaudio/best",
                postprocessors=[
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            )
        elif format_id.startswith("video_"):
            height = format_id.replace("video_", "")
            extra.update(
                format=f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best",
                merge_output_format="mp4",
            )
            if shutil.which("ffmpeg"):
                extra["postprocessors"] = [
                    {"key": "FFmpegVideoConvertor", "preferredformat": "mp4"}
                ]
        else:
            extra.update(
                format="bestvideo+bestaudio/best",
                merge_output_format="mp4",
            )

        info = extract_youtube(url, download=True, cookiefile=temp_cookie, **extra)
        title = info.get("title", "download")

        candidates = list(DOWNLOAD_DIR.glob(f"{job_id}.*"))
        if not candidates:
            candidates = sorted(
                DOWNLOAD_DIR.glob("*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:5]
            candidates = [p for p in candidates if job_id in p.name]

        if not candidates:
            raise FileNotFoundError("下载文件未找到")

        outfile = candidates[0]
        safe_title = re.sub(r'[<>:"/\\|?*]', "", title)[:80]
        final_name = f"{safe_title}.{outfile.suffix.lstrip('.')}"
        jobs[job_id]["file"] = str(outfile)
        jobs[job_id]["filename"] = final_name
        jobs[job_id]["status"] = "done"
        jobs[job_id]["progress"] = 100

    except Exception as ytdlp_err:
        if user_cookies:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = friendly_youtube_error(
                str(ytdlp_err), user_cookies=True
            )
            return
        vid = video_id_from_url(url)
        if not vid:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = friendly_youtube_error(str(ytdlp_err))
            return
        try:
            data = piped_cache.get(vid) or fetch_piped(vid)
            piped_cache[vid] = data
            title = data.get("title", "download")
            jobs[job_id]["status"] = "downloading"
            jobs[job_id]["progress"] = 5
            run_piped_download(job_id, url, format_id, download_type, title)
        except Exception as e2:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = friendly_youtube_error(str(e2))
    finally:
        cleanup_cookie_file(temp_cookie)
        jobs[job_id].pop("cookies_raw", None)


@app.route("/api/status/<job_id>")
def download_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(job)


@app.route("/api/file/<job_id>")
def download_file(job_id):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done" or not job.get("file"):
        return jsonify({"error": "文件不可用"}), 404

    path = Path(job["file"])
    if not path.exists():
        return jsonify({"error": "文件已过期，请重新下载"}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name=job.get("filename", path.name),
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    cleanup_old_files()
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
