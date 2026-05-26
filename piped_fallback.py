"""Piped API fallback when yt-dlp fails on cloud (Render) IPs."""
from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from pathlib import Path

PIPED_APIS = [
    "https://pipedapi.tokhmi.xyz",
    "https://pipedapi.syncpundit.io",
    "https://api-piped.mha.fi",
    "https://pipedapi.moomoo.me",
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi-libre.kavin.rocks",
]

INVIDIOUS_APIS = [
    "https://invidious.privacyredirect.com",
    "https://inv.nadeko.net",
    "https://yt.chocolatemoo53.com",
    "https://invidious.f5.si",
]

UA = "Mozilla/5.0 (compatible; YouTubeDownloader/1.0)"


def video_id_from_url(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else None


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read().decode()
        if not raw.strip().startswith("{"):
            raise ValueError("not json")
        return json.loads(raw)


def fetch_invidious(video_id: str) -> dict:
    """Invidious fallback when Piped instances are down."""
    last_err = None
    for base in INVIDIOUS_APIS:
        try:
            data = _fetch_json(f"{base}/api/v1/videos/{video_id}")
            formats = []
            for f in data.get("adaptiveFormats") or []:
                if f.get("type", "").startswith("video/"):
                    h = f.get("resolution", "")
                    if h.endswith("p"):
                        formats.append({"quality": h, "url": f.get("url")})
            return {
                "title": data.get("title"),
                "thumbnailUrl": data.get("videoThumbnails", [{}])[0].get("url"),
                "duration": data.get("lengthSeconds"),
                "uploader": data.get("author"),
                "videoStreams": [
                    {
                        "url": f["url"],
                        "quality": f.get("quality", "720p"),
                        "videoOnly": False,
                    }
                    for f in formats
                    if f.get("url")
                ],
                "audioStreams": [
                    {
                        "url": f.get("url"),
                        "bitrate": f.get("bitrate", 128000),
                    }
                    for f in (data.get("adaptiveFormats") or [])
                    if f.get("type", "").startswith("audio/")
                ],
            }
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Invidious 备用失败: {last_err}")


def fetch_piped(video_id: str) -> dict:
    last_err = None
    for base in PIPED_APIS:
        try:
            return _fetch_json(f"{base}/streams/{video_id}")
        except Exception as e:
            last_err = e
    try:
        return fetch_invidious(video_id)
    except Exception as e2:
        raise RuntimeError(f"Piped/Invidious 备用均失败: {last_err}; {e2}") from e2


def _parse_height(quality: str) -> int:
    m = re.match(r"(\d+)p", quality or "")
    return int(m.group(1)) if m else 0


def piped_to_formats(data: dict) -> list[dict]:
    formats = []
    seen: set[str] = set()

    for vs in data.get("videoStreams") or []:
        if vs.get("videoOnly"):
            continue
        h = _parse_height(vs.get("quality", ""))
        if h <= 0:
            continue
        key = f"video_{h}"
        if key in seen:
            continue
        seen.add(key)
        formats.append(
            {
                "id": key,
                "type": "video",
                "label": vs.get("quality", f"{h}p"),
                "quality": h,
                "ext": "mp4",
            }
        )

    if not formats:
        for vs in data.get("videoStreams") or []:
            h = _parse_height(vs.get("quality", "")) or 720
            key = f"video_{h}"
            if key in seen:
                continue
            seen.add(key)
            formats.append(
                {
                    "id": key,
                    "type": "video",
                    "label": vs.get("quality", "视频"),
                    "quality": h,
                    "ext": "mp4",
                }
            )

    formats.sort(key=lambda x: -x.get("quality", 0))
    return formats


def piped_info_dict(data: dict, video_id: str) -> dict:
    thumb = data.get("thumbnailUrl") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    uploader = data.get("uploader") or ""
    if not uploader and data.get("uploaderUrl"):
        uploader = str(data["uploaderUrl"]).rstrip("/").split("/")[-1]

    return {
        "id": video_id,
        "title": data.get("title") or "YouTube Video",
        "thumbnail": thumb,
        "duration": data.get("duration"),
        "uploader": uploader,
        "formats": piped_to_formats(data),
        "source": "piped",
    }


def pick_stream_url(data: dict, format_id: str, audio_only: bool) -> tuple[str, str | None]:
    """Return (primary_url, secondary_audio_url for merge)."""
    if audio_only:
        streams = data.get("audioStreams") or []
        if not streams:
            raise RuntimeError("没有可用音频流")
        best = max(streams, key=lambda s: s.get("bitrate", 0))
        return best["url"], None

    target_h = None
    if format_id.startswith("video_"):
        target_h = int(format_id.replace("video_", ""))

    combined = [s for s in (data.get("videoStreams") or []) if not s.get("videoOnly")]
    if combined:
        if target_h:
            for s in combined:
                if _parse_height(s.get("quality", "")) == target_h:
                    return s["url"], None
            for s in combined:
                if _parse_height(s.get("quality", "")) <= target_h:
                    return s["url"], None
        return combined[0]["url"], None

    videos = [s for s in (data.get("videoStreams") or []) if s.get("videoOnly")]
    audios = data.get("audioStreams") or []
    if not videos or not audios:
        raise RuntimeError("没有可用视频流")
    v = videos[0]
    if target_h:
        for s in videos:
            if _parse_height(s.get("quality", "")) == target_h:
                v = s
                break
    a = max(audios, key=lambda s: s.get("bitrate", 0))
    return v["url"], a["url"]


def download_file(
    url: str,
    dest: Path,
    on_progress=None,
) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(1024 * 512)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if on_progress and total > 0:
                    on_progress(min(99, int(done * 100 / total)))


def merge_av(video_path: Path, audio_path: Path, out_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c",
            "copy",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def to_mp3(src: Path, dest: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-b:a",
            "192k",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
