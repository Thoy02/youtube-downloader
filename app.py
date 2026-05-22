from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

import yt_dlp

app = Flask(__name__, static_folder="static", static_url_path="")
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


def get_ydl_opts(out_template: str, format_selector: str | None = None) -> dict:
    opts = {
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
    }
    if format_selector:
        opts["format"] = format_selector
    return opts


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/health")
def health():
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    return jsonify({"status": "ok", "ffmpeg": ffmpeg_ok})


@app.route("/api/info", methods=["POST"])
def video_info():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "请粘贴 YouTube 链接"}), 400
    if not is_valid_youtube_url(url):
        return jsonify({"error": "无效的 YouTube 链接"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return jsonify({"error": f"无法获取视频信息: {str(e)}"}), 400

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

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "pending", "progress": 0, "error": None, "file": None}

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


def run_download(job_id: str, url: str, format_id: str, download_type: str):
    jobs[job_id]["status"] = "downloading"
    out_base = str(DOWNLOAD_DIR / f"{job_id}")

    try:
        if download_type == "audio" or format_id == "mp3":
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": out_base + ".%(ext)s",
                "quiet": True,
                "noplaylist": True,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
                "progress_hooks": [progress_hook(job_id)],
            }
            expected_ext = "mp3"
        elif format_id.startswith("video_"):
            height = format_id.replace("video_", "")
            ydl_opts = {
                "format": f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best",
                "outtmpl": out_base + ".%(ext)s",
                "quiet": True,
                "noplaylist": True,
                "merge_output_format": "mp4",
                "progress_hooks": [progress_hook(job_id)],
            }
            if shutil.which("ffmpeg"):
                ydl_opts["postprocessors"] = [
                    {"key": "FFmpegVideoConvertor", "preferredformat": "mp4"}
                ]
            expected_ext = "mp4"
        else:
            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": out_base + ".%(ext)s",
                "quiet": True,
                "noplaylist": True,
                "merge_output_format": "mp4",
                "progress_hooks": [progress_hook(job_id)],
            }
            expected_ext = "mp4"

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "download")

        # Find output file
        candidates = list(DOWNLOAD_DIR.glob(f"{job_id}.*"))
        if not candidates:
            # yt-dlp may use different naming
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

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


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
