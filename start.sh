#!/bin/bash
# 一键启动（不需要 npm）
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "正在创建虚拟环境..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

if ! command -v ffmpeg &>/dev/null; then
  echo "警告: 未检测到 ffmpeg。MP3 和部分 MP4 合并需要安装 ffmpeg。"
  echo "  macOS: brew install ffmpeg"
  echo "  Ubuntu: sudo apt install ffmpeg"
fi

export PORT="${PORT:-8080}"
echo ""
echo "  YouTube 下载器已启动"
echo "  本机访问: http://localhost:$PORT"
echo "  局域网访问: http://$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}'):$PORT"
echo "  按 Ctrl+C 停止"
echo ""

python app.py
