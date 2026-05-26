#!/bin/bash
# yutto Web UI 启动脚本
# 确保在 yutto-main 项目根目录下运行：sh webui/start.sh

set -e
cd "$(dirname "$0")"   # 切换到 webui/ 目录

echo "🧊 yutto Web UI"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 安装 webui 依赖..."
uv sync

echo ""
echo "🚀 启动后端服务..."
echo "   访问地址 → http://localhost:8765"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
uv run python server.py
