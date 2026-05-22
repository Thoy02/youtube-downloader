FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -U "yt-dlp[default]"

COPY app.py piped_fallback.py .
COPY static ./static

RUN mkdir -p downloads

ENV PORT=8080
EXPOSE 8080

# 必须 1 个 worker：下载任务存在内存里，2 个 worker 会导致「解析成功、下载失败」
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "300", "app:app"]
