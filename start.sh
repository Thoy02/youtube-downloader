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

# 若未指定 PORT，从 8080 起找第一个空闲端口
if [ -z "$PORT" ]; then
  for p in 8080 8081 8082 5001 5002; do
    if ! lsof -i :"$p" -sTCP:LISTEN >/dev/null 2>&1; then
      PORT=$p
      break
    fi
  done
  PORT="${PORT:-8081}"
fi

if lsof -i :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "端口 $PORT 仍被占用。可手动结束："
  echo "  lsof -i :$PORT"
  echo "  kill <PID>"
  echo "或指定其他端口： PORT=8081 ./start.sh"
  exit 1
fi

export PORT
echo ""
echo "  YouTube 下载器已启动"
echo "  本机访问: http://localhost:$PORT"
echo "  局域网访问: http://$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}'):$PORT"
echo "  按 Ctrl+C 停止"
echo ""

python app.py
