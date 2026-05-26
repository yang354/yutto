#!/bin/bash
# 切换至项目根目录以进行构建
cd "$(dirname "$0")/.."

echo "📦 开始构建 yutto Web UI 镜像..."
docker build -t yutto-webui:mac-m1 -f docker/Dockerfile.webui .

echo "✅ 镜像构建成功！标签为：yutto-webui:mac-m1"
